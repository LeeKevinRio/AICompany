"""Tests for the risk budget: every cap, in all three states, plus sizing."""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from app.advice import limits
from app.advice.limits import (
    KELLY_STALE_AFTER_DAYS,
    LIMIT_IDS,
    LIMIT_NAMES,
    MAX_GROSS_EXPOSURE_CEILING,
    MAX_POSITION_WEIGHT_CEILING,
    NET_WORTH_SOFT_NOTICE_DAYS,
    NET_WORTH_STALE_AFTER_DAYS,
    NO_SECTOR_CANDIDATE_DETAIL,
    NO_SECTOR_DETAILS,
    NO_SECTOR_ETF_CAUSE_DETAIL,
    NO_SECTOR_ETF_DETAIL,
    NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL,
    NO_SECTOR_UNFILED_DETAIL,
    NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL,
    NO_SECTOR_UNSUPPORTED_MARKET_DETAIL,
    NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL,
    RANGE_ACTION_LABELS,
    SECTOR_MIXED_DETAIL,
    KellyInputs,
    KellyInputSource,
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
from app.api import kelly_wording as wording
from app.kelly import models as kelly_models
from app.kelly.models import KellyInputRow, ageing_of
from tests.advice_helpers import kelly_inputs, reported_net_worth

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
        ("etf_instrument", NO_SECTOR_ETF_DETAIL),
        ("unsupported_market", NO_SECTOR_UNSUPPORTED_MARKET_DETAIL),
        ("mixed", SECTOR_MIXED_DETAIL),
    ],
)
def test_each_way_the_sector_is_missing_gets_its_own_sentence(gap: str, expected: str) -> None:
    # AC-12.3 as risk-compliance settled it on 2026-08-09: distinct states,
    # distinct sentences, none of them shared. The 2026-08-09 texts and the ETF
    # one (D6 + R-D6-1, 2026-08-16) are all risk-approved copy, asserted
    # verbatim rather than by keyword.
    check = _check(_ctx(sector_gap=gap), "sector_weight")
    assert check.status == "not_evaluable"
    assert check.detail == expected
    assert len({*NO_SECTOR_DETAILS.values()}) == len(NO_SECTOR_DETAILS)


def test_the_etf_sentence_is_the_risk_approved_wording_character_for_character() -> None:
    # R-D6-1 (2026-08-16): both sentences are risk-approved copy pinned here in
    # full. Any edit -- including punctuation -- is a wording drift that has to
    # go back to risk-compliance before it ships.
    assert NO_SECTOR_ETF_DETAIL == (
        "此標的的持倉為 ETF；台灣證交所產業別分類僅適用於個股，不適用於 ETF，"
        "單一產業佔比上限本次不計算，回報 not_evaluable。"
        "本上限不計算，不代表此 ETF 沒有產業集中風險；系統目前無法就此評估。"
    )
    assert NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL == (
        "本上限不計算，不代表此 ETF 沒有產業集中風險；系統目前無法就此評估。"
    )


def test_the_etf_cause_never_ships_without_the_residual_risk_disclosure() -> None:
    # R-D6-1's whole point: "the cap did not run" must not be readable as
    # "there is nothing to worry about". The two sentences are one constant, so
    # there must be no reachable string that carries the cause alone -- neither
    # in the mapping every caller reads, nor out of the check itself.
    assert NO_SECTOR_ETF_DETAIL.startswith(NO_SECTOR_ETF_CAUSE_DETAIL)
    assert NO_SECTOR_ETF_DETAIL.endswith(NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL)
    for detail in NO_SECTOR_DETAILS.values():
        assert (NO_SECTOR_ETF_CAUSE_DETAIL in detail) == (
            NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL in detail
        )
    detail = _check(_ctx(sector_gap="etf_instrument"), "sector_weight").detail
    assert NO_SECTOR_ETF_CAUSE_DETAIL in detail
    assert NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL in detail


def test_the_residual_risk_sentence_is_not_reused_on_any_other_state() -> None:
    # The "此 ETF" subject is only true on the ETF state. ``unsupported_market``
    # now carries its own approved disclosure (D8 句 2, 2026-08-19) as a
    # separate constant with its own subject; copying the ETF sentence there
    # would be publishing copy that was never reviewed for that state.
    for gap, detail in NO_SECTOR_DETAILS.items():
        if gap == "etf_instrument":
            continue
        assert NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL not in detail


