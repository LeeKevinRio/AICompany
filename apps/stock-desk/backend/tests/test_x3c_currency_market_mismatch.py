"""X-3c: a legacy row whose currency does not match its market is withdrawn on read.

Task X-3 (``work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md``,
KX-A1..KX-A11, the "KX-A 測試矩陣增補" section and "X-3c 第二段裁定"); risk
review ``work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md``,
second part (RX-1..RX-10). Every approved sentence is referenced through its
constant; none is copied here (RX-1).

* The valuator short-circuits such a row before any lookup (KX-A2): unvalued,
  ``missing == [currency_market_mismatch]`` and nothing else, every figure and
  ``fx`` empty, and no price or FX call for it.
* The book layer withdraws the close and the ATR for it with sentence (c)
  (KX-A4, KX-A11), counts it in a third cause group with sentence (b)
  (KX-A9, KX-A10), and the alert snapshot reads (c) off the book (RX-6).
* N1-A and N1-B (X3-R5, RX-8, RX-10) run the real chain -- store, valuator,
  summary, API and snapshot -- and assert the figures the review names.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import app.advice.book as book
from app.advice.book_limits import (
    SECTOR_UNVALUED_EXCLUSION_SUFFIX,
    SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX,
    UNVALUED_EXCLUSION_SUFFIX,
    WORST_SECTOR_PREFIX,
    evaluate_book_limits,
)
from app.advice.limits import (
    LIMIT_NAMES,
    PRICE_INPUT_LIMIT_IDS,
    RiskBudget,
    evaluate_limits,
    format_percent,
    notional_caps,
    suggest_quantity_range,
)
from app.advice.loader import BANNED_PHRASES
from app.alerts.engine import SymbolSnapshot, evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.deps import get_position_store
from app.data.interface import DataStatus, Market
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.main import app
from app.portfolio import valuation
from app.portfolio.summary import SummaryPosition, build_summary
from app.portfolio.valuation import PRICE_NOT_QUERIED, PositionValuator
from app.positions import models as models_module
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore
from app.services.fx_notes import GENERIC_SOURCE_NOTE, SOURCE_NOTES
from tests.alerts_helpers import add_rule, limit_rule
from tests.api_helpers import (
    FakePriceService,
    position_payload,
    recent_bars,
    serve_us_market,
    trending_closes,
)
from tests.conftest import ApiHarness
from tests.test_advice_book import _fx, _position, _summary
from tests.test_rk2_fx_source_set_disclosure import _shared_forbidden_terms
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

APP_ROOT = Path(book.__file__).resolve().parents[1]
MODELS_FILE = Path(models_module.__file__).resolve()

#: Every methodology sentence an FX source can contribute.
METHODOLOGY = (*SOURCE_NOTES.values(), GENERIC_SOURCE_NOTE)


def _head(template: str) -> str:
    """The fixed text of ``template`` before its first placeholder."""
    return template.split("{", 1)[0]


#: Sentences that name an FX lookup, a rate or a mixed holding: none may sit on
#: a card or snapshot that (c) explains (risk second part, display condition (c)).
FX_HEADS = (
    _head(book.NO_FX_QUOTE_NOTE),
    _head(book.FX_UNAVAILABLE_NOTE),
    _head(book.FX_PAIR_MISMATCH_NOTE),
    _head(book.FX_APPLIED_NOTE),
    book.MIXED_CURRENCY_NOTE,
    book.FX_MIXED_SOURCES_NOTE,
)


def _mismatch_note() -> str:
    """Sentence (c)."""
    note: str = book.CURRENCY_MARKET_MISMATCH_NOTE
    return note


def _mismatch_cause(count: int) -> str:
    """Sentence (b) with its count."""
    cause: str = book.CURRENCY_MARKET_MISMATCH_CAUSE
    return cause.format(count=count)


def _token() -> str:
    token: str = valuation.CURRENCY_MARKET_MISMATCH
    return token


def _cause_note(cause: str, direction: str) -> str:
    return book.UNVALUED_NOTE_TEMPLATE.format(cause=cause, direction=direction)


def _count_pattern(template: str) -> re.Pattern[str]:
    before, after = template.split("{count}")
    return re.compile(re.escape(before) + r"(\d+)" + re.escape(after) + "；")


def _cause_counts(notes: list[str]) -> dict[str, int]:
    """The three cause groups' counts as the notes state them (KX-A9)."""
    patterns = {
        "asked": _count_pattern(book.UNVALUED_POSITIONS_CAUSE),
        "not_queried": _count_pattern(book.UNVALUED_POSITIONS_CAUSE_CACHE_ONLY),
        "mismatch": _count_pattern(book.CURRENCY_MARKET_MISMATCH_CAUSE),
    }
    counts = dict.fromkeys(patterns, 0)
    for note in notes:
        for name, pattern in patterns.items():
            found = pattern.match(note)
            if found is not None:
                counts[name] += int(found.group(1))
    return counts


def _assert_cause_sum(notes: list[str], unvalued: dict[str, Any], non_ok: int) -> None:
    """KX-A9 / RX-4: the groups add up to the composition and to the non-ok rows."""
    composition = (
        unvalued["own_lots"]
        + unvalued["same_sector_lots"]
        + sum(unvalued["unknown_sector_lots"].values())
        + unvalued["other_sector_lots"]
    )
    assert sum(_cause_counts(notes).values()) == composition == non_ok


def _assert_no_fx_wording(texts: list[str]) -> None:
    for text in texts:
        for sentence in METHODOLOGY:
            assert sentence not in text
        for head in FX_HEADS:
            assert head not in text


def _mismatched(
    position_id: int,
    symbol: str,
    *,
    market: str,
    currency: str,
    sector: str | None = None,
    missing: list[str] | None = None,
) -> SummaryPosition:
    """A hand-built X-3 row as the valuator reports it after X-3c."""
    row = _position(
        position_id, symbol, market=market, currency=currency, sector=sector, price=None
    )
    flagged = row.valuation.model_copy(update={"missing": missing or [_token()]})
    return row.model_copy(update={"valuation": flagged})


# --- Shared fakes -------------------------------------------------------------


class CountingFx(FxRateProvider):
    """USDTWD 31.5 from Bank of Taiwan (or nothing), counting every lookup."""

    source_id = "bank_of_taiwan"

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[str] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls.append(pair)
        now = datetime.now(UTC)
        if not self.available:
            return FxRateResult(rates=[], status=DataStatus.UNAVAILABLE, as_of=now, source="none")
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=Decimal("31.5"), as_of=now, source="bot")],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


def _ending_at(close: float) -> list[float]:
    """200 gently rising closes whose last one is ``close``."""
    step = close / 1000.0
    return trending_closes(200, start=round(close - step * 199, 4), step=step)


def _seed(service: FakePriceService, symbol: str, close: float, market: Market = "TW") -> None:
    service.seed(symbol, recent_bars(_ending_at(close), symbol=symbol, market=market))


