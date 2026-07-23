"""USD/TWD daily FX rate adapter.

Data source: Bank of Taiwan (台灣銀行) public exchange-rate CSV export, one
file per calendar day.

Endpoint (documented per Bank of Taiwan's public historical-rate CSV export,
widely referenced pattern; queried against project knowledge on 2026-07-23,
NOT re-verified against a live response in this sandbox because outbound
HTTPS to ``rate.bot.com.tw`` is blocked by the environment's egress policy
-- see ``tests/fixtures/README.md``)::

    GET https://rate.bot.com.tw/xrt/flcsv/0/<YYYY-MM-DD>

Response: UTF-8 CSV, one row per currency for that date. The header row
labels each rate category (cash / spot / forward) once per buy+sell pair,
in that order (buy column first, then sell column), and the currency code
appears in the first data-row column (e.g. ``USD``).

Because Bank of Taiwan does not publish a single official "daily close" for
FX, this adapter reports the mid-point of the spot ("即期") buy and sell
rates as the day's rate. Header matching is done by locating the "即期"
label rather than a hardcoded column index, so a header column reordering
degrades to a clear "unavailable" instead of silently reading the wrong
column -- but a genuine schema change could still require an update here;
this is flagged as unverified in ``tests/fixtures/README.md``.

Only the single-day CSV endpoint exists for this feed, so a date range is
fetched with one HTTP call per calendar day; days with no published rate
(weekends, holidays) are simply absent from the result, never fabricated.
"""

from __future__ import annotations

import csv
import io
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus

logger = logging.getLogger(__name__)

BOT_BASE_URL = "https://rate.bot.com.tw"
FLCSV_PATH_TEMPLATE = "/xrt/flcsv/0/{date}"
SPOT_LABEL = "即期"


class FxRate(BaseModel):
    """One daily USD/TWD (or other pair) rate, self-describing like PriceBar."""

    model_config = ConfigDict(frozen=True)

    pair: str
    date: date_type
    rate: Decimal
    as_of: datetime
    source: str

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value


class FxRateResult(BaseModel):
    """Envelope returned by every ``FxRateProvider.get_daily_rates`` call."""

    model_config = ConfigDict(frozen=True)

    rates: list[FxRate]
    status: DataStatus
    as_of: datetime
    source: str
    staleness_minutes: int | None = None


class FxRateProvider(ABC):
    """Abstract adapter for a daily FX rate source, mirroring MarketDataProvider."""

    source_id: ClassVar[str]

    @abstractmethod
    def get_daily_rates(self, pair: str, start: date_type, end: date_type) -> FxRateResult:
        """Return daily rates for ``pair`` (e.g. ``"USDTWD"``) within [start, end]."""
        raise NotImplementedError


def _iter_dates(start: date_type, end: date_type) -> list[date_type]:
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


class BankOfTaiwanFxAdapter(FxRateProvider):
    """Primary FX adapter: Bank of Taiwan daily spot-rate CSV export."""

    source_id: ClassVar[str] = "bank_of_taiwan"

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            base_url=BOT_BASE_URL, min_interval_seconds=0.5
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_daily_rates(self, pair: str, start: date_type, end: date_type) -> FxRateResult:
        now = datetime.now(UTC)
        currency_code = pair[:3].upper()
        rates: list[FxRate] = []
        try:
            for day in _iter_dates(start, end):
                rate = self._fetch_one_day(pair, currency_code, day, now)
                if rate is not None:
                    rates.append(rate)
        except httpx.TransportError as exc:
            logger.warning("Bank of Taiwan FX request failed for %s: %s", pair, exc)
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
            )

        if not rates:
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source=self.source_id,
                staleness_minutes=None,
            )
        return FxRateResult(
            rates=rates,
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
        )

    def _fetch_one_day(
        self, pair: str, currency_code: str, day: date_type, now: datetime
    ) -> FxRate | None:
        response = self._client.get(FLCSV_PATH_TEMPLATE.format(date=day.isoformat()))
        if response.status_code != httpx.codes.OK:
            logger.debug(
                "Bank of Taiwan FX: HTTP %d for %s on %s",
                response.status_code,
                pair,
                day.isoformat(),
            )
            return None
        return self._parse_csv(response.text, pair, currency_code, day, now)

    def _parse_csv(
        self, body: str, pair: str, currency_code: str, day: date_type, now: datetime
    ) -> FxRate | None:
        reader = csv.reader(io.StringIO(body))
        rows = list(reader)
        if not rows:
            logger.debug("Bank of Taiwan FX: empty CSV for %s on %s", pair, day.isoformat())
            return None

        header = rows[0]
        spot_indices = [idx for idx, cell in enumerate(header) if SPOT_LABEL in cell]
        if len(spot_indices) < 2:
            logger.warning(
                "Bank of Taiwan FX: could not locate spot-rate columns for %s on %s "
                "(header=%r) -- schema may have changed",
                pair,
                day.isoformat(),
                header,
            )
            return None
        buy_idx, sell_idx = spot_indices[0], spot_indices[1]

        for row in rows[1:]:
            if not row or not row[0].strip().upper().startswith(currency_code):
                continue
            if len(row) <= max(buy_idx, sell_idx):
                continue
            try:
                buy = Decimal(row[buy_idx].strip())
                sell = Decimal(row[sell_idx].strip())
            except InvalidOperation:
                logger.debug(
                    "Bank of Taiwan FX: unparseable rate cells for %s on %s: %r",
                    pair,
                    day.isoformat(),
                    row,
                )
                return None
            mid_rate = (buy + sell) / Decimal(2)
            return FxRate(
                pair=pair,
                date=day,
                rate=mid_rate,
                as_of=now,
                source=self.source_id,
            )
        logger.debug(
            "Bank of Taiwan FX: currency %s row not found for %s", currency_code, day.isoformat()
        )
        return None
