"""The one reader of the published dirdef and rule set registries (ADR-0027 D-1 ``definitions.py``).

``get_definition(definition_version)`` and ``get_ruleset(rules_version)``
return the registered object or raise; there is no default and no fallback.
The registries are empty while the G-3 freeze is pending, so in production both
always raise. ``claims.py``, the recorder, on-demand, the D-14 gate, the replay
runner and the store's write validation get their definitions and rule sets
here and nowhere else.

Rule files (ADR-0025 D-2 point 3): ``app/outlook/rules/h3.yaml`` and
``h5.yaml``, picked by the registered horizon and resolved against the
``app/outlook/`` package directory; the getters take no path and this module
reads no environment variable. The bytes go to the ``app.dirdef`` loader with
the registered ``rules_sha256`` and ``banned_phrases=BANNED_PHRASES`` imported
from ``app.advice.loader`` (the single source of banned phrases; this module is
the only loader call site in ``app/``).

Before a definition is returned it is checked, in order (B2D-1d): its
``definition_version`` equals the registry key, ``definition_logic_sha256`` and
``definition_sha256`` recomputed equal the registered values (so no field of a
registered version, text and C-8 provenance included, can be edited in place),
and no string value holds a banned phrase (ADR-0027 N-128). An empty banned
phrase list is a rejection, as in the rule set loader. Successful results are
cached for the process; a failure at any step is not cached.

The definition scan enumerates string values with
``app.dirdef.strings.string_values`` -- the same function the rule set validator
uses, the one enumeration in ``app/`` -- and a hit raises
:class:`BannedPhraseInDefinitionError`.

Test seams (named in the tests): the two registry names below, the
:func:`_read_rules_bytes` reader, and the two cache dicts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, get_args

from app.advice.loader import BANNED_PHRASES
from app.dirdef.definition import (
    DirectionDefinition,
    Horizon,
    definition_logic_sha256,
    definition_sha256,
)
from app.dirdef.registry import PUBLISHED_DIRECTION_DEFINITIONS, PUBLISHED_RULESETS
from app.dirdef.rules import OutlookRuleSet, RuleSetLoadError, load_ruleset
from app.dirdef.strings import string_values

#: ``app/outlook/rules/``, resolved against the ``app/outlook/`` package directory.
RULES_DIR: Final = Path(__file__).resolve().parent.parent / "outlook" / "rules"


class UnpublishedVersionError(LookupError):
    """The requested version is not in its registry."""


class PublishedVersionRejectedError(ValueError):
    """A registered version failed its checks; it is not returned."""


class BannedPhraseInDefinitionError(PublishedVersionRejectedError):
    """A registered definition holds a banned phrase in a string value (ADR-0027 N-128)."""


_DEFINITION_CACHE: dict[str, DirectionDefinition] = {}
_RULESET_CACHE: dict[str, OutlookRuleSet] = {}


def rules_path(horizon: int) -> Path:
    """The rule file of ``horizon`` (3 or 5)."""
    if isinstance(horizon, bool) or horizon not in get_args(Horizon):
        raise ValueError(f"no rule file for horizon {horizon!r}")
    return RULES_DIR / f"h{horizon}.yaml"


def _read_rules_bytes(horizon: int) -> bytes:
    return rules_path(horizon).read_bytes()


def _scan_definition(definition: DirectionDefinition) -> None:
    """Reject ``definition`` if any of its string values contains a banned phrase.

    No phrases to scan with is a rejection too (fail-closed).
    """
    if not BANNED_PHRASES:
        raise PublishedVersionRejectedError("no banned phrases to scan with: rejected")
    for text in string_values(definition):
        for phrase in BANNED_PHRASES:
            if phrase in text:
                raise BannedPhraseInDefinitionError(
                    "registered definition holds a banned phrase in a string value"
                )


def get_definition(definition_version: str) -> DirectionDefinition:
    """The registered definition of ``definition_version``; raises when absent or rejected."""
    cached = _DEFINITION_CACHE.get(definition_version)
    if cached is not None:
        return cached
    entry = PUBLISHED_DIRECTION_DEFINITIONS.get(definition_version)
    if entry is None:
        raise UnpublishedVersionError("definition_version is not published")
    definition = entry.definition
    if definition.definition_version != definition_version:
        raise PublishedVersionRejectedError(
            "registered definition carries a different definition_version"
        )
    if definition_logic_sha256(definition) != entry.definition_logic_sha256:
        raise PublishedVersionRejectedError(
            "definition does not match its registered definition_logic_sha256"
        )
    if definition_sha256(definition) != entry.definition_sha256:
        raise PublishedVersionRejectedError(
            "definition does not match its registered definition_sha256"
        )
    _scan_definition(definition)
    _DEFINITION_CACHE[definition_version] = definition
    return definition


def get_ruleset(rules_version: str) -> OutlookRuleSet:
    """The registered rule set of ``rules_version``; raises when absent or rejected."""
    cached = _RULESET_CACHE.get(rules_version)
    if cached is not None:
        return cached
    entry = PUBLISHED_RULESETS.get(rules_version)
    if entry is None:
        raise UnpublishedVersionError("rules_version is not published")
    try:
        data = _read_rules_bytes(entry.horizon)
    except OSError as exc:
        raise PublishedVersionRejectedError(
            f"rule file of horizon {entry.horizon} cannot be read ({type(exc).__name__})"
        ) from exc
    try:
        ruleset = load_ruleset(data, rules_sha256=entry.rules_sha256, banned_phrases=BANNED_PHRASES)
    except RuleSetLoadError as exc:
        raise PublishedVersionRejectedError(f"rule set rejected: {exc}") from exc
    _RULESET_CACHE[rules_version] = ruleset
    return ruleset
