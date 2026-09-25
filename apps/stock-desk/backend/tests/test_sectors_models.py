"""D-10 response types: exact field names, forbidden names, structural rules.

* Field names are pinned to ADR-0012 D-10, the only naming authority.
* C-26: no response field name contains a forbidden term. ``corporate_action``
  is D-10's own compound (category ③, 公司行動) and is the one sanctioned
  occurrence of ``action``; see the test docstring.
* The response validators enforce C-23 (not_evaluated -> no A-class objects),
  C-40 (pit_gaps iff NE-1), C-42/C-43 (insufficient -> reason set, sectors and
  excluded empty, no historical objects; T-27 backend) and C-44
  (excluded_reason_counts iff no_sector_computable; T-28 backend).
"""

from __future__ import annotations

import re
from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.api.common import DataMeta
from app.api.common import PayloadStatus as ApiPayloadStatus
from app.sectors import models
from app.sectors.models import (
    Accumulation,
    ConstituentItem,
    Coverage,
    ExcludedReasonCounts,
    ExcludedSector,
    HistoricalStat,
    SectorItem,
    SectorMomentumResponse,
)

Response = SectorMomentumResponse[DataMeta]

D10_RESPONSE_FIELDS = [
    "market",
    "status",
    "insufficient_reason",
    "reason",
    "method_version",
    "lookback_days",
    "holding_days",
    "data_as_of",
    "market_scope",
    "benchmark",
    "data_source",
    "coverage",
    "min_constituents",
    "sector_coverage_threshold",
    "overall_coverage_threshold",
    "computable_ratio",
    "computable_ratio_min",
    "computable_ratio_pct_display",
    "completeness_pct_display",
    "market_expected_count",
    "market_missing_count",
    "market_ex_date_excluded_count",
    "market_corporate_action_excluded_count",
    "market_ex_date_excluded_ratio",
    "ex_date_tag_ratio_min",
    "ex_date_tag",
    "excluded_reason_counts",
    "headline_count",
    "sectors",
    "excluded_sectors",
    "gate_status",
    "not_evaluated_reason",
    "not_evaluated_reasons",
    "pit_gaps",
    "accumulation",
    "historical_stat",
    "gate_checks",
    "fee_verified_on",
    "disclosures",
    "data",
    "as_of",
]


def test_response_fields_are_exactly_d10() -> None:
    assert list(Response.model_fields) == D10_RESPONSE_FIELDS


def test_nested_fields_are_exactly_d10() -> None:
    assert list(Coverage.model_fields) == [
        "expected_count",
        "calculation_count",
        "missing_count",
        "ex_date_excluded_count",
        "corporate_action_excluded_count",
        "suspended_count",
        "coverage_ratio",
        "completeness_ratio",
    ]
    assert list(ConstituentItem.model_fields) == ["symbol", "name", "return_L", "held"]
    assert list(SectorItem.model_fields) == [
        "rank",
        "sector_code",
        "sector_name",
        "sector_return_L",
        "benchmark_return_L",
        "rel_return_L",
        "up_count",
        "constituent_count",
        "turnover_value_ratio_5_20",
        "reference_taiex_return_L",
        "coverage",
        "top_contributor_share",
        "single_stock_dominated",
        "constituents",
    ]
    assert list(ExcludedSector.model_fields) == [
        "sector_code",
        "sector_name",
        "reason_code",
        "computable_count",
        "expected_count",
        "coverage",
    ]
    assert list(ExcludedReasonCounts.model_fields) == [
        "too_few_members",
        "low_coverage",
        "ex_dividend_exclusion",
    ]
    assert list(Accumulation.model_fields) == [
        "accumulated_samples",
        "accumulation_start",
        "required_samples",
    ]
    assert list(HistoricalStat.model_fields) == [
        "rank_scope",
        "method_version",
        "m_at_evaluation",
        "sample_count",
        "effective_sample_count",
        "beat_count_net",
        "beat_count_gross",
        "base_rate_net",
        "base_rate_gross",
        "ci_low_net",
        "ci_high_net",
        "bootstrap_low_net",
        "bootstrap_high_net",
        "delta_real",
        "delta_shuffle",
        "benchmark",
        "sample_start",
        "sample_end",
        "stats_as_of",
        "computed_at",
        "run_id",
    ]


