"""Read, write and clear the Kelly input behind risk cap 5 (ADR-0006 D-8).

This router is the manual half of the surface: the pair a user types in
themselves. The import half (``POST .../import-backtest``, which re-runs a
backtest server-side and stores what *it* computed) is a separate change and is
deliberately absent here rather than stubbed -- a route that accepted p/b as a
request body would let the backtest badge be attached to numbers the server
never verified.

Three rules the endpoints below implement:

* out-of-range numbers are **refused, not clamped** (約束 6). ``win_rate``
  outside (0, 1) or a non-positive ``payoff_ratio`` is a 422 that states the
  bound and says the value was not adjusted, and the stored input keeps
  standing -- the same stance the settings router takes on the reported net
  worth.
* the write stamp is the server's. :class:`KellyManualInput` carries no
  timestamp at all, so an input cannot be backdated into looking fresh.
* editing an imported pair by hand does not erase the import. The row's source
  becomes ``backtest_overridden`` and the imported numbers stay beside the new
  ones (約束 4), so "the user changed this" remains visible.

``DELETE`` removes the input row and **nothing else**: the import-attempt log
is a different table in a different store and is not touched (約束 35).
Clearing an input the user no longer trusts must not also erase how many
imports they tried before keeping one.

Freshness is stated, not acted on: this router reports ``age_days`` and which
band the input falls in (fresh / ageing / expired, D-4). Whether cap 5 still
computes from an expired input is the risk layer's decision, taken from the
same constants, so the two cannot drift into disagreeing about the same row.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from app.api.common import now_iso
from app.api.deps import get_kelly_input_store
from app.kelly.models import (
    KellyFreshness,
    KellyInputRecord,
    KellyInputRow,
    KellyManualInput,
    age_in_days,
    anchor_moment,
    freshness_of,
    normalize_symbol,
)
from app.kelly.store import KellyInputStore
from app.positions.models import Market

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kelly-inputs", tags=["kelly"])

KellyStoreDep = Annotated[KellyInputStore, Depends(get_kelly_input_store)]
MarketQuery = Annotated[Market, Query(description="市場別")]

KELLY_INPUT_NOT_FOUND_MESSAGE = "找不到 {symbol}（{market}）的 Kelly 輸入。"


class KellyInputView(BaseModel):
    """One stored Kelly input plus the freshness facts about it.

    ``anchored_at`` is spelled out rather than left implicit because it differs
    by source: a manual input ages from when it was typed, an imported one from
    the end of the segment it was measured over (D-4). A reader who could not
    see which of the two ``age_days`` counts from would be unable to check it.
    """

    model_config = ConfigDict(frozen=True)

    item: KellyInputRow
    anchored_at: str
    age_days: int
    freshness: KellyFreshness
    as_of: str


def _view(row: KellyInputRow) -> KellyInputView:
    anchor = anchor_moment(row)
    age = age_in_days(anchor)
    return KellyInputView(
        item=row,
        anchored_at=anchor.isoformat(),
        age_days=age,
        freshness=freshness_of(age),
        as_of=now_iso(),
    )


def _not_found(symbol: str, market: Market) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=KELLY_INPUT_NOT_FOUND_MESSAGE.format(symbol=symbol, market=market),
    )


@router.get("/{symbol}", response_model=KellyInputView)
def read_kelly_input(
    symbol: str, store: KellyStoreDep, market: MarketQuery = "TW"
) -> KellyInputView:
    """The input in force for one instrument, with its age.

    An expired input is returned like any other, carrying ``freshness:
    expired``. Withholding it would make "entered a long time ago" look like
    "never entered", and those two states are not the same thing to a user who
    has to decide what to do next.
    """
    row = store.get(symbol, market)
    if row is None:
        raise _not_found(normalize_symbol(symbol), market)
    return _view(row)


@router.put("/{symbol}", response_model=KellyInputView)
def write_kelly_input(
    symbol: str, body: KellyManualInput, store: KellyStoreDep, market: MarketQuery = "TW"
) -> KellyInputView:
    """Store a hand-entered pair for one instrument.

    A first write creates a ``manual`` row with no provenance -- there is none,
    and a fabricated ``strategy_id`` would make a typed number look measured.
    A write over an imported row keeps everything the import established and
    only moves the effective pair, marking the row ``backtest_overridden``.

    Range violations never reach this function: they are refused by
    :class:`KellyManualInput` as a 422 naming the field and its bound, and
    nothing is written, so the previously stored pair still stands.
    """
    current = store.get(symbol, market)
    if current is None or current.source == "manual":
        record = KellyInputRecord.manual(
            symbol=symbol,
            market=market,
            win_rate=body.win_rate,
            payoff_ratio=body.payoff_ratio,
        )
    else:
        record = KellyInputRecord.overriding(
            current, win_rate=body.win_rate, payoff_ratio=body.payoff_ratio
        )
    saved = store.upsert(record)
    # No history table (D-2), but the change does leave a trace.
    logger.info(
        "kelly input written: symbol=%s market=%s source=%s win_rate=%.4f "
        "payoff_ratio=%.4f previous_source=%s",
        saved.symbol,
        saved.market,
        saved.source,
        saved.win_rate,
        saved.payoff_ratio,
        None if current is None else current.source,
    )
    return _view(saved)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kelly_input(
    symbol: str, store: KellyStoreDep, market: MarketQuery = "TW"
) -> Response:
    """Remove the input in force for one instrument.

    Only the input row. The import-attempt log keeps every row it had, so
    ``K_observed`` is unchanged by this call (約束 35).
    """
    if not store.delete(symbol, market):
        raise _not_found(normalize_symbol(symbol), market)
    logger.info(
        "kelly input deleted: symbol=%s market=%s", normalize_symbol(symbol), market
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
