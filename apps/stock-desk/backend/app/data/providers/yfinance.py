"""Yahoo Finance ("yfinance") daily bar adapter -- two distinct roles.

1. **Backup adapter for US-market individual securities**
   (:meth:`YFinanceAdapter.get_daily_bars`, the ``MarketDataProvider``
   contract method), used by ``MarketDataService`` only when Alpha Vantage's
   daily quota is spent or Alpha Vantage itself failed (ADR-0003).
2. **Sole adapter for standard index series**
   (:meth:`YFinanceAdapter.get_index_daily_bars`, deliberately *not* part of
   the ``MarketDataProvider`` ABC -- indices are not a per-security fetch and
   are wired up by a separate caller, see ADR-0005 決策五 "``app/services/
   index.py`` 一處"). Per ADR-0005 決策一:
     - Alpha Vantage never participates in the index path at all.
     - The index ``ProviderResult.status`` is **always** ``BACKUP``, even
       when the fetch succeeds -- this is a non-official data source and
       must never be labelled ``fresh`` (ADR-0005 約束 I-3).
     - Only the three symbols ADR-0005 決策一 point 4 named are in scope:
       ``^NDX`` (NASDAQ-100), ``^GSPC`` (S&P 500), ``^TWII`` (臺灣加權股價指
       數). Any other index symbol is an explicit ``insufficient_data``-style
       ``unavailable``, never a guessed proxy.

Both roles share the same unofficial "chart" endpoint and parsing logic
below; only the request symbol (and, for the per-security role, canonical
validation) differs.

Data source: Yahoo Finance's undocumented "chart" JSON endpoint -- the same
one the real ``yfinance`` PyPI package calls internally. There is no official
API contract for this; it is documented here per the widely-referenced public
pattern, queried against project knowledge on 2026-07-26, **NOT re-verified
against a live response in this sandbox** because outbound HTTPS to
``query1.finance.yahoo.com`` is blocked by the environment's egress policy --
see ``tests/fixtures/README.md``. This is the *backup* / *only* index source
by design (ADR-0003, ADR-0005): its unofficial, undocumented nature is exactly
why it never gets to be the primary path for individual securities.

Endpoint::

    GET https://query1.finance.yahoo.com/v8/finance/chart/<symbol>
        ?period1=<unix_seconds>&period2=<unix_seconds>&interval=1d

Response shape (JSON)::

    {
      "chart": {
        "result": [
          {
            "meta": {"currency": "USD", "symbol": "AAPL", ...},
            "timestamp": [1704182400, 1704268800, ...],
            "indicators": {
              "quote": [
                {"open": [...], "high": [...], "low": [...],
                 "close": [...], "volume": [...]}
              ]
            }
          }
        ],
        "error": null
      }
    }

On failure, ``"result"`` is ``null`` and ``"error"`` carries a ``code`` and a
``description`` such as ``"No data found, symbol may be delisted"``. Per this
task's red line (and ADR-0005 D-4): Yahoo's own wording ("may be delisted")
is itself an admission that it cannot reliably distinguish "this ticker never
existed / was mistyped" from "this ticker used to exist but is gone" from
"transiently no data" -- this adapter passes that ambiguity through honestly
in ``ProviderResult.reason`` rather than pretending to resolve it.

A trading day with no session for one indicator field shows up as ``null`` at
that index in each parallel array; such entries are skipped, never
interpolated. Bar dates are derived from the UTC calendar date of each Unix
timestamp -- an unverified simplification: for symbols with a very large UTC
offset intraday session start, the UTC date and the true local trading date
could in principle disagree, but for every session type in scope here
(regular US and Taiwan cash-equity market hours) the two coincide in
practice.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Final
from urllib.parse import quote

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers.us_symbols import (
    YFINANCE_PROVIDER_ID,
    InvalidUsSymbolError,
    canonical_us_symbol,
    to_provider_symbol,
)

logger = logging.getLogger(__name__)

YFINANCE_BASE_URL = "https://query1.finance.yahoo.com"
CHART_PATH_TEMPLATE = "/v8/finance/chart/{symbol}"
INTERVAL = "1d"
#: Unverified, browser-like header; Yahoo's undocumented endpoint is widely
#: reported to reject requests with no User-Agent at all.
_REQUEST_HEADERS: Final[dict[str, str]] = {"User-Agent": "Mozilla/5.0"}

#: The only index series in scope for Phase 7 (ADR-0005 決策一 point 4).
#: symbol -> (market, currency). Deliberately NOT extensible by guesswork --
#: any symbol outside this table is an explicit "not in supported range"
#: unavailable, never a proxy substitution.
INDEX_SYMBOL_METADATA: Final[dict[str, tuple[Market, str]]] = {
    "^NDX": ("US", "USD"),
    "^GSPC": ("US", "USD"),
    "^TWII": ("TW", "TWD"),
}


def _unavailable(now: datetime, *, reason: str) -> ProviderResult:
    return ProviderResult(
        bars=[],
        status=DataStatus.UNAVAILABLE,
        as_of=now,
        source=YFinanceAdapter.source_id,
        staleness_minutes=None,
        reason=reason,
    )


class YFinanceAdapter(MarketDataProvider):
    """Backup adapter for US securities; sole adapter for index series."""

    source_id: ClassVar[str] = "yfinance"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        # No documented rate limit for this unofficial endpoint (ADR-0003
        # "尚缺的事實"); the modest client-side throttle here is our own
        # conservative choice, not a claim about Yahoo's actual limit.
        self._client = client or RateLimitedClient(
            base_url=YFINANCE_BASE_URL, min_interval_seconds=1.0
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        """Backup path for an individual US security (ADR-0003 備援)."""
        now = datetime.now(UTC)
        try:
            canonical = canonical_us_symbol(symbol)
        except InvalidUsSymbolError as exc:
            logger.warning("yfinance: rejecting invalid US symbol %r: %s", symbol, exc)
            return _unavailable(
                now,
                reason=(
                    f"「{symbol}」不是合法的美股個股代號格式；指數請改用 "
                    "get_index_daily_bars。"
                ),
            )
        provider_symbol = to_provider_symbol(canonical, provider_id=YFINANCE_PROVIDER_ID)
        bars, error_reason = self._fetch(provider_symbol, canonical, "US", "USD", start, end, now)
        if error_reason is not None:
            return _unavailable(now, reason=error_reason)
        if not bars:
            return _unavailable(
                now,
                reason=(
                    f"yfinance 查無「{canonical}」在指定區間的日線資料；"
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

    def get_index_daily_bars(
        self, index_symbol: str, start: date, end: date
    ) -> ProviderResult:
        """Sole adapter for standard index series (ADR-0005 決策一).

        ``index_symbol`` must be one of :data:`INDEX_SYMBOL_METADATA`'s keys
        verbatim (e.g. ``"^NDX"``) and is passed straight through to the
        request -- it never goes through ``canonical_us_symbol`` (ADR-0005
        決策三 point 5: the ``^`` prefix is index territory, structurally
        separate from the per-security symbol path).

        The returned ``status`` is **always** ``DataStatus.BACKUP`` on
        success, never ``FRESH`` (ADR-0005 約束 I-3): this is a non-official
        source and must not be presented as a system of record, even though
        it is the only index source Phase 7 has.
        """
        now = datetime.now(UTC)
        metadata = INDEX_SYMBOL_METADATA.get(index_symbol)
        if metadata is None:
            logger.info(
                "yfinance: index symbol %r is not in the supported range %s",
                index_symbol,
                sorted(INDEX_SYMBOL_METADATA),
            )
            return _unavailable(
                now,
                reason=(
                    f"「{index_symbol}」目前不在本工具支援的指數範圍內"
                    f"（僅支援 {', '.join(sorted(INDEX_SYMBOL_METADATA))}），"
                    "本次不以其他指數或代理 ETF 替代。"
                ),
            )
        market, currency = metadata
        bars, error_reason = self._fetch(
            index_symbol, index_symbol, market, currency, start, end, now
        )
        if error_reason is not None:
            return _unavailable(now, reason=error_reason)
        if not bars:
            return _unavailable(
                now,
                reason=f"yfinance 查無「{index_symbol}」在指定區間的指數日線資料。",
            )
        bars.sort(key=lambda bar: bar.date)
        return ProviderResult(
            bars=bars,
            status=DataStatus.BACKUP,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
        )

    def _fetch(
        self,
        request_symbol: str,
        bar_symbol: str,
        market: Market,
        currency: str,
        start: date,
        end: date,
        now: datetime,
    ) -> tuple[list[PriceBar], str | None]:
        """Shared HTTP + parsing for both roles. Returns ``(bars, error_reason)``."""
        period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp())
        # period2 is exclusive-ish in practice for this endpoint, so push one
        # day past `end` to make sure `end` itself is included.
        end_boundary = datetime.combine(end, datetime.min.time(), tzinfo=UTC)
        period2 = int(end_boundary.timestamp()) + 86_400

        path = CHART_PATH_TEMPLATE.format(symbol=quote(request_symbol, safe=""))
        try:
            response = self._client.get(
                path,
                params={"period1": str(period1), "period2": str(period2), "interval": INTERVAL},
                headers=_REQUEST_HEADERS,
            )
        except httpx.TransportError as exc:
            logger.warning("yfinance request failed for %s: %s", request_symbol, exc)
            return [], "yfinance 連線逾時或發生錯誤，暫不可用。"

        if response.status_code != httpx.codes.OK:
            logger.warning(
                "yfinance returned HTTP %d for %s", response.status_code, request_symbol
            )
            return [], "yfinance 回應非預期的 HTTP 狀態，暫不可用。"

        try:
            payload = response.json(parse_float=Decimal)
        except ValueError:
            logger.warning("yfinance returned non-JSON body for %s", request_symbol)
            return [], "yfinance 回應格式無法解析，暫不可用。"

        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not isinstance(chart, dict):
            return [], "yfinance 回應缺少預期的 chart 區塊，暫不可用。"

        error = chart.get("error")
        if error:
            description = (
                error.get("description") if isinstance(error, dict) else str(error)
            )
            return [], (
                f"yfinance 回報錯誤：{description}；"
                "無法確定是代號不存在、已下市，或暫時無資料。"
            )

        results = chart.get("result")
        if not isinstance(results, list) or not results:
            return [], f"yfinance 對「{request_symbol}」未回傳任何結果區塊。"

        bars = self._parse_result(results[0], bar_symbol, market, currency, start, end, now)
        return bars, None

    def _parse_result(
        self,
        result: Any,
        bar_symbol: str,
        market: Market,
        currency: str,
        start: date,
        end: date,
        now: datetime,
    ) -> list[PriceBar]:
        if not isinstance(result, dict):
            return []
        timestamps = result.get("timestamp")
        indicators = result.get("indicators")
        if not isinstance(timestamps, list) or not isinstance(indicators, dict):
            return []
        quotes = indicators.get("quote")
        if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
            return []
        quote_data = quotes[0]
        opens = quote_data.get("open") or []
        highs = quote_data.get("high") or []
        lows = quote_data.get("low") or []
        closes = quote_data.get("close") or []
        volumes = quote_data.get("volume") or []

        bars: list[PriceBar] = []
        for idx, ts in enumerate(timestamps):
            try:
                bar = self._parse_row(
                    ts, opens, highs, lows, closes, volumes, idx, bar_symbol, market, currency, now
                )
            except (KeyError, TypeError, ValueError, InvalidOperation, IndexError) as exc:
                logger.debug(
                    "skipping unparseable yfinance row #%d for %s: %s", idx, bar_symbol, exc
                )
                continue
            if bar is not None and start <= bar.date <= end:
                bars.append(bar)
        return bars

    def _parse_row(
        self,
        ts: Any,
        opens: list[Any],
        highs: list[Any],
        lows: list[Any],
        closes: list[Any],
        volumes: list[Any],
        idx: int,
        bar_symbol: str,
        market: Market,
        currency: str,
        now: datetime,
    ) -> PriceBar | None:
        if ts is None:
            return None
        raw_values = (opens[idx], highs[idx], lows[idx], closes[idx], volumes[idx])
        if any(value is None for value in raw_values):
            # A non-trading day / data gap for this index in the parallel
            # arrays -- skipped, never interpolated or carried forward.
            return None
        trade_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
        open_price, high_price, low_price, close_price, volume_raw = raw_values
        return PriceBar(
            symbol=bar_symbol,
            market=market,
            date=trade_date,
            open=Decimal(str(open_price)),
            high=Decimal(str(high_price)),
            low=Decimal(str(low_price)),
            close=Decimal(str(close_price)),
            volume=int(Decimal(str(volume_raw))),
            currency=currency,
            as_of=now,
            source=self.source_id,
        )