def test_the_unsupported_market_sentences_are_the_risk_approved_wording_verbatim() -> None:
    # D8 句 2 (2026-08-19, work/reviews/2026-08-19-三句補充揭露-風控批審.md):
    # both halves and their concatenation are risk-approved copy pinned here in
    # full. Any edit -- including punctuation -- is a wording drift that has to
    # go back to risk-compliance before it ships.
    assert NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL == (
        "此標的為非台股持倉；系統目前只提供台灣證交所產業別分類，"
        "尚未決定其他市場的分類方式，單一產業佔比上限本次不計算，回報 not_evaluable。"
    )
    assert NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL == (
        "本上限不計算，不代表此持倉沒有產業集中風險；系統目前無法就此評估。"
    )
    assert NO_SECTOR_UNSUPPORTED_MARKET_DETAIL == (
        "此標的為非台股持倉；系統目前只提供台灣證交所產業別分類，"
        "尚未決定其他市場的分類方式，單一產業佔比上限本次不計算，回報 not_evaluable。"
        "本上限不計算，不代表此持倉沒有產業集中風險；系統目前無法就此評估。"
    )


def test_the_unsupported_market_cause_never_ships_without_its_residual_disclosure() -> None:
    # Same construction as R-D6-1: the two sentences are one constant, in a
    # fixed order, and the mapping every caller reads holds only the
    # concatenated form -- so no reachable string carries the cause alone.
    assert NO_SECTOR_UNSUPPORTED_MARKET_DETAIL.startswith(
        NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL
    )
    assert NO_SECTOR_UNSUPPORTED_MARKET_DETAIL.endswith(
        NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL
    )
    assert NO_SECTOR_DETAILS["unsupported_market"] == NO_SECTOR_UNSUPPORTED_MARKET_DETAIL
    for detail in NO_SECTOR_DETAILS.values():
        assert (NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL in detail) == (
            NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL in detail
        )
    detail = _check(_ctx(sector_gap="unsupported_market"), "sector_weight").detail
    assert NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL in detail
    assert NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL in detail


def test_the_unsupported_market_residual_is_its_own_constant_not_the_etf_one() -> None:
    # 風控落地條件 (2026-08-19): the two residual sentences must not share a
    # constant -- each is pinned verbatim by its own test, so neither can be
    # edited through the other. Their subjects differ ("此持倉" vs "此 ETF").
    assert (
        NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL != NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL
    )
    assert "此持倉" in NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL
    assert "此 ETF" not in NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL


def test_the_unsupported_market_residual_is_not_applied_to_the_other_states() -> None:
    # The 2026-08-19 approval covers ``unsupported_market`` only: ``unfiled``,
    # ``mixed`` and ``no_position`` were not reviewed for this sentence, so it
    # must not appear on them.
    for gap, detail in NO_SECTOR_DETAILS.items():
        if gap == "unsupported_market":
            continue
        assert NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL not in detail
    for gap in ("unfiled", "mixed", "no_position"):
        detail = _check(_ctx(sector_gap=gap), "sector_weight").detail
        assert NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL not in detail


def test_a_candidate_is_not_told_to_fill_in_a_holding_it_does_not_have() -> None:
    # Nothing is held, so there is no position to file a category on: the
    # sentence states what was not computed and stops there.
    detail = _check(_ctx(sector_gap="no_position"), "sector_weight").detail
    assert "填入" not in detail
    assert "not_evaluable" in detail


def test_an_etf_is_not_told_to_fill_in_a_category_that_does_not_apply() -> None:
    # D6: TWSE's taxonomy classifies companies, not funds, so the ETF sentence
    # must state that inapplicability and never carry the fill-in guidance --
    # that was exactly the misleading instruction the CEO's 2026-08-13 實測
    # reported for 00631L/00685L/00981A.
    detail = _check(_ctx(sector_gap="etf_instrument"), "sector_weight").detail
    assert "填入" not in detail
    assert "尚未填寫" not in detail
    assert "啟用這條上限" not in detail
    assert "ETF" in detail
    assert "不適用" in detail


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
    assert kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(0.6, 2.0))) == pytest.approx(0.1)
    # A huge edge is still capped at 10%.
    assert kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(0.9, 5.0))) == pytest.approx(0.1)
    # Quarter of 0.2 = 0.05, below the hard cap.
    assert kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(0.6, 1.0))) == pytest.approx(0.05)
    # A negative edge allows nothing.
    assert kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(0.3, 1.0))) == 0.0


