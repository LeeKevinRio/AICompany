"""Tests for the book-level risk caps (``app/advice/book_limits.py``, FR-8).

The point of every case here is the same: the aggregate must say exactly what
the per-symbol caps say, about the worst holding, and must never let a cap it
could not evaluate look like a cap that passed.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.advice.book import EQUITY_BASIS_NOTE, SYMBOL_UNVALUED_NOTE
from app.advice.book_limits import (
    EMPTY_BOOK_DETAIL,
    EXCLUDED_SUFFIX,
    NO_CANDIDATE_DETAILS,
    SECTOR_UNVALUED_EXCLUSION_SUFFIX,
    UNVALUED_EXCLUSION_SUFFIX,
    WORST_SECTOR_PREFIX,
    WORST_SYMBOL_PREFIX,
    BookLimitCheck,
    BookLimits,
    SymbolMarketInput,
    evaluate_book_limits,
)
from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    NET_WORTH_STALE_AFTER_DAYS,
    NO_NET_WORTH_DETAIL,
    NO_SECTOR_UNFILED_DETAIL,
    NO_SECTOR_UNSUPPORTED_MARKET_DETAIL,
    SECTOR_MIXED_DETAIL,
    RiskBudget,
    SelfReportedNetWorth,
    format_percent,
)
from app.portfolio.summary import PortfolioSummary
from app.positions.models import Market
from tests.advice_helpers import book_position, book_summary, reported_net_worth

BUDGET = RiskBudget()


def _by_id(report: BookLimits) -> dict[str, BookLimitCheck]:
    return {check.limit_id: check for check in report.limits}


def _report(
    summary: PortfolioSummary,
    *,
    budget: RiskBudget = BUDGET,
    net_worth: SelfReportedNetWorth | None = None,
    market_data: Mapping[tuple[str, Market], SymbolMarketInput] | None = None,
) -> dict[str, BookLimitCheck]:
    return _by_id(
        evaluate_book_limits(summary, budget, net_worth=net_worth, market_data=market_data)
    )


# --- shape -------------------------------------------------------------------


def test_every_cap_is_reported_once_in_the_fixed_order() -> None:
    report = evaluate_book_limits(book_summary(book_position(1, "2330")), BUDGET)
    assert [check.limit_id for check in report.limits] == list(LIMIT_IDS)
    assert [check.index for check in report.limits] == [1, 2, 3, 4, 5]


def test_the_book_notes_travel_with_the_verdicts() -> None:
    report = evaluate_book_limits(book_summary(book_position(1, "2330")), BUDGET)
    # The equity assumption is stated on the book, not left for the reader.
    assert EQUITY_BASIS_NOTE in report.notes


# --- cap 1: worst holding ----------------------------------------------------


def test_the_worst_holding_drives_the_single_position_cap() -> None:
    # 2330 is 60% of the book, 2454 is 40%: the cap must report the 60% one.
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="600"),
            book_position(2, "2454", quantity="400"),
        )
    )
    cap = checks["single_position_weight"]
    assert cap.worst_symbol == "2330"
    assert cap.status == "violated"  # 60% is far past the 15% default
    assert cap.observed == 0.6
    assert cap.threshold == BUDGET.max_position_weight
    assert cap.evaluated_count == 2
    assert cap.excluded == []
    # The per-symbol sentence is quoted verbatim inside the aggregate.
    assert WORST_SYMBOL_PREFIX.format(count=2, symbol="2330") in cap.detail
    assert f"2330 佔總資產 {format_percent(0.6)}" in cap.detail


def test_a_book_inside_the_cap_reports_the_highest_weight_as_passed() -> None:
    checks = _report(
        book_summary(*(book_position(i, f"000{i}", quantity="100") for i in range(1, 11)))
    )
    cap = checks["single_position_weight"]
    assert cap.status == "passed"
    assert cap.observed is not None and abs(cap.observed - 0.1) < 1e-9
    assert cap.evaluated_count == 10


def test_a_violated_holding_outranks_a_passing_one() -> None:
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="100"),
            book_position(2, "2454", quantity="900"),
        )
    )
    assert checks["single_position_weight"].worst_symbol == "2454"
    assert checks["single_position_weight"].status == "violated"


def test_the_same_ticker_in_two_markets_is_two_holdings() -> None:
    # Two instruments in two currencies: merging them would put one weight on
    # both. The US leg cannot be valued here, so it is withheld, not merged.
    checks = _report(
        book_summary(
            book_position(1, "2330", market="TW"),
            book_position(2, "2330", market="US", currency="USD", price=None),
        )
    )
    cap = checks["single_position_weight"]
    assert cap.evaluated_count == 1
    assert [entry.market for entry in cap.excluded] == ["US"]


# --- cap 2: worst industry ---------------------------------------------------


def test_the_worst_industry_drives_the_sector_cap() -> None:
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="400", sector="半導體業"),
            book_position(2, "2454", quantity="300", sector="半導體業"),
            book_position(3, "2882", quantity="300", sector="金融保險業"),
        )
    )
    cap = checks["sector_weight"]
    assert cap.status == "violated"  # 70% against a 30% default
    assert cap.observed is not None and abs(cap.observed - 0.7) < 1e-9
    # Industries are compared, not holdings: two semiconductor rows are one
    # industry, so the count is 2 and no symbol is named as "the worst".
    assert cap.evaluated_count == 2
    assert cap.worst_symbol is None
    assert WORST_SECTOR_PREFIX.format(count=2) in cap.detail
    assert "半導體業 產業佔總資產" in cap.detail


def test_holdings_with_no_industry_are_excluded_with_their_own_reason() -> None:
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="100", sector="半導體業"),
            book_position(2, "2454", quantity="900"),
        )
    )
    cap = checks["sector_weight"]
    assert cap.status == "passed"
    assert cap.evaluated_count == 1
    assert [entry.symbol for entry in cap.excluded] == ["2454"]
    # Verbatim approved copy, not a paraphrase invented here.
    assert cap.excluded[0].reason == NO_SECTOR_UNFILED_DETAIL
    assert EXCLUDED_SUFFIX.format(count=1) in cap.detail


def test_an_unclassifiable_market_keeps_its_own_sentence() -> None:
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="500", sector="半導體業"),
            book_position(2, "AAPL", market="US", currency="USD", quantity="500"),
        )
    )
    reasons = [entry.reason for entry in checks["sector_weight"].excluded]
    assert NO_SECTOR_UNSUPPORTED_MARKET_DETAIL in reasons


def test_one_symbol_filed_under_two_industries_keeps_the_mixed_sentence() -> None:
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="500", sector="半導體業"),
            book_position(2, "2330", quantity="500", sector="金融保險業"),
        )
    )
    cap = checks["sector_weight"]
    assert cap.status == "not_evaluable"
    assert cap.detail == NO_CANDIDATE_DETAILS["sector_weight"]
    assert [entry.reason for entry in cap.excluded] == [SECTOR_MIXED_DETAIL]


def test_a_book_with_no_industry_at_all_is_not_evaluable_not_passed() -> None:
    checks = _report(book_summary(book_position(1, "2330"), book_position(2, "2454")))
    cap = checks["sector_weight"]
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    assert cap.threshold == BUDGET.max_sector_weight
    assert len(cap.excluded) == 2


# --- cap 3: the book's own number --------------------------------------------


def test_gross_exposure_without_a_reported_net_worth_keeps_its_old_sentence() -> None:
    checks = _report(book_summary(book_position(1, "2330")))
    cap = checks["gross_exposure"]
    assert cap.status == "not_evaluable"
    assert cap.detail == NO_NET_WORTH_DETAIL
    assert cap.worst_symbol is None
    assert cap.evaluated_count == 0


def test_gross_exposure_is_computed_once_for_the_whole_book() -> None:
    # 600,000 of valued book against a 1,000,000 net worth: one book-level ratio.
    checks = _report(
        book_summary(book_position(1, "2330")), net_worth=reported_net_worth(1_000_000.0)
    )
    cap = checks["gross_exposure"]
    assert cap.status == "passed"
    assert cap.observed == 0.6
    assert "組合總曝險" in cap.detail
    assert "分子（已估值部位市值合計）由系統計算" in cap.detail


def test_gross_exposure_is_withheld_when_a_position_cannot_be_valued() -> None:
    checks = _report(
        book_summary(book_position(1, "2330"), book_position(2, "2454", price=None)),
        net_worth=reported_net_worth(1_000_000.0),
    )
    cap = checks["gross_exposure"]
    assert cap.status == "not_evaluable"
    assert "分子漏算只會讓曝險看起來偏低" in cap.detail


def test_an_expired_net_worth_takes_the_exposure_cap_back_off() -> None:
    checks = _report(
        book_summary(book_position(1, "2330")),
        net_worth=reported_net_worth(1_000_000.0, age_days=NET_WORTH_STALE_AFTER_DAYS),
    )
    cap = checks["gross_exposure"]
    assert cap.status == "not_evaluable"
    assert f"淨值輸入已超過 {NET_WORTH_STALE_AFTER_DAYS} 天未更新" in cap.detail


# --- cap 4: worst stop-out loss ----------------------------------------------


def test_the_worst_stop_out_loss_drives_the_per_trade_cap() -> None:
    summary = book_summary(
        book_position(1, "2330", quantity="500"),
        book_position(2, "2454", quantity="500"),
    )
    checks = _report(
        summary,
        market_data={
            ("2330", "TW"): SymbolMarketInput(close=600.0, currency="TWD", atr=30.0),
            ("2454", "TW"): SymbolMarketInput(close=600.0, currency="TWD", atr=5.0),
        },
    )
    cap = checks["per_trade_loss"]
    assert cap.worst_symbol == "2330"
    assert cap.status == "violated"
    # 500 shares x 2 x 30 = 30,000 of a 600,000 book = 5%.
    assert cap.observed is not None and abs(cap.observed - 0.05) < 1e-9
    assert cap.evaluated_count == 2


def test_holdings_with_no_atr_are_excluded_and_counted_not_passed() -> None:
    summary = book_summary(
        book_position(1, "2330", quantity="500"),
        book_position(2, "2454", quantity="500"),
    )
    checks = _report(
        summary,
        market_data={("2330", "TW"): SymbolMarketInput(close=600.0, currency="TWD", atr=1.0)},
    )
    cap = checks["per_trade_loss"]
    assert cap.status == "passed"
    assert cap.worst_symbol == "2330"
    assert cap.evaluated_count == 1
    assert [entry.symbol for entry in cap.excluded] == ["2454"]
    assert cap.excluded[0].reason.startswith("缺少 ATR(14)")
    assert EXCLUDED_SUFFIX.format(count=1) in cap.detail


def test_no_atr_anywhere_leaves_the_cap_not_evaluable() -> None:
    checks = _report(book_summary(book_position(1, "2330")))
    cap = checks["per_trade_loss"]
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    assert cap.detail == NO_CANDIDATE_DETAILS["per_trade_loss"]
    assert cap.threshold == BUDGET.max_loss_per_trade


def test_a_foreign_holding_without_a_rate_is_excluded_rather_than_converted() -> None:
    # No FX quote, so the price and ATR are withheld upstream (ADR-0005 F-1/F-2)
    # and this cap cannot be computed for that holding -- it must not be sized
    # with an invented 1.0 rate.
    checks = _report(
        book_summary(
            book_position(1, "AAPL", market="US", currency="USD", quantity="100", price="200")
        ),
        market_data={("AAPL", "US"): SymbolMarketInput(close=200.0, currency="USD", atr=4.0)},
    )
    cap = checks["per_trade_loss"]
    assert cap.status == "not_evaluable"
    assert [entry.symbol for entry in cap.excluded] == ["AAPL"]


# --- cap 5 -------------------------------------------------------------------


def test_kelly_has_no_data_source_and_says_so() -> None:
    checks = _report(book_summary(book_position(1, "2330")))
    cap = checks["kelly_fraction"]
    assert cap.status == "not_evaluable"
    assert "目前沒有資料來源提供這兩項輸入" in cap.detail
    assert cap.threshold is None


# --- unvalued holdings -------------------------------------------------------


def test_a_holding_with_an_unvalued_lot_is_withheld_from_every_per_symbol_cap() -> None:
    # 2454's second lot has no price, so its position value is short by that lot
    # and every ratio built on it would read low. It is excluded, not compared.
    summary = book_summary(
        book_position(1, "2330", quantity="500", sector="半導體業"),
        book_position(2, "2454", quantity="500", sector="半導體業"),
        book_position(3, "2454", quantity="500", price=None, sector="半導體業"),
    )
    checks = _report(
        summary,
        market_data={
            ("2330", "TW"): SymbolMarketInput(close=600.0, currency="TWD", atr=1.0),
            ("2454", "TW"): SymbolMarketInput(close=600.0, currency="TWD", atr=1.0),
        },
    )
    for limit_id in ("single_position_weight", "sector_weight", "per_trade_loss"):
        cap = checks[limit_id]
        assert [entry.symbol for entry in cap.excluded] == ["2454"], limit_id
    for limit_id in ("single_position_weight", "per_trade_loss"):
        assert checks[limit_id].excluded[0].reason == (
            SYMBOL_UNVALUED_NOTE.format(count=1) + UNVALUED_EXCLUSION_SUFFIX
        ), limit_id
    # Cap 2 says one thing more: the withheld holding is a semiconductor one, so
    # the industry that *is* being reported may be short its value.
    assert checks["sector_weight"].excluded[0].reason == (
        SYMBOL_UNVALUED_NOTE.format(count=1) + SECTOR_UNVALUED_EXCLUSION_SUFFIX
    )
    # And the holding that *was* comparable is still the one being reported.
    assert checks["single_position_weight"].worst_symbol == "2330"
    assert checks["single_position_weight"].evaluated_count == 1


def test_the_sector_cap_discloses_that_an_exclusion_can_understate_it() -> None:
    # The withheld holding may belong to an industry still in the comparison, so
    # the reported industry share can be lower than the truth. That direction is
    # the one this product may never leave implied -- and the book notes say the
    # opposite ("偏高") about a different quantity, so it cannot lean on those.
    checks = _report(
        book_summary(
            book_position(1, "2330", quantity="500", sector="半導體業"),
            book_position(2, "2454", quantity="500", price=None, sector="半導體業"),
        )
    )
    cap = checks["sector_weight"]
    # Route (a): the verdict is still reported, with the caveat stated -- not
    # withdrawn into not_evaluable.
    assert cap.status != "not_evaluable"
    assert "使該產業的佔比被低估" in cap.excluded[0].reason
    # Cap 1 and cap 4 must not carry the sentence: their observed value belongs
    # to the withheld holding alone, so nothing they report is understated.
    for limit_id in ("single_position_weight", "per_trade_loss"):
        assert "低估" not in checks[limit_id].excluded[0].reason, limit_id


def test_a_book_nothing_could_be_valued_in_reports_no_zero_weight_pass() -> None:
    checks = _report(book_summary(book_position(1, "2330", price=None)))
    cap = checks["single_position_weight"]
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    assert cap.detail == NO_CANDIDATE_DETAILS["single_position_weight"]
    assert len(cap.excluded) == 1


# --- the empty book ----------------------------------------------------------


def test_an_empty_book_reports_every_cap_as_not_evaluable() -> None:
    report = evaluate_book_limits(book_summary(), BUDGET)
    assert [check.status for check in report.limits] == ["not_evaluable"] * 5
    assert all(check.observed is None for check in report.limits)
    assert all(check.worst_symbol is None for check in report.limits)


def test_an_empty_book_says_there_is_nothing_to_judge_not_that_data_is_missing() -> None:
    checks = _by_id(evaluate_book_limits(book_summary(), BUDGET))
    for limit_id in ("single_position_weight", "sector_weight", "per_trade_loss"):
        assert checks[limit_id].detail == EMPTY_BOOK_DETAIL.format(
            name=checks[limit_id].name
        ), limit_id
        assert checks[limit_id].excluded == []


def test_an_empty_book_with_a_valid_net_worth_is_no_zero_exposure_pass() -> None:
    # A net worth on file makes cap 3 computable in principle, and with no
    # holding the ratio comes out 0% -- which would render as a green pass on a
    # book that was never judged. There is nothing in the numerator to judge.
    checks = _report(book_summary(), net_worth=reported_net_worth(1_000_000.0))
    cap = checks["gross_exposure"]
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    assert cap.detail == EMPTY_BOOK_DETAIL.format(name=cap.name)


def test_an_empty_book_without_a_net_worth_keeps_the_net_worth_reason() -> None:
    # Both gaps are real; the cap states the one it established itself rather
    # than describing a missing net worth as a missing holding.
    cap = _report(book_summary())["gross_exposure"]
    assert cap.status == "not_evaluable"
    assert cap.detail == NO_NET_WORTH_DETAIL


# --- the aggregate sentence names no cause -----------------------------------


def test_the_no_candidate_sentence_states_only_that_nothing_could_be_compared() -> None:
    # AC-12.3: one gap may not be described with another gap's cause. The
    # aggregate sentence therefore names the cap and what it had nothing of;
    # every cause stays verbatim on the holding it belongs to, in `excluded`.
    causes = ("估值", "產業別", "沒填", "尚未填寫", "ATR", "停損距離", "淨值", "資料")
    for limit_id, detail in NO_CANDIDATE_DETAILS.items():
        assert LIMIT_NAMES[limit_id] in detail
        assert "本次不計算，回報 not_evaluable；各標的的成因逐檔列出。" in detail
        for cause in causes:
            assert cause not in detail, (limit_id, cause)


def test_the_no_candidate_sentence_counts_industries_for_the_sector_cap() -> None:
    # Cap 2 compares industries, so "no candidate" is about industries; the
    # other two caps compare holdings.
    assert "沒有可納入比較的產業" in NO_CANDIDATE_DETAILS["sector_weight"]
    for limit_id in ("single_position_weight", "per_trade_loss"):
        assert "沒有可納入比較的標的" in NO_CANDIDATE_DETAILS[limit_id], limit_id
