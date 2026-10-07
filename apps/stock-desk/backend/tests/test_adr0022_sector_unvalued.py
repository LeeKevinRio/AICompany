"""ADR-0022: cap 2 when holdings in (or possibly in) its industry cannot be valued.

An unvalued lot is outside every industry's numerator, so a computed industry
share is short by every unvalued lot that is -- or may be -- in that industry.
These tests pin route C' (Decision 3), the per-holding classification and
numerators (Decision 1, M-1 to M-5), the sizing gate (Decision 4, C-1), the
notes' direction clause (Decision 5) and the one finalizer every response's
notes go through (ADR-0023 Decision 8-1, KD-2).

Every approved sentence is referenced through its constant; none is retyped
here (landing requirement 7 of the risk review).

Two reading rules of this implementation, accepted by the coordinator on
2026-10-07 and pinned below:

* "Unvalued" means ``valuation.status != "ok"`` everywhere the lots are
  classified -- the same test the book-level note counts with -- so the four
  counts of :class:`UnvaluedComposition` always add up to that note's count.
* ``PortfolioContext.valued_unclassified_lots is None`` (a hand-assembled
  context; every production builder sets it) reads as "no valued holding
  without a category". Reading it conservatively would change the
  pre-existing ``notional_caps`` expectation in ``test_advice_limits.py``
  (K-4); the production paths are pinned to set it in the K-5 tests here.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.advice import book as book_module
from app.advice import book_limits as book_limits_module
from app.advice.book import (
    EQUITY_BASIS_NOTE,
    UNVALUED_DIRECTION_OWN_AND_OTHERS,
    UNVALUED_DIRECTION_OWN_AND_OTHERS_TEMPLATE,
    UNVALUED_DIRECTION_OWN_ONLY,
    UNVALUED_DIRECTION_OWN_ONLY_TEMPLATE,
    UNVALUED_DIRECTION_READS_HIGH,
    UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW,
    UNVALUED_DIRECTION_TARGET_BOOK,
    UNVALUED_DIRECTION_TARGET_SYMBOL,
    UNVALUED_NOTE_TEMPLATE,
    UNVALUED_POSITIONS_CAUSE,
    UNVALUED_POSITIONS_CAUSE_CACHE_ONLY,
    UNVALUED_POSITIONS_NOTE,
    UNVALUED_POSITIONS_NOTE_CACHE_ONLY,
    BookContext,
    SectorComparison,
    book_notes,
    build_book_context,
    build_book_level_context,
)
from app.advice.book_limits import (
    NO_CANDIDATE_DETAILS,
    SECTOR_UNVALUED_EXCLUSION_SUFFIX,
    SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX,
    SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX,
    SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX,
    WORST_SECTOR_PREFIX,
    BookLimitCheck,
    BookLimits,
    evaluate_book_limits,
    format_sector_list,
)
from app.advice.engine import build_advice
from app.advice.limits import (
    LIMIT_NAMES,
    NO_SECTOR_DETAILS,
    SECTOR_MIXED_DETAIL,
    SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL,
    SECTOR_UNVALUED_SAME_VIOLATED_DETAIL,
    SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL,
    LimitCheck,
    PortfolioContext,
    RiskBudget,
    UnknownSectorLots,
    UnvaluedComposition,
    evaluate_limits,
    format_percent,
    notional_caps,
    suggest_quantity_range,
)
from app.advice.loader import BANNED_PHRASES
from app.alerts import snapshot as snapshot_module
from app.alerts.engine import UNEVALUATED_LIMITS_NOTE, EvaluationResult, evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api import advice as advice_module
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.portfolio.valuation import PRICE_NOT_QUERIED, PositionValuator
from app.positions.models import PositionInput
from app.positions.sectors import TWSE_SECTORS
from app.positions.store import PositionStore
from tests.advice_helpers import book_position, book_summary, reported_net_worth, uptrend_signals
from tests.alerts_helpers import RecordingLoader, add_rule, limit_rule
from tests.alerts_helpers import snapshot as alert_snapshot
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

BUDGET = RiskBudget()
SEMI = "半導體業"
FIN = "金融保險業"
CEMENT = "水泥工業"
COMPONENTS = "電子零組件業"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
STOCK_DESK_ROOT = BACKEND_ROOT.parent


# --- helpers -------------------------------------------------------------------


def _etf(position: SummaryPosition) -> SummaryPosition:
    return position.model_copy(update={"instrument_type": "etf"})


def _not_queried(position: SummaryPosition) -> SummaryPosition:
    """The same unvalued lot as a cache-only book reports it (ADR-0010 D-1)."""
    valuation = position.valuation.model_copy(update={"missing": [PRICE_NOT_QUERIED]})
    return position.model_copy(update={"valuation": valuation})


def _unknown_lot(kind: str, position_id: int = 9) -> SummaryPosition:
    """One unvalued lot of a holding filed under no category, by sub-type."""
    if kind == "tw_unfiled":
        return book_position(position_id, "2317", price=None)
    if kind == "etf":
        return _etf(book_position(position_id, "0050", price=None))
    return book_position(position_id, "AAPL", market="US", currency="USD", price=None)


def _valued_unknown(kind: str, position_id: int = 8) -> SummaryPosition:
    """One valued holding filed under no category, by sub-type (AC-12.5)."""
    if kind == "tw_unfiled":
        return book_position(position_id, "2317", quantity="100")
    if kind == "etf":
        return _etf(book_position(position_id, "0050", quantity="100"))
    return book_position(position_id, "AAPL", market="US", currency="USD", quantity="100")


UNKNOWN_KINDS = ("tw_unfiled", "etf", "non_tw")


def _card(summary: PortfolioSummary, symbol: str = "2330") -> BookContext:
    return build_book_context(summary, symbol=symbol, market="TW", close=600.0, currency="TWD")


def _check(context: PortfolioContext, limit_id: str = "sector_weight") -> LimitCheck:
    return next(check for check in evaluate_limits(BUDGET, context) if check.id == limit_id)


def _without_overlap(context: PortfolioContext) -> PortfolioContext:
    """The same context with no unvalued lot anywhere -- the pre-ADR verdict."""
    return context.model_copy(
        update={
            "unvalued": UnvaluedComposition(
                own_lots=0,
                same_sector_lots=0,
                unknown_sector_lots=UnknownSectorLots(),
                other_sector_lots=0,
            ),
            "book_fully_valued": True,
        }
    )


def _report(summary: PortfolioSummary) -> BookLimits:
    return evaluate_book_limits(summary, BUDGET)


def _cap2(report: BookLimits) -> BookLimitCheck:
    return next(check for check in report.limits if check.limit_id == "sector_weight")


def _reason(cap: BookLimitCheck, symbol: str) -> str:
    return next(entry.reason for entry in cap.excluded if entry.symbol == symbol)


def _unvalued_note(cause: str, count: int, direction: str) -> str:
    return UNVALUED_NOTE_TEMPLATE.format(cause=cause.format(count=count), direction=direction)


def _symbol_target(sector: str) -> str:
    return UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector=sector)
    )


BOOK_TARGET = UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(target=UNVALUED_DIRECTION_TARGET_BOOK)


# --- Decision 1 / M-3: classification ------------------------------------------


def test_an_unfiled_lot_beside_a_filed_one_counts_in_that_industry() -> None:
    """[X, None]: the holding is an X holding, so its unvalued lot is "same"."""
    summary = book_summary(
        book_position(1, "2330", sector=SEMI),
        book_position(2, "2303", sector=SEMI),
        book_position(3, "2303", price=None),  # no category on this lot
    )
    composition = _card(summary).context.unvalued
    assert composition is not None
    assert composition.same_sector_lots == 1
    assert composition.unknown_sector_lots.total() == 0


def test_a_holding_filed_under_several_categories_is_same_for_each_of_them() -> None:
    summary = book_summary(
        book_position(1, "2330", sector=SEMI),
        book_position(2, "2881", sector=FIN),
        book_position(3, "2303", sector=SEMI, price=None),
        book_position(4, "2303", sector=FIN, price=None),
    )
    for symbol in ("2330", "2881"):
        composition = _card(summary, symbol).context.unvalued
        assert composition is not None
        assert composition.same_sector_lots == 2, symbol
        # A mixed holding is never "unknown" (M-3).
        assert composition.unknown_sector_lots.total() == 0, symbol


def test_a_holding_filed_only_elsewhere_is_other() -> None:
    summary = book_summary(
        book_position(1, "2330", sector=SEMI),
        book_position(2, "1101", sector=CEMENT, price=None),
        book_position(3, "2881", sector=FIN, price=None),
        book_position(4, "2881", sector=CEMENT, price=None),
    )
    composition = _card(summary).context.unvalued
    assert composition is not None
    assert composition.other_sector_lots == 3
    assert composition.same_sector_lots == 0


@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_a_holding_with_no_category_is_unknown_by_sub_type(kind: str) -> None:
    summary = book_summary(book_position(1, "2330", sector=SEMI), _unknown_lot(kind))
    composition = _card(summary).context.unvalued
    assert composition is not None
    assert composition.unknown_sector_lots.model_dump() == {
        sub: (1 if sub == kind else 0) for sub in UNKNOWN_KINDS
    }


def test_the_symbols_own_lots_are_own_and_never_same_without_an_industry() -> None:
    summary = book_summary(
        book_position(1, "2330"),
        book_position(2, "2330", price=None),
        book_position(3, "2303", sector=SEMI, price=None),
    )
    context = _card(summary).context
    assert context.sector is None
    assert context.unvalued is not None
    assert context.unvalued.own_lots == 1
    assert context.unvalued.same_sector_lots == 0
    # X is None: cap 2 keeps its own sentence ahead of route C' (Decision 3).
    assert context.sector_gap is not None
    check = _check(context)
    assert check.status == "not_evaluable"
    assert check.detail == NO_SECTOR_DETAILS[context.sector_gap]


BOOKS: dict[str, PortfolioSummary] = {
    "mixed": book_summary(
        book_position(1, "2330", sector=SEMI),
        book_position(2, "2330", price=None),
        book_position(3, "2303", sector=SEMI, price=None),
        book_position(4, "2303", price=None),
        book_position(5, "2881", sector=FIN, price=None),
        book_position(6, "2881", sector=SEMI, price=None),
        _not_queried(book_position(7, "1101", sector=CEMENT, price=None)),
        _unknown_lot("tw_unfiled", 8),
        _unknown_lot("etf", 9),
        _unknown_lot("non_tw", 10),
    ),
    "own_only": book_summary(
        book_position(1, "2330", sector=SEMI), book_position(2, "2330", price=None)
    ),
    "fully_valued": book_summary(book_position(1, "2330", sector=SEMI)),
}


@pytest.mark.parametrize("name", list(BOOKS))
@pytest.mark.parametrize("symbol", ["2330", "2303", "1101", "9999"])
def test_the_four_counts_partition_the_books_unvalued_lots(name: str, symbol: str) -> None:
    summary = BOOKS[name]
    composition = _card(summary, symbol).context.unvalued
    assert composition is not None
    unvalued = sum(1 for p in summary.positions if p.valuation.status != "ok")
    assert composition.total() == unvalued
    # D-d1's condition read off the partition is the same statement as "this
    # symbol's own lots are every unvalued lot in the book" (risk D-d1 correction).
    others = (
        composition.same_sector_lots
        + composition.unknown_sector_lots.total()
        + composition.other_sector_lots
    )
    assert (composition.own_lots > 0 and others == 0) == (
        composition.own_lots > 0 and composition.own_lots == unvalued
    )


# --- Decision 3: route C' on the card -----------------------------------------


def _semi_book(*extra: SummaryPosition, cement_quantity: str | None = "3000") -> PortfolioSummary:
    """2330 (600,000, semiconductors) beside a cement holding of the given size.

    ``cement_quantity=None`` drops the cement holding, leaving semiconductors
    at 100% of the valued book.
    """
    cement = (
        [book_position(2, "1101", sector=CEMENT, quantity=cement_quantity)]
        if cement_quantity is not None
        else []
    )
    return book_summary(book_position(1, "2330", sector=SEMI), *cement, *extra)


def test_same_industry_under_the_cap_is_not_evaluable_with_w1() -> None:
    # 600,000 / 2,400,000 = 25%, under the 30% cap -- a floor, not a pass.
    context = _card(_semi_book(book_position(3, "2303", sector=SEMI, price=None))).context
    check = _check(context)
    assert check.status == "not_evaluable"
    assert check.observed is None
    assert check.threshold == BUDGET.max_sector_weight
    assert check.detail == SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(sector=SEMI, count=1)
    assert "sector_weight" not in notional_caps(BUDGET, context)


def test_the_count_includes_the_symbols_own_lots() -> None:
    context = _card(
        _semi_book(
            book_position(3, "2303", sector=SEMI, price=None),
            book_position(4, "2330", sector=SEMI, price=None),
        )
    ).context
    assert _check(context).detail == SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(
        sector=SEMI, count=2
    )


def test_same_industry_at_the_cap_stays_violated_with_w2() -> None:
    # 600,000 / 600,000 = 100%: the breach is provable from the valued lots.
    context = _card(
        _semi_book(book_position(3, "2303", sector=SEMI, price=None), cement_quantity=None)
    )
    check = _check(context.context)
    before = _check(_without_overlap(context.context))
    assert check.status == "violated"
    assert check.observed == before.observed
    assert check.detail == before.detail + SECTOR_UNVALUED_SAME_VIOLATED_DETAIL.format(
        sector=SEMI, count=1
    )
    assert "sector_weight" not in notional_caps(BUDGET, context.context)


@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_unknown_only_keeps_passed_and_appends_w3(kind: str) -> None:
    context = _card(_semi_book(_unknown_lot(kind))).context
    check = _check(context)
    before = _check(_without_overlap(context))
    assert check.status == before.status == "passed"
    assert check.observed == before.observed
    assert check.detail == before.detail + SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL.format(sector=SEMI)
    # A pass with W3 is still an incomplete numerator: not sized from.
    assert "sector_weight" not in notional_caps(BUDGET, context)


@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_unknown_only_leaves_a_breach_unchanged(kind: str) -> None:
    context = _card(_semi_book(_unknown_lot(kind), cement_quantity=None)).context
    assert _check(context) == _check(_without_overlap(context))
    assert _check(context).status == "violated"


def test_other_industries_only_leave_cap_2_word_for_word_unchanged() -> None:
    context = _card(_semi_book(book_position(3, "2881", sector=FIN, price=None))).context
    assert _check(context) == _check(_without_overlap(context))
    assert "sector_weight" in notional_caps(BUDGET, context)


def test_a_hand_built_context_falls_back_to_industry_unknown() -> None:
    """Decision 2: no classification and no explicit full valuation -> unknown."""
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "quantity": 500.0,
        "close": 100.0,
        "sector": SEMI,
        "sector_market_value_twd": 100_000.0,
    }
    unknown = PortfolioContext(**base)
    complete = PortfolioContext(**base, book_fully_valued=True)
    assert _check(unknown).detail == _check(complete).detail + (
        SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL.format(sector=SEMI)
    )
    assert "sector_weight" not in notional_caps(BUDGET, unknown)
    assert "sector_weight" in notional_caps(BUDGET, complete)


@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_a_valued_holding_in_no_industry_keeps_cap_2_out_of_sizing(kind: str) -> None:
    """C-1 (6-c): verdict unchanged, but cap 2 is not sized from."""
    context = _card(_semi_book(_valued_unknown(kind))).context
    assert context.valued_unclassified_lots is not None
    assert context.valued_unclassified_lots.total() == 1
    check = _check(context)
    assert check == _check(context.model_copy(update={"valued_unclassified_lots": None}))
    assert "sector_weight" not in notional_caps(BUDGET, context)


def test_a_violated_cap_2_with_w2_blocks_an_add() -> None:
    context = PortfolioContext(
        symbol="2330",
        total_equity_twd=1_000_000.0,
        position_market_value_twd=50_000.0,
        position_cost_twd=45_000.0,
        gross_exposure_twd=500_000.0,
        net_worth=reported_net_worth(1_000_000.0),
        book_fully_valued=False,
        quantity=500.0,
        close=110.0,
        sector=SEMI,
        sector_market_value_twd=400_000.0,
        unvalued=UnvaluedComposition(
            own_lots=0,
            same_sector_lots=1,
            unknown_sector_lots=UnknownSectorLots(),
            other_sector_lots=0,
        ),
        valued_unclassified_lots=UnknownSectorLots(),
    )
    card = build_advice(symbol="2330", signals=uptrend_signals(), portfolio=context, budget=BUDGET)
    sector = next(check for check in card["limits_check"] if check["id"] == "sector_weight")
    assert sector["status"] == "violated"
    assert sector["detail"].endswith(
        SECTOR_UNVALUED_SAME_VIOLATED_DETAIL.format(sector=SEMI, count=1)
    )
    assert card["blocked_action"] == "add"
    assert any(
        f"第 2 條上限（{LIMIT_NAMES['sector_weight']}）" in n for n in card["blocked_notices"]
    )


def test_a_withheld_cap_2_is_named_among_the_caps_left_out_of_the_range() -> None:
    context = _card(_semi_book(book_position(3, "2303", sector=SEMI, price=None))).context
    small = context.model_copy(update={"position_market_value_twd": 60_000.0, "quantity": 100.0})
    quantity = suggest_quantity_range(BUDGET, small, action="add")
    assert quantity is not None
    assert LIMIT_NAMES["sector_weight"] in quantity.basis


# --- M-1: numerators -------------------------------------------------------------


def test_a_valued_mixed_holding_counts_in_full_in_each_of_its_industries() -> None:
    """T-1: a [semiconductors, finance] holding counts whole in both numerators (conservative)."""
    summary = book_summary(
        book_position(1, "2330", sector=SEMI, quantity="500"),
        book_position(2, "2330", sector=FIN, quantity="500"),
        book_position(3, "2454", sector=SEMI, quantity="500"),
        book_position(4, "2881", sector=FIN, quantity="500"),
    )
    semi = _card(summary, "2454").context.sector_market_value_twd
    fin = _card(summary, "2881").context.sector_market_value_twd
    # 2330 is 600,000 (both lots) in each; 2454 and 2881 add 300,000 apiece.
    assert semi == pytest.approx(900_000.0)
    assert fin == pytest.approx(900_000.0)


def test_an_unfiled_lot_beside_a_filed_one_is_in_the_numerator() -> None:
    """T-3 / K-2: both lots of a [semiconductors, None] holding are counted."""
    summary = book_summary(
        book_position(1, "2330", sector=SEMI, quantity="500"),
        book_position(2, "2330", quantity="500"),
    )
    book = _card(summary)
    assert book.context.sector_market_value_twd == pytest.approx(600_000.0)
    # And it is therefore not an "unclassified" holding (M-1).
    assert book.context.valued_unclassified_lots == UnknownSectorLots()
    assert not any("未計入任何產業的市值合計" in note for note in book.notes)


def test_holdings_of_one_industry_get_the_identical_cap_2_verdict() -> None:
    """T-5 (`_one_per_sector` invariant): status, detail and observed coincide."""
    summary = book_summary(
        book_position(1, "2330", sector=SEMI),
        book_position(2, "2454", sector=SEMI),
        book_position(3, "2454"),
        book_position(4, "1101", sector=CEMENT, quantity="9000"),
        book_position(5, "2303", sector=SEMI, price=None),
        _unknown_lot("etf"),
    )
    checks = {symbol: _check(_card(summary, symbol).context) for symbol in ("2330", "2454")}
    assert checks["2330"] == checks["2454"]


# --- /limits: route C', M-2a, M-4, W6, W-6m, W7 ----------------------------------


def test_an_industry_held_only_through_a_mixed_holding_is_not_compared() -> None:
    """T-2 / M-2a: the mixed holding keeps its sentence and is not counted."""
    cap = _cap2(
        _report(
            book_summary(
                book_position(1, "2330", sector=SEMI),
                book_position(2, "2330", sector=FIN),
                book_position(3, "1101", sector=CEMENT),
            )
        )
    )
    assert cap.evaluated_count == 1
    assert cap.detail.startswith(WORST_SECTOR_PREFIX.format(count=1))
    assert FIN not in cap.detail and SEMI not in cap.detail
    assert _reason(cap, "2330") == SECTOR_MIXED_DETAIL


def test_an_unvalued_holding_of_an_uncompared_industry_gets_w6() -> None:
    cap = _cap2(
        _report(
            book_summary(
                book_position(1, "1101", sector=CEMENT),
                book_position(2, "2303", sector=SEMI, price=None),
            )
        )
    )
    assert _reason(cap, "2303") == book_module.SYMBOL_UNVALUED_NOTE.format(
        count=1
    ) + SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX.format(sector=SEMI)


def test_same_industry_under_the_cap_is_excluded_with_w1_on_the_overview() -> None:
    cap = _cap2(_report(_semi_book(book_position(3, "2303", sector=SEMI, price=None))))
    assert _reason(cap, "2330") == SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(
        sector=SEMI, count=1
    )
    # Semiconductors are therefore not compared, so 2303 gets W6.
    assert _reason(cap, "2303").endswith(
        SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX.format(sector=SEMI)
    )
    assert cap.evaluated_count == 1


def _mixed_unvalued(*, valued_semi_quantity: str | None) -> PortfolioSummary:
    positions = [
        book_position(1, "2330", sector=FIN),
        book_position(2, "2330", sector=SEMI, price=None),
        book_position(3, "1101", sector=CEMENT),
    ]
    if valued_semi_quantity is not None:
        positions.append(book_position(4, "2454", sector=SEMI, quantity=valued_semi_quantity))
    return book_summary(*positions)


def test_a_mixed_unvalued_holding_with_nothing_compared_gets_w6m() -> None:
    """T-4: none of its industries is in the comparison."""
    cap = _cap2(_report(_mixed_unvalued(valued_semi_quantity=None)))
    reason = _reason(cap, "2330")
    assert reason == book_module.SYMBOL_UNVALUED_NOTE.format(
        count=1
    ) + SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX.format(
        sectors=format_sector_list({SEMI, FIN})
    )
    assert "金融保險業、半導體業" in reason


def test_a_mixed_unvalued_holding_in_an_empty_comparison_gets_w6m() -> None:
    """T-4: comparable is empty -- the 2026-08-09 sentence would point at nothing."""
    cap = _cap2(
        _report(
            book_summary(
                book_position(1, "2330", sector=FIN, price=None),
                book_position(2, "2330", sector=SEMI),
                book_position(3, "2330", sector=COMPONENTS),
            )
        )
    )
    assert cap.status == "not_evaluable"
    assert cap.evaluated_count == 0
    assert _reason(cap, "2330").endswith(
        SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX.format(
            sectors="金融保險業、半導體業、電子零組件業"
        )
    )


def test_a_mixed_unvalued_holding_with_one_industry_compared_keeps_the_old_sentence() -> None:
    # 2454 is so large that semiconductors breach the cap and stay compared.
    cap = _cap2(_report(_mixed_unvalued(valued_semi_quantity="9000")))
    assert cap.status == "violated"
    assert cap.evaluated_count > 0  # the old sentence is only true with something compared
    assert (
        _reason(cap, "2330")
        == book_module.SYMBOL_UNVALUED_NOTE.format(count=1) + SECTOR_UNVALUED_EXCLUSION_SUFFIX
    )


@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_an_unvalued_holding_in_no_industry_keeps_the_old_sentence(kind: str) -> None:
    lot = _unknown_lot(kind)
    cap = _cap2(_report(book_summary(book_position(1, "1101", sector=CEMENT), lot)))
    assert cap.evaluated_count > 0  # cement is compared
    assert _reason(cap, lot.symbol).endswith(SECTOR_UNVALUED_EXCLUSION_SUFFIX)


def test_the_overview_prefix_counts_only_the_compared_industries() -> None:
    cap = _cap2(
        _report(
            book_summary(
                book_position(1, "2330", sector=SEMI),
                book_position(2, "2881", sector=FIN),
                book_position(3, "2317", sector=SEMI),
                book_position(4, "2317", sector=CEMENT),
            )
        )
    )
    assert cap.evaluated_count == 2
    assert cap.detail.startswith(WORST_SECTOR_PREFIX.format(count=2))


def test_the_acceptance_book_reports_no_semiconductor_pass() -> None:
    """ADR-0022 acceptance 3."""
    report = _report(
        book_summary(
            book_position(1, "2330", sector=SEMI),
            book_position(2, "2303", sector=SEMI, price=None),
            book_position(3, "2881", sector=FIN, quantity="3000"),
            _etf(book_position(4, "0050", price=None)),
        )
    )
    cap = _cap2(report)
    assert f"{SEMI} 產業佔總資產" not in cap.detail
    assert _reason(cap, "2303").endswith(
        SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX.format(sector=SEMI)
    )
    assert cap.evaluated_count > 0  # 2881 is compared
    assert _reason(cap, "0050").endswith(SECTOR_UNVALUED_EXCLUSION_SUFFIX)
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, 2, BOOK_TARGET) in report.notes


# --- Decision 5: the direction clause -----------------------------------------


def test_the_ratios_read_high_sentences_are_byte_identical_to_2026_09_18() -> None:
    """K-11: the composed D-a output is the locked sentence, byte for byte.

    Pinned by digest so the approved wording is not retyped into a test.
    """
    assert (
        hashlib.sha256(UNVALUED_POSITIONS_NOTE.encode()).hexdigest()
        == "968349c2c124cc09810395e34d9c9e277fe28bd6c2113c7fffc6860a67f0e325"
    )
    assert (
        hashlib.sha256(UNVALUED_POSITIONS_NOTE_CACHE_ONLY.encode()).hexdigest()
        == "86cdceef9ee396812bf14b13c86f533dc77793d029cee0f8c1d21a6cfb1e9ef7"
    )
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, 3, UNVALUED_DIRECTION_READS_HIGH) == (
        UNVALUED_POSITIONS_NOTE.format(count=3)
    )
    assert _unvalued_note(
        UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, 3, UNVALUED_DIRECTION_READS_HIGH
    ) == UNVALUED_POSITIONS_NOTE_CACHE_ONLY.format(count=3)


def test_the_own_lot_clauses_are_byte_identical_to_the_approved_wording() -> None:
    """RC-2: D-d1 / D-d2 as rendered from ``LIMIT_NAMES``, pinned by digest.

    The digests were computed independently of the constants, from the
    approved wording itself: ``hashlib.sha256(text.encode("utf-8")).hexdigest()``
    where ``text`` is

    * D-d1 -- the "new wording" bullet of the D-d1 correction-note section of
      ``docs/adr/0022-stock-desk-單一產業佔比上限在同產業或產業未知持股無法估值時的判定.md``
      (87 characters);
    * D-d2 -- the D-d2 row of the approved-wording table in
      ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md``
      (103 characters).
    """
    assert (
        hashlib.sha256(UNVALUED_DIRECTION_OWN_ONLY.encode("utf-8")).hexdigest()
        == "687cd525400421dd7b331421656d8fdd96eeba0bea3a540817cc581f73f5b01a"
    )
    assert (
        hashlib.sha256(UNVALUED_DIRECTION_OWN_AND_OTHERS.encode("utf-8")).hexdigest()
        == "98c17acb5eb3dccca84a405bfd6162cb2b1937207e0552d5c705657d0fb74d6a"
    )


#: sha256 hex digests of the approved wording, each computed independently of
#: the constants from the review record itself, as
#: ``hashlib.sha256(text.encode("utf-8")).hexdigest()``:
#:
#: * W1, W2, W3, W6, W7 -- the template cells (placeholders included) of the
#:   approved-wording table in
#:   ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md``;
#: * D-P -- that table's D-P cell with ``{target}`` replaced by the card target
#:   (``" {sector} 產業"`` with ``{sector}`` = 半導體業) or by the overview
#:   target, both as given in the same cell's variable column;
#: * W-6m -- the corrected W-6m cell of the third section of
#:   ``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md``,
#:   with ``{sectors}`` replaced by the two-industry example of that section;
#: * W-6u -- the quoted sentence of the W-6u verbatim review section of the
#:   first review record.
APPROVED_DIGESTS: dict[str, tuple[str, str]] = {
    "W1": (
        SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL,
        "11ce82e8c35ab94a269a31229ac9f3125d7272c5c2e5173d5f15b9f6c8364d82",
    ),
    "W2": (
        SECTOR_UNVALUED_SAME_VIOLATED_DETAIL,
        "4e97a445e4a0bd5debfbddd2051847058d71ad24c2283475ea1a46a4ac8bccff",
    ),
    "W3": (
        SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL,
        "9c8ab8a14df09119a896e800559b9c508c76e35277058db4eaaab7909454a468",
    ),
    "D-P card": (
        _symbol_target(SEMI),
        "1a436edcf9f7d6d86ff5659e3addacc62d580c52bb6049a4778c047215639913",
    ),
    "D-P overview": (
        BOOK_TARGET,
        "8cba917357c26dcc862b14b5cd9dfed4f2764d8c03c90406faa0dacfbdf85622",
    ),
    "W6": (
        SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX,
        "a409df0f489e282781d1c3f4d8961dae71d56357fbee0886df8f81d142116eaf",
    ),
    "W-6m two industries": (
        SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX.format(
            sectors=format_sector_list({SEMI, FIN})
        ),
        "63e4da9f0cf179febce8dea069cbc30bebed33b746b3b2ad2c103daa8aafe7af",
    ),
    "W-6u": (
        SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX,
        "205a1366573ed91452eda91ec0674cb5a6d7be76008bf74bca1b822184a363d6",
    ),
    "W7": (
        WORST_SECTOR_PREFIX,
        "a1c4299f488eb0df942966349d0fce16efbebb688e2fd16fbef119d38aa545fe",
    ),
}


@pytest.mark.parametrize("code", list(APPROVED_DIGESTS))
def test_the_sector_wording_is_byte_identical_to_the_approved_wording(code: str) -> None:
    """K-8 / RM-4: every new sentence of this change, pinned by digest."""
    text, digest = APPROVED_DIGESTS[code]
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == digest


def test_the_sector_sentences_name_the_cap_they_qualify() -> None:
    """D-P, W1 and W2 carry cap 2's name as ``LIMIT_NAMES`` spells it."""
    name = LIMIT_NAMES["sector_weight"]
    assert name in UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW
    assert name in SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL
    assert name in SECTOR_UNVALUED_SAME_VIOLATED_DETAIL


