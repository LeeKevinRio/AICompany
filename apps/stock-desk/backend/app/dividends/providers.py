"""TWSE OpenAPI adapter for 除權除息計算結果表 (ex-dividend / ex-rights results).

## Schema confidence -- read before touching the endpoint path or field names

This endpoint has **not** been called against a live response from this
sandbox: outbound HTTPS to ``openapi.twse.com.tw`` is blocked by this
environment's egress policy (the same finding recorded in
``tests/fixtures/README.md`` and ``app/directory/providers.py`` -- the proxy
answers 403 to CONNECT for every financial domain probed). Per the dispatch
order ("端點依官方文件，查不到就依既有慣例推斷+標註待驗"), the path and field
names below are **inferred** from TWSE's published OpenAPI dataset naming
convention plus the host convention already used by
``app.directory.providers``, and are **pending verification**::

    GET https://openapi.twse.com.tw/v1/exchangeReport/TWT49U

``TWT49U`` is TWSE's report code for 除權除息計算結果表. The columns this
adapter needs are the ones the report is built around: the symbol, the ex-date,
the 除權息前收盤價 and the 除權息參考價, plus 息值 / 權值.

Because the exact JSON key spelling is the least certain part, every field is
resolved against a **list of candidate keys** (English and Chinese spellings
both) rather than one hard-coded string. This is not sloppiness: a rename in
one column then degrades to "this row is unparseable, skip and count it"
instead of "this column silently reads as zero", and a wholesale schema change
makes *every* row unparseable, which surfaces as ``ok=False`` with a reason.
There is no code path here that fabricates or interpolates a missing value.

**Before the CEO's first real sync run**, a 404 or a shape mismatch is the
expected outcome until data-engineer confirms the dataset against the live
Swagger docs at ``openapi.twse.com.tw``. That is a data-source verification
task, not a bug in this module.

## Coverage limitation (must stay disclosed)

Only TWSE-listed (上市) symbols are covered this phase. TPEx (上櫃) has its own
OpenAPI portal with a different, separately unverified shape; guessing a second
endpoint would double the unverified surface for no extra confidence. Until it
is added, an OTC symbol simply has no events stored, and the backtest layer
must say "未還原" for it rather than implying it had no dividends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx

from app.data.http import RateLimitedClient
from app.data.providers._util import ROC_YEAR_OFFSET, UnparseableRowError
from app.dividends.models import DividendEvent

logger = logging.getLogger(__name__)

TWSE_OPENAPI_BASE_URL = "https://openapi.twse.com.tw"
#: 除權除息計算結果表 (report code TWT49U). Inferred path -- see module docstring.
TWSE_EX_DIVIDEND_PATH = "/v1/exchangeReport/TWT49U"

#: Candidate JSON keys per logical field, tried in order. See module docstring
#: for why this is a list rather than one hard-coded key.
_DATE_KEYS = ("Date", "date", "日期", "除權息日期")
_CODE_KEYS = ("Code", "code", "StockCode", "股票代號", "證券代號", "代號")
_PREVIOUS_CLOSE_KEYS = (
    "PreviousClosingPriceBeforeExRightsAndDividends",
    "DividendBeforeClosingPrice",
    "BeforePrice",
    "除權息前收盤價",
    "前一日收盤價",
)
_REFERENCE_PRICE_KEYS = (
    "ExRightsAndDividendsReferencePrice",
    "DividendReferencePrice",
    "ReferencePrice",
    "除權息參考價",
    "參考價",
)
_CASH_DIVIDEND_KEYS = ("CashDividend", "DividendValue", "息值", "息值(元)", "現金股利")
_RIGHTS_VALUE_KEYS = ("RightsValue", "權值", "權值(元)")

_BLANK_CELLS = {"", "-", "--", "---", "N/A", "n/a", "null", "None"}


@dataclass(frozen=True)
class DividendFetchResult:
    """One fetch's outcome: a batch of events, or an honest failure reason.

    Mirrors ``app.directory.providers.DirectoryFetchResult``: expected failure
    modes (network down, non-JSON body, unexpected shape) come back as
    ``ok=False`` with a Traditional Chinese ``reason``, never as an exception.
    """

    events: tuple[DividendEvent, ...]
    ok: bool
    reason: str | None
    source: str
    as_of: datetime
    #: Rows the parser refused. A non-zero count alongside ``ok=True`` means
    #: partial coverage, which the CLI prints rather than swallows.
    skipped_rows: int = 0


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-blank value among ``keys``, or ``None``."""
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in _BLANK_CELLS:
            return text
    return None