def _create(
    store: PositionStore,
    symbol: str,
    market: str,
    currency: str,
    *,
    quantity: int,
    avg_cost: int,
    sector: str | None = None,
) -> Position:
    # ``PositionInput`` carries no market/currency rule (ADR-0017 C3): the only
    # way to store the legacy row the write doors now refuse.
    return store.create(
        PositionInput(
            symbol=symbol,
            market=market,  # type: ignore[arg-type]
            quantity=Decimal(quantity),
            avg_cost=Decimal(avg_cost),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            sector=sector,
            note=None,
        )
    )


# --- KX-A2 / RX-2: the valuator ---------------------------------------------------


@pytest.mark.parametrize("price_mode", ["live", "cache_only"])
@pytest.mark.parametrize("available", [True, False], ids=["fx-ok", "fx-failed"])
@pytest.mark.parametrize(
    ("symbol", "market", "currency"),
    [
        pytest.param("AAPL", "US", "TWD", id="type-A"),
        pytest.param("2330", "TW", "USD", id="type-B"),
    ],
)
def test_kxa2_a_mismatched_row_is_unvalued_without_any_lookup(
    tmp_path: Path,
    symbol: str,
    market: str,
    currency: str,
    available: bool,
    price_mode: valuation.PriceMode,
) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    _create(store, symbol, market, currency, quantity=100, avg_cost=150)
    services: dict[Market, FakePriceService] = {"TW": FakePriceService(), "US": FakePriceService()}
    _seed(services["TW"], "2330", 600.0)
    _seed(services["US"], "AAPL", 200.0, market="US")
    fx = CountingFx(available=available)
    valuator = PositionValuator(market_services=services, fx_provider=fx, price_mode=price_mode)

    [valued] = valuator.value_all(store.list_all())

    result = valued.valuation
    assert result.status == "insufficient_data"
    assert result.missing == [_token()]
    assert PRICE_NOT_QUERIED not in result.missing
    assert result.price is None
    assert result.fx is None  # art-lead R-1: no "匯率 資料不足" badge to draw
    assert result.pnl_original is None
    assert result.pnl_twd is None
    assert result.asset_contribution_twd is None
    assert result.fx_contribution_twd is None
    assert valued.cost_twd is None
    assert valued.market_value_twd is None
    assert valued.change_basis is None
    # Not one price or FX lookup for it, in either mode.
    for service in services.values():
        assert service.calls == []
        assert service.cached_calls == []
    assert fx.calls == []


def test_kxa2_matched_rows_beside_it_are_valued_and_asked_as_before(tmp_path: Path) -> None:
    """RX-8: the mismatched row adds no lookup to a book; its neighbours are unchanged."""
    services: dict[Market, FakePriceService] = {"TW": FakePriceService(), "US": FakePriceService()}
    _seed(services["US"], "AAPL", 200.0, market="US")
    _seed(services["US"], "MSFT", 400.0, market="US")

    def value(with_mismatch: bool) -> tuple[list[Any], list[str], list[Any]]:
        store = PositionStore(db_path=tmp_path / f"positions-{with_mismatch}.db")
        if with_mismatch:
            _create(store, "AAPL", "US", "TWD", quantity=100, avg_cost=150)
        _create(store, "MSFT", "US", "USD", quantity=10, avg_cost=300)
        fx = CountingFx()
        for service in services.values():
            service.calls.clear()
        rows = PositionValuator(market_services=services, fx_provider=fx).value_all(
            store.list_all()
        )
        return rows, fx.calls, list(services["US"].calls)

    with_rows, with_fx, with_prices = value(True)
    without_rows, without_fx, without_prices = value(False)
    assert with_fx == without_fx
    assert [call[0] for call in with_prices] == [call[0] for call in without_prices] == ["MSFT"]
    msft_with = with_rows[1]
    msft_without = without_rows[0]
    assert msft_with.valuation == msft_without.valuation
    assert msft_with.market_value_twd == msft_without.market_value_twd == Decimal("126000")


@pytest.mark.parametrize(
    ("symbol", "market", "currency"),
    [
        pytest.param("AAPL", "US", "TWD", id="type-A"),
        pytest.param("2330", "TW", "USD", id="type-B"),
    ],
)
def test_kxa2_the_summary_payload_carries_no_fx_for_a_mismatched_row(
    api_harness: ApiHarness, symbol: str, market: str, currency: str
) -> None:
    """art-lead R-1: the home page's FX badge reads ``valuation.fx``; it is null."""
    us = FakePriceService()
    _seed(us, "AAPL", 200.0, market="US")
    _seed(api_harness.price_service, "2330", 600.0)
    serve_us_market(tw_service=api_harness.price_service, us_service=us, fx_provider=CountingFx())
    _create(api_harness.positions, symbol, market, currency, quantity=100, avg_cost=150)

    body = api_harness.client.get("/api/portfolio/summary").json()

    [row] = body["positions"]
    assert row["valuation"]["status"] == "insufficient_data"
    assert row["valuation"]["missing"] == [_token()]
    assert row["valuation"]["fx"] is None
    assert row["valuation"]["price"] is None
    assert row["market_value_twd"] is None
    assert body["fx_disclosures"] == []
    assert Decimal(body["totals"]["market_value_twd"]) == 0


