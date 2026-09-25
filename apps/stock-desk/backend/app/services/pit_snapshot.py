"""Daily PIT snapshot capture, plus the pre-D0 warm-up backfill CLI (ADR-0012 D-3, D-5).

## Daily capture (:func:`capture_once`)

Fetches one :class:`~app.data.interface.SnapshotResult` from a
``MarketSnapshotProvider`` and writes it into the market DB, one
``pit_snapshot_runs`` row per kind. Per D-5:

- the four kinds fail independently -- one kind's failure never blocks the
  others;
- a kind already ``"ok"`` for today is skipped (idempotent against the
  scheduler's three-times-a-day cron, D-5's ``pit_snapshot_capture`` job);
- the ``bars`` run is only allowed ``status="ok"`` when its coverage against
  the PIT-visible listing size is >= ``BARS_OK_COVERAGE_MIN`` (0.98,
  D-2) -- this is where that threshold is actually enforced (the provider
  cannot compute it itself, since it does not read the store).

This module does **not** wire itself into ``app.scheduler`` -- ADR-0012 says
the scheduler jobs are wave 3 (dev-lead), and the task instructs
data-engineer not to touch ``app/scheduler.py``.

## Warm-up backfill CLI

    python -m app.services.pit_snapshot --warmup --since YYYY-MM-DD

Fetches at least 80 trading days of history per symbol from FinMind
(``TaiwanStockPrice``), one HTTP request per symbol, and writes each day's
row as its own ``kind="bars"``, ``source="finmind_warmup"`` run (one run per
symbol per day, all written inside a single SQLite transaction per symbol --
see :meth:`app.data.market_panel.MarketPanelStore.record_symbol_backfill`'s
docstring for why one run cannot span more than one day: D-2's
``market_daily_bars`` primary key is ``(run_id, symbol)``). This still
honours D-3's "以 symbol 為最小重試單位，一檔一個 transaction" at the
transaction level. Progress is checkpointed in ``market_backfill_progress``
so a re-run only retries symbols that have not already succeeded.

Refuses to run once D0 (the first session all four kinds reached ``"ok"``
together) has passed -- see :func:`app.data.market_panel.MarketPanelStore.
first_all_kinds_ok_session`. The FinMind token is read exclusively from the
``FINMIND_API_TOKEN`` environment variable and is never logged or written
anywhere (skill red line).

## Daily capture CLI

    python -m app.services.pit_snapshot

Runs :func:`capture_once` once against the live ``TwseSnapshotAdapter`` and
prints a summary -- useful for CEO to run manually before the scheduler job
(wave 3) exists, and for verifying the pipeline end to end. This is the
default (no ``--warmup`` flag), not a ``capture`` subcommand.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Protocol
from zoneinfo import ZoneInfo

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import (
    BarSnapshotRow,
    MarketSnapshotProvider,
    SnapshotKind,
    SnapshotResult,
    SnapshotRunStatus,
)
from app.data.market_panel import BARS_OK_COVERAGE_MIN, MarketPanelStore
from app.data.providers._util import UnparseableRowError
from app.data.providers.finmind import DATA_PATH, DATASET, FINMIND_BASE_URL, TOKEN_ENV_VAR
from app.data.providers.twse_snapshot import TwseSnapshotAdapter

logger = logging.getLogger(__name__)

TAIPEI: Final = ZoneInfo("Asia/Taipei")

#: Minimum trading days of pre-D0 history the warm-up must fetch per symbol
#: (D-3: "上市天數 60 加流動性 20 日窗" -> at least 80 trading sessions).
WARMUP_MIN_TRADING_DAYS: Final[int] = 80

_ALL_KINDS: Final[tuple[SnapshotKind, ...]] = (
    "listing",
    "classification",
    "dividend_announce",
    "bars",
)


@dataclass(frozen=True)
class KindCaptureRecord:
    """What happened writing one kind's run for one capture attempt."""

    kind: SnapshotKind
    run_id: int | None
    status: str
    row_count: int
    expected_count: int | None
    reason: str | None
    skipped_already_ok: bool


@dataclass(frozen=True)
class CaptureSummary:
    session_date: date | None
    records: tuple[KindCaptureRecord, ...]


