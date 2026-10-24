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

3. **Raw-response access for the replay snapshot**
   (:meth:`YFinanceAdapter.get_index_raw_responses`, ADR-0005 I-3 解釋性註記
   "adapter 一側"; follow-up N-82). It hands back, per response, the raw
   ``meta.exchangeTimezoneName`` / ``meta.gmtoffset`` values, the time the
   response was received, and, per bar, the raw timestamp, the derived session
   date and the OHLCV values. Rows whose OHLCV has a ``null`` but whose date is
   derivable and in range are not bars; they are handed back one by one as
   ``null_gap_rows`` so the snapshot never silently loses a row. Like
   ``get_index_daily_bars`` it is deliberately *not* part of the
   ``MarketDataProvider`` ABC and is never wrapped by ``IndexProviderBridge``;
   it accepts only :data:`INDEX_SYMBOL_METADATA` keys. It always issues exactly
   one request, for ``[start - 1 day, end + 1 day]``, and keeps rows by their
   derived ``session_date`` in ``[start, end]``. It is fail-closed: any failed
   request, unparseable response or **malformed row** fails the whole call (no
   bars, no partial responses). Its only consumer is the single replay fetch
   function in ``app/services/index.py``. Design rulings:
   ``work/reviews/2026-10-24-N82設計裁量點裁定-tech-architect.md``.

All roles share the same unofficial "chart" endpoint and parsing logic below
(the per-row parse exists once, in :func:`_parse_chart_row`, and the
timestamp-to-date derivation exists exactly once, in
:func:`_derive_session_date`); only the request symbol (and, for the per-security
role, canonical validation) differs.

Data source: Yahoo Finance's undocumented "chart" JSON endpoint -- the same
one the real ``yfinance`` PyPI package calls internally. There is no official
API contract for this; it is documented here per the widely-referenced public
pattern, queried against project knowledge on 2026-07-26. This is the
*backup* / *only* index source by design (ADR-0003, ADR-0005): its
unofficial, undocumented nature is exactly why it never gets to be the
primary path for individual securities.