def test_kxa2_the_x3b_warning_still_names_the_row(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    row = _create(store, "AAPL", "US", "TWD", quantity=100, avg_cost=150)
    valuator = PositionValuator(market_services={}, fx_provider=CountingFx())
    with caplog.at_level("WARNING", logger="app.portfolio.valuation"):
        valuator.value_all(store.list_all())
    assert [record.getMessage() for record in caplog.records] == [
        f"position currency does not match market: id={row.id} market=US currency=TWD"
    ]


# --- KX-A1: one definition ---------------------------------------------------------


def test_kxa1_no_market_currency_table_outside_models() -> None:
    pairs = set(models_module.MARKET_CURRENCY.items())
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.resolve() == MODELS_FILE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literal = {
                (key.value, value.value)
                for key, value in zip(node.keys, node.values, strict=True)
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
            }
            if literal & pairs:
                offenders.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")
    assert offenders == []


def test_kxa1_the_book_layer_defers_to_the_shared_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    assert vars(book)["currency_matches_market"] is models_module.currency_matches_market
    # A rule that calls everything a mismatch withdraws a consistent TW card;
    # a local copy of the table would not.
    monkeypatch.setattr(book, "currency_matches_market", lambda _market, _currency: False)
    context = book.build_book_context(
        _summary(_position(1, "2330")), symbol="2330", market="TW", close=600.0, currency="TWD"
    )
    assert _mismatch_note() in context.symbol_notes
    assert context.context.close is None


# --- RX-1 / RX-5: the approved constants -------------------------------------------


def test_rx1_the_constants_have_the_approved_lengths() -> None:
    # The review counts ``{count}`` as one character (第二段 table: 75 and 31).
    cause: str = book.CURRENCY_MARKET_MISMATCH_CAUSE
    assert cause.count("{count}") == 1
    assert len(cause.replace("{count}", "N")) == 75
    assert "{" not in _mismatch_note()
    assert len(_mismatch_note()) == 31


@pytest.mark.parametrize(
    "name", ["CURRENCY_MARKET_MISMATCH_CAUSE", "CURRENCY_MARKET_MISMATCH_NOTE"]
)
def test_rx1_each_constant_carries_its_approval(name: str) -> None:
    lines = inspect.getsource(book).splitlines()
    [index] = [i for i, line in enumerate(lines) if line.startswith(f"{name} = ")]
    comments: list[str] = []
    for line in reversed(lines[:index]):
        if not line.startswith("#:"):
            break
        comments.append(line)
    block = "\n".join(comments)
    assert "風控核可文案,修改須重新送審(2026-10-08)" in block
    assert "work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md" in block


@dataclass(frozen=True)
class _Combination:
    """One of the five direction clauses (b) is joined to, and a book showing it."""

    direction: str
    notes: list[str]


def _five_combinations() -> dict[str, _Combination]:
    budget = RiskBudget()
    semis = "半導體業"
    ok_2330 = _position(1, "2330", sector=semis)
    # D-a: the only unvalued row is in another industry.
    b_row_other = _mismatched(2, "2603", market="TW", currency="USD", sector="航運業")
    d_a = book.build_book_context(
        _summary(ok_2330, b_row_other), symbol="2330", market="TW", close=600.0, currency="TWD"
    )
    # D-P on the card: a type-A row has no industry, so it may be in X.
    a_row = _mismatched(3, "AAPL", market="US", currency="TWD")
    d_p_card = book.build_book_context(
        _summary(ok_2330, a_row), symbol="2330", market="TW", close=600.0, currency="TWD"
    )
    # D-P on the overview: the same book, judged as a whole.
    d_p_book = evaluate_book_limits(_summary(ok_2330, a_row), budget)
    # D-d1 / D-d2: the card of the mismatched symbol itself.
    d_d1 = book.build_book_context(
        _summary(ok_2330, a_row), symbol="AAPL", market="US", close=200.0, currency="USD"
    )
    other_unvalued = _position(4, "2303", sector=semis, price=None)
    d_d2 = book.build_book_context(
        _summary(ok_2330, a_row, other_unvalued),
        symbol="AAPL",
        market="US",
        close=200.0,
        currency="USD",
    )
    return {
        "D-a": _Combination(book.UNVALUED_DIRECTION_READS_HIGH, book.book_notes(d_a)),
        "D-P card": _Combination(
            book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
                target=book.UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector=semis)
            ),
            book.book_notes(d_p_card),
        ),
        "D-P limits": _Combination(
            book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
                target=book.UNVALUED_DIRECTION_TARGET_BOOK
            ),
            d_p_book.notes,
        ),
        "D-d1": _Combination(book.UNVALUED_DIRECTION_OWN_ONLY, book.book_notes(d_d1)),
        "D-d2": _Combination(book.UNVALUED_DIRECTION_OWN_AND_OTHERS, book.book_notes(d_d2)),
    }


@pytest.mark.parametrize("name", ["D-a", "D-P card", "D-P limits", "D-d1", "D-d2"])
def test_rx5_each_combination_renders_byte_for_byte(name: str) -> None:
    combination = _five_combinations()[name]
    expected = _cause_note(_mismatch_cause(1), combination.direction)
    assert combination.notes.count(expected) == 1
    # It is the last cause sentence: W4 -> W5 -> (b).
    causes = [note for note in combination.notes if sum(_cause_counts([note]).values())]
    assert causes[-1] == expected


#: The task's additional list (risk first part, section 三): new fragments only,
#: never a rendered sentence -- the approved D-P itself contains "屬於" (RX-5).
NEW_FRAGMENT_ONLY_TERMS = (
    "請",
    "仍",
    "擋下",
    "通過",
    "安全",
    "正常",
    "更高",
    "屬於",
    "等",
    "涉及",
    "被低估",
)


def test_rx5_new_fragments_and_rendered_sentences_pass_every_wording_scan() -> None:
    shared = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert shared  # not vacuous
    fragments = [_mismatch_cause(1), _mismatch_note()]
    rendered = [
        _cause_note(_mismatch_cause(1), combination.direction)
        for combination in _five_combinations().values()
    ]
    for text in fragments + rendered:
        assert [term for term in sorted(shared) if term in text] == []
        assert find_bare_realtime_claims(text) == []
    for text in fragments:
        assert [term for term in NEW_FRAGMENT_ONLY_TERMS if term in text] == []


# --- KX-A9 / KX-A10 / RX-4: three cause groups ------------------------------------


def test_kxa9_three_groups_are_disjoint_ordered_and_add_up() -> None:
    asked = _position(2, "2317", price=None)  # missing == ["price"]
    not_queried = _position(3, "2454", price=None)
    not_queried = not_queried.model_copy(
        update={
            "valuation": not_queried.valuation.model_copy(update={"missing": [PRICE_NOT_QUERIED]})
        }
    )
    # A hand-built row carrying both tokens still counts once, as a mismatch.
    both = _mismatched(
        4, "AAPL", market="US", currency="TWD", missing=[_token(), PRICE_NOT_QUERIED]
    )
    b_row = _mismatched(5, "2603", market="TW", currency="USD", sector="航運業")
    summary = _summary(_position(1, "2330"), asked, not_queried, both, b_row)
    context = book.build_book_context(
        summary, symbol="2330", market="TW", close=600.0, currency="TWD"
    )
    notes = book.book_notes(context)
    direction = book.UNVALUED_DIRECTION_READS_HIGH
    expected = [
        _cause_note(book.UNVALUED_POSITIONS_CAUSE.format(count=1), direction),
        _cause_note(book.UNVALUED_POSITIONS_CAUSE_CACHE_ONLY.format(count=1), direction),
        _cause_note(_mismatch_cause(2), direction),
    ]
    assert [note for note in notes if note in expected] == expected
    assert _cause_counts(notes) == {"asked": 1, "not_queried": 1, "mismatch": 2}
    composition = context.context.unvalued
    assert composition is not None
    non_ok = sum(1 for row in summary.positions if row.valuation.status != "ok")
    assert sum(_cause_counts(notes).values()) == composition.total() == non_ok == 4


def test_kxa10_a_mismatched_row_is_never_counted_as_missing_a_price_or_rate() -> None:
    summary = _summary(_position(1, "2330"), _mismatched(2, "AAPL", market="US", currency="TWD"))
    notes = book.book_notes(
        book.build_book_context(summary, symbol="2330", market="TW", close=600.0, currency="TWD")
    )
    assert _cause_counts(notes) == {"asked": 0, "not_queried": 0, "mismatch": 1}
    assert not any(
        note.startswith(_head(book.UNVALUED_POSITIONS_CAUSE)) and "缺價格" in note for note in notes
    )


