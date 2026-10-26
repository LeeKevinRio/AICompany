"""``app/forecast/definitions.py`` (ADR-0027 D-1; FL-26, FL-78 (k)(l2)).

Seams (FL-78 (k)(l); ``tests.dirdef_helpers.DEFINITIONS_SEAMS``): the module's
``PUBLISHED_DIRECTION_DEFINITIONS`` / ``PUBLISHED_RULESETS`` names (replaced by
test registries), ``_read_rules_bytes`` (replaced to serve fixture bytes) and
the two cache dicts (reset per test). The outlook field list is replaced
through ``tests.dirdef_helpers.RULE_FIELDS_SEAM``.

* production: both registries are empty, so every lookup raises (G-3 closed);
* B2D-1d/1f: ``get_definition`` checks the version key, the logic hash, the
  full hash ``definition_sha256`` and then the banned phrases, in that order; an
  in-place edit of a registered version (description, C-8 provenance) keeps the
  logic hash and is refused on the full hash; nothing failed is cached;
* FL-26: a ``rules_version`` that is not registered is refused; registered
  bytes are hash-checked by the loader (one changed byte with the old hash is
  refused);
* FL-78 (l2): every banned phrase x every string value position of the fixture
  definition. Each position is marked: ``scan`` (``get_definition`` raises
  ``BannedPhraseInDefinitionError``, nothing is returned or cached) or
  ``type`` (the definition type itself refuses the value: construction fails,
  so there is nothing to register or return). A clean definition is returned;
* caching: successes are cached for the process, failures are not.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from pydantic import ValidationError

from app.advice.loader import BANNED_PHRASES
from app.dirdef import registry, rules
from app.dirdef.definition import DirectionDefinition, definition_logic_sha256, definition_sha256
from app.dirdef.registry import PublishedDefinition, PublishedRuleset
from app.dirdef.rules import BannedPhraseRuleSetError
from app.dirdef.strings import string_values
from app.forecast import definitions
from app.forecast.definitions import (
    RULES_DIR,
    BannedPhraseInDefinitionError,
    PublishedVersionRejectedError,
    UnpublishedVersionError,
    get_definition,
    get_ruleset,
    rules_path,
)
from tests.dirdef_helpers import (
    DEFINITIONS_SEAMS,
    RULE_FIELDS_SEAM,
    SUBSTITUTE_FIELDS,
    definition_data,
    make_definition,
    rule_data,
    ruleset_bytes,
    ruleset_data,
    sha256_hex,
)

REGISTRY_DEFINITIONS, REGISTRY_RULESETS, READER, DEFINITION_CACHE, RULESET_CACHE = DEFINITIONS_SEAMS


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(definitions, DEFINITION_CACHE, {})
    monkeypatch.setattr(definitions, RULESET_CACHE, {})


def _register_definition(
    monkeypatch: pytest.MonkeyPatch,
    definition: DirectionDefinition,
    *,
    logic: str | None = None,
    full: str | None = None,
    registered_as: DirectionDefinition | None = None,
) -> None:
    """Register ``definition``; hashes default to those of ``registered_as`` (or itself)."""
    basis = registered_as or definition
    entry = PublishedDefinition(
        definition=definition,
        definition_logic_sha256=logic or definition_logic_sha256(basis),
        definition_sha256=full or definition_sha256(basis),
    )
    monkeypatch.setattr(
        definitions,
        REGISTRY_DEFINITIONS,
        MappingProxyType({definition.definition_version: entry}),
    )


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Callable[[bytes, str | None], list[int]]:
    """Register ``outlook-market-v1.0-h3`` and serve ``data`` as its rule file."""
    monkeypatch.setattr(rules, RULE_FIELDS_SEAM, SUBSTITUTE_FIELDS)

    def install(data: bytes, digest: str | None = None) -> list[int]:
        calls: list[int] = []
        entry = PublishedRuleset(horizon=3, rules_sha256=digest or sha256_hex(data))
        monkeypatch.setattr(
            definitions, REGISTRY_RULESETS, MappingProxyType({"outlook-market-v1.0-h3": entry})
        )

        def read(horizon: int) -> bytes:
            calls.append(horizon)
            return data

        monkeypatch.setattr(definitions, READER, read)
        return calls

    return install


# --- Production state ------------------------------------------------------------------


def test_the_registries_are_empty() -> None:
    assert dict(registry.PUBLISHED_DIRECTION_DEFINITIONS) == {}
    assert dict(registry.PUBLISHED_RULESETS) == {}


@pytest.mark.parametrize("version", ["dirdef-v1.0", "dirdef-v0.1"])
def test_every_definition_lookup_raises_in_production(version: str) -> None:
    with pytest.raises(UnpublishedVersionError):
        get_definition(version)


@pytest.mark.parametrize("version", ["outlook-market-v1.0-h3", "outlook-market-v1.0-h5"])
def test_every_ruleset_lookup_raises_in_production(version: str) -> None:
    with pytest.raises(UnpublishedVersionError):
        get_ruleset(version)


def test_every_published_ruleset_loads() -> None:
    # FL-78 (k): each registered version must load; no version is registered yet.
    for version in registry.PUBLISHED_RULESETS:
        get_ruleset(version)  # pragma: no cover - the registry is empty until G-3


def test_the_rule_files_sit_under_the_outlook_package() -> None:
    assert Path(rules.__file__).resolve().parents[1] / "outlook" / "rules" == RULES_DIR
    assert rules_path(3) == RULES_DIR / "h3.yaml"
    assert rules_path(5) == RULES_DIR / "h5.yaml"


@pytest.mark.parametrize("horizon", [1, 4, True])
def test_rules_path_refuses_other_horizons(horizon: int) -> None:
    with pytest.raises(ValueError):
        rules_path(horizon)


def test_the_default_reader_reads_the_horizon_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "h5.yaml").write_bytes(b"fixture")
    monkeypatch.setattr(definitions, "RULES_DIR", tmp_path)
    assert definitions._read_rules_bytes(5) == b"fixture"


# --- Definitions -----------------------------------------------------------------------


def test_a_registered_clean_definition_is_returned_and_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = make_definition()
    _register_definition(monkeypatch, definition)
    assert get_definition("dirdef-v1.0") is definition
    monkeypatch.setattr(definitions, REGISTRY_DEFINITIONS, MappingProxyType({}))
    assert get_definition("dirdef-v1.0") is definition


def test_a_registration_under_another_version_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = make_definition()
    entry = PublishedDefinition(
        definition=definition,
        definition_logic_sha256=definition_logic_sha256(definition),
        definition_sha256=definition_sha256(definition),
    )
    monkeypatch.setattr(definitions, REGISTRY_DEFINITIONS, MappingProxyType({"dirdef-v2.0": entry}))
    with pytest.raises(PublishedVersionRejectedError, match="definition_version"):
        get_definition("dirdef-v2.0")


def test_a_registered_hash_mismatch_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _register_definition(monkeypatch, make_definition(), logic="f" * 64)
    with pytest.raises(PublishedVersionRejectedError, match="definition_logic_sha256"):
        get_definition("dirdef-v1.0")
    assert definitions._DEFINITION_CACHE == {}


def test_a_registered_full_hash_mismatch_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _register_definition(monkeypatch, make_definition(), full="f" * 64)
    for _ in range(2):  # not cached
        with pytest.raises(PublishedVersionRejectedError, match="definition_sha256"):
            get_definition("dirdef-v1.0")
    assert definitions._DEFINITION_CACHE == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("description", "edited in place after registration", id="description"),
        pytest.param("c8_decision_ref", "work/decisions/c8-edited.md", id="c8-ref"),
        pytest.param("c8_decision_sha256", "2" * 64, id="c8-sha"),
    ],
)
def test_an_in_place_edit_of_a_registered_version_is_refused(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    # B2D-1f: hashes registered for the original; the object served is edited.
    original = make_definition()
    edited = make_definition(**{field: value})
    assert definition_logic_sha256(edited) == definition_logic_sha256(original)
    _register_definition(monkeypatch, edited, registered_as=original)
    with pytest.raises(PublishedVersionRejectedError, match="definition_sha256"):
        get_definition("dirdef-v1.0")
    assert definitions._DEFINITION_CACHE == {}


def test_the_version_key_is_checked_before_the_logic_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # qa F-4: wrong key and wrong hashes -> the error names definition_version.
    definition = make_definition()
    entry = PublishedDefinition(
        definition=definition, definition_logic_sha256="f" * 64, definition_sha256="f" * 64
    )
    monkeypatch.setattr(definitions, REGISTRY_DEFINITIONS, MappingProxyType({"dirdef-v9.0": entry}))
    with pytest.raises(PublishedVersionRejectedError, match="definition_version") as caught:
        get_definition("dirdef-v9.0")
    assert "sha256" not in str(caught.value)
    assert definitions._DEFINITION_CACHE == {}


def test_the_checks_run_version_then_logic_then_full_then_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # C-3 order: a definition that would fail every later step fails the earliest one.
    poisoned = make_definition(description=f"x {BANNED_PHRASES[0]}")
    _register_definition(monkeypatch, poisoned, logic="f" * 64, full="f" * 64)
    with pytest.raises(PublishedVersionRejectedError, match="definition_logic_sha256"):
        get_definition("dirdef-v1.0")
    _register_definition(monkeypatch, poisoned, full="f" * 64)
    with pytest.raises(PublishedVersionRejectedError, match="definition_sha256") as caught:
        get_definition("dirdef-v1.0")
    assert not isinstance(caught.value, BannedPhraseInDefinitionError)
    _register_definition(monkeypatch, poisoned)
    with pytest.raises(BannedPhraseInDefinitionError):
        get_definition("dirdef-v1.0")


def test_an_empty_banned_phrase_list_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # qa low: fail-closed like the rule set loader.
    _register_definition(monkeypatch, make_definition())
    monkeypatch.setattr(definitions, "BANNED_PHRASES", ())
    with pytest.raises(PublishedVersionRejectedError, match="no banned phrases"):
        get_definition("dirdef-v1.0")
    assert definitions._DEFINITION_CACHE == {}


#: (position id, field, value builder from the phrase, what stops it).
DEFINITION_POSITIONS: list[tuple[str, str, Callable[[str], Any], str]] = [
    ("definition_version", "definition_version", lambda p: f"dirdef-v1.0{p}", "type"),
    ("description", "description", lambda p: f"note {p}", "scan"),
    (
        "basket_order[0]",
        "BASKET_EXCLUSION_REASON_ORDER",
        lambda p: (p, "split_or_reduction_suspected", "t_plus_h_bar_unavailable"),
        "type",
    ),
    (
        "basket_order[1]",
        "BASKET_EXCLUSION_REASON_ORDER",
        lambda p: ("dividend_factor_unusable", p, "t_plus_h_bar_unavailable"),
        "type",
    ),
    (
        "basket_order[2]",
        "BASKET_EXCLUSION_REASON_ORDER",
        lambda p: ("dividend_factor_unusable", "split_or_reduction_suspected", p),
        "type",
    ),
    ("f2_variant", "f2_variant", lambda p: p, "type"),
    ("c8_decision_ref", "c8_decision_ref", lambda p: f"work/{p}.md", "scan"),
    ("c8_decision_sha256", "c8_decision_sha256", lambda p: p * 64, "type"),
]


def test_the_position_table_covers_every_string_value() -> None:
    # A new string field in the type grows string_values and forces a new row.
    assert len(string_values(make_definition())) == len(DEFINITION_POSITIONS)


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
@pytest.mark.parametrize(("position", "field", "value", "stopped_by"), DEFINITION_POSITIONS)
def test_a_banned_phrase_in_any_definition_position_is_not_returned(
    monkeypatch: pytest.MonkeyPatch,
    phrase: str,
    position: str,
    field: str,
    value: Callable[[str], Any],
    stopped_by: str,
) -> None:
    data = definition_data(**{field: value(phrase)})
    if stopped_by == "type":
        with pytest.raises(ValidationError):
            DirectionDefinition.model_validate(data)
        return
    _register_definition(monkeypatch, DirectionDefinition.model_validate(data))
    for _ in range(2):  # not cached: the second call is refused the same way
        with pytest.raises(BannedPhraseInDefinitionError):
            get_definition("dirdef-v1.0")
    assert definitions._DEFINITION_CACHE == {}


# --- Rule sets (FL-26) ------------------------------------------------------------------


def test_a_registered_clean_ruleset_is_returned_and_cached(
    serve: Callable[[bytes, str | None], list[int]],
) -> None:
    calls = serve(ruleset_bytes(ruleset_data()), None)
    first = get_ruleset("outlook-market-v1.0-h3")
    assert first.version == "1.0.0"
    assert get_ruleset("outlook-market-v1.0-h3") is first
    assert calls == [3]


def test_an_unregistered_rules_version_is_refused(
    serve: Callable[[bytes, str | None], list[int]],
) -> None:
    calls = serve(ruleset_bytes(ruleset_data()), None)
    with pytest.raises(UnpublishedVersionError):
        get_ruleset("outlook-market-v9.9-h3")
    assert calls == []


def test_bytes_that_miss_the_registered_hash_are_refused(
    serve: Callable[[bytes, str | None], list[int]],
) -> None:
    raw = ruleset_bytes(ruleset_data())
    serve(raw.replace(b"0.5", b"0.6", 1), sha256_hex(raw))
    with pytest.raises(PublishedVersionRejectedError, match="rules_sha256"):
        get_ruleset("outlook-market-v1.0-h3")


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_a_ruleset_with_a_banned_phrase_is_refused(
    serve: Callable[[bytes, str | None], list[int]], phrase: str
) -> None:
    serve(ruleset_bytes(ruleset_data(rule_data(explanation=f"it {phrase}"))), None)
    with pytest.raises(PublishedVersionRejectedError) as caught:
        get_ruleset("outlook-market-v1.0-h3")
    assert isinstance(caught.value.__cause__, BannedPhraseRuleSetError)


def test_an_unreadable_rule_file_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = PublishedRuleset(horizon=5, rules_sha256="0" * 64)
    monkeypatch.setattr(definitions, REGISTRY_RULESETS, MappingProxyType({"v": entry}))
    monkeypatch.setattr(definitions, "RULES_DIR", tmp_path / "missing")
    with pytest.raises(PublishedVersionRejectedError, match="cannot be read"):
        get_ruleset("v")


def test_a_failure_is_not_cached(serve: Callable[[bytes, str | None], list[int]]) -> None:
    good = ruleset_bytes(ruleset_data())
    serve(good.replace(b"0.5", b"0.6", 1), sha256_hex(good))
    with pytest.raises(PublishedVersionRejectedError):
        get_ruleset("outlook-market-v1.0-h3")
    serve(good, None)
    assert get_ruleset("outlook-market-v1.0-h3").version == "1.0.0"


# --- Registry entry types --------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        pytest.param({"horizon": 4, "rules_sha256": "0" * 64}, ValueError, id="horizon"),
        pytest.param({"horizon": True, "rules_sha256": "0" * 64}, ValueError, id="bool"),
        pytest.param({"horizon": 3, "rules_sha256": "0" * 63}, ValueError, id="sha"),
    ],
)
def test_published_ruleset_entries_are_checked(
    kwargs: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error):
        PublishedRuleset(**kwargs)


def test_published_definition_entries_are_checked() -> None:
    with pytest.raises(TypeError):
        PublishedDefinition(
            definition=object(),  # type: ignore[arg-type]
            definition_logic_sha256="0" * 64,
            definition_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="definition_logic_sha256"):
        PublishedDefinition(
            definition=make_definition(), definition_logic_sha256="X", definition_sha256="0" * 64
        )
    with pytest.raises(ValueError, match="definition_sha256"):
        PublishedDefinition(
            definition=make_definition(), definition_logic_sha256="0" * 64, definition_sha256="X"
        )