def test_kelly_allowed_weight_is_none_for_a_pair_the_cap_will_not_use() -> None:
    """D-4/D-6: an absent, unanchorable or expired pair sizes nothing.

    Stated on ``kelly_allowed_weight`` and not only on the check, because this
    is the function ``notional_caps`` calls: a pair that stopped being usable
    must stop producing a TWD ceiling in the same breath, or the card would say
    ``not_evaluable`` while the quantity range kept sizing from it.
    """
    assert kelly_allowed_weight(BUDGET, _ctx()) is None
    assert (
        kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(age_days=None, anchored_at=None)))
        is None
    )
    assert (
        kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS)))
        is None
    )
    # The last day inside the window still computes.
    assert (
        kelly_allowed_weight(BUDGET, _ctx(kelly=kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS - 1)))
        is not None
    )


def test_kelly_passed_when_the_position_fits_the_edge() -> None:
    ctx = _ctx(kelly=kelly_inputs(0.6, 2.0), position_market_value_twd=50_000.0)
    check = _check(ctx, "kelly_fraction")
    assert check.status == "passed"
    assert check.threshold == pytest.approx(0.1)


def test_kelly_violated_when_the_position_exceeds_the_edge() -> None:
    ctx = _ctx(kelly=kelly_inputs(0.6, 1.0), position_market_value_twd=80_000.0)
    check = _check(ctx, "kelly_fraction")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.08)
    assert check.threshold == pytest.approx(0.05)


def test_kelly_not_evaluable_without_position_weight() -> None:
    ctx = _ctx(kelly=kelly_inputs(0.6, 2.0), position_market_value_twd=None)
    assert _status(ctx, "kelly_fraction") == "not_evaluable"


# --- Cap 5's boundary with the storage layer (約束 12/13/36/37) --------------


def test_the_freshness_window_matches_the_one_the_storage_layer_publishes() -> None:
    """Two declarations of one window, pinned equal.

    ``limits.py`` may not import ``app/kelly`` (約束 12) and ``app/kelly`` may not
    import ``app/advice`` (約束 13), so the constant is spelled out on both
    sides. They answer the same question -- may cap 5 still use this pair -- so
    a drift would have the settings page calling a pair usable while the cap
    refuses it, or the reverse.
    """
    assert KELLY_STALE_AFTER_DAYS == kelly_models.KELLY_STALE_AFTER_DAYS


def test_the_source_literal_matches_the_stored_one() -> None:
    """The same copy-not-import situation, for the值 (e)/(e-manual) branch on.

    A source this layer did not recognise would fall to the ``else`` arm and
    attach (e-manual) to an imported pair -- 落地條件 18's "掛錯" case.
    """
    assert set(get_args(KellyInputSource)) == set(get_args(kelly_models.KellySource))


@pytest.mark.parametrize(
    ("age_days", "anchored_at"), [(30, None), (None, "2026-06-30")]
)
def test_an_age_without_an_anchor_is_not_a_constructible_state(
    age_days: int | None, anchored_at: str | None
) -> None:
    """The two are ``None`` together or not at all.

    ``KellyAgeing`` only ever produces them as a pair, and the (g-2)/(g-3)
    sentences print both. Half a pair would render one of them from nothing --
    a date with no elapsed count, or a count anchored on nothing.
    """
    with pytest.raises(ValidationError):
        KellyInputs(
            win_rate=0.6,
            payoff_ratio=2.0,
            source="manual",
            age_days=age_days,
            anchored_at=anchored_at,
        )