def test_literals_are_exactly_d10() -> None:
    assert get_args(models.PitGap) == (
        "pit_universe",
        "pit_classification",
        "pit_ex_dividend",
        "de5_unverified",
    )
    assert get_args(models.ReasonCode) == (
        "unranked_category",
        "too_few_members",
        "low_coverage",
        "ex_dividend_exclusion",
    )
    assert get_args(models.GateStatus) == ("passed", "failed", "not_evaluated")
    assert get_args(models.NotEvaluatedReason)[-1] == "pending_review"


def test_payload_status_matches_the_shared_api_literal() -> None:
    assert get_args(models.PayloadStatus) == get_args(ApiPayloadStatus)


def _all_field_names(model: type[BaseModel], seen: set[type[BaseModel]] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return set()
    seen.add(model)
    names: set[str] = set()
    for name, info in model.model_fields.items():
        names.add(name)
        for arg in _flatten(info.annotation):
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                names |= _all_field_names(arg, seen)
    return names


def _flatten(annotation: Any) -> list[Any]:
    args = get_args(annotation)
    if not args:
        return [annotation]
    out: list[Any] = []
    for arg in args:
        out.extend(_flatten(arg))
    return out


FORBIDDEN = ("volume", "hit_rate", "win_rate", "score", "rating", "confidence", "action")
#: ``corporate_action`` is ADR-0012 D-10's own name for exclusion category ③
#: (公司行動 insurance). C-26 targets the advice engine's ``action`` output; the
#: two D-10 fields carrying the compound are the only sanctioned occurrences.
SANCTIONED_COMPOUNDS = ("corporate_action",)


def test_no_forbidden_term_in_any_response_field_name() -> None:
    names = _all_field_names(Response)
    assert "corporate_action_excluded_count" in names  # the scan really recurses
    for name in names:
        cleaned = name
        for compound in SANCTIONED_COMPOUNDS:
            cleaned = cleaned.replace(compound, "")
        for term in FORBIDDEN:
            assert term not in cleaned.lower(), f"{name} contains {term}"


def test_the_forbidden_scan_has_teeth() -> None:
    class Leaky(BaseModel):
        sector_score: int

    names = _all_field_names(Leaky)
    assert any(term in name for name in names for term in FORBIDDEN)


def test_openapi_schema_carries_the_shared_data_meta() -> None:
    schema = Response.model_json_schema()
    assert schema["properties"]["data"] == {"$ref": "#/$defs/DataMeta"}
    assert not re.search(r"\bscore\b|\brating\b", str(sorted(schema["properties"])))


# ---------------------------------------------------------------------------
# structural validators
# ---------------------------------------------------------------------------

COVERAGE = Coverage(
    expected_count=10,
    calculation_count=9,
    missing_count=1,
    ex_date_excluded_count=0,
    corporate_action_excluded_count=0,
    suspended_count=None,
    coverage_ratio=0.9,
    completeness_ratio=0.9,
)


def _sector(rank: int = 1) -> SectorItem:
    return SectorItem(
        rank=rank,
        sector_code="24",
        sector_name="半導體業",
        sector_return_L=0.03,
        benchmark_return_L=0.01,
        rel_return_L=0.02,
        up_count=6,
        constituent_count=9,
        turnover_value_ratio_5_20=1.2,
        reference_taiex_return_L=None,
        coverage=COVERAGE,
        top_contributor_share=0.2,
        single_stock_dominated=False,
        constituents=[
            ConstituentItem(symbol=s, name=s, return_L=r, held=None)
            for s, r in (("2330", 0.05), ("2303", 0.04), ("2344", -0.02))
        ],
    )


def _historical() -> HistoricalStat:
    return HistoricalStat(
        rank_scope="rank_1",
        method_version="sector-rel-v1.0-L5-H5",
        m_at_evaluation=1,
        sample_count=160,
        effective_sample_count=70.0,
        beat_count_net=100,
        beat_count_gross=110,
        base_rate_net=0.5,
        base_rate_gross=0.52,
        ci_low_net=0.55,
        ci_high_net=0.7,
        bootstrap_low_net=0.55,
        bootstrap_high_net=0.7,
        delta_real=12.5,
        delta_shuffle=2.0,
        benchmark="equal_weight_market",
        sample_start="2026-10-01",
        sample_end="2029-11-01",
        stats_as_of="2029-11-01",
        computed_at="2029-11-02T10:00:00+00:00",
        run_id="run-1",
    )


def _payload(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "market": "TW",
        "status": "ok",
        "insufficient_reason": None,
        "reason": None,
        "method_version": "sector-rel-v1.0-L5-H5",
        "lookback_days": 5,
        "holding_days": 5,
        "data_as_of": "2026-10-01",
        "market_scope": "twse_only",
        "benchmark": "equal_weight_market",
        "data_source": "twse_snapshot",
        "coverage": COVERAGE,
        "min_constituents": 5,
        "sector_coverage_threshold": 0.9,
        "overall_coverage_threshold": 0.98,
        "computable_ratio": 0.9,
        "computable_ratio_min": 0.8,
        "computable_ratio_pct_display": 90.0,
        "completeness_pct_display": 90.0,
        "market_expected_count": 10,
        "market_missing_count": 1,
        "market_ex_date_excluded_count": 0,
        "market_corporate_action_excluded_count": 0,
        "market_ex_date_excluded_ratio": 0.0,
        "ex_date_tag_ratio_min": 0.05,
        "ex_date_tag": False,
        "excluded_reason_counts": None,
        "headline_count": 3,
        "sectors": [_sector()],
        "excluded_sectors": [],
        "gate_status": "not_evaluated",
        "not_evaluated_reason": "accumulating",
        "not_evaluated_reasons": ["accumulating", "fee_unverified"],
        "pit_gaps": [],
        "accumulation": Accumulation(
            accumulated_samples=3, accumulation_start="2026-09-28", required_samples=150
        ),
        "historical_stat": None,
        "gate_checks": None,
        "fee_verified_on": None,
        "disclosures": [],
        "data": DataMeta(
            status="cached_stale",
            source="twse_snapshot",
            staleness_minutes=30,
            is_within_ttl=True,
            bar_count=6,
            first_bar_date=None,
            last_bar_date="2026-10-01",
            trading_days_behind=0,
            reason=None,
        ),
        "as_of": "2026-10-01T10:00:00+00:00",
    }
    base.update(kw)
    return base


def test_a_well_formed_payload_validates() -> None:
    Response(**_payload())
    Response(
        **_payload(
            gate_status="passed",
            not_evaluated_reason=None,
            not_evaluated_reasons=[],
            historical_stat=_historical(),
            gate_checks=[],
        )
    )


@pytest.mark.parametrize(
    "overrides",
    [
        # C-23: not_evaluated carries no A-class object.
        {"historical_stat": _historical()},
        {"gate_checks": []},
        # reason iff not_evaluated
        {"not_evaluated_reason": None},
        {"gate_status": "passed", "not_evaluated_reason": None},
        # C-29: demo data reports demo_data.
        {"data_source": "demo_synthetic"},
        # C-40: pit_gaps iff NE-1.
        {"pit_gaps": ["de5_unverified"]},
        {"not_evaluated_reasons": ["pit_history_missing", "accumulating"], "pit_gaps": []},
        # C-42: status and reason agree.
        {"status": "insufficient_data"},
        {"insufficient_reason": "computable_ratio_low"},
        # C-44: n1/n2/n3 only for no_sector_computable.
        {
            "excluded_reason_counts": ExcludedReasonCounts(
                too_few_members=1, low_coverage=0, ex_dividend_exclusion=0
            )
        },
        # C-28: ranks 1..n.
        {"sectors": [_sector(rank=2)]},
    ],
)
def test_structural_violations_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Response(**_payload(**overrides))


def _insufficient(reason: str, **kw: Any) -> dict[str, Any]:
    counts = (
        ExcludedReasonCounts(too_few_members=2, low_coverage=1, ex_dividend_exclusion=0)
        if reason == "no_sector_computable"
        else None
    )
    fields: dict[str, Any] = {
        "status": "insufficient_data",
        "insufficient_reason": reason,
        "sectors": [],
        "excluded_sectors": [],
        "excluded_reason_counts": counts,
    }
    fields.update(kw)
    return _payload(**fields)


@pytest.mark.parametrize(
    "reason",
    [
        "as_of_unknown",
        "ex_dividend_feed_gap",
        "overall_completeness_low",
        "computable_ratio_low",
        "no_sector_computable",
    ],
)
def test_insufficient_payloads_carry_no_sectors_and_no_history(reason: str) -> None:
    ok = Response(**_insufficient(reason))
    assert ok.sectors == [] and ok.excluded_sectors == []
    assert ok.historical_stat is None and ok.gate_checks is None
    assert ok.data_as_of == "2026-10-01" and ok.data_source == "twse_snapshot"
    with pytest.raises(ValidationError):
        Response(**_insufficient(reason, sectors=[_sector()]))
    with pytest.raises(ValidationError):
        Response(
            **_insufficient(
                reason,
                excluded_sectors=[
                    ExcludedSector(
                        sector_code="01",
                        sector_name="水泥工業",
                        reason_code="too_few_members",
                        computable_count=3,
                        expected_count=3,
                        coverage=Coverage(
                            expected_count=3,
                            calculation_count=3,
                            missing_count=0,
                            ex_date_excluded_count=0,
                            corporate_action_excluded_count=0,
                            suspended_count=None,
                            coverage_ratio=1.0,
                            completeness_ratio=1.0,
                        ),
                    )
                ],
            )
        )
    passed: dict[str, Any] = {
        "gate_status": "passed",
        "not_evaluated_reason": None,
        "not_evaluated_reasons": [],
    }
    with pytest.raises(ValidationError):
        Response(**_insufficient(reason, historical_stat=_historical(), **passed))


def test_completeness_and_computable_fields_stay_separate() -> None:
    """C-44: ③ and ④ each have their own ratio display and threshold field."""
    payload = Response(
        **_insufficient(
            "computable_ratio_low",
            computable_ratio_pct_display=79.9,
            completeness_pct_display=99.0,
            computable_ratio_min=0.8,
            overall_coverage_threshold=0.98,
        )
    )
    assert payload.computable_ratio_pct_display != payload.completeness_pct_display
    assert payload.computable_ratio_min != payload.overall_coverage_threshold


def test_coverage_counts_must_add_up() -> None:
    with pytest.raises(ValidationError):
        Coverage(
            expected_count=10,
            calculation_count=10,
            missing_count=1,
            ex_date_excluded_count=0,
            corporate_action_excluded_count=0,
            suspended_count=None,
            coverage_ratio=1.0,
            completeness_ratio=0.9,
        )


def test_a_ranked_sector_lists_exactly_three_constituents() -> None:
    with pytest.raises(ValidationError):
        SectorItem(**{**_sector().model_dump(), "constituents": _sector().constituents[:2]})
    with pytest.raises(ValidationError):
        SectorItem(**{**_sector().model_dump(), "constituent_count": 8})
