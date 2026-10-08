"""PR-RK4c: the quote's FX sentences follow what a response shows (RK4-E1b-1).

Risk ruling RK4-E1b-1
(``work/reviews/2026-10-08-E1b卡片與儀表匯率來源並存-RK4-E1b-1-風控.md``) found
that (A′) -- "the quote was applied to a usable close" -- stood in for "the
quote was multiplied into a figure this card or this push shows", and the two
part ways: a card with no ATR, no share range and a hold showed no figure that
used the quote, yet carried the quote's sentence and, on split sources, the
bridge. The tech-architect specification
(``work/reviews/2026-10-08-tech-architect-PR-RK4c規格-RK4-E1b-1報價呈現判斷.md``,
R4c-1 to R4c-17) makes (A′) a necessary condition only:

* the book layer prepares both versions (``fx_disclosure`` /
  ``fx_disclosure_without_quote``, ``symbol_notes`` /
  ``symbol_notes_without_quote``) and judges nothing about what is shown;
* each response picks one with
  :func:`app.advice.limits.shows_price_input_figure` from what it actually
  shows -- the card from its own ``limits_check`` and ``quantity_range``, a
  fired push from the caps its message lists, ``/limits`` from the compared
  holdings (behaviour unchanged).

The risk review of the specification
(``work/reviews/2026-10-08-PR-RK4c規格審查-RK4c-R1～R12-風控.md``) adds RK4c-R1
(the push judges the very ``violated`` list its details come from), RK4c-R2
(the source guards below cover the whole of ``app/``) and RK4c-R9 (premises of
the rewritten expectations, in the files they live in). Expected sentences are
derived from the source that actually answered each lookup (the recording
ladder), never from the scenario's intent.
"""

from __future__ import annotations

import ast
import dataclasses
import typing
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel

import app as app_package
from app.advice import book as book_module
from app.advice.book import (
    BookContext,
    SectorComparison,
    book_notes,
    build_book_context,
    build_book_level_context,
)
from app.advice.book_limits import BookLimitCheck, BookLimits, ExcludedSymbol
from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    PRICE_INPUT_LIMIT_IDS,
    LimitCheck,
    LimitStatus,
    PortfolioContext,
    RiskBudget,
    evaluate_limits,
    shows_price_input_figure,
)
from app.alerts.engine import SymbolSnapshot, evaluate_alerts
from app.alerts.models import AlertEvent
from app.alerts.notify import format_message
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.deps import get_cached_valuator, get_fx_provider, get_market_resolver, get_valuator
from app.api.portfolio import PortfolioLimitsResponse
from app.data.interface import DataStatus, Market
from app.data.service import MIXED_SOURCES_REASON, RECENT_ATTEMPT_FAILED_REASON
from app.main import app
from app.portfolio.valuation import PositionValuator
from app.positions.sectors import TWSE_SECTORS
from app.positions.store import PositionStore
from app.services.fx_notes import source_note
from tests.advice_helpers import book_summary, kelly_inputs, reported_net_worth
from tests.alerts_helpers import add_rule, limit_rule
from tests.api_helpers import FakePriceService, recent_bars
from tests.conftest import ApiHarness
from tests.test_advice_limits import _PRICED_CONTEXTS, BUDGET, T_E1B_2_BACK_TO_RISK, _ctx
from tests.test_rk2_fx_source_set_disclosure import (
    APPROVED_BRIDGE,
    BANK,
    BANK_NOTE,
    CONSISTENT,
    METHODOLOGY,
    MIXED,
    SYMBOL,
    YAHOO,
    YAHOO_NOTE,
    Scenario,
    _Alerts,
    _alerts,
    _clock,
    _hold_usd,
    _quote,
    _RecordingLadder,
    _today,
    _usd,
)
from tests.test_rk4_fx_attribution import (
    APPLIED,
    APPLIED_HEAD,
    BACK_TO_RISK,
    SCOPED,
    SILENT,
    Cell,
    W,
    _cell,
)

APP_ROOT = Path(app_package.__file__).resolve().parent
BACKEND_ROOT = APP_ROOT.parent
NOW = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
#: T-E1b-2 (2): the definition this tripwire also guards (R4c-16).
SHOWN_FIGURE_DEFINITION = f"{T_E1B_2_BACK_TO_RISK} RK4-E1b-1 呈現數字定義"

#: Eight rising daily bars: too short for ATR(14), and no rule asks for a cut.
#: The E1b card: hold, cap 4 ``not_evaluable`` for the ATR, no share range.
E1B_CLOSES = [round(180.0 + 0.5 * index, 4) for index in range(8)]
#: Eight bars falling 25% from the window's high: ``drawdown_protection``
#: matches (R4c-17), cap 1 is violated, so the card sizes a sell range while
#: the ATR is still missing.
DRAWDOWN_CLOSES = [200.0, 200.0, 200.0, 190.0, 180.0, 170.0, 160.0, 150.0]


