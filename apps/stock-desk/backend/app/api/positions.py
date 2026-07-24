"""Position CRUD, CSV template download, and CSV import endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_position_store
from app.positions.csv_io import ImportResult, build_template_csv, parse_import_csv
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore

router = APIRouter(prefix="/api/positions", tags=["positions"])

_TEMPLATE_FILENAME = "positions_template.csv"

StoreDep = Annotated[PositionStore, Depends(get_position_store)]


class PositionListResponse(BaseModel):
    """Envelope for the position list, carrying an ``as_of`` timestamp."""

    items: list[Position]
    as_of: str


@router.get("", response_model=PositionListResponse)
def list_positions(
    store: StoreDep,
) -> PositionListResponse:
    return PositionListResponse(
        items=store.list_all(),
        as_of=datetime.now(UTC).isoformat(),
    )


@router.post("", response_model=Position, status_code=status.HTTP_201_CREATED)
def create_position(
    body: PositionInput,
    store: StoreDep,
) -> Position:
    return store.create(body)


@router.get("/template.csv")
def download_template() -> Response:
    return Response(
        content=build_template_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{_TEMPLATE_FILENAME}"'
        },
    )


@router.post("/import", response_model=ImportResult)
async def import_positions(
    file: UploadFile,
    store: StoreDep,
) -> ImportResult:
    raw = await file.read()
    # utf-8-sig tolerates a spreadsheet-exported BOM without corrupting the
    # first header cell.
    text = raw.decode("utf-8-sig", errors="replace")
    inputs, errors = parse_import_csv(text)
    for position in inputs:
        store.create(position)
    return ImportResult(imported=len(inputs), errors=errors)


@router.put("/{position_id}", response_model=Position)
def update_position(
    position_id: int,
    body: PositionInput,
    store: StoreDep,
) -> Position:
    updated = store.update(position_id, body)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的部位"
        )
    return updated


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(
    position_id: int,
    store: StoreDep,
) -> Response:
    if not store.delete(position_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的部位"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