def test_the_risk_layer_never_imports_the_kelly_package() -> None:
    """約束 12: no clock, no database, no storage types in this module."""
    imported = {
        (node.module or "")
        for node in ast.walk(ast.parse(Path(limits.__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }

    assert not any(module.startswith("app.kelly") for module in imported), sorted(imported)
    # The wording module is the one import this cap does need, and it is text
    # with no imports of its own (``tests/test_kelly_wording.py``).
    assert "app.api.kelly_wording" in imported


# --- Cap 5's four not-evaluable causes, verbatim (落地條件 1 / (g-1)..(g-4)) ---


def test_a_symbol_with_no_kelly_input_at_all_gets_g1_verbatim() -> None:
    """(g-1): nothing entered. The one state ``kelly=None`` stands for."""
    check = _check(_ctx(), "kelly_fraction")

    assert check.status == "not_evaluable"
    assert check.detail == (
        "此標的尚未輸入 Kelly 所需的勝率與盈虧比（可透過手動輸入或回測帶入取得），"
        "本條上限目前無法評估。"
    )
    # A refusal names no measured value (5-3): the pair is described, not shown.
    assert "%" not in check.detail


def test_an_expired_manual_pair_gets_g2_verbatim() -> None:
    """(g-2): typed by hand, past the window, anchored on the write stamp."""
    check = _check(
        _ctx(kelly=kelly_inputs(source="manual", age_days=41, anchored_at="2026-06-13")),
        "kelly_fraction",
    )

    assert check.status == "not_evaluable"
    assert check.detail == (
        "此標的的 Kelly 輸入（來源：手動輸入）已過期——上次更新於 2026-06-13，距今 41 天，"
        "超過 30 天的新鮮期，本條上限暫不評估；請重新確認數字後更新。"
    )


def test_an_expired_imported_pair_gets_g3_verbatim() -> None:
    """(g-3): imported, past the window, anchored on the OOS segment's end."""
    check = _check(
        _ctx(kelly=kelly_inputs(source="backtest", age_days=90, anchored_at="2026-05-25")),
        "kelly_fraction",
    )

    assert check.status == "not_evaluable"
    assert check.detail == (
        "此標的的 Kelly 輸入（來源：回測帶入）已過期——樣本外區段結束於 2026-05-25，"
        "距今 90 天，超過 30 天的新鮮期，本條上限暫不評估；"
        "請重新執行回測並確認後更新。"
    )


def test_an_expired_overridden_pair_gets_g_overridden_verbatim() -> None:
    """(g-overridden), 第七輪任務 9: imported, hand-adjusted, and now stale.

    It ages from the import's anchor -- mirroring
    :func:`app.kelly.models.anchor_moment`, where ``manual`` is the only source
    counting from the write stamp -- but neither neighbouring sentence states
    its source truthfully, which is why it has one of its own (條件 51/52).
    """
    check = _check(
        _ctx(
            kelly=kelly_inputs(
                source="backtest_overridden", age_days=31, anchored_at="2026-07-01"
            )
        ),
        "kelly_fraction",
    )

    assert check.status == "not_evaluable"
    assert check.detail == (
        "此標的的 Kelly 輸入（來源：回測帶入，已手動調整）已過期——"
        "樣本外區段結束於 2026-07-01，距今 31 天，超過 30 天的新鮮期，"
        "本條上限暫不評估；請重新執行回測並確認後更新。"
    )


def test_the_overridden_cell_no_longer_borrows_the_plain_backtest_sentence() -> None:
    """條件 52: the K4b stand-in is retired -- 掛錯非暫行.

    Until the seventh round there was no approved sentence for this cell and it
    showed (g-3), whose source parenthesis omits that the effective numbers are
    the user's own. That is a false statement about where a number came from,
    not a cosmetic gap, so the reverse assertion is kept permanently.
    """
    detail = _check(
        _ctx(kelly=kelly_inputs(source="backtest_overridden", age_days=31)), "kelly_fraction"
    ).detail

    assert wording.KELLY_NOT_EVALUABLE_BACKTEST_EXPIRED.format(
        anchored_on="2026-07-24", age_days=31, days=KELLY_STALE_AFTER_DAYS
    ) != detail
    assert "（來源：回測帶入）" not in detail
    assert "已手動調整" in detail


def test_a_pair_with_no_anchor_gets_g4_verbatim_and_no_invented_date() -> None:
    """(g-4): an imported pair with no OOS end date cannot be aged at all."""
    check = _check(
        _ctx(kelly=kelly_inputs(source="backtest", age_days=None, anchored_at=None)),
        "kelly_fraction",
    )

    assert check.status == "not_evaluable"
    assert check.detail == (
        "此標的的 Kelly 輸入（來源：回測帶入）缺少樣本外區段結束日，本系統無法判定其新鮮度，"
        "一律視為已過期，本條上限暫不評估；請重新執行回測並確認後更新。"
    )
    # 6-B: no anchor exists, so no stand-in date is invented for one.
    assert not re.search(r"\d{4}-\d{2}-\d{2}", check.detail)


#: The (g) table exactly as 第七輪併裁 wrote it and 第八輪 closed it: six cells,
#: keyed on (source, anchor state), with the no-row cell as the first. The
#: seventh cell of the Cartesian product -- (manual, unanchorable) -- is not in
#: the ruling's table because it cannot occur, and is asserted as such below
#: rather than being given a sentence (第八輪 E3).
G_TABLE_CELLS: tuple[tuple[str | None, bool, str], ...] = (
    (None, False, "g-1"),
    ("manual", False, "g-2"),
    ("backtest", False, "g-3"),
    ("backtest_overridden", False, "g-overridden"),
    ("backtest", True, "g-4"),
    ("backtest_overridden", True, "g-4-overridden"),
)


def test_the_g_table_is_mutually_exclusive_and_exhaustive_over_the_ruled_six() -> None:
    """條件 51: every cell of the review's own table resolves to its own句.

    Keyed on the ruling's six rather than on a Cartesian product, so the test
    and the table it is checking are the same object. Exhaustive because each
    cell must produce a sentence, and mutually exclusive because the six must be
    six *different* sentences -- a cell borrowing another's wording is a false
    statement about where the number came from, not a cosmetic overlap.
    """
    seen: dict[str, str] = {}
    for source, unanchored, item in G_TABLE_CELLS:
        kelly = (
            None
            if source is None
            else kelly_inputs(
                source=source,  # type: ignore[arg-type]
                # Anchored cells are aged past the window so all six are
                # not-evaluable; the unanchorable ones are expired by rule.
                age_days=None if unanchored else KELLY_STALE_AFTER_DAYS + 1,
                anchored_at=None if unanchored else "2026-07-24",
            )
        )
        check = _check(_ctx(kelly=kelly), "kelly_fraction")

        assert check.status == "not_evaluable", item
        assert check.detail, item
        # Each cell shows the sentence the review assigned to it, and that
        # sentence is in the approved inventory under that very id.
        assert check.detail == wording.RISK_CONFIRMED_WORDING[item].format(
            anchored_on="2026-07-24",
            age_days=KELLY_STALE_AFTER_DAYS + 1,
            days=KELLY_STALE_AFTER_DAYS,
        ), item
        seen[item] = check.detail

    assert len(seen) == 6
    assert len(set(seen.values())) == 6, "兩格共用同一句：(g) 表不再互斥"


def test_the_seventh_combination_is_unreachable_rather_than_answered() -> None:
    """(manual, 缺錨) has no cell because it cannot happen (第八輪 E2/E3).

    A hand-typed pair always carries the server's write stamp, so
    :func:`app.kelly.models.ageing_of` never returns a manual row with no
    anchor -- asserted here against the real ageing rule rather than assumed.
    Should that ever change, cap 5 raises instead of quietly borrowing a
    sentence that names a source the row does not have.
    """
    manual_row = KellyInputRow(
        symbol="2330",
        market="TW",
        win_rate=0.6,
        payoff_ratio=2.0,
        source="manual",
        updated_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert ageing_of(manual_row).anchored_at is not None

    with pytest.raises(ValueError, match="無對應的定稿說明句"):
        limits._kelly_not_evaluable_detail(
            KellyInputs(win_rate=0.6, payoff_ratio=2.0, source="manual")
        )


def test_an_unanchored_overridden_pair_gets_g4_overridden_verbatim() -> None:
    """(g-4-overridden), 第八輪組三: the sixth cell, closed (條件 66).

    Reachable for the reason the ruling gives:
    :meth:`app.kelly.models.KellyInputRecord.overriding` copies the provenance
    column by column, so a row that arrived with no OOS end date still has none
    after a hand edit.
    """
    check = _check(
        _ctx(kelly=kelly_inputs(source="backtest_overridden", age_days=None, anchored_at=None)),
        "kelly_fraction",
    )

    assert check.status == "not_evaluable"
    assert check.detail == (
        "此標的的 Kelly 輸入（來源：回測帶入，已手動調整）缺少樣本外區段結束日，"
        "本系統無法判定其新鮮度，一律視為已過期，本條上限暫不評估；"
        "請重新執行回測並確認後更新。"
    )
    # 6-B: no anchor exists, so no stand-in date is invented for one.
    assert not re.search(r"\d{4}-\d{2}-\d{2}", check.detail)


def test_the_sixth_cell_no_longer_borrows_the_plain_backtest_sentence() -> None:
    """第八輪 E1: the reverse assertion that replaces the xfail placeholder.

    Until the eighth round this cell showed (g-4), whose source parenthesis
    omits that the effective numbers are the user's own. Removing the xfail
    without replacing the positive "it still shows (g-4)" assertion with this
    one would have left the regression unguarded, which the review classed as
    BLOCKING -- so the guard is kept, pointing the other way.
    """
    detail = _check(
        _ctx(kelly=kelly_inputs(source="backtest_overridden", age_days=None, anchored_at=None)),
        "kelly_fraction",
    ).detail

    assert "（來源：回測帶入）" not in detail
    assert "已手動調整" in detail
    assert detail != wording.KELLY_NOT_EVALUABLE_NO_OOS_END_DATE
    assert detail in set(wording.RISK_CONFIRMED_WORDING.values())


def test_the_freshness_window_is_interpolated_and_never_written_out() -> None:
    """落地條件 9: the two expiry sentences carry the constant in force.

    A literal 30 would leave the sentence behind the day the window moves, so
    the assertion is that the rendered number tracks the constant rather than
    that it reads "30".
    """
    for source in ("manual", "backtest"):
        detail = _check(
            _ctx(kelly=kelly_inputs(source=source, age_days=999)),
            "kelly_fraction",
        ).detail
        assert f"超過 {KELLY_STALE_AFTER_DAYS} 天的新鮮期" in detail


def test_the_anchor_is_a_plain_date_and_never_an_iso_datetime() -> None:
    """6-A: a padded time of day would be precision the measurement lacks."""
    detail = _check(
        _ctx(kelly=kelly_inputs(source="manual", age_days=60, anchored_at="2026-06-01")),
        "kelly_fraction",
    ).detail

    assert "2026-06-01" in detail
    assert "T" not in detail
    assert "+00:00" not in detail and "Z" not in detail


def test_the_boundary_day_expires_and_the_day_before_it_does_not() -> None:
    """``>=`` at the window, the same direction every other cap breaches in."""
    inside = _check(
        _ctx(kelly=kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS - 1)), "kelly_fraction"
    )
    outside = _check(_ctx(kelly=kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS)), "kelly_fraction")

    assert inside.status != "not_evaluable"
    assert outside.status == "not_evaluable"
    assert "已過期" in outside.detail


# --- (e) / (e-manual) / (a-2): what travels with a shown win rate ------------


@pytest.mark.parametrize("status_source", ["backtest"])
def test_a_shown_backtest_win_rate_carries_e_verbatim(status_source: str) -> None:
    """落地條件 11/18: a sampled frequency gets (e), and only (e)."""
    detail = _check(
        _ctx(kelly=kelly_inputs(source=status_source), position_market_value_twd=50_000.0),  # type: ignore[arg-type]
        "kelly_fraction",
    ).detail

    assert wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY in detail
    assert wording.KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY not in detail


@pytest.mark.parametrize("source", ["manual", "backtest_overridden"])
def test_a_shown_hand_keyed_win_rate_carries_e_manual_verbatim(source: str) -> None:
    """落地條件 18: a hand-keyed pair is no sample frequency, so (e) would lie."""
    detail = _check(
        _ctx(kelly=kelly_inputs(source=source), position_market_value_twd=50_000.0),  # type: ignore[arg-type]
        "kelly_fraction",
    ).detail

    assert wording.KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY in detail
    assert wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY not in detail


def test_the_two_source_sentences_are_mutually_exclusive_and_exhaustive() -> None:
    """落地條件 18, as a property over every source there is.

    "掛空或掛錯即 BLOCKING": exactly one of the two must be attached, for each of
    the three sources and in both verdict states.
    """
    sources = get_args(KellyInputSource)
    assert set(sources) == {"manual", "backtest", "backtest_overridden"}

    for source in sources:
        for held in (50_000.0, 200_000.0):  # passed, then violated
            detail = _check(
                _ctx(kelly=kelly_inputs(source=source), position_market_value_twd=held),
                "kelly_fraction",
            ).detail
            attached = [
                sentence
                for sentence in (
                    wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY,
                    wording.KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY,
                )
                if sentence in detail
            ]
            assert len(attached) == 1, (source, held, attached)


def test_neither_source_sentence_is_attached_to_a_refusal() -> None:
    """A cap that used no number has no shown win rate to qualify (5-3)."""
    for kelly in (None, kelly_inputs(age_days=99), kelly_inputs(age_days=None, anchored_at=None)):
        detail = _check(_ctx(kelly=kelly), "kelly_fraction").detail
        assert wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY not in detail
        assert wording.KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY not in detail
        assert wording.KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE not in detail


def test_the_no_edge_flag_attaches_a2_verbatim_after_the_source_sentence() -> None:
    """(a-2) 落地: 約束 36's boolean branch, in the order the module documents."""
    detail = _check(
        _ctx(
            kelly=kelly_inputs(ci_includes_no_edge=True),
            position_market_value_twd=50_000.0,
        ),
        "kelly_fraction",
    ).detail

    assert wording.KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE in detail
    assert detail.index(wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY) < detail.index(
        wording.KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE
    )
    # 落地條件 7: (a-2) is the flag version precisely because no interval number
    # is shown beside it, and the banned framings may not appear either.
    for banned in ("信賴區間", "信心水準", "有 95% 的機率落在", "建議比例", "最佳倉位"):
        assert banned not in detail


def test_a_clear_interval_attaches_nothing() -> None:
    """The flag asserts a finding; a false one is not a finding of the reverse."""
    detail = _check(
        _ctx(kelly=kelly_inputs(ci_includes_no_edge=False), position_market_value_twd=50_000.0),
        "kelly_fraction",
    ).detail

    assert wording.KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE not in detail


def test_the_detail_is_one_assembled_string() -> None:
    """The verdict, the numbers and the disclosures reach the card as one field."""
    check = _check(
        _ctx(kelly=kelly_inputs(ci_includes_no_edge=True), position_market_value_twd=50_000.0),
        "kelly_fraction",
    )

    assert isinstance(check.detail, str)
    assert check.detail.startswith("以勝率 ")
    assert check.detail.endswith(wording.KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE)


# --- Precision of the two shown numbers (分歧① required 5) -------------------


def test_the_shown_pair_is_printed_at_a_precision_the_sample_supports() -> None:
    """分歧① required 5: ``:g``'s six significant digits were false precision."""
    detail = _check(
        _ctx(kelly=kelly_inputs(0.625, 1.8327429), position_market_value_twd=50_000.0),
        "kelly_fraction",
    ).detail

    assert "以勝率 62.5%、盈虧比 1.83 計算" in detail
    # The rejected rendering, pinned so a revert is visible.
    assert "1.83274" not in detail
    assert "62.50%" not in detail


def test_the_two_shown_numbers_keep_a_fixed_width() -> None:
    """A whole-number ratio keeps its decimals; ``:g`` would drop them."""
    detail = _check(
        _ctx(kelly=kelly_inputs(0.6, 2.0), position_market_value_twd=50_000.0), "kelly_fraction"
    ).detail

    assert "以勝率 60.0%、盈虧比 2.00 計算" in detail


# --- f*<=0: the cap that allows nothing (D-5, 第六輪 任務 1/2) ---------------

#: w=0.3, b=1.0 -> f* = 0.3 - 0.7/1.0 = -0.4, so the allowance is exactly 0.
NO_EDGE = (0.3, 1.0)


def test_a_non_positive_edge_is_violated_with_its_own_sentence() -> None:
    """D-5 / 條件 40: the dedicated sentence, and none of the general phrasing.

    The ordinary wording ("目前佔比 X 已達或超過該上限") would be read as a demand
    to sell down to a cap of zero, which is the reading D-5 forbids the cap from
    producing.
    """
    check = _check(_ctx(kelly=kelly_inputs(*NO_EDGE)), "kelly_fraction")

    assert check.status == "violated"
    assert check.detail == wording.KELLY_NON_POSITIVE_FRACTION_DETAIL
    assert "已達或超過該上限" not in check.detail
    assert check.threshold == 0.0
    # 約束 11: no operating verb of any kind in this branch.
    for banned in ("建議", "應該", "賣出", "清倉", "減碼至", "最佳倉位"):
        assert banned not in check.detail


def test_the_non_positive_sentence_appears_on_no_other_branch() -> None:
    """條件 40 反向斷言: f*>0, and every not-evaluable cause, must not carry it."""
    others = [
        _ctx(kelly=kelly_inputs(0.6, 2.0)),
        _ctx(kelly=kelly_inputs(0.6, 2.0), position_market_value_twd=200_000.0),
        _ctx(),
        _ctx(kelly=kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS)),
        _ctx(kelly=kelly_inputs(age_days=None, anchored_at=None)),
    ]
    for ctx in others:
        detail = _check(ctx, "kelly_fraction").detail
        assert wording.KELLY_NON_POSITIVE_FRACTION_DETAIL not in detail


def test_the_non_positive_sentence_precedes_the_interval_flag() -> None:
    """條件 41: 任務 1 句在前、(a-2) 在後，順序屬定稿一部分."""
    detail = _check(
        _ctx(kelly=kelly_inputs(*NO_EDGE, ci_includes_no_edge=True)), "kelly_fraction"
    ).detail

    assert detail.startswith(wording.KELLY_NON_POSITIVE_FRACTION_DETAIL)
    assert detail.endswith(wording.KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE)


def test_a_non_positive_edge_is_not_listed_as_missing_data() -> None:
    """條件 35: the skipped sentence says the cap lacked data; here it had data.

    Cap 5 computed from a real pair and arrived at a definite zero, so putting
    it in that list would be a false statement -- and one that sits next to the
    (任務 2) sentence saying the opposite.
    """
    # Every other cap is evaluable here, so cap 5 is the only candidate for the
    # skipped list -- and the list must come out empty, leaving no "missing
    # data" sentence on the card at all.
    ctx = _ctx(
        sector="半導體業",
        sector_market_value_twd=200_000.0,
        kelly=kelly_inputs(*NO_EDGE),
    )
    quantity = suggest_quantity_range(BUDGET, ctx, action="add")

    assert quantity is not None
    assert "缺少可用資料" not in quantity.basis
    assert "未參與這個區間的計算" not in quantity.basis
    # It is disclosed, just by the sentence that describes what actually happened.
    assert wording.KELLY_ZERO_ALLOWANCE_RANGE_NOTE in quantity.basis


def test_an_unusable_pair_is_still_listed_as_missing_data() -> None:
    """The other side of 條件 35: absent or expired really is missing data."""
    for kelly in (None, kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS)):
        quantity = suggest_quantity_range(BUDGET, _ctx(kelly=kelly), action="add")
        assert quantity is not None
        assert "缺少可用資料" in quantity.basis
        assert LIMIT_NAMES["kelly_fraction"] in quantity.basis
        assert wording.KELLY_ZERO_ALLOWANCE_RANGE_NOTE not in quantity.basis


