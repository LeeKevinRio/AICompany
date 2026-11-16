"""The published registries (ADR-0027 D-1 ``app/dirdef/``, D-10 point 1, D-14 G-3).

A version is added only by the batch that registers it after its freeze
(ADR-0030 D-6 CG-2); a registered version's entry, object and hashes are never
modified afterwards (risk R-4). A version that is not in its registry is not
published, and every lookup of it raises.

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
from app.dirdef.v1_0 import DIRDEF_V1_0

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


PUBLISHED_DIRECTION_DEFINITIONS: Final[Mapping[str, PublishedDefinition]] = MappingProxyType(
    {
        "dirdef-v1.0": PublishedDefinition(
            definition=DIRDEF_V1_0,
            definition_logic_sha256=(
                "4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa"
            ),
            definition_sha256="2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0",
        ),
    }
)
PUBLISHED_RULESETS: Final[Mapping[str, PublishedRuleset]] = MappingProxyType(
    {
        "outlook-market-v1.0-h3": PublishedRuleset(
            horizon=3,
            rules_sha256="f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443",
        ),
        "outlook-market-v1.0-h5": PublishedRuleset(
            horizon=5,
            rules_sha256="0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
        ),
    }
)