def _both_causes(*lots: SummaryPosition) -> tuple[SummaryPosition, ...]:
    """Each lot twice: once unpriced (live), once not queried (cache-only)."""
    out: list[SummaryPosition] = []
    for index, lot in enumerate(lots):
        out.append(lot)
        out.append(_not_queried(lot.model_copy(update={"id": 100 + index})))
    return tuple(out)


CARD_CASES: dict[str, tuple[tuple[SummaryPosition, ...], str]] = {
    # a: only other industries -> D-a.
    "a": (_both_causes(book_position(3, "2881", sector=FIN, price=None)), "high"),
    # b: same industry -> D-P.
    "b": (_both_causes(book_position(3, "2303", sector=SEMI, price=None)), "sector"),
    # c: unknown only -> D-P.
    "c": (_both_causes(_unknown_lot("etf")), "sector"),
}


@pytest.mark.parametrize("case", list(CARD_CASES))
def test_the_card_chooses_its_direction_clause_by_the_classification(case: str) -> None:
    lots, expected = CARD_CASES[case]
    book = _card(_semi_book(*lots))
    direction = UNVALUED_DIRECTION_READS_HIGH if expected == "high" else _symbol_target(SEMI)
    notes = book_notes(book)
    # Both causes take the same clause (one choice per response).
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, 1, direction) in notes
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, 1, direction) in notes


