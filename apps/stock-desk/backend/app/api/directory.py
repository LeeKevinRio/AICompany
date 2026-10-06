"""Security directory endpoints: 代號 -> 公司名稱 -> 市場 lookup (FR-2/FR-3).

``GET /api/directory/resolve/{symbol}`` backs FR-2's automatic market
determination: a hit means the caller can trust the returned ``market``
without asking the user to pick one; a miss is the honest "not in the
directory" signal FR-2's Q1 fallback (CEO 裁示 (b)：僅在查無時跳出縮小版手動
選市場) is built on. A miss is an expected answer, not a failure, so it comes
back as ``200`` with ``found: false`` (see ``ResolveMiss``) rather than a 404:
every individual position page looks its own symbol up, and a 404 there showed
up as a browser console error on every page whose symbol the directory lacks.
A hit's body is unchanged. Genuine failures (an unreadable directory DB) still
surface as 5xx.

``GET /api/directory/search`` backs FR-3's combobox candidates: symbol-prefix
+ name-substring, merged and capped, with an honest ``directory_synced`` flag
so an empty directory (FR-7) never gets mistaken for "no candidates found".

Both responses also carry the security's TWSE industry category when the
directory has one (CEO 指示 2026-08-16: 持倉的台股產業別應自動判斷,不該手填).
It is a *default* for the position form's existing dropdown, not a decision:
the field stays editable, and a security with no category in the directory
leaves it empty rather than being filed somewhere plausible.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.common import now_iso
from app.api.deps import get_directory_store
from app.directory.models import DirectoryEntry
from app.directory.store import SecurityDirectoryStore
from app.positions.models import Market

router = APIRouter(prefix="/api/directory", tags=["directory"])

DirectoryStoreDep = Annotated[SecurityDirectoryStore, Depends(get_directory_store)]

#: Per the dispatch order's explicit instruction ("合併候選(上限 12 筆..." --
#: overrides the PRD's illustrative "如 20 筆"). Callers may raise this per
#: request up to ``_MAX_SEARCH_LIMIT`` (FR-3: "可由前端帶參數覆寫").
_DEFAULT_SEARCH_LIMIT = 12
_MAX_SEARCH_LIMIT = 50


class DirectoryItem(BaseModel):
    """One search candidate or resolve hit.

    ``sector`` rides along on the candidate rather than getting its own
    endpoint: the position form already holds the picked candidate when it
    needs the category, so a second round trip would only add a way for the
    two answers to disagree. ``None`` means the directory has no category for
    this security (上櫃 / ETF, an un-synced directory, or a TWSE code this
    build refuses to resolve) -- the form leaves the field empty in that case
    instead of guessing, so a ``null`` here must never be rendered as a
    category of its own.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    market: Market
    source: str
    as_of: str
    #: Always one of ``app.positions.sectors.TWSE_SECTORS`` when present, so a
    #: caller can submit it back unchanged as a ``Position.sector``.
    sector: str | None
    #: The sector's own provenance -- a different TWSE dataset, fetched at a
    #: different moment from ``source``/``as_of`` above.
    sector_source: str | None
    sector_as_of: str | None


class ResolveMiss(BaseModel):
    """``GET /api/directory/resolve/{symbol}`` when the directory has no entry.

    Carries none of ``DirectoryItem``'s ``name`` / ``market`` / sector
    fields -- not even as ``null`` -- so a caller can never mistake a miss for
    a hit with blank fields. ``found`` is the discriminator: a hit carries no
    ``found`` key at all, keeping its body exactly what it was before this
    model existed. ``directory_synced`` mirrors ``SearchResponse`` so a caller can
    tell "not in the directory" from "directory never synced" (FR-7).
    """

    model_config = ConfigDict(frozen=True)

    found: Literal[False]
    #: Echo of the requested symbol, unchanged.
    symbol: str
    directory_synced: bool
    as_of: str


class SearchResponse(BaseModel):
    """``GET /api/directory/search``."""

    model_config = ConfigDict(frozen=True)

    query: str
    items: list[DirectoryItem]
    #: True when more candidates matched than ``limit`` allows -- never claim
    #: "these are the only results" when some were cut (AC-7).
    truncated: bool
    #: False when the directory has never been synced (FR-7): the front end
    #: uses this to distinguish "no candidates" from "nothing to search yet",
    #: so it never shows an empty dropdown that looks like a real zero-result
    #: search.
    directory_synced: bool
    limit: int
    as_of: str


def _to_item(entry: DirectoryEntry) -> DirectoryItem:
    return DirectoryItem(
        symbol=entry.symbol,
        name=entry.name,
        market=entry.market,
        source=entry.source,
        as_of=entry.as_of.isoformat(),
        sector=entry.sector,
        sector_source=entry.sector_source,
        sector_as_of=None if entry.sector_as_of is None else entry.sector_as_of.isoformat(),
    )


@router.get("/resolve/{symbol}", response_model=DirectoryItem | ResolveMiss)
def resolve_symbol(symbol: str, store: DirectoryStoreDep) -> DirectoryItem | ResolveMiss:
    entry = store.resolve(symbol)
    if entry is None:
        return ResolveMiss(
            found=False,
            symbol=symbol,
            directory_synced=store.is_synced(),
            as_of=now_iso(),
        )
    return _to_item(entry)


@router.get("/search", response_model=SearchResponse)
def search_directory(
    store: DirectoryStoreDep,
    q: Annotated[str, Query(min_length=1, description="代號片段或公司名稱片段")],
    limit: Annotated[int, Query(ge=1, le=_MAX_SEARCH_LIMIT)] = _DEFAULT_SEARCH_LIMIT,
) -> SearchResponse:
    if not store.is_synced():
        # FR-7 honest degrade: never a 500, never a fake candidate list.
        return SearchResponse(
            query=q,
            items=[],
            truncated=False,
            directory_synced=False,
            limit=limit,
            as_of=now_iso(),
        )
    entries, truncated = store.search(q, limit=limit)
    return SearchResponse(
        query=q,
        items=[_to_item(entry) for entry in entries],
        truncated=truncated,
        directory_synced=True,
        limit=limit,
        as_of=now_iso(),
    )