def _check(limit_id: str, status: LimitStatus) -> LimitCheck:
    return LimitCheck(
        index=LIMIT_IDS.index(limit_id) + 1,
        id=limit_id,
        name=LIMIT_NAMES[limit_id],
        status=status,
        detail="",
        observed=None,
        threshold=None,
    )


def _per_trade(checks: typing.Iterable[LimitCheck]) -> LimitCheck:
    (found,) = [check for check in checks if check.id == "per_trade_loss"]
    return found


# --- R4c-2 / R4c-14: the one predicate, its truth table ---------------------------


@pytest.mark.parametrize(
    ("shown", "sized", "expected"),
    [
        pytest.param([_check("per_trade_loss", "passed")], False, True, id="cap-4-passed"),
        pytest.param([_check("per_trade_loss", "violated")], False, True, id="cap-4-violated"),
        pytest.param(
            [_check("per_trade_loss", "not_evaluable")], False, False, id="cap-4-not-evaluable"
        ),
        pytest.param(
            [
                _check(limit_id, "violated")
                for limit_id in LIMIT_IDS
                if limit_id != "per_trade_loss"
            ],
            False,
            False,
            id="no-cap-4",
        ),
        pytest.param([_check("per_trade_loss", "not_evaluable")], True, True, id="sized"),
        pytest.param([], True, True, id="sized-with-no-verdict"),
        pytest.param([], False, False, id="empty"),
    ],
)
def test_r4c_2_truth_table(shown: list[LimitCheck], sized: bool, expected: bool) -> None:
    assert shows_price_input_figure(shown, sized=sized) is expected
    # Any iterable: ``/limits`` hands over a dict's values, the engine a list.
    assert shows_price_input_figure(iter(shown), sized=sized) is expected


def test_r4c_2_every_price_input_cap_counts() -> None:
    """The predicate reads :data:`PRICE_INPUT_LIMIT_IDS`, not a spelled-out id."""
    assert PRICE_INPUT_LIMIT_IDS  # not vacuous
    for limit_id in LIMIT_IDS:
        shown = [_check(limit_id, "passed")]
        assert shows_price_input_figure(shown, sized=False) is (limit_id in PRICE_INPUT_LIMIT_IDS)


# --- API harness with a chosen bar series -------------------------------------------


def _serve_closes(
    api_harness: ApiHarness, scenario: Scenario, closes: list[float]
) -> tuple[_RecordingLadder, date]:
    """``_serve`` of the RK-2 tests, with ``closes`` as the US symbol's bars."""
    today = _today()
    ladder = scenario.ladder(today)
    us = FakePriceService()
    us.seed(SYMBOL, recent_bars(closes, symbol=SYMBOL, market="US", end=today - timedelta(days=1)))
    services: dict[Market, FakePriceService] = {"TW": api_harness.price_service, "US": us}
    clock = _clock(today)
    valuator = PositionValuator(market_services=services, fx_provider=ladder, clock=clock)
    cached = PositionValuator(
        market_services=services, fx_provider=ladder, clock=clock, price_mode="cache_only"
    )
    app.dependency_overrides[get_market_resolver] = lambda: services
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_cached_valuator] = lambda: cached
    app.dependency_overrides[get_fx_provider] = lambda: ladder
    return ladder, today


def _advice(api_harness: ApiHarness) -> dict[str, typing.Any]:
    body: dict[str, typing.Any] = api_harness.client.get(
        f"/api/advice/{SYMBOL}", params={"market": "US"}
    ).json()
    assert body["status"] == "ok"  # not vacuous: a card was produced
    return body


def _sources(ladder: _RecordingLadder, today: date) -> tuple[str, str]:
    """``(quote source, valuation source)`` as they actually answered."""
    return ladder.source_on(today - timedelta(days=1)), ladder.source_on(today)


def _card_checks(body: dict[str, typing.Any]) -> list[LimitCheck]:
    return [LimitCheck.model_validate(entry) for entry in body["advice"]["limits_check"]]


# --- R4c-14: the E1b card cell -------------------------------------------------------


