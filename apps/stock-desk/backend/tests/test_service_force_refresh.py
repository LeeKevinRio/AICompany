"""``MarketDataService.refresh_daily_bars_live`` (ADR-0030 supplement 10 point 2, S-20a).

The forced live refresh is the ladder part of ``get_daily_bars`` walked once,
without layer 0, without any cooldown and without falling back to the cache:

* layer 0 and the cooldown are skipped (a current cache inside the cooldown is
  still asked for again);
* the written fields: ``as_of`` is the source's request time, ``fetched_at``
  and the coverage's ``last_fetched_at`` the service clock;
* a failed ask with a cache on hand is not a success, and the cache is not read
  as the answer;
* bars past the latest closed session are dropped (all dropped -> not ok);
* the incremental start, and the whole range when the cached series is refused
  by the currency gate (checkpoint ``force_refresh_cache``);
* a live answer refused by the currency gate, a failed read-back, a refused
  read-back, a raising source, a partial answer (no coverage);
* the equivalence with ``get_daily_bars`` when that one reaches the ladder:
  four starting states, the cache's three tables equal column by column;
* the AST guard: the method calls none of the layer-0 or fall-back helpers.

Every cache is a ``tmp_path`` file and every source is a fake.
"""

from __future__ import annotations

import ast
import inspect
import logging
import shutil
import textwrap
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.data.admission import admit_any_shape
from app.data.cache import CacheReadResult, PriceBarCache
from app.data.interface import Market
from app.data.service import (
    CURRENCY_DIFFERS_LOG_PREFIX,
    MERGE_READBACK_FAILED_REASON,
    CurrencyLookupError,
    LiveRefreshOutcome,
    MarketDataService,
)
from tests.force_refresh_helpers import (
    AT_22_10,
    END,
    MARKET,
    START,
    SYMBOL,
    Clock,
    FakeIndexSource,
    T,
    dump_tables,
    index_bar,
    seed,
    weekdays,
)
from tests.market_service_helpers import build_service, index_service, market_currency

SERVICE_LOGGER = "app.data.service"
SERVICE_FILE = Path(__file__).resolve().parent.parent / "app" / "data" / "service.py"
#: Every session from START to T; the last one is T.
ALL_DAYS = weekdays(START, T)
#: The fake source's own history: everything up to T.
LIVE_DAYS = ALL_DAYS
YESTERDAY = datetime(2026, 11, 17, 14, 10, tzinfo=UTC)
FORBIDDEN_HELPERS = {
    "_try_session_fresh_cache",
    "_layer_zero_answer",
    "_fall_back_to_cache",
    "_cached_result",
    "_refused_answer",
}


def _service(
    cache: PriceBarCache,
    source: FakeIndexSource,
    clock: Clock,
    *,
    backups: tuple[FakeIndexSource, ...] = (),
) -> MarketDataService:
    """The index ladder as ``deps`` builds it: ``cache_first=True``, scope index."""
    return index_service(
        primary=source, backups=backups, cache=cache, clock=clock, cache_first=True
    )


def _layers(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage().split(" layer=", 1)[1].split(" ", 1)[0]
        for record in caplog.records
        if record.name == SERVICE_LOGGER
        and record.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]


# --- layer 0 and the cooldown are skipped -------------------------------------------------------


