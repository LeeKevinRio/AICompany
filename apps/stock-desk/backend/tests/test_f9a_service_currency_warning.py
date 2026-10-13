"""F-9a / F-9b0 / F-9b: the service's off-market currency record, checkpoint by checkpoint.

Each scenario drives ``MarketDataService`` down one path that obtains bars
(a live provider, the incremental read-back, layer 0, the degrade-to-cache
rung, the cache-only read). For a checkpoint that is still observed only, it
runs twice on identical fresh databases -- once with the currency check live,
once with the check neutralised (its verdict forced to ``ok`` at every
checkpoint) -- and the returned result, every cache table and every live call
must come out identical; only the log differs.

F-9b0 (ADR-0024 TA5 R-60) extended the record with ``verdict`` and ``scope``
and logs ``scope=index`` at ERROR. The matrix below is TA5 section 2 test 6 and
the fixed-text test is test 1. Test 5 (the shipped index wiring logs nothing)
replaced ``test_index_ladder_is_explicitly_not_checked`` and lives in
``test_f9b0_index_currency_tripwire.py``.

F-9b commit 5 gates the live rung (ADR-0024 D-2): the ``provider`` checkpoint
now refuses (its record unchanged), and the incremental scenario's off-market
bar sits in the cached head, where only the read-back sees it. F-9b commit 6
gates every cache checkpoint (D-2 (5)), so no checkpoint is "observation only"
any more: each test below pins the record *and* the refusal, and the
neutralised run is kept only to show that no cached row is deleted. The
refusals themselves are pinned in ``test_f9b_live_currency_gate.py`` and
``test_f9b_cache_currency_gate.py``.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.api import deps
from app.data import service as service_module
from app.data.cache import PriceBarCache
from app.data.gate_wording import CACHE_UNIT_REJECTED_REASON
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.quality import CurrencyVerdict
from app.data.service import (
    CURRENCY_DIFFERS_LOG_PREFIX,
    CurrencyLookup,
    CurrencyLookupError,
    MarketDataService,
    ServiceScope,
)
from app.positions.models import MARKET_CURRENCY
from tests.market_service_helpers import build_service, market_currency

SERVICE_LOGGER = "app.data.service"


def _bar(
    day: date, currency: str, source: str, *, symbol: str = "2330", market: Market = "TW"
) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market=market,
        date=day,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        currency=currency,
        as_of=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        source=source,
    )


def _blank_bar(day: date, currency: str) -> PriceBar:
    """A bar declaring ``currency`` verbatim, blank included (``PriceBar`` refuses blanks today)."""
    return _bar(day, "TWD", "twse").model_copy(update={"currency": currency})


class _Provider(MarketDataProvider):
    source_id = "stub"

    def __init__(self, label: str, bars: list[PriceBar]) -> None:
        self._label = label
        self._bars = bars
        self.asked: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((symbol, start, end))
        return ProviderResult(
            bars=self._bars,
            status=DataStatus.FRESH if self._bars else DataStatus.UNAVAILABLE,
            as_of=datetime(2024, 1, 3, 8, 0, tzinfo=UTC),
            source=self._label,
            staleness_minutes=0 if self._bars else None,
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    #: Seeds the cache; receives the off-market currency under test.
    seed: Callable[[PriceBarCache, str], None]
    #: What the primary returns, given that currency.
    primary_bars: Callable[[str], list[PriceBar]]
    cache_first: bool
    clock: datetime
    call: Callable[[MarketDataService], ProviderResult]
    #: Layers whose record is expected when the currency is off-market.
    layers: tuple[str, ...]
    #: How many checkpoints judge bars on this path (the neutralised baseline
    #: must stand at each of them). Equals ``len(layers)`` unless a checkpoint
    #: judges market-currency bars and so writes no record.
    checkpoints: int = 0

    @property
    def judged(self) -> int:
        return self.checkpoints or len(self.layers)


def _no_seed(_cache: PriceBarCache, _currency: str) -> None:
    return None


def _seed_one(cache: PriceBarCache, currency: str) -> None:
    cache.put(
        [_bar(date(2024, 1, 2), currency, "twse")],
        source="twse",
        fetched_at=datetime(2024, 1, 2, 7, 0, tzinfo=UTC),
    )


def _seed_layer_zero(cache: PriceBarCache, currency: str) -> None:
    _seed_one(cache, currency)
    cache.record_fetch(
        "2330",
        "TW",
        start=date(2024, 1, 1),
        end=date(2024, 1, 2),
        fetched_at=datetime(2024, 1, 2, 7, 40, tzinfo=UTC),
    )


def _seed_incremental(cache: PriceBarCache, currency: str) -> None:
    # A TWD head in November, the off-market bar at the end of December.
    cache.put(
        [_bar(date(2023, 11, 30), "TWD", "twse"), _bar(date(2023, 12, 29), currency, "twse")],
        source="twse",
        fetched_at=datetime(2023, 12, 29, 8, 0, tzinfo=UTC),
    )
    cache.record_fetch(
        "2330",
        "TW",
        start=date(2023, 11, 1),
        end=date(2023, 12, 29),
        fetched_at=datetime(2023, 12, 29, 8, 0, tzinfo=UTC),
    )


SCENARIOS = [
    Scenario(
        name="provider",
        seed=_no_seed,
        primary_bars=lambda c: [_bar(date(2024, 1, 2), c, "twse")],
        cache_first=False,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("provider",),
    ),
    Scenario(
        name="incremental",
        seed=_seed_incremental,
        # F-9b commit 5: the live tail carries the market currency (an off-market
        # tail is now refused at the provider checkpoint); the off-market bar is
        # the cached head's, which only the read-back sees.
        primary_bars=lambda c: [_bar(date(2024, 1, 3), "TWD", "twse")],
        cache_first=True,
        clock=datetime(2024, 1, 3, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2023, 11, 1), date(2024, 1, 31)),
        layers=("incremental_readback",),
        checkpoints=3,
    ),
    Scenario(
        name="layer0",
        seed=_seed_layer_zero,
        primary_bars=lambda c: [],
        cache_first=True,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("layer0_cache",),
    ),
    Scenario(
        name="fallback",
        seed=_seed_one,
        primary_bars=lambda c: [],
        cache_first=False,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("fallback_cache",),
    ),
    Scenario(
        name="cache_only",
        seed=_seed_one,
        primary_bars=lambda c: [],
        cache_first=False,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_cached_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("cache_only",),
    ),
]

#: The checkpoints still observed only (the cache gate is F-9b commit 6).
CACHE_SCENARIOS = [scenario for scenario in SCENARIOS if scenario.name != "provider"]
#: The live rung, gated since F-9b commit 5.
LIVE_SCENARIO = SCENARIOS[0]

#: The live path with a blank declaration beside a matching bar. Only the live
#: rung can carry a blank before F-9c: the cache cannot read one back.
BLANK_PROVIDER = Scenario(
    name="blank_provider",
    seed=_no_seed,
    primary_bars=lambda c: [
        _blank_bar(date(2024, 1, 2), c),
        _bar(date(2024, 1, 3), "TWD", "twse"),
    ],
    cache_first=False,
    clock=datetime(2024, 1, 3, 8, 0, tzinfo=UTC),
    call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
    layers=("provider",),
)


def _dump(db: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(db)) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
            for table in ("price_bars_cache", "price_bars_fetch_log", "price_bars_attempt_log")
        }


@dataclass(frozen=True)
class Run:
    result: ProviderResult
    tables: dict[str, list[tuple[Any, ...]]]
    #: Every record carrying the prefix, at any level: ``(levelno, message)``.
    records: list[tuple[int, str]]
    primary_asked: list[tuple[str, date, date]]

    @property
    def warnings(self) -> list[str]:
        return [message for _level, message in self.records]


def _run(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    scenario: Scenario,
    *,
    currency: str,
    lookup: CurrencyLookup = market_currency,
    scope: ServiceScope = "equity",
    tag: str = "checked",
    after_build: Callable[[], None] = lambda: None,
) -> Run:
    db = tmp_path / f"{scenario.name}-{currency.strip() or 'blank'}-{scope}-{tag}.db"
    cache = PriceBarCache(db_path=db)
    scenario.seed(cache, currency)
    primary = _Provider("twse", scenario.primary_bars(currency))
    service = build_service(
        primary=primary,
        cache=cache,
        clock=lambda: scenario.clock,
        cache_first=scenario.cache_first,
        currency_for_market=lookup,
        scope=scope,
    )
    after_build()
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=SERVICE_LOGGER):
        result = scenario.call(service)
    records = [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if record.name == SERVICE_LOGGER
        and record.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]
    return Run(result, _dump(db), records, primary.asked)


def _neutral_run(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    scenario: Scenario,
    *,
    currency: str,
    scope: ServiceScope = "equity",
) -> Run:
    """The baseline: the same service with the verdict forced to ``ok`` at every checkpoint."""
    calls: list[str] = []

    def always_ok(bars: object, expected: str) -> CurrencyVerdict:
        calls.append(expected)
        return "ok"

    with monkeypatch.context() as patch:
        patch.setattr(service_module, "classify_currency", always_ok)
        run = _run(tmp_path, caplog, scenario, currency=currency, scope=scope, tag="neutral")
    # Not vacuous: the neutralised check really stood at every checkpoint.
    assert len(calls) == scenario.judged
    return run


def _field(message: str, name: str) -> str:
    return message.split(f" {name}=")[1].split(" ")[0]


def _layer(message: str) -> str:
    return _field(message, "layer")


#: The checkpoints each cache scenario's refusal is recorded at (F-9b commit 6).
#: Layer 0 refused outside the R-8 cooldown runs the ladder, which fails here,
#: so the degrade-to-cache rung judges the same rows again (TA5 section 2 test 2).
#: In the incremental scenario layer 0 now judges the whole cached range first
#: (D-2 (5)(a)), refuses the off-market head and asks the live rung for the
#: whole range, which answers: the self-repair of ADR-0024 壞處 5, not a
#: refusal. (The read-back refusal needs a write between the two reads; it is
#: pinned in ``test_f9b_cache_currency_gate.py``.)
REFUSED_LAYERS = {
    "incremental": ("layer0_cache",),
    "layer0": ("layer0_cache", "fallback_cache"),
    "fallback": ("fallback_cache",),
    "cache_only": ("cache_only",),
}
SELF_REPAIRED = {"incremental"}


@pytest.mark.parametrize("scenario", CACHE_SCENARIOS, ids=lambda s: s.name)
def test_off_market_currency_on_each_cache_path_is_refused_with_its_record(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    scenario: Scenario,
) -> None:
    """TA5 test 6: equity, one WARNING per refusing checkpoint; the refusal is T-15.

    Rewritten for F-9b commit 6 (was
    ``test_off_market_currency_warns_on_each_path_and_changes_nothing``): the
    cache checkpoints now refuse. No cached row is deleted (D-8): the
    cache table equals the neutralised run's.
    """
    checked = _run(tmp_path, caplog, scenario, currency="USD")
    neutral = _neutral_run(tmp_path, caplog, monkeypatch, scenario, currency="USD")

    layers = REFUSED_LAYERS[scenario.name]
    assert [_layer(message) for message in checked.warnings] == list(layers)
    assert [level for level, _ in checked.records] == [logging.WARNING] * len(layers)
    assert {_field(m, "scope") for m in checked.warnings} == {"equity"}
    assert {_field(m, "verdict") for m in checked.warnings} == {"mismatch"}
    if scenario.name in SELF_REPAIRED:
        _assert_self_repaired(checked, scenario)
    else:
        assert checked.result.bars == []
        assert checked.result.status is DataStatus.UNAVAILABLE
        assert checked.result.rejection == "cache_unit_rejected"
        assert checked.result.reason == CACHE_UNIT_REJECTED_REASON
        assert checked.tables["price_bars_cache"] == neutral.tables["price_bars_cache"]


def _assert_self_repaired(checked: Run, scenario: Scenario) -> None:
    """The live rung was asked for the whole range and only its own bars came back."""
    assert checked.primary_asked == [("2330", date(2023, 11, 1), date(2024, 1, 31))]
    assert checked.result.bars == scenario.primary_bars("USD")
    assert checked.result.rejection is None


@pytest.mark.parametrize("scope", ["equity", "index"])
def test_off_market_currency_on_the_live_rung_is_refused_with_the_same_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scope: ServiceScope
) -> None:
    """F-9b commit 5: the provider checkpoint's record is unchanged, and the rung declines."""
    checked = _run(tmp_path, caplog, LIVE_SCENARIO, currency="USD", scope=scope)

    assert [_layer(message) for message in checked.warnings] == ["provider"]
    level = logging.ERROR if scope == "index" else logging.WARNING
    assert [lvl for lvl, _ in checked.records] == [level]
    assert checked.result.bars == []
    assert checked.result.rejection == "unit_mismatch"
    assert checked.tables["price_bars_cache"] == []
    assert checked.tables["price_bars_fetch_log"] == []
    assert len(checked.tables["price_bars_attempt_log"]) == 1
    assert len(checked.primary_asked) == 1


