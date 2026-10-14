"""F-9b commit 3: the book's fourth cause group, T-11, and its place in the order.

ADR-0024 D-7 (4)-(6), C-20, C-21, C-29, 壞處 10; 風控 F9W-11, F9W-13, F9W-17,
F9W-18, F9W-25 (T-18), F9W-29:

* rows the valuator marked with the refused-answer token are counted in a
  group of their own, after X-3c and before W5/W4 (each group disjoint), and
  stated last: W4 -> W5 -> (b) -> this group;
* the group's sentence is T-11 verbatim, its own constant (never X-3c's (b)),
  joined through the unchanged ``UNVALUED_NOTE_TEMPLATE`` to the one direction
  clause every cause shares;
* the direction clause does not read causes (方向子句測試 1-6, ADR-0024
  「風險與相依」): a withdrawn row is one more unvalued lot.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import app.advice.book as book
from app.advice.book import SectorComparison
from app.advice.book_limits import evaluate_book_limits
from app.advice.limits import RiskBudget
from app.advice.loader import BANNED_PHRASES
from app.data.interface import DataStatus, Market, ProviderResult
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.data.service import _combine_reasons
from app.portfolio.summary import PortfolioSummary, SummaryPosition, build_summary
from app.portfolio.valuation import (
    CURRENCY_MARKET_MISMATCH,
    PRICE_NOT_QUERIED,
    SYMBOL_OR_UNIT_REJECTED,
    PositionValuator,
    PriceMode,
    PriceService,
)
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import recent_bars, trending_closes
from tests.f9b_helpers import AV_QUOTA_REASON, W_A, W_C_PRIME_US, answered, refused
from tests.test_advice_book import _position, _summary
from tests.test_rk2_fx_source_set_disclosure import _shared_forbidden_terms
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

SEMI = "半導體業"
SHIPPING = "航運業"

RULING = "work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md"
#: T-11 主案, read from the ruling's own line (L26; F9W-17) as the expected
#: value (風控 F9W-42 (c) suggested), never a copy kept here.
T_11 = (
    (Path(__file__).resolve().parents[4] / RULING)
    .read_text(encoding="utf-8")
    .splitlines()[25]
    .removeprefix("> ")
)


def _with_missing(row: SummaryPosition, missing: list[str]) -> SummaryPosition:
    valuation = row.valuation.model_copy(update={"missing": missing})
    return row.model_copy(update={"valuation": valuation})


def _rejected(position_id: int, symbol: str, *, sector: str | None = None) -> SummaryPosition:
    """A withdrawn TW row as the valuator reports it (``missing == [token]``)."""
    return _with_missing(
        _position(position_id, symbol, sector=sector, price=None), [SYMBOL_OR_UNIT_REJECTED]
    )


def _cause(template: str, count: int, direction: str) -> str:
    return book.UNVALUED_NOTE_TEMPLATE.format(
        cause=template.format(count=count), direction=direction
    )


def _pattern(template: str) -> re.Pattern[str]:
    before, after = template.split("{count}")
    return re.compile(re.escape(before) + r"(\d+)" + re.escape(after) + "；")


#: The four groups, in their stated order: W4, W5, (b), T-11.
GROUPS = {
    "asked": book.UNVALUED_POSITIONS_CAUSE,
    "not_queried": book.UNVALUED_POSITIONS_CAUSE_CACHE_ONLY,
    "mismatch": book.CURRENCY_MARKET_MISMATCH_CAUSE,
    "rejected": T_11,
}


def _counts(notes: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(GROUPS, 0)
    for note in notes:
        for name, template in GROUPS.items():
            found = _pattern(template).match(note)
            if found is not None:
                counts[name] += int(found.group(1))
    return counts


def _cause_notes(notes: list[str]) -> list[str]:
    return [note for note in notes if sum(_counts([note]).values())]


def _card_notes(summary: PortfolioSummary, *, symbol: str = "2330") -> list[str]:
    context = book.build_book_context(
        summary, symbol=symbol, market="TW", close=600.0, currency="TWD"
    )
    return book.book_notes(context)


def _d_p_card(sector: str) -> str:
    return book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=book.UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector=sector)
    )


# --- The constant (C-29, F9W-17, F9W-29) ----------------------------------------------


def test_t11_is_the_approved_sentence_verbatim() -> None:
    assert book.SYMBOL_OR_UNIT_REJECTED_CAUSE == T_11
    assert T_11.count("{count}") == 1
    # F9W-11 (c): no "；" inside, so the template's separator stays the only one.
    assert "；" not in T_11
    # F9W-17: no "非…中斷" / "並非只是…" negation.
    assert "非" not in T_11
    assert "中斷" not in T_11


def test_t11_carries_its_approval() -> None:
    lines = inspect.getsource(book).splitlines()
    [index] = [
        i for i, line in enumerate(lines) if line.startswith("SYMBOL_OR_UNIT_REJECTED_CAUSE = ")
    ]
    block: list[str] = []
    for line in reversed(lines[:index]):
        if not line.startswith("#:"):
            break
        block.append(line)
    text = "\n".join(block)
    assert "風控核可文案,修改須重新送審(2026-10-12)" in text
    assert RULING in text
    assert "T-11" in text
    assert "F9W-17" in text


def test_t11_is_its_own_constant_not_x3c_b() -> None:
    """F9W-17: the group never reuses ``CURRENCY_MARKET_MISMATCH_CAUSE``."""
    assert book.SYMBOL_OR_UNIT_REJECTED_CAUSE != book.CURRENCY_MARKET_MISMATCH_CAUSE
    tree = ast.parse(textwrap.dedent(inspect.getsource(book._book_level_notes)))
    branches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name)
    ]
    by_test = {node.test.id: node for node in branches if isinstance(node.test, ast.Name)}
    names = {node.id for node in ast.walk(by_test["rejected"]) if isinstance(node, ast.Name)}
    assert "SYMBOL_OR_UNIT_REJECTED_CAUSE" in names
    assert "CURRENCY_MARKET_MISMATCH_CAUSE" not in names


def test_the_note_template_is_unchanged() -> None:
    """F9W-17: ``UNVALUED_NOTE_TEMPLATE`` is not touched."""
    assert book.UNVALUED_NOTE_TEMPLATE == "{cause}；{direction}"


def test_t11_passes_every_wording_scan() -> None:
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert terms  # not vacuous
    rendered = [
        T_11.format(count=1),
        _cause(T_11, 1, book.UNVALUED_DIRECTION_READS_HIGH),
        _cause(T_11, 1, _d_p_card(SEMI)),
        _cause(T_11, 1, book.UNVALUED_DIRECTION_OWN_ONLY),
    ]
    for text in rendered:
        assert [term for term in sorted(terms) if term in text] == []
        assert find_bare_realtime_claims(text) == []


# --- Counting and order (C-20, T-18) ---------------------------------------------------


def test_the_group_is_stated_after_b() -> None:
    asked = _position(2, "2317", price=None)
    not_queried = _with_missing(_position(3, "2454", price=None), [PRICE_NOT_QUERIED])
    mismatch = _with_missing(
        _position(4, "2603", currency="USD", sector=SHIPPING, price=None),
        [CURRENCY_MARKET_MISMATCH],
    )
    rejected = _rejected(5, "00679K", sector=SHIPPING)
    notes = _card_notes(_summary(_position(1, "2330"), asked, not_queried, mismatch, rejected))

    direction = book.UNVALUED_DIRECTION_READS_HIGH
    assert _cause_notes(notes) == [
        _cause(book.UNVALUED_POSITIONS_CAUSE, 1, direction),
        _cause(book.UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, 1, direction),
        _cause(book.CURRENCY_MARKET_MISMATCH_CAUSE, 1, direction),
        _cause(T_11, 1, direction),
    ]


def test_a_book_with_only_withdrawn_rows_states_only_t11() -> None:
    """F9W-11: the rows are not "缺價格或匯率"; nothing else is said about them."""
    notes = _card_notes(
        _summary(
            _position(1, "2330"),
            _rejected(2, "00679K", sector=SHIPPING),
            _rejected(3, "00680K", sector=SHIPPING),
        )
    )

    assert _cause_notes(notes) == [_cause(T_11, 2, book.UNVALUED_DIRECTION_READS_HIGH)]
    assert _counts(notes) == {"asked": 0, "not_queried": 0, "mismatch": 0, "rejected": 2}


def test_precedence_x3c_then_this_group_then_not_queried_then_asked() -> None:
    """D-7 (4): X-3c > this group > ``price_not_queried`` > asked; each row once."""
    with_mismatch = _with_missing(
        _position(2, "AAPL", market="US", currency="TWD", price=None),
        [CURRENCY_MARKET_MISMATCH, SYMBOL_OR_UNIT_REJECTED],
    )
    with_not_queried = _with_missing(
        _position(3, "00679K", price=None), [SYMBOL_OR_UNIT_REJECTED, PRICE_NOT_QUERIED]
    )
    with_price = _with_missing(
        _position(4, "00680K", price=None), ["price", SYMBOL_OR_UNIT_REJECTED]
    )
    notes = _card_notes(_summary(_position(1, "2330"), with_mismatch, with_not_queried, with_price))

    assert _counts(notes) == {"asked": 0, "not_queried": 0, "mismatch": 1, "rejected": 2}


# --- 方向子句測試 1-6 (C-21, C-20; F9W-13) -------------------------------------------


def test_direction_1_a_withdrawn_row_is_in_the_unvalued_composition() -> None:
    summary = _summary(
        _position(1, "2330", sector=SEMI),
        _rejected(2, "00679K", sector=SHIPPING),
        _rejected(3, "00680K"),
        _position(4, "2317", price=None, sector=SEMI),
    )
    context = book.build_book_context(
        summary, symbol="2330", market="TW", close=600.0, currency="TWD"
    )
    composition = context.context.unvalued
    assert composition is not None
    non_ok = sum(1 for row in summary.positions if row.valuation.status != "ok")
    assert composition.total() == non_ok == 3
    assert composition.same_sector_lots == 1
    assert composition.other_sector_lots == 1
    assert composition.unknown_sector_lots.total() == 1
    assert sum(_counts(book.book_notes(context)).values()) == 3


def test_direction_2_own_rows_read_d_d1_alone_and_d_d2_beside_others() -> None:
    own = _rejected(2, "00679K", sector=SHIPPING)
    only_own = _card_notes(_summary(_position(1, "2330", sector=SEMI), own), symbol="00679K")
    with_others = _card_notes(
        _summary(
            _position(1, "2330", sector=SEMI), own, _position(3, "2317", price=None, sector=SEMI)
        ),
        symbol="00679K",
    )

    assert _cause_notes(only_own) == [_cause(T_11, 1, book.UNVALUED_DIRECTION_OWN_ONLY)]
    assert _cause_notes(with_others) == [
        _cause(book.UNVALUED_POSITIONS_CAUSE, 1, book.UNVALUED_DIRECTION_OWN_AND_OTHERS),
        _cause(T_11, 1, book.UNVALUED_DIRECTION_OWN_AND_OTHERS),
    ]


@pytest.mark.parametrize(
    "sector", [pytest.param(SEMI, id="same-industry"), pytest.param(None, id="unknown-industry")]
)
def test_direction_3_another_symbol_in_or_maybe_in_x_reads_d_p(sector: str | None) -> None:
    notes = _card_notes(
        _summary(_position(1, "2330", sector=SEMI), _rejected(2, "00679K", sector=sector))
    )

    assert _cause_notes(notes) == [_cause(T_11, 1, _d_p_card(SEMI))]


def test_direction_4_another_symbol_in_another_industry_reads_d_a() -> None:
    notes = _card_notes(
        _summary(_position(1, "2330", sector=SEMI), _rejected(2, "00679K", sector=SHIPPING))
    )

    assert _cause_notes(notes) == [_cause(T_11, 1, book.UNVALUED_DIRECTION_READS_HIGH)]


def test_direction_5_the_overview_reads_d_a_without_y_and_d_p_with_the_row_in_y() -> None:
    summary = _summary(_position(1, "2330", sector=SEMI), _rejected(2, "00679K", sector=SEMI))
    level = book.build_book_level_context(summary)

    no_y = book.book_notes(level, sector_comparison=SectorComparison(reported_sector=None))
    in_y = book.book_notes(level, sector_comparison=SectorComparison(reported_sector=SEMI))

    assert _cause_notes(no_y) == [_cause(T_11, 1, book.UNVALUED_DIRECTION_READS_HIGH)]
    d_p_book = book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=book.UNVALUED_DIRECTION_TARGET_BOOK
    )
    assert _cause_notes(in_y) == [_cause(T_11, 1, d_p_book)]
    # The real aggregate states the group once, with one of the two clauses.
    report_causes = _cause_notes(evaluate_book_limits(summary, RiskBudget()).notes)
    assert len(report_causes) == 1
    assert report_causes[0] in {
        _cause(T_11, 1, book.UNVALUED_DIRECTION_READS_HIGH),
        _cause(T_11, 1, d_p_book),
    }


def test_direction_6_four_groups_each_counted_and_sharing_one_clause() -> None:
    summary = _summary(
        _position(1, "2330", sector=SEMI),
        _with_missing(
            _position(2, "AAPL", market="US", currency="TWD", price=None),
            [CURRENCY_MARKET_MISMATCH],
        ),
        _rejected(3, "00679K", sector=SEMI),
        _with_missing(_position(4, "2454", price=None, sector=SHIPPING), [PRICE_NOT_QUERIED]),
        _position(5, "2317", price=None, sector=SHIPPING),
    )
    context = book.build_book_context(
        summary, symbol="2330", market="TW", close=600.0, currency="TWD"
    )
    notes = book.book_notes(context)

    assert _counts(notes) == {"asked": 1, "not_queried": 1, "mismatch": 1, "rejected": 1}
    # The clause is chosen once (D-P: a lot is in X) and every cause takes it,
    # in the stated order W4 -> W5 -> (b) -> T-11.
    assert _cause_notes(notes) == [
        _cause(template, 1, _d_p_card(SEMI)) for template in GROUPS.values()
    ]
    assert context.context.unvalued is not None
    assert context.context.unvalued.total() == sum(_counts(notes).values()) == 4


# --- The real chain: valuator -> summary -> notes (F9W-13, F9W-18) ---------------------


class _FlatFx(FxRateProvider):
    source_id = "fake_fx"

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=Decimal("31.5"), as_of=now, source="fake_fx")],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


class _BySymbol:
    """``TSCO.LON`` is refused; ``AAPL`` comes back from the cache with a W-c' reason."""

    def __init__(self) -> None:
        bars = recent_bars(trending_closes(5), symbol="AAPL", market="US", end=date.today())
        self.with_bars = answered(
            bars,
            status=DataStatus.CACHED_STALE,
            reason=_combine_reasons([AV_QUOTA_REASON, W_C_PRIME_US.format(provider="yfinance")]),
        )
        self.refusal = refused("symbol_not_admitted", W_A)

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        return self.with_bars if symbol == "AAPL" else self.refusal

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        return self.get_daily_bars(symbol, market, start, end)