@pytest.mark.parametrize("scenario", MIXED)
def test_r4c_14_e1b_card_split_sources_states_no_quote_sentence(
    api_harness: ApiHarness, scenario: Scenario
) -> None:
    """The E1b cell, (α): no figure on the card used the quote, so no applied-rate
    sentence, no quote sentence and no bridge -- W-RK4-1, then the valuator's."""
    ladder, today = _serve_closes(api_harness, scenario, E1B_CLOSES)
    _hold_usd(api_harness.positions)
    body = _advice(api_harness)
    quote_source, valuation_source = _sources(ladder, today)
    # Premises: the cell is the E1b one, and the two lookups did split.
    per_trade = _per_trade(_card_checks(body))
    assert per_trade.status == "not_evaluable"
    assert per_trade.detail.startswith("缺少 ATR(14)")
    assert body["advice"]["action"] == "hold"
    assert body["advice"]["quantity_range"] is None
    assert quote_source != valuation_source
    assert body["portfolio_context"]["close"] is not None  # (A′) held: the quote reached it

    notes: list[str] = body["context_notes"]
    assert not any(note.startswith(APPLIED_HEAD) for note in notes)
    assert source_note(quote_source) not in notes
    assert APPROVED_BRIDGE not in notes
    assert notes[-2:] == [W, source_note(valuation_source)]
    assert notes.count(W) == 1


@pytest.mark.parametrize("scenario", CONSISTENT)
def test_r4c_14_e1b_card_same_source_states_the_sentence_once(
    api_harness: ApiHarness, scenario: Scenario
) -> None:
    ladder, today = _serve_closes(api_harness, scenario, E1B_CLOSES)
    _hold_usd(api_harness.positions)
    body = _advice(api_harness)
    quote_source, valuation_source = _sources(ladder, today)
    assert quote_source == valuation_source  # not vacuous
    assert _per_trade(_card_checks(body)).status == "not_evaluable"
    assert body["advice"]["quantity_range"] is None

    notes: list[str] = body["context_notes"]
    assert not any(note.startswith(APPLIED_HEAD) for note in notes)
    assert notes[-2:] == [W, source_note(valuation_source)]
    assert notes.count(source_note(valuation_source)) == 1


# --- R4c-14 / R4c-17: no ATR, but a share range ---------------------------------------


@pytest.mark.parametrize("scenario", MIXED)
def test_r4c_14_no_atr_with_a_share_range_keeps_the_quote_sentences(
    api_harness: ApiHarness, scenario: Scenario
) -> None:
    """The range is priced through the quote, so the card keeps the applied-rate
    sentence, the quote's, the valuator's and the bridge (S-E1b, (s-i))."""
    ladder, today = _serve_closes(api_harness, scenario, DRAWDOWN_CLOSES)
    _hold_usd(api_harness.positions)
    body = _advice(api_harness)
    quote_source, valuation_source = _sources(ladder, today)
    checks = {check.id: check for check in _card_checks(body)}
    # Premises (R4c-17): a range, no ATR, cap 1 violated, split sources.
    assert body["advice"]["quantity_range"] is not None
    assert body["advice"]["action"] in ("reduce", "stop_loss")
    assert checks["per_trade_loss"].status == "not_evaluable"
    assert checks["single_position_weight"].status == "violated"
    assert quote_source != valuation_source

    notes: list[str] = body["context_notes"]
    applied = [index for index, note in enumerate(notes) if note.startswith(APPLIED_HEAD)]
    assert len(applied) == 1
    at = applied[0]
    assert f"來源 {quote_source}" in notes[at]
    assert notes[at + 1 :] == [
        source_note(quote_source),
        source_note(valuation_source),
        APPROVED_BRIDGE,
    ]
    assert W not in notes


# --- R4c-14: the push -------------------------------------------------------------------


def _budget_snapshot(harness: _Alerts, budget: RiskBudget) -> SymbolSnapshot:
    """``_Alerts.snapshot`` with a chosen risk budget."""
    ladder = harness.scenario.ladder(harness.today)
    harness.ladders.append(ladder)
    return build_snapshot(
        SYMBOL,
        "US",
        resolver=dict(harness.resolver),
        store=harness.store,
        valuator=PositionValuator(
            market_services=dict(harness.resolver),
            fx_provider=ladder,
            clock=_clock(harness.today),
        ),
        budget=budget,
        fx_provider=ladder,
        today=harness.today,
    )


def _push(
    tmp_path: Path,
    harness: _Alerts,
    *limit_ids: str,
    budget: RiskBudget | None = None,
) -> tuple[list[AlertEvent], SymbolSnapshot, tuple[str, str]]:
    """Fire one rule per cap id (``any`` by default) in one tick.

    Returns the events, the tick's one snapshot and ``(quote source, valuation
    source)`` as they actually answered for it.
    """
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    for limit_id in limit_ids or ("any",):
        add_rule(alerts, limit_rule(limit_id=limit_id, symbol=SYMBOL, market="US"))
    snaps: list[SymbolSnapshot] = []

    def load(_symbol: str, _market: Market) -> SymbolSnapshot:
        snaps.append(_budget_snapshot(harness, budget or RiskBudget()))
        return snaps[-1]

    result = evaluate_alerts(alerts, load, now=NOW)
    assert len(snaps) == 1  # one snapshot per tick and symbol
    return result.events, snaps[0], _sources(harness.ladders[-1], harness.today)