def test_a_card_with_no_industry_reads_high() -> None:
    """a0: X is None and the symbol has no unvalued lot of its own -> D-a."""
    book = _card(
        book_summary(
            book_position(1, "2330"),
            book_position(2, "2303", sector=SEMI, price=None),
            _unknown_lot("tw_unfiled"),
        )
    )
    assert UNVALUED_POSITIONS_NOTE.format(count=2) in book_notes(book)


def _limits_notes(summary: PortfolioSummary) -> list[str]:
    return _report(summary).notes


def test_the_overview_reads_low_when_the_book_holds_an_unknown_lot() -> None:
    notes = _limits_notes(_semi_book(_unknown_lot("non_tw")))
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, 1, BOOK_TARGET) in notes


def test_the_overview_reads_low_when_the_reported_industry_has_an_unvalued_lot() -> None:
    summary = _semi_book(book_position(3, "2303", sector=SEMI, price=None), cement_quantity=None)
    assert _cap2(_report(summary)).status == "violated"
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, 1, BOOK_TARGET) in _limits_notes(summary)


def test_a_mixed_unvalued_holding_counts_for_the_reported_industry() -> None:
    """M-5: categories(G) containing Y is enough."""
    summary = _mixed_unvalued(valued_semi_quantity="9000")
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, 1, BOOK_TARGET) in _limits_notes(summary)


