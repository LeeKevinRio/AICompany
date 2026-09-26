"""Publishing a test-only definition for a while (ADR-0012 D-15, Consequences).

Every entry that persists or outputs something accepts only the objects in
``app.sectors.definition.PUBLISHED_DEFINITIONS`` (C-47). A test that needs a
cheaper or stricter definition -- e.g. V1 with fewer T1 dates -- publishes it
here for its own duration: the module attribute is swapped, so
``require_published`` (which reads it on every call) sees the addition, and the
original tuple is restored afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from app.sectors import definition as definition_module
from app.sectors.definition import SectorMomentumDefinition


@contextmanager
def published(*extra: SectorMomentumDefinition) -> Iterator[None]:
    """``PUBLISHED_DEFINITIONS`` plus ``extra`` inside the block, the original after."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            definition_module,
            "PUBLISHED_DEFINITIONS",
            (*definition_module.PUBLISHED_DEFINITIONS, *extra),
        )
        yield
