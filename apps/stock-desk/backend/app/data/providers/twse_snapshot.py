"""``MarketSnapshotProvider`` over TWSE's whole-market snapshot endpoints (ADR-0012 D-3).

Captures all four PIT snapshot kinds from three "current state" TWSE OpenAPI
endpoints in one call:

- ``STOCK_DAY_ALL`` -- same-day OHLCV for every symbol that actually traded
  (bars). This is a *trading* snapshot, not a membership list: a symbol with
  no trade today (or suspended) simply has no row here.
- ``t187ap03_L`` -- 上市公司基本資料, used for **both** ``classification``
  and ``listing`` (reusing ``app.directory.providers.TwseSectorProfileAdapter``
  and ``app.directory.twse_sector_codes`` for the code -> name resolution,
  per ADR-0012's "沿用 app/directory 的解析與代碼對照，不寫入
  positions／directory"). ``listing`` is the **full** resolvable-code
  population from this dataset -- deliberately **not** intersected with
  ``STOCK_DAY_ALL``'s symbol set (qa-reviewer wave-1 blocking finding: an
  intersection makes the listing snapshot only ever as large as whatever
  STOCK_DAY_ALL happened to return that day, which in turn is the
  denominator :func:`app.services.pit_snapshot`'s bars coverage gate divides
  by -- coverage against a self-shrinking denominator can never fail no
  matter how little of the market actually got captured). A listed symbol
  with no bar today is a real absence and must show up as a category-①
  "missing" count downstream (D-4/D-7's "no suspension-list source ->
  counted as missing"), not silently vanish from the population it is
  missing *from*.
- ``TWT48U_ALL`` -- 上市股票除權除息預告表, captured verbatim for
  ``dividend_announce``.

## VERIFICATION STATUS

Same footing as the modules this one reuses: ``STOCK_DAY_ALL``,
``t187ap03_L`` and ``TWT48U_ALL`` are each individually CEO-verified
end-to-end (2026-08-12, see ``app/directory/providers.py`` and
``app/dividends/providers.py``). What is **new and unverified** in this
module:

- **DE-1' (does ``STOCK_DAY_ALL`` carry a trading date?)**: NO -- confirmed
  by this task's own inspection of ``tests/fixtures/twse_openapi_stock_day_all.json``,
  which has no date field at all (only ``Code``/``Name``/OHLCV/``Change``/
  ``Transaction``). This is why :meth:`TwseSnapshotAdapter.get_latest_snapshot`
  never trusts the wall clock for ``session_date`` (D-3, C-12) and instead
  cross-certifies a *candidate* date (the wall-clock date is only ever used
  as a hypothesis to test, never asserted outright) against FinMind's
  independently-dated ``TaiwanStockPrice`` feed for a small symbol sample.
  This cross-check has never been run against live data in this sandbox
  (egress blocked) -- CEO must run it once on a real trading day and record
  the result before this adapter is trusted in production (see the
  verification script this wave also ships,
  ``apps/stock-desk/scripts/verify_sector_data.py``).
- **DE-5 (is ``Change`` measured against the ex-dividend reference price?)**:
  unverified. ``CHANGE_SEMANTICS_VERIFIED_ON`` stays ``None`` until CEO
  confirms this against a real ex-dividend day (module docstring below).
- The 張→股 (board-lot -> shares) unit for ``STOCK_DAY_ALL``'s ``TradeVolume``
  column is treated as already-shares (matching the individual, CEO-verified
  ``STOCK_DAY`` endpoint's ``成交股數`` convention), via a header-driven check
  that is a defensive no-op today rather than a hardcoded assumption --
  see :func:`normalize_shares_by_header`.

This sandbox cannot reach ``openapi.twse.com.tw`` or
``api.finmindtrade.com`` (egress blocked); every test for this module uses
``httpx.MockTransport`` and the fixtures already in ``tests/fixtures/``.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Final
from zoneinfo import ZoneInfo

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import (
    BarSnapshotRow,
    ClassificationSnapshotRow,
    DividendAnnounceSnapshotRow,
    ListingSnapshotRow,
    MarketSnapshotProvider,
    SnapshotKindOutcome,
    SnapshotResult,
)
from app.data.providers._util import UnparseableRowError, parse_decimal_cell, parse_int_cell
from app.data.providers.finmind import FinMindAdapter
from app.directory.providers import (
    TWSE_OPENAPI_BASE_URL,
    TWSE_STOCK_LIST_PATH,
    TwseSectorProfileAdapter,
)
from app.directory.twse_sector_codes import TWSE_SECTOR_CODE_TO_NAME
from app.dividends.providers import TWSE_EX_DIVIDEND_PATH, parse_twse_date

logger = logging.getLogger(__name__)

TAIPEI: Final = ZoneInfo("Asia/Taipei")

#: Written into ``pit_snapshot_runs.source`` / ``SnapshotResult.source``.
SOURCE_ID: Final[str] = "twse_snapshot"

#: ``ListingSnapshotRow.security_type`` values this provider ever produces.
#: ``app.sectors.universe`` (dev-lead) treats ``"common_stock"`` as the sole
#: eligible value -- this pairing must not drift, or the whole card silently
#: goes empty. ``t187ap03_L`` is per-*company*, not per-*security*, so ETFs
#: (no row at all, no industry code exists for them), preferred shares and
#: warrants (traded under the parent company's own code, no separate
#: ``t187ap03_L`` row) never appear in the ``listing`` snapshot at all -- the
#: one distinguishable non-common case this dataset actually carries is code
#: 91 (存託憑證 / depositary receipts, i.e. TDRs), which resolves here to
#: ``"tdr"``. Every other resolvable industry code -- including 20 (其他業),
#: which is excluded from ranking downstream but is still an ordinary common
#: share -- resolves to ``"common_stock"``.
SECURITY_TYPE_COMMON_STOCK: Final[str] = "common_stock"
SECURITY_TYPE_TDR: Final[str] = "tdr"
#: The ``t187ap03_L`` industry code TWSE uses for depositary-receipt issuers.
_TDR_SECTOR_CODE: Final[str] = "91"

#: DE-5: whether ``STOCK_DAY_ALL``'s ``Change`` column is measured against the
#: ex-dividend reference price (as opposed to the prior day's raw close).
#: ``None`` until CEO verifies this against a real ex-dividend session --
#: see ``apps/stock-desk/scripts/verify_sector_data.py``'s DE-5 check. Until
#: verified, ADR-0012 D-8/D-12 treats this as NE-1 (``pit_history_missing``),
#: not a silent assumption either way.
CHANGE_SEMANTICS_VERIFIED_ON: date | None = None

#: STOCK_DAY_ALL's own field label for its volume column (fixed -- unlike
#: TPEx's site, this OpenAPI dataset does not vary its field names between
#: calls, so there is no per-request ``fields`` array to inspect the way
#: ``app.data.providers.tpex`` does). Kept as a named constant, not inlined,
#: so :func:`normalize_shares_by_header` reads the same way that module's
#: header lookup does.
_STOCK_DAY_ALL_VOLUME_HEADER: Final[str] = "TradeVolume"

#: Cross-check sample (D-3): a fixed symbol plus random picks from the
#: payload, total capped at this size. "固定清單加隨機抽樣，seed 要記錄".
_FIXED_CROSS_CHECK_SYMBOLS: Final[tuple[str, ...]] = ("2330",)
_CROSS_CHECK_SAMPLE_SIZE: Final[int] = 3


def normalize_shares_by_header(volume_header: str, raw_value: int) -> int:
    """1 張 = 1,000 股 when ``volume_header`` names a lot-based unit (張/仟/千).

    Mirrors ``app.data.providers.tpex.TpexAdapter``'s header-driven detection
    instead of hardcoding "this dataset is always in shares" -- see module
    docstring for why ``STOCK_DAY_ALL``'s actual header is a defensive no-op
    today.
    """
    if any(marker in volume_header for marker in ("張", "仟", "千")):
        return raw_value * 1000
    return raw_value


class SessionCertificationFailed(Exception):
    """Internal signal: the batch's trading session could not be self-certified."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _empty_outcome(reason: str) -> SnapshotKindOutcome:
    return SnapshotKindOutcome(status="failed", row_count=0, expected_count=None, reason=reason)


