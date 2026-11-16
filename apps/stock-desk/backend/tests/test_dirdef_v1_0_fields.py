"""``dirdef-v1.0`` fields against the freeze pack G7 table (ADR-0030 D-10; TA G5 notes).

* the G7 rows are exactly the ``DirectionDefinition`` fields; the D-NL rows are
  exactly :data:`DEFINITION_NON_LOGIC_FIELDS`, every other row is a logic field
  (TA G5 note: the sets equal the quant table's columns);
* the G7 values validate (``tests.dirdef_helpers.DIRDEF_V1_0_G7``; the two C-8
  provenance fields are test stand-ins until the CG-2 registration batch lands
  the C-8 decision record);
* ``N_MIN``, ``K_c`` and alpha* each come from one function (G7 "不設欄位、由程式導出");
* the registered ``dirdef-v1.0`` and the two rule sets are exactly the CG-2 ones
  (their hashes are pinned in ``tests/test_cg2_registration_values.py``);
* the two user-facing strings (``description``, ``MARKET_PRICE_INDEX_DEVIATION``)
  hold no banned phrase after NFKC and whitespace removal (freeze pack 4.3);
* TA SP-A ruling (2026-11-15): ``name`` stays inside ``rules_logic_sha256``, so an
  edit of a rule's ``name`` alone changes that hash.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from app.advice.loader import BANNED_PHRASES
from app.dirdef.definition import (
    DEFINITION_NON_LOGIC_FIELDS,
    DirectionDefinition,
    alpha_star,
    market_checkpoint_count,
    n_min,
)
from app.dirdef.registry import PUBLISHED_DIRECTION_DEFINITIONS, PUBLISHED_RULESETS
from app.dirdef.rules import (
    BANNED_PHRASES_CONTEXT_KEY,
    RULE_TEXT_FIELDS,
    OutlookRuleSet,
    rules_logic_sha256,
)
from app.forecast.definitions import squeeze
from tests.dirdef_helpers import DIRDEF_V1_0_G7, G7_NON_LOGIC_ROWS, dirdef_v1_0

RULES_DIR = Path(__file__).resolve().parent.parent / "app" / "outlook" / "rules"
CONTEXT = {BANNED_PHRASES_CONTEXT_KEY: BANNED_PHRASES}


def _squeezed(text: str) -> str:
    return squeeze(text)  # the one comparison form (qa batch 4 follow-up 4)


def test_the_g7_rows_are_exactly_the_definition_fields() -> None:
    assert set(DIRDEF_V1_0_G7) == set(DirectionDefinition.model_fields)
    assert len(DIRDEF_V1_0_G7) == 34


def test_the_g7_non_logic_rows_are_the_non_logic_fields() -> None:
    assert G7_NON_LOGIC_ROWS == DEFINITION_NON_LOGIC_FIELDS
    logic = set(DirectionDefinition.model_fields) - DEFINITION_NON_LOGIC_FIELDS
    assert {"SIGMA_WINDOW", "B2_WINDOW", "B2_MIN_REALIZED", "MAJORITY_TIE_ORDER"} <= logic
    assert {"NEFF_BLOCK_LEN3", "NEFF_BLOCK_LEN5", "SEASON_MONTHS", "f2_variant"} <= logic


def test_the_g7_values_validate() -> None:
    definition = dirdef_v1_0()
    assert definition.definition_version == "dirdef-v1.0"
    assert definition.f2_variant == "F2-B"
    assert definition.SIGMA_WINDOW == 60
    assert definition.B2_WINDOW == 250 and definition.B2_MIN_REALIZED == 120
    assert definition.MAJORITY_TIE_ORDER == ("range", "bullish", "bearish")
    assert definition.SEASON_MONTHS == (6, 7, 8, 9)
    assert (definition.NEFF_BLOCK_LEN3, definition.NEFF_BLOCK_LEN5) == (3, 5)
    assert definition.MIN_MEAN_RECALL == 1 / 3


def test_n_min_is_the_first_market_checkpoint() -> None:
    assert n_min(dirdef_v1_0()) == 30


def test_k_c_is_the_number_of_market_checkpoints() -> None:
    assert market_checkpoint_count(dirdef_v1_0()) == 6


def test_alpha_star_is_the_family_level_over_m_eff_times_k_c() -> None:
    assert alpha_star(dirdef_v1_0(), m_eff=8) == 0.05 / 48


def test_alpha_star_refuses_a_bad_m_eff() -> None:
    for bad in (0, -1, True, 8.0):
        with pytest.raises(ValueError):
            alpha_star(dirdef_v1_0(), m_eff=bad)  # type: ignore[arg-type]


def test_cg2_registers_exactly_dirdef_v1_0_and_the_two_rule_sets() -> None:
    # The CG-2 registration batch registers dirdef-v1.0 and the market h3 / h5 rule sets.
    assert set(PUBLISHED_DIRECTION_DEFINITIONS) == {"dirdef-v1.0"}
    assert set(PUBLISHED_RULESETS) == {"outlook-market-v1.0-h3", "outlook-market-v1.0-h5"}


def test_the_two_user_facing_strings_hold_no_banned_phrase() -> None:
    assert len(BANNED_PHRASES) == 10
    for name in ("description", "MARKET_PRICE_INDEX_DEVIATION"):
        text = _squeezed(DIRDEF_V1_0_G7[name])
        hits = [p for p in BANNED_PHRASES if _squeezed(p) in text]
        assert hits == [], name


def test_rule_text_fields_leave_name_inside_the_logic_hash() -> None:
    # TA SP-A ruling 2026-11-15: ``name`` stays inside rules_logic_sha256 (the
    # stricter, fail-closed side); RULE_TEXT_FIELDS does not hold it.
    assert frozenset({"explanation", "counterargument"}) == RULE_TEXT_FIELDS
    assert "name" not in RULE_TEXT_FIELDS


@pytest.mark.parametrize("horizon", [3, 5])
def test_changing_only_a_rule_name_changes_rules_logic_sha256(horizon: int) -> None:
    # TA SP-A qa check: an edit of ``name`` alone moves the logic hash, while an
    # edit of a RULE_TEXT_FIELDS value alone does not.
    data = (RULES_DIR / f"h{horizon}.yaml").read_bytes()
    raw = yaml.safe_load(data)
    original = OutlookRuleSet.model_validate(raw, context=CONTEXT)
    renamed = copy.deepcopy(raw)
    renamed["rules"][0]["name"] = renamed["rules"][0]["name"] + " (renamed)"
    reworded = copy.deepcopy(raw)
    reworded["rules"][0]["explanation"] = reworded["rules"][0]["explanation"] + " (reworded)"
    logic = rules_logic_sha256(original)
    assert rules_logic_sha256(OutlookRuleSet.model_validate(renamed, context=CONTEXT)) != logic
    assert rules_logic_sha256(OutlookRuleSet.model_validate(reworded, context=CONTEXT)) == logic
