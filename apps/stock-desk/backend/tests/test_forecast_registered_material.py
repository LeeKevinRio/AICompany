"""``definitions.registered_ruleset`` / ``registered_definition`` (ADR-0030 D-5 points 2-3).

``report verify`` rebuilds a claim's rule set and definition from the bytes
and the JSON stored in ``forecast_claim_registry``, not from the file on disk
or the published registry. Every check of the published path holds for them
too: the rule bytes' hash and logic hash, the definition's two hashes and the
banned phrase scan. Synthetic fixtures only.
"""

from __future__ import annotations

import hashlib

import pytest

from app.dirdef.definition import DirectionDefinition, definition_logic_sha256, definition_sha256
from app.dirdef.hashing import canonical_json
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions
from app.forecast.definitions import (
    BannedPhraseInDefinitionError,
    PublishedVersionRejectedError,
    registered_definition,
    registered_ruleset,
)
from tests.dirdef_helpers import DIRDEF_V1_0_G7
from tests.outlook_helpers import definition, rule_bytes, ruleset


def _rules(horizon: int = 3) -> tuple[bytes, str, str]:
    data = rule_bytes(horizon)
    return data, hashlib.sha256(data).hexdigest(), rules_logic_sha256(ruleset(horizon))


def _definition_json(defn: DirectionDefinition | None = None) -> tuple[str, str, str]:
    target = defn or definition()
    return (
        canonical_json(target.model_dump(mode="json")),
        definition_sha256(target),
        definition_logic_sha256(target),
    )


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_registered_bytes_rebuild_the_rule_set(horizon: int) -> None:
    data, sha, logic = _rules(horizon)
    assert registered_ruleset(data, rules_sha256=sha, logic_sha256=logic) == ruleset(horizon)


def test_the_registered_rule_bytes_are_checked() -> None:
    data, sha, logic = _rules()
    with pytest.raises(PublishedVersionRejectedError, match="rule set rejected"):
        registered_ruleset(data + b"# x\n", rules_sha256=sha, logic_sha256=logic)
    with pytest.raises(PublishedVersionRejectedError, match="rules_logic_sha256"):
        registered_ruleset(data, rules_sha256=sha, logic_sha256="0" * 64)
    with pytest.raises(PublishedVersionRejectedError, match="not bytes"):
        registered_ruleset(data.decode("utf-8"), rules_sha256=sha, logic_sha256=logic)  # type: ignore[arg-type]


def test_the_registered_rule_bytes_go_through_the_banned_phrases() -> None:
    poisoned = rule_bytes(3).replace("趨勢票計為偏多一票。".encode(), "保證。".encode(), 1)
    with pytest.raises(PublishedVersionRejectedError, match="rule set rejected"):
        registered_ruleset(
            poisoned,
            rules_sha256=hashlib.sha256(poisoned).hexdigest(),
            logic_sha256=rules_logic_sha256(ruleset(3)),
        )


def test_the_registered_json_rebuilds_the_definition() -> None:
    text, full, logic = _definition_json()
    assert registered_definition(text, full_sha256=full, logic_sha256=logic) == definition()


def test_the_registered_definition_is_checked() -> None:
    text, full, logic = _definition_json()
    with pytest.raises(PublishedVersionRejectedError, match="cannot be read"):
        registered_definition("{", full_sha256=full, logic_sha256=logic)
    with pytest.raises(PublishedVersionRejectedError, match="definition_logic_sha256"):
        registered_definition(text, full_sha256=full, logic_sha256="0" * 64)
    with pytest.raises(PublishedVersionRejectedError, match="definition_sha256"):
        registered_definition(text, full_sha256="0" * 64, logic_sha256=logic)
    poisoned = DirectionDefinition.model_validate({**DIRDEF_V1_0_G7, "description": "穩賺"})
    text, full, logic = _definition_json(poisoned)
    with pytest.raises(BannedPhraseInDefinitionError):
        registered_definition(text, full_sha256=full, logic_sha256=logic)


def _caches() -> tuple[dict[str, object], dict[str, object]]:
    return dict(vars(definitions)["_RULESET_CACHE"]), dict(vars(definitions)["_DEFINITION_CACHE"])


def test_nothing_registered_is_cached() -> None:
    data, sha, logic = _rules()
    before = _caches()
    registered_ruleset(data, rules_sha256=sha, logic_sha256=logic)
    text, full, d_logic = _definition_json()
    registered_definition(text, full_sha256=full, logic_sha256=d_logic)
    assert _caches() == before