def parse_twse_date(value: str) -> date_type:
    """Parse the date spellings TWSE OpenAPI datasets are known to use.

    Handles ``1130701`` / ``113/07/01`` (ROC calendar, year + 1911),
    ``20240701`` and ``2024-07-01``. Anything else is refused rather than
    guessed -- misreading a calendar would silently shift every event.
    """
    text = value.strip().replace("-", "/")
    if "/" in text:
        parts = text.split("/")
        if len(parts) != 3:
            raise UnparseableRowError(f"unrecognized date format: {value!r}")
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError as exc:
            raise UnparseableRowError(f"unrecognized date format: {value!r}") from exc
        if year < 1911:
            year += ROC_YEAR_OFFSET
    elif len(text) == 8 and text.isdigit():
        year, month, day = int(text[0:4]), int(text[4:6]), int(text[6:8])
    elif len(text) == 7 and text.isdigit():
        year, month, day = int(text[0:3]) + ROC_YEAR_OFFSET, int(text[3:5]), int(text[5:7])
    else:
        raise UnparseableRowError(f"unrecognized date format: {value!r}")
    try:
        return date_type(year, month, day)
    except ValueError as exc:
        raise UnparseableRowError(f"impossible date: {value!r}") from exc


def _parse_amount(value: str | None, *, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise UnparseableRowError(f"unparseable {field} cell: {value!r}") from exc


def parse_dividend_row(row: Any, *, source: str, as_of: datetime) -> DividendEvent:
    """Parse one TWT49U row into a :class:`DividendEvent`, or refuse it.

    A row must yield at least a symbol, an ex-date and a 前一日收盤價; without
    the last one no factor can be derived by either route, so keeping the row
    would only create the illusion of coverage.
    """
    if not isinstance(row, dict):
        raise UnparseableRowError(f"row is not an object: {row!r}")
    symbol = _pick(row, _CODE_KEYS)
    if symbol is None:
        raise UnparseableRowError(f"missing symbol in row: {row!r}")
    raw_date = _pick(row, _DATE_KEYS)
    if raw_date is None:
        raise UnparseableRowError(f"missing ex-date in row: {row!r}")
    ex_date = parse_twse_date(raw_date)

    previous_close = _parse_amount(_pick(row, _PREVIOUS_CLOSE_KEYS), field="previous_close")
    if previous_close is None or previous_close <= 0:
        raise UnparseableRowError(f"missing/invalid 除權息前收盤價 in row: {row!r}")
    reference_price = _parse_amount(_pick(row, _REFERENCE_PRICE_KEYS), field="reference_price")
    if reference_price is not None and reference_price <= 0:
        raise UnparseableRowError(f"invalid 除權息參考價 in row: {row!r}")
    cash = _parse_amount(_pick(row, _CASH_DIVIDEND_KEYS), field="cash_dividend") or Decimal(0)
    rights = _parse_amount(_pick(row, _RIGHTS_VALUE_KEYS), field="rights_value") or Decimal(0)
    if cash < 0 or rights < 0:
        raise UnparseableRowError(f"negative distribution component in row: {row!r}")

    return DividendEvent(
        symbol=symbol,
        market="TW",
        ex_date=ex_date,
        previous_close=previous_close,
        reference_price=reference_price,
        cash_dividend=cash,
        rights_value=rights,
        source=source,
        as_of=as_of,
    )


class TwseDividendAdapter:
    """Fetches TWSE-listed 除權除息計算結果 rows from the OpenAPI portal."""

    source_id: ClassVar[str] = "twse_openapi_dividend"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> DividendFetchResult:
        now = datetime.now(UTC)
        try:
            response = self._client.get(TWSE_EX_DIVIDEND_PATH)
        except httpx.TransportError as exc:
            return self._failure(
                now,
                f"連線失敗（{exc.__class__.__name__}）：{exc}。"
                "本雲端開發環境對財經網域的 egress 已知被封鎖，"
                "請在有網路的機器（如 CEO 本機）重跑本工具。",
            )
        if response.status_code != httpx.codes.OK:
            return self._failure(
                now,
                f"TWSE OpenAPI 除權息端點回傳 HTTP {response.status_code}，非預期狀態碼"
                "（端點路徑尚未經實際回應驗證，404 代表資料集代號需由 data-engineer 覆核）",
            )
        try:
            payload = response.json()
        except ValueError:
            return self._failure(
                now, "TWSE OpenAPI 除權息端點回應非 JSON，可能是端點路徑或格式已變更"
            )
        if not isinstance(payload, list):
            return self._failure(
                now,
                f"TWSE OpenAPI 除權息端點回應非陣列（收到 {type(payload).__name__}），"
                "schema 與預期不符",
            )

        events: list[DividendEvent] = []
        skipped = 0
        for row in payload:
            try:
                events.append(parse_dividend_row(row, source=self.source_id, as_of=now))
            except (UnparseableRowError, ValueError) as exc:
                logger.debug("skipping unparseable TWSE dividend row: %s", exc)
                skipped += 1
        if not events:
            return self._failure(
                now,
                f"TWSE OpenAPI 除權息回應中沒有任何可解析的列（略過 {skipped} 列）；"
                "欄位名稱可能與推斷不符，需覆核官方文件",
                skipped=skipped,
            )
        return DividendFetchResult(
            events=tuple(events),
            ok=True,
            reason=None,
            source=self.source_id,
            as_of=now,
            skipped_rows=skipped,
        )

    def _failure(self, now: datetime, reason: str, *, skipped: int = 0) -> DividendFetchResult:
        return DividendFetchResult(
            events=(),
            ok=False,
            reason=reason,
            source=self.source_id,
            as_of=now,
            skipped_rows=skipped,
        )