def capture_once(provider: MarketSnapshotProvider, store: MarketPanelStore) -> CaptureSummary:
    """Fetch one snapshot and write it, one run per kind, independently and idempotently."""
    result = provider.get_latest_snapshot()

    if result.session_date is None:
        failed_records = tuple(_write_failed_run(store, kind, result) for kind in _ALL_KINDS)
        return CaptureSummary(session_date=None, records=failed_records)

    ok_records: list[KindCaptureRecord] = []
    # Listing/classification/dividend_announce first: bars' coverage check
    # needs the PIT-visible listing size, and processing listing first means
    # a same-day success is already visible to that lookup (D-2 "當日可見上
    # 市名單").
    for kind in ("listing", "classification", "dividend_announce"):
        ok_records.append(_capture_simple_kind(store, kind, result))
    ok_records.append(_capture_bars(store, result))
    return CaptureSummary(session_date=result.session_date, records=tuple(ok_records))


def _write_failed_run(
    store: MarketPanelStore, kind: SnapshotKind, result: SnapshotResult
) -> KindCaptureRecord:
    outcome = getattr(result, kind)
    run_id = store.record_run(
        kind=kind,
        session_date=None,
        source=result.source,
        status="failed",
        row_count=0,
        expected_count=None,
        reason=outcome.reason,
    )
    return KindCaptureRecord(kind, run_id, "failed", 0, None, outcome.reason, False)


def _already_ok_today(store: MarketPanelStore, kind: SnapshotKind, session_date: date) -> bool:
    """Whether ``kind`` already has an ``ok`` run for exactly ``session_date`` (D-5 idempotency)."""
    return store.last_ok_session(kind, before=session_date) == session_date


def _capture_simple_kind(
    store: MarketPanelStore, kind: SnapshotKind, result: SnapshotResult
) -> KindCaptureRecord:
    assert result.session_date is not None
    if _already_ok_today(store, kind, result.session_date):
        return KindCaptureRecord(kind, None, "ok", 0, None, None, True)

    outcome = getattr(result, kind)
    rows = getattr(result, f"{kind}_rows")
    kwargs: dict[str, Any] = {f"{kind}_rows": rows} if outcome.status == "ok" else {}
    run_id = store.record_run(
        kind=kind,
        session_date=result.session_date,
        source=result.source,
        status=outcome.status,
        row_count=outcome.row_count,
        expected_count=None,
        reason=outcome.reason,
        **kwargs,
    )
    return KindCaptureRecord(
        kind, run_id, outcome.status, outcome.row_count, None, outcome.reason, False
    )


def _capture_bars(store: MarketPanelStore, result: SnapshotResult) -> KindCaptureRecord:
    """Write the bars run, gating ``status="ok"`` on real coverage.

    (qa-reviewer wave-1 blocking fix.)

    Coverage is ``|bars_symbols ∩ listing_common| / |listing_common|`` --
    **never** ``bars_row_count / listing_row_count`` and never against a
    listing snapshot the bars themselves helped define (the wave-1 bug: when
    listing was ``STOCK_DAY_ALL ∩ t187ap03_L``, the denominator was a subset
    of the numerator by construction, so the 0.98 gate could not fail no
    matter how little of the market ``STOCK_DAY_ALL`` actually returned).

    ``listing_common`` prefers **this same capture's** ``result.listing_rows``
    (dev-lead's ruling: "listing 用同一次擷取的 t187ap03_L 結果") when that
    kind succeeded this run; only when it did not does this fall back to the
    most recent visible ``ok`` listing run in the store. When neither is
    available, coverage cannot be judged at all, and bars can only ever be
    ``"partial"`` -- never ``"ok"`` by default.
    """
    assert result.session_date is not None
    if _already_ok_today(store, "bars", result.session_date):
        return KindCaptureRecord("bars", None, "ok", 0, None, None, True)

    outcome = result.bars
    if outcome.status != "ok":
        run_id = store.record_run(
            kind="bars",
            session_date=result.session_date,
            source=result.source,
            status="failed",
            row_count=0,
            expected_count=None,
            reason=outcome.reason,
        )
        return KindCaptureRecord("bars", run_id, "failed", 0, None, outcome.reason, False)

    listing_common: frozenset[str]
    if result.listing.status == "ok":
        listing_common = frozenset(
            row.symbol for row in result.listing_rows if row.security_type == "common_stock"
        )
        listing_source_note = "同次擷取的 t187ap03_L"
    else:
        listing_common = store.pit_visible_listing_symbols(
            on_or_before=result.session_date, security_type="common_stock"
        )
        listing_source_note = "store 中最近一份可見 ok listing"

    expected_count = len(listing_common) if listing_common else None
    bars_symbols = {row.symbol for row in result.bars_rows}
    matched_count = len(bars_symbols & listing_common) if expected_count else 0
    coverage = matched_count / expected_count if expected_count else None

    final_status: SnapshotRunStatus
    reason: str | None
    if coverage is None:
        final_status = "partial"
        reason = (
            "無可見的普通股上市名單可供計算覆蓋率（本次擷取與 store 中最近一份 ok listing "
            "皆不可得），無法判定覆蓋率，不得標為 ok"
        )
    elif coverage >= BARS_OK_COVERAGE_MIN:
        final_status, reason = "ok", None
    else:
        final_status = "partial"
        reason = (
            f"覆蓋率 {coverage:.4f}（{matched_count}/{expected_count}，"
            f"分母來源＝{listing_source_note}）低於門檻 {BARS_OK_COVERAGE_MIN}"
        )

    run_id = store.record_run(
        kind="bars",
        session_date=result.session_date,
        source=result.source,
        status=final_status,
        row_count=outcome.row_count,
        expected_count=expected_count,
        reason=reason,
        bars_rows=result.bars_rows,
    )
    return KindCaptureRecord(
        "bars", run_id, final_status, outcome.row_count, expected_count, reason, False
    )