def test_the_overview_reads_high_when_no_industry_was_compared() -> None:
    """Y undefined -> D-a, ahead of every other rule (risk-compliance 2026-10-07 R-1).

    This book holds no unknown lot; the cases that do are pinned in
    :func:`test_an_unknown_lot_reads_high_when_nothing_was_compared`.
    """
    summary = book_summary(
        book_position(1, "2330"),
        book_position(2, "2303", sector=SEMI, price=None),
    )
    assert _cap2(_report(summary)).evaluated_count == 0
    assert UNVALUED_POSITIONS_NOTE.format(count=1) in _limits_notes(summary)


def test_the_overview_reads_high_when_only_other_industries_are_unvalued() -> None:
    summary = _semi_book(book_position(3, "2881", sector=FIN, price=None))
    assert UNVALUED_POSITIONS_NOTE.format(count=1) in _limits_notes(summary)


# --- the finalizer (ADR-0023 Decision 8-1, KD-2) -----------------------------------


def test_the_finalizer_keeps_the_order_the_notes_always_had() -> None:
    book = _card(_semi_book(book_position(3, "2330", sector=SEMI, price=None)))
    notes = book_notes(book)
    assert notes[0] == EQUITY_BASIS_NOTE
    assert notes[-len(book.symbol_notes) :] == list(book.symbol_notes)
    assert book.notes == notes