def test_a_current_cache_inside_the_cooldown_is_still_asked_for(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    five_minutes_ago = AT_22_10 - timedelta(minutes=5)
    seed(cache, ALL_DAYS, at=five_minutes_ago, covered=(START, END), attempted=five_minutes_ago)
    source = FakeIndexSource(clock, LIVE_DAYS)
    service = _service(cache, source, clock)

    # The ladder's own entry serves this cache without asking anyone (layer 0) ...
    assert service.get_daily_bars(SYMBOL, MARKET, START, END).bars
    assert source.asked == []
    # ... the forced refresh asks once all the same.
    outcome = service.refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is True
    assert len(source.asked) == 1


def test_a_recent_failed_attempt_does_not_hold_the_refresh_back(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    # Coverage from yesterday, and a failed attempt 5 minutes ago (R-8 cooldown).
    seed(
        cache,
        weekdays(START, T - timedelta(days=1)),
        at=YESTERDAY,
        covered=(START, T - timedelta(days=1)),
        attempted=AT_22_10 - timedelta(minutes=5),
    )
    source = FakeIndexSource(clock, LIVE_DAYS)
    service = _service(cache, source, clock)

    served = service.get_daily_bars(SYMBOL, MARKET, START, END)
    assert source.asked == [] and served.bars  # the ladder serves the cache in the cooldown
    assert service.refresh_daily_bars_live(SYMBOL, MARKET, START, END).ok is True
    assert len(source.asked) == 1


# --- what is written ----------------------------------------------------------------------------


def test_the_written_fields(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    requested = AT_22_10

    def later() -> None:
        clock.tick(2)  # the answer arrives two seconds after the request

    source = FakeIndexSource(clock, LIVE_DAYS, before=later)
    service = _service(cache, source, clock)

    outcome = service.refresh_daily_bars_live(SYMBOL, MARKET, START, END)

    written = requested + timedelta(seconds=2)
    assert outcome == LiveRefreshOutcome(
        ok=True,
        source="yfinance",
        requested_at=requested,
        written_at=written,
        live_bar_count=len(LIVE_DAYS),
        live_latest_date=T,
        complete=True,
        reason=None,
    )
    rows = dump_tables(tmp_path / "cache.db")
    t_row = next(row for row in rows["price_bars_cache"] if row[2] == T.isoformat())
    assert t_row[10] == requested.isoformat()  # as_of: the request time
    assert t_row[11] == written.isoformat()  # fetched_at: the service clock
    assert rows["price_bars_fetch_log"] == [
        (SYMBOL, MARKET, START.isoformat(), END.isoformat(), written.isoformat())
    ]
    assert rows["price_bars_attempt_log"] == [(SYMBOL, MARKET, written.isoformat())]


def test_a_failed_ask_with_a_cache_on_hand_is_not_a_success(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    seed(cache, ALL_DAYS, at=YESTERDAY)
    before = dump_tables(tmp_path / "cache.db")["price_bars_cache"]
    source = FakeIndexSource(clock, LIVE_DAYS, unavailable=True)
    service = _service(cache, source, clock)

    outcome = service.refresh_daily_bars_live(SYMBOL, MARKET, START, END)

    assert outcome.ok is False
    assert outcome == LiveRefreshOutcome.failed(outcome.reason)
    assert outcome.reason  # the source's own sentence
    rows = dump_tables(tmp_path / "cache.db")
    assert rows["price_bars_cache"] == before  # nothing rewritten
    assert rows["price_bars_fetch_log"] == []
    assert rows["price_bars_attempt_log"] == [(SYMBOL, MARKET, AT_22_10.isoformat())]


def test_a_raising_source_is_not_a_success_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    source = FakeIndexSource(clock, LIVE_DAYS, raises=True)
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        outcome = _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is False and outcome.reason is not None
    assert any("unexpected provider error" in r.getMessage() for r in caplog.records)
    rows = dump_tables(tmp_path / "cache.db")
    assert rows["price_bars_cache"] == [] and rows["price_bars_fetch_log"] == []
    assert rows["price_bars_attempt_log"] == [(SYMBOL, MARKET, AT_22_10.isoformat())]


def test_a_later_rung_answers_when_the_first_fails(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    primary = FakeIndexSource(clock, LIVE_DAYS, unavailable=True)
    backup = FakeIndexSource(clock, LIVE_DAYS, source="backup_source")
    outcome = _service(cache, primary, clock, backups=(backup,)).refresh_daily_bars_live(
        SYMBOL, MARKET, START, END
    )
    assert outcome.ok is True and outcome.source == "backup_source"
    assert len(primary.asked) == len(backup.asked) == 1


# --- the unfinished session ---------------------------------------------------------------------


def test_before_the_close_the_bar_of_the_day_is_dropped(tmp_path: Path) -> None:
    at_13_00 = datetime(2026, 11, 18, 5, 0, tzinfo=UTC)  # 13:00 Taipei on T
    clock = Clock(at_13_00)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    outcome = _service(cache, FakeIndexSource(clock, LIVE_DAYS), clock).refresh_daily_bars_live(
        SYMBOL, MARKET, START, END
    )
    assert outcome.ok is True
    assert outcome.live_latest_date == T - timedelta(days=1)
    assert outcome.live_bar_count == len(LIVE_DAYS) - 1
    dates = [row[2] for row in dump_tables(tmp_path / "cache.db")["price_bars_cache"]]
    assert T.isoformat() not in dates


def test_at_22_10_the_bar_of_the_day_is_kept(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    outcome = _service(cache, FakeIndexSource(clock, LIVE_DAYS), clock).refresh_daily_bars_live(
        SYMBOL, MARKET, START, END
    )
    assert outcome.ok is True and outcome.live_latest_date == T


def test_an_answer_left_with_no_bar_is_not_a_success(tmp_path: Path) -> None:
    at_13_00 = datetime(2026, 11, 18, 5, 0, tzinfo=UTC)
    clock = Clock(at_13_00)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    outcome = _service(cache, FakeIndexSource(clock, [T]), clock).refresh_daily_bars_live(
        SYMBOL, MARKET, START, END
    )
    assert outcome.ok is False
    rows = dump_tables(tmp_path / "cache.db")
    assert rows["price_bars_cache"] == [] and rows["price_bars_fetch_log"] == []


# --- where the live ask starts ------------------------------------------------------------------


def test_a_covered_cache_narrows_the_ask_to_the_last_cached_month(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    t_minus_1 = T - timedelta(days=1)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))
    source = FakeIndexSource(clock, LIVE_DAYS)
    outcome = _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is True
    assert source.asked == [(SYMBOL, t_minus_1.replace(day=1), END)]
    # Every row of that month is rewritten by this ask; the head keeps yesterday's stamp.
    rows = dump_tables(tmp_path / "cache.db")["price_bars_cache"]
    for row in rows:
        stamped = AT_22_10 if str(row[2]) >= T.replace(day=1).isoformat() else YESTERDAY
        assert row[10] == stamped.isoformat()
    assert dump_tables(tmp_path / "cache.db")["price_bars_fetch_log"] == [
        (SYMBOL, MARKET, START.isoformat(), END.isoformat(), AT_22_10.isoformat())
    ]


def test_without_coverage_the_whole_range_is_asked_for(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    seed(cache, weekdays(START, T - timedelta(days=1)), at=YESTERDAY)
    source = FakeIndexSource(clock, LIVE_DAYS)
    assert _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END).ok
    assert source.asked == [(SYMBOL, START, END)]


def test_a_refused_cached_series_is_asked_for_in_full(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    t_minus_1 = T - timedelta(days=1)
    # Covered (so the ask would be narrowed) but declared in another unit.
    seed(
        cache,
        weekdays(START, t_minus_1),
        at=YESTERDAY,
        currency="USD",
        covered=(START, t_minus_1),
    )
    source = FakeIndexSource(clock, LIVE_DAYS)
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        outcome = _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is True
    assert source.asked == [(SYMBOL, START, END)]
    assert _layers(caplog) == ["force_refresh_cache"]
    currencies = {row[8] for row in dump_tables(tmp_path / "cache.db")["price_bars_cache"]}
    assert currencies == {"TWD"}  # every refused row overwritten


# --- the currency gate on the live answer -------------------------------------------------------


def test_a_live_answer_in_another_unit_is_refused_and_nothing_is_written(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    source = FakeIndexSource(clock, LIVE_DAYS, currency="USD")
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        outcome = _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is False
    assert _layers(caplog) == ["provider"]
    rows = dump_tables(tmp_path / "cache.db")
    assert rows["price_bars_cache"] == [] and rows["price_bars_fetch_log"] == []
    assert rows["price_bars_attempt_log"] == [(SYMBOL, MARKET, AT_22_10.isoformat())]


def test_after_a_refused_live_answer_the_next_rung_is_asked_for_the_whole_range(
    tmp_path: Path,
) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    t_minus_1 = T - timedelta(days=1)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))
    primary = FakeIndexSource(clock, LIVE_DAYS, currency="USD")
    backup = FakeIndexSource(clock, LIVE_DAYS, source="backup_source")
    outcome = _service(cache, primary, clock, backups=(backup,)).refresh_daily_bars_live(
        SYMBOL, MARKET, START, END
    )
    assert outcome.ok is True
    assert primary.asked == [(SYMBOL, t_minus_1.replace(day=1), END)]
    assert backup.asked == [(SYMBOL, START, END)]


def test_a_lookup_that_cannot_answer_raises(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    answers = {"armed": False}

    def lookup(market: Market) -> str | None:
        return None if answers["armed"] else market_currency(market)

    service = build_service(
        primary=FakeIndexSource(clock, LIVE_DAYS),
        cache=cache,
        scope="index",
        currency_for_market=lookup,
        clock=clock,
        cache_first=True,
    )
    answers["armed"] = True
    with pytest.raises(CurrencyLookupError):
        service.refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert dump_tables(tmp_path / "cache.db")["price_bars_cache"] == []


def test_a_symbol_the_admission_refuses_asks_nothing(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    source = FakeIndexSource(clock, LIVE_DAYS)
    service = build_service(
        primary=source,
        cache=cache,
        scope="index",
        clock=clock,
        cache_first=True,
        admission=lambda symbol, market: False,
    )
    outcome = service.refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is False and source.asked == []
    assert all(rows == [] for rows in dump_tables(tmp_path / "cache.db").values())
    assert admit_any_shape(SYMBOL, MARKET)  # the production index admission lets it through


# --- the read-back ------------------------------------------------------------------------------


class _HeadlessCache(PriceBarCache):
    """Answers the first read, then loses the cached head (the read-back returns ``None``)."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path=db_path)
        self.reads = 0

    def get(self, *args: object, **kwargs: object) -> CacheReadResult | None:
        self.reads += 1
        if self.reads > 1:
            return None
        return super().get(*args, **kwargs)  # type: ignore[arg-type]


def test_a_failed_read_back_is_not_a_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock(AT_22_10)
    cache = _HeadlessCache(tmp_path / "cache.db")
    t_minus_1 = T - timedelta(days=1)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        outcome = _service(cache, FakeIndexSource(clock, LIVE_DAYS), clock).refresh_daily_bars_live(
            SYMBOL, MARKET, START, END
        )
    assert outcome.ok is False
    assert outcome.reason == MERGE_READBACK_FAILED_REASON
    rows = dump_tables(tmp_path / "cache.db")
    # As in the ladder: the tail was already written; the coverage is not widened.
    assert rows["price_bars_fetch_log"] == [
        (SYMBOL, MARKET, START.isoformat(), t_minus_1.isoformat(), YESTERDAY.isoformat())
    ]


def test_a_refused_read_back_is_not_a_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    t_minus_1 = T - timedelta(days=1)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))

    def foreign_head() -> None:
        # Another writer puts an off-unit head bar between the two reads.
        cache.put(
            [index_bar(START + timedelta(days=1), as_of=YESTERDAY, currency="USD")],
            source="yfinance",
            fetched_at=YESTERDAY,
        )

    source = FakeIndexSource(clock, LIVE_DAYS, before=foreign_head)
    with caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        outcome = _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is False
    assert _layers(caplog) == ["incremental_readback"]
    assert dump_tables(tmp_path / "cache.db")["price_bars_fetch_log"][0][3] == t_minus_1.isoformat()


# --- a partial answer ---------------------------------------------------------------------------


def test_a_partial_answer_is_written_without_coverage(tmp_path: Path) -> None:
    clock = Clock(AT_22_10)
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    source = FakeIndexSource(clock, LIVE_DAYS, complete=False)
    outcome = _service(cache, source, clock).refresh_daily_bars_live(SYMBOL, MARKET, START, END)
    assert outcome.ok is True and outcome.complete is False
    rows = dump_tables(tmp_path / "cache.db")
    assert len(rows["price_bars_cache"]) == len(LIVE_DAYS)
    assert rows["price_bars_fetch_log"] == []


# --- T-EQ: the copy of the ladder does not drift ------------------------------------------------


def _empty(cache: PriceBarCache) -> None:
    return None


def _covered_incremental(cache: PriceBarCache) -> None:
    # Covered through T-1 by yesterday's fetch, outside every cooldown: layer 0
    # judges REFETCH and the ladder asks from T-1's month.
    t_minus_1 = T - timedelta(days=1)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))


def _cache_refused(cache: PriceBarCache) -> None:
    # Declared in another unit, no recent attempt: layer 0 refuses outside the
    # cooldown and the ladder asks for the whole range.
    t_minus_1 = T - timedelta(days=1)
    seed(
        cache,
        weekdays(START, t_minus_1),
        at=YESTERDAY,
        currency="USD",
        covered=(START, t_minus_1),
    )


#: name -> (seeding, source currency)
EQUIVALENCE_STATES: dict[str, tuple[Callable[[PriceBarCache], None], str]] = {
    "empty-cache": (_empty, "TWD"),
    "covered-incremental": (_covered_incremental, "TWD"),
    "cache-refused": (_cache_refused, "TWD"),
    "live-refused": (_empty, "USD"),
}


@pytest.mark.parametrize("state", list(EQUIVALENCE_STATES))
def test_t_eq_the_refresh_writes_what_the_ladder_writes(tmp_path: Path, state: str) -> None:
    seeding, currency = EQUIVALENCE_STATES[state]
    seeded = tmp_path / "seeded.db"
    seeding(PriceBarCache(db_path=seeded))
    (tmp_path / "ladder").mkdir()
    (tmp_path / "refresh").mkdir()
    ladder_db = tmp_path / "ladder" / "cache.db"
    refresh_db = tmp_path / "refresh" / "cache.db"
    shutil.copyfile(seeded, ladder_db)
    shutil.copyfile(seeded, refresh_db)
    assert dump_tables(ladder_db) == dump_tables(refresh_db)

    ladder_clock, refresh_clock = Clock(AT_22_10), Clock(AT_22_10)
    ladder_source = FakeIndexSource(
        ladder_clock, LIVE_DAYS, currency=currency, before=lambda: ladder_clock.tick(2)
    )
    refresh_source = FakeIndexSource(
        refresh_clock, LIVE_DAYS, currency=currency, before=lambda: refresh_clock.tick(2)
    )
    ladder = _service(PriceBarCache(db_path=ladder_db), ladder_source, ladder_clock)
    refresh = _service(PriceBarCache(db_path=refresh_db), refresh_source, refresh_clock)

    answer = ladder.get_daily_bars(SYMBOL, MARKET, START, END)
    outcome = refresh.refresh_daily_bars_live(SYMBOL, MARKET, START, END)

    # The ladder really ran (layer 0 did not answer), asking exactly what the refresh asked.
    assert len(ladder_source.asked) == 1
    assert ladder_source.asked == refresh_source.asked
    assert outcome.ok is bool(answer.bars)
    assert dump_tables(ladder_db) == dump_tables(refresh_db)
    if state == "live-refused":
        assert dump_tables(refresh_db)["price_bars_cache"] == []
    else:
        assert dump_tables(refresh_db)["price_bars_fetch_log"] != []


def test_t_eq_compares_every_column() -> None:
    # The dump is ``SELECT *``: a change in any column of any of the three tables shows.
    source = inspect.getsource(dump_tables)
    assert "SELECT * FROM" in source


# --- AST: no layer-0 or fall-back helper --------------------------------------------------------


def _called_names(function: ast.FunctionDef) -> set[str]:
    return {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    }


def _method(tree: ast.Module, cls: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
    raise AssertionError(f"{cls}.{name} not found")


def test_the_refresh_calls_no_layer_zero_or_fall_back_helper() -> None:
    tree = ast.parse(SERVICE_FILE.read_text(encoding="utf-8"))
    method = _method(tree, "MarketDataService", "refresh_daily_bars_live")
    called = _called_names(method)
    assert called & FORBIDDEN_HELPERS == set()
    # The helpers it is allowed to reuse are the ladder's own.
    assert {"_refuse_unadmitted", "_cache_refuses", "_incremental_start", "_try_provider"} <= called


def test_the_helper_scan_has_teeth() -> None:
    for helper in sorted(FORBIDDEN_HELPERS):
        source = textwrap.dedent(
            f"""
            class MarketDataService:
                def refresh_daily_bars_live(self):
                    return self.{helper}()
            """
        )
        method = _method(ast.parse(source), "MarketDataService", "refresh_daily_bars_live")
        assert _called_names(method) & FORBIDDEN_HELPERS == {helper}


def test_the_ladder_entry_still_uses_layer_zero_and_the_fall_back() -> None:
    # The scan reads the right file: the ladder entry next to it does call them.
    tree = ast.parse(SERVICE_FILE.read_text(encoding="utf-8"))
    called = _called_names(_method(tree, "MarketDataService", "get_daily_bars"))
    assert {"_try_session_fresh_cache", "_fall_back_to_cache", "_refused_answer"} <= called
