"""Leveraged-ETF chapter endpoint for one held symbol.

``chapter`` is the :func:`app.leverage.service.build_leverage_chapter` output
verbatim, including its own ``chapter_status``, disclosure and per-block
statuses.

The chapter is computed **for a holding**, because its drag decomposition is
measured from ``opened_at``; a symbol with no position is therefore a 404 rather
than a card about nobody's position.

Index bars: there is still no data adapter for an underlying index, so
``index_bars`` is passed as ``None`` and the drag/erosion blocks honestly report
``insufficient_data``. The code path is exercised end to end -- when an index
adapter arrives, only the loader below changes.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ConfigDict

from app.api.common import EnvelopeBase, PayloadStatus, data_meta, now_iso
from app.api.deps import get_market_resolver, get_position_store
from app.leverage.service import build_leverage_chapter
from app.positions.models import Market, Position
from app.positions.store import PositionStore
from app.services.market import MarketDataResolver, load_bars

router = APIRouter(prefix="/api/leverage", tags=["leverage"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
StoreDep = Annotated[PositionStore, Depends(get_position_store)]

#: Long enough to cover a multi-year holding's drag decomposition.
DEFAULT_LOOKBACK_DAYS = 1200

#: Why the two quantitative blocks are not computed today.
NO_INDEX_ADAPTER_NOTE = (
    "目前沒有標的指數的日線資料來源，拆解與情境推估皆不計算；本模組不會以其他標的替代。"
)


class LeverageResponse(EnvelopeBase):
    """``GET /api/leverage/{symbol}``: a ``build_leverage_chapter`` output."""

    model_config = ConfigDict(frozen=True)

    #: Exactly ``app.leverage.service.build_leverage_chapter`` output.
    chapter: dict[str, Any] | None
    position_id: int | None
    #: ``False`` until an index data adapter exists (see the module docstring).
    index_bars_available: bool


def _pick_position(store: PositionStore, symbol: str, market: Market) -> Position | None:
    """The earliest-opened holding of ``symbol`` in ``market``, or ``None``.

    Earliest-opened is the conservative choice: it yields the longest holding
    window, which is the one whose compounding drag the chapter is about.
    """
    wanted = symbol.strip().upper()
    matches = [
        position
        for position in store.list_all()
        if position.symbol.strip().upper() == wanted and position.market == market
    ]
    if not matches:
        return None
    return min(matches, key=lambda position: (position.opened_at, position.id))


@router.get("/{symbol}", response_model=LeverageResponse)
def get_leverage_chapter(
    symbol: str,
    resolver: ResolverDep,
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
    loaded = load_bars(
        resolver,
        symbol=symbol,
        market=market,
        start=end - timedelta(days=DEFAULT_LOOKBACK_DAYS),
        end=end,
    )
    # ``index_bars=None``: no adapter yet, so the chapter reports the two
    # index-based blocks as insufficient_data instead of substituting a proxy.
    chapter = build_leverage_chapter(position, loaded.bars, None)
    notes = chapter.get("notes")
    if isinstance(notes, list) and NO_INDEX_ADAPTER_NOTE not in notes:
        notes.append(NO_INDEX_ADAPTER_NOTE)

    # ``not_applicable`` is a complete answer ("this chapter does not apply"),
    # so it is an ``ok`` payload; only an actually-uncomputable chapter is
    # reported as insufficient data.
    chapter_status = chapter.get("chapter_status")
    payload_status: PayloadStatus = (
        "insufficient_data" if chapter_status == "insufficient_data" else "ok"
    )
    return LeverageResponse(
        symbol=symbol,
        market=market,
        status=payload_status,
        reason=chapter.get("reason") or (loaded.reason if not loaded.bars else None),
        chapter=chapter,
        position_id=position.id,
        index_bars_available=False,
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
