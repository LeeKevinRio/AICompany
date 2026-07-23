"""FinMind daily bar adapter (backup source for both TWSE and TPEx symbols).

Data source: FinMind public API v4, ``TaiwanStockPrice`` dataset. Requires
an API token (free tier available) passed as a query parameter -- the token
is read exclusively from the ``FINMIND_API_TOKEN`` environment variable per
the company's credential rule; it is never hardcoded or written to a
fixture.

Endpoint (documented per FinMind's public API reference; queried against
project knowledge on 2026-07-23, NOT re-verified against a live response in
this sandbox because outbound HTTPS to ``api.finmindtrade.com`` is blocked
by the environment's egress policy -- see ``tests/fixtures/README.md``)::

    GET https://api.finmindtrade.com/api/v4/data
        ?dataset=TaiwanStockPrice&data_id=<symbol>
        &start_date=<YYYY-MM-DD>&end_date=<YYYY-MM-DD>&token=<token>

Response shape (JSON)::

    {
      "msg": "success",
      "status": 200,
      "data": [
        {
          "date": "2024-01-02", "stock_id": "2330",
          "Trading_Volume": 41393088, "Trading_money": 24585432000,
          "open": 594.0, "max": 598.0, "min": 590.0, "close": 594.0,
          "spread": 2.0, "Trading_turnover": 12345
        }
      ]
    }

Notes:
  - ``status`` in the response body (not just the HTTP status code) must be
    200 for the payload to be trusted; FinMind returns HTTP 200 with a
    non-200 body ``status`` for some error conditions (e.g. rate limit,
    invalid token).
  - Price fields are decoded with ``parse_float=Decimal`` so we never round
    through a binary float on the way into ``PriceBar``.
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

logger = logging.getLogger(__name__)

FINMIND_BASE_URL = "https://api.finmindtrade.com"
DATA_PATH = "/api/v4/data"
DATASET = "TaiwanStockPrice"
CURRENCY = "TWD"
TOKEN_ENV_VAR = "FINMIND_API_TOKEN"


def _unavailable(now: datetime) -> ProviderResult:
    return ProviderResult(
        bars=[],
        status=DataStatus.UNAVAILABLE,
        as_of=now,
        source=FinMindAdapter.source_id,
        staleness_minutes=None,
    )


class FinMindAdapter(MarketDataProvider):
    """Backup adapter used when TWSE/TPEx are both unavailable."""

    source_id: ClassVar[str] = "finmind"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=FINMIND_BASE_URL, min_interval_seconds=0.3
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        now = datetime.now(UTC)
        token = os.environ.get(TOKEN_ENV_VAR)
        if not token:
            logger.warning(
                "FinMind adapter unavailable: %s environment variable is not set", TOKEN_ENV_VAR
            )
            return _unavailable(now)

        try:
            response = self._client.get(
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
            logger.warning("FinMind request failed for %s: %s", symbol, exc)
            return _unavailable(now)

        if response.status_code != httpx.codes.OK:
            logger.warning("FinMind returned HTTP %d for %s", response.status_code, symbol)
            return _unavailable(now)

        try:
            payload = response.json(parse_float=Decimal)
        except ValueError:
            logger.warning("FinMind returned non-JSON body for %s", symbol)
            return _unavailable(now)

        bars = self._parse_payload(payload, symbol, now)
        if not bars:
            return _unavailable(now)
        bars.sort(key=lambda bar: bar.date)
        return ProviderResult(
            bars=bars,
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
        )

    def _parse_payload(self, payload: Any, symbol: str, now: datetime) -> list[PriceBar]:
        if not isinstance(payload, dict) or payload.get("status") != 200:
            logger.warning(
                "FinMind response body status not OK for %s: %r",
                symbol,
                payload.get("status") if isinstance(payload, dict) else payload,
            )
            return []
        rows = payload.get("data") or []
        bars: list[PriceBar] = []
        for row in rows:
            try:
                bars.append(self._parse_row(row, symbol, now))
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                logger.debug("skipping unparseable FinMind row for %s: %s", symbol, exc)
                continue
        return bars

    def _parse_row(self, row: dict[str, Any], symbol: str, now: datetime) -> PriceBar:
        return PriceBar(
            symbol=symbol,
            market="TW",
            date=date.fromisoformat(str(row["date"])),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["max"])),
            low=Decimal(str(row["min"])),
            close=Decimal(str(row["close"])),
            volume=int(row["Trading_Volume"]),
            currency=CURRENCY,
            as_of=now,
            source=self.source_id,
        )
