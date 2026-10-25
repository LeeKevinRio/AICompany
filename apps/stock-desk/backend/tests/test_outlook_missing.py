"""``MissingItem`` and ``SourceStatus`` (ADR-0027 D-13; FL-39 backend half).

The invariants are enforced by the model validator in both directions (per
ADR-0027 D-13, N-115 sub-item N115-11), every field is required, and an
undeclared key is refused -- for items built in code and for stored
``missing_json`` items read back alike.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from app.outlook.missing import SOURCE_STATUS_PRECEDENCE, MissingItem, SourceStatus

AS_OF = date(2026, 10, 8)
ATTEMPTED = datetime(2026, 10, 8, 14, 5, tzinfo=UTC)
LATEST = date(2026, 10, 7)


def _item(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "code": "E-BARS-SHORT",
        "item": "bars",
        "required": "60",
        "available": "54",
        "source": "twse",
        "source_status": "failed_check",
        "attempted_at": None,
        "latest_available": None,
        "as_of": AS_OF,
        "detail": {"window": "60"},
    }
    fields.update(overrides)
    return fields


def _for_status(status: str | None) -> dict[str, Any]:
    if status is None:
        return _item(code="E-SCOPE-TYPE", source=None, source_status=None)
    extra: dict[str, Any] = {}
    if status == "fetch_failed":
        extra["attempted_at"] = ATTEMPTED
    if status == "not_yet_published":
        extra["latest_available"] = LATEST
    return _item(source_status=status, **extra)


def test_source_status_is_the_closed_d13_list() -> None:
    assert set(get_args(SourceStatus)) == {
        "not_covered",
        "fetch_failed",
        "not_yet_published",
        "failed_check",
        "not_configured",
        "unknown",
    }


def test_the_precedence_is_the_d13_judgement_order() -> None:
    assert SOURCE_STATUS_PRECEDENCE == (
        "not_configured",
        "not_covered",
        "fetch_failed",
        "failed_check",
        "not_yet_published",
        "unknown",
    )
    assert set(SOURCE_STATUS_PRECEDENCE) == set(get_args(SourceStatus))


@pytest.mark.parametrize("status", [*get_args(SourceStatus), None])
def test_an_item_that_keeps_the_invariants_builds(status: str | None) -> None:
    item = MissingItem(**_for_status(status))
    assert item.source_status == status
    assert (item.attempted_at is not None) == (status == "fetch_failed")
    assert (item.latest_available is not None) == (status == "not_yet_published")


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"source_status": None}, id="source-without-status"),
        pytest.param({"source": None}, id="status-without-source"),
        pytest.param({"source_status": "fetch_failed"}, id="fetch-failed-without-attempt"),
        pytest.param({"attempted_at": ATTEMPTED}, id="attempt-without-fetch-failed"),
        pytest.param(
            {"source": None, "source_status": None, "attempted_at": ATTEMPTED},
            id="attempt-without-status",
        ),
        pytest.param({"source_status": "not_yet_published"}, id="unpublished-without-latest"),
        pytest.param(
            {
                "source_status": "fetch_failed",
                "attempted_at": ATTEMPTED,
                "latest_available": LATEST,
            },
            id="latest-with-fetch-failed",
        ),
        pytest.param(
            {"source": None, "source_status": None, "latest_available": LATEST},
            id="latest-without-status",
        ),
    ],
)
def test_invariants_are_enforced(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MissingItem(**_item(**overrides))


@pytest.mark.parametrize("missing", list(_item()))
def test_every_field_is_required(missing: str) -> None:
    fields = _item()
    del fields[missing]
    with pytest.raises(ValidationError):
        MissingItem(**fields)


def test_an_undeclared_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        MissingItem(**_item(note="free text"))


def test_a_source_status_outside_the_list_is_refused() -> None:
    with pytest.raises(ValidationError):
        MissingItem(**_item(source_status="missing_setting"))


def test_the_item_is_frozen() -> None:
    item = MissingItem(**_item())
    with pytest.raises(ValidationError):
        item.code = "E-OTHER"


def test_a_stored_item_round_trips() -> None:
    item = MissingItem(**_for_status("fetch_failed"))
    stored = item.model_dump_json()
    assert MissingItem.model_validate_json(stored) == item


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda row: row.update(extra="x"), id="undeclared-key"),
        pytest.param(lambda row: row.update(attempted_at=None), id="broken-invariant"),
        pytest.param(lambda row: row.update(source_status="stale"), id="status-outside"),
    ],
)
def test_a_stored_item_that_breaks_an_invariant_does_not_load(mutate: Any) -> None:
    row = json.loads(MissingItem(**_for_status("fetch_failed")).model_dump_json())
    mutate(row)
    with pytest.raises(ValidationError):
        MissingItem.model_validate_json(json.dumps(row))