def _harness_with_closes(tmp_path: Path, scenario: Scenario, closes: list[float]) -> _Alerts:
    today = _today()
    store = PositionStore(db_path=tmp_path / "positions.db")
    _hold_usd(store)
    service = FakePriceService()
    service.seed(
        SYMBOL, recent_bars(closes, symbol=SYMBOL, market="US", end=today - timedelta(days=1))
    )
    return _Alerts(
        store=store, resolver={"US": service}, scenario=scenario, today=today, ladders=[]
    )


@pytest.mark.parametrize("scenario", MIXED)
def test_r4c_14_push_a_cap_1_only_states_the_valuators_sentence_scoped(
    tmp_path: Path, scenario: Scenario
) -> None:
    """(a): RK2-T3's push, default budget -- only cap 1 is listed."""
    events, snap, (quote_source, valuation_source) = _push(tmp_path, _alerts(tmp_path, scenario))
    assert quote_source != valuation_source  # not vacuous
    assert _per_trade(snap.limits).status == "passed"
    expected = f"{W} {source_note(valuation_source)}"
    assert snap.fx_disclosure_without_quote == expected
    assert len(events) == 1
    message = events[0].message
    assert "第 4 條" not in message
    assert message.endswith(f" {expected}")
    assert source_note(quote_source) not in message
    assert APPROVED_BRIDGE not in message


@pytest.mark.parametrize("scenario", MIXED)
def test_r4c_14_push_b_cap_4_listed_states_the_quote_and_the_bridge(
    tmp_path: Path, scenario: Scenario
) -> None:
    """(b): ``max_loss_per_trade=0.001`` -- cap 4 is violated and listed."""
    events, snap, (quote_source, valuation_source) = _push(
        tmp_path, _alerts(tmp_path, scenario), budget=RiskBudget(max_loss_per_trade=0.001)
    )
    assert quote_source != valuation_source  # not vacuous
    assert _per_trade(snap.limits).status == "violated"
    assert len(events) == 1
    message = events[0].message
    assert "第 4 條" in message
    quote_note, valuation_note = source_note(quote_source), source_note(valuation_source)
    assert message.endswith(f" {quote_note} {valuation_note} {APPROVED_BRIDGE}")
    assert W not in message


@pytest.mark.parametrize("scenario", MIXED)
def test_r4c_14_push_c_e1b_bars_state_the_valuators_sentence_scoped(
    tmp_path: Path, scenario: Scenario
) -> None:
    """(c): the E1b bars on the push -- no ATR, cap 1 violated."""
    harness = _harness_with_closes(tmp_path, scenario, E1B_CLOSES)
    events, snap, (quote_source, valuation_source) = _push(tmp_path, harness)
    assert quote_source != valuation_source  # not vacuous
    assert _per_trade(snap.limits).status == "not_evaluable"
    assert snap.fx_disclosure is not None and APPROVED_BRIDGE in snap.fx_disclosure  # (A′)
    assert len(events) == 1
    message = events[0].message
    assert message.endswith(f" {W} {source_note(valuation_source)}")
    assert source_note(quote_source) not in message
    assert APPROVED_BRIDGE not in message


@pytest.mark.parametrize("scenario", MIXED)
def test_r4c_14_push_d_one_tick_two_rules_each_state_their_own(
    tmp_path: Path, scenario: Scenario
) -> None:
    """(d): one snapshot, two rules -- each message judged on its own caps."""
    events, _, (quote_source, valuation_source) = _push(
        tmp_path,
        _alerts(tmp_path, scenario),
        "single_position_weight",
        "per_trade_loss",
        budget=RiskBudget(max_loss_per_trade=0.001),
    )
    assert quote_source != valuation_source  # not vacuous
    quote_note, valuation_note = source_note(quote_source), source_note(valuation_source)
    by_cap = {
        ("第 1 條" in event.message, "第 4 條" in event.message): event.message for event in events
    }
    assert set(by_cap) == {(True, False), (False, True)}
    assert by_cap[(True, False)].endswith(f" {W} {valuation_note}")
    assert quote_note not in by_cap[(True, False)]
    assert by_cap[(False, True)].endswith(f" {quote_note} {valuation_note} {APPROVED_BRIDGE}")
    assert W not in by_cap[(False, True)]


