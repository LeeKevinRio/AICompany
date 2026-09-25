"""``app.services.pit_snapshot`` capture + warm-up tests (ADR-0012 D-3, D-5).

Offline only: providers are hand-built stubs, never the live adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.data.interface import (
    BarSnapshotRow,
    ClassificationSnapshotRow,
    DividendAnnounceSnapshotRow,
    ListingSnapshotRow,
    MarketSnapshotProvider,
    SnapshotKindOutcome,
    SnapshotResult,
)
from app.data.market_panel import BARS_OK_COVERAGE_MIN, MarketPanelStore
from app.services.pit_snapshot import (
    WarmupAfterD0Error,
    capture_once,
    run_warmup,
)

SESSION = date(2026, 9, 24)


def _bar(symbol: str) -> BarSnapshotRow:
    return BarSnapshotRow(
        symbol=symbol,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        shares=1000,
        traded_value=Decimal("100500"),
        change=Decimal("0.5"),
    )


class StubProvider(MarketSnapshotProvider):
    source_id = "stub_snapshot"

    def __init__(self, result: SnapshotResult) -> None:
        self._result = result
        self.call_count = 0

    def get_latest_snapshot(self) -> SnapshotResult:
        self.call_count += 1
        return self._result


def _ok_result(
    *, session_date: date = SESSION, symbols: tuple[str, ...] = ("2330", "0050")
) -> SnapshotResult:
    ok = SnapshotKindOutcome(status="ok", row_count=len(symbols))
    return SnapshotResult(
        as_of=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        source="stub_snapshot",
        session_date=session_date,
        session_date_self_certified=True,
        bars=ok,
        bars_rows=tuple(_bar(s) for s in symbols),
        listing=ok,
        listing_rows=tuple(
            ListingSnapshotRow(symbol=s, security_type="common_stock") for s in symbols
        ),
        classification=ok,
        classification_rows=tuple(
            ClassificationSnapshotRow(symbol=s, sector_code="24", sector_name="半導體業")
            for s in symbols
        ),
        dividend_announce=ok,
        dividend_announce_rows=(
            DividendAnnounceSnapshotRow(symbol=symbols[0], ex_date=date(2026, 10, 1), raw={}),
        ),
    )


def _failed_result(reason: str = "無法自證交易日") -> SnapshotResult:
    failed = SnapshotKindOutcome(status="failed", row_count=0, reason=reason)
    return SnapshotResult(
        as_of=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        source="stub_snapshot",
        session_date=None,
        session_date_self_certified=False,
        bars=failed,
        listing=failed,
        classification=failed,
        dividend_announce=failed,
    )


@pytest.fixture
def store(tmp_path: Path) -> MarketPanelStore:
    return MarketPanelStore(
        tmp_path / "market.db", clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC)
    )


def test_capture_once_writes_all_four_kinds_and_marks_bars_ok_when_coverage_is_full(
    store: MarketPanelStore,
) -> None:
    provider = StubProvider(_ok_result())
    summary = capture_once(provider, store)

    assert summary.session_date == SESSION
    by_kind = {r.kind: r for r in summary.records}
    assert by_kind["listing"].status == "ok"
    assert by_kind["classification"].status == "ok"
    assert by_kind["dividend_announce"].status == "ok"
    # bars coverage = 2 bars / 2 listed symbols = 100% >= 0.98
    assert by_kind["bars"].status == "ok"
    assert by_kind["bars"].expected_count == 2


def test_bars_coverage_exactly_at_the_threshold_is_ok(store: MarketPanelStore) -> None:
    """Boundary: coverage == BARS_OK_COVERAGE_MIN exactly must still be "ok"."""
    assert BARS_OK_COVERAGE_MIN == 0.98
    # 49/50 == 0.98 exactly.
    common_symbols = tuple(f"S{i:03d}" for i in range(50))
    traded_symbols = common_symbols[:49]
    ok = SnapshotKindOutcome(status="ok", row_count=len(traded_symbols))
    result = SnapshotResult(
        as_of=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        source="stub_snapshot",
        session_date=SESSION,
        session_date_self_certified=True,
        bars=ok,
        bars_rows=tuple(_bar(s) for s in traded_symbols),
        listing=SnapshotKindOutcome(status="ok", row_count=len(common_symbols)),
        listing_rows=tuple(
            ListingSnapshotRow(symbol=s, security_type="common_stock") for s in common_symbols
        ),
        classification=ok,
        classification_rows=(),
        dividend_announce=ok,
        dividend_announce_rows=(),
    )
    provider = StubProvider(result)
    summary = capture_once(provider, store)
    by_kind = {r.kind: r for r in summary.records}
    assert by_kind["bars"].status == "ok"


def test_capture_once_falls_back_to_the_stores_last_listing_when_todays_listing_fails(
    store: MarketPanelStore,
) -> None:
    """qa-reviewer wave-1 point 2 (second half): when *this* capture's t187ap03_L
    fetch failed, coverage must fall back to the store's last visible ``ok``
    listing rather than silently skipping the gate -- and it must still only
    count ``"common_stock"`` symbols (a TDR present that day must not inflate
    the denominator)."""
    # Yesterday's listing: 3 common stocks + 1 TDR.
    store.record_run(
        kind="listing",
        session_date=date(2026, 9, 23),
        source="twse_snapshot",
        status="ok",
        row_count=4,
        expected_count=None,
        listing_rows=[
            ListingSnapshotRow(symbol="2330", security_type="common_stock"),
            ListingSnapshotRow(symbol="0050x", security_type="common_stock"),
            ListingSnapshotRow(symbol="3037", security_type="common_stock"),
            ListingSnapshotRow(symbol="9188", security_type="tdr"),
        ],
    )

    # Today's capture: listing (t187ap03_L) itself failed, but bars succeeded
    # for all 3 common stocks.
    ok = SnapshotKindOutcome(status="ok", row_count=3)
    failed_listing = SnapshotKindOutcome(status="failed", row_count=0, reason="t187ap03_L 逾時")
    result = SnapshotResult(
        as_of=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        source="stub_snapshot",
        session_date=SESSION,
        session_date_self_certified=True,
        bars=ok,
        bars_rows=(_bar("2330"), _bar("0050x"), _bar("3037")),
        listing=failed_listing,
        listing_rows=(),
        classification=ok,
        classification_rows=(
            ClassificationSnapshotRow(symbol="2330", sector_code="24", sector_name="半導體業"),
        ),
        dividend_announce=ok,
        dividend_announce_rows=(
            DividendAnnounceSnapshotRow(symbol="2330", ex_date=date(2026, 10, 1), raw={}),
        ),
    )
    provider = StubProvider(result)
    summary = capture_once(provider, store)
    by_kind = {r.kind: r for r in summary.records}

    assert by_kind["listing"].status == "failed"
    # 3/3 common stocks matched against the FALLBACK listing (TDR excluded
    # from the denominator) -> full coverage, ok.
    assert by_kind["bars"].expected_count == 3
    assert by_kind["bars"].status == "ok"


def test_capture_once_marks_bars_partial_when_no_listing_is_available_at_all(
    store: MarketPanelStore,
) -> None:
    """Neither this capture's listing nor any prior store listing exists ->
    coverage is undecidable, so bars can only ever be "partial", never "ok"."""
    ok = SnapshotKindOutcome(status="ok", row_count=1)
    failed_listing = SnapshotKindOutcome(status="failed", row_count=0, reason="t187ap03_L 逾時")
    result = SnapshotResult(
        as_of=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        source="stub_snapshot",
        session_date=SESSION,
        session_date_self_certified=True,
        bars=ok,
        bars_rows=(_bar("2330"),),
        listing=failed_listing,
        listing_rows=(),
        classification=ok,
        classification_rows=(
            ClassificationSnapshotRow(symbol="2330", sector_code="24", sector_name="半導體業"),
        ),
        dividend_announce=ok,
        dividend_announce_rows=(),
    )
    provider = StubProvider(result)
    summary = capture_once(provider, store)
    by_kind = {r.kind: r for r in summary.records}
    assert by_kind["bars"].status == "partial"
    assert by_kind["bars"].expected_count is None


def test_capture_once_is_idempotent_within_the_same_session(store: MarketPanelStore) -> None:
    provider = StubProvider(_ok_result())
    first = capture_once(provider, store)
    second = capture_once(provider, store)

    assert all(not r.skipped_already_ok for r in first.records)
    assert all(r.skipped_already_ok for r in second.records)

    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    # only ONE bars run recorded, not two -- idempotency prevented a duplicate write
    assert (frames.runs["kind"] == "bars").sum() == 1


def test_capture_once_handles_a_kind_failing_independently(store: MarketPanelStore) -> None:
    result = _ok_result()
    failed_dividend = SnapshotKindOutcome(status="failed", row_count=0, reason="TWT48U_ALL 逾時")
    result = result.model_copy(
        update={"dividend_announce": failed_dividend, "dividend_announce_rows": ()}
    )
    provider = StubProvider(result)
    summary = capture_once(provider, store)
    by_kind = {r.kind: r for r in summary.records}
    assert by_kind["dividend_announce"].status == "failed"
    assert by_kind["listing"].status == "ok"
    assert by_kind["bars"].status == "ok"


def test_capture_once_records_all_four_as_failed_when_session_uncertifiable(
    store: MarketPanelStore,
) -> None:
    provider = StubProvider(_failed_result())
    summary = capture_once(provider, store)
    assert summary.session_date is None
    assert {r.status for r in summary.records} == {"failed"}
    frames = store.load_panel_frames(date(2020, 1, 1), date(2030, 1, 1))
    assert frames.runs.empty  # session_date NULL -> invisible to load_panel_frames


# -- warm-up backfill -----------------------------------------------------------


class FakeFinMindClient:
    """Stand-in for RateLimitedClient, returning canned FinMind-shaped JSON.

    Satisfies ``app.services.pit_snapshot._HttpGetClient`` structurally (a
    ``Protocol``), so this needs no subclassing and no ``type: ignore``.
    """

    def __init__(self, history: dict[str, list[dict[str, object]]]) -> None:
        self._history = history

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        assert params is not None
        symbol = params["data_id"]
        rows = self._history.get(symbol, [])
        return httpx.Response(200, json={"status": 200, "data": rows})


def _finmind_row(day: date, symbol: str) -> dict[str, object]:
    return {
        "date": day.isoformat(),
        "stock_id": symbol,
        "Trading_Volume": 1000,
        "Trading_money": 100000,
        "open": "10.0",
        "max": "10.5",
        "min": "9.5",
        "close": "10.2",
        "spread": "0.2",
        "Trading_turnover": 10,
    }


def test_run_warmup_writes_one_run_per_symbol_per_day_and_checkpoints(
    store: MarketPanelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINMIND_API_TOKEN", "test-token")
    since = date(2026, 6, 1)
    today = date(2026, 6, 3)
    history = {
        "2330": [_finmind_row(date(2026, 6, 1), "2330"), _finmind_row(date(2026, 6, 2), "2330")],
        "0050": [_finmind_row(date(2026, 6, 1), "0050")],
    }
    client = FakeFinMindClient(history)
    results = run_warmup(store, client, ["2330", "0050"], since=since, today=today)

    assert {r.symbol: r.status for r in results} == {"2330": "done", "0050": "done"}
    assert store.backfill_progress() == {"2330": "done", "0050": "done"}

    summary = store.run_status_summary(date(2026, 5, 1), date(2026, 7, 1))
    assert summary["bars"].ok_sessions == frozenset({date(2026, 6, 1), date(2026, 6, 2)})


def test_run_warmup_skips_symbols_already_done(
    store: MarketPanelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINMIND_API_TOKEN", "test-token")
    store.upsert_backfill_progress("2330", status="done")
    client = FakeFinMindClient({"2330": [_finmind_row(date(2026, 6, 1), "2330")]})
    results = run_warmup(
        store,
        client,
        ["2330"],
        since=date(2026, 6, 1),
        today=date(2026, 6, 1),
    )
    assert results[0].status == "skipped_already_done"


def test_run_warmup_refuses_to_run_after_d0(
    store: MarketPanelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINMIND_API_TOKEN", "test-token")
    # Reach D0: all four kinds ok on the same session.
    provider = StubProvider(_ok_result())
    capture_once(provider, store)
    assert store.first_all_kinds_ok_session() == SESSION

    client = FakeFinMindClient({"2330": [_finmind_row(date(2026, 6, 1), "2330")]})
    with pytest.raises(WarmupAfterD0Error):
        run_warmup(
            store,
            client,
            ["2330"],
            since=date(2026, 6, 1),
            today=date(2026, 6, 1),
        )


def test_run_warmup_records_failure_without_a_token(
    store: MarketPanelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FINMIND_API_TOKEN", raising=False)
    client = FakeFinMindClient({})
    with pytest.raises(RuntimeError, match="FINMIND_API_TOKEN"):
        run_warmup(
            store,
            client,
            ["2330"],
            since=date(2026, 6, 1),
            today=date(2026, 6, 1),
        )