def test_kxa9_a_consistent_book_states_no_mismatch_sentence() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2317", price=None))
    notes = book.book_notes(
        book.build_book_context(summary, symbol="2330", market="TW", close=600.0, currency="TWD")
    )
    assert notes.count(book.UNVALUED_POSITIONS_NOTE.format(count=1)) == 1
    assert _cause_counts(notes)["mismatch"] == 0
    assert _mismatch_note() not in notes


@pytest.mark.parametrize("unvalued_token", ["price", PRICE_NOT_QUERIED])
def test_rx4_sentence_b_is_the_same_live_and_cache_only(
    tmp_path: Path, unvalued_token: str
) -> None:
    """The mismatched row carries only the new token in both modes, so (b) does not
    depend on the mode, while the other unvalued row follows it (W4 or W5)."""
    store = PositionStore(db_path=tmp_path / "positions.db")
    _create(store, "AAPL", "US", "TWD", quantity=100, avg_cost=150)
    _create(store, "2330", "TW", "TWD", quantity=1000, avg_cost=500, sector="半導體業")
    _create(store, "2303", "TW", "TWD", quantity=1000, avg_cost=40, sector="半導體業")
    tw = FakePriceService()
    _seed(tw, "2330", 600.0)
    mode: valuation.PriceMode = "live" if unvalued_token == "price" else "cache_only"
    valuator = PositionValuator(
        market_services={"TW": tw}, fx_provider=CountingFx(), price_mode=mode
    )
    summary = build_summary(store, valuator)
    assert [row.valuation.missing for row in summary.positions] == [
        [_token()],
        [],
        [unvalued_token],
    ]
    notes = book.book_notes(
        book.build_book_context(summary, symbol="2330", market="TW", close=600.0, currency="TWD")
    )
    direction = book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=book.UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector="半導體業")
    )
    assert _cause_note(_mismatch_cause(1), direction) in notes
    counts = _cause_counts(notes)
    assert counts["mismatch"] == 1
    assert counts["asked" if mode == "live" else "not_queried"] == 1


# --- KX-A4 / KX-A11 / RX-6 / RX-7: the withdrawn card --------------------------------


QUOTES = [
    pytest.param(_fx(), id="quote-applied"),
    pytest.param(None, id="no-quote"),
    pytest.param(_fx(None, status=DataStatus.UNAVAILABLE, as_of=None), id="quote-unavailable"),
    pytest.param(
        _fx(source="bank_of_taiwan", source_note=SOURCE_NOTES["bank_of_taiwan"]),
        id="quote-applied-bot",
    ),
]

ROWS = [
    pytest.param("AAPL", "US", "TWD", "USD", id="type-A"),
    pytest.param("2330", "TW", "USD", "TWD", id="type-B"),
]


@pytest.mark.parametrize("quote", QUOTES)
@pytest.mark.parametrize(("symbol", "market", "currency", "bar_currency"), ROWS)
def test_kxa4_the_card_withholds_close_and_atr_with_sentence_c_only(
    symbol: str, market: str, currency: str, bar_currency: str, quote: book.FxQuote | None
) -> None:
    summary = _summary(
        _position(1, "2317", sector="其他電子業"),
        _mismatched(2, symbol, market=market, currency=currency),
        # A valued USD row of the same pair: nothing may borrow its disclosure.
        _position(3, "MSFT", market="US", currency="USD", price="400", fx_to_twd="31.5"),
    )
    context = book.build_book_context(
        summary,
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        close=200.0,
        currency=bar_currency,
        atr=4.0,
        fx=quote,
    )
    notes = book.book_notes(context)
    assert context.symbol_notes.count(_mismatch_note()) == 1
    assert context.price_withheld_note == _mismatch_note()
    assert context.fx_rate is None
    assert context.fx_note is None
    assert context.fx_disclosure is None
    _assert_no_fx_wording(notes)
    # RX-7: everything (c) says is not computed is not computed.
    assert context.context.close is None
    assert context.context.atr is None
    budget = RiskBudget()
    checks = {check.id: check.status for check in evaluate_limits(budget, context.context)}
    for limit_id in PRICE_INPUT_LIMIT_IDS:
        assert checks[limit_id] not in {"passed", "violated"}
    assert notional_caps(budget, context.context) == {}
    assert suggest_quantity_range(budget, context.context, action="add") is None


def test_kxa4_a_mixed_holding_keeps_the_mixed_sentence_and_still_counts_b() -> None:
    """K-1 / risk first part RX-6: mixed wins over (c); (b) is still stated."""
    summary = _summary(
        _position(1, "AAPL", market="US", currency="USD", price="200", fx_to_twd="31.5"),
        _mismatched(2, "AAPL", market="US", currency="TWD"),
    )
    context = book.build_book_context(
        summary, symbol="AAPL", market="US", close=200.0, currency="USD", atr=4.0, fx=_fx()
    )
    notes = book.book_notes(context)
    assert book.MIXED_CURRENCY_NOTE in notes
    assert _mismatch_note() not in notes
    assert context.price_withheld_note is None
    assert _cause_counts(notes)["mismatch"] == 1
    assert not any(note.startswith(_head(book.NO_FX_QUOTE_NOTE)) for note in notes)


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        pytest.param(None, book.NO_FX_QUOTE_NOTE.format(currency="USD"), id="no-quote"),
        pytest.param(
            _fx(None, status=DataStatus.UNAVAILABLE, as_of=None),
            book.FX_UNAVAILABLE_NOTE.format(
                currency="USD", pair="USDTWD", status="unavailable", source="fake_fx", as_of="未知"
            ),
            id="quote-unavailable",
        ),
        pytest.param(
            _fx(pair="JPYTWD"),
            book.FX_PAIR_MISMATCH_NOTE.format(currency="USD", expected="USDTWD", pair="JPYTWD"),
            id="pair-mismatch",
        ),
    ],
)
def test_kxa11_a_failed_conversion_keeps_its_own_cause(
    quote: book.FxQuote | None, expected: str
) -> None:
    """``price_withheld_note`` names each failed conversion exactly as before."""
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    context = book.build_book_context(
        summary, symbol="AAPL", market="US", close=200.0, currency="USD", atr=4.0, fx=quote
    )
    assert context.price_withheld_note == context.fx_note == expected
    assert context.context.close is None


def test_kxa11_an_applied_rate_withholds_nothing() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    context = book.build_book_context(
        summary, symbol="AAPL", market="US", close=200.0, currency="USD", atr=4.0, fx=_fx()
    )
    assert context.fx_rate == pytest.approx(31.5)
    assert context.context.close == pytest.approx(200.0)
    # ``fx_note`` states the applied rate; it is not a cause of anything withheld.
    assert context.fx_note is not None
    assert context.fx_note.startswith(_head(book.FX_APPLIED_NOTE))
    assert context.price_withheld_note is None