# ---------------------------------------------------------------------------
# Warm-up backfill (D-3): FinMind, one symbol at a time, checkpointed.
# ---------------------------------------------------------------------------


class WarmupAfterD0Error(RuntimeError):
    """Raised when the warm-up CLI is invoked after D0 has already been reached."""


@dataclass(frozen=True)
class WarmupSymbolResult:
    symbol: str
    status: str  # "done" | "failed" | "skipped_already_done"
    row_count: int
    detail: str | None


class _HttpGetClient(Protocol):
    """The narrow slice of ``RateLimitedClient`` the warm-up fetch actually calls.

    Lets tests substitute a hand-written fake without needing a real
    ``httpx.MockTransport``-backed ``RateLimitedClient`` -- the warm-up loop
    never uses anything beyond ``.get(url, params=...)``.
    """

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response: ...


def _fetch_finmind_history(
    client: _HttpGetClient, symbol: str, start: date, end: date, *, token: str
) -> tuple[list[tuple[date, BarSnapshotRow]] | None, str | None]:
    """Fetch one symbol's full ``[start, end]`` history in one request.

    Deliberately not ``FinMindAdapter.get_daily_bars`` -- that adapter's
    ``PriceBar`` has no ``traded_value`` field, and the warm-up needs it for
    ``BarSnapshotRow`` (D-2 schema). Reuses ``FinMindAdapter``'s endpoint
    constants so the two never drift, but does its own minimal row parsing.
    """
    try:
        response = client.get(
            DATA_PATH,
            params={
                "dataset": DATASET,
                "data_id": symbol,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "token": token,
            },
        )
    except httpx.TransportError as exc:
        return None, f"連線失敗（{exc.__class__.__name__}）：{exc}"
    if response.status_code != httpx.codes.OK:
        return None, f"FinMind 回傳 HTTP {response.status_code}"
    try:
        payload = response.json(parse_float=Decimal)
    except ValueError:
        return None, "FinMind 回應非 JSON"
    if not isinstance(payload, dict) or payload.get("status") != 200:
        return None, f"FinMind 回應 status 非 200：{payload!r}"
    rows = payload.get("data") or []
    parsed: list[tuple[date, BarSnapshotRow]] = []
    for row in rows:
        try:
            parsed.append(_parse_finmind_row(row, symbol))
        except (UnparseableRowError, KeyError, TypeError, ValueError, InvalidOperation) as exc:
            logger.debug("skipping unparseable FinMind warm-up row for %s: %s", symbol, exc)
            continue
    if not parsed:
        return None, "FinMind 回應中沒有任何可解析的列"
    return parsed, None


def _parse_finmind_row(row: dict[str, Any], symbol: str) -> tuple[date, BarSnapshotRow]:
    trade_date = date.fromisoformat(str(row["date"]))
    bar = BarSnapshotRow(
        symbol=symbol,
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["max"])),
        low=Decimal(str(row["min"])),
        close=Decimal(str(row["close"])),
        shares=int(row["Trading_Volume"]),
        traded_value=Decimal(str(row["Trading_money"])),
        change=Decimal(str(row["spread"])) if row.get("spread") is not None else None,
    )
    return trade_date, bar