@pytest.mark.parametrize("scenario", CACHE_SCENARIOS, ids=lambda s: s.name)
def test_index_scope_logs_error_on_each_cache_path_and_refuses_without_wording(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    scenario: Scenario,
) -> None:
    """TA5 R-60 / D-4: the same checkpoints on ``scope=index`` log ERROR and refuse.

    Rewritten for F-9b commit 6 (was
    ``test_index_scope_logs_error_on_each_path_and_changes_nothing``): the
    index path adds no sentence of its own (D-4 (c)); these scenarios' rungs
    state none either, so the reason is ``None``.
    """
    checked = _run(tmp_path, caplog, scenario, currency="USD", scope="index")
    neutral = _neutral_run(tmp_path, caplog, monkeypatch, scenario, currency="USD", scope="index")

    layers = REFUSED_LAYERS[scenario.name]
    assert [_layer(message) for message in checked.warnings] == list(layers)
    assert [level for level, _ in checked.records] == [logging.ERROR] * len(layers)
    assert {_field(m, "scope") for m in checked.warnings} == {"index"}
    if scenario.name in SELF_REPAIRED:
        _assert_self_repaired(checked, scenario)
    else:
        assert checked.result.bars == []
        assert checked.result.rejection == "cache_unit_rejected"
        assert checked.result.reason is None
        assert checked.tables["price_bars_cache"] == neutral.tables["price_bars_cache"]


