"""Technical + risk signal endpoint for one symbol.

The ``signals`` field is the :func:`app.signals.service.compute_signals` output
verbatim -- no repackaging, no renamed keys -- so the UI reads the same shape
the engine emits and the two cannot drift.

Not having enough data is a **200 with ``status="insufficient_data"``**, not a
500: "the provider chain and the cache had nothing for this symbol" is an answer
about the world, not a server fault, and the reason is stated in ``reason`` and
in ``data``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import ConfigDict

from app.api.common import EnvelopeBase, data_meta, now_iso
from app.api.deps import get_market_resolver
from app.positions.models import Market
from app.services.market import MarketDataResolver, load_bars
from app.signals.service import compute_signals

router = APIRouter(prefix="/api/signals", tags=["signals"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]

#: Calendar days of history requested. Roughly 18 months, comfortably more than
#: the longest indicator window (MA60) plus the risk layer's return sample.
DEFAULT_LOOKBACK_DAYS = 540


class SignalsResponse(EnvelopeBase):
    """``GET /api/signals/{symbol}``: a ``compute_signals`` output plus provenance."""

    model_config = ConfigDict(frozen=True)

    #: Exactly ``app.signals.service.compute_signals`` output, or ``None``.
    signals: dict[str, Any] | None


@router.get("/{symbol}", response_model=SignalsResponse)
def get_signals(
    symbol: str,
    resolver: ResolverDep,
    market: Annotated[Market, Query(description="市場別")] = "TW",
    lookback_days: Annotated[int, Query(ge=30, le=2000)] = DEFAULT_LOOKBACK_DAYS,
) -> SignalsResponse:
    end = date.today()
    loaded = load_bars(
        resolver,
        symbol=symbol,
        market=market,
        start=end - timedelta(days=lookback_days),
        end=end,
    )
    if not loaded.bars:
        return SignalsResponse(
            symbol=symbol,
            market=market,
            status="insufficient_data",
            reason=loaded.reason,
            signals=None,
            data=data_meta(loaded.meta()),
            as_of=now_iso(),
        )
    # Bars exist, so the aggregate is produced. Individual indicators still
    # report their own ``insufficient_data`` when their window is not filled --
    # that per-indicator honesty is what the UI renders.
    return SignalsResponse(
        symbol=symbol,
        market=market,
        status="ok",
        reason=None,
        signals=compute_signals(symbol, loaded.bars),
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