@pytest.mark.parametrize("scenario", CONSISTENT)
def test_r4c_14_push_e_consistent_book(tmp_path: Path, scenario: Scenario) -> None:
    """(e), (γ): cap 1 only gains W-RK4-1; cap 4 listed keeps the one sentence."""
    events, _, (quote_source, valuation_source) = _push(
        tmp_path / "cap-1", _mkdir_alerts(tmp_path / "cap-1", scenario)
    )
    assert quote_source == valuation_source  # not vacuous
    note = source_note(valuation_source)
    assert len(events) == 1
    assert events[0].message.endswith(f" {W} {note}")
    assert events[0].message.count(note) == 1

    events, _, _ = _push(
        tmp_path / "cap-4",
        _mkdir_alerts(tmp_path / "cap-4", scenario),
        budget=RiskBudget(max_loss_per_trade=0.001),
    )
    assert len(events) == 1
    message = events[0].message
    assert "第 4 條" in message
    assert message.endswith(f" {note}")
    assert message.count(note) == 1
    assert W not in message


def _mkdir_alerts(path: Path, scenario: Scenario) -> _Alerts:
    path.mkdir()
    return _alerts(path, scenario)


# --- R4c-14: the W4-T3 matrix, the version without the quote ----------------------------

#: What the version without the quote gives where (A′) holds (R4c-14).
WITHOUT_QUOTE_APPLIED: dict[str, tuple[str, ...] | None] = {
    "a-prime-consistent": (W, BANK_NOTE),
    "a-prime-split": (W, YAHOO_NOTE),
    "a-prime-candidate": None,
}
MATRIX = [
    pytest.param(param.id, param.values[0], id=param.id) for param in (*SCOPED, *SILENT, *APPLIED)
]


def _book(cell: Cell) -> BookContext:
    return build_book_context(
        cell.summary,
        symbol=cell.symbol,
        market=cell.market,
        close=cell.close,
        currency=cell.currency,
        atr=4.0,
        fx=cell.quote,
    )


@pytest.mark.parametrize(("name", "cell"), MATRIX)
def test_r4c_14_w4_t3_without_the_quote(name: str, cell: Cell) -> None:
    book = _book(cell)
    expected = WITHOUT_QUOTE_APPLIED[name] if name in WITHOUT_QUOTE_APPLIED else cell.expected
    joined = None if expected is None else " ".join(expected)
    assert book.fx_disclosure_without_quote == joined
    notes = book_notes(book, quote_shown=False)
    if expected is None:
        assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE, W))
    else:
        assert notes[-len(expected) :] == list(expected)
        assert notes.count(W) == 1
    # No applied-rate sentence without the quote's; a failed conversion's stays.
    assert not any(note.startswith(APPLIED_HEAD) for note in notes)
    if book.fx_note is not None and not book.fx_note.startswith(APPLIED_HEAD):
        assert book.fx_note in notes
    # ``True`` is the version with the quote, the compatibility view's.
    assert book_notes(book, quote_shown=True) == book_notes(book)


@pytest.mark.parametrize(("name", "cell"), MATRIX)
def test_r4c_14_invariants_of_the_two_versions(name: str, cell: Cell) -> None:
    book = _book(cell)
    for quote_shown in (True, False):
        notes = book_notes(book, quote_shown=quote_shown)
        # RK4-R2 in each version: never W-RK4-1 beside the bridge.
        assert not (W in notes and APPROVED_BRIDGE in notes), quote_shown
        # The applied-rate sentence right before W-RK4-1: the RK4-C4 cell only.
        if W in notes and notes.index(W) > 0:
            before = notes[notes.index(W) - 1]
            if before.startswith(APPLIED_HEAD):
                assert name == "test-only-quote-without-sentence", BACK_TO_RISK
    for disclosure in (book.fx_disclosure, book.fx_disclosure_without_quote):
        assert not (W in (disclosure or "") and APPROVED_BRIDGE in (disclosure or ""))
    assert APPROVED_BRIDGE not in (book.fx_disclosure_without_quote or "")
    if book.disclosed_quote is None:
        assert book.fx_disclosure == book.fx_disclosure_without_quote
        assert book.symbol_notes_without_quote == tuple(
            note for note in book.symbol_notes if not note.startswith(APPLIED_HEAD)
        )


def test_r4c_14_the_rk4_c4_cell_is_the_one_an_beside_w() -> None:
    """Not vacuous: the cell the invariant above excuses does put them together."""
    notes = book_notes(_book(_cell(SCOPED, "test-only-quote-without-sentence")))
    assert notes[notes.index(W) - 1].startswith(APPLIED_HEAD)


