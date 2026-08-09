"""Tests for the risk budget: every cap, in all three states, plus sizing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from app.advice import limits
from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    MAX_GROSS_EXPOSURE_CEILING,
    MAX_POSITION_WEIGHT_CEILING,
    NET_WORTH_SOFT_NOTICE_DAYS,
    NET_WORTH_STALE_AFTER_DAYS,
    NO_SECTOR_CANDIDATE_DETAIL,
    NO_SECTOR_DETAILS,
    NO_SECTOR_UNFILED_DETAIL,
    NO_SECTOR_UNSUPPORTED_MARKET_DETAIL,
    RANGE_ACTION_LABELS,
    SECTOR_MIXED_DETAIL,
    LimitCheck,
    PortfolioContext,
    RiskBudget,
    SelfReportedNetWorth,
    atr_max_shares,
    evaluate_limits,
    format_reported_at,
    kelly_allowed_weight,
    kelly_fraction,
    limit_status_after,
    notional_caps,
    project_position,
    suggest_quantity_range,
)
from tests.advice_helpers import reported_net_worth

BUDGET = RiskBudget()


def _ctx(**overrides: Any) -> PortfolioContext:
    """A fully populated context; override one field per test.

    The self-reported net worth is set to the same 1,000,000 as the valued book
    so the gross-exposure numbers below read the same as they did before FR-9
    gave that cap its own denominator -- the change of *meaning* is covered by
    its own tests, not smuggled into every other one.
    """
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "position_cost_twd": 40_000.0,
        "gross_exposure_twd": 500_000.0,
        "net_worth": reported_net_worth(1_000_000.0),
        "book_fully_valued": True,
        "quantity": 500.0,
        "close": 100.0,
        "atr": 2.0,
    }
    base.update(overrides)
    return PortfolioContext(**base)


def _check(ctx: PortfolioContext, limit_id: str, budget: RiskBudget = BUDGET) -> LimitCheck:
    checks = {check.id: check for check in evaluate_limits(budget, ctx)}
    return checks[limit_id]


def _status(ctx: PortfolioContext, limit_id: str, budget: RiskBudget = BUDGET) -> str:
    return _check(ctx, limit_id, budget).status


# --- Defaults and ordering ---------------------------------------------------


def test_default_budget_is_conservative() -> None:
    assert BUDGET.max_position_weight == 0.15
    assert BUDGET.max_sector_weight == 0.30
    assert BUDGET.max_gross_exposure == 1.00
    assert BUDGET.max_loss_per_trade == 0.01
    assert BUDGET.atr_stop_multiple == 2.0
    assert BUDGET.kelly_fraction_cap == 0.25
    assert BUDGET.kelly_position_cap == 0.10


def test_kelly_fraction_cap_cannot_exceed_a_quarter() -> None:
    with pytest.raises(ValueError):
        RiskBudget(kelly_fraction_cap=0.5)
    with pytest.raises(ValueError):
        RiskBudget(kelly_position_cap=0.2)


def test_the_hard_ceilings_are_where_policy_put_them() -> None:
    assert MAX_POSITION_WEIGHT_CEILING == 0.50
    assert MAX_GROSS_EXPOSURE_CEILING == 1.50


def test_a_cap_may_be_raised_up_to_its_ceiling() -> None:
    # The ceiling itself is a legal setting; only a value past it is refused.
    budget = RiskBudget(
        max_position_weight=MAX_POSITION_WEIGHT_CEILING,
        max_gross_exposure=MAX_GROSS_EXPOSURE_CEILING,
    )
    assert budget.max_position_weight == MAX_POSITION_WEIGHT_CEILING
    assert budget.max_gross_exposure == MAX_GROSS_EXPOSURE_CEILING


@pytest.mark.parametrize(
    ("field_name", "ceiling"),
    [
        ("max_position_weight", MAX_POSITION_WEIGHT_CEILING),
        ("max_gross_exposure", MAX_GROSS_EXPOSURE_CEILING),
    ],
)
def test_a_cap_cannot_be_raised_past_its_ceiling(field_name: str, ceiling: float) -> None:
    # The refusal has to name the number and what it would take to move it --
    # these caps used to accept 1.0 and 2.0 with no gate at all.
    with pytest.raises(ValueError) as exc:
        RiskBudget(**{field_name: ceiling + 0.01})
    message = str(exc.value)
    assert f"{ceiling:.2f}" in message
    assert "硬性上界" in message
    assert "風控" in message and "CEO" in message


def test_every_limit_is_reported_once_in_order() -> None:
    checks = evaluate_limits(BUDGET, _ctx())
    assert [check.id for check in checks] == list(LIMIT_IDS)
    assert [check.index for check in checks] == [1, 2, 3, 4, 5]
    assert [check.name for check in checks] == [LIMIT_NAMES[i] for i in LIMIT_IDS]


# --- 1. Single position weight ----------------------------------------------


def test_single_position_weight_passed() -> None:
    assert _status(_ctx(position_market_value_twd=50_000.0), "single_position_weight") == "passed"


def test_single_position_weight_violated_at_the_cap() -> None:
    # Exactly at 15%: the budget is spent, so there is no room left to add.
    check = _check(_ctx(position_market_value_twd=150_000.0), "single_position_weight")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.15)
    assert check.threshold == 0.15


def test_single_position_weight_violated_above_the_cap() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0)
    assert _status(ctx, "single_position_weight") == "violated"


def test_single_position_weight_not_evaluable_without_equity() -> None:
    assert _status(_ctx(total_equity_twd=None), "single_position_weight") == "not_evaluable"


# --- 2. Sector weight (FR-12: the field exists, the value may not) ----------


def test_sector_weight_not_evaluable_without_sector_data() -> None:
    check = _check(_ctx(), "sector_weight")
    assert check.status == "not_evaluable"
    assert "產業別" in check.detail
    assert check.observed is None


def test_missing_sector_reads_as_an_unfilled_value_not_a_missing_field() -> None:
    # AC-12.3: the two states are different problems. Since FR-12 the column
    # exists, so the reason must point at the value the user can supply and no
    # longer claim the product has no such field.
    detail = _check(_ctx(sector_gap="unfiled"), "sector_weight").detail
    assert "沒有產業別欄位" not in detail
    assert "填" in detail  # names the action that would make the cap evaluable


@pytest.mark.parametrize(
    ("gap", "expected"),
    [
        ("no_position", NO_SECTOR_CANDIDATE_DETAIL),
        ("unfiled", NO_SECTOR_UNFILED_DETAIL),
        ("unsupported_market", NO_SECTOR_UNSUPPORTED_MARKET_DETAIL),
        ("mixed", SECTOR_MIXED_DETAIL),
    ],
)
def test_each_way_the_sector_is_missing_gets_its_own_sentence(gap: str, expected: str) -> None:
    # AC-12.3 as risk-compliance settled it on 2026-08-09: four states, four
    # sentences, none of them shared. The texts are risk-approved copy, so they
    # are asserted verbatim rather than by keyword.
    check = _check(_ctx(sector_gap=gap), "sector_weight")
    assert check.status == "not_evaluable"
    assert check.detail == expected
    assert len({*NO_SECTOR_DETAILS.values()}) == len(NO_SECTOR_DETAILS)


def test_a_candidate_is_not_told_to_fill_in_a_holding_it_does_not_have() -> None:
    # Nothing is held, so there is no position to file a category on: the
    # sentence states what was not computed and stops there.
    detail = _check(_ctx(sector_gap="no_position"), "sector_weight").detail
    assert "填入" not in detail
    assert "not_evaluable" in detail


def test_a_non_tw_holding_is_not_promised_a_cap_it_cannot_turn_on() -> None:
    # The API answers a category on a non-TW holding with a 422 (AC-12.6), so
    # "fill it in and this cap starts working" would be an instruction the
    # product refuses to carry out.
    detail = _check(_ctx(sector_gap="unsupported_market"), "sector_weight").detail
    assert "填入" not in detail
    assert "啟用這條上限" not in detail


def test_mixed_categories_are_not_reported_as_an_unfilled_field() -> None:
    # Two categories on one symbol is the opposite of "not stated"; saying the
    # field is empty would be factually wrong, so this state reuses the mixed
    # sentence and names the fix.
    detail = _check(_ctx(sector_gap="mixed"), "sector_weight").detail
    assert "尚未填寫" not in detail
    assert "不只一種產業別" in detail
    assert "統一為同一種產業別" in detail


def test_an_unstated_gap_falls_back_to_what_the_context_can_show() -> None:
    # A context assembled without the signal (the alert vocabulary's, and older
    # callers') still gets a true sentence: the model can tell "nothing held"
    # from "held but unclassified", and never guesses the other two.
    candidate = _ctx(sector_gap=None, position_market_value_twd=0.0, quantity=0.0)
    assert _check(candidate, "sector_weight").detail == NO_SECTOR_CANDIDATE_DETAIL
    assert _check(_ctx(sector_gap=None), "sector_weight").detail == NO_SECTOR_UNFILED_DETAIL


def test_sector_weight_passed_when_the_caller_supplies_sector_data() -> None:
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0)
    assert _status(ctx, "sector_weight") == "passed"


def test_sector_weight_violated_when_the_sector_is_over_the_cap() -> None:
    ctx = _ctx(sector="半導體業", sector_market_value_twd=350_000.0)
    check = _check(ctx, "sector_weight")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.35)


def test_sector_weight_not_evaluable_without_equity() -> None:
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0, total_equity_twd=None)
    assert _status(ctx, "sector_weight") == "not_evaluable"


# --- 3. Gross exposure ------------------------------------------------------


def test_gross_exposure_passed() -> None:
    assert _status(_ctx(gross_exposure_twd=600_000.0), "gross_exposure") == "passed"


def test_gross_exposure_violated_at_full_investment() -> None:
    check = _check(_ctx(gross_exposure_twd=1_000_000.0), "gross_exposure")
    assert check.status == "violated"
    assert check.observed == pytest.approx(1.0)


def test_gross_exposure_not_evaluable_without_book_value() -> None:
    assert _status(_ctx(gross_exposure_twd=None), "gross_exposure") == "not_evaluable"


# --- 3b. FR-9: the self-reported net worth is cap 3's only denominator -------


def test_gross_exposure_divides_by_the_reported_net_worth_not_the_book() -> None:
    # AC-9.3. The book is 1,000,000 of valued positions against a 2,000,000
    # account: 50% exposure. Dividing by the book itself would have said 100%.
    check = _check(
        _ctx(gross_exposure_twd=1_000_000.0, net_worth=reported_net_worth(2_000_000.0)),
        "gross_exposure",
    )
    assert check.status == "passed"
    assert check.observed == pytest.approx(0.5)
    assert check.threshold == pytest.approx(1.0)


def test_gross_exposure_violated_against_the_reported_net_worth() -> None:
    check = _check(
        _ctx(gross_exposure_twd=1_000_000.0, net_worth=reported_net_worth(900_000.0)),
        "gross_exposure",
    )
    assert check.status == "violated"
    assert check.observed == pytest.approx(1_000_000.0 / 900_000.0)


def test_gross_exposure_keeps_its_pre_fr9_wording_when_none_was_reported() -> None:
    # AC-9.2: a user who never entered a net worth must see exactly what this
    # cap said before FR-9 existed, plus the one thing that would enable it.
    check = _check(_ctx(net_worth=None), "gross_exposure")
    assert check.status == "not_evaluable"
    assert check.observed is None
    assert check.detail.startswith("缺少組合總市值，無法計算總曝險。")
    assert "帳戶總淨值（新台幣）" in check.detail


def test_gross_exposure_expires_after_thirty_days() -> None:
    # AC-9.4 / FR-9 (b): a stale figure is never quietly turned into a pass.
    check = _check(
        _ctx(net_worth=reported_net_worth(2_000_000.0, age_days=NET_WORTH_STALE_AFTER_DAYS)),
        "gross_exposure",
    )
    assert check.status == "not_evaluable"
    assert check.observed is None
    assert f"淨值輸入已超過 {NET_WORTH_STALE_AFTER_DAYS} 天未更新" in check.detail
    assert "更新" in check.detail


def test_gross_exposure_still_evaluates_the_day_before_it_expires() -> None:
    check = _check(
        _ctx(net_worth=reported_net_worth(2_000_000.0, age_days=NET_WORTH_STALE_AFTER_DAYS - 1)),
        "gross_exposure",
    )
    assert check.status == "passed"


def test_gross_exposure_says_how_long_since_the_report_past_the_soft_notice() -> None:
    aged = _check(
        _ctx(net_worth=reported_net_worth(2_000_000.0, age_days=NET_WORTH_SOFT_NOTICE_DAYS)),
        "gross_exposure",
    )
    assert aged.status == "passed"
    assert f"已 {NET_WORTH_SOFT_NOTICE_DAYS} 天未更新" in aged.detail
    fresh = _check(
        _ctx(net_worth=reported_net_worth(2_000_000.0, age_days=NET_WORTH_SOFT_NOTICE_DAYS - 1)),
        "gross_exposure",
    )
    assert "天未更新" not in fresh.detail


def test_gross_exposure_is_withheld_when_a_position_could_not_be_valued() -> None:
    # FR-9 (a-附加): the numerator would be short, and a short numerator makes
    # exposure look *lower* than it is -- the one direction this cap must not
    # err in. So it reports nothing rather than something reassuring.
    check = _check(_ctx(book_fully_valued=False), "gross_exposure")
    assert check.status == "not_evaluable"
    assert "分子不完整" in check.detail


def test_gross_exposure_requires_coverage_to_be_stated_not_assumed() -> None:
    # An unknown coverage is not evidence of a complete book.
    assert _status(_ctx(book_fully_valued=None), "gross_exposure") == "not_evaluable"


def test_gross_exposure_verdict_carries_the_three_required_sentences() -> None:
    # FR-9 (a-附加) required disclosure: mixed provenance, an assumption of a
    # complete position list, and when the denominator was last reported.
    net_worth = reported_net_worth(2_000_000.0)
    detail = _check(_ctx(net_worth=net_worth), "gross_exposure").detail
    assert "兩者來源不同" in detail
    assert "未登錄的部位不計入分子，會讓曝險看起來偏低" in detail
    # The third sentence is a *readable* time, not the raw stored value: the
    # fixture reports 2026-07-24T15:51:56.015754+00:00.
    assert "2026-07-24 23:51（台北時間）" in detail
    assert net_worth.reported_at not in detail


def test_the_expiry_reason_also_carries_a_readable_time() -> None:
    detail = _check(
        _ctx(net_worth=reported_net_worth(2_000_000.0, age_days=NET_WORTH_STALE_AFTER_DAYS)),
        "gross_exposure",
    ).detail
    assert "2026-06-24 23:51（台北時間）" in detail
    assert "015754" not in detail


# --- The timestamp format the disclosures use --------------------------------


def test_reported_at_is_converted_to_taipei_and_labelled() -> None:
    # A real conversion: 15:51 UTC is 23:51 the same day in Taipei. Labelled,
    # because an unlabelled local time reads exactly like an unconverted UTC
    # one and the two are eight hours apart.
    assert (
        format_reported_at("2026-08-05T15:51:56.015754+00:00")
        == "2026-08-05 23:51（台北時間）"
    )


def test_reported_at_crossing_midnight_moves_the_date_too() -> None:
    # 20:00 UTC is 04:00 the *next* day in Taipei; string surgery on the
    # timestamp would have kept the wrong date.
    assert format_reported_at("2026-08-05T20:00:00+00:00") == "2026-08-06 04:00（台北時間）"


def test_a_non_utc_offset_is_honoured_rather_than_assumed_away() -> None:
    # Already Taipei time: the instant is unchanged, so the rendering is too.
    assert format_reported_at("2026-08-05T23:51:00+08:00") == "2026-08-05 23:51（台北時間）"


def test_a_naive_timestamp_is_read_as_utc_like_everywhere_else() -> None:
    # Same assumption ``self_reported_net_worth`` makes when measuring its age,
    # so the age and the displayed time can never disagree about the instant.
    assert format_reported_at("2026-08-05T15:51:56") == "2026-08-05 23:51（台北時間）"


def test_seconds_and_microseconds_are_dropped() -> None:
    rendered = format_reported_at("2026-08-05T15:51:56.015754+00:00")
    assert "56" not in rendered.split("（")[0].split(" ")[1]
    assert "015754" not in rendered


def test_an_unparseable_timestamp_comes_back_untouched() -> None:
    # Half-formatting a value nobody could read would present a time that was
    # never verified; the raw string at least cannot be mistaken for one.
    assert format_reported_at("上週三") == "上週三"


def test_a_reported_net_worth_must_be_positive() -> None:
    # The settings boundary rejects these first; this is the second line.
    with pytest.raises(ValueError):
        SelfReportedNetWorth(amount_twd=0.0, reported_at="2026-08-05", age_days=0)
    with pytest.raises(ValueError):
        SelfReportedNetWorth(amount_twd=-1.0, reported_at="2026-08-05", age_days=0)


def test_the_net_worth_never_reaches_caps_1_and_4() -> None:
    # AC-9.6 regression guard for option B. A net worth ten times the book is
    # exactly the input that would loosen every ratio if the denominators were
    # ever merged: caps 1 and 4 must not move by a single basis point.
    book_only = _ctx(net_worth=None)
    with_net_worth = _ctx(net_worth=reported_net_worth(10_000_000.0))
    for limit_id in ("single_position_weight", "per_trade_loss"):
        before = _check(book_only, limit_id)
        after = _check(with_net_worth, limit_id)
        assert (before.status, before.observed, before.threshold, before.detail) == (
            after.status,
            after.observed,
            after.threshold,
            after.detail,
        )
    # And the one cap that *is* meant to move, moved.
    assert _status(book_only, "gross_exposure") == "not_evaluable"
    assert _status(with_net_worth, "gross_exposure") == "passed"


def test_gross_exposure_headroom_is_measured_against_the_net_worth() -> None:
    caps = notional_caps(BUDGET, _ctx(net_worth=reported_net_worth(2_000_000.0)))
    # 100% of the 2,000,000 net worth, less the 450,000 held by other names.
    assert caps["gross_exposure"] == pytest.approx(1_550_000.0)


def test_no_gross_exposure_headroom_while_the_cap_cannot_be_evaluated() -> None:
    # Sizing must never be derived from a cap the card reports as unevaluable.
    for ctx in (
        _ctx(net_worth=None),
        _ctx(net_worth=reported_net_worth(2_000_000.0, age_days=NET_WORTH_STALE_AFTER_DAYS)),
        _ctx(book_fully_valued=False),
    ):
        assert "gross_exposure" not in notional_caps(BUDGET, ctx)


def test_a_projected_trade_does_not_move_the_reported_net_worth() -> None:
    ctx = _ctx(net_worth=reported_net_worth(2_000_000.0))
    after = project_position(ctx, share_delta=1_000.0)
    assert after.net_worth == ctx.net_worth
    # The numerator does move: the trade really did add to the book.
    assert after.gross_exposure_twd == pytest.approx(600_000.0)


# --- 4. Per-trade loss, derived from ATR ------------------------------------


def test_per_trade_loss_passed_and_quotes_the_stop_basis() -> None:
    # 500 shares x 2 x ATR 2.0 = 2,000 TWD at risk = 0.2% of 1,000,000.
    check = _check(_ctx(), "per_trade_loss")
    assert check.status == "passed"
    assert check.observed == pytest.approx(0.002)
    assert "ATR(14)" in check.detail


def test_per_trade_loss_violated_when_the_stop_out_loss_is_too_large() -> None:
    # 3,000 shares x 4 TWD stop distance = 12,000 = 1.2% > 1%.
    check = _check(_ctx(quantity=3_000.0, position_market_value_twd=300_000.0), "per_trade_loss")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.012)


def test_per_trade_loss_not_evaluable_without_atr() -> None:
    assert _status(_ctx(atr=None), "per_trade_loss") == "not_evaluable"


def test_per_trade_loss_not_evaluable_with_zero_atr() -> None:
    assert _status(_ctx(atr=0.0), "per_trade_loss") == "not_evaluable"


def test_per_trade_loss_not_evaluable_without_a_share_count() -> None:
    ctx = _ctx(quantity=None, position_market_value_twd=None, close=None)
    assert _status(ctx, "per_trade_loss") == "not_evaluable"


def test_atr_max_shares_uses_the_stop_multiple() -> None:
    # 1% of 1,000,000 = 10,000 TWD risk; stop distance 2 x 2.0 = 4 TWD.
    assert atr_max_shares(BUDGET, _ctx()) == pytest.approx(2_500.0)
    assert atr_max_shares(BUDGET, _ctx(atr=None)) is None
    assert atr_max_shares(BUDGET, _ctx(atr=0.0)) is None
    assert atr_max_shares(BUDGET, _ctx(total_equity_twd=None)) is None


def test_atr_max_shares_converts_a_foreign_currency_stop() -> None:
    ctx = _ctx(close=20.0, atr=0.5, fx_to_twd=32.0)
    # Stop distance = 2 x 0.5 x 32 = 32 TWD; 10,000 / 32 = 312.5 shares.
    assert atr_max_shares(BUDGET, ctx) == pytest.approx(312.5)


# --- 5. Fractional Kelly ----------------------------------------------------


def test_kelly_fraction_matches_the_textbook_formula() -> None:
    # w = 0.6, b = 2  ->  0.6 - 0.4/2 = 0.4
    assert kelly_fraction(0.6, 2.0) == pytest.approx(0.4)
    assert kelly_fraction(0.4, 1.0) == pytest.approx(-0.2)
    assert kelly_fraction(1.5, 2.0) is None
    assert kelly_fraction(0.6, 0.0) is None


def test_kelly_allowed_weight_applies_the_quarter_and_the_hard_cap() -> None:
    # Quarter of 0.4 = 0.10, exactly at the hard cap.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.6, payoff_ratio=2.0)) == pytest.approx(0.1)
    # A huge edge is still capped at 10%.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.9, payoff_ratio=5.0)) == pytest.approx(0.1)
    # Quarter of 0.2 = 0.05, below the hard cap.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.6, payoff_ratio=1.0)) == pytest.approx(0.05)
    # A negative edge allows nothing.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.3, payoff_ratio=1.0)) == 0.0


def test_kelly_not_evaluable_without_win_rate_or_payoff() -> None:
    check = _check(_ctx(), "kelly_fraction")
    assert check.status == "not_evaluable"
    assert "勝率" in check.detail
    assert _status(_ctx(win_rate=0.6), "kelly_fraction") == "not_evaluable"
    assert _status(_ctx(payoff_ratio=2.0), "kelly_fraction") == "not_evaluable"


def test_kelly_passed_when_the_position_fits_the_edge() -> None:
    ctx = _ctx(win_rate=0.6, payoff_ratio=2.0, position_market_value_twd=50_000.0)
    check = _check(ctx, "kelly_fraction")
    assert check.status == "passed"
    assert check.threshold == pytest.approx(0.1)


def test_kelly_violated_when_the_position_exceeds_the_edge() -> None:
    ctx = _ctx(win_rate=0.6, payoff_ratio=1.0, position_market_value_twd=80_000.0)
    check = _check(ctx, "kelly_fraction")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.08)
    assert check.threshold == pytest.approx(0.05)


def test_kelly_not_evaluable_without_position_weight() -> None:
    ctx = _ctx(win_rate=0.6, payoff_ratio=2.0, position_market_value_twd=None)
    assert _status(ctx, "kelly_fraction") == "not_evaluable"


# --- Notional caps and quantity ranges --------------------------------------


def test_notional_caps_skip_the_caps_they_cannot_evaluate() -> None:
    caps = notional_caps(BUDGET, _ctx())
    assert set(caps) == {"single_position_weight", "gross_exposure", "per_trade_loss"}
    assert caps["single_position_weight"] == pytest.approx(150_000.0)
    # Gross: 1,000,000 cap less the other 450,000 already invested.
    assert caps["gross_exposure"] == pytest.approx(550_000.0)
    # ATR: 2,500 shares x 100 TWD.
    assert caps["per_trade_loss"] == pytest.approx(250_000.0)


def test_notional_caps_are_empty_without_equity() -> None:
    assert notional_caps(BUDGET, _ctx(total_equity_twd=None)) == {}


def test_notional_caps_include_sector_and_kelly_when_available() -> None:
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0, win_rate=0.6, payoff_ratio=2.0)
    caps = notional_caps(BUDGET, ctx)
    # Sector: 300,000 cap less the 150,000 held by other names in the sector.
    assert caps["sector_weight"] == pytest.approx(150_000.0)
    assert caps["kelly_fraction"] == pytest.approx(100_000.0)


def test_add_range_is_derived_from_the_tightest_cap() -> None:
    quantity = suggest_quantity_range(BUDGET, _ctx(), action="add")
    assert quantity is not None
    # Binding cap 150,000 less 50,000 held = 100,000 / 100 TWD = 1,000 shares --
    # but 1,000 lands exactly on the cap, which counts as breached, so the
    # suggestion stops one share short.
    assert quantity.max_shares == 999
    assert quantity.min_shares == 499
    assert "單一標的佔比上限" in quantity.basis
    assert "未參與這個區間的計算" in quantity.basis


def test_add_range_is_none_when_the_budget_is_spent() -> None:
    ctx = _ctx(position_market_value_twd=150_000.0, quantity=1_500.0)
    assert suggest_quantity_range(BUDGET, ctx, action="add") is None


def test_add_range_is_none_without_a_price() -> None:
    assert suggest_quantity_range(BUDGET, _ctx(close=None), action="add") is None


def test_add_range_is_none_without_any_evaluable_cap() -> None:
    ctx = _ctx(total_equity_twd=None)
    assert suggest_quantity_range(BUDGET, ctx, action="add") is None


def test_reduce_range_covers_the_excess_up_to_the_whole_holding() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    # 200,000 held vs a 150,000 cap: 500 shares above the cap, plus one more so
    # the remaining position sits strictly inside the cap rather than on it.
    assert quantity.min_shares == 501
    assert quantity.max_shares == 2_000
    assert "單一標的佔比上限" in quantity.basis


def test_acting_on_the_suggested_add_leaves_the_cap_passing() -> None:
    # The whole point of a suggested quantity: buying it must not put the book
    # into the state the same cap would report as violated.
    ctx = _ctx()
    quantity = suggest_quantity_range(BUDGET, ctx, action="add")
    assert quantity is not None
    for shares in (quantity.min_shares, quantity.max_shares):
        after = project_position(ctx, share_delta=float(shares))
        assert _status(after, "single_position_weight") == "passed"
        assert evaluate_limits(BUDGET, after) == evaluate_limits(BUDGET, after)
        assert not [check for check in evaluate_limits(BUDGET, after) if check.status == "violated"]
    # One share past the upper edge is exactly what the cap rejects.
    over = project_position(ctx, share_delta=float(quantity.max_shares + 1))
    assert _status(over, "single_position_weight") == "violated"


def test_acting_on_the_suggested_reduction_leaves_the_cap_passing() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    assert _status(ctx, "single_position_weight") == "violated"
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    for shares in (quantity.min_shares, quantity.max_shares):
        after = project_position(ctx, share_delta=-float(shares))
        assert _status(after, "single_position_weight") == "passed"
    # One share short of the lower edge still leaves the cap breached.
    under = project_position(ctx, share_delta=-float(quantity.min_shares - 1))
    assert _status(under, "single_position_weight") == "violated"


def test_add_sizing_respects_a_binding_per_trade_loss_cap() -> None:
    # ATR 8 makes the stop distance 16 TWD, so the per-trade cap (625 shares
    # x 100 TWD = 62,500) binds well before the 15% position cap.
    ctx = _ctx(atr=8.0, position_market_value_twd=0.0, quantity=0.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="add")
    assert quantity is not None
    assert quantity.max_shares == 624
    after = project_position(ctx, share_delta=float(quantity.max_shares))
    assert _status(after, "per_trade_loss") == "passed"
    assert _status(project_position(ctx, share_delta=625.0), "per_trade_loss") == "violated"


def test_limit_status_after_projects_the_whole_book() -> None:
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0)
    after = project_position(ctx, share_delta=1_000.0)
    assert after.position_market_value_twd == pytest.approx(150_000.0)
    assert after.quantity == pytest.approx(1_500.0)
    assert after.gross_exposure_twd == pytest.approx(600_000.0)
    assert after.sector_market_value_twd == pytest.approx(300_000.0)
    # Equity is untouched: a market-price trade swaps cash for shares.
    assert after.total_equity_twd == ctx.total_equity_twd
    assert limit_status_after(
        BUDGET, ctx, limit_id="single_position_weight", share_delta=1_000.0
    ) == "violated"


def test_selling_everything_is_the_floor_when_nothing_else_clears_the_cap() -> None:
    # Gross exposure is over the cap because of *other* holdings, so no partial
    # sale of this name fixes it; the suggestion stops at the whole holding.
    ctx = _ctx(position_market_value_twd=50_000.0, quantity=500.0, gross_exposure_twd=2_000_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.min_shares == 500
    assert quantity.max_shares == 500


# --- Sell-side wording must match what the sale actually achieves ------------


def test_reduce_basis_claims_a_return_to_compliance_only_when_it_happens() -> None:
    # The excess is this position's own, so the sized sale really does clear it.
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.restores_compliance is True
    assert "可回到這條上限的範圍內" in quantity.basis
    assert "仍然超標" not in quantity.basis
    # And the claim is true: after the sale the cap is no longer violated.
    after = project_position(ctx, share_delta=-float(quantity.min_shares))
    assert _status(after, "single_position_weight") == "passed"


def test_reduce_basis_does_not_claim_compliance_when_selling_everything_fails() -> None:
    # Gross exposure is driven by *other* holdings: selling this whole holding
    # leaves the cap violated, so the card must not say it returns to compliance.
    ctx = _ctx(position_market_value_twd=50_000.0, quantity=500.0, gross_exposure_twd=2_000_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.restores_compliance is False
    assert "可回到這條上限的範圍內" not in quantity.basis
    assert "這個區間只有一個數字:500 股,也就是目前持股全數" in quantity.basis
    assert "但這條上限主要由其他部位造成,把這一檔全部賣出後仍然超標" in quantity.basis
    # And the disclaimer is true: after selling the lot the cap still breaches.
    after = project_position(ctx, share_delta=-float(quantity.max_shares))
    assert _status(after, "gross_exposure") == "violated"


# --- The risk-approved range copy (risk-compliance ruling, 2026-08-09) -------
#
# The ruling that approved these sentences is verbatim: "任何一字與核可全文不同
# 即視為未過審". The expected strings below are therefore transcribed from the
# ruling by hand rather than built from the module's own f-strings -- a test
# that imports the template it is checking would pass on any rewrite.


BACKEND_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_WORDING = BACKEND_ROOT.parent / "frontend" / "app" / "lib" / "adviceWording.ts"

#: The approved note appended after the basis's final full stop, with the two
#: caps this file's ``_ctx`` leaves unevaluable already interpolated.
SKIPPED_NOTE = (
    "以下上限本次缺少可用資料,未參與這個區間的計算:單一產業佔比上限、分數 Kelly 部位上限。"
    "未參與計算不等於已通過,這個區間沒有檢查過這幾條。"
)


def _front_end_action_labels() -> dict[str, str]:
    """``HELD_ACTION_LABELS`` as declared in the front-end wording module.

    Read out of the TypeScript source instead of mirrored into a Python
    literal: a copied table drifts the moment one side is edited, and the
    contract the ruling asks for is precisely that the two cannot drift.
    """
    source = FRONTEND_WORDING.read_text(encoding="utf-8")
    block = re.search(
        r"HELD_ACTION_LABELS:\s*Record<CardAction,\s*string>\s*=\s*\{(.*?)\}", source, re.S
    )
    assert block is not None, f"HELD_ACTION_LABELS not found in {FRONTEND_WORDING}"
    return dict(re.findall(r'(\w+):\s*"([^"]*)"', block.group(1)))


def test_range_action_labels_match_the_front_end_whitelist() -> None:
    labels = _front_end_action_labels()
    assert set(RANGE_ACTION_LABELS) == {"add", "reduce", "take_profit", "stop_loss"}
    for action, label in RANGE_ACTION_LABELS.items():
        assert labels[action] == label, f"「{action}」的後端標籤與前端白名單不一致"


def test_add_basis_is_the_approved_copy_verbatim() -> None:
    quantity = suggest_quantity_range(BUDGET, _ctx(), action="add")
    assert quantity is not None
    assert quantity.basis == (
        "規則評估:加碼參考,區間為再買進 499 ~ 999 股。"
        "目前有納入計算的上限中,額度最緊的是「單一標的佔比上限」;"
        "以它換算,買進後這條上限仍為通過的最大股數是 999 股,也就是區間上緣。"
        "下緣 499 股取上緣的一半,用意是給出一個範圍而不是單一數字,"
        "不是「最少要買」的數量。" + SKIPPED_NOTE
    )


def test_sell_basis_is_the_approved_copy_verbatim_when_the_sale_clears_the_cap() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.basis == (
        "規則評估:減碼參考,區間為賣出 501 ~ 2,000 股。"
        "目前部位已超出「單一標的佔比上限」這條上限,"
        "賣出 501 股後可回到這條上限的範圍內;"
        "區間上緣 2,000 股是目前持股全數,是這個區間的上界,"
        "不是這條上限要求賣到的數量。" + SKIPPED_NOTE
    )


def test_sell_basis_is_the_approved_copy_verbatim_when_selling_everything_falls_short() -> None:
    ctx = _ctx(gross_exposure_twd=2_000_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="stop_loss")
    assert quantity is not None
    assert quantity.basis == (
        "規則評估:停損評估,這個區間只有一個數字:500 股,也就是目前持股全數。"
        "目前部位已超出「總曝險上限」這條上限,"
        "但這條上限主要由其他部位造成,把這一檔全部賣出後仍然超標。" + SKIPPED_NOTE
    )


def test_every_sell_action_reuses_the_same_approved_template() -> None:
    # One template, one label slot: the three defensive actions differ only in
    # the name the sentence opens with.
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    for action in ("reduce", "stop_loss", "take_profit"):
        quantity = suggest_quantity_range(BUDGET, ctx, action=action)
        assert quantity is not None
        assert quantity.basis.startswith(f"規則評估:{RANGE_ACTION_LABELS[action]},")
        assert "區間為賣出 501 ~ 2,000 股。" in quantity.basis


def test_the_skipped_note_is_absent_when_every_cap_was_evaluated() -> None:
    # Nothing was left out, so there is no sentence saying anything was.
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0, win_rate=0.6, payoff_ratio=2.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="add")
    assert quantity is not None
    assert "缺少可用資料" not in quantity.basis
    assert "未參與這個區間的計算" not in quantity.basis
    assert quantity.basis.endswith("不是「最少要買」的數量。")


def test_range_figures_carry_thousand_separators() -> None:
    # The card prints the same numbers through ``toLocaleString``; a bare
    # "20000" beside a "20,000" reads as a different quantity.
    ctx = _ctx(
        total_equity_twd=10_000_000.0,
        position_market_value_twd=2_000_000.0,
        quantity=20_000.0,
    )
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.max_shares == 20_000
    assert "20,000 股" in quantity.basis
    assert "20000" not in quantity.basis


def test_the_superseded_copy_is_gone_from_the_backend() -> None:
    # The four phrases the ruling replaced. Left anywhere in the package or its
    # tests they would be a second, unapproved wording of the same fact. Each
    # one is spelled in two halves so the guard does not trip over its own
    # search list and can therefore scan this file as well as every other.
    superseded = (
        "上緣為" + "目前持股全數",
        "未納入" + "計算的上限",
        "區間下緣" + "取上緣的一半",
        "賣出後" + "仍為違反",
    )
    scanned = sorted(BACKEND_ROOT.glob("app/**/*.py")) + sorted(BACKEND_ROOT.glob("tests/**/*.py"))
    assert scanned
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        for phrase in superseded:
            assert phrase not in text, f"{path} 仍留有已被取代的舊文案「{phrase}」"


def test_the_approved_range_copy_never_reaches_the_alert_push_path() -> None:
    # The alert layer is measurement-only: its own guards ban 買進/賣出/加碼/
    # 減碼/建議 in every message (see ``test_alerts_engine``). This copy is full
    # of exactly those words by design, so the two surfaces must stay apart --
    # no alert module may reach for the sizing API or quote its sentences.
    banned_in_alerts = ("買進", "賣出", "加碼", "減碼", "建議")
    quantity = suggest_quantity_range(BUDGET, _ctx(), action="add")
    assert quantity is not None
    assert any(word in quantity.basis for word in banned_in_alerts)

    fragments = ("規則評估:", "這個區間", "未參與這個區間的計算", "區間上緣")
    for path in sorted(BACKEND_ROOT.glob("app/alerts/*.py")):
        text = path.read_text(encoding="utf-8")
        assert "suggest_quantity_range" not in text, f"{path} 觸及建議股數區間"
        assert "RANGE_ACTION_LABELS" not in text, f"{path} 觸及動作標籤表"
        for fragment in fragments:
            assert fragment not in text, f"{path} 出現建議股數區間文案片段「{fragment}」"


# --- The loop-bound fall-throughs (unreachable with a consistent budget) -----


def test_buy_sizing_gives_up_rather_than_suggesting_an_unverified_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # White-box: shrinking the adjustment bound to zero forces the fall-through
    # that a consistent budget never reaches. It must yield "no suggestion",
    # never an unverified share count.
    monkeypatch.setattr(limits, "MAX_SIZING_ADJUSTMENTS", 0)
    assert suggest_quantity_range(BUDGET, _ctx(), action="add") is None


def test_sell_sizing_gives_up_rather_than_suggesting_an_unverified_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same white-box premise on the sell side. It must behave like the buy side:
    # no suggestion at all. Reusing the "已為持股全數／由其他部位驅動" wording here
    # would state two facts this path never established.
    monkeypatch.setattr(limits, "MAX_SIZING_ADJUSTMENTS", 0)
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    assert suggest_quantity_range(BUDGET, ctx, action="reduce") is None


# --- A holding smaller than one whole share ---------------------------------


def _fractional_ctx() -> PortfolioContext:
    """A half-share holding that is the entire book, so the weight cap breaches.

    ``quantity`` is a Decimal in the position model, so half a share is a legal
    holding; a one-position book makes ``position_weight`` 100%, which always
    breaches the 15% cap. This combination is reachable in normal use, not a
    contrived edge.
    """
    return PortfolioContext(
        symbol="2330",
        total_equity_twd=50.0,
        position_market_value_twd=50.0,
        quantity=0.5,
        close=100.0,
    )


def test_a_sub_one_share_holding_really_does_breach_the_cap() -> None:
    # Guards the premise of the next test: if this stopped breaching, that test
    # would pass for the wrong reason.
    assert _status(_fractional_ctx(), "single_position_weight") == "violated"


def test_no_quantity_is_suggested_when_the_holding_is_under_one_share() -> None:
    # Rounding 0.5 shares up to "sell 1 share" would suggest more than the user
    # owns and call it 持股全數. No quantity, no claim.
    for action in ("reduce", "stop_loss", "take_profit"):
        assert suggest_quantity_range(BUDGET, _fractional_ctx(), action=action) is None


def test_a_holding_of_exactly_one_share_still_gets_a_suggestion() -> None:
    # The boundary the previous test guards must not swallow a legitimate case.
    ctx = _fractional_ctx().model_copy(
        update={
            "quantity": 1.0,
            "position_market_value_twd": 100.0,
            "total_equity_twd": 100.0,
        }
    )
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.min_shares == 1
    assert quantity.max_shares == 1


def test_a_suggested_sale_never_exceeds_the_holding() -> None:
    # The invariant behind both branches of the sell-side wording.
    for quantity_held, market_value in ((0.5, 50.0), (1.0, 100.0), (3.0, 300.0), (7.0, 700.0)):
        ctx = _fractional_ctx().model_copy(
            update={
                "quantity": quantity_held,
                "position_market_value_twd": market_value,
                "total_equity_twd": market_value,
            }
        )
        suggestion = suggest_quantity_range(BUDGET, ctx, action="reduce")
        if suggestion is None:
            continue
        assert suggestion.max_shares <= quantity_held
        assert suggestion.min_shares <= suggestion.max_shares


# --- A cap that cannot be evaluated is not a pass ----------------------------


def test_sizing_requires_an_explicit_pass_not_merely_a_non_violation() -> None:
    # ``not_evaluable`` means "we could not check", which must never be counted
    # as "inside the budget" when sizing a suggested quantity.
    ctx = _ctx()
    assert limits._passes(BUDGET, ctx, binding_id="single_position_weight", share_delta=1.0)
    # Remove the equity input: the same cap becomes not_evaluable, and the
    # helper must report that as "not a pass".
    blind = ctx.model_copy(update={"total_equity_twd": None})
    assert (
        limits.limit_status_after(
            BUDGET, blind, limit_id="single_position_weight", share_delta=1.0
        )
        == "not_evaluable"
    )
    assert not limits._passes(
        BUDGET, blind, binding_id="single_position_weight", share_delta=1.0
    )


def test_reduce_range_is_none_for_a_compliant_position() -> None:
    assert suggest_quantity_range(BUDGET, _ctx(), action="reduce") is None


def test_hold_and_unknown_actions_get_no_range() -> None:
    over = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    assert suggest_quantity_range(BUDGET, over, action="hold") is None
    assert suggest_quantity_range(BUDGET, over, action="insufficient_data") is None


def test_stop_loss_and_take_profit_share_the_reduce_sizing() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    for action in ("stop_loss", "take_profit"):
        quantity = suggest_quantity_range(BUDGET, ctx, action=action)
        assert quantity is not None
        assert quantity.min_shares == 501


# --- Context helpers ---------------------------------------------------------


def test_position_weight_and_pnl_helpers() -> None:
    ctx = _ctx()
    assert ctx.position_weight() == pytest.approx(0.05)
    assert ctx.unrealized_pnl_pct() == pytest.approx(0.25)
    assert ctx.price_twd() == pytest.approx(100.0)
    assert ctx.held_shares() == pytest.approx(500.0)


def test_helpers_return_none_on_missing_inputs() -> None:
    assert _ctx(total_equity_twd=0.0).position_weight() is None
    assert _ctx(position_cost_twd=None).unrealized_pnl_pct() is None
    assert _ctx(position_cost_twd=0.0).unrealized_pnl_pct() is None
    assert _ctx(close=None).price_twd() is None
    assert _ctx(quantity=None, close=None).held_shares() is None
    assert _ctx(quantity=None).held_shares() == pytest.approx(500.0)
    assert _ctx(position_market_value_twd=None).unrealized_pnl_pct() is None
