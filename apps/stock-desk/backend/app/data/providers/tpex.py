"""TPEx (Taipei Exchange, 上櫃) daily bar adapter.

Data source: TPEx "個股日成交資訊" query on the legacy ``aftertrading``
endpoint. Like TWSE, one HTTP call returns one calendar month of daily bars
for a single stock.

Endpoint (documented per TPEx's public ``st43_result`` query; queried
against project knowledge on 2026-07-23, NOT re-verified against a live
response in this sandbox because outbound HTTPS to ``www.tpex.org.tw`` is
blocked by the environment's egress policy -- see
``tests/fixtures/README.md``)::

    GET https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php
        ?l=zh-tw&d=<ROC year>/<month>&stkno=<symbol>&o=json

Response shape (JSON)::

    {
      "stat": "ok",
      "date": "...",
      "title": "...",
      "fields": ["日期", "成交股數", "成交金額(元)", "開盤", "最高",
                 "最低", "收盤", "漲跌", "筆數"],
      "aaData": [["113/01/02", "1,234,000", "56,789,000",
                   "45.50", "46.00", "45.10", "45.80", "+0.30", "321"], ...]
    }

Notes mirror the TWSE adapter: ROC dates, comma-separated numbers, "--"
placeholders for no-trade rows (skipped, never fabricated), and
``stat != "ok"`` treated as "no bars this month" rather than a hard failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any, ClassVar

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers._util import (
    ROC_YEAR_OFFSET,
    UnparseableRowError,
    iter_month_starts,
    parse_decimal_cell,
    parse_int_cell,
    parse_roc_date,
)

logger = logging.getLogger(__name__)

TPEX_BASE_URL = "https://www.tpex.org.tw"
ST43_RESULT_PATH = "/web/stock/aftertrading/daily_trading_info/st43_result.php"
CURRENCY = "TWD"


class TpexAdapter(MarketDataProvider):
    """Primary adapter for TPEx-listed (上櫃) stocks."""

    source_id: ClassVar[str] = "tpex"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=TPEX_BASE_URL, min_interval_seconds=0.5
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
                roc_year = month_start.year - ROC_YEAR_OFFSET
                response = self._client.get(
                    ST43_RESULT_PATH,
                    params={
                        "l": "zh-tw",
                        "d": f"{roc_year}/{month_start.month:02d}",
                        "stkno": symbol,
                        "o": "json",
                    },
                )
                if response.status_code != httpx.codes.OK:
                    logger.warning(
                        "TPEx st43_result returned HTTP %d for %s %s",
                        response.status_code,
                        symbol,
                        month_start.isoformat(),
                    )
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    logger.warning(
                        "TPEx st43_result returned non-JSON body for %s %s",
                        symbol,
                        month_start.isoformat(),
                    )
                    continue
                bars.extend(self._parse_month(payload, symbol, start, end, now))
        except httpx.TransportError as exc:
            logger.warning("TPEx st43_result request failed for %s: %s", symbol, exc)
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
        if not isinstance(payload, dict) or payload.get("stat") not in ("ok", "OK"):
            return []
        rows = payload.get("aaData") or []
        parsed: list[PriceBar] = []
        for row in rows:
            try:
                bar = self._parse_row(row, symbol, now)
            except UnparseableRowError as exc:
                logger.debug("skipping unparseable TPEx row for %s: %s", symbol, exc)
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
