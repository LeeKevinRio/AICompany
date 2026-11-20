"""The job ``forecast_record`` over the real index services (qa N-9; ADR-0030 supplement 10).

Nothing of the five steps is stood in: ``run_forecast_record`` runs the target
check, takes t0, calls the real ``force_refresh_benchmark`` over a real
``IndexSeriesService(MarketDataService(scope="index", cache_first=True,
primary=IndexProviderBridge(fake source)))``, checks the newest cached bar and
calls the real recorder with ``load_market_benchmark`` on a ledger with both
core claims registered. Only these are replaced:

* ``get_index_resolver`` (the service above, on a ``tmp_path`` cache) and
  ``production_db_target`` (a ``tmp_path`` main DB);
* the clocks: the scheduler's ``_utc_now``, ``app.services.index._system_now``,
  the service clock and the store clock (``ledger_store`` is pointed at the
  same file with that clock) all read one settable clock, so the run sits at
  22:10 Taipei on T whatever the wall clock says.

The fake source stamps every bar with the clock at the request (as the yfinance
adapter does) and counts its requests. No network.

Cases: a normal run; a T bar cached at 17:45 is replaced by this run's; the
source fails (raises / unavailable) with a 17:45 T bar cached; the answer lacks
T while a 17:45 T bar is cached (supplement 10 point 1 (f), last item); the
answer lacks T and nothing cached has T (point 1 (f): the run goes on, the
third line is logged, T-1 is recorded late).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app import scheduler as scheduler_module
from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, PriceBar, ProviderResult
from app.dirdef.rules import rules_logic_sha256
from app.forecast.schema import create_schema
from app.forecast.store import ForecastStore
from app.services import index as index_module
from app.services.index import IndexProviderBridge, IndexSeriesService
from tests.force_refresh_helpers import Clock
from tests.market_service_helpers import index_service
from tests.outlook_helpers import TAIPEI, definition, price_bar, rule_bytes, ruleset
from tests.test_forecast_recorder import CLOSES, H3, H5, SESSIONS, T, publish

T_MINUS_1 = SESSIONS[SESSIONS.index(T) - 1]
#: t0 of the run: 22:10 Taipei on T (a Thursday).
T0 = datetime(T.year, T.month, T.day, 22, 10, tzinfo=TAIPEI).astimezone(UTC)
AT_17_45 = datetime(T.year, T.month, T.day, 17, 45, tzinfo=TAIPEI).astimezone(UTC)
YESTERDAY_22_10 = datetime(
    T_MINUS_1.year, T_MINUS_1.month, T_MINUS_1.day, 22, 10, tzinfo=TAIPEI
).astimezone(UTC)
CLOSE_BY_DAY = {day: Decimal(close) for day, close in zip(SESSIONS, CLOSES, strict=True)}
LINE_1 = scheduler_module.FORECAST_RECORD_REFRESH_FAILED
LINE_2 = scheduler_module.FORECAST_RECORD_BAR_PREDATES_RUN
LINE_3 = scheduler_module.FORECAST_RECORD_SERIES_ENDS_EARLY


class _IndexSource:
    """The slice of the yfinance index adapter the bridge needs; bars stamped at the request."""

    def __init__(
        self, clock: Clock, *, until: date = T, mode: str = "answer", close_shift: str = "0"
    ) -> None:
        self._clock = clock
        self._until = until
        self._mode = mode
        self._shift = Decimal(close_shift)
        self.asked: list[tuple[str, date, date]] = []

    def get_index_daily_bars(self, index_symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((index_symbol, start, end))
        requested = self._clock()
        self._clock.tick(1)  # the answer arrives a second later
        if self._mode == "raise":
            raise RuntimeError("adapter bug")
        bars = [
            price_bar(day, close + self._shift, requested)
            for day, close in CLOSE_BY_DAY.items()
            if start <= day <= end and day <= self._until
        ]
        if self._mode == "unavailable" or not bars:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=requested,
                source="none",
                reason="yfinance 連線逾時或發生錯誤，暫不可用。",
            )
        return ProviderResult(
            bars=bars, status=DataStatus.BACKUP, as_of=requested, source="yfinance"
        )


class _Rig:
    """A main DB with both core claims registered, a price cache and one clock for all."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STOCK_DESK_DB_PATH", raising=False)
        monkeypatch.chdir(root)
        (root / "data").mkdir()
        self.db = (root / "data" / "stock-desk.db").resolve()
        with closing(sqlite3.connect(self.db, isolation_level=None)) as conn:
            create_schema(conn)  # test only: in production only bootstrap creates it
        publish(monkeypatch)
        self._register(datetime(2026, 10, 1, 1, 0, tzinfo=UTC))
        self.clock = Clock(T0)
        self.cache = PriceBarCache(db_path=root / "cache.db")
        self.monkeypatch = monkeypatch
        clock = self.clock
        monkeypatch.setattr(scheduler_module, "production_db_target", lambda: self.db)
        monkeypatch.setattr(scheduler_module, "_utc_now", clock)
        monkeypatch.setattr(index_module, "_system_now", clock)
        monkeypatch.setattr(
            scheduler_module, "ledger_store", lambda path: ForecastStore(path, clock=clock)
        )

    def _register(self, at: datetime) -> None:
        moments = iter([at + timedelta(seconds=n) for n in range(1, 100)])
        store = ForecastStore(self.db, clock=lambda: next(moments))
        for horizon in (3, 5):
            store.register_claim(
                horizon=horizon,
                rules_version=H3 if horizon == 3 else H5,
                rules_bytes=rule_bytes(horizon),
                rules_logic_sha256=rules_logic_sha256(ruleset(horizon)),
                definition=definition(),
                frozen_commit="abc123",
                prereg_doc_path="docs/prereg-v0.32.md",
                prereg_doc_blob=b"prereg",
                review_refs="work/reviews/x.md",
                replaces_claim_id=None,
                replace_reason=None,
                provisional_results_seen=False,
            )

    def seed(self, until: date, at: datetime) -> None:
        """Cached bars up to ``until`` stamped ``at``, covered by a complete fetch at ``at``."""
        bars: list[PriceBar] = [
            price_bar(day, close, at) for day, close in CLOSE_BY_DAY.items() if day <= until
        ]
        self.cache.put(bars, source="yfinance", fetched_at=at)
        start = T - timedelta(days=531)
        self.cache.record_fetch("^TWII", "TW", start=start, end=until, fetched_at=at)

    def wire(self, source: _IndexSource) -> None:
        service = index_service(
            primary=IndexProviderBridge(source),
            cache=self.cache,
            clock=self.clock,
            cache_first=True,
        )
        facade = IndexSeriesService(service)
        self.monkeypatch.setattr(
            scheduler_module, "get_index_resolver", lambda: {"TW": facade, "US": facade}
        )

    def rows(self, table: str) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]

    def snapshot_bar(self, day: date) -> dict[str, Any]:
        (snapshot,) = self.rows("forecast_input_series")
        bars = json.loads(snapshot["bars_json"])
        (found,) = [b for b in bars if b["session_date"] == day.isoformat()]
        return dict(found)


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Rig:
    return _Rig(tmp_path, monkeypatch)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "scheduler" and r.levelno == logging.WARNING
    ]


