"""Model base with the unvalidated construction paths disabled (ADR-0027 D-1 ``app/dirdef/`` (4)).

``model_construct`` skips every validator, and ``model_copy(update=...)`` writes
the update without validating it; either would yield a rule set (or a
definition) that never went through the banned-phrase scan or the field checks.
Both are refused with ``TypeError``, mirroring ADR-0027 D-15 point 3a. A plain
``model_copy()`` (no ``update``) is an exact copy of an already validated
object, so it stays available.

The deprecated ``copy`` is the same bypass under an older name: with
``update`` it builds the new object without validating the update, and with
``include`` / ``exclude`` it builds one with fields missing. It follows the
``model_copy`` rule -- any of the three given is a ``TypeError`` -- and a plain
``copy()`` is ``model_copy()`` (qa M-1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel


class GuardedModel(BaseModel):
    """A ``BaseModel`` that can only be built through validation."""

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Self:
        raise TypeError(
            f"{cls.__name__}.model_construct is disabled: build it through validation "
            "(ADR-0027 D-1 app/dirdef/ (4), as D-15 point 3a)"
        )

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        if update is not None:
            raise TypeError(
                f"{type(self).__name__}.model_copy(update=...) is disabled: validate a new "
                "object instead (ADR-0027 D-1 app/dirdef/ (4), as D-15 point 3a)"
            )
        return super().model_copy(deep=deep)

    def copy(
        self,
        *,
        include: Any = None,
        exclude: Any = None,
        update: Any = None,
        deep: bool = False,
    ) -> Self:
        if update is not None or include is not None or exclude is not None:
            raise TypeError(
                f"{type(self).__name__}.copy(update/include/exclude=...) is disabled: validate "
                "a new object instead (ADR-0027 D-1 app/dirdef/ (4), as D-15 point 3a)"
            )
        return self.model_copy(deep=deep)
