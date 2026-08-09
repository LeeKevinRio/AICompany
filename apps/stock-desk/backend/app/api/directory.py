"""Security directory endpoints: 代號 -> 公司名稱 -> 市場 lookup (FR-2/FR-3).

``GET /api/directory/resolve/{symbol}`` backs FR-2's automatic market
determination: a hit means the caller can trust the returned ``market``
without asking the user to pick one; a miss (404) is the honest "not in the
directory" signal FR-2's Q1 fallback (CEO 裁示 (b)：僅在查無時跳出縮小版手動
選市場) is built on.

``GET /api/directory/search`` backs FR-3's combobox candidates: symbol-prefix
+ name-substring, merged and capped, with an honest ``directory_synced`` flag
so an empty directory (FR-7) never gets mistaken for "no candidates found".
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
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
    """One search candidate or resolve hit."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    market: Market
    source: str
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
    )


@router.get("/resolve/{symbol}", response_model=DirectoryItem)
def resolve_symbol(symbol: str, store: DirectoryStoreDep) -> DirectoryItem:
    entry = store.resolve(symbol)
    if entry is None:
        raise HTTPException(status_code=404, detail="目錄查無此代號")
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