def _stamp(text: str) -> datetime:
    return datetime.fromisoformat(text)


# --- the check holds ----------------------------------------------------------------------------


def test_n9_a_normal_run_records_with_bars_fetched_by_this_run(
    rig: _Rig, caplog: pytest.LogCaptureFixture
) -> None:
    source = _IndexSource(rig.clock)
    rig.wire(source)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_forecast_record()
    assert result is not None
    assert (result.outcome, result.candidate_t, result.records_written) == ("ok", T, 2)
    records = rig.rows("forecast_record")
    assert {(r["data_as_of"], r["late"]) for r in records} == {(T.isoformat(), 0)}
    t_bar = rig.snapshot_bar(T)
    assert _stamp(t_bar["as_of"]) >= T0
    assert len(source.asked) == 1  # the forced refresh only; the recorder asked nothing
    assert _warnings(caplog) == []
    assert len(rig.rows("forecast_run")) == 1


def test_n9_a_t_bar_cached_at_17_45_is_replaced_by_this_runs(rig: _Rig) -> None:
    rig.seed(T, AT_17_45)
    source = _IndexSource(rig.clock, close_shift="1")  # the source revised T's close since
    rig.wire(source)
    result = scheduler_module.run_forecast_record()
    assert result is not None and (result.outcome, result.records_written) == ("ok", 2)
    t_bar = rig.snapshot_bar(T)
    assert _stamp(t_bar["as_of"]) >= T0 and _stamp(t_bar["as_of"]) != AT_17_45
    assert Decimal(t_bar["close"]) == CLOSE_BY_DAY[T] + 1
    assert {Decimal(r["base_close"]) for r in rig.rows("forecast_record")} == {CLOSE_BY_DAY[T] + 1}
    assert len(source.asked) == 1
    # Incremental: the ask starts at the first day of the cached tail's month.
    ((_, start, end),) = source.asked
    assert (start, end) == (T.replace(day=1), T)


