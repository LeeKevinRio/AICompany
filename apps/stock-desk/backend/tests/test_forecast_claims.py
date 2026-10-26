"""Claim id and m / m_eff pure functions (ADR-0027 D-10 points 2, 4; FL-28 m, FL-33 pure part).

The claim ids are the eight rows of pre-registration §12, written out here as
literals rather than recomputed. Registration, the CLI and the UNIQUE half of
FL-33 come with the store batch.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.forecast.claims import claim_id, count_m, m_eff
from tests.dirdef_helpers import make_definition

PREREG_CLAIMS = [
    (
        "market",
        3,
        "outlook-market-v1.0-h3",
        "forward",
        "market|h3|outlook-market-v1.0-h3|dirdef-v1.0|forward",
    ),
    (
        "market",
        5,
        "outlook-market-v1.0-h5",
        "forward",
        "market|h5|outlook-market-v1.0-h5|dirdef-v1.0|forward",
    ),
    (
        "sector_main",
        3,
        "outlook-sector_main-v1.0-h3",
        "forward",
        "sector_main|h3|outlook-sector_main-v1.0-h3|dirdef-v1.0|forward",
    ),
    (
        "sector_main",
        5,
        "outlook-sector_main-v1.0-h5",
        "forward",
        "sector_main|h5|outlook-sector_main-v1.0-h5|dirdef-v1.0|forward",
    ),
    (
        "symbol",
        3,
        "outlook-symbol-v1.0-h3",
        "forward",
        "symbol|h3|outlook-symbol-v1.0-h3|dirdef-v1.0|forward",
    ),
    (
        "symbol",
        5,
        "outlook-symbol-v1.0-h5",
        "forward",
        "symbol|h5|outlook-symbol-v1.0-h5|dirdef-v1.0|forward",
    ),
    (
        "market",
        3,
        "outlook-market-v1.0-h3",
        "replay",
        "market|h3|outlook-market-v1.0-h3|dirdef-v1.0|replay",
    ),
    (
        "market",
        5,
        "outlook-market-v1.0-h5",
        "replay",
        "market|h5|outlook-market-v1.0-h5|dirdef-v1.0|replay",
    ),
]


@pytest.mark.parametrize(
    ("scope_kind", "horizon", "rules_version", "kind", "expected"), PREREG_CLAIMS
)
def test_claim_ids_match_the_registration_table(
    scope_kind: Any, horizon: Any, rules_version: str, kind: Any, expected: str
) -> None:
    assert (
        claim_id(
            scope_kind=scope_kind,
            horizon=horizon,
            rules_version=rules_version,
            definition_version="dirdef-v1.0",
            kind=kind,
        )
        == expected
    )


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"scope_kind": "sector"}, id="scope-kind"),
        pytest.param({"horizon": 4}, id="horizon"),
        pytest.param({"horizon": True}, id="bool-horizon"),
        pytest.param({"kind": "on_demand"}, id="kind"),
        pytest.param({"rules_version": ""}, id="empty-rules-version"),
        pytest.param({"rules_version": "a|b"}, id="separator"),
        pytest.param({"rules_version": " v1"}, id="surrounding-space"),
        pytest.param({"rules_version": 1}, id="non-string-rules-version"),
        pytest.param({"definition_version": "v1.0"}, id="definition-version"),
        pytest.param({"definition_version": "dirdef-v1.0|x"}, id="definition-separator"),
    ],
)
def test_bad_claim_id_parts_are_refused(overrides: dict[str, Any]) -> None:
    parts: dict[str, Any] = {
        "scope_kind": "market",
        "horizon": 3,
        "rules_version": "outlook-market-v1.0-h3",
        "definition_version": "dirdef-v1.0",
        "kind": "forward",
    }
    parts.update(overrides)
    with pytest.raises(ValueError):
        claim_id(**parts)


def test_claim_id_takes_keywords_only() -> None:
    with pytest.raises(TypeError):
        claim_id("market", 3, "r", "dirdef-v1.0", "forward")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("values", "expected"),
    [([], 0), ([0, 0], 0), ([1, 0, 1, 1], 3), ([1] * 8, 8), ((v for v in (1, 1)), 2)],
)
def test_m_counts_the_rows_that_count(values: Any, expected: int) -> None:
    assert count_m(values) == expected


@pytest.mark.parametrize("bad", [2, -1, True, 1.0, None])
def test_m_refuses_values_other_than_zero_and_one(bad: Any) -> None:
    with pytest.raises(ValueError):
        count_m([1, bad])


@pytest.mark.parametrize(("m", "expected"), [(0, 8), (6, 8), (8, 8), (9, 9), (40, 40)])
def test_m_eff_is_m_floored_by_the_definition(m: int, expected: int) -> None:
    assert m_eff(m, definition=make_definition(M_EFF_FLOOR=8)) == expected


def test_m_eff_reads_the_floor_of_the_definition_passed_in() -> None:
    assert m_eff(6, definition=make_definition(M_EFF_FLOOR=10)) == 10


@pytest.mark.parametrize("bad", [-1, True, 1.5])
def test_m_eff_refuses_bad_m(bad: Any) -> None:
    with pytest.raises(ValueError):
        m_eff(bad, definition=make_definition())
