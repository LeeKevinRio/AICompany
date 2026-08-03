"""Technical + risk signal endpoint for one symbol.

The ``signals`` field is the :func:`app.signals.service.compute_signals` output
verbatim -- no repackaging, no renamed keys -- so the UI reads the same shape
the engine emits and the two cannot drift.

Not having enough data is a **200 with ``status="insufficient_data"``**, not a
500: "the provider chain and the cache had nothing for this symbol" is an answer
about the world, not a server fault, and the reason is stated in ``reason`` and
in ``data``.

Beta needs a second series, so this endpoint also loads the market's benchmark
index (``app/services/index.py``, the same chain the leverage chapter uses --
official index codes only, never a tracking ETF, ADR-0005 決策一). That load is
a *side* input: it degrades to an explained empty result instead of raising, so
a benchmark that could not be fetched costs the reader beta and nothing else --
every other indicator is computed from the symbol's own bars and is unaffected.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.common import EnvelopeBase, data_meta, now_iso
from app.api.deps import get_index_resolver, get_market_resolver
from app.positions.models import Market
from app.services.index import IndexServiceResolver, load_market_benchmark
from app.services.market import MarketDataResolver, load_bars
from app.signals.service import compute_signals

router = APIRouter(prefix="/api/signals", tags=["signals"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
IndexResolverDep = Annotated[IndexServiceResolver, Depends(get_index_resolver)]

#: Calendar days of history requested. Roughly 18 months, comfortably more than
#: the longest indicator window (MA60) plus the risk layer's return sample.
DEFAULT_LOOKBACK_DAYS = 540


class BenchmarkMeta(BaseModel):
    """Provenance of the benchmark series behind ``signals.risk.beta``.

    ``series_symbol`` / ``label`` state which index was *wanted* and are filled
    in even when the fetch failed; ``available`` says whether it was obtained
    and ``reason`` says why not. ``signals.risk.beta.benchmark`` is deliberately
    the narrower field: it is ``null`` unless a series really was used, so
    "there was no benchmark at all" cannot be misread as "there was one, but the
    overlap was too short".
    """

    model_config = ConfigDict(frozen=True)

    series_symbol: str | None
    label: str | None
    available: bool
    status: str
    source: str
    staleness_minutes: int | None
    bar_count: int
    reason: str | None
    #: Standing disclosures about the series (non-official source, unverified
    #: code); shown as-is, not summarised away.
    notes: list[str]


class SignalsResponse(EnvelopeBase):
    """``GET /api/signals/{symbol}``: a ``compute_signals`` output plus provenance."""

    model_config = ConfigDict(frozen=True)

    #: Exactly ``app.signals.service.compute_signals`` output, or ``None``.
    signals: dict[str, Any] | None
    #: ``None`` only when no payload was produced: with no bars of its own to
    #: measure, the endpoint does not spend a fetch on a benchmark either.
    benchmark: BenchmarkMeta | None = None


@router.get("/{symbol}", response_model=SignalsResponse)
def get_signals(
    symbol: str,
    resolver: ResolverDep,
    index_resolver: IndexResolverDep,
    market: Annotated[Market, Query(description="市場別")] = "TW",
    lookback_days: Annotated[int, Query(ge=30, le=2000)] = DEFAULT_LOOKBACK_DAYS,
) -> SignalsResponse:
    end = date.today()
    start = end - timedelta(days=lookback_days)
    loaded = load_bars(resolver, symbol=symbol, market=market, start=start, end=end)
    if not loaded.bars:
        return SignalsResponse(
            symbol=symbol,
            market=market,
            status="insufficient_data",
            reason=loaded.reason,
            signals=None,
            benchmark=None,
            data=data_meta(loaded.meta()),
            as_of=now_iso(),
        )
    benchmark = load_market_benchmark(index_resolver, market=market, start=start, end=end)
    # Bars exist, so the aggregate is produced. Individual indicators still
    # report their own ``insufficient_data`` when their window is not filled --
    # that per-indicator honesty is what the UI renders. The same applies to
    # beta when the benchmark is missing: no series is passed and no label
    # either, so it reports the state instead of naming an index it never used.
    return SignalsResponse(
        symbol=symbol,
        market=market,
        status="ok",
        reason=None,
        signals=compute_signals(
            symbol,
            loaded.bars,
            benchmark_bars=benchmark.bars,
            benchmark_label=benchmark.label if benchmark.available else None,
        ),
        benchmark=BenchmarkMeta.model_validate(benchmark.meta()),
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