@pytest.mark.parametrize(("name", "cell"), MATRIX)
def test_r4c_4_each_assembler_runs_as_often_as_before(
    monkeypatch: pytest.MonkeyPatch, name: str, cell: Cell
) -> None:
    """``_fx_disclosures`` (and its mixed-source log line, R4c-10) runs exactly
    where (A′) holds, once; (B) is assembled at most once for both versions."""
    calls: dict[str, int] = {"fx": 0, "valuation": 0}
    fx_disclosures = book_module._fx_disclosures
    valuation_disclosures = book_module._valuation_disclosures

    def counted(key: str, function: Callable[..., tuple[str, ...]]) -> Callable[..., typing.Any]:
        def wrapper(*args: typing.Any) -> tuple[str, ...]:
            calls[key] += 1
            return function(*args)

        return wrapper

    monkeypatch.setattr(book_module, "_fx_disclosures", counted("fx", fx_disclosures))
    monkeypatch.setattr(
        book_module, "_valuation_disclosures", counted("valuation", valuation_disclosures)
    )
    book = _book(cell)
    assert calls["fx"] == (1 if book.disclosed_quote is not None else 0), name
    assert calls["valuation"] <= 1, name


def test_r4c_4_the_new_fields_have_defaults() -> None:
    fields = {field.name: field for field in dataclasses.fields(BookContext)}
    assert fields["fx_disclosure_without_quote"].default is None
    assert fields["symbol_notes_without_quote"].default == ()
    assert BookContext.__dataclass_params__.frozen  # type: ignore[attr-defined]


# --- R4c-6: the finalizer refuses the argument for the book scope -------------------------


@pytest.mark.parametrize("quote_shown", [True, False])
def test_r4c_6_book_scope_refuses_quote_shown(quote_shown: bool) -> None:
    level = build_book_level_context(book_summary(_usd(1, source=BANK)))
    comparison = SectorComparison(reported_sector=None)
    assert book_notes(level, sector_comparison=comparison)  # not vacuous: it does work
    with pytest.raises(ValueError, match="quote_shown"):
        book_notes(level, sector_comparison=comparison, quote_shown=quote_shown)


def test_r4c_6_a_symbol_scope_none_is_the_version_with_the_quote() -> None:
    book = build_book_context(
        book_summary(_usd(1, source=YAHOO)),
        symbol=SYMBOL,
        market="US",
        close=200.0,
        currency="USD",
        atr=4.0,
        fx=_quote(BANK),
    )
    assert book.symbol_notes != book.symbol_notes_without_quote  # not vacuous
    assert book_notes(book) == book_notes(book, quote_shown=True)
    assert book_notes(book)[-len(book.symbol_notes) :] == list(book.symbol_notes)
    without = book_notes(book, quote_shown=False)
    assert without[-len(book.symbol_notes_without_quote) :] == list(book.symbol_notes_without_quote)


# --- R4c-14 / RK4c-R2: source guards over app/ --------------------------------------------


def _modules() -> list[tuple[str, ast.Module]]:
    found = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(BACKEND_ROOT).as_posix()
        found.append((relative, ast.parse(path.read_text(encoding="utf-8"))))
    assert found  # not vacuous
    return found


def _scoped_nodes(tree: ast.Module) -> Iterator[tuple[str, ast.AST]]:
    """Every node with the qualified name of the function or class around it."""

    def walk(node: ast.AST, scope: str) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            yield scope, child
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                yield from walk(child, f"{scope}.{child.name}" if scope else child.name)
            else:
                yield from walk(child, scope)

    yield from walk(tree, "")


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_rk4c_r2_every_symbol_scope_book_notes_call_passes_quote_shown() -> None:
    """RK4c-R2: in all of ``app/``, a symbol-scope ``book_notes`` call carries
    ``quote_shown=``; the book-scope one (``sector_comparison=``) does not. The
    compatibility view :attr:`BookContext.notes` is the one exception: no
    production code reads it (ADR-0023 KD-2)."""
    symbol_scope: list[str] = []
    book_scope: list[str] = []
    for relative, tree in _modules():
        for scope, node in _scoped_nodes(tree):
            if not isinstance(node, ast.Call) or _called_name(node) != "book_notes":
                continue
            keywords = {keyword.arg for keyword in node.keywords}
            where = f"{relative}::{scope}"
            if "sector_comparison" in keywords:
                book_scope.append(where)
                assert "quote_shown" not in keywords, where
            elif where == "app/advice/book.py::BookContext.notes":
                assert keywords == set(), where
            else:
                symbol_scope.append(where)
                assert "quote_shown" in keywords, where
    assert book_scope == ["app/advice/book_limits.py::evaluate_book_limits"]
    assert symbol_scope.count("app/api/advice.py::get_advice") == 2  # not vacuous


