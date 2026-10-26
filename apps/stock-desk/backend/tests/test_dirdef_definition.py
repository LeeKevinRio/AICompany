"""``DirectionDefinition`` and its two hashes (ADR-0027 D-1 ``app/dirdef/``, D-10, B2D-1).

* the type satisfies ``app.forecast.band.BandDefinition`` (mypy strict, static
  assignment below) and works with ``labeled_snapshot_violations``;
* frozen, ``extra="forbid"``, strict types, and the shape checks;
* ``model_construct``, ``model_copy(update=...)`` and the deprecated
  ``copy(update/include/exclude=...)`` raise ``TypeError`` (B2D-2, qa M-1);
* FL-31, FL-36, FL-37 in B2: each named constant exists and lies inside
  ``definition_logic_sha256`` (changing it changes the hash); value pins and
  "only stricter" come with the first registration;
* B2D-1f / FL-33 pure part: every field outside
  ``DEFINITION_NON_LOGIC_FIELDS`` moves the logic hash (table tied to the
  field set); every non-logic field (version label, description, the two C-8
  provenance fields) keeps the logic hash and moves ``definition_sha256``.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import pytest
from pydantic import ValidationError

from app.dirdef.definition import (
    DEFINITION_NON_LOGIC_FIELDS,
    DirectionDefinition,
    definition_logic_sha256,
    definition_sha256,
)
from app.forecast.band import BandDefinition, labeled_snapshot_violations
from tests.dirdef_helpers import definition_data, make_definition

#: Static check (mypy strict): the concrete type satisfies band.py's Protocol.
_AS_BAND: BandDefinition = make_definition()

#: For each logic field, a different but valid value (the hash must move).
CHANGED_VALUES: dict[str, Any] = {
    "K3": 0.44,
    "K5": 0.5,
    "EPS": 2e-12,
    "SIGMA_MIN_VALID": 56,
    "SIGMA_FLOOR": 0.0011,
    "BASKET_EXCLUSION_REASON_ORDER": (
        "split_or_reduction_suspected",
        "dividend_factor_unusable",
        "t_plus_h_bar_unavailable",
    ),
    "SPLIT_SUSPECT_ABS_RETURN": 0.12,
    "BASKET_MIN_MEMBER_WEIGHT": 0.95,
    "f2_variant": "F2-A",
    "EXIT_DEADLINE_N_MARKET_SYMBOL": 100,
    "EXIT_DEADLINE_N_SECTOR": 150,
    "CHECKPOINTS_MARKET_SYMBOL": (30, 60, 100, 150, 250, 400),
    "CHECKPOINTS_SECTOR": (150, 250, 400),
    "REPLAY_CHECKPOINT_COUNT": 2,
    "ALPHA_FAMILY": 0.04,
    "M_EFF_FLOOR": 9,
    "MIN_MEAN_RECALL": 0.34,
    "MIN_COVERAGE": 0.85,
    "VOID_RATE_W_THRESHOLD": 0.04,
    "BOOTSTRAP_RESAMPLES": 20_000,
    "BOOTSTRAP_BLOCK_LEN": 5,
    "BOOTSTRAP_BLOCK_LEN_ALTERNATIVES": (2, 6, 8),
}

#: The constants FL-31, FL-36 and FL-37 name (provisional names).
FL31_FIELDS = ("EXIT_DEADLINE_N_MARKET_SYMBOL", "EXIT_DEADLINE_N_SECTOR")
FL36_FIELDS = (
    "CHECKPOINTS_MARKET_SYMBOL",
    "CHECKPOINTS_SECTOR",
    "REPLAY_CHECKPOINT_COUNT",
    "ALPHA_FAMILY",
    "M_EFF_FLOOR",
    "MIN_MEAN_RECALL",
    "MIN_COVERAGE",
    "VOID_RATE_W_THRESHOLD",
    "BOOTSTRAP_RESAMPLES",
    "BOOTSTRAP_BLOCK_LEN",
    "BOOTSTRAP_BLOCK_LEN_ALTERNATIVES",
)
FL37_FIELDS = ("f2_variant",)
#: D-1 named constants and the three D-14 fields.
D1_D14_FIELDS = (
    "BASKET_MIN_MEMBER_WEIGHT",
    "K3",
    "K5",
    "EPS",
    "SIGMA_MIN_VALID",
    "SIGMA_FLOOR",
    "BASKET_EXCLUSION_REASON_ORDER",
    "SPLIT_SUSPECT_ABS_RETURN",
    "f2_variant",
    "c8_decision_ref",
    "c8_decision_sha256",
)


#: For each non-logic field, a different but valid value (logic hash must stay).
NON_LOGIC_CHANGES: dict[str, Any] = {
    "definition_version": "dirdef-v1.1",
    "description": "reworded description",
    "c8_decision_ref": "work/decisions/c8-moved.md",
    "c8_decision_sha256": "1" * 64,
}


def _canonical(payload: object) -> str:
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expected_hash(definition: DirectionDefinition) -> str:
    """The logic hash recomputed here from its definition (D-10 point 1), not via app code."""
    payload = {
        name: definition.model_dump(mode="json")[name]
        for name in DirectionDefinition.model_fields
        if name
        not in {"definition_version", "description", "c8_decision_ref", "c8_decision_sha256"}
    }
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- Type -----------------------------------------------------------------------------


def test_the_type_works_as_band_definition() -> None:
    definition = make_definition()
    band = {"K_h": 0.43, "EPS": 1e-12, "sigma_d": 0.01, "valid_returns": 60}
    assert labeled_snapshot_violations(band, horizon=5, definition=definition) == ()
    assert _AS_BAND.k_for(3) == 0.43


@pytest.mark.parametrize(("horizon", "field"), [(3, "K3"), (5, "K5")])
def test_k_for_reads_the_horizon_constant(horizon: int, field: str) -> None:
    definition = make_definition(**{field: 0.7})
    assert definition.k_for(horizon) == 0.7


@pytest.mark.parametrize("horizon", [1, 4, 10, True])
def test_k_for_refuses_other_horizons(horizon: int) -> None:
    with pytest.raises(ValueError):
        make_definition().k_for(horizon)


@pytest.mark.parametrize("name", D1_D14_FIELDS + FL31_FIELDS + FL36_FIELDS + FL37_FIELDS)
def test_the_named_constant_is_a_field(name: str) -> None:
    assert name in DirectionDefinition.model_fields


def test_no_field_has_a_default() -> None:
    assert [
        name for name, f in DirectionDefinition.model_fields.items() if not f.is_required()
    ] == []


def test_the_definition_is_frozen() -> None:
    definition = make_definition()
    with pytest.raises(ValidationError):
        setattr(definition, "K3", 0.5)  # noqa: B010


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"unknown": 1}, id="extra-key"),
        pytest.param({"K3": "0.43"}, id="string-for-float"),
        pytest.param({"SIGMA_MIN_VALID": True}, id="bool-for-int"),
        pytest.param({"SIGMA_MIN_VALID": 55.0}, id="float-for-int"),
        pytest.param({"CHECKPOINTS_SECTOR": [150, 250, 500]}, id="list-for-tuple"),
        pytest.param({"definition_version": "dirdef-1.0"}, id="version-pattern"),
        pytest.param({"definition_version": "dirdef-v1.0.0"}, id="version-patch"),
        pytest.param({"description": ""}, id="empty-description"),
        pytest.param({"K3": 0.0}, id="k-zero"),
        pytest.param({"K5": math.nan}, id="k-nan"),
        pytest.param({"EPS": math.inf}, id="eps-inf"),
        pytest.param({"SIGMA_FLOOR": -0.001}, id="floor-negative"),
        pytest.param({"SIGMA_MIN_VALID": 1}, id="min-valid-below-two"),
        pytest.param({"SPLIT_SUSPECT_ABS_RETURN": 1.0}, id="split-not-below-one"),
        pytest.param({"BASKET_MIN_MEMBER_WEIGHT": 0.0}, id="basket-weight-zero"),
        pytest.param({"BASKET_MIN_MEMBER_WEIGHT": 0.8999}, id="basket-weight-below-floor"),
        pytest.param({"BASKET_MIN_MEMBER_WEIGHT": 1.1}, id="basket-weight-above-one"),
        pytest.param({"BASKET_MIN_MEMBER_WEIGHT": math.nan}, id="basket-weight-nan"),
        pytest.param({"BASKET_EXCLUSION_REASON_ORDER": ()}, id="basket-empty"),
        pytest.param(
            {"BASKET_EXCLUSION_REASON_ORDER": ("dividend_factor_unusable",) * 2},
            id="basket-repeat",
        ),
        pytest.param({"BASKET_EXCLUSION_REASON_ORDER": ("other",)}, id="basket-unknown"),
        pytest.param({"f2_variant": "F2-C"}, id="f2-unknown"),
        pytest.param({"c8_decision_ref": ""}, id="ref-empty"),
        pytest.param({"c8_decision_ref": "/abs/c8.md"}, id="ref-absolute"),
        pytest.param({"c8_decision_ref": "work/../c8.md"}, id="ref-dotdot"),
        pytest.param({"c8_decision_ref": "work//c8.md"}, id="ref-empty-part"),
        pytest.param({"c8_decision_ref": "work\\c8.md"}, id="ref-backslash"),
        pytest.param({"c8_decision_sha256": "A" * 64}, id="sha-upper"),
        pytest.param({"c8_decision_sha256": "0" * 63}, id="sha-short"),
        pytest.param({"CHECKPOINTS_MARKET_SYMBOL": (60, 30, 150)}, id="checkpoints-order"),
        pytest.param({"CHECKPOINTS_SECTOR": (150, 150, 250)}, id="checkpoints-repeat"),
        pytest.param({"CHECKPOINTS_SECTOR": ()}, id="checkpoints-empty"),
        pytest.param({"CHECKPOINTS_SECTOR": (0, 250)}, id="checkpoint-zero"),
        pytest.param({"EXIT_DEADLINE_N_MARKET_SYMBOL": 120}, id="deadline-not-checkpoint"),
        pytest.param({"EXIT_DEADLINE_N_SECTOR": 100}, id="sector-deadline-not-checkpoint"),
        pytest.param({"BOOTSTRAP_BLOCK_LEN_ALTERNATIVES": (2, 4)}, id="block-repeat"),
        pytest.param({"BOOTSTRAP_BLOCK_LEN_ALTERNATIVES": (8, 2)}, id="block-order"),
        pytest.param({"ALPHA_FAMILY": 1.0}, id="alpha-one"),
        pytest.param({"MIN_COVERAGE": 0.0}, id="coverage-zero"),
        pytest.param({"M_EFF_FLOOR": 0}, id="floor-zero"),
        pytest.param({"BOOTSTRAP_RESAMPLES": 0}, id="resamples-zero"),
    ],
)
def test_malformed_definitions_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DirectionDefinition.model_validate(definition_data(**overrides))


def test_a_missing_field_is_refused() -> None:
    data = definition_data()
    del data["f2_variant"]
    with pytest.raises(ValidationError):
        DirectionDefinition.model_validate(data)


# --- Construction guards ---------------------------------------------------------------


def test_model_construct_raises() -> None:
    with pytest.raises(TypeError, match="model_construct"):
        DirectionDefinition.model_construct(**definition_data())


@pytest.mark.parametrize("update", [{"K3": 9.0}, {}])
def test_model_copy_with_update_raises(update: dict[str, Any]) -> None:
    with pytest.raises(TypeError, match="model_copy"):
        make_definition().model_copy(update=update)


@pytest.mark.parametrize("deep", [False, True])
def test_plain_model_copy_still_works(deep: bool) -> None:
    definition = make_definition()
    copy = definition.model_copy(deep=deep)
    assert copy == definition
    assert copy is not definition


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"update": {"K3": 9.0}}, id="update"),
        pytest.param({"update": {}}, id="empty-update"),
        pytest.param({"exclude": {"K3"}}, id="exclude"),
        pytest.param({"include": {"K3"}}, id="include"),
    ],
)
def test_the_deprecated_copy_with_arguments_raises(kwargs: dict[str, Any]) -> None:
    # qa M-1: BaseModel.copy(update=...) would build an unvalidated object.
    with pytest.raises(TypeError, match="copy"):
        make_definition().copy(**kwargs)


@pytest.mark.parametrize("deep", [False, True])
def test_the_plain_deprecated_copy_is_an_exact_copy(deep: bool) -> None:
    definition = make_definition()
    assert definition.copy(deep=deep) == definition


# --- Logic hash ------------------------------------------------------------------------


def test_the_logic_hash_follows_the_canonical_form() -> None:
    definition = make_definition()
    assert definition_logic_sha256(definition) == _expected_hash(definition)
    assert definition_logic_sha256(make_definition()) == definition_logic_sha256(definition)


def test_the_non_logic_fields_are_version_description_and_c8_provenance() -> None:
    assert DEFINITION_NON_LOGIC_FIELDS == frozenset(
        {"definition_version", "description", "c8_decision_ref", "c8_decision_sha256"}
    )


def test_every_field_has_exactly_one_changed_value_cell() -> None:
    # A field added to the type must land in one of the two tables (and so in the hash cells).
    assert set(NON_LOGIC_CHANGES) == DEFINITION_NON_LOGIC_FIELDS
    assert (
        set(CHANGED_VALUES) == set(DirectionDefinition.model_fields) - DEFINITION_NON_LOGIC_FIELDS
    )


def test_the_full_hash_follows_the_canonical_form() -> None:
    definition = make_definition()
    assert definition_sha256(definition) == _canonical(definition.model_dump(mode="json"))
    assert definition_sha256(definition) != definition_logic_sha256(definition)


@pytest.mark.parametrize("name", sorted(NON_LOGIC_CHANGES))
def test_a_non_logic_change_keeps_the_logic_hash_and_moves_the_full_hash(name: str) -> None:
    # B2D-1f; FL-33 pure part: same logic hash, so registering it again collides on UNIQUE.
    changed = make_definition(**{name: NON_LOGIC_CHANGES[name]})
    assert definition_logic_sha256(changed) == definition_logic_sha256(make_definition())
    assert definition_sha256(changed) != definition_sha256(make_definition())


@pytest.mark.parametrize("name", sorted(CHANGED_VALUES))
def test_changing_a_constant_changes_the_logic_hash(name: str) -> None:
    # FL-31 / FL-36 / FL-37 in B2: the named constants are inside the hash.
    changed = make_definition(**{name: CHANGED_VALUES[name]})
    assert definition_logic_sha256(changed) != definition_logic_sha256(make_definition())
    assert definition_sha256(changed) != definition_sha256(make_definition())


def test_an_int_given_for_a_float_hashes_like_the_float() -> None:
    assert definition_logic_sha256(make_definition(K3=1)) == definition_logic_sha256(
        make_definition(K3=1.0)
    )


@pytest.mark.parametrize("weight", [0.9, 0.95, 1.0, 1])
def test_basket_weights_from_the_floor_to_one_are_allowed(weight: float) -> None:
    # Risk R-1: [0.90, 1]; 0.8999 is refused above.
    assert make_definition(BASKET_MIN_MEMBER_WEIGHT=weight).BASKET_MIN_MEMBER_WEIGHT == weight