@pytest.mark.parametrize("mode", ["live", "cache_only"])
def test_a_refused_row_reaches_t11_and_a_row_with_bars_does_not(
    tmp_path: Path, mode: PriceMode
) -> None:
    """F9W-18 / C-34 (b): only the refused row enters the group."""
    store = PositionStore(db_path=tmp_path / "positions.db")
    for symbol in ("AAPL", "TSCO.LON"):
        store.create(
            PositionInput(
                symbol=symbol,
                market="US",
                quantity=Decimal(10),
                avg_cost=Decimal(100),
                currency="USD",
                opened_at=date(2024, 1, 2),
                instrument_type="stock",
                sector=None,
                note=None,
            )
        )
    services: dict[Market, PriceService] = {"US": _BySymbol()}
    valuator = PositionValuator(market_services=services, fx_provider=_FlatFx(), price_mode=mode)

    summary = build_summary(store, valuator)

    by_symbol = {row.symbol: row.valuation.missing for row in summary.positions}
    assert by_symbol == {"AAPL": [], "TSCO.LON": [SYMBOL_OR_UNIT_REJECTED]}
    notes = book.book_notes(
        book.build_book_context(summary, symbol="AAPL", market="US", close=None, currency="USD")
    )
    assert _counts(notes) == {"asked": 0, "not_queried": 0, "mismatch": 0, "rejected": 1}