def test_the_finalizer_refuses_a_scope_mismatch() -> None:
    summary = _semi_book()
    with pytest.raises(ValueError):
        book_notes(_card(summary), sector_comparison=SectorComparison(reported_sector=SEMI))
    level = build_book_level_context(summary)
    with pytest.raises(ValueError):
        book_notes(level)
    assert book_notes(level, sector_comparison=SectorComparison(reported_sector=None))


def _book_context_receivers(tree: ast.AST) -> set[str]:
    """Names bound to a ``build_book_context``/``build_book_level_context`` result."""
    builders = {"build_book_context", "build_book_level_context"}
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called in builders:
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def test_no_production_code_reads_book_context_notes() -> None:
    """KD-2, static half: no ``<book context>.notes`` anywhere under ``app/``."""
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        receivers = _book_context_receivers(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "notes"
                and isinstance(node.value, ast.Name)
                and node.value.id in receivers
            ):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}")
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "notes"
                and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", "")
                in {"build_book_context", "build_book_level_context"}
            ):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}")
    assert offenders == []


@pytest.fixture
def notes_property_forbidden(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """KD-2, runtime half: reading ``BookContext.notes`` fails the test."""

    def _forbidden(self: BookContext) -> list[str]:
        raise AssertionError("production code read BookContext.notes")

    monkeypatch.setattr(BookContext, "notes", property(_forbidden))
    yield


@pytest.mark.usefixtures("notes_property_forbidden")
def test_both_responses_assemble_their_notes_through_the_finalizer(
    api_harness: ApiHarness,
) -> None:
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload(sector=SEMI))
    api_harness.client.post("/api/positions", json=position_payload(symbol="2303", sector=SEMI))

    ok = api_harness.client.get("/api/advice/2330")
    assert ok.status_code == 200 and ok.json()["status"] == "ok"
    insufficient = api_harness.client.get("/api/advice/2303")
    assert insufficient.status_code == 200
    assert insufficient.json()["status"] == "insufficient_data"
    assert EQUITY_BASIS_NOTE in insufficient.json()["context_notes"]
    overview = api_harness.client.get("/api/portfolio/limits")
    assert overview.status_code == 200
    assert EQUITY_BASIS_NOTE in overview.json()["notes"]


# --- K-5 / R-10: no shown path reaches the fallback --------------------------------


class _ContextSpy:
    """Records every context a consumer module's builder returned."""

    def __init__(self) -> None:
        self.contexts: list[PortfolioContext] = []

    def __call__(self, *args: Any, **kwargs: Any) -> BookContext:
        book = build_book_context(*args, **kwargs)
        self.contexts.append(book.context)
        return book


@pytest.fixture
def context_spy(monkeypatch: pytest.MonkeyPatch) -> Callable[[Any], _ContextSpy]:
    recorder = _ContextSpy()

    def install(module: Any) -> _ContextSpy:
        monkeypatch.setattr(module, "build_book_context", recorder)
        return recorder

    return install


def _assert_classified(contexts: list[PortfolioContext]) -> None:
    assert contexts, "the path under test never reached build_book_context"
    for context in contexts:
        assert context.unvalued is not None
        assert context.valued_unclassified_lots is not None


def test_the_advice_endpoint_never_reaches_the_fallback(
    api_harness: ApiHarness, context_spy: Callable[[Any], _ContextSpy]
) -> None:
    recorder = context_spy(advice_module)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    assert api_harness.client.get("/api/advice/2330").json()["status"] == "ok"
    _assert_classified(recorder.contexts)


def test_the_overview_never_reaches_the_fallback(
    api_harness: ApiHarness, context_spy: Callable[[Any], _ContextSpy]
) -> None:
    recorder = context_spy(book_limits_module)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    assert api_harness.client.get("/api/portfolio/limits").status_code == 200
    _assert_classified(recorder.contexts)
    level = build_book_level_context(book_summary(book_position(1, "2330")))
    _assert_classified([level.context])


def test_the_alert_snapshot_never_reaches_the_fallback(
    tmp_path: Path, context_spy: Callable[[Any], _ContextSpy]
) -> None:
    recorder = context_spy(snapshot_module)
    store = PositionStore(db_path=tmp_path / "positions.db")
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(600),
            currency="TWD",
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            sector=SEMI,
            note=None,
        )
    )
    service = FakePriceService()
    service.seed("2330", recent_bars(trending_closes(60), symbol="2330"))
    build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=store,
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        fx_provider=None,
        today=datetime.now(UTC).date(),
    )
    _assert_classified(recorder.contexts)


# --- M-1 required / T-6: no cross-industry sum or average --------------------------


_AGGREGATORS = {"sum", "mean", "fmean", "average", "median", "fsum"}
_SECTOR_FIGURES = ("sector_market_value", "_sector_rollup", "sector_weight")


