"""Raw daily OHLCV endpoint: the price series a candlestick chart is drawn from.

Every other symbol-scoped endpoint returns *derived* numbers; this one returns
the bars themselves, so the UI can draw a K-line chart and overlay the
indicators from ``/api/signals`` on the same x-axis. It goes through the same
loader as ``/api/signals`` (``MarketDataService`` -> the degradation ladder), and
defaults to the **same lookback window**, so the two responses cover the same
range and the overlay lines up bar-for-bar rather than drifting.

Money fields are ``Decimal`` and therefore serialize as JSON **strings**, per
the project-wide convention (``app/positions``, ``app/portfolio``): prices never
cross the wire as floats. ``volume`` stays an integer.

Not having data is a 200 with ``status="insufficient_data"`` and an empty
``bars`` list -- never a fabricated or interpolated series.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.common import EnvelopeBase, data_meta, now_iso
from app.api.deps import get_market_resolver
from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.interface import PriceBar
from app.positions.models import Market
from app.services.market import MarketDataResolver, load_bars

router = APIRouter(prefix="/api/bars", tags=["bars"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]


class Bar(BaseModel):
    """One daily OHLCV bar as the chart consumes it.

    A narrower projection of :class:`app.data.interface.PriceBar`: ``symbol``
    and ``market`` are dropped because the envelope already carries them, and
    ``as_of`` is dropped because the ``data`` block reports provenance for the
    whole series.
    """

    model_config = ConfigDict(frozen=True)

    date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    currency: str
    source: str


class BarsResponse(EnvelopeBase):
    """``GET /api/bars/{symbol}``: the raw series plus its provenance."""

    model_config = ConfigDict(frozen=True)

    #: Ascending by date. Empty when ``status`` is ``insufficient_data``.
    bars: list[Bar]


def _to_bar(bar: PriceBar) -> Bar:
    return Bar(
        date=bar.date.isoformat(),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        currency=bar.currency,
        source=bar.source,
    )


@router.get("/{symbol}", response_model=BarsResponse)
def get_bars(
    symbol: str,
    resolver: ResolverDep,
    market: Annotated[Market, Query(description="市場別")] = "TW",
    lookback_days: Annotated[int, Query(ge=1, le=2000)] = DEFAULT_LOOKBACK_DAYS,
) -> BarsResponse:
    end = date.today()
    loaded = load_bars(
        resolver,
        symbol=symbol,
        market=market,
        start=end - timedelta(days=lookback_days),
        end=end,
    )
    ordered = sorted(loaded.bars, key=lambda bar: bar.date)
    return BarsResponse(
        symbol=symbol,
        market=market,
        status="ok" if ordered else "insufficient_data",
        reason=loaded.reason,
        bars=[_to_bar(bar) for bar in ordered],
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