VERIFICATION STATUS (2026-08-16, CEO 本機真實驗證，
``work/stock-desk-已知限制與後續.md`` 首輪記錄): role 2 above (the **index**
path, :meth:`YFinanceAdapter.get_index_daily_bars`) was confirmed against a
live response -- ``scripts/verify_market_data.py --index-symbol ^TWII``
returned 7 fresh bars, and this is the actual chain the current portfolio's
holdings depend on (backup for ``^TWII`` in the TW index/leverage path), so
that dependency is cleared. **Role 1 (the US-market individual-security
backup path, :meth:`YFinanceAdapter.get_daily_bars`) was NOT separately
exercised in that run** -- the verification tool only probes the index
symbol for this adapter; no live call was made against, e.g., ``AAPL``
through the ``get_daily_bars`` method. That role remains unverified against
a live response until it is (there are currently no US-market holdings to
have forced the question, per the same work-log entry). **Role 3 (the raw-
response method, :meth:`YFinanceAdapter.get_index_raw_responses`) is likewise
NOT verified against a live response**: it reuses role 2's endpoint, request
shape and parsing, but no live call has been made through it. In particular the
real ``^TWII`` timestamp time-of-day, ``meta.exchangeTimezoneName`` and
``meta.gmtoffset`` values are unverified (follow-up N-81 / 決策包 #49); handing
them back unmodified is what lets the replay gate inspect them.

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
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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


_VALUE_FIELDS: Final = ("open", "high", "low", "close", "volume")

#: The one reason given for every malformed-row failure of the raw path.
_MALFORMED_ROW_REASON: Final = "yfinance 回應含無法解析的列，暫不可用。"


@dataclass(frozen=True)
class RawChartBar:
    """One bar exactly as one row of a chart response, plus its derived date.

    ``raw_timestamp`` is the element of the response's ``timestamp`` array
    verbatim (the JSON is parsed with ``parse_float=Decimal``, so a fractional
    value arrives as ``Decimal``; a string stays a string). It is deliberately
    **not** rejected for being a non-integer: ADR-0027 D-3 stores it as
    received and the replay gate judges it. Downstream obligations for storing
    it (type-preserving serialization, strict ``type(x) is int`` reading) are in
    ``work/reviews/2026-10-24-N82設計裁量點裁定-tech-architect.md`` point 3.
    ``session_date`` is the single date derivation in this module
    (:func:`_derive_session_date`). The OHLCV values are converted the same way
    ``PriceBar``'s are.
    """

    raw_timestamp: object
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class RawNullGapRow:
    """An in-range row that has a derivable date but a ``null`` OHLCV field.

    Not a bar and never filled in; reported so the snapshot's row set is
    explainable. ``null_fields`` lists the null fields in the order open, high,
    low, close, volume.
    """

    raw_timestamp: object
    session_date: date
    null_fields: tuple[str, ...]


@dataclass(frozen=True)
class RawChartResponse:
    """One chart response: raw ``meta`` values, in-range bars and null-gap rows.

    ``exchange_timezone_name`` / ``gmtoffset`` are ``meta.exchangeTimezoneName``
    / ``meta.gmtoffset`` untouched -- any type, ``None`` when absent. Judging
    them is the replay gate's job, never this adapter's. ``received_at`` is
    taken right after the request returned successfully.
    """

    response_seq: int
    exchange_timezone_name: object
    gmtoffset: object
    bars: tuple[RawChartBar, ...]
    received_at: datetime
    null_gap_rows: tuple[RawNullGapRow, ...] = ()


@dataclass(frozen=True)
class RawChartFetch:
    """Result of :meth:`YFinanceAdapter.get_index_raw_responses`.

    All-or-nothing: either ``reason is None`` and ``responses`` holds every
    response (each with at least one bar), or ``reason`` is set and
    ``responses`` is empty. There is no partial result.
    """

    index_symbol: str
    as_of: datetime
    source: str
    responses: tuple[RawChartResponse, ...] = ()
    reason: str | None = None


class _MalformedRowError(Exception):
    """A row of a raw response that cannot be parsed; fails the whole raw fetch."""


def _raw_failure(index_symbol: str, now: datetime, *, reason: str) -> RawChartFetch:
    return RawChartFetch(
        index_symbol=index_symbol,
        as_of=now,
        source=YFinanceAdapter.source_id,
        responses=(),
        reason=reason,
    )


def _chart_columns(
    result: Any,
) -> tuple[list[Any], list[Any], list[Any], list[Any], list[Any], list[Any]] | None:
    """``(timestamps, opens, highs, lows, closes, volumes)`` of a result block, or ``None``."""
    if not isinstance(result, dict):
        return None
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    if not isinstance(timestamps, list) or not isinstance(indicators, dict):
        return None
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        return None
    quote_data = quotes[0]
    return (
        timestamps,
        quote_data.get("open") or [],
        quote_data.get("high") or [],
        quote_data.get("low") or [],
        quote_data.get("close") or [],
        quote_data.get("volume") or [],
    )


def _derive_session_date(ts: Any) -> date:
    """The only place a timestamp becomes a date (UTC calendar date of the instant).

    A test asserts ``fromtimestamp`` appears exactly once in this module, here,
    and that only :func:`_parse_chart_row` and :func:`_classify_raw_rows` call
    this function -- so no role can grow a second, divergent date derivation.
    """
    return datetime.fromtimestamp(int(ts), tz=UTC).date()


def _to_price(value: Any) -> Decimal:
    return Decimal(str(value))


def _to_volume(value: Any) -> int:
    return int(Decimal(str(value)))


def _parse_chart_row(
    ts: Any,
    opens: list[Any],
    highs: list[Any],
    lows: list[Any],
    closes: list[Any],
    volumes: list[Any],
    idx: int,
) -> RawChartBar | None:
    """The one per-row parse for bars, shared by every role (bars and raw responses alike)."""
    if ts is None:
        return None
    raw_values = (opens[idx], highs[idx], lows[idx], closes[idx], volumes[idx])
    if any(value is None for value in raw_values):
        # A non-trading day / data gap for this index in the parallel
        # arrays -- skipped, never interpolated or carried forward.
        return None
    session_date = _derive_session_date(ts)
    open_price, high_price, low_price, close_price, volume_raw = raw_values
    return RawChartBar(
        raw_timestamp=ts,
        session_date=session_date,
        open=_to_price(open_price),
        high=_to_price(high_price),
        low=_to_price(low_price),
        close=_to_price(close_price),
        volume=_to_volume(volume_raw),
    )


def _classify_raw_rows(
    columns: tuple[list[Any], list[Any], list[Any], list[Any], list[Any], list[Any]],
    start: date,
    end: date,
) -> tuple[list[RawChartBar], list[RawNullGapRow]]:
    """Split one raw response into bars and null-gap rows, or raise on a malformed row.

    Every row is exactly one of:

    * **malformed** -- parallel arrays of different length (an absent array
      counts as empty), a timestamp that is ``None`` or a ``bool``, a timestamp
      that cannot become a date, or a non-null value that cannot be converted.
      Raises :class:`_MalformedRowError` whether or not the row would fall in
      range: a malformed row's date cannot be trusted either way;
    * a **null gap** -- a derivable, in-range date with at least one ``null``
      OHLCV field: reported in the second list, never a bar;
    * a **bar** -- built by :func:`_parse_chart_row`, kept only when its derived
      date is in ``[start, end]``. Source order is kept, nothing is de-duplicated.

    A null-gap row whose derived date is outside ``[start, end]`` is dropped
    like an out-of-range bar.

    Edge conventions (pinned by tests; risk review N-97):

    * "A timestamp that cannot become a date" is decided by Python ``int()``
      followed by the date derivation: a JSON number such as ``1704157200.5``
      (parsed as ``Decimal``) converts and is a bar; the string
      ``"1704157200.5"`` does not and is malformed. The raw value is kept as
      received either way.
    * A non-finite **price** (``NaN`` / ``Infinity`` JSON literals) is not
      malformed: it converts to a non-finite ``Decimal`` and the row is a bar,
      left for the replay gate's value checks (treated like any other value).
    * A non-finite **volume** is malformed: ``int()`` of a non-finite
      ``Decimal`` raises, so the whole fetch fails.
    """
    timestamps, opens, highs, lows, closes, volumes = columns
    arrays = (opens, highs, lows, closes, volumes)
    if any(not isinstance(a, list) or len(a) != len(timestamps) for a in arrays):
        raise _MalformedRowError("timestamp and OHLCV arrays differ in length")
    bars: list[RawChartBar] = []
    gaps: list[RawNullGapRow] = []
    for idx, ts in enumerate(timestamps):
        if ts is None or isinstance(ts, bool):
            raise _MalformedRowError(f"row #{idx}: unusable timestamp {ts!r}")
        try:
            session_date = _derive_session_date(ts)
            values = tuple(array[idx] for array in arrays)
            null_fields = tuple(
                name for name, value in zip(_VALUE_FIELDS, values, strict=True) if value is None
            )
            if null_fields:
                for name, value in zip(_VALUE_FIELDS, values, strict=True):
                    if value is None:
                        continue
                    # Validate the non-null values; a bad one makes the row malformed.
                    if name == "volume":
                        _to_volume(value)
                    else:
                        _to_price(value)
                if start <= session_date <= end:
                    gaps.append(RawNullGapRow(ts, session_date, null_fields))
                continue
            bar = _parse_chart_row(ts, opens, highs, lows, closes, volumes, idx)
        except (
            KeyError,
            TypeError,
            ValueError,
            InvalidOperation,
            IndexError,
            OverflowError,
            OSError,
        ) as exc:
            raise _MalformedRowError(f"row #{idx}: {exc}") from exc
        if bar is None:  # unreachable: no null field and a non-None timestamp
            raise _MalformedRowError(f"row #{idx}: unparseable")
        if start <= bar.session_date <= end:
            bars.append(bar)
    return bars, gaps


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
                    f"「{symbol}」不是合法的美股個股代號格式；指數請改用 get_index_daily_bars。"
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

    def get_index_daily_bars(self, index_symbol: str, start: date, end: date) -> ProviderResult:
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

    def fetch_chart_closes(
        self, request_symbol: str, start: date, end: date
    ) -> tuple[list[PriceBar], str | None]:
        """Public, symbol-agnostic entry point onto this adapter's chart parsing.

        Neither :meth:`get_daily_bars` (validates via ``canonical_us_symbol``,
        which rejects a symbol shape like ``"TWD=X"``) nor
        :meth:`get_index_daily_bars` (restricted to :data:`INDEX_SYMBOL_METADATA`)
        fits a caller that needs Yahoo's *FX cross-pair* symbol shape -- see
        :class:`app.data.providers.fx_yfinance.YFinanceFxAdapter`. This method
        exists so that caller reuses this module's HTTP + JSON parsing instead
        of duplicating it (data-source-integration skill: "adapter 必要條件缺一
        不可" applies once per parser, not once per symbol shape).

        ``request_symbol`` is passed through to the request verbatim -- no
        validation, no canonicalization. The returned bars' ``market``/
        ``currency`` are placeholders (``"TW"``/``"TWD"``) since this method's
        only established caller (the FX ladder) only reads ``date``/``close``;
        it must **not** be used to build a ``ProviderResult`` presented as
        equity or index data (those roles' own validation is what makes
        ``get_daily_bars``/``get_index_daily_bars`` safe to call directly).
        """
        now = datetime.now(UTC)
        return self._fetch(request_symbol, request_symbol, "TW", "TWD", start, end, now)

    def get_index_raw_responses(self, index_symbol: str, start: date, end: date) -> RawChartFetch:
        """Raw chart responses for one index, for the replay snapshot (ADR-0005 I-3 註記).

        Not part of the ``MarketDataProvider`` ABC and never reached through
        ``IndexProviderBridge``. ``index_symbol`` must be a key of
        :data:`INDEX_SYMBOL_METADATA` verbatim; anything else fails with **zero**
        requests. Always exactly one request, for ``[start - 1 day, end + 1
        day]`` (so the request window does not depend on how a timestamp is
        turned into a date); rows are then kept by their derived
        ``session_date`` in ``[start, end]``. The single response carries its
        ``meta.exchangeTimezoneName`` / ``meta.gmtoffset`` untouched, its
        ``received_at``, its bars (raw timestamp, derived ``session_date``,
        OHLCV) and its ``null_gap_rows``. Bars are kept in source order -- no
        sorting, no de-duplication, no interpolation.

        Fail-closed: a transport error, non-200 status, unparseable body,
        ``chart.error``, missing or malformed result block, **any malformed row**
        (see :func:`_classify_raw_rows`), or a response with no in-range bar
        fails the **whole** call -- ``responses`` is empty and ``reason`` says
        why. It never serves a cache or retries on a different symbol. The
        client's own transport-level retry (``RateLimitedClient``) is part of the
        same request and is the only retry.
        """
        now = datetime.now(UTC)
        if index_symbol not in INDEX_SYMBOL_METADATA:
            logger.info(
                "yfinance: raw-response request for %r is outside the supported range %s",
                index_symbol,
                sorted(INDEX_SYMBOL_METADATA),
            )
            return _raw_failure(
                index_symbol,
                now,
                reason=(
                    f"「{index_symbol}」目前不在本工具支援的指數範圍內"
                    f"（僅支援 {', '.join(sorted(INDEX_SYMBOL_METADATA))}），"
                    "本次不以其他指數或代理 ETF 替代。"
                ),
            )
        if end < start:
            return _raw_failure(
                index_symbol, now, reason="取數區間不合法（結束日早於起始日），本次不發出請求。"
            )

        result, error_reason = self._request_chart_result(
            index_symbol, start - timedelta(days=1), end + timedelta(days=1)
        )
        received_at = datetime.now(UTC)
        if error_reason is not None:
            return _raw_failure(index_symbol, now, reason=error_reason)
        columns = _chart_columns(result)
        if columns is None:
            return _raw_failure(
                index_symbol, now, reason="yfinance 回應的結果區塊格式無法解析，暫不可用。"
            )
        try:
            bars, gaps = _classify_raw_rows(columns, start, end)
        except _MalformedRowError as exc:
            logger.warning("yfinance returned a malformed row for %s: %s", index_symbol, exc)
            return _raw_failure(index_symbol, now, reason=_MALFORMED_ROW_REASON)
        if not bars:
            return _raw_failure(
                index_symbol,
                now,
                reason=f"yfinance 查無「{index_symbol}」在指定區間的指數日線資料。",
            )
        # `result` is a dict here: _chart_columns() returned columns for it.
        meta = result.get("meta") if isinstance(result, dict) else None
        meta_dict = meta if isinstance(meta, dict) else {}
        response = RawChartResponse(
            response_seq=1,
            exchange_timezone_name=meta_dict.get("exchangeTimezoneName"),
            gmtoffset=meta_dict.get("gmtoffset"),
            bars=tuple(bars),
            received_at=received_at,
            null_gap_rows=tuple(gaps),
        )
        return RawChartFetch(
            index_symbol=index_symbol,
            as_of=now,
            source=self.source_id,
            responses=(response,),
            reason=None,
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
        result, error_reason = self._request_chart_result(request_symbol, start, end)
        if error_reason is not None:
            return [], error_reason
        bars = self._parse_result(result, bar_symbol, market, currency, start, end, now)
        return bars, None

    def _request_chart_result(
        self, request_symbol: str, start: date, end: date
    ) -> tuple[Any, str | None]:
        """One chart request. Returns ``(first result block, None)`` or ``(None, reason)``."""
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
            return None, "yfinance 連線逾時或發生錯誤，暫不可用。"

        if response.status_code != httpx.codes.OK:
            logger.warning("yfinance returned HTTP %d for %s", response.status_code, request_symbol)
            return None, "yfinance 回應非預期的 HTTP 狀態，暫不可用。"

        try:
            payload = response.json(parse_float=Decimal)
        except ValueError:
            logger.warning("yfinance returned non-JSON body for %s", request_symbol)
            return None, "yfinance 回應格式無法解析，暫不可用。"

        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not isinstance(chart, dict):
            return None, "yfinance 回應缺少預期的 chart 區塊，暫不可用。"

        error = chart.get("error")
        if error:
            description = error.get("description") if isinstance(error, dict) else str(error)
            return None, (
                f"yfinance 回報錯誤：{description}；無法確定是代號不存在、已下市，或暫時無資料。"
            )

        results = chart.get("result")
        if not isinstance(results, list) or not results:
            return None, f"yfinance 對「{request_symbol}」未回傳任何結果區塊。"
        return results[0], None

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
        columns = _chart_columns(result)
        if columns is None:
            return []
        timestamps, opens, highs, lows, closes, volumes = columns

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
        raw_bar = _parse_chart_row(ts, opens, highs, lows, closes, volumes, idx)
        if raw_bar is None:
            return None
        return PriceBar(
            symbol=bar_symbol,
            market=market,
            date=raw_bar.session_date,
            open=raw_bar.open,
            high=raw_bar.high,
            low=raw_bar.low,
            close=raw_bar.close,
            volume=raw_bar.volume,
            currency=currency,
            as_of=now,
            source=self.source_id,
        )