# --- RX-6: the alert snapshot reads (c) off the book ---------------------------------


def _snapshot_for(
    tmp_path: Path, symbol: str, market: Market, currency: str, *, mixed: bool = False
) -> tuple[SymbolSnapshot, PositionStore, Any]:
    store = PositionStore(db_path=tmp_path / "positions.db")
    _create(store, symbol, market, currency, quantity=100, avg_cost=150)
    if mixed:
        _create(
            store, symbol, market, "USD" if currency == "TWD" else "TWD", quantity=1, avg_cost=1
        )
    service = FakePriceService()
    _seed(service, symbol, 200.0, market=market)
    fx = CountingFx()

    def load(asked: str, asked_market: Market) -> SymbolSnapshot:
        return build_snapshot(
            asked,
            asked_market,
            resolver={market: service},
            store=store,
            valuator=PositionValuator(market_services={market: service}, fx_provider=fx),
            budget=RiskBudget(),
            fx_provider=fx,
        )

    return load(symbol, market), store, load


@pytest.mark.parametrize(
    ("symbol", "market", "currency"),
    [
        pytest.param("AAPL", "US", "TWD", id="type-A"),
        pytest.param("2330", "TW", "USD", id="type-B"),
    ],
)
def test_rx6_the_skip_of_a_price_cap_ends_with_sentence_c(
    tmp_path: Path, symbol: str, market: Market, currency: str
) -> None:
    snap, _, load = _snapshot_for(tmp_path, symbol, market, currency)
    assert snap.close is not None and snap.close > 0  # past the A′ gate
    assert snap.price_cap_cause == _mismatch_note()
    assert snap.fx_disclosure is None
    _assert_no_fx_wording([snap.reason or "", snap.data_disclosure or ""])

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    rule = add_rule(alerts, limit_rule(limit_id="per_trade_loss", symbol=symbol, market=market))
    result = evaluate_alerts(alerts, load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC))
    [outcome] = [o for o in result.outcomes if o.rule_id == rule.id]
    assert outcome.status == "skipped"
    name = LIMIT_NAMES["per_trade_loss"]
    assert outcome.reason == f"監看的上限（{name}）缺少輸入，無法判定是否違反。 {_mismatch_note()}"


def test_rx6_a_mixed_holding_has_no_price_cap_cause(tmp_path: Path) -> None:
    snap, _, _ = _snapshot_for(tmp_path, "AAPL", "US", "USD", mixed=True)
    assert snap.price_cap_cause is None
    assert snap.fx_disclosure is None


def test_rx6_the_snapshot_reads_the_book_and_judges_nothing() -> None:
    source = inspect.getsource(build_snapshot)
    assert "price_cap_cause=book.price_withheld_note" in source
    assert "source_note" not in source
    assert "currency_matches_market" not in source


def test_rx6_a_type_a_snapshot_does_not_depend_on_the_rate(tmp_path: Path) -> None:
    """RX3C-R4: the alert path's counterpart of the type A card check.

    The snapshot loads AAPL's USD bars and asks for USDTWD; the answer may only
    be discarded. With and without a rate the cause, the disclosure, the reason
    and every cap are the same.
    """
    snapshots: dict[bool, SymbolSnapshot] = {}
    for available in (True, False):
        store = PositionStore(db_path=tmp_path / f"snapshot-{available}.db")
        _create(store, "AAPL", "US", "TWD", quantity=100, avg_cost=150)
        service = FakePriceService()
        _seed(service, "AAPL", 200.0, market="US")
        fx = CountingFx(available=available)
        snap = build_snapshot(
            "AAPL",
            "US",
            resolver={"US": service},
            store=store,
            valuator=PositionValuator(market_services={"US": service}, fx_provider=fx),
            budget=RiskBudget(),
            fx_provider=fx,
        )
        # The rate really is asked for, so the equalities below are not vacuous.
        assert fx.calls != []
        assert set(fx.calls) == {"USDTWD"}
        assert snap.price_cap_cause == _mismatch_note()
        assert snap.fx_disclosure is None
        _assert_no_fx_wording([snap.reason or ""])
        assert "匯率" not in (snap.reason or "")
        assert snap.limits
        snapshots[available] = snap
    ok, failed = snapshots[True], snapshots[False]
    assert ok.price_cap_cause == failed.price_cap_cause
    assert ok.fx_disclosure == failed.fx_disclosure
    assert ok.reason == failed.reason
    assert list(ok.limits) == list(failed.limits)


# --- N1-A / N1-B (X3-R5, RX-8, RX-10): the real chain ---------------------------------


@dataclass
class _Book:
    harness: ApiHarness
    fx: CountingFx
    us: FakePriceService
    ids: dict[str, int]

    def card(self, symbol: str, market: Market = "TW") -> dict[str, Any]:
        response = self.harness.client.get(f"/api/advice/{symbol}", params={"market": market})
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        return body

    def summary(self) -> dict[str, Any]:
        body: dict[str, Any] = self.harness.client.get("/api/portfolio/summary").json()
        return body

    def limits(self) -> dict[str, Any]:
        body: dict[str, Any] = self.harness.client.get("/api/portfolio/limits").json()
        return body


def _cap(body: dict[str, Any], limit_id: str) -> dict[str, Any]:
    check: dict[str, Any] = next(c for c in body["advice"]["limits_check"] if c["id"] == limit_id)
    return check


def _book_limit(body: dict[str, Any], limit_id: str) -> dict[str, Any]:
    check: dict[str, Any] = next(c for c in body["limits"] if c["limit_id"] == limit_id)
    return check


def _composition(
    own: int = 0, same: int = 0, other: int = 0, *, tw_unfiled: int = 0, non_tw: int = 0
) -> dict[str, Any]:
    return {
        "own_lots": own,
        "same_sector_lots": same,
        "unknown_sector_lots": {"tw_unfiled": tw_unfiled, "etf": 0, "non_tw": non_tw},
        "other_sector_lots": other,
    }


def _card_notes(body: dict[str, Any]) -> list[str]:
    notes: list[str] = body["context_notes"]
    return notes


def _non_ok(summary: dict[str, Any]) -> int:
    return sum(1 for row in summary["positions"] if row["valuation"]["status"] != "ok")