@pytest.mark.parametrize("action", ["reduce", "stop_loss", "take_profit"])
def test_the_zero_allowance_sentence_travels_with_the_sell_side_range(action: str) -> None:
    """條件 36/37: the reachable case, verbatim, as a whole sentence at the end."""
    ctx = _ctx(
        kelly=kelly_inputs(*NO_EDGE),
        position_market_value_twd=200_000.0,
        quantity=2_000.0,
    )
    quantity = suggest_quantity_range(BUDGET, ctx, action=action)

    assert quantity is not None
    assert wording.KELLY_ZERO_ALLOWANCE_RANGE_NOTE in quantity.basis
    assert quantity.basis.endswith(wording.KELLY_ZERO_ALLOWANCE_RANGE_NOTE)
    # A whole sentence appended after a full stop, never spliced into another.
    head = quantity.basis[: -len(wording.KELLY_ZERO_ALLOWANCE_RANGE_NOTE)]
    assert head.endswith("。")


@pytest.mark.parametrize("action", ["reduce", "stop_loss", "take_profit"])
def test_cap_5_is_never_the_binding_cap_on_a_sell_side_range(action: str) -> None:
    """條件 34 反向斷言: no sell quantity may be derived from a zero allowance."""
    ctx = _ctx(
        kelly=kelly_inputs(*NO_EDGE),
        position_market_value_twd=200_000.0,
        quantity=2_000.0,
    )
    quantity = suggest_quantity_range(BUDGET, ctx, action=action)

    assert quantity is not None
    assert f"「{LIMIT_NAMES['kelly_fraction']}」這條上限" not in quantity.basis
    assert "kelly_fraction" not in notional_caps(BUDGET, ctx)