# --- the check fails ----------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["raise", "unavailable"])
def test_n9_a_failing_source_records_nothing_and_does_not_use_the_cache(
    rig: _Rig, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    rig.seed(T, AT_17_45)  # a usable T bar is cached, but from 17:45
    source = _IndexSource(rig.clock, mode=mode)
    rig.wire(source)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        assert scheduler_module.run_forecast_record() is None
    assert _warnings(caplog) == [LINE_1]
    assert rig.rows("forecast_run") == []
    assert rig.rows("forecast_record") == []
    assert rig.rows("forecast_input_series") == []
    assert len(source.asked) == 1


def test_n9_an_answer_without_t_and_a_17_45_t_bar_in_the_cache_skips_the_run(
    rig: _Rig, caplog: pytest.LogCaptureFixture
) -> None:
    # Supplement 10 point 1 (f), last item: B is the old T bar, stamped before t0.
    rig.seed(T, AT_17_45)
    source = _IndexSource(rig.clock, until=T_MINUS_1)
    rig.wire(source)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        assert scheduler_module.run_forecast_record() is None
    assert _warnings(caplog) == [LINE_2]
    assert rig.rows("forecast_run") == []
    assert rig.rows("forecast_record") == []
    assert len(source.asked) == 1


def test_n9_an_answer_without_t_and_no_t_in_the_cache_records_t_minus_1_late(
    rig: _Rig, caplog: pytest.LogCaptureFixture
) -> None:
    # Supplement 10 point 1 (f): a success; B is T-1 re-stamped by this refresh, the third
    # line is logged, and the recorder takes T-1 as the newest final session (late = 1).
    rig.seed(T_MINUS_1, YESTERDAY_22_10)
    source = _IndexSource(rig.clock, until=T_MINUS_1)
    rig.wire(source)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_forecast_record()
    assert result is not None
    assert (result.outcome, result.candidate_t, result.records_written) == ("ok", T_MINUS_1, 2)
    assert _warnings(caplog) == [LINE_3]
    records = rig.rows("forecast_record")
    assert {(r["data_as_of"], r["late"]) for r in records} == {(T_MINUS_1.isoformat(), 1)}
    assert _stamp(rig.snapshot_bar(T_MINUS_1)["as_of"]) >= T0
    assert len(source.asked) == 1


def test_n9_the_rig_replaces_only_the_resolver_the_target_and_the_clocks(rig: _Rig) -> None:
    # The forced refresh and the recorder are the real ones.
    names = vars(scheduler_module)
    assert names["force_refresh_benchmark"] is index_module.force_refresh_benchmark
    assert names["record_forecasts"].__module__ == "app.forecast.recorder"
    assert names["load_market_benchmark"] is index_module.load_market_benchmark
    replaced: Callable[[Path], ForecastStore] = names["ledger_store"]
    assert replaced(rig.db)._db_path == rig.db
