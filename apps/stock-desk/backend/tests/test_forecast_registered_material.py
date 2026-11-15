"""``definitions.registered_ruleset`` / ``registered_definition`` (ADR-0030 D-5 points 2-3).

``report verify`` rebuilds a claim's rule set and definition from the bytes
and the JSON stored in ``forecast_claim_registry``, not from the file on disk
or the published registry. Every check of the published path holds for them
too: the rule bytes' hash and logic hash, the definition's two hashes and the
banned phrase scan. Synthetic fixtures only.
"""

from __future__ import annotations

import ast
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
from tests.import_graph import APP_ROOT
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


# --- K-11 (qa batch 5 follow-up 5): only report.py takes caller bytes into a rule set ---------

#: The two ``app/`` functions that accept rule bytes and a definition from the caller.
CALLER_MATERIAL = frozenset({"registered_ruleset", "registered_definition"})


def _material_uses(source: str) -> list[str]:
    """Every reference to :data:`CALLER_MATERIAL` in ``source``, except their own ``def``.

    A call, an attribute, a bare name (an alias or a callback), an import and a
    string argument (``getattr``) all count, so an indirect use is caught too.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in CALLER_MATERIAL:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in CALLER_MATERIAL:
            found.append(ast.unparse(node))
        elif isinstance(node, ast.ImportFrom):
            found += [alias.name for alias in node.names if alias.name in CALLER_MATERIAL]
        elif isinstance(node, ast.Call):
            found += [
                str(arg.value)
                for arg in node.args
                if isinstance(arg, ast.Constant) and arg.value in CALLER_MATERIAL
            ]
    return found


def test_k11_only_the_report_uses_the_caller_material_functions() -> None:
    users = {
        path.relative_to(APP_ROOT).as_posix()
        for path in sorted(APP_ROOT.rglob("*.py"))
        if _material_uses(path.read_text(encoding="utf-8"))
    }
    assert users == {"forecast/report.py"}
    # definitions.py defines them and does not use them itself.
    source = (APP_ROOT / "forecast" / "definitions.py").read_text(encoding="utf-8")
    defined = {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}
    assert CALLER_MATERIAL <= defined and _material_uses(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "definitions.registered_ruleset(b, rules_sha256=s, logic_sha256=l)\n",
        "from app.forecast.definitions import registered_definition\n",
        "from app.forecast.definitions import registered_ruleset as load\n",
        "f = definitions.registered_definition\n",
        "f = getattr(definitions, 'registered_ruleset')\n",
        "registered_ruleset(b, rules_sha256=s, logic_sha256=l)\n",
    ],
)
def test_the_caller_material_scan_has_teeth(source: str) -> None:
    assert _material_uses(source) != []


def test_the_caller_material_scan_ignores_docstrings_and_other_names() -> None:
    source = '"""registered_ruleset is mentioned here."""\ndef registered_rulesets():\n    pass\n'
    assert _material_uses(source) == []
