"""Claim identifiers and the m count (ADR-0027 D-10 points 2 and 4) -- pure functions only.

* :func:`claim_id` -- the R-113 key
  ``{scope_kind}|h{h}|{rules_version}|{definition_version}|{kind}``;
* :func:`count_m` -- m, the number of registry rows with ``counts_toward_m = 1``;
* :func:`m_eff` -- ``max(m, M_EFF_FLOOR)`` with the floor taken from the claim's
  registered definition (pre-registration §4.4: 8 in v1).

The registration function and the ``python -m app.forecast.claims register``
CLI (D-10 point 3, N-115 #10) need the store and come with it; this module has
no DB access, no CLI and no ``__main__`` block yet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final, Literal, get_args

from app.dirdef.definition import DEFINITION_VERSION_PATTERN, DirectionDefinition, Horizon

#: ADR-0025 D-2 point 1 scopes; v1 registers market, sector_main and symbol.
ScopeKind = Literal["market", "sector_main", "sector_sub", "theme", "symbol"]
ClaimKind = Literal["forward", "replay"]

CLAIM_ID_SEPARATOR: Final = "|"

_DEFINITION_VERSION: Final = re.compile(DEFINITION_VERSION_PATTERN)


def claim_id(
    *,
    scope_kind: ScopeKind,
    horizon: Horizon,
    rules_version: str,
    definition_version: str,
    kind: ClaimKind,
) -> str:
    """The claim key of D-10 point 2; every part is validated, none may hold the separator."""
    if scope_kind not in get_args(ScopeKind):
        raise ValueError(f"unknown scope_kind {scope_kind!r}")
    if isinstance(horizon, bool) or horizon not in get_args(Horizon):
        raise ValueError(f"unknown horizon {horizon!r}")
    if kind not in get_args(ClaimKind):
        raise ValueError(f"unknown claim kind {kind!r}")
    if not isinstance(rules_version, str) or not rules_version.strip():
        raise ValueError("rules_version must be a non-empty string")
    if rules_version != rules_version.strip() or CLAIM_ID_SEPARATOR in rules_version:
        raise ValueError("rules_version may not hold the separator or surrounding spaces")
    if not isinstance(definition_version, str) or not _DEFINITION_VERSION.fullmatch(
        definition_version
    ):
        raise ValueError("definition_version must be dirdef-vMAJOR.MINOR")
    return CLAIM_ID_SEPARATOR.join(
        (scope_kind, f"h{horizon}", rules_version, definition_version, kind)
    )


def count_m(counts_toward_m: Iterable[int]) -> int:
    """m: how many of the registry's ``counts_toward_m`` values are 1 (each must be 0 or 1)."""
    m = 0
    for value in counts_toward_m:
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError(f"counts_toward_m must be 0 or 1, got {value!r}")
        m += value
    return m


def m_eff(m: int, *, definition: DirectionDefinition) -> int:
    """``max(m, definition.M_EFF_FLOOR)`` for a non-negative ``m``."""
    if isinstance(m, bool) or not isinstance(m, int) or m < 0:
        raise ValueError(f"m must be a non-negative int, got {m!r}")
    return max(m, definition.M_EFF_FLOOR)