def test_r4c_3_the_book_layer_neither_judges_nor_reads_the_cap_ids() -> None:
    """R4c-3: ``book.py`` does not import the predicate and its code does not
    read :data:`PRICE_INPUT_LIMIT_IDS` (comments may name it)."""
    tree = ast.parse(Path(book_module.__file__).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom | ast.Import)
        for alias in node.names
    }
    for forbidden in ("shows_price_input_figure", "PRICE_INPUT_LIMIT_IDS"):
        assert forbidden not in names | attributes | imported, forbidden


def test_r4c_2_only_the_allowed_places_read_the_price_input_ids() -> None:
    """R4c-2: ``limits.py`` itself and ``alerts/engine.py::_limit_cause``."""
    readers = set()
    for relative, tree in _modules():
        for scope, node in _scoped_nodes(tree):
            if isinstance(node, ast.Name) and node.id == "PRICE_INPUT_LIMIT_IDS":
                readers.add(
                    relative if relative == "app/advice/limits.py" else f"{relative}::{scope}"
                )
    assert readers == {"app/advice/limits.py", "app/alerts/engine.py::_limit_cause"}


def test_rk4c_r2_only_the_push_reads_the_snapshots_disclosures() -> None:
    """RK4c-R2: outside ``_limit_outcome`` nothing in ``app/`` reads either
    disclosure field to build text; ``build_snapshot`` only carries the book
    layer's two fields over."""
    reads = set()
    fields = {"fx_disclosure", "fx_disclosure_without_quote"}
    for relative, tree in _modules():
        for scope, node in _scoped_nodes(tree):
            if isinstance(node, ast.Attribute) and node.attr in fields:
                assert isinstance(node.ctx, ast.Load)
                owner = node.value.id if isinstance(node.value, ast.Name) else "?"
                reads.add((relative, scope, f"{owner}.{node.attr}"))
            if isinstance(node, ast.Constant) and node.value in fields:
                pytest.fail(f"{relative}::{scope} names a disclosure field as a string")
    assert reads == {
        ("app/alerts/engine.py", "_limit_outcome", "snapshot.fx_disclosure"),
        ("app/alerts/engine.py", "_limit_outcome", "snapshot.fx_disclosure_without_quote"),
        ("app/alerts/snapshot.py", "build_snapshot", "book.fx_disclosure"),
        ("app/alerts/snapshot.py", "build_snapshot", "book.fx_disclosure_without_quote"),
    }