def run_warmup(
    store: MarketPanelStore,
    client: _HttpGetClient,
    symbols: Sequence[str],
    *,
    since: date,
    today: date,
) -> list[WarmupSymbolResult]:
    """Backfill ``[since, today]`` FinMind bars for every symbol, checkpointed.

    Refuses outright if D0 has already been reached (D-3: "D0 之後 CLI 拒絕
    執行暖身"). Idempotent: a symbol already ``"done"`` in
    ``market_backfill_progress`` is skipped without another HTTP request.
    """
    d0 = store.first_all_kinds_ok_session()
    if d0 is not None:
        raise WarmupAfterD0Error(f"D0（{d0.isoformat()}）已到達，暖身 CLI 依 ADR-0012 D-3 拒絕執行")

    trading_span_days = (today - since).days
    if trading_span_days < WARMUP_MIN_TRADING_DAYS:
        logger.warning(
            "warm-up window [%s, %s] is only %d calendar days; ADR-0012 D-3 wants at least "
            "%d TRADING days -- this is a lower bound on calendar days, not a substitute for "
            "checking the actual trading-day count",
            since.isoformat(),
            today.isoformat(),
            trading_span_days,
            WARMUP_MIN_TRADING_DAYS,
        )

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        raise RuntimeError(f"{TOKEN_ENV_VAR} 未設定，暖身需要 FinMind token")

    progress = store.backfill_progress()
    results: list[WarmupSymbolResult] = []
    for symbol in symbols:
        if progress.get(symbol) == "done":
            results.append(WarmupSymbolResult(symbol, "skipped_already_done", 0, None))
            continue
        rows, error = _fetch_finmind_history(client, symbol, since, today, token=token)
        if rows is None:
            store.upsert_backfill_progress(symbol, status="failed", last_error=error)
            results.append(WarmupSymbolResult(symbol, "failed", 0, error))
            continue
        store.record_symbol_backfill(symbol=symbol, source="finmind_warmup", rows=rows)
        store.upsert_backfill_progress(symbol, status="done")
        results.append(WarmupSymbolResult(symbol, "done", len(rows), None))
    return results


def _resolve_warmup_symbols() -> list[str]:
    """Fetch a fresh listing snapshot just to source the warm-up's symbol universe.

    Does not write anything to the market DB -- the daily capture
    (:func:`capture_once`) is the sanctioned writer for ``listing`` runs;
    this only reads the same live endpoint to decide *which* symbols to
    backfill bars for.
    """
    adapter = TwseSnapshotAdapter()
    try:
        result = adapter.get_latest_snapshot()
    finally:
        adapter.close()
    if result.session_date is None or not result.listing_rows:
        raise RuntimeError(
            "無法取得上市名單以決定暖身標的範圍（快照日期無法自證或上市名單為空）："
            f"{result.listing.reason}"
        )
    return sorted(row.symbol for row in result.listing_rows)


def _cli_capture() -> int:
    adapter = TwseSnapshotAdapter()
    store = MarketPanelStore()
    try:
        summary = capture_once(adapter, store)
    finally:
        adapter.close()
    print(f"session_date={summary.session_date}")
    for record in summary.records:
        print(
            f"  {record.kind}: status={record.status} row_count={record.row_count} "
            f"expected_count={record.expected_count} skipped_already_ok="
            f"{record.skipped_already_ok} reason={record.reason}"
        )
    return 0


def _cli_warmup(since: date) -> int:
    store = MarketPanelStore()
    client = RateLimitedClient(base_url=FINMIND_BASE_URL, min_interval_seconds=0.3)
    try:
        symbols = _resolve_warmup_symbols()
        today = datetime.now(UTC).astimezone(TAIPEI).date()
        results = run_warmup(store, client, symbols, since=since, today=today)
    except WarmupAfterD0Error as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    finally:
        client.close()
    done = sum(1 for r in results if r.status == "done")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped_already_done")
    print(f"warm-up: {done} done, {failed} failed, {skipped} already done (of {len(results)})")
    for result in results:
        if result.status == "failed":
            print(f"  FAILED {result.symbol}: {result.detail}")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.services.pit_snapshot")
    parser.add_argument(
        "--warmup", action="store_true", help="Pre-D0 FinMind bars backfill (ADR-0012 D-3)."
    )
    parser.add_argument("--since", help="ISO date, e.g. 2026-06-01 -- required with --warmup.")
    args = parser.parse_args(argv)

    if not args.warmup:
        return _cli_capture()
    if not args.since:
        parser.error("--warmup requires --since YYYY-MM-DD")
    since = date.fromisoformat(args.since)
    return _cli_warmup(since)


if __name__ == "__main__":
    raise SystemExit(main())