class _ForgetfulLookup:
    """Answers while the service is built, then has no currency for any market.

    A lookup with no currency at construction is refused there (C-35 (b),
    ``test_f9b_live_currency_gate.py``); this one reaches the checkpoints.
    """

    def __init__(self) -> None:
        self.forget = False

    def __call__(self, market: Market) -> str | None:
        return None if self.forget else MARKET_CURRENCY[market]

    def forget_now(self) -> None:
        self.forget = True


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_a_market_without_a_currency_raises_at_every_checkpoint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scenario: Scenario
) -> None:
    """C-35 (c), 風控 F9W-39: raised after its record; no row and no coverage written.

    Rewritten for C-35 (d) (was
    ``test_a_market_without_a_currency_counts_as_mismatch_and_changes_nothing``,
    split at commit 5): the lookup answers at construction and forgets
    afterwards; every checkpoint now raises instead of logging and serving.
    """
    lookup = _ForgetfulLookup()
    with pytest.raises(CurrencyLookupError):
        _run(
            tmp_path,
            caplog,
            scenario,
            currency="TWD",
            lookup=lookup,
            after_build=lookup.forget_now,
        )
    records = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]
    assert len(records) == 1
    assert _field(records[0], "expected") == "<none>"
    tables = _dump(tmp_path / f"{scenario.name}-TWD-equity-checked.db")
    fresh = PriceBarCache(db_path=tmp_path / "fresh.db")
    scenario.seed(fresh, "TWD")
    seeded = _dump(tmp_path / "fresh.db")
    for table in ("price_bars_cache", "price_bars_fetch_log"):
        assert tables[table] == seeded[table]