@pytest.fixture
def n1a(api_harness: ApiHarness, request: pytest.FixtureRequest) -> Iterator[_Book]:
    """N1-A: type A AAPL, valued MSFT and 2330, unvalued 2303 (unless dropped)."""
    with_2303 = getattr(request, "param", True)
    us = FakePriceService()
    _seed(us, "AAPL", 200.0, market="US")
    _seed(us, "MSFT", 400.0, market="US")
    _seed(api_harness.price_service, "2330", 600.0)
    fx = CountingFx()
    serve_us_market(tw_service=api_harness.price_service, us_service=us, fx_provider=fx)
    store = api_harness.positions
    ids = {
        "AAPL": _create(store, "AAPL", "US", "TWD", quantity=100, avg_cost=150).id,
        "MSFT": _create(store, "MSFT", "US", "USD", quantity=10, avg_cost=300).id,
        "2330": _create(
            store, "2330", "TW", "TWD", quantity=1000, avg_cost=500, sector="半導體業"
        ).id,
    }
    if with_2303:
        ids["2303"] = _create(
            store, "2303", "TW", "TWD", quantity=1000, avg_cost=40, sector="半導體業"
        ).id
    yield _Book(api_harness, fx, us, ids)


def test_n1a_valuation_and_summary(n1a: _Book) -> None:
    n1a.us.calls.clear()
    summary = n1a.summary()
    rows = {row["symbol"]: row for row in summary["positions"]}
    aapl = rows["AAPL"]["valuation"]
    assert aapl["status"] == "insufficient_data"
    assert aapl["missing"] == [_token()]
    for key in ("price", "fx", "pnl_original", "pnl_twd"):
        assert aapl[key] is None
    assert rows["AAPL"]["market_value_twd"] is None
    assert rows["AAPL"]["cost_twd"] is None
    assert Decimal(rows["MSFT"]["market_value_twd"]) == Decimal("126000")
    assert Decimal(rows["2330"]["market_value_twd"]) == Decimal("600000")
    assert rows["2303"]["valuation"]["status"] == "insufficient_data"
    # RX-8: the home page's total and the FX disclosure come from MSFT alone.
    assert Decimal(summary["totals"]["market_value_twd"]) == Decimal("726000")
    assert summary["fx_disclosures"] == [SOURCE_NOTES["bank_of_taiwan"]]
    # No price lookup for AAPL by the valuator (the summary loads no bars).
    assert [call[0] for call in n1a.us.calls] == ["MSFT"]


@pytest.mark.parametrize(
    ("n1a", "direction"),
    [
        pytest.param(True, book.UNVALUED_DIRECTION_OWN_AND_OTHERS, id="with-2303-D-d2"),
        pytest.param(False, book.UNVALUED_DIRECTION_OWN_ONLY, id="without-2303-D-d1"),
    ],
    indirect=["n1a"],
)
def test_n1a_the_aapl_card(n1a: _Book, direction: str) -> None:
    body = n1a.card("AAPL", "US")
    with_2303 = "2303" in n1a.ids
    assert body["status"] == "ok"
    context = body["portfolio_context"]
    assert context["unvalued"] == _composition(own=1, other=1 if with_2303 else 0)
    notes = _card_notes(body)
    expected = [_cause_note(_mismatch_cause(1), direction)]
    if with_2303:
        # The card values the book from the cache only (ADR-0010 D-1).
        expected.insert(
            0, _cause_note(book.UNVALUED_POSITIONS_CAUSE_CACHE_ONLY.format(count=1), direction)
        )
    assert [note for note in notes if sum(_cause_counts([note]).values())] == expected
    assert book.SYMBOL_UNVALUED_NOTE.format(count=1) in notes
    assert notes.count(_mismatch_note()) == 1
    assert not any(book.UNVALUED_DIRECTION_READS_HIGH in note for note in notes)
    assert not any(_head(book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW) in note for note in notes)
    _assert_no_fx_wording(notes)
    # ADR-0023 own > 0: caps 1, 4 and 5 do not pass; no share count is offered.
    for limit_id in ("single_position_weight", "per_trade_loss", "kelly_fraction"):
        assert _cap(body, limit_id)["status"] != "passed"
    assert _cap(body, "per_trade_loss")["status"] != "violated"
    assert context["close"] is None and context["atr"] is None
    assert body["advice"]["quantity_range"] is None
    _assert_cause_sum(notes, context["unvalued"], _non_ok(n1a.summary()))


def test_n1a_the_msft_card_reads_high_and_is_true(n1a: _Book) -> None:
    body = n1a.card("MSFT", "US")
    context = body["portfolio_context"]
    assert context["unvalued"] == _composition(other=1, non_tw=1)
    notes = _card_notes(body)
    direction = book.UNVALUED_DIRECTION_READS_HIGH
    assert _cause_note(_mismatch_cause(1), direction) in notes
    assert _cause_note(book.UNVALUED_POSITIONS_CAUSE_CACHE_ONLY.format(count=1), direction) in notes
    assert context["total_equity_twd"] == pytest.approx(726_000.0)
    observed = _cap(body, "single_position_weight")["observed"]
    assert observed == pytest.approx(126_000 / 726_000)
    # The D-a sentence is true: whatever the excluded rows are worth (>= 0),
    # the real share is no higher -- here with AAPL at its true USD value.
    assert observed >= 126_000 / (726_000 + 100 * 200 * 31.5)
    _assert_cause_sum(notes, context["unvalued"], _non_ok(n1a.summary()))


def test_n1a_the_2330_card_reads_d_p(n1a: _Book) -> None:
    body = n1a.card("2330")
    context = body["portfolio_context"]
    assert context["unvalued"] == _composition(same=1, non_tw=1)
    direction = book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=book.UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector="半導體業")
    )
    notes = _card_notes(body)
    assert _cause_note(_mismatch_cause(1), direction) in notes
    # RX-8: the industry group holds 2330 alone.
    assert context["sector_market_value_twd"] == pytest.approx(600_000.0)
    _assert_cause_sum(notes, context["unvalued"], _non_ok(n1a.summary()))


def test_n1a_the_overview(n1a: _Book) -> None:
    body = n1a.limits()
    notes: list[str] = body["notes"]
    direction = book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=book.UNVALUED_DIRECTION_TARGET_BOOK
    )
    # RX-10: (b) is on the overview, after W4 (the overview values live).
    causes = [note for note in notes if sum(_cause_counts([note]).values())]
    assert causes == [
        _cause_note(book.UNVALUED_POSITIONS_CAUSE.format(count=1), direction),
        _cause_note(_mismatch_cause(1), direction),
    ]
    # RX-8: AC-12.5's amount is MSFT's alone (before X-3c: 2 rows, 146,000).
    assert (
        book.SECTOR_UNCLASSIFIED_NOTE.format(
            count=1, amount=126_000.0, share=format_percent(126_000 / 726_000)
        )
        in notes
    )
    # RX-10: AAPL is excluded with the unvalued sentence and the cap's suffix.
    for limit_id in ("single_position_weight", "sector_weight", "per_trade_loss", "kelly_fraction"):
        [excluded] = [e for e in _book_limit(body, limit_id)["excluded"] if e["symbol"] == "AAPL"]
        suffix = (
            SECTOR_UNVALUED_EXCLUSION_SUFFIX
            if limit_id == "sector_weight"
            else UNVALUED_EXCLUSION_SUFFIX
        )
        assert excluded["reason"] == book.SYMBOL_UNVALUED_NOTE.format(count=1) + suffix
        assert "匯率" not in excluded["reason"]
        _assert_no_fx_wording([excluded["reason"]])
    _assert_cause_sum(
        notes,
        {
            "own_lots": 0,
            "same_sector_lots": 0,
            "unknown_sector_lots": {"non_tw": 1},
            "other_sector_lots": 1,
        },
        _non_ok(n1a.summary()),
    )


