"""TPEx (Taipei Exchange, 上櫃) daily bar adapter.

Data source: TPEx "個股日成交資訊" query, **new site** (``www.tpex.org.tw/www/...``).
One HTTP call returns one calendar month of daily bars for a single stock, same
as before.

VERIFICATION STATUS: **NOT verified against a live response in this sandbox**
-- outbound HTTPS to ``www.tpex.org.tw`` is blocked by this environment's
egress policy (``CONNECT`` returns 403). This rewrite targets the endpoint
below per its publicly documented shape and community write-ups (queried
against project knowledge on 2026-09-19), because the legacy endpoint this
adapter used until 2026-09-19 (``/web/stock/aftertrading/daily_trading_info/
st43_result.php``) was retired in TPEx's 2024 site migration and now returns
404 / redirects to the homepage -- see
``work/stock-desk-一眼一句簡化-派工單.md`` §1.2 for the incident that surfaced
this. **CEO must run the real-endpoint check before this is trusted**::

    cd apps/stock-desk/backend
    uv run python ../scripts/verify_market_data.py --tpex-symbol 6147

(the CLI flag is ``--tpex-symbol``, not ``--symbol``/``--market`` -- see that
script's own module docstring for the full flag set). Until that check comes
back PASS for at least one 上櫃 symbol, treat this adapter's bars the same as
any other unverified source: do not cite it as confirmed-correct in a report.

Endpoint (documented per TPEx's public "個股日成交資訊" query on the current
site; NOT re-verified against a live response in this sandbox, see above)::

    GET https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock
        ?code=<symbol>&date=<YYYY>/<MM>/01&id=&response=json

Response shape (JSON)::

    {
      "stat": "ok",
      "date": "20260901",
      "tables": [
        {
          "title": "...",
          "date": "20260901",
          "fields": ["日期", "成交仟股", "成交仟元", "開盤", "最高",
                     "最低", "收盤", "漲跌", "筆數"],
          "data": [["115/09/01", "1,234", "56,789", "45.50", "46.00",
                     "45.10", "45.80", "+0.30", "321"], ...],
          "totalCount": 1,
          "notes": [...]
        }
      ]
    }

Notes:
  - ROC dates, comma-separated numbers and "--" no-trade placeholders are
    parsed the same way as the TWSE adapter (``app/data/providers/_util.py``).
  - The new site's volume column has been observed labelled both "成交股數"
    (already in shares) and "成交仟股" (in thousands of shares, i.e. needs
    ``* 1000``). This adapter never hardcodes which one is in effect: it reads
    ``tables[0]["fields"]`` and multiplies by 1000 only when that column's own
    header text contains "仟" or "千". A column layout this adapter cannot
    recognise (missing date/volume/OHLC headers) is treated as an unparseable
    month, not guessed at.
  - ``stat != "ok"`` (case-insensitive) is treated as "no bars this month",
    not a hard failure, same as before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, ClassVar

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers._util import (
    UnparseableRowError,
    iter_month_starts,
    parse_decimal_cell,
    parse_int_cell,
    parse_roc_date,
)

logger = logging.getLogger(__name__)

TPEX_BASE_URL = "https://www.tpex.org.tw"
TRADING_STOCK_PATH = "/www/zh-tw/afterTrading/tradingStock"
CURRENCY = "TWD"

#: Header substrings identifying a required column, in the order this
#: adapter looks for them. Matched by substring (not exact string, not a
#: fixed index) so a header wording change or reordering does not silently
#: mis-map a column -- an unrecognised layout is skipped, never guessed at.
_DATE_HEADER_KEYWORDS = ("日期",)
#: Specific first (the two headers seen so far), then a bare "股" fallback for
#: a wording change; see ``_find_column`` for why a header matched by more
#: than one column is refused rather than resolved to the first hit.
_VOLUME_HEADER_KEYWORDS = ("成交股數", "成交仟股", "成交千股", "股")
_OPEN_HEADER_KEYWORDS = ("開盤",)
_HIGH_HEADER_KEYWORDS = ("最高",)
_LOW_HEADER_KEYWORDS = ("最低",)
_CLOSE_HEADER_KEYWORDS = ("收盤",)
#: Either of these appearing in the volume column's own header means the
#: figure is reported in thousands and must be multiplied by 1000.
_THOUSANDS_MARKERS = ("仟", "千")


@dataclass(frozen=True)
class _ColumnMap:
    """Which ``fields``/``data`` column index holds each value, resolved once per table."""

    date: int
    volume: int
    volume_in_thousands: bool
    open: int
    high: int
    low: int
    close: int


class UnrecognisedLayoutError(UnparseableRowError):
    """The month's ``fields`` header could not be mapped to the columns this adapter needs.

    Distinct from a row that fails to parse: a layout this adapter cannot read
    is a *skipped month* under ADR-0009 (the range is not recorded as covered),
    whereas ``stat != "ok"`` is the source stating there were no trades.
    """


def _find_column(fields: list[Any], keywords: tuple[str, ...]) -> int | None:
    """Return the one column whose header matches ``keywords``.

    Keywords are tried in order so a specific header wins over a bare
    fallback. A keyword that matches more than one header is refused
    (``UnrecognisedLayoutError``) instead of resolved to the first hit -- a
    silent mis-map to a neighbouring column is exactly the failure mode the
    header-driven lookup exists to prevent (qa-reviewer 2026-09-19).
    """
    for keyword in keywords:
        hits = [
            idx
            for idx, header in enumerate(fields)
            if isinstance(header, str) and keyword in header
        ]
        if len(hits) > 1:
            raise UnrecognisedLayoutError(
                f"header {keyword!r} matches columns {hits} in {fields!r}"
            )
        if hits:
            return hits[0]
    return None


def _resolve_columns(fields: list[Any]) -> _ColumnMap:
    """Map ``fields`` header text to column indices, or raise if the shape is unrecognised."""
    required = {
        "日期": _find_column(fields, _DATE_HEADER_KEYWORDS),
        "成交量": _find_column(fields, _VOLUME_HEADER_KEYWORDS),
        "開盤": _find_column(fields, _OPEN_HEADER_KEYWORDS),
        "最高": _find_column(fields, _HIGH_HEADER_KEYWORDS),
        "最低": _find_column(fields, _LOW_HEADER_KEYWORDS),
        "收盤": _find_column(fields, _CLOSE_HEADER_KEYWORDS),
    }
    missing = [label for label, idx in required.items() if idx is None]
    if missing:
        raise UnrecognisedLayoutError(f"unrecognised TPEx fields {fields!r}: missing {missing}")
    volume_idx = required["成交量"]
    assert volume_idx is not None  # narrowed by the missing-check above
    volume_header = fields[volume_idx]
    volume_in_thousands = isinstance(volume_header, str) and any(
        marker in volume_header for marker in _THOUSANDS_MARKERS
    )
    return _ColumnMap(
        date=required["日期"],  # type: ignore[arg-type]
        volume=volume_idx,
        volume_in_thousands=volume_in_thousands,
        open=required["開盤"],  # type: ignore[arg-type]
        high=required["最高"],  # type: ignore[arg-type]
        low=required["最低"],  # type: ignore[arg-type]
        close=required["收盤"],  # type: ignore[arg-type]
    )


class TpexAdapter(MarketDataProvider):
    """Primary adapter for TPEx-listed (上櫃) stocks."""

    source_id: ClassVar[str] = "tpex"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(base_url=TPEX_BASE_URL, min_interval_seconds=0.5)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        now = datetime.now(UTC)
        bars: list[PriceBar] = []
        # ADR-0009: a skipped month makes the answer partial; the service then
        # caches what came back but does not record the range as covered.
        skipped_months = 0
        try:
            for month_start in iter_month_starts(start, end):
                response = self._client.get(
                    TRADING_STOCK_PATH,
                    params={
                        "code": symbol,
                        "date": f"{month_start.year}/{month_start.month:02d}/01",
                        "id": "",
                        "response": "json",
                    },
                )
                if response.status_code != httpx.codes.OK:
                    logger.warning(
                        "TPEx tradingStock returned HTTP %d for %s %s",
                        response.status_code,
                        symbol,
                        month_start.isoformat(),
                    )
                    skipped_months += 1
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    logger.warning(
                        "TPEx tradingStock returned non-JSON body for %s %s",
                        symbol,
                        month_start.isoformat(),
                    )
                    skipped_months += 1
                    continue
                try:
                    bars.extend(self._parse_month(payload, symbol, start, end, now))
                except UnrecognisedLayoutError as exc:
                    # A layout this adapter cannot read is a skipped month, not
                    # "no trades": the range must not be recorded as covered.
                    logger.warning(
                        "TPEx tradingStock column layout unrecognised for %s %s: %s",
                        symbol,
                        month_start.isoformat(),
                        exc,
                    )
                    skipped_months += 1
        except httpx.TransportError as exc:
            logger.warning("TPEx tradingStock request failed for %s: %s", symbol, exc)
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
            )

        if not bars:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
            )
        bars.sort(key=lambda bar: bar.date)
        return ProviderResult(
            bars=bars,
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
            complete=skipped_months == 0,
        )

    def _parse_month(
        self, payload: Any, symbol: str, start: date, end: date, now: datetime
    ) -> list[PriceBar]:
        if not isinstance(payload, dict) or str(payload.get("stat", "")).lower() != "ok":
            return []
        # ``stat == "ok"`` without a readable table is a schema drift, not "no
        # trades": count it as a skipped month (qa-reviewer 2026-09-19).
        tables = payload.get("tables")
        if not isinstance(tables, list) or not tables:
            raise UnrecognisedLayoutError(f"stat ok but no tables list for {symbol}")
        table = tables[0]
        if not isinstance(table, dict):
            raise UnrecognisedLayoutError(f"tables[0] is not an object for {symbol}")
        fields = table.get("fields")
        rows = table.get("data")
        if not isinstance(fields, list) or not isinstance(rows, list):
            raise UnrecognisedLayoutError(f"table without fields/data lists for {symbol}")
        columns = _resolve_columns(fields)  # raises UnrecognisedLayoutError; caller counts it
        parsed: list[PriceBar] = []
        for row in rows:
            try:
                bar = self._parse_row(row, columns, symbol, now)
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable TPEx row for %s: %s", symbol, exc)
                continue
            if start <= bar.date <= end:
                parsed.append(bar)
        return parsed

    def _parse_row(self, row: Any, columns: _ColumnMap, symbol: str, now: datetime) -> PriceBar:
        if not isinstance(row, list) or len(row) <= max(
            columns.date, columns.volume, columns.open, columns.high, columns.low, columns.close
        ):
            raise UnparseableRowError(f"row too short: {row!r}")
        trade_date = parse_roc_date(row[columns.date])
        volume = parse_int_cell(row[columns.volume])
        if columns.volume_in_thousands:
            volume *= 1000
        open_price = parse_decimal_cell(row[columns.open])
        high_price = parse_decimal_cell(row[columns.high])
        low_price = parse_decimal_cell(row[columns.low])
        close_price = parse_decimal_cell(row[columns.close])
        return PriceBar(
            symbol=symbol,
            market="TW",
            date=trade_date,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            currency=CURRENCY,
            as_of=now,
            source=self.source_id,
        )