def test_a_blank_currency_logs_verdict_missing_and_is_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``missing`` on the live path, the only one a blank value can reach before F-9c.

    Rewritten for F-9b commit 5: the record is unchanged and the rung now
    declines (W-c'), so nothing is cached.
    """
    checked = _run(tmp_path, caplog, BLANK_PROVIDER, currency="")

    assert [_field(m, "verdict") for m in checked.warnings] == ["missing"]
    assert checked.result.bars == []
    assert checked.result.rejection == "unit_missing"
    assert checked.tables["price_bars_cache"] == []
    assert checked.tables["price_bars_fetch_log"] == []


@pytest.mark.parametrize("scope", ["equity", "index"])
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_market_currency_bars_log_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scenario: Scenario, scope: ServiceScope
) -> None:
    clean = _run(tmp_path, caplog, scenario, currency="TWD", scope=scope)
    assert clean.warnings == []
    assert clean.result.bars


def test_warning_text_is_fixed(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """TA5 R-60 test 1: an equity WARNING, an index ERROR, a ``missing`` with ``<blank>``."""
    equity = _run(tmp_path, caplog, SCENARIOS[0], currency="USD")
    assert equity.records == [
        (
            logging.WARNING,
            "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
            "observed=USD mismatched=1/1 layer=provider source=twse "
            "verdict=mismatch scope=equity",
        )
    ]
    index = _run(tmp_path, caplog, SCENARIOS[0], currency="USD", scope="index")
    assert index.records == [
        (
            logging.ERROR,
            "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
            "observed=USD mismatched=1/1 layer=provider source=twse "
            "verdict=mismatch scope=index",
        )
    ]
    blank = _run(tmp_path, caplog, BLANK_PROVIDER, currency="  ")
    assert blank.records == [
        (
            logging.WARNING,
            "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
            "observed=<blank>,TWD mismatched=1/2 layer=provider source=twse "
            "verdict=missing scope=equity",
        )
    ]
    incremental = _run(tmp_path, caplog, SCENARIOS[1], currency="USD")
    # F-9b commit 5: the live tail is TWD now, so only the cached head differs;
    # F-9b commit 6: layer 0 judges that head first (D-2 (5)(a)).
    assert incremental.warnings == [
        "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
        "observed=TWD,USD mismatched=1/2 layer=layer0_cache source=twse "
        "verdict=mismatch scope=equity"
    ]


def test_mismatch_wins_over_blank_in_the_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``verdict`` follows D-2 (1)'s order; ``observed`` keeps raw case, blanks as ``<blank>``."""
    mixed = Scenario(
        name="mixed",
        seed=_no_seed,
        primary_bars=lambda c: [
            _blank_bar(date(2024, 1, 2), ""),
            _blank_bar(date(2024, 1, 3), " "),
            _bar(date(2024, 1, 4), "usd", "twse"),
        ],
        cache_first=False,
        clock=datetime(2024, 1, 4, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("provider",),
    )
    run = _run(tmp_path, caplog, mixed, currency="mixed")
    assert run.warnings == [
        "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
        "observed=<blank>,usd mismatched=3/3 layer=provider source=twse "
        "verdict=mismatch scope=equity"
    ]


@pytest.mark.parametrize("scope", ["equity", "index"])
def test_warning_is_one_record_at_warning_level(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scope: ServiceScope
) -> None:
    _run(tmp_path, caplog, SCENARIOS[0], currency="USD", scope=scope)
    records = [r for r in caplog.records if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)]
    assert len(records) == 1
    assert records[0].levelno == (logging.ERROR if scope == "index" else logging.WARNING)
    assert records[0].name == SERVICE_LOGGER
    assert records[0].exc_info is None


# --- assembly layer (deps.py) --------------------------------------------------


class _IndexSource:
    """Stands in for the yfinance adapter in both of its roles."""

    source_id = "yfinance"

    def __init__(self, currency: str) -> None:
        self._currency = currency

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=datetime(2024, 1, 2, tzinfo=UTC),
            source="yfinance",
            staleness_minutes=None,
        )

    def get_index_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        bar = _bar(date(2024, 1, 2), self._currency, "yfinance", symbol=symbol, market="US")
        return ProviderResult(
            bars=[bar],
            status=DataStatus.BACKUP,
            as_of=datetime(2024, 1, 2, tzinfo=UTC),
            source="yfinance",
            staleness_minutes=0,
        )