def _n1a_without_usd_rows(
    api_harness: ApiHarness, *, fx_available: bool, store: PositionStore
) -> _Book:
    """N1-A without MSFT: type A AAPL beside valued 2330 and unvalued 2303.

    MSFT is left out on purpose: it is the one row whose value really depends
    on USDTWD, so with it in the book the two runs below could not be equal.
    """
    tw = api_harness.price_service
    _seed(tw, "2330", 600.0)
    us = FakePriceService()
    _seed(us, "AAPL", 200.0, market="US")
    fx = CountingFx(available=fx_available)
    serve_us_market(tw_service=tw, us_service=us, fx_provider=fx)
    app.dependency_overrides[get_position_store] = lambda: store
    ids = {
        "AAPL": _create(store, "AAPL", "US", "TWD", quantity=100, avg_cost=150).id,
        "2330": _create(
            store, "2330", "TW", "TWD", quantity=1000, avg_cost=500, sector="半導體業"
        ).id,
        "2303": _create(
            store, "2303", "TW", "TWD", quantity=1000, avg_cost=40, sector="半導體業"
        ).id,
    }
    return _Book(api_harness, fx, us, ids)


def test_n1a_the_output_does_not_depend_on_the_rate(
    tmp_path: Path, api_harness: ApiHarness
) -> None:
    """Type A's counterpart of N1-B's check, byte-for-byte with and without a rate.

    Unlike type B, the AAPL card and ``/limits`` still load AAPL's USD bars and
    ask for USDTWD (qa-reviewer's known limitation 1). The answer may only
    exclude the row: no figure, sentence or disclosure may carry it.
    """
    outputs: dict[bool, dict[str, str]] = {}
    for available in (True, False):
        store = PositionStore(db_path=tmp_path / f"n1a-{available}.db")
        n1a = _n1a_without_usd_rows(api_harness, fx_available=available, store=store)
        outputs[available] = {"summary": _without_clock(n1a.summary())}
        # The summary itself asks for nothing: AAPL is the only USD row.
        assert n1a.fx.calls == []
        # Keyed by endpoint so a failure names every response that differs.
        outputs[available] |= {
            "AAPL card": _without_clock(n1a.card("AAPL", "US")),
            "2330 card": _without_clock(n1a.card("2330")),
            "limits": _without_clock(n1a.limits()),
        }
        # The rate really is asked for, so the equality below is not vacuous.
        assert n1a.fx.calls != []
        assert set(n1a.fx.calls) == {"USDTWD"}
    assert outputs[True] == outputs[False]


def test_n1a_correcting_the_row_restores_its_valuation(n1a: _Book) -> None:
    client = n1a.harness.client
    response = client.put(
        f"/api/positions/{n1a.ids['AAPL']}",
        json=position_payload(
            symbol="AAPL", market="US", currency="USD", quantity="100", avg_cost="5"
        ),
    )
    assert response.status_code == 200
    rows = {row["symbol"]: row for row in n1a.summary()["positions"]}
    assert rows["AAPL"]["valuation"]["status"] == "ok"
    assert Decimal(rows["AAPL"]["market_value_twd"]) == Decimal("630000")
    notes = _card_notes(n1a.card("AAPL", "US"))
    assert _mismatch_note() not in notes
    assert _cause_counts(notes)["mismatch"] == 0
    assert _cause_counts(n1a.limits()["notes"])["mismatch"] == 0


def _n1b(
    api_harness: ApiHarness,
    *,
    fx_available: bool,
    variant: str = "base",
    store: PositionStore | None = None,
) -> _Book:
    """N1-B: type B 2330 beside valued 2603 and 2317 and unvalued 1101."""
    tw = api_harness.price_service
    _seed(tw, "2330", 600.0)
    _seed(tw, "2603", 50.0)
    _seed(tw, "2317", 150.0)
    fx = CountingFx(available=fx_available)
    us = FakePriceService()
    serve_us_market(tw_service=tw, us_service=us, fx_provider=fx)
    if store is None:
        store = api_harness.positions
    else:
        app.dependency_overrides[get_position_store] = lambda: store
    b_sector = None if variant == "B3" else "半導體業"
    ids = {
        "2330": _create(
            store, "2330", "TW", "USD", quantity=1000, avg_cost=600, sector=b_sector
        ).id,
        "2603": _create(store, "2603", "TW", "TWD", quantity=1000, avg_cost=40, sector="航運業").id,
        "2317": _create(
            store, "2317", "TW", "TWD", quantity=1000, avg_cost=100, sector="其他電子業"
        ).id,
        "1101": _create(
            store, "1101", "TW", "TWD", quantity=1000, avg_cost=40, sector="水泥工業"
        ).id,
    }
    if variant == "B2":
        _seed(tw, "2454", 600.0)
        ids["2454"] = _create(
            store, "2454", "TW", "TWD", quantity=100, avg_cost=500, sector="半導體業"
        ).id
    return _Book(api_harness, fx, us, ids)


