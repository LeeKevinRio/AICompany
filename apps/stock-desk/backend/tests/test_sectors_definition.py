"""T-12 / C-16: one definition, version string locked to L and H, thresholds tighten only."""

from __future__ import annotations

import dataclasses

import pytest

from app.sectors.definition import (
    SECTOR_MOMENTUM_V1,
    CoverageRules,
    GateRules,
    SectorMomentumDefinition,
    UniverseRules,
)


def test_v1_is_the_frozen_methodology_values() -> None:
    v1 = SECTOR_MOMENTUM_V1
    assert v1.method_version == "sector-rel-v1.0-L5-H5"
    assert (v1.lookback_days, v1.holding_days) == (5, 5)
    assert v1.market_scope == "twse_only"
    assert v1.ranking_signal == "rel_return_L"
    assert v1.benchmark == "equal_weight_market"
    assert v1.ex_dividend_lookback == "exclude_window"
    assert v1.constituent_rule == "top2_bottom1"
    assert v1.open_limit_up_factor == 1.095
    assert (
        v1.coverage.min_constituents,
        v1.coverage.sector_coverage_threshold,
        v1.coverage.overall_coverage_threshold,
        v1.coverage.computable_ratio_min,
        v1.coverage.ex_date_tag_ratio_min,
    ) == (5, 0.90, 0.98, 0.80, 0.05)
    assert (
        v1.universe.min_listing_sessions,
        v1.universe.liquidity_window_sessions,
        v1.universe.min_median_traded_value,
        v1.universe.min_traded_sessions,
    ) == (60, 20, 10_000_000.0, 18)
    assert v1.universe.unranked_sector_codes == {"20"}
    assert v1.universe.excluded_sector_codes == {"91"}
    gate = v1.gate
    assert (gate.min_samples, gate.min_effective_samples) == (150, 60.0)
    assert (gate.base_rate_floor, gate.min_effect, gate.alpha) == (0.5, 0.05, 0.05)
    assert gate.stale_after_sessions == 20
    assert (gate.bootstrap_block_length, gate.bootstrap_draws) == (4, 10_000)


def test_a_version_string_that_disagrees_with_l_or_h_fails() -> None:
    with pytest.raises(ValueError, match="L20"):
        SectorMomentumDefinition(
            method_version="sector-rel-v1.1-L20-H5", lookback_days=5, holding_days=5
        )
    with pytest.raises(ValueError, match="H10"):
        SectorMomentumDefinition(
            method_version="sector-rel-v1.1-L5-H10", lookback_days=5, holding_days=5
        )
    with pytest.raises(ValueError, match="must look like"):
        SectorMomentumDefinition(method_version="v1-L5-H5", lookback_days=5, holding_days=5)


def test_l_equal_10_fails() -> None:
    with pytest.raises(ValueError, match="lookback_days"):
        SectorMomentumDefinition(
            method_version="sector-rel-v1.1-L10-H5",
            lookback_days=10,  # type: ignore[arg-type]
            holding_days=5,
        )


def test_l_20_with_h_5_is_a_valid_separate_version() -> None:
    v = SectorMomentumDefinition(
        method_version="sector-rel-v1.1-L20-H5", lookback_days=20, holding_days=5
    )
    assert (v.lookback_days, v.holding_days) == (20, 5)


def test_frozen_family_fields_cannot_be_changed() -> None:
    with pytest.raises(ValueError, match="benchmark"):
        dataclasses.replace(SECTOR_MOMENTUM_V1, benchmark="taiex")  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        SECTOR_MOMENTUM_V1.lookback_days = 20  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (CoverageRules, {"min_constituents": 3}),
        (CoverageRules, {"sector_coverage_threshold": 0.85}),
        (CoverageRules, {"overall_coverage_threshold": 0.95}),
        (CoverageRules, {"computable_ratio_min": 0.75}),
        (CoverageRules, {"ex_date_tag_ratio_min": 0.10}),
        (GateRules, {"min_samples": 100}),
        (GateRules, {"min_effective_samples": 30}),
        (GateRules, {"base_rate_floor": 0.4}),
        (GateRules, {"min_effect": 0.01}),
        (GateRules, {"alpha": 0.10}),
        (GateRules, {"stale_after_sessions": 30}),
        (GateRules, {"leak_margin": 0.1}),
        (UniverseRules, {"min_listing_sessions": 20}),
        (UniverseRules, {"min_median_traded_value": 5_000_000.0}),
        (UniverseRules, {"min_traded_sessions": 10}),
    ],
)
def test_thresholds_may_only_be_tightened(factory: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        factory(**kwargs)


def test_tightening_is_allowed() -> None:
    CoverageRules(computable_ratio_min=0.85, sector_coverage_threshold=0.95)
    GateRules(min_samples=200, alpha=0.01)


def test_alpha_over_m_drives_the_levels() -> None:
    gate = SECTOR_MOMENTUM_V1.gate
    assert gate.significance(1) == 0.05
    assert gate.significance(2) == 0.025
    assert gate.confidence_level(2) == 0.975
    with pytest.raises(ValueError):
        gate.significance(0)