@pytest.fixture
def stub_wiring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "wiring.db")
    source = _IndexSource("GBP")
    monkeypatch.setattr(deps, "_default_cache", lambda: cache)
    monkeypatch.setattr(deps, "_default_yfinance", lambda: source)
    for name, market in (
        ("TwseAdapter", "TW"),
        ("TpexAdapter", "TW"),
        ("FinMindAdapter", "TW"),
        ("AlphaVantageAdapter", "US"),
    ):
        bars = [_bar(date(2024, 1, 2), "GBP", "stub", market=market)]  # type: ignore[arg-type]
        monkeypatch.setattr(deps, name, lambda bars=bars: _Provider("stub", bars))


@pytest.mark.usefixtures("stub_wiring")
@pytest.mark.parametrize("market", ["TW", "US"])
def test_equity_ladders_are_told_their_market_currency(
    caplog: pytest.LogCaptureFixture, market: Market
) -> None:
    resolver = deps._default_resolver.__wrapped__()  # bypass lru_cache
    # F-9b commit 7: a symbol each ladder's admission asks about ("2330" is not
    # a US shape, D-4).
    symbol = "2330" if market == "TW" else "AAPL"
    with caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER):
        resolver[market].get_daily_bars(symbol, market, date(2024, 1, 1), date(2024, 1, 2))
    records = [
        r
        for r in caplog.records
        if r.name == SERVICE_LOGGER and r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]
    assert any(f" expected={MARKET_CURRENCY[market]} " in r.getMessage() for r in records)
    # F-9b0: the shipped equity ladders are ``scope=equity`` and log at WARNING.
    assert {r.levelno for r in records} == {logging.WARNING}
    assert all(r.getMessage().endswith(" scope=equity") for r in records)


@pytest.mark.usefixtures("stub_wiring")
def test_index_ladder_is_checked_per_market_and_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Replaces ``test_index_ladder_is_explicitly_not_checked`` (TA5 R-60, test 5).

    The shipped index service is now checked, against the currency of the
    market the caller names, at ERROR -- and, since F-9b commit 5, refuses the
    bars (D-4: no cached price either, no sentence). The negative half (the
    shipped configuration logs nothing for any index the product asks for) is
    in ``test_f9b0_index_currency_tripwire.py``.
    """
    resolver = deps._default_index_resolver.__wrapped__()  # bypass lru_cache
    with caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER):
        result = resolver["US"].get_daily_bars("^GSPC", "US", date(2024, 1, 1), date(2024, 1, 2))
    assert result.bars == []
    assert result.rejection == "unit_mismatch"
    assert result.reason is None
    records = [r for r in caplog.records if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)]
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (
            logging.ERROR,
            "price bars currency differs from market: symbol=^GSPC market=US expected=USD "
            "observed=GBP mismatched=1/1 layer=provider source=yfinance "
            "verdict=mismatch scope=index",
        )
    ]
