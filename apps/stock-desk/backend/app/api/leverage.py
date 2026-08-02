"""Leveraged-ETF chapter endpoint for one held symbol.

``chapter`` is the :func:`app.leverage.service.build_leverage_chapter` output
verbatim, including its own ``chapter_status``, disclosure and per-block
statuses.

The chapter is computed **for a holding**, because its drag decomposition is
measured from ``opened_at``; a symbol with no position is therefore a 404 rather
than a card about nobody's position.

Index bars come from ``app/services/index.py`` (the single junction between the
pure ``app/leverage`` package and the data layer, ADR-0005 constraint I-1). A
symbol whose mapping row is ``unmapped`` never reaches a data source at all --
the row's own note is the reason -- and a mapped symbol whose series could not
be fetched degrades to the same ``insufficient_data`` the blocks reported
before, with the data layer's reason attached instead of a generic sentence.
No proxy series is ever substituted in either case.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ConfigDict

from app.api.common import EnvelopeBase, PayloadStatus, data_meta, now_iso
from app.api.deps import get_index_resolver, get_market_resolver, get_position_store
from app.leverage.service import build_leverage_chapter
from app.positions.models import Market, Position
from app.positions.store import PositionStore
from app.services.index import IndexServiceResolver, load_index_bars
from app.services.market import MarketDataResolver, load_bars

router = APIRouter(prefix="/api/leverage", tags=["leverage"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
IndexResolverDep = Annotated[IndexServiceResolver, Depends(get_index_resolver)]
StoreDep = Annotated[PositionStore, Depends(get_position_store)]

#: Long enough to cover a multi-year holding's drag decomposition.
DEFAULT_LOOKBACK_DAYS = 1200


class LeverageResponse(EnvelopeBase):
    """``GET /api/leverage/{symbol}``: a ``build_leverage_chapter`` output."""

    model_config = ConfigDict(frozen=True)

    #: Exactly ``app.leverage.service.build_leverage_chapter`` output.
    chapter: dict[str, Any] | None
    position_id: int | None
    #: Whether an underlying-index series was actually obtained for this
    #: symbol. ``False`` covers both "there is no queryable index for it" and
    #: "there is one but it could not be fetched"; the two are told apart by
    #: the note carried in ``chapter["notes"]``.
    index_bars_available: bool


def _pick_position(store: PositionStore, symbol: str, market: Market) -> Position | None:
    """The earliest-opened holding of ``symbol`` in ``market``, or ``None``.

    Earliest-opened is the conservative choice: it yields the longest holding
    window, which is the one whose compounding drag the chapter is about. A
    holding with no stated open date is not truncated at all, so it spans the
    longest window of any and sorts first under the same rule.
    """
    wanted = symbol.strip().upper()
    matches = [
        position
        for position in store.list_all()
        if position.symbol.strip().upper() == wanted and position.market == market
    ]
    if not matches:
        return None
    return min(matches, key=lambda position: (position.opened_at or date.min, position.id))


@router.get("/{symbol}", response_model=LeverageResponse)
def get_leverage_chapter(
    symbol: str,
    resolver: ResolverDep,
    index_resolver: IndexResolverDep,
    store: StoreDep,
    market: Annotated[Market, Query(description="市場別")] = "TW",
) -> LeverageResponse:
    position = _pick_position(store, symbol, market)
    if position is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此標的的持倉；槓桿專章以實際持倉的建倉日為計算基礎",
        )

    end = date.today()
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    loaded = load_bars(resolver, symbol=symbol, market=market, start=start, end=end)
    index_loaded = load_index_bars(index_resolver, etf_symbol=symbol, start=start, end=end)

    chapter = build_leverage_chapter(position, loaded.bars, index_loaded.bars)
    # ``not_applicable`` is a complete answer ("this chapter does not apply"),
    # so it is an ``ok`` payload; only an actually-uncomputable chapter is
    # reported as insufficient data.
    chapter_status = chapter.get("chapter_status")
    payload_status: PayloadStatus = (
        "insufficient_data" if chapter_status == "insufficient_data" else "ok"
    )

    notes = chapter.get("notes")
    index_reason = index_loaded.reason
    # Two things are deliberately *not* said here. Nothing about an index on a
    # chapter that does not apply -- an ordinary stock has no benchmark to
    # decompose against and the absence is not a finding. And nothing twice:
    # when the mapping row settles the matter (``unmapped``) the chapter has
    # already stated that row's note, and the loader returns the same text.
    # What is worth adding is the case the chapter cannot know about -- a
    # queryable series the data layer could not fetch this time.
    if (
        chapter_status != "not_applicable"
        and isinstance(notes, list)
        and index_reason
        and index_reason not in notes
    ):
        notes.append(index_reason)

    reason = chapter.get("reason") or (loaded.reason if not loaded.bars else None)
    if payload_status == "insufficient_data" and not reason:
        # The ETF bars were fine; what is missing is the index series, so its
        # reason is the one that answers the reader's question.
        reason = index_reason
    return LeverageResponse(
        symbol=symbol,
        market=market,
        status=payload_status,
        reason=reason,
        chapter=chapter,
        position_id=position.id,
        index_bars_available=index_loaded.available,
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
