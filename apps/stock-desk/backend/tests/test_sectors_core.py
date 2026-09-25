"""Sector pure core: universe, calculation set, returns, ranking, constituents, coverage.

ADR-0012 tests covered here (backend halves):

* T-9  same set: R_g, 「上漲 k／n 家」 and the constituents all come from
  ``universe.calculation_set()``; teeth -- one extra name must be caught.
* T-12 turnover is descriptive: perturbing it leaves every rank unchanged.
* T-20 same set, exclusion attribution (three single cases + coexistence),
  thresholds echoed from the definition object, constituent invariant fault
  injection, C-18 feed coverage.
* T-23 computable ratio boundary, peak-season case, e - a - b - c identity,
  floor display (0.79999 -> 79.9).
* T-24 ex-date tag.
* T-28 backend: n1/n2/n3 add up to the rankable sectors.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
from collections.abc import Mapping, Sequence
from fractions import Fraction

import pytest

from app.data.panel import PointInTimePanel
from app.sectors import constituents, coverage, index, ranking, universe
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.ranking import SectorRanking
from app.sectors.universe import CalculationSet
from tests.sectors_helpers import Member, PanelBuilder, members, scenario, weekdays

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _core(
    sectors: Mapping[str, Sequence[Member]], **kwargs: object
) -> tuple[PointInTimePanel, CalculationSet, SectorRanking]:
    sc = scenario(sectors, **kwargs)  # type: ignore[arg-type]
    panel = sc.market.as_of(sc.t)
    calc = universe.calculation_set(panel, V1)
    return panel, calc, ranking.rank_sectors(calc, V1)


def assert_same_set(calc: CalculationSet, board: SectorRanking) -> None:
    """The qa assertion of risk §6.2 (a): three consumers, one set."""
    for row in board.ranked:
        members_set = calc.sector(row.sector_code).members
        assert row.members == members_set
        assert row.constituent_count == len(members_set) == row.coverage.calculation_count
        returns = {symbol: calc.member_returns[symbol] for symbol in row.members}
        assert row.up_count == sum(1 for value in returns.values() if value > 0)
        assert {item.symbol for item in row.constituents} <= members_set
        expected_return = math.fsum(returns[s] for s in sorted(returns)) / len(returns)
        assert row.sector_return == expected_return
        cov = row.coverage
        assert (
            cov.expected_count
            - cov.missing_count
            - cov.ex_date_excluded_count
            - cov.corporate_action_excluded_count
            == cov.calculation_count
        )


def _reason(board: SectorRanking, code: str) -> str | None:
    for row in board.excluded:
        if row.sector_code == code:
            return row.reason_code
    return None


# ---------------------------------------------------------------------------
# universe
# ---------------------------------------------------------------------------


def test_core_refuses_anything_but_a_point_in_time_view() -> None:
    sc = scenario({"01": members("11", 5)})
    with pytest.raises(TypeError, match="PointInTimePanel"):
        universe.calculation_set(sc.market, V1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="PointInTimePanel"):
        universe.eligible(sc.market.frames, V1)  # type: ignore[arg-type]


def test_code_91_is_out_entirely_and_code_20_is_benchmark_only() -> None:
    _, calc, board = _core({"01": members("11", 5), "20": members("20", 3), "91": members("91", 3)})
    codes = {sector.sector_code for sector in calc.sectors}
    assert "91" not in codes
    assert not any(symbol.startswith("91") for symbol in calc.market.expected)
    assert {"2000", "2001", "2002"} <= calc.market.members  # counted in B_EW
    assert _reason(board, "20") == "unranked_category"
    assert [row.sector_code for row in board.ranked] == ["01"]


def test_listing_age_liquidity_and_security_type_filter_the_expected_set() -> None:
    thin = Member("1190", traded_value=5_000_000.0)  # median NT$5m < NT$10m
    etf = Member("1191", security_type="etf")
    _, calc, _ = _core({"01": [*members("11", 5), thin, etf]})
    expected = calc.sector("01").expected
    assert "1190" not in expected
    assert "1191" not in expected
    assert len(expected) == 5

    # 59 sessions of history: every name is one session short of seasoned.
    _, young, _ = _core({"01": members("11", 5)}, n_sessions=59)
    assert young.sector("01").expected == frozenset()


def test_traded_days_below_18_of_20_are_illiquid() -> None:
    days = weekdays(70)
    builder = PanelBuilder()
    for day in days:
        bars = builder.run("bars", day)
        listing = builder.run("listing", day)
        classes = builder.run("classification", day)
        builder.run("dividend_announce", day)
        for i in range(6):
            symbol = f"110{i}"
            # 1100 is absent on 3 of the last 20 sessions: 17 traded days.
            if not (symbol == "1100" and day in days[-12:-9]):
                builder.bar(bars, day, symbol, 100.0, traded_value=2e8)
            builder.listed(listing, day, symbol)
            builder.classified(classes, day, symbol, "01", "水泥工業")
    calc = universe.calculation_set(builder.panel().as_of(days[-1]), V1)
    assert "1100" not in calc.sector("01").expected
    assert len(calc.sector("01").expected) == 5


# ---------------------------------------------------------------------------
# calculation set: attribution ① -> ② -> ③ (C-32, T-20, T-23)
# ---------------------------------------------------------------------------


def test_each_name_is_attributed_once_missing_then_ex_date_then_corporate_action() -> None:
    group = [
        Member("2400", missing=True, ex_date=True),  # ① wins over ②
        Member("2401", ex_date=True, jump=True),  # ② wins over ③
        Member("2402", jump=True),  # ③ alone
        Member("2403", missing=True),
        *members("245", 6),
    ]
    _, calc, _ = _core({"24": group})
    split = calc.sector("24").split
    assert split.missing == {"2400", "2403"}
    assert split.ex_date_excluded == {"2401"}
    assert split.corporate_action_excluded == {"2402"}
    assert len(split.expected) - len(split.missing) - len(split.ex_date_excluded) - len(
        split.corporate_action_excluded
    ) == len(split.members)
    market = calc.market
    assert (market.missing, market.ex_date_excluded, market.corporate_action_excluded) == (
        split.missing,
        split.ex_date_excluded,
        split.corporate_action_excluded,
    )
    assert set(calc.member_returns) == set(market.members)


def test_ex_date_only_counts_inside_the_window_and_only_if_already_announced() -> None:
    sc = scenario({"24": [Member("2400", ex_date=True), *members("245", 5)]})
    # Before the announcement window opened (15 sessions back) nothing is known.
    early = universe.calculation_set(sc.market.as_of(sc.sessions[-20]), V1)
    assert "2400" not in early.sector("24").split.ex_date_excluded
    late = universe.calculation_set(sc.market.as_of(sc.t), V1)
    assert late.sector("24").split.ex_date_excluded == {"2400"}


def test_member_return_is_close_t_over_close_t_minus_l() -> None:
    panel, calc, _ = _core({"01": [Member("1100", ret=0.2), *members("115", 4)]})
    window = index.lookback_window(panel, V1.lookback_days)
    assert window is not None and len(window) == V1.lookback_days + 1
    assert window[-1] == panel.decision_date
    assert calc.member_returns["1100"] == pytest.approx(0.2, abs=1e-12)


# ---------------------------------------------------------------------------
# T-9 / T-20 same set, with teeth
# ---------------------------------------------------------------------------


def test_sector_return_up_count_and_constituents_share_one_set() -> None:
    _, calc, board = _core(
        {
            "01": [Member("1100", missing=True), *members("115", 9, ret=-0.01)],
            "02": [*members("12", 7, ret=0.02), Member("1290", ret=-0.03)],
            "20": members("20", 4),
        }
    )
    assert len(board.ranked) == 2
    assert_same_set(calc, board)
    assert calc.market.members == frozenset(calc.member_returns)
    benchmark = math.fsum(calc.member_returns[s] for s in sorted(calc.market.members)) / len(
        calc.market.members
    )
    assert board.benchmark_return == benchmark


def test_same_set_check_has_teeth_when_one_set_gains_a_name() -> None:
    _, calc, board = _core({"01": members("11", 6), "02": members("12", 6, ret=0.01)})
    row = board.ranked[0]
    tampered = dataclasses.replace(
        board, ranked=(dataclasses.replace(row, members=row.members | {"9999"}), *board.ranked[1:])
    )
    with pytest.raises(AssertionError):
        assert_same_set(calc, tampered)
    bumped = dataclasses.replace(
        board, ranked=(dataclasses.replace(row, up_count=row.up_count + 1), *board.ranked[1:])
    )
    with pytest.raises(AssertionError):
        assert_same_set(calc, bumped)


# ---------------------------------------------------------------------------
# ranking and constituents (C-17)
# ---------------------------------------------------------------------------


def test_rank_is_by_relative_return_and_ties_break_on_sector_code() -> None:
    same = [Member(f"{p}0{i}", ret=0.01 * (i - 2)) for p in ("14", "12") for i in range(5)]
    _, _, board = _core({"14": same[:5], "12": same[5:], "03": members("03", 5, ret=0.05)})
    assert [row.sector_code for row in board.ranked] == ["03", "12", "14"]
    assert [row.rank for row in board.ranked] == [1, 2, 3]
    assert board.ranked[1].rel_return == board.ranked[2].rel_return


def test_constituents_are_top_two_then_bottom_one_by_return_then_symbol() -> None:
    group = [
        Member("1105", ret=0.05),
        Member("1101", ret=0.05),  # tie with 1105 -> symbol order
        Member("1102", ret=0.01),
        Member("1103", ret=-0.02),
        Member("1104", ret=-0.02),  # tie with 1103 -> 1104 sorts last
    ]
    _, calc, board = _core({"01": group})
    listed = [item.symbol for item in board.ranked[0].constituents]
    assert listed == ["1101", "1105", "1104"]
    assert constituents.list_constituents(calc, "01") == board.ranked[0].constituents


def test_turnover_is_not_a_ranking_input() -> None:
    assert "turnover" not in " ".join(inspect.signature(ranking.rank_sectors).parameters)
    base = {"01": members("11", 5, ret=0.01), "02": members("12", 5, ret=0.02)}
    boosted = {
        "01": [dataclasses.replace(m, traded_value=4e8) for m in base["01"]],
        "02": base["02"],
    }
    panel_a, calc_a, board_a = _core(base)
    panel_b, calc_b, board_b = _core(boosted)
    turnover_a = index.turnover_value_ratio_5_20(panel_a, calc_a.sector("01").members)
    turnover_b = index.turnover_value_ratio_5_20(panel_b, calc_b.sector("01").members)
    # Raise only the last 5 sessions to move the ratio itself.
    builder_panel = scenario(base).market
    frames = builder_panel.frames
    last5 = sorted(set(frames.bars["session_date"]))[-5:]
    bumped = frames.bars.copy()
    mask = bumped["session_date"].isin(last5) & bumped["symbol"].str.startswith("11")
    bumped.loc[mask, "traded_value"] = bumped.loc[mask, "traded_value"] * 3
    from app.data.panel import MarketPanel

    panel_c = MarketPanel(dataclasses.replace(frames, bars=bumped)).as_of(last5[-1])
    calc_c = universe.calculation_set(panel_c, V1)
    board_c = ranking.rank_sectors(calc_c, V1)
    turnover_c = index.turnover_value_ratio_5_20(panel_c, calc_c.sector("01").members)
    assert turnover_a == pytest.approx(1.0) and turnover_b == pytest.approx(1.0)
    assert turnover_c == pytest.approx(2.0)  # (5 x 3) / 5 over (5 x 3 + 15) / 20
    ranks = [(row.sector_code, row.rank, row.rel_return) for row in board_a.ranked]
    assert ranks == [(row.sector_code, row.rank, row.rel_return) for row in board_b.ranked]
    assert ranks == [(row.sector_code, row.rank, row.rel_return) for row in board_c.ranked]


def test_single_stock_dominance_is_flagged_not_ranked_on() -> None:
    group = [Member("1100", ret=0.30), *[Member(f"110{i}", ret=0.001) for i in range(1, 5)]]
    _, _, board = _core({"01": group, "02": members("12", 5)})
    row = next(row for row in board.ranked if row.sector_code == "01")
    assert row.top_contributor_share is not None and row.top_contributor_share > 0.5
    assert row.single_stock_dominated is True


# ---------------------------------------------------------------------------
# exclusion attribution (C-39, T-20)
# ---------------------------------------------------------------------------


def test_too_few_members() -> None:
    _, _, board = _core({"01": members("11", 4), "02": members("12", 5)})
    assert _reason(board, "01") == "too_few_members"


def test_low_coverage_from_missing_alone() -> None:
    # 10 expected, 2 missing -> 80% < 90%.
    group = [Member("1100", missing=True), Member("1101", missing=True), *members("115", 8)]
    _, _, board = _core({"01": group, "02": members("12", 5)})
    assert _reason(board, "01") == "low_coverage"


def test_ex_dividend_exclusion_without_any_missing() -> None:
    group = [Member("1100", ex_date=True), *members("115", 5)]  # 5/6 < 90%
    _, _, board = _core({"01": group, "02": members("12", 5)})
    assert _reason(board, "01") == "ex_dividend_exclusion"
    corporate = [Member("1100", jump=True), *members("115", 5)]
    _, _, board = _core({"01": corporate, "02": members("12", 5)})
    assert _reason(board, "01") == "ex_dividend_exclusion"


def test_missing_and_ex_date_together_already_short_on_missing_is_low_coverage() -> None:
    group = [
        Member("1100", missing=True),
        Member("1101", missing=True),
        Member("1102", ex_date=True),
        *members("115", 7),
    ]
    _, _, board = _core({"01": group, "02": members("12", 5)})
    excluded = [row for row in board.excluded if row.sector_code == "01"]
    assert len(excluded) == 1
    assert excluded[0].reason_code == "low_coverage"
    assert excluded[0].computable_count == 7
    assert excluded[0].expected_count == 10


def test_attribution_order_constant_is_pinned() -> None:
    assert coverage.REASON_CODE_ORDER == (
        "unranked_category",
        "too_few_members",
        "low_coverage",
        "ex_dividend_exclusion",
    )


def test_coverage_threshold_is_inclusive_at_exactly_ninety_percent() -> None:
    group = [Member("1100", ex_date=True), *members("115", 9)]  # 9/10 == 0.90
    _, _, board = _core({"01": group})
    assert [row.sector_code for row in board.ranked] == ["01"]
    assert board.ranked[0].coverage.coverage_ratio == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# thresholds echoed from the gate's own object (C-33)
# ---------------------------------------------------------------------------


def test_published_thresholds_are_the_definition_objects() -> None:
    out = coverage.published_thresholds(V1)
    rules = V1.coverage
    assert out["min_constituents"] is rules.min_constituents
    assert out["sector_coverage_threshold"] is rules.sector_coverage_threshold
    assert out["overall_coverage_threshold"] is rules.overall_coverage_threshold
    assert out["computable_ratio_min"] is rules.computable_ratio_min
    assert out["ex_date_tag_ratio_min"] is rules.ex_date_tag_ratio_min
    assert out == {
        "min_constituents": 5,
        "sector_coverage_threshold": 0.90,
        "overall_coverage_threshold": 0.98,
        "computable_ratio_min": 0.80,
        "ex_date_tag_ratio_min": 0.05,
    }


# ---------------------------------------------------------------------------
# constituent invariant (C-35), fault injection
# ---------------------------------------------------------------------------


def test_short_constituent_list_moves_the_sector_out_as_low_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, calc, _ = _core({"01": members("11", 6), "02": members("12", 6, ret=0.01)})
    real = constituents.list_constituents

    def broken(calc_: CalculationSet, sector_code: str) -> tuple[constituents.Constituent, ...]:
        picked = real(calc_, sector_code)
        return picked[:2] if sector_code == "02" else picked

    monkeypatch.setattr(constituents, "list_constituents", broken)
    board = ranking.rank_sectors(calc, V1)
    assert [row.sector_code for row in board.ranked] == ["01"]
    assert board.ranked[0].rank == 1
    moved = next(row for row in board.excluded if row.sector_code == "02")
    assert moved.reason_code == "low_coverage"
    assert moved.internal_reason == ranking.CONSTITUENT_INVARIANT_VIOLATED
    assert board.invariant_violations == ("02",)


def test_every_ranked_sector_lists_three_constituents() -> None:
    _, _, board = _core({"01": members("11", 5), "02": members("12", 9), "03": members("03", 20)})
    assert board.ranked
    assert all(len(row.constituents) == 3 for row in board.ranked)


# ---------------------------------------------------------------------------
# card level: completeness, computable ratio, floor display (C-37, T-23)
# ---------------------------------------------------------------------------


def test_floor_display_rounds_down() -> None:
    assert coverage.floor_pct_display(0.79999) == 79.9
    assert coverage.floor_pct_display(0.80) == 80.0
    assert coverage.floor_pct_display(0.29) == 29.0
    assert coverage.floor_pct_display(0.97999) == 97.9
    assert coverage.floor_pct_display(Fraction(799, 1000)) == 79.9
    assert coverage.floor_pct_display(Fraction(1, 3)) == 33.3
    assert coverage.floor_pct_display(1.0) == 100.0


def test_card_counts_satisfy_e_minus_a_minus_b_minus_c() -> None:
    card = coverage.card_from_counts(
        expected=200, missing=3, ex_date=30, corporate_action=2, rules=V1.coverage
    )
    assert card.coverage.calculation_count == 200 - 3 - 30 - 2
    assert (
        card.market_expected_count
        - card.market_missing_count
        - card.market_ex_date_excluded_count
        - card.market_corporate_action_excluded_count
        == card.coverage.calculation_count
    )


def test_computable_ratio_exactly_at_the_minimum_does_not_degrade() -> None:
    at = coverage.card_from_counts(
        expected=100, missing=0, ex_date=20, corporate_action=0, rules=V1.coverage
    )
    assert at.computable_ratio == 0.8 and at.computable_low is False
    assert at.computable_ratio_pct_display == 80.0
    below = coverage.card_from_counts(
        expected=100_000, missing=0, ex_date=20_001, corporate_action=0, rules=V1.coverage
    )
    assert below.computable_low is True
    assert below.computable_ratio_pct_display == 79.9


def test_peak_season_is_computable_ratio_low_not_completeness_low() -> None:
    card = coverage.card_from_counts(
        expected=1000, missing=10, ex_date=250, corporate_action=0, rules=V1.coverage
    )
    assert card.completeness_ratio == pytest.approx(0.99)
    assert card.completeness_low is False
    assert card.computable_low is True


def test_completeness_counts_missing_only_and_floors() -> None:
    card = coverage.card_from_counts(
        expected=100_000, missing=2_001, ex_date=5, corporate_action=5, rules=V1.coverage
    )
    assert card.completeness_low is True
    assert card.completeness_pct_display == 97.9  # 97.999 floored
    exact = coverage.card_from_counts(
        expected=50, missing=1, ex_date=0, corporate_action=0, rules=V1.coverage
    )
    assert exact.completeness_ratio == 0.98 and exact.completeness_low is False


def test_empty_expected_market_leaves_ratios_undefined() -> None:
    card = coverage.card_from_counts(
        expected=0, missing=0, ex_date=0, corporate_action=0, rules=V1.coverage
    )
    assert card.completeness_ratio is None and card.computable_ratio is None
    assert card.completeness_low is False and card.computable_low is False


# ---------------------------------------------------------------------------
# ex-date tag (C-38, T-24)
# ---------------------------------------------------------------------------


def test_ex_date_tag_at_the_threshold_is_on() -> None:
    card = coverage.card_from_counts(
        expected=100, missing=0, ex_date=5, corporate_action=0, rules=V1.coverage
    )
    assert card.market_ex_date_excluded_ratio == 0.05
    assert coverage.ex_date_tag(card, ()) is True


def test_ex_date_tag_just_below_the_threshold_is_off_without_an_exclusion() -> None:
    card = coverage.card_from_counts(
        expected=1000, missing=0, ex_date=49, corporate_action=0, rules=V1.coverage
    )
    assert coverage.ex_date_tag(card, ("too_few_members", "low_coverage")) is False


def test_ex_date_tag_below_the_threshold_is_on_with_an_ex_dividend_exclusion() -> None:
    card = coverage.card_from_counts(
        expected=1000, missing=0, ex_date=10, corporate_action=0, rules=V1.coverage
    )
    assert coverage.ex_date_tag(card, ("ex_dividend_exclusion",)) is True


# ---------------------------------------------------------------------------
# n1 / n2 / n3 (C-44, T-28 backend)
# ---------------------------------------------------------------------------


def test_excluded_reason_counts_add_up_to_the_rankable_sectors() -> None:
    _, _, board = _core(
        {
            "01": members("11", 4),  # too_few_members
            "02": [Member("1200", missing=True), *members("125", 4)],  # low_coverage
            "03": [Member("0300", ex_date=True), *members("035", 5)],  # ex_dividend_exclusion
            "20": members("20", 6),  # unranked, not counted
        }
    )
    assert board.ranked == ()
    counts = coverage.excluded_reason_counts(board.excluded_reason_codes)
    assert (counts.too_few_members, counts.low_coverage, counts.ex_dividend_exclusion) == (1, 1, 1)
    rankable = sum(1 for row in board.excluded if row.reason_code != "unranked_category")
    assert counts.too_few_members + counts.low_coverage + counts.ex_dividend_exclusion == rankable


# ---------------------------------------------------------------------------
# C-18: the TWT48U_ALL feed must cover the last L sessions
# ---------------------------------------------------------------------------


def test_ex_dividend_feed_gap_on_any_of_the_last_l_sessions() -> None:
    covered = scenario({"01": members("11", 5)})
    assert coverage.ex_dividend_feed_covered(covered.market.as_of(covered.t), V1) is True
    gap = scenario({"01": members("11", 5)}, dividend_run_missing_on=[weekdays(70)[-3]])
    assert coverage.ex_dividend_feed_covered(gap.market.as_of(gap.t), V1) is False
    older = scenario({"01": members("11", 5)}, dividend_run_missing_on=[weekdays(70)[-6]])
    assert coverage.ex_dividend_feed_covered(older.market.as_of(older.t), V1) is True


def test_every_panel_reading_function_refuses_a_market_panel() -> None:
    sc = scenario({"01": members("11", 5)})
    raw = sc.market
    for call in (
        lambda: index.member_returns(raw, {"1100"}, 5),  # type: ignore[arg-type]
        lambda: index.lookback_window(raw, 5),  # type: ignore[arg-type]
        lambda: index.turnover_value_ratio_5_20(raw, {"1100"}),  # type: ignore[arg-type]
        lambda: coverage.ex_dividend_feed_covered(raw, V1),  # type: ignore[arg-type]
    ):
        with pytest.raises(TypeError, match="PointInTimePanel"):
            call()