def test_no_production_code_sums_or_averages_industry_figures() -> None:
    """Grep half of M-1 required: no aggregate over industry figures in ``app/``."""
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in _AGGREGATORS and any(term in ast.unparse(node) for term in _SECTOR_FIGURES):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}")
    assert offenders == []
    # The industry numerator is computed in exactly one place.
    callers = [
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "_sector_rollup(" in path.read_text(encoding="utf-8")
    ]
    assert callers == ["app/advice/book.py"]


def _numbers(payload: Any) -> list[float]:
    if isinstance(payload, bool):
        return []
    if isinstance(payload, int | float):
        return [float(payload)]
    if isinstance(payload, dict):
        return [n for value in payload.values() for n in _numbers(value)]
    if isinstance(payload, list):
        return [n for value in payload for n in _numbers(value)]
    return []


def test_no_response_carries_a_cross_industry_total_or_average(api_harness: ApiHarness) -> None:
    """Test half of M-1 required, on a book whose numerators overlap."""
    for symbol in ("2330", "2454", "2881"):
        api_harness.price_service.seed(symbol, recent_bars(trending_closes(200), symbol=symbol))
    api_harness.client.post("/api/positions", json=position_payload(symbol="2330", sector=SEMI))
    api_harness.client.post("/api/positions", json=position_payload(symbol="2330", sector=FIN))
    api_harness.client.post("/api/positions", json=position_payload(symbol="2454", sector=SEMI))
    # Unequal industries, so an average could not coincide with either share.
    api_harness.client.post(
        "/api/positions", json=position_payload(symbol="2881", quantity="3000", sector=FIN)
    )

    summary = api_harness.client.get("/api/portfolio/summary").json()
    values = {row["id"]: Decimal(row["market_value_twd"]) for row in summary["positions"]}
    rows = {row["id"]: row for row in summary["positions"]}
    equity = float(sum(values.values(), Decimal(0)))
    semi = float(sum(v for i, v in values.items() if rows[i]["symbol"] in {"2330", "2454"}))
    fin = float(sum(v for i, v in values.items() if rows[i]["symbol"] in {"2330", "2881"}))
    assert semi + fin > equity  # the fixture really does double-count

    forbidden_amounts = [semi + fin]
    forbidden_ratios = [(semi + fin) / equity, (semi + fin) / equity / 2]
    for response in (
        api_harness.client.get("/api/portfolio/limits").json(),
        api_harness.client.get("/api/advice/2454").json(),
        api_harness.client.get("/api/advice/2881").json(),
    ):
        numbers = _numbers(response)
        text = json.dumps(response, ensure_ascii=False)
        for amount in forbidden_amounts:
            assert all(n != pytest.approx(amount) for n in numbers)
            assert f"{amount:,.0f}" not in text
        for ratio in forbidden_ratios:
            assert all(n != pytest.approx(ratio) for n in numbers)
            assert format_percent(ratio) not in text


# --- RM-2 / RM-4: the industry list and the wording scans --------------------------


def test_two_industries_are_listed_in_twse_order() -> None:
    assert format_sector_list({SEMI, FIN}) == "金融保險業、半導體業"


def test_three_industries_are_listed_in_twse_order() -> None:
    assert format_sector_list([COMPONENTS, SEMI, FIN, SEMI]) == "金融保險業、半導體業、電子零組件業"


def test_a_value_outside_the_taxonomy_sorts_last_by_code_point() -> None:
    assert format_sector_list(["乙", SEMI, "甲", FIN]) == "、".join(
        [FIN, SEMI, *sorted(["乙", "甲"])]
    )
    # Total order: no input makes the key raise.
    assert format_sector_list(["", "  ", "{}", SEMI]).startswith(SEMI)


def test_every_industry_is_listed_without_truncation_or_a_trailing_etc() -> None:
    listed = format_sector_list(reversed(TWSE_SECTORS))
    assert listed.split("、") == list(TWSE_SECTORS)


@pytest.mark.parametrize(
    "sectors", [{SEMI, FIN}, {SEMI, FIN, COMPONENTS}, set(TWSE_SECTORS)], ids=["2", "3", "all"]
)
def test_w6m_says_what_was_filed_not_what_the_holding_is(sectors: set[str]) -> None:
    rendered = SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX.format(
        sectors=format_sector_list(sectors)
    )
    for word in ("屬於", "等", "涉及"):
        assert word not in rendered


def _shared_forbidden_terms() -> tuple[str, ...]:
    payload = json.loads(
        (STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text(encoding="utf-8")
    )
    return tuple(payload["guarantee"]) + tuple(payload["price_target"])


def _rendered_new_sentences() -> list[str]:
    sentences = [
        SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(sector=SEMI, count=2),
        SECTOR_UNVALUED_SAME_VIOLATED_DETAIL.format(sector=SEMI, count=2),
        SECTOR_UNVALUED_UNKNOWN_PASSED_DETAIL.format(sector=SEMI),
        _unvalued_note(UNVALUED_POSITIONS_CAUSE, 2, _symbol_target(SEMI)),
        _unvalued_note(UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, 2, BOOK_TARGET),
        WORST_SECTOR_PREFIX.format(count=3),
        SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX.format(
            sectors=format_sector_list(TWSE_SECTORS)
        ),
    ]
    sentences += [SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX.format(sector=s) for s in TWSE_SECTORS]
    sentences += [
        SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX,
        book_module.SYMBOL_UNVALUED_NOTE.format(count=2)
        + SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX,
    ]
    # RC-1: D-d1 / D-d2 alone and joined to each cause.
    for direction in (UNVALUED_DIRECTION_OWN_ONLY, UNVALUED_DIRECTION_OWN_AND_OTHERS):
        sentences += [
            direction,
            _unvalued_note(UNVALUED_POSITIONS_CAUSE, 2, direction),
            _unvalued_note(UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, 2, direction),
        ]
    return sentences


@pytest.mark.parametrize("text", _rendered_new_sentences())
def test_the_new_sentences_pass_the_three_wording_scans(text: str) -> None:
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert [term for term in sorted(terms) if term in text] == []
    assert find_bare_realtime_claims(text) == []


# --- D-d1 / D-d2: the symbol's own unvalued lots (Decision 5 (1)) ----------------


OWN_POSITION_NAMES = "、".join(
    LIMIT_NAMES[limit_id]
    for limit_id in ("single_position_weight", "per_trade_loss", "kelly_fraction")
)


def test_the_own_lot_clauses_are_built_from_the_cap_names() -> None:
    """Cap names are built from ``LIMIT_NAMES``, never typed (risk-compliance required)."""
    assert UNVALUED_DIRECTION_OWN_ONLY == UNVALUED_DIRECTION_OWN_ONLY_TEMPLATE.format(
        names=OWN_POSITION_NAMES
    )
    assert UNVALUED_DIRECTION_OWN_AND_OTHERS == UNVALUED_DIRECTION_OWN_AND_OTHERS_TEMPLATE.format(
        names=OWN_POSITION_NAMES
    )
    for template in (
        UNVALUED_DIRECTION_OWN_ONLY_TEMPLATE,
        UNVALUED_DIRECTION_OWN_AND_OTHERS_TEMPLATE,
    ):
        for limit_id in ("single_position_weight", "per_trade_loss", "kelly_fraction"):
            assert LIMIT_NAMES[limit_id] not in template


def _own_book(*, sector: str | None, with_others: bool) -> PortfolioSummary:
    """2330 with one unvalued lot of its own, optionally beside other unvalued lots."""
    positions = [
        book_position(1, "2330", sector=sector),
        book_position(2, "2330", sector=sector, price=None),
        _not_queried(book_position(3, "2330", sector=sector, price=None)),
        book_position(4, "1101", sector=CEMENT, quantity="3000"),
    ]
    if with_others:
        positions += [
            book_position(5, "2881", sector=FIN, price=None),
            _not_queried(book_position(6, "2881", sector=FIN, price=None)),
        ]
    return book_summary(*positions)


@pytest.mark.parametrize("with_others", [False, True], ids=["d1", "d2"])
@pytest.mark.parametrize("sector", [None, SEMI], ids=["x_none", "x_set"])
def test_the_symbols_own_unvalued_lots_choose_d_d1_or_d_d2(
    sector: str | None, with_others: bool
) -> None:
    """d0/d1/d2: the own-lot clause wins whatever X is, for both causes."""
    book = _card(_own_book(sector=sector, with_others=with_others))
    direction = UNVALUED_DIRECTION_OWN_AND_OTHERS if with_others else UNVALUED_DIRECTION_OWN_ONLY
    count = 2 if with_others else 1
    notes = book_notes(book)
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE, count, direction) in notes
    assert _unvalued_note(UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, count, direction) in notes
    for other in (UNVALUED_DIRECTION_READS_HIGH, _symbol_target(SEMI)):
        assert not any(note.endswith(other) for note in notes)
    check = _check(book.context)
    if sector is None:
        # d0: cap 2 keeps the no-industry sentence verbatim (D-d1 correction, required).
        assert book.context.sector_gap is not None
        assert check.status == "not_evaluable"
        assert check.detail == NO_SECTOR_DETAILS[book.context.sector_gap]
    else:
        # Cap 2 follows b: the symbol's own lots count as same.
        assert check.detail == SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(
            sector=SEMI, count=2
        )


