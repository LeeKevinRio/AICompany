"""The missing-item structure of an outlook (ADR-0027 D-13, M-7; FL-39 backend half).

Standard library and ``pydantic`` only. ``SourceStatus`` is the closed D-13 list;
adding a value means revising D-13 and sending the wording for review.
``SOURCE_STATUS_PRECEDENCE`` is the D-13 judgement order: the first status with
positive evidence wins, and none may be inferred from "no data".

``MissingItem`` invariants, enforced by its model validator:

* ``source_status`` is not ``None`` if and only if ``source`` is not ``None``;
* ``attempted_at`` is not ``None`` if and only if ``source_status`` is
  ``fetch_failed``;
* ``latest_available`` is not ``None`` if and only if ``source_status`` is
  ``not_yet_published``.

The reverse directions of the last two (the D-13 field comments "fetch_failed
only", "not_yet_published only"), ``frozen=True``, ``extra="forbid"`` and the
absence of any field default are per ADR-0027 D-13 invariants, N-115
sub-item (N115-11, landed 94fa2f9). A stored ``missing_json`` item with an
undeclared key or a broken invariant does not load: it is neither skipped nor
filled in. The D-13 invariant "``label == insufficient`` iff ``missing`` is
non-empty" belongs to the whole record and is not judged here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

SourceStatus = Literal[
    "not_covered",
    "fetch_failed",
    "not_yet_published",
    "failed_check",
    "not_configured",
    "unknown",
]

#: D-13 judgement order; the first status that holds is the one recorded.
SOURCE_STATUS_PRECEDENCE: Final[tuple[SourceStatus, ...]] = (
    "not_configured",
    "not_covered",
    "fetch_failed",
    "failed_check",
    "not_yet_published",
    "unknown",
)


class MissingItem(BaseModel):
    """One missing input of an outlook (D-13)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: dirdef E-code, e.g. ``E-BARS-SHORT``.
    code: str
    #: Vocabulary key of the missing input.
    item: str
    #: Decimal or int, as a string.
    required: str | None
    available: str | None
    #: Data source id.
    source: str | None
    source_status: SourceStatus | None
    #: Attempt time; ``fetch_failed`` only.
    attempted_at: datetime | None
    #: ``not_yet_published`` only.
    latest_available: date | None
    as_of: date
    detail: dict[str, str]

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if (self.source_status is None) != (self.source is None):
            raise ValueError("source_status is set if and only if source is set")
        if (self.attempted_at is None) == (self.source_status == "fetch_failed"):
            raise ValueError("attempted_at is set if and only if source_status is fetch_failed")
        if (self.latest_available is None) == (self.source_status == "not_yet_published"):
            raise ValueError(
                "latest_available is set if and only if source_status is not_yet_published"
            )
        return self