def test_rk4c_r1_the_push_judges_the_list_its_details_come_from() -> None:
    """RK4c-R1: ``_limit_outcome`` passes the predicate the very ``violated``
    name that ``details`` is joined from, with ``sized=False``."""
    tree = ast.parse((APP_ROOT / "alerts" / "engine.py").read_text(encoding="utf-8"))
    (function,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_limit_outcome"
    ]
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and _called_name(node) == "shows_price_input_figure"
    ]
    assert len(calls) == 1
    (call,) = calls
    assert [ast.unparse(arg) for arg in call.args] == ["violated"]
    assert [(k.arg, ast.unparse(k.value)) for k in call.keywords] == [("sized", "False")]
    details = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "details" for t in node.targets)
    ]
    assert len(details) == 1
    assert "for check in violated" in ast.unparse(details[0].value)
    assigned = [
        target.id
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    assert assigned.count("violated") == 1  # never rebound between the two


# --- R4c-14: the longest push with the scope sentence still fits -----------------------


def test_r4c_14_worst_case_push_without_the_quote_is_at_most_2000_characters(
    tmp_path: Path,
) -> None:
    """Caps 1, 2, 3 and 5 violated with the largest figures the inputs allow,
    cap 4 not listed, W-RK4-1, the longest source sentence and a degraded data
    layer (the RK4-R10 variant)."""
    symbol = "ABCDEFGHIJKL"
    sector = max(TWSE_SECTORS, key=len)
    context = PortfolioContext(
        symbol=symbol,
        total_equity_twd=987_654_321_098.0,
        position_market_value_twd=876_543_210_987.0,
        position_cost_twd=765_432_109_876.0,
        gross_exposure_twd=987_654_321_098.0,
        net_worth=reported_net_worth(123_456_789.0, age_days=6),
        book_fully_valued=True,
        quantity=9_876_543_210.0,
        close=98_765.4321,
        fx_to_twd=31.4567,
        atr=None,
        sector=sector,
        sector_market_value_twd=876_543_210_987.0,
        kelly=kelly_inputs(0.61, 1.87, age_days=29),
    )
    checks = evaluate_limits(RiskBudget(), context)
    statuses = {check.id: check.status for check in checks}
    assert statuses.pop("per_trade_loss") == "not_evaluable"
    assert set(statuses.values()) == {"violated"}
    longest = max(METHODOLOGY, key=len)

    def load(_symbol: str, market: Market) -> SymbolSnapshot:
        return SymbolSnapshot(
            symbol=symbol,
            market="US",
            limits=checks,
            fx_disclosure=f"{longest} {longest} {APPROVED_BRIDGE}",
            fx_disclosure_without_quote=f"{W} {longest}",
            data_disclosure=(
                f"資料來自 {DataStatus.CACHED_STALE.value} 層（twse_openapi）。 "
                f"{RECENT_ATTEMPT_FAILED_REASON} "
                f"{MIXED_SOURCES_REASON.format(sources='yfinance、alpha_vantage、finmind')}"
            ),
        )

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    add_rule(alerts, limit_rule(limit_id="any", symbol=symbol, market="US"))
    result = evaluate_alerts(alerts, load, now=NOW)
    assert len(result.events) == 1
    text = format_message(result.events[0])
    assert f"{W} {longest}" in text
    assert APPROVED_BRIDGE not in text
    assert len(text) <= 2000, len(text)


# --- R4c-16: T-E1b-2 tripwires ---------------------------------------------------------


def _price_variants(overrides: dict[str, typing.Any]) -> list[dict[str, typing.Any]]:
    """The close, the ATR and the rate of one priced context, each moved alone."""
    base = _ctx(**overrides)
    assert base.close is not None and base.atr is not None
    rate = base.fx_to_twd
    return [
        {"fx_to_twd": 29.0 if rate == 31.5 else 31.5},
        {"fx_to_twd": rate * 2},
        {"close": base.close * 2},
        {"atr": base.atr * 2},
        {"close": base.close * 2, "atr": base.atr * 2, "fx_to_twd": rate * 2},
    ]


@pytest.mark.parametrize("budget", [BUDGET, RiskBudget(max_loss_per_trade=0.001)])
@pytest.mark.parametrize("overrides", _PRICED_CONTEXTS)
def test_r4c_16_only_the_price_input_caps_read_the_price_the_atr_or_the_rate(
    overrides: dict[str, typing.Any], budget: RiskBudget
) -> None:
    """T-E1b-2 (2): every other cap's whole verdict -- status, detail and
    observed value -- is the same whatever the close, the ATR and the rate."""
    base = _ctx(**overrides)
    before = {check.id: check for check in evaluate_limits(budget, base)}
    for change in _price_variants(overrides):
        moved = base.model_copy(update=change)
        after = {check.id: check for check in evaluate_limits(budget, moved)}
        for limit_id in LIMIT_IDS:
            if limit_id in PRICE_INPUT_LIMIT_IDS:
                continue
            assert after[limit_id] == before[limit_id], (SHOWN_FIGURE_DEFINITION, change)


def _field_names(model: type[BaseModel], seen: set[type[BaseModel]]) -> Iterator[str]:
    """Every field name of ``model`` and of the models nested in it."""
    if model in seen:
        return
    seen.add(model)
    for name, info in model.model_fields.items():
        yield name
        for nested in _models_in(info.annotation):
            yield from _field_names(nested, seen)


def _models_in(annotation: object) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
    for argument in typing.get_args(annotation):
        yield from _models_in(argument)


def test_r4c_16_limits_shows_no_share_range() -> None:
    """T-E1b-2 (3): ``/limits`` G1 rests on the overview showing no figure but
    the caps' verdicts -- no share range, nothing priced through the quote."""
    assert set(BookLimitCheck.model_fields) == {
        "index",
        "limit_id",
        "name",
        "status",
        "observed",
        "threshold",
        "detail",
        "worst_symbol",
        "evaluated_count",
        "excluded",
    }, T_E1B_2_BACK_TO_RISK
    assert set(ExcludedSymbol.model_fields) == {"symbol", "market", "reason"}, T_E1B_2_BACK_TO_RISK
    assert set(BookLimits.model_fields) == {"limits", "notes"}, T_E1B_2_BACK_TO_RISK
    assert set(PortfolioLimitsResponse.model_fields) == {
        "limits",
        "notes",
        "sources",
        "as_of",
    }, T_E1B_2_BACK_TO_RISK
    names = set(_field_names(PortfolioLimitsResponse, set()))
    assert "worst_symbol" in names  # not vacuous: the nested models were walked
    for word in ("quantity", "shares", "range", "price", "atr", "fx"):
        assert not [name for name in names if word in name], (T_E1B_2_BACK_TO_RISK, word)