@pytest.mark.parametrize("name", list(BOOKS))
@pytest.mark.parametrize("symbol", ["2330", "2303", "1101", "9999"])
def test_d_d1_is_chosen_exactly_when_the_symbol_holds_every_unvalued_lot(
    name: str, symbol: str
) -> None:
    """D-d1 correction, required: the partition test equals "own lots == book total"."""
    summary = BOOKS[name]
    book = _card(summary, symbol)
    composition = book.context.unvalued
    assert composition is not None
    unvalued = sum(1 for p in summary.positions if p.valuation.status != "ok")
    own_is_everything = composition.own_lots > 0 and composition.own_lots == unvalued
    notes = book_notes(book)
    assert any(n.endswith(UNVALUED_DIRECTION_OWN_ONLY) for n in notes) == own_is_everything
    assert any(n.endswith(UNVALUED_DIRECTION_OWN_AND_OTHERS) for n in notes) == (
        composition.own_lots > 0 and not own_is_everything
    )


def test_cap_4_is_not_evaluable_when_the_symbols_lots_mix_currencies() -> None:
    """D-d1's premise (tech-architect): no single price, so no cap 4 ratio."""
    summary = book_summary(
        book_position(1, "AAPL", market="US", currency="USD", fx_to_twd="31.5"),
        book_position(2, "AAPL", market="US", currency="TWD"),
        book_position(3, "AAPL", market="US", currency="USD", price=None),
    )
    book = build_book_context(summary, symbol="AAPL", market="US", close=200.0, atr=5.0)
    assert book.context.close is None and book.context.atr is None
    assert _check(book.context, "per_trade_loss").status == "not_evaluable"


def test_cap_4_is_not_evaluable_when_the_symbols_lots_span_markets() -> None:
    """The same premise across markets.

    A production caller always names the market (``test_book_context_call_sites``),
    so the other market's lot is another holding, never "own"; only a caller
    that omits the market merges the two, and their currencies then differ.
    """
    summary = book_summary(
        book_position(1, "2330", market="TW"),
        book_position(2, "2330", market="TW", price=None),
        book_position(3, "2330", market="US", currency="USD", fx_to_twd="31.5"),
    )
    pinned = _card(summary).context
    assert pinned.unvalued is not None and pinned.unvalued.own_lots == 1
    merged = build_book_context(summary, symbol="2330", close=600.0, atr=5.0)
    assert merged.currency is None
    assert _check(merged.context, "per_trade_loss").status == "not_evaluable"
    us = book_summary(
        book_position(1, "2330", market="TW"),
        book_position(2, "2330", market="US", currency="USD", price=None),
    )
    composition = _card(us).context.unvalued
    assert composition is not None
    assert composition.own_lots == 0


# --- risk-compliance 2026-10-07 correction: Y undefined first (R-1, R-2) and W-6u (R-5) ------


@pytest.mark.parametrize("cause", ["live", "cache_only"])
@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_an_unknown_lot_reads_high_when_nothing_was_compared(kind: str, cause: str) -> None:
    """R-2: Y undefined x unknown sub-type x cause -> the 2026-09-18 sentence."""
    lot = _unknown_lot(kind)
    if cause == "cache_only":
        lot = _not_queried(lot)
    # 2330 is valued but unfiled, so cap 2 has nothing to compare.
    summary = book_summary(book_position(1, "2330"), lot)
    report = _report(summary)
    assert _cap2(report).evaluated_count == 0
    locked = (
        UNVALUED_POSITIONS_NOTE if cause == "live" else UNVALUED_POSITIONS_NOTE_CACHE_ONLY
    ).format(count=1)
    assert locked in report.notes
    assert not any(BOOK_TARGET in note for note in report.notes)


def test_a_mixed_unvalued_holding_reads_high_when_nothing_was_compared() -> None:
    """R-2: Y undefined x the W-6m situation -> D-a."""
    report = _report(
        book_summary(
            book_position(1, "2330", sector=FIN, price=None),
            book_position(2, "2330", sector=SEMI),
            _unknown_lot("etf"),
        )
    )
    assert _cap2(report).evaluated_count == 0
    assert UNVALUED_POSITIONS_NOTE.format(count=2) in report.notes
    assert not any(BOOK_TARGET in note for note in report.notes)


EQUIVALENCE_BOOKS: dict[str, PortfolioSummary] = {
    "nothing_compared_unknown": book_summary(book_position(1, "2330"), _unknown_lot("non_tw")),
    "nothing_compared_same": book_summary(
        book_position(1, "2330"), book_position(2, "2303", sector=SEMI, price=None)
    ),
    "c_prime_empties_the_comparison": book_summary(
        book_position(1, "2330", sector=SEMI, quantity="100"),
        book_position(2, "2303", sector=SEMI, price=None),
        book_position(3, "2317", quantity="900"),
        _etf(book_position(4, "0050", price=None)),
    ),
    "compared_with_unknown": _semi_book(_unknown_lot("tw_unfiled")),
    "compared_with_same": _semi_book(
        book_position(3, "2303", sector=SEMI, price=None), cement_quantity=None
    ),
    "compared_mixed": _mixed_unvalued(valued_semi_quantity="9000"),
    "fully_valued": _semi_book(),
}