def _without_clock(body: dict[str, Any]) -> str:
    stripped = {key: value for key, value in body.items() if key != "as_of"}
    return json.dumps(stripped, ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize("fx_available", [True, False], ids=["fx-ok", "fx-failed"])
def test_n1b_valuation_and_summary(api_harness: ApiHarness, fx_available: bool) -> None:
    n1b = _n1b(api_harness, fx_available=fx_available)
    summary = n1b.summary()
    rows = {row["symbol"]: row for row in summary["positions"]}
    b_row = rows["2330"]["valuation"]
    assert b_row["status"] == "insufficient_data"
    assert b_row["missing"] == [_token()]
    assert b_row["fx"] is None
    assert summary["fx_disclosures"] == []
    assert Decimal(summary["totals"]["market_value_twd"]) == Decimal("200000")
    # RX-8: no USDTWD lookup at all -- 2330 is the only USD row.
    assert n1b.fx.calls == []


def test_n1b_the_output_does_not_depend_on_the_rate(
    tmp_path: Path, api_harness: ApiHarness
) -> None:
    """KX-A2's short-circuit: with and without a rate, byte-for-byte the same."""
    outputs: dict[bool, list[str]] = {}
    for available in (True, False):
        store = PositionStore(db_path=tmp_path / f"n1b-{available}.db")
        n1b = _n1b(api_harness, fx_available=available, store=store)
        outputs[available] = [
            _without_clock(n1b.summary()),
            _without_clock(n1b.card("2603")),
            _without_clock(n1b.card("2330")),
            _without_clock(n1b.limits()),
        ]
        assert n1b.fx.calls == []
    assert outputs[True] == outputs[False]


def test_n1b_the_2603_card_reads_high_and_is_true(api_harness: ApiHarness) -> None:
    n1b = _n1b(api_harness, fx_available=True)
    body = n1b.card("2603")
    context = body["portfolio_context"]
    assert context["unvalued"] == _composition(other=2)
    notes = _card_notes(body)
    # The other unvalued row's sentence is the 2026-09-18 one, byte for byte,
    # and its count leaves the mismatched row out.
    assert book.UNVALUED_POSITIONS_NOTE_CACHE_ONLY.format(count=1) in notes
    assert _cause_note(_mismatch_cause(1), book.UNVALUED_DIRECTION_READS_HIGH) in notes
    assert context["total_equity_twd"] == pytest.approx(200_000.0)
    observed = _cap(body, "single_position_weight")["observed"]
    assert observed == pytest.approx(0.25)
    assert observed >= 50_000 / (200_000 + 1000 * 600)
    _assert_cause_sum(notes, context["unvalued"], _non_ok(n1b.summary()))


@pytest.mark.parametrize("n1b_variant", ["B2", "B3"])
def test_n1b_variants_name_the_industry_the_row_is_filed_under(
    api_harness: ApiHarness, n1b_variant: str
) -> None:
    n1b = _n1b(api_harness, fx_available=True, variant=n1b_variant)
    symbol, sector, composition = (
        ("2454", "半導體業", _composition(same=1, other=1))
        if n1b_variant == "B2"
        else ("2603", "航運業", _composition(other=1, tw_unfiled=1))
    )
    body = n1b.card(symbol)
    context = body["portfolio_context"]
    assert context["unvalued"] == composition
    direction = book.UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
        target=book.UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector=sector)
    )
    notes = _card_notes(body)
    assert _cause_note(_mismatch_cause(1), direction) in notes
    if n1b_variant == "B2":
        # RX-8: the B row's inflated value is in no industry total.
        assert context["sector_market_value_twd"] == pytest.approx(60_000.0)
    _assert_cause_sum(notes, context["unvalued"], _non_ok(n1b.summary()))


def test_n1b_the_2330_card_is_withdrawn_without_an_fx_cause(api_harness: ApiHarness) -> None:
    n1b = _n1b(api_harness, fx_available=True)
    body = n1b.card("2330")
    context = body["portfolio_context"]
    assert context["unvalued"] == _composition(own=1, other=1)
    notes = _card_notes(body)
    assert _cause_note(_mismatch_cause(1), book.UNVALUED_DIRECTION_OWN_AND_OTHERS) in notes
    assert notes.count(_mismatch_note()) == 1
    _assert_no_fx_wording(notes)
    for limit_id in ("single_position_weight", "per_trade_loss", "kelly_fraction"):
        assert _cap(body, limit_id)["status"] != "passed"
    assert body["advice"]["quantity_range"] is None
    _assert_cause_sum(notes, context["unvalued"], _non_ok(n1b.summary()))


def test_n1b_the_overview(api_harness: ApiHarness) -> None:
    n1b = _n1b(api_harness, fx_available=True)
    body = n1b.limits()
    notes: list[str] = body["notes"]
    direction = book.UNVALUED_DIRECTION_READS_HIGH
    causes = [note for note in notes if sum(_cause_counts([note]).values())]
    assert causes == [
        _cause_note(book.UNVALUED_POSITIONS_CAUSE.format(count=1), direction),
        _cause_note(_mismatch_cause(1), direction),
    ]
    sector_cap = _book_limit(body, "sector_weight")
    assert sector_cap["evaluated_count"] == 2
    assert sector_cap["detail"].startswith(WORST_SECTOR_PREFIX.format(count=2))
    assert sector_cap["observed"] == pytest.approx(0.75)
    [excluded] = [e for e in sector_cap["excluded"] if e["symbol"] == "2330"]
    assert excluded["reason"] == book.SYMBOL_UNVALUED_NOTE.format(
        count=1
    ) + SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX.format(sector="半導體業")
    for check in body["limits"]:
        for entry in check["excluded"]:
            assert "匯率" not in entry["reason"]
    _assert_cause_sum(
        notes,
        {"own_lots": 0, "same_sector_lots": 0, "unknown_sector_lots": {}, "other_sector_lots": 2},
        _non_ok(n1b.summary()),
    )


def test_n1b_the_snapshot_of_another_symbol(api_harness: ApiHarness) -> None:
    n1b = _n1b(api_harness, fx_available=True)
    tw = api_harness.price_service
    snap = build_snapshot(
        "2603",
        "TW",
        resolver={"TW": tw},
        store=api_harness.positions,
        valuator=PositionValuator(market_services={"TW": tw}, fx_provider=n1b.fx),
        budget=RiskBudget(),
        fx_provider=n1b.fx,
    )
    weight = next(check for check in snap.limits if check.id == "single_position_weight")
    assert weight.observed == pytest.approx(0.25)
    assert snap.price_cap_cause is None
    assert snap.fx_disclosure is None
    assert n1b.fx.calls == []


def test_n1b_the_net_worth_yardstick_leaves_the_row_out(api_harness: ApiHarness) -> None:
    """FR-9: the stored yardstick is the valued book without the mismatched row."""
    _n1b(api_harness, fx_available=True)
    response = api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": 400_000.0}}
    )
    assert response.status_code == 200
    stored = response.json()["settings"]["net_worth"]["valued_book_twd_at_report"]
    assert stored == pytest.approx(200_000.0)


# --- XC-N4: the front end's rule and this one read the same table -----------------

#: Written by frontend-engineer for risk XC-N4; the frontend pins its own copy
#: to it (``marketCurrencyShared.test.ts``), and this pins the backend's.
SHARED_MARKET_CURRENCY_PATH = (
    Path(__file__).resolve().parents[2] / "shared" / "market-currency.json"
)


def _shared_market_currency() -> dict[str, str]:
    payload = json.loads(SHARED_MARKET_CURRENCY_PATH.read_text(encoding="utf-8"))
    table: dict[str, str] = payload["market_currency"]
    return table


def test_xcn4_the_backend_table_is_the_shared_table() -> None:
    assert dict(models_module.MARKET_CURRENCY) == _shared_market_currency()


@pytest.mark.parametrize("currency", ["TWD", "USD", "JPY", ""])
@pytest.mark.parametrize("market", ["TW", "US", "HK", "", "toString"])
def test_xcn4_the_rule_matches_the_shared_table_for_every_pair(market: str, currency: str) -> None:
    expected = _shared_market_currency().get(market) == currency
    assert models_module.currency_matches_market(market, currency) is expected