def test_a_positive_edge_carries_no_zero_allowance_sentence() -> None:
    """The sentence states a finding; a cap that did size something has none."""
    quantity = suggest_quantity_range(
        BUDGET, _ctx(kelly=kelly_inputs(0.6, 2.0)), action="add"
    )

    assert quantity is not None
    assert wording.KELLY_ZERO_ALLOWANCE_RANGE_NOTE not in quantity.basis


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


def test_a_non_positive_edge_is_excluded_from_the_notional_caps() -> None:
    """ADR-0006 D-5: f*<=0 leaves cap 5 out of the sizing inputs entirely.

    Not "included as 0". A zero binding cap is turned into a share count by
    :func:`suggest_quantity_range`, i.e. into a "sell the whole holding"
    quantity derived from an estimate whose only content is "no edge was
    measured". The cap still reports ``violated``; it just sizes nothing, and
    the fifth batch's f*<=0 sentence rests on this being true of the code.
    """
    # w=0.3, b=1.0 -> f* = 0.3 - 0.7/1.0 = -0.4.
    ctx = _ctx(kelly=kelly_inputs(*NO_EDGE))
    full = kelly_fraction(*NO_EDGE)
    assert full is not None and full <= 0.0

    caps = notional_caps(BUDGET, ctx)

    assert "kelly_fraction" not in caps
    assert caps.get("kelly_fraction") != 0.0
    # The verdict itself is unaffected: the cap is still reported, still binding.
    assert _status(ctx, "kelly_fraction") == "violated"


def test_an_unusable_pair_is_excluded_from_the_notional_caps() -> None:
    """No sizing may be derived from a cap the card reports ``not_evaluable``."""
    for kelly in (
        None,
        kelly_inputs(age_days=KELLY_STALE_AFTER_DAYS),
        kelly_inputs(age_days=None, anchored_at=None),
    ):
        ctx = _ctx(kelly=kelly)
        assert _status(ctx, "kelly_fraction") == "not_evaluable"
        assert "kelly_fraction" not in notional_caps(BUDGET, ctx)


def test_notional_caps_include_sector_and_kelly_when_available() -> None:
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0, kelly=kelly_inputs(0.6, 2.0))
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
    ctx = _ctx(sector="半導體業", sector_market_value_twd=200_000.0, kelly=kelly_inputs(0.6, 2.0))
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