@pytest.mark.parametrize("name", list(EQUIVALENCE_BOOKS))
def test_y_is_defined_exactly_when_an_industry_was_compared(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-2: ``evaluated_count == 0`` <=> no ``reported_sector`` <=> no D-P target."""
    seen: list[SectorComparison] = []

    def spy(book: BookContext, *, sector_comparison: SectorComparison | None = None) -> list[str]:
        assert sector_comparison is not None
        seen.append(sector_comparison)
        return book_notes(book, sector_comparison=sector_comparison)

    monkeypatch.setattr(book_limits_module, "book_notes", spy)
    report = _report(EQUIVALENCE_BOOKS[name])
    [comparison] = seen
    cap = _cap2(report)
    if cap.evaluated_count == 0:
        assert comparison.reported_sector is None
        assert not any(BOOK_TARGET in note for note in report.notes)
    else:
        assert comparison.reported_sector is not None


def test_the_route_a_book_of_the_existing_suite_still_compares_an_industry() -> None:
    """Confirms risk-compliance's reading of ``test_advice_book_limits.py:447``.

    That assertion keeps ``SECTOR_UNVALUED_EXCLUSION_SUFFIX``; it is only true
    while something is compared, and here semiconductors are (violated, C').
    """
    cap = _cap2(
        _report(
            book_summary(
                book_position(1, "2330", quantity="500", sector=SEMI),
                book_position(2, "2454", quantity="500", sector=SEMI),
                book_position(3, "2454", quantity="500", price=None, sector=SEMI),
            )
        )
    )
    assert cap.evaluated_count > 0
    assert _reason(cap, "2454").endswith(SECTOR_UNVALUED_EXCLUSION_SUFFIX)


INVARIANT_BOOKS: dict[str, PortfolioSummary] = {
    **EQUIVALENCE_BOOKS,
    **{
        f"w6u_{kind}": book_summary(book_position(1, "2330"), _unknown_lot(kind))
        for kind in UNKNOWN_KINDS
    },
    "unknown_beside_a_compared_industry": _semi_book(_unknown_lot("etf")),
    "mixed_beside_a_compared_industry": _mixed_unvalued(valued_semi_quantity=None),
}


#: The clause of the 2026-08-09 sentence that needs a compared industry to be
#: true; taken from the constant, not retyped.
MAY_BELONG_CLAUSE = "可能屬於已納入比較的產業"


@pytest.mark.parametrize("name", list(INVARIANT_BOOKS))
def test_each_exclusion_sentence_appears_only_where_it_has_a_referent(name: str) -> None:
    """RU-4: the 2026-08-09 sentence needs a compared industry; W-6u needs none."""
    assert MAY_BELONG_CLAUSE in SECTOR_UNVALUED_EXCLUSION_SUFFIX
    cap = _cap2(_report(INVARIANT_BOOKS[name]))
    reasons = [entry.reason for entry in cap.excluded]
    # Matched on the clause itself, so the sentence is caught wherever it sits.
    if any(MAY_BELONG_CLAUSE in r for r in reasons):
        assert cap.evaluated_count > 0
    if any(r.endswith(SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX) for r in reasons):
        assert cap.evaluated_count == 0
        assert cap.detail == NO_CANDIDATE_DETAILS["sector_weight"]


def test_the_suffix_for_a_holding_with_no_category_follows_the_comparison() -> None:
    """RU-4: the branch itself."""
    assert (
        book_limits_module._sector_unvalued_suffix(frozenset(), frozenset())
        == SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX
    )
    assert (
        book_limits_module._sector_unvalued_suffix(frozenset(), frozenset({SEMI}))
        == SECTOR_UNVALUED_EXCLUSION_SUFFIX
    )


def _c_prime_book(lot: SummaryPosition) -> PortfolioSummary:
    """2330 semiconductors under the cap, 2303 semiconductors unvalued, plus ``lot``.

    C' withdraws 2330 (W1), and the valued 2317 has no category, so nothing is
    compared at all.
    """
    return book_summary(
        book_position(1, "2330", sector=SEMI, quantity="100"),
        book_position(2, "2303", sector=SEMI, price=None),
        book_position(3, "2317", quantity="900"),
        lot,
    )


W6U_BOOKS: dict[str, Callable[[SummaryPosition], PortfolioSummary]] = {
    # The shape of the F-1 book: one valued holding without a category beside
    # the unvalued one, so cap 2 has nothing to compare.
    "f1_book": lambda lot: book_summary(book_position(1, "2330"), lot),
    "c_prime_book": _c_prime_book,
}


@pytest.mark.parametrize("book", list(W6U_BOOKS))
@pytest.mark.parametrize("cause", ["live", "cache_only"])
@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_a_holding_with_no_category_gets_w6u_when_nothing_is_compared(
    kind: str, cause: str, book: str
) -> None:
    """RU-3: every sub-type, both causes, word for word."""
    lot = _unknown_lot(kind)
    if cause == "cache_only":
        lot = _not_queried(lot)
    report = _report(W6U_BOOKS[book](lot))
    cap = _cap2(report)
    assert cap.evaluated_count == 0
    assert _reason(cap, lot.symbol) == (
        book_module.SYMBOL_UNVALUED_NOTE.format(count=1)
        + SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX
    )
    # RU-5: caps 1, 4 and 5 keep their own suffix.
    for limit_id in ("single_position_weight", "per_trade_loss", "kelly_fraction"):
        check = next(c for c in report.limits if c.limit_id == limit_id)
        assert all(
            SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX not in entry.reason
            for entry in check.excluded
        ), limit_id
    # RU-5: a *valued* holding with no category keeps cap 2's own detail.
    if book == "f1_book":
        assert _reason(cap, "2330") == NO_SECTOR_DETAILS["unfiled"]


def test_the_c_prime_acceptance_book_gives_the_etf_w6u() -> None:
    """RU-3: 2330 under the cap, 2303 unvalued, 0050 unvalued -> 0050 gets W-6u."""
    cap = _cap2(_report(_c_prime_book(_etf(book_position(4, "0050", price=None)))))
    assert _reason(cap, "2330") == SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(
        sector=SEMI, count=1
    )
    assert _reason(cap, "0050").endswith(SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX)


@pytest.mark.parametrize("kind", UNKNOWN_KINDS)
def test_no_w6u_while_an_industry_is_compared(kind: str) -> None:
    """RU-5: unknown with something compared keeps the 2026-08-09 sentence."""
    cap = _cap2(_report(_semi_book(_unknown_lot(kind))))
    assert cap.evaluated_count > 0
    assert all(
        SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX not in entry.reason
        for entry in cap.excluded
    )


def test_w6u_names_no_industry_and_no_direction() -> None:
    """RU-6: the wording checks W-6m gets, plus two more words the review names."""
    whole = (
        book_module.SYMBOL_UNVALUED_NOTE.format(count=2)
        + SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX
    )
    for text in (SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX, whole):
        for word in ("屬於", "所屬", "被低估", "等", "涉及"):
            assert word not in text


# --- the alert path (ADR-0022 acceptance 1; alerts/engine.py unchanged) ------------


def _alert_outcome(tmp_path: Path, context: PortfolioContext) -> EvaluationResult:
    store = AlertStore(db_path=tmp_path / "alerts.db")
    add_rule(store, limit_rule(limit_id="any"))
    return evaluate_alerts(store, RecordingLoader(alert_snapshot(context=context)))


def test_a_violated_cap_2_fires_with_w2_right_after_the_industry_sentence(
    tmp_path: Path,
) -> None:
    """W2 reaches the push message, directly after the sentence it qualifies."""
    summary = book_summary(
        book_position(1, "2330", sector=SEMI, quantity="100"),
        book_position(2, "2454", sector=SEMI),
        book_position(3, "2303", sector=SEMI, price=None),
        book_position(4, "1101", sector=CEMENT),
    )
    context = _card(summary).context.model_copy(update={"atr": 1.0})
    violated = [
        check.id for check in evaluate_limits(BUDGET, context) if check.status == "violated"
    ]
    assert violated == ["sector_weight"]

    result = _alert_outcome(tmp_path, context)

    assert [outcome.status for outcome in result.outcomes] == ["fired"]
    industry_sentence = _check(_without_overlap(context)).detail
    w2 = SECTOR_UNVALUED_SAME_VIOLATED_DETAIL.format(sector=SEMI, count=1)
    assert result.events[0].message.endswith(industry_sentence + w2)


def test_a_withheld_cap_2_is_named_by_the_any_rule_as_unevaluated(tmp_path: Path) -> None:
    """W1 makes cap 2 not_evaluable, so the quiet note lists it by name."""
    summary = book_summary(
        book_position(1, "2330", sector=SEMI, quantity="100"),
        book_position(2, "1101", sector=CEMENT, quantity="3000"),
        book_position(3, "2303", sector=SEMI, price=None),
    )
    context = _card(summary).context.model_copy(update={"atr": 1.0})
    checks = evaluate_limits(BUDGET, context)
    assert next(c for c in checks if c.id == "sector_weight").detail == (
        SECTOR_UNVALUED_SAME_NOT_EVALUABLE_DETAIL.format(sector=SEMI, count=1)
    )
    assert not any(c.status == "violated" for c in checks)
    unevaluated = [c.name for c in checks if c.status == "not_evaluable"]

    result = _alert_outcome(tmp_path, context)

    assert [outcome.status for outcome in result.outcomes] == ["quiet"]
    assert LIMIT_NAMES["sector_weight"] in unevaluated
    assert result.outcomes[0].reason == UNEVALUATED_LIMITS_NOTE.format(
        n=len(unevaluated), names="、".join(unevaluated)
    )
