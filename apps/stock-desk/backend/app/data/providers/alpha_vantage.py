"""Alpha Vantage daily bar adapter -- primary source for US-market symbols.

Per ADR-0003 (accepted 2026-07-23) and ADR-0005 決策一 point 2, this adapter
serves **individual securities only** (stocks/ETFs a user actually holds). It
is never used for index series -- Alpha Vantage does not participate in the
index path at all, so its whole free-tier daily budget stays reserved for
symbols the user holds (see ``app/data/providers/yfinance.py`` for indices).

Data source: Alpha Vantage ``TIME_SERIES_DAILY`` function. ADR-0003 records
that whether the free tier still offers the adjusted variant
(``TIME_SERIES_DAILY_ADJUSTED``) is one of its "尚缺的事實" -- unverified in
this build -- so this adapter deliberately uses the unadjusted
``TIME_SERIES_DAILY`` function, which has historically been the more reliably
free one.

Endpoint (documented per Alpha Vantage's public API reference; queried
against project knowledge on 2026-07-23)::

    GET https://www.alphavantage.co/query
        ?function=TIME_SERIES_DAILY&symbol=<symbol>&outputsize=compact&apikey=<key>

VERIFICATION STATUS (2026-08-16, CEO 本機真實驗證，見
``work/stock-desk-已知限制與後續.md`` 2026-08-16 二輪記錄):
``ALPHA_VANTAGE_API_KEY`` is confirmed valid -- a real request against this
endpoint succeeded. That same run also found the assumption baked into this
file until now (``outputsize=full``, i.e. "full request history") to be
**stale/wrong**: Alpha Vantage's live response for ``outputsize=full`` was::

    {"Information": "The outputsize=full parameter value is a premium
     feature for the TIME_SERIES_DAILY endpoint..."}

i.e. ``full`` now requires a paid plan; only ``outputsize=compact`` (the
vendor's documented "latest ~100 data points") remains free. This module was
switched to ``compact`` in response (2026-08-16, data-engineer) -- see
"Compact coverage and the deep-history problem" below for what that changes
for callers. **This specific code fix is itself unverified against a live
response** (the finding above only confirms the *old* ``full`` value fails;
it does not yet confirm ``compact`` succeeds against a real response in this
build) -- pending CEO re-running ``scripts/verify_market_data.py`` to confirm
the corrected adapter against live Alpha Vantage traffic.

Compact coverage and the deep-history problem: Alpha Vantage's ``compact``
mode returns roughly the most recent 100 trading days, regardless of what
``start``/``end`` a caller asks for. That is enough for the daily indicator /
advice-card paths (they look back on the order of tens of bars), but it is
**not** enough for the walk-forward backtest, whose default geometry alone
(``DEFAULT_TRAIN_SIZE=252`` + ``DEFAULT_TEST_SIZE=63`` in
``app/api/backtest.py``) already needs 315 bars. Silently handing back
whatever partial window ``compact`` happens to contain, labelled ``FRESH``,
would let a caller believe it received the requested range when it did not --
exactly the kind of silent truncation this company's data-engineering red
line forbids. Instead, after every successful fetch this adapter compares the
*earliest* date Alpha Vantage's response actually carries against the
caller's requested ``start``: if the response does not reach back that far,
the adapter declines outright (``DataStatus.UNAVAILABLE``, honest reason
text) rather than returning a truncated series under a status that claims
success. Because ``app.data.service.MarketDataService`` already tries each
provider in order and only advances past a rung that declined
(``ADR-0005`` 決策四: AV -> yfinance -> cache -> unavailable), this single
change is enough to route any deep-history request (backtest chief among
them) to the yfinance backup automatically, with no change needed to
``app/api/backtest.py`` or ``app/services/market.py``. If yfinance also
cannot help, the ladder's existing, already-honest fallbacks apply
unchanged: cached data if any, else the backtest endpoint's own
``status="insufficient_data"`` response with the true bar count spelled out
(never a fabricated or interpolated fill).

Response shape (JSON)::

    {
      "Meta Data": {
        "1. Information": "Daily Prices (open, high, low, close) and volumes",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-05",
        "4. Output Size": "Compact",
        "5. Time Zone": "US/Eastern"
      },
      "Time Series (Daily)": {
        "2024-01-05": {
          "1. open": "182.0000", "2. high": "182.7600",
          "3. low": "180.1700", "4. close": "181.1800",
          "5. volume": "62303300"
        },
        ...
      }
    }

Alpha Vantage returns HTTP 200 even for error conditions, signalled instead
by one of three top-level keys in the JSON body: ``"Error Message"`` (bad
request/unknown symbol), ``"Note"`` (the vendor's own rate-limit message),
``"Information"`` (commonly used for "this requires a premium key" notices).
All three are treated as ``UNAVAILABLE`` with a Traditional Chinese reason
carried on ``ProviderResult.reason``.

Quota (ADR-0005 決策三): every call to this adapter first reserves a slot in
``app.data.quota.QuotaLedger`` *before* issuing any HTTP request. If the
day's budget (``ALPHA_VANTAGE_DAILY_LIMIT`` minus ``ALPHA_VANTAGE_SAFETY_MARGIN``)
is already spent, the adapter returns ``UNAVAILABLE`` without making a
request at all -- this is asserted in tests via a transport spy that must
observe zero calls.

Symbol handling (ADR-0005 決策三 ticker 正規化): the input ``symbol`` is run
through ``app.data.providers.us_symbols.canonical_us_symbol`` and the
resulting canonical (dotted) form is what ends up on every returned
``PriceBar.symbol`` -- never the provider-wire symbol used to build the HTTP
request (see ``us_symbols.to_provider_symbol``).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers.us_symbols import (
    ALPHA_VANTAGE_PROVIDER_ID,
    InvalidUsSymbolError,
    canonical_us_symbol,
    to_provider_symbol,
)
from app.data.quota import (
    QuotaConfigError,
    QuotaLedger,
    resolve_min_interval_seconds,
    resolve_quota_config,
)

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co"
QUERY_PATH = "/query"
FUNCTION = "TIME_SERIES_DAILY"
#: Fixed 2026-08-16: CEO's live verification found ``full`` now requires a
#: paid plan (see the module docstring's "VERIFICATION STATUS" section);
#: ``compact`` (~100 most recent daily bars) is what the free tier still
#: allows.
OUTPUT_SIZE = "compact"
CURRENCY = "USD"
API_KEY_ENV_VAR = "ALPHA_VANTAGE_API_KEY"

_SERIES_KEY = "Time Series (Daily)"


def _unavailable(now: datetime, *, reason: str) -> ProviderResult:
    return ProviderResult(
        bars=[],
        status=DataStatus.UNAVAILABLE,
        as_of=now,
        source=AlphaVantageAdapter.source_id,
        staleness_minutes=None,
        reason=reason,
    )


def _check_response_errors(payload: Any) -> str | None:
    """Return a Traditional Chinese reason if ``payload`` signals an AV-side error.

    ``None`` means no error signal was found (caller still has to check
    whether the payload actually contains a usable series).
    """
    if not isinstance(payload, dict):
        return None
    if "Error Message" in payload:
        return f"Alpha Vantage 回報請求錯誤：{payload['Error Message']}"
    if "Note" in payload:
        return f"Alpha Vantage 回報已達其自訂的呼叫頻率限制：{payload['Note']}"
    if "Information" in payload:
        return f"Alpha Vantage 回報此功能目前對本 API key 不可用：{payload['Information']}"
    return None


def _earliest_series_date(series: dict[str, Any]) -> date | None:
    """The earliest trading date ``series`` (the raw, unfiltered payload) claims.

    Used purely to measure how far back a ``compact`` response actually
    reaches -- deliberately independent of whether each row's own fields
    parse cleanly, because even an unparseable placeholder row (e.g. an
    "N/A" row for a still-listed symbol) still tells us which date Alpha
    Vantage attempted to include, which is what coverage-depth is about.
    Returns ``None`` when ``series`` has no ISO-formatted date keys at all.
    """
    dates: list[date] = []
    for key in series:
        try:
            dates.append(date.fromisoformat(key))
        except ValueError:
            continue
    return min(dates) if dates else None


class AlphaVantageAdapter(MarketDataProvider):
    """Primary adapter for US-market daily bars (individual securities only)."""

    source_id: ClassVar[str] = "alpha_vantage"

    def __init__(
        self,
        client: RateLimitedClient | None = None,
        *,
        ledger: QuotaLedger | None = None,
        min_interval_seconds: float | None = None,
    ) -> None:
        resolved_interval = (
            min_interval_seconds
            if min_interval_seconds is not None
            else resolve_min_interval_seconds()
        )
        self._client = client or RateLimitedClient(
            base_url=ALPHA_VANTAGE_BASE_URL, min_interval_seconds=resolved_interval
        )
        self._owns_client = client is None
        self._ledger = ledger or QuotaLedger()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        now = datetime.now(UTC)

        api_key = os.environ.get(API_KEY_ENV_VAR)
        if not api_key:
            logger.warning(
                "Alpha Vantage adapter unavailable: %s environment variable is not set",
                API_KEY_ENV_VAR,
            )
            return _unavailable(now, reason="Alpha Vantage API key 尚未設定，暫不可用。")

        try:
            canonical = canonical_us_symbol(symbol)
        except InvalidUsSymbolError as exc:
            logger.warning("Alpha Vantage: rejecting invalid US symbol %r: %s", symbol, exc)
            return _unavailable(
                now,
                reason=f"「{symbol}」不是合法的美股個股代號格式，可能誤用了指數或其他市場代號。",
            )

        try:
            config = resolve_quota_config()
        except QuotaConfigError as exc:
            logger.error("Alpha Vantage quota configuration invalid: %s", exc)
            return _unavailable(now, reason="Alpha Vantage 額度設定尚未完成或有誤，暫不可用。")

        # Reserve BEFORE issuing any HTTP request (ADR-0005 約束 Q-2/Q-3): a
        # slot is spent the moment we decide to call, not after the call
        # succeeds, and a denied reservation must short-circuit here with no
        # network I/O at all.
        reservation = self._ledger.reserve(
            self.source_id,
            limit_value=config.effective_limit,
            now=now,
            reset_tz=config.reset_tz,
        )
        if not reservation.granted:
            logger.warning(
                "Alpha Vantage daily quota exhausted (%d/%d used on %s) for %s; "
                "not issuing the request",
                reservation.used,
                reservation.limit_value,
                reservation.quota_date,
                canonical,
            )
            return _unavailable(
                now,
                reason=(
                    "Alpha Vantage 今日查詢額度已用罄，本次不呼叫主來源，"
                    "請由備援來源接手。"
                ),
            )

        provider_symbol = to_provider_symbol(canonical, provider_id=ALPHA_VANTAGE_PROVIDER_ID)
        try:
            response = self._client.get(
                QUERY_PATH,
                params={
                    "function": FUNCTION,
                    "symbol": provider_symbol,
                    "outputsize": OUTPUT_SIZE,
                    "apikey": api_key,
                },
            )
        except httpx.TransportError as exc:
            logger.warning("Alpha Vantage request failed for %s: %s", canonical, exc)
            return _unavailable(now, reason="Alpha Vantage 連線逾時或發生錯誤，暫不可用。")

        if response.status_code != httpx.codes.OK:
            logger.warning(
                "Alpha Vantage returned HTTP %d for %s", response.status_code, canonical
            )
            return _unavailable(now, reason="Alpha Vantage 回應非預期的 HTTP 狀態，暫不可用。")

        try:
            payload = response.json(parse_float=Decimal)
        except ValueError:
            logger.warning("Alpha Vantage returned non-JSON body for %s", canonical)
            return _unavailable(now, reason="Alpha Vantage 回應格式無法解析，暫不可用。")

        error_reason = _check_response_errors(payload)
        if error_reason is not None:
            logger.warning("Alpha Vantage response error for %s: %s", canonical, error_reason)
            return _unavailable(now, reason=error_reason)

        # Coverage guard (2026-08-16, see module docstring "Compact coverage
        # and the deep-history problem"): ``outputsize=compact`` only reaches
        # back ~100 trading days no matter what ``start`` was requested. If
        # this response does not cover the requested start at all, declining
        # here -- rather than silently handing back a truncated window under
        # a "fresh"/success status -- lets MarketDataService's existing
        # degradation ladder try the yfinance backup, which does carry deeper
        # history.
        series = payload.get(_SERIES_KEY) if isinstance(payload, dict) else None
        if isinstance(series, dict):
            earliest = _earliest_series_date(series)
            if earliest is not None and earliest > start:
                logger.info(
                    "Alpha Vantage compact response for %s starts at %s, later than "
                    "the requested start %s; declining so the degradation ladder can "
                    "try a source with deeper history",
                    canonical,
                    earliest,
                    start,
                )
                return _unavailable(
                    now,
                    reason=(
                        "Alpha Vantage 免費方案的 outputsize=compact 僅提供最近約 100 根"
                        f"日線，本次回應最早涵蓋 {earliest.isoformat()}，"
                        f"早於請求起始日 {start.isoformat()}；為避免以不完整資料冒充完整回應，"
                        "本次不回傳，改由備援來源（如 yfinance）承接較長歷史需求。"
                    ),
                )

        bars = self._parse_payload(payload, canonical, start, end, now)
        if not bars:
            # Alpha Vantage has no documented way to distinguish "this ticker
            # does not exist" from "this ticker exists but has no data in the
            # requested window" -- both come back as an empty/near-empty
            # series object. That ambiguity is stated honestly rather than
            # guessed at (ADR-0005 D-4 / this task's red line).
            return _unavailable(
                now,
                reason=(
                    f"Alpha Vantage 查無「{canonical}」在指定區間的日線資料；"
                    "無法區分是代號不存在、已下市，或僅是暫時無資料。"
                ),
            )
        bars.sort(key=lambda bar: bar.date)
        return ProviderResult(
            bars=bars,
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
        )

    def _parse_payload(
        self, payload: Any, canonical: str, start: date, end: date, now: datetime
    ) -> list[PriceBar]:
        if not isinstance(payload, dict):
            return []
        series = payload.get(_SERIES_KEY)
        if not isinstance(series, dict):
            return []
        bars: list[PriceBar] = []
        for trade_date_str, row in series.items():
            try:
                bar = self._parse_row(trade_date_str, row, canonical, now)
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                logger.debug(
                    "skipping unparseable Alpha Vantage row for %s on %s: %s",
                    canonical,
                    trade_date_str,
                    exc,
                )
                continue
            if start <= bar.date <= end:
                bars.append(bar)
        return bars

    def _parse_row(
        self, trade_date_str: str, row: Any, canonical: str, now: datetime
    ) -> PriceBar:
        if not isinstance(row, dict):
            raise TypeError(f"row is not an object: {row!r}")
        return PriceBar(
            symbol=canonical,
            market="US",
            date=date.fromisoformat(trade_date_str),
            open=Decimal(str(row["1. open"])),
            high=Decimal(str(row["2. high"])),
            low=Decimal(str(row["3. low"])),
            close=Decimal(str(row["4. close"])),
            volume=int(Decimal(str(row["5. volume"]))),
            currency=CURRENCY,
            as_of=now,
            source=self.source_id,
        )
