"""The published registries (ADR-0027 D-1 ``app/dirdef/``, D-10 point 1, D-14 G-3).

Both registries are **empty**: nothing is frozen yet, so G-3 does not hold and
the write gate stays closed. A version is added only in the batch that
registers it after the G-3 freeze.

* the direction definition registry maps ``definition_version`` to the frozen
  definition object and its registered ``definition_logic_sha256`` and
  ``definition_sha256`` (B2D-1);
* the rule set registry maps ``rules_version`` to the horizon and the
  ``rules_sha256`` of the rule file bytes -- no rule content (D-1).

In ``app/`` only ``app/forecast/definitions.py`` reads them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, get_args

from app.dirdef.definition import DirectionDefinition, Horizon

_SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")


def _require_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_HEX.fullmatch(value) is None:
        raise ValueError(f"{name} must be 64 lower-case hex digits")


@dataclass(frozen=True)
class PublishedDefinition:
    """One registered dirdef version."""

    definition: DirectionDefinition
    definition_logic_sha256: str
    definition_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.definition, DirectionDefinition):
            raise TypeError("definition must be a DirectionDefinition")
        _require_sha256(self.definition_logic_sha256, "definition_logic_sha256")
        _require_sha256(self.definition_sha256, "definition_sha256")


@dataclass(frozen=True)
class PublishedRuleset:
    """One registered rule set version: its horizon and the hash of its bytes."""

    horizon: Horizon
    rules_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or self.horizon not in get_args(Horizon):
            raise ValueError(f"horizon must be one of {get_args(Horizon)}")
        _require_sha256(self.rules_sha256, "rules_sha256")


PUBLISHED_DIRECTION_DEFINITIONS: Final[Mapping[str, PublishedDefinition]] = MappingProxyType({})
PUBLISHED_RULESETS: Final[Mapping[str, PublishedRuleset]] = MappingProxyType({})
