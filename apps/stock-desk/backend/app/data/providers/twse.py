"""TWSE (Taiwan Stock Exchange, 上市) daily bar adapter.

Data source: TWSE "個股日成交資訊" (STOCK_DAY) query. One HTTP call returns
one calendar month of daily bars for a single stock, so a multi-month date
range is fetched with one request per month.

Endpoint (documented per TWSE's public exchangeReport API; queried against
project knowledge on 2026-07-23, NOT re-verified against a live response in
this sandbox because outbound HTTPS to ``www.twse.com.tw`` is blocked by the
environment's egress policy -- see ``tests/fixtures/README.md``)::

    GET https://www.twse.com.tw/exchangeReport/STOCK_DAY
        ?response=json&date=YYYYMMDD&stockNo=<symbol>

Response shape (JSON)::

    {
      "stat": "OK",
      "date": "YYYYMMDD",
      "title": "...",
      "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價",
                 "最低價", "收盤價", "漲跌價差", "成交筆數"],
      "data": [["113/01/02", "41,393,088", "24,585,432,000",
                 "594.00", "598.00", "590.00", "594.00", "+2.00", "12,345"], ...]
    }

Notes:
  - The date column is on the ROC (Minguo) calendar: "113/01/02" ==
    2024-01-02 (year + 1911).
  - Numeric columns use thousands separators, and rows for days with no
    trades use "--" placeholders; such rows are skipped (never fabricated)
    -- they surface as gaps for ``app.data.quality`` to flag if a caller
    supplies a trading calendar.
  - ``stat != "OK"`` (e.g. no data for that month/symbol) is treated as "no
    bars this month", not a hard failure.
"""

from __future__ import annotations

import logging
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

TWSE_BASE_URL = "https://www.twse.com.tw"
STOCK_DAY_PATH = "/exchangeReport/STOCK_DAY"
CURRENCY = "TWD"


class TwseAdapter(MarketDataProvider):
    """Primary adapter for TWSE-listed (上市) stocks."""

    source_id: ClassVar[str] = "twse"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TWSE_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        now = datetime.now(UTC)
        bars: list[PriceBar] = []
        try:
            for month_start in iter_month_starts(start, end):
                response = self._client.get(
                    STOCK_DAY_PATH,
                    params={
                        "response": "json",
                        "date": month_start.strftime("%Y%m%d"),
                        "stockNo": symbol,
                    },
                )
                if response.status_code != httpx.codes.OK:
                    logger.warning(
                        "TWSE STOCK_DAY returned HTTP %d for %s %s",
                        response.status_code,
                        symbol,
                        month_start.isoformat(),
                    )
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    logger.warning(
                        "TWSE STOCK_DAY returned non-JSON body for %s %s",
                        symbol,
                        month_start.isoformat(),
                    )
                    continue
                bars.extend(self._parse_month(payload, symbol, start, end, now))
        except httpx.TransportError as exc:
            logger.warning("TWSE STOCK_DAY request failed for %s: %s", symbol, exc)
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
        )

    def _parse_month(
        self, payload: Any, symbol: str, start: date, end: date, now: datetime
    ) -> list[PriceBar]:
        if not isinstance(payload, dict) or payload.get("stat") != "OK":
            return []
        rows = payload.get("data") or []
        parsed: list[PriceBar] = []
        for row in rows:
            try:
                bar = self._parse_row(row, symbol, now)
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable TWSE row for %s: %s", symbol, exc)
                continue
            if start <= bar.date <= end:
                parsed.append(bar)
        return parsed

    def _parse_row(self, row: list[str], symbol: str, now: datetime) -> PriceBar:
        if len(row) < 7:
            raise UnparseableRowError(f"row too short: {row!r}")
        trade_date = parse_roc_date(row[0])
        volume = parse_int_cell(row[1])
        open_price = parse_decimal_cell(row[3])
        high_price = parse_decimal_cell(row[4])
        low_price = parse_decimal_cell(row[5])
        close_price = parse_decimal_cell(row[6])
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