class TwseSnapshotAdapter(MarketSnapshotProvider):
    """``MarketSnapshotProvider`` capturing TWSE's four whole-market PIT snapshot kinds."""

    source_id: ClassVar[str] = SOURCE_ID

    def __init__(
        self,
        *,
        client: RateLimitedClient | None = None,
        finmind: FinMindAdapter | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        candidate_session_date: Callable[[], date] | None = None,
        sample_seed: int | None = None,
    ) -> None:
        self._client = client or RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None
        self._finmind = finmind or FinMindAdapter()
        self._owns_finmind = finmind is None
        self._clock = clock
        self._candidate_session_date = candidate_session_date or self._default_candidate_session
        #: Recorded (never silently regenerated per call) so the cross-check
        #: is reproducible and the seed can be surfaced in ``reason`` text
        #: (D-3: "seed 要記錄").
        self._sample_seed = (
            sample_seed if sample_seed is not None else random.SystemRandom().randrange(2**32)
        )
        self._rng = random.Random(self._sample_seed)
        self._sector_profile_adapter = TwseSectorProfileAdapter(client=self._client)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
        if self._owns_finmind:
            self._finmind.close()

    def _default_candidate_session(self) -> date:
        return self._clock().astimezone(TAIPEI).date()

    # -- orchestration ----------------------------------------------------

    def get_latest_snapshot(self) -> SnapshotResult:
        now = self._clock()
        candidate = self._candidate_session_date()

        bars_rows, bars_reason = self._fetch_bars()
        sector_entries, sector_reason = self._fetch_sector_profile()
        dividend_rows, dividend_reason = self._fetch_dividend_announce()

        if bars_rows is None:
            # Without a parsed bars payload there is nothing to cross-check a
            # candidate session against -- the whole batch is undated.
            return self._all_failed_result(
                now, reason=bars_reason or "STOCK_DAY_ALL 無法解析，無法自證交易日"
            )

        try:
            session_date, self_certified = self._certify_session(bars_rows, candidate)
        except SessionCertificationFailed as exc:
            return self._all_failed_result(now, reason=exc.reason)

        bars_outcome = SnapshotKindOutcome(status="ok", row_count=len(bars_rows), reason=None)

        listing_rows: list[ListingSnapshotRow] = []
        classification_rows: list[ClassificationSnapshotRow] = []
        listing_outcome: SnapshotKindOutcome
        classification_outcome: SnapshotKindOutcome
        if sector_entries is None:
            listing_outcome = _empty_outcome(sector_reason or "t187ap03_L 無法解析")
            classification_outcome = _empty_outcome(sector_reason or "t187ap03_L 無法解析")
        else:
            # Listing is the FULL t187ap03_L common-stock population, not
            # intersected with STOCK_DAY_ALL's symbol set (qa-reviewer wave-1
            # blocking finding: intersecting with bars made the bars coverage
            # denominator a subset of its own numerator, so the 0.98 gate
            # could never fail no matter how little of the market
            # STOCK_DAY_ALL actually returned that day). A symbol with no
            # trade today (or suspended) stays in the listing snapshot and is
            # counted as a category-① "missing" bar downstream (D-4/D-7),
            # exactly as the ADR specifies for "no suspension-list source".
            unresolved_codes: set[str] = set()
            for entry in sector_entries:
                sector_name = TWSE_SECTOR_CODE_TO_NAME.get(entry.sector)
                if sector_name is None:
                    unresolved_codes.add(entry.sector)
                    continue
                security_type = (
                    SECURITY_TYPE_TDR
                    if entry.sector == _TDR_SECTOR_CODE
                    else SECURITY_TYPE_COMMON_STOCK
                )
                listing_rows.append(
                    ListingSnapshotRow(symbol=entry.symbol, security_type=security_type)
                )
                classification_rows.append(
                    ClassificationSnapshotRow(
                        symbol=entry.symbol, sector_code=entry.sector, sector_name=sector_name
                    )
                )
            listing_rows.sort(key=lambda row: row.symbol)
            classification_rows.sort(key=lambda row: row.symbol)
            listing_outcome = SnapshotKindOutcome(status="ok", row_count=len(listing_rows))
            classification_reason = (
                "以下產業別代碼未收錄於 TWSE_SECTOR_CODE_TO_NAME，"
                f"已略過：{sorted(unresolved_codes)}"
                if unresolved_codes
                else None
            )
            classification_outcome = SnapshotKindOutcome(
                status="ok", row_count=len(classification_rows), reason=classification_reason
            )

        dividend_outcome: SnapshotKindOutcome
        if dividend_rows is None:
            dividend_outcome = _empty_outcome(dividend_reason or "TWT48U_ALL 無法解析")
            dividend_rows = []
        else:
            dividend_outcome = SnapshotKindOutcome(status="ok", row_count=len(dividend_rows))

        return SnapshotResult(
            as_of=now,
            source=self.source_id,
            session_date=session_date,
            session_date_self_certified=self_certified,
            bars=bars_outcome,
            bars_rows=tuple(bars_rows),
            listing=listing_outcome,
            listing_rows=tuple(listing_rows),
            classification=classification_outcome,
            classification_rows=tuple(classification_rows),
            dividend_announce=dividend_outcome,
            dividend_announce_rows=tuple(dividend_rows),
        )

    def _all_failed_result(self, now: datetime, *, reason: str) -> SnapshotResult:
        outcome = _empty_outcome(reason)
        return SnapshotResult(
            as_of=now,
            source=self.source_id,
            session_date=None,
            session_date_self_certified=False,
            bars=outcome,
            listing=outcome,
            classification=outcome,
            dividend_announce=outcome,
        )

    # -- session self-certification (D-3, C-12) ----------------------------

    def _certify_session(
        self, bars_rows: Sequence[BarSnapshotRow], candidate: date
    ) -> tuple[date, bool]:
        """Cross-check ``candidate`` against FinMind for a small symbol sample.

        Never falls back to the wall clock or to trying other candidate
        dates: a failed cross-check means "failed", full stop (D-3: "完全相符
        才認定快照屬於該日，否則記 failed").
        """
        by_symbol = {row.symbol: row for row in bars_rows}
        symbols = self._pick_cross_check_symbols(sorted(by_symbol))
        if not symbols:
            raise SessionCertificationFailed(f"沒有可供交叉比對的標的（seed={self._sample_seed}）")
        for symbol in symbols:
            result = self._finmind.get_daily_bars(symbol, candidate, candidate)
            matching = next((bar for bar in result.bars if bar.date == candidate), None)
            if matching is None:
                raise SessionCertificationFailed(
                    f"FinMind 交叉比對失敗：{symbol} 於候選交易日 {candidate.isoformat()} "
                    f"查無資料（seed={self._sample_seed}，樣本={symbols}）"
                )
            payload_row = by_symbol[symbol]
            if matching.close != payload_row.close or matching.volume != payload_row.shares:
                raise SessionCertificationFailed(
                    f"FinMind 交叉比對不相符：{symbol} 於候選交易日 {candidate.isoformat()} "
                    f"收盤/成交量與 STOCK_DAY_ALL 不一致（seed={self._sample_seed}，"
                    f"樣本={symbols}）"
                )
        logger.info(
            "session date %s self-certified via FinMind cross-check (seed=%d, symbols=%s)",
            candidate.isoformat(),
            self._sample_seed,
            symbols,
        )
        return candidate, True

    def _pick_cross_check_symbols(self, available: Sequence[str]) -> list[str]:
        fixed = [symbol for symbol in _FIXED_CROSS_CHECK_SYMBOLS if symbol in available]
        pool = [symbol for symbol in available if symbol not in fixed]
        remaining = max(0, _CROSS_CHECK_SAMPLE_SIZE - len(fixed))
        sampled = self._rng.sample(pool, k=min(remaining, len(pool))) if pool else []
        return fixed + sampled

    # -- fetch: STOCK_DAY_ALL (bars only; listing comes from t187ap03_L) ---

    def _fetch_bars(self) -> tuple[list[BarSnapshotRow] | None, str | None]:
        try:
            response = self._client.get(TWSE_STOCK_LIST_PATH)
        except httpx.TransportError as exc:
            return None, f"連線失敗（{exc.__class__.__name__}）：{exc}"
        if response.status_code != httpx.codes.OK:
            return None, f"STOCK_DAY_ALL 回傳 HTTP {response.status_code}，非預期狀態碼"
        try:
            payload = response.json()
        except ValueError:
            return None, "STOCK_DAY_ALL 回應非 JSON，可能是端點路徑或格式已變更"
        if not isinstance(payload, list):
            return None, f"STOCK_DAY_ALL 回應非陣列（收到 {type(payload).__name__}）"

        rows: list[BarSnapshotRow] = []
        skipped = 0
        for row in payload:
            try:
                rows.append(self._parse_bar_row(row))
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable STOCK_DAY_ALL row: %s", exc)
                skipped += 1
        if not rows:
            return None, f"STOCK_DAY_ALL 回應中沒有任何可解析的列（略過 {skipped} 列）"
        return rows, None

    def _parse_bar_row(self, row: Any) -> BarSnapshotRow:
        if not isinstance(row, dict):
            raise UnparseableRowError(f"row is not an object: {row!r}")
        symbol = row.get("Code")
        if not isinstance(symbol, str) or not symbol.strip():
            raise UnparseableRowError(f"missing/blank Code in row: {row!r}")
        try:
            open_price = parse_decimal_cell(str(row.get("OpeningPrice", "")))
            high_price = parse_decimal_cell(str(row.get("HighestPrice", "")))
            low_price = parse_decimal_cell(str(row.get("LowestPrice", "")))
            close_price = parse_decimal_cell(str(row.get("ClosingPrice", "")))
            shares = parse_int_cell(str(row.get("TradeVolume", "")))
            traded_value = parse_decimal_cell(str(row.get("TradeValue", "")))
        except UnparseableRowError:
            raise
        shares = normalize_shares_by_header(_STOCK_DAY_ALL_VOLUME_HEADER, shares)
        change_raw = row.get("Change")
        change: Decimal | None
        try:
            change = Decimal(str(change_raw)) if change_raw not in (None, "", "--") else None
        except InvalidOperation:
            change = None
        return BarSnapshotRow(
            symbol=symbol.strip(),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            shares=shares,
            traded_value=traded_value,
            change=change,
        )

    # -- fetch: t187ap03_L (classification + full listing population) -----

    def _fetch_sector_profile(self) -> tuple[list[Any] | None, str | None]:
        result = self._sector_profile_adapter.fetch()
        if not result.ok:
            return None, result.reason
        return list(result.entries), None

    # -- fetch: TWT48U_ALL (dividend announcements, verbatim) ---------------

    def _fetch_dividend_announce(
        self,
    ) -> tuple[list[DividendAnnounceSnapshotRow] | None, str | None]:
        try:
            response = self._client.get(TWSE_EX_DIVIDEND_PATH)
        except httpx.TransportError as exc:
            return None, f"連線失敗（{exc.__class__.__name__}）：{exc}"
        if response.status_code != httpx.codes.OK:
            return None, f"TWT48U_ALL 回傳 HTTP {response.status_code}，非預期狀態碼"
        try:
            payload = response.json()
        except ValueError:
            return None, "TWT48U_ALL 回應非 JSON，可能是端點路徑或格式已變更"
        if not isinstance(payload, list):
            return None, f"TWT48U_ALL 回應非陣列（收到 {type(payload).__name__}）"

        rows: list[DividendAnnounceSnapshotRow] = []
        skipped = 0
        for row in payload:
            if not isinstance(row, dict):
                skipped += 1
                continue
            symbol = row.get("Code")
            if not isinstance(symbol, str) or not symbol.strip():
                # No symbol means no usable (content_hash, key) primary key
                # for this row -- it cannot be stored, only counted as
                # skipped (never silently merged into another row).
                skipped += 1
                continue
            raw = {str(k): "" if v is None else str(v) for k, v in row.items()}
            ex_date: date | None
            try:
                ex_date = parse_twse_date(str(row.get("Date", "")))
            except UnparseableRowError:
                ex_date = None
            rows.append(
                DividendAnnounceSnapshotRow(symbol=symbol.strip(), ex_date=ex_date, raw=raw)
            )
        if not rows:
            return None, f"TWT48U_ALL 回應中沒有任何可解析的列（略過 {skipped} 列）"
        return rows, None
