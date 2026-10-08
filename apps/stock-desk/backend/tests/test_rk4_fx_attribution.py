"""RK-4 (PR-RK4a): a converted market value carries its source sentence, scoped.

Task RK-4
(``work/dispatch/2026-10-08-任務單-RK-4-匯率已換算卻無來源句的缺漏型揭露.md``) and
the second revision of X3-R1 (risk RK4-R1): a context's FX source sentences
appear if and only if

* (A′) ``_resolve_fx`` applied a quote, the close it converts is usable and the
  quote carries a sentence -- the RK-2 content, unchanged; or
* (B) at least one of this symbol's own lots is ``ok`` with a valuator rate
  that is neither ``None`` nor ``UNAVAILABLE`` and carries a sentence.

When only (B) holds, the valuator's sentence(s) follow the risk-approved scope
sentence W-RK4-1 (:data:`app.advice.book.FX_VALUATION_SCOPE_NOTE`): it comes
first, right after any failed-conversion note, so the sentence after it is not
read as covering the price and the ATR, which were withheld. The bridge
(:data:`app.advice.book.FX_MIXED_SOURCES_NOTE`) only ever follows (A′); the two
never meet (RK4-R2).

The test names carry the W4-T numbers of the risk review
``work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md``, the
RK4-C numbers of ``work/reviews/2026-10-08-RK-4規格四點確認-RK4-C1～C5-風控.md``
and the R4-x constraints of the tech-architect specification
``work/reviews/2026-10-08-tech-architect-RK-4實作規格-R5-10補段-S-L3查證.md``.
Expected sentences are derived from the source that actually answered each
valuator lookup (the recording ladder), never from the scenario's intent.

Re-review trigger (risk RK4-C1(d), clause 3): when ADR-0015 W11 (the
cross-request FX rate cache) is wired, configuration E4 of PR-RK4b ("/limits",
two or more distinct quote sources among the compared holdings) goes back to
risk-compliance for re-review. A cache hit reports the cached row's original
source id, and rows written while Bank of Taiwan answered can outlive a block,
so E4 may become reachable even while Bank of Taiwan is blocked. The same
wiring is covered for this PR by the one-source-per-pair invariant below
(W4-T11 / RK4-R9).
"""

from __future__ import annotations

import inspect
import logging
import re
import typing
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.advice import book as book_module
from app.advice.book import (
    FX_APPLIED_NOTE,
    MIXED_CURRENCY_NOTE,
    NO_FX_QUOTE_NOTE,
    FxQuote,
    book_notes,
    build_book_context,
)
from app.advice.limits import LIMIT_IDS, PortfolioContext, RiskBudget, evaluate_limits
from app.advice.loader import BANNED_PHRASES
from app.alerts.engine import SymbolSnapshot, evaluate_alerts
from app.alerts.notify import format_message
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api import deps
from app.api.deps import get_cached_valuator, get_fx_provider, get_market_resolver, get_valuator
from app.data.interface import DataStatus, Market
from app.data.providers.fx import FxRateLadder
from app.data.service import MIXED_SOURCES_REASON, RECENT_ATTEMPT_FAILED_REASON
from app.main import app
from app.portfolio.summary import PortfolioSummary, SummaryPosition, build_summary
from app.portfolio.valuation import CURRENCY_MARKET_MISMATCH, FxInfo, PositionValuator
from app.positions.models import Currency, PositionInput
from app.positions.sectors import TWSE_SECTORS
from app.positions.store import PositionStore
from app.services import fx_notes
from app.services.fx_notes import GENERIC_SOURCE_NOTE, SOURCE_NOTES, source_note
from tests.advice_helpers import book_position, book_summary, kelly_inputs, reported_net_worth
from tests.alerts_helpers import add_rule, limit_rule
from tests.api_helpers import FakePriceService, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.test_rk2_fx_source_set_disclosure import (
    APPROVED_BRIDGE,
    BANK,
    BANK_NOTE,
    BOOK_LOGGER,
    METHODOLOGY,
    OPENED,
    QUANTITY,
    RK2_FORBIDDEN,
    SYMBOL,
    YAHOO,
    YAHOO_NOTE,
    Scenario,
    _alerts,
    _always,
    _BankRung,
    _book_records,
    _card,
    _clock,
    _fire,
    _hold_usd,
    _never,
    _quote,
    _RecordingLadder,
    _serve,
    _shared_forbidden_terms,
    _today,
    _us_service,
    _usd,
    _YahooRung,
)
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

#: W-RK4-1 as risk-compliance approved it verbatim (alternative A, 2026-10-08).
#: Kept here as a literal on purpose: W4-T1 compares the production constant
#: against it, so an edit to either side is a red test, not a silent drift.
APPROVED_SCOPE_NOTE = (
    "此處來源說明所指的匯率，只對應持倉市值與總資產中經換算的部分，不含價格與 ATR。"
)
W = APPROVED_SCOPE_NOTE
APPROVAL_MARK = "風控核可文案,修改須重新送審(2026-10-08)"
APPROVAL_FILE = "work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md"
#: The failure message every premise tripwire of this wording carries (W4-T11).
BACK_TO_RISK = "回風控重審 W-RK4-1、W-RK5-1"

#: Every failed-conversion sentence a scope sentence can sit next to, by a
#: phrase only that sentence has (RK4-R3).
UNAVAILABLE_PHRASE = "匯率報價沒有可用數值"
PAIR_MISMATCH_PHRASE = "但取得的報價是"
NO_QUOTE_PHRASE = "沒有取得任何匯率報價"
APPLIED_HEAD = FX_APPLIED_NOTE.split("{", 1)[0]

TWD_LOT = book_position(4, SYMBOL, market="US", currency="TWD", price="6000")


def _other_pair_quote(source: str = YAHOO) -> FxQuote:
    """A quote for a pair the USD holding does not need (``FX_PAIR_MISMATCH_NOTE``)."""
    return FxQuote(
        pair="JPYTWD",
        rate=0.21,
        as_of="2026-10-07",
        source=source,
        status=DataStatus.FRESH,
        source_note=source_note(source),
    )


def _with_fx(row: SummaryPosition, fx: FxInfo | None) -> SummaryPosition:
    return row.model_copy(update={"valuation": row.valuation.model_copy(update={"fx": fx})})


def _bank_fx(pair: str = "USDTWD") -> FxInfo:
    return FxInfo(
        pair=pair,
        as_of="2026-10-08",
        source=BANK,
        data_status=DataStatus.FRESH,
        source_note=BANK_NOTE,
    )


def _with_fx_open(row: SummaryPosition, source: str) -> SummaryPosition:
    """``row`` whose open-date rate came from ``source`` (task RK-5's ``fx_open``)."""
    fx_open = FxInfo(
        pair="USDTWD",
        as_of=OPENED.isoformat(),
        source=source,
        data_status=DataStatus.FRESH,
        source_note=source_note(source),
    )
    valuation = row.valuation.model_copy(update={"fx_open": fx_open})
    return row.model_copy(update={"valuation": valuation})


class Cell(typing.NamedTuple):
    """One book-unit cell of the W4-T3 matrix: inputs and the disclosure it must give."""

    summary: PortfolioSummary
    quote: FxQuote | None
    #: The sentences of ``fx_disclosure`` in order, or ``None`` for no disclosure.
    expected: tuple[str, ...] | None
    symbol: str = SYMBOL
    market: Market = "US"
    currency: str | None = "USD"
    close: float | None = 200.0


def _build(cell: Cell) -> tuple[book_module.BookContext, list[str]]:
    book = build_book_context(
        cell.summary,
        symbol=cell.symbol,
        market=cell.market,
        close=cell.close,
        currency=cell.currency,
        atr=4.0,
        fx=cell.quote,
    )
    return book, book_notes(book)


#: (A′) does not hold and (B) does: the scope sentence, then the valuator's.
SCOPED = [
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK)), _quote(YAHOO, rate=None), (W, BANK_NOTE)),
        id="2a-unavailable-quote",
    ),
    pytest.param(
        # S-1 in the (B) branch: two unknown ids sharing GENERIC_SOURCE_NOTE;
        # the quote's id is not counted, the valuator's one is.
        Cell(
            book_summary(_usd(1, source="fx_other")),
            _quote("fx_one", rate=None),
            (W, GENERIC_SOURCE_NOTE),
        ),
        id="2a-generic-sources",
    ),
    pytest.param(
        # What /api/advice hands over when the card has no usable close (2c).
        Cell(book_summary(_usd(1, source=BANK)), None, (W, BANK_NOTE), currency=None, close=None),
        id="2c-no-quote",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK)), _other_pair_quote(), (W, BANK_NOTE)),
        id="pair-mismatch",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK), TWD_LOT), _quote(YAHOO), (W, BANK_NOTE)),
        id="mixed-currencies-usd-lot-ok",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source=YAHOO)), _quote(BANK), (W, YAHOO_NOTE), close=None),
        id="o1-held-split-sources",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK)), _quote(BANK), (W, BANK_NOTE), close=None),
        id="o1-held-same-source",
    ),
    pytest.param(
        # Test-only cell (risk RK4-C4): production never builds a quote that
        # has a rate and an empty sentence -- ``source_note`` is empty for the
        # ladder's ``"none"`` only, and ``"none"`` never carries a rate.
        Cell(book_summary(_usd(1, source=YAHOO)), _quote(BANK, note=""), (W, YAHOO_NOTE)),
        id="test-only-quote-without-sentence",
    ),
    pytest.param(
        # Test-only cell: two sources in one summary for one pair (the memo
        # makes this unreachable, RK4-R9). Exactly two items of two ids, and
        # still no bridge: the bridge belongs to (A′) only.
        Cell(
            book_summary(_usd(1, source=BANK), _usd(2, source="fx_other", symbol="MSFT")),
            _quote(YAHOO, rate=None),
            (W, BANK_NOTE, GENERIC_SOURCE_NOTE),
        ),
        id="two-valuator-ids-never-bridged",
    ),
    pytest.param(
        # R4-12: only ``valuation.fx`` is read; the open-date rate's source
        # (another lookup, priced into the cost) contributes no sentence.
        Cell(
            book_summary(_with_fx_open(_usd(1, source=BANK), YAHOO)),
            _quote("fx_one", rate=None),
            (W, BANK_NOTE),
        ),
        id="fx-open-on-another-source-is-not-read",
    ),
]

#: Neither (A′) nor (B): no source sentence at all.
SILENT = [
    pytest.param(
        Cell(book_summary(_usd(1, source=YAHOO, symbol="MSFT")), _quote(BANK), None, close=None),
        id="o1-not-held",
    ),
    pytest.param(
        Cell(
            book_summary(_usd(1, source="none", note="", data_status=DataStatus.UNAVAILABLE)),
            _quote(YAHOO, rate=None),
            None,
        ),
        id="2b-unapplied",
    ),
    pytest.param(
        # A hand-built ``ok`` row whose rate is UNAVAILABLE with a sentence.
        Cell(
            book_summary(_usd(1, source="fx_other", data_status=DataStatus.UNAVAILABLE)),
            _quote(YAHOO, rate=None),
            None,
        ),
        id="2b-unavailable-rate-on-ok-row",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK, priced=False)), _quote(YAHOO, rate=None), None),
        id="scenario-9-unvalued-row",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source="fx_silent", note="")), _quote(YAHOO, rate=None), None),
        id="valuator-note-empty",
    ),
    pytest.param(
        # R4-12: an ``fx_open`` with a sentence does not stand in for an
        # unusable ``fx`` (hand-built: such a row is not ``ok`` in production).
        Cell(
            book_summary(
                _with_fx_open(
                    _usd(1, source="none", note="", data_status=DataStatus.UNAVAILABLE), BANK
                )
            ),
            _quote(YAHOO, rate=None),
            None,
        ),
        id="fx-open-alone-does-not-qualify",
    ),
    pytest.param(
        Cell(
            book_summary(
                book_position(1, SYMBOL, market="US", currency="USD", price="200", fx_to_twd="31")
            ),
            _quote(YAHOO, rate=None),
            None,
        ),
        id="valuator-fx-none",
    ),
    pytest.param(
        # O-3: a TWD symbol whose denominator holds converted USD rows.
        Cell(
            book_summary(_usd(1, source=BANK, symbol="MSFT"), book_position(3, "2330")),
            _quote(YAHOO),
            None,
            symbol="2330",
            market="TW",
            currency="TWD",
            close=600.0,
        ),
        id="twd-symbol",
    ),
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK, symbol="MSFT")), _quote(YAHOO, rate=None), None),
        id="candidate-not-held",
    ),
    pytest.param(
        # W4-T9, hand-built: an X-3 type-B row (TW market, USD) *as if* the
        # valuator had valued it -- KX-A11 decides before (B) is looked at.
        Cell(
            book_summary(
                _with_fx(
                    book_position(
                        1, "2330", market="TW", currency="USD", price="600", fx_to_twd="31.5"
                    ),
                    _bank_fx(),
                )
            ),
            _quote(YAHOO),
            None,
            symbol="2330",
            market="TW",
            currency="TWD",
            close=600.0,
        ),
        id="mismatch-type-b-hand-built-ok",
    ),
    pytest.param(
        # W4-T9, hand-built: an X-3 type-A row (US market, TWD) carrying a rate.
        Cell(
            book_summary(
                _with_fx(book_position(1, SYMBOL, market="US", currency="TWD"), _bank_fx())
            ),
            _quote(YAHOO),
            None,
        ),
        id="mismatch-type-a-hand-built-ok",
    ),
]

#: (A′) holds: the RK-2 content, byte for byte (R4-4).
APPLIED = [
    pytest.param(
        Cell(book_summary(_usd(1, source=BANK)), _quote(BANK), (BANK_NOTE,)),
        id="a-prime-consistent",
    ),
    pytest.param(
        Cell(
            book_summary(_usd(1, source=YAHOO)),
            _quote(BANK),
            (BANK_NOTE, YAHOO_NOTE, APPROVED_BRIDGE),
        ),
        id="a-prime-split",
    ),
    pytest.param(
        Cell(
            book_summary(_usd(1, source=YAHOO, symbol="MSFT")),
            _quote(BANK),
            (BANK_NOTE, YAHOO_NOTE, APPROVED_BRIDGE),
        ),
        id="a-prime-candidate",
    ),
]


def _cell(params: list[typing.Any], wanted: str) -> Cell:
    """The cell behind the ``pytest.param`` whose id is ``wanted``."""
    for param in params:
        if param.id == wanted:
            cell = param.values[0]
            assert isinstance(cell, Cell)
            return cell
    raise KeyError(wanted)


# --- W4-T1 / W4-T2: the wording itself --------------------------------------------


def test_w4_t1_the_scope_note_is_the_approved_wording() -> None:
    scope = book_module.FX_VALUATION_SCOPE_NOTE
    assert scope == APPROVED_SCOPE_NOTE
    assert len(scope) == 41
    source = inspect.getsource(book_module)
    marker = source.index("FX_VALUATION_SCOPE_NOTE = ")
    header = source[source.rindex("\n\n", 0, marker) : marker]
    assert APPROVAL_MARK in header
    assert APPROVAL_FILE in header
    # A book-layer sentence: never a source's standing disclosure.
    assert APPROVED_SCOPE_NOTE not in inspect.getsource(fx_notes)
    assert APPROVED_SCOPE_NOTE not in SOURCE_NOTES.values()
    for source_id in (*SOURCE_NOTES, "none", "fx_unknown"):
        assert source_note(source_id) != APPROVED_SCOPE_NOTE


#: W4-T2's own list on top of the three shared ones and RK2-T8's.
W4_T2_FORBIDDEN = (
    "本次",
    "取得",
    "上方",
    "下方",
    "上列",
    "下列",
    "前述",
    "如上",
    "全部",
    "整筆",
    "所有",
    "估值器",
    "snapshot",
    "梯子",
    "fx_now",
    "fx_open",
    "source id",
)


def test_w4_t2_the_scope_note_passes_every_wording_scan() -> None:
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert terms  # not vacuous
    assert [term for term in sorted(terms) if term in APPROVED_SCOPE_NOTE] == []
    assert find_bare_realtime_claims(APPROVED_SCOPE_NOTE) == []
    assert [term for term in RK2_FORBIDDEN if term in APPROVED_SCOPE_NOTE] == []
    assert [term for term in W4_T2_FORBIDDEN if term in APPROVED_SCOPE_NOTE] == []
    assert re.search(r"[0-9０-９]", APPROVED_SCOPE_NOTE) is None
    for required in ("持倉市值與總資產", "經換算的部分", "不含價格與 ATR"):
        assert required in APPROVED_SCOPE_NOTE


# --- W4-T3 / W4-T5: when it appears, and never beside the bridge -------------------


@pytest.mark.parametrize("cell", [*SCOPED, *SILENT, *APPLIED])
def test_w4_t3_w4_t5_scope_note_iff_not_a_prime_and_b(cell: Cell) -> None:
    book, notes = _build(cell)
    expected = None if cell.expected is None else " ".join(cell.expected)
    assert book.fx_disclosure == expected
    scoped = cell.expected is not None and cell.expected[0] == W
    assert (W in notes) is scoped
    assert notes.count(W) == (1 if scoped else 0)
    # W4-T5 / RK4-R2: never both, in any cell.
    assert not (W in notes and APPROVED_BRIDGE in notes)
    if cell.expected is None:
        assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE, W))


@pytest.mark.parametrize("cell", SCOPED)
def test_r4_13_the_scoped_branch_never_attaches_the_bridge(cell: Cell) -> None:
    book, notes = _build(cell)
    assert APPROVED_BRIDGE not in notes
    assert APPROVED_BRIDGE not in (book.fx_disclosure or "")


# --- W4-T4: order and adjacency, card notes and the pushed field -------------------


@pytest.mark.parametrize("cell", SCOPED)
def test_w4_t4_scope_note_first_then_the_sentences_it_scopes(cell: Cell) -> None:
    book, notes = _build(cell)
    assert cell.expected is not None
    # The pushed field: W-RK4-1 is its first item, joined by single spaces.
    assert book.fx_disclosure is not None
    assert book.fx_disclosure.startswith(f"{W} ")
    # The card: fx_note (if any) -> W-RK4-1 -> the sentences, contiguous, last.
    at = notes.index(W)
    assert notes[at:] == list(cell.expected)
    before = notes[at - 1]
    if book.fx_note is not None:
        assert before == book.fx_note
    else:
        assert before == MIXED_CURRENCY_NOTE


@pytest.mark.parametrize(
    ("cell", "phrase"),
    [
        (_cell(SCOPED, "2a-unavailable-quote"), UNAVAILABLE_PHRASE),
        (_cell(SCOPED, "2c-no-quote"), NO_QUOTE_PHRASE),
        (_cell(SCOPED, "pair-mismatch"), PAIR_MISMATCH_PHRASE),
        (_cell(SCOPED, "mixed-currencies-usd-lot-ok"), MIXED_CURRENCY_NOTE),
        (_cell(SCOPED, "o1-held-split-sources"), APPLIED_HEAD),
    ],
    ids=["fx-unavailable", "no-fx-quote", "pair-mismatch", "mixed-currency", "o1-applied-note"],
)
def test_w4_t4_the_neighbour_is_the_failure_sentence_it_must_hold_beside(
    cell: Cell, phrase: str
) -> None:
    """RK4-R3: true beside each failed-conversion sentence it can follow."""
    _, notes = _build(cell)
    at = notes.index(W)
    assert phrase in notes[at - 1]


# --- W4-T6 / RK4-C3: the valuator's sentences only, never the quote's ----------------


def test_w4_t6_a_split_cell_never_shows_the_quotes_sentence() -> None:
    for quote, close in (
        (_quote(BANK, rate=None), 200.0),  # 2a
        (_other_pair_quote(BANK), 200.0),  # pair mismatch
        (_quote(BANK), None),  # O-1
    ):
        book, notes = _build(Cell(book_summary(_usd(1, source=YAHOO)), quote, None, close=close))
        assert book.fx_disclosure == f"{W} {YAHOO_NOTE}"
        assert BANK_NOTE not in notes
        assert BANK_NOTE not in (book.fx_disclosure or "")


def test_w4_t6_same_source_cell_shows_it_once_as_the_valuators() -> None:
    for quote, close in ((_quote(BANK, rate=None), 200.0), (_quote(BANK), None)):
        _, notes = _build(Cell(book_summary(_usd(1, source=BANK)), quote, None, close=close))
        assert notes.count(BANK_NOTE) == 1
        assert notes[notes.index(W) + 1] == BANK_NOTE


@pytest.mark.parametrize("valuator_ids", [("fx_other",), ("fx_other", "fx_third")])
def test_w4_t6_generic_count_is_the_valuators_distinct_ids(valuator_ids: tuple[str, ...]) -> None:
    """RK4-C3: two ids sharing ``GENERIC_SOURCE_NOTE`` -- the quote's adds none."""
    rows = [
        _usd(index, source=source_id, symbol=SYMBOL)
        for index, source_id in enumerate(valuator_ids, start=1)
    ]
    for quote, close in ((_quote("fx_one", rate=None), 200.0), (_quote("fx_one"), None)):
        _, notes = _build(Cell(book_summary(*rows), quote, None, close=close))
        assert notes.count(GENERIC_SOURCE_NOTE) == len(valuator_ids)


def test_rk4_c3_the_scoped_branch_cannot_receive_the_quote() -> None:
    """RK4-C3: the (B) assembler's signature takes no quote, so no sentence can
    appear *because of* the quote."""
    for function in (book_module._valuation_converted, book_module._valuation_disclosures):
        parameters = inspect.signature(function).parameters
        hints = typing.get_type_hints(function)
        assert not {"fx", "applied", "quote"} & set(parameters)
        assert all(FxQuote not in typing.get_args(hint) for hint in hints.values())
        assert FxQuote not in hints.values()


# --- R4-6 / W4-T4 / W4-T6: end to end, derived from the recorded answers ------------

#: 2a: the valuator's two lookups land on ``source``; the quote finds nothing.
TWO_A = [
    pytest.param(Scenario(bank=lambda call, day, today: call < 3, yahoo=_never), id="2a-bank"),
    pytest.param(Scenario(bank=_never, yahoo=lambda call, day, today: call < 3), id="2a-yahoo"),
]


@pytest.mark.parametrize("scenario", TWO_A)
def test_r4_6_scenario_2a_snapshot_push_and_card(
    tmp_path: Path,
    api_harness: ApiHarness,
    caplog: pytest.LogCaptureFixture,
    scenario: Scenario,
) -> None:
    harness = _alerts(tmp_path, scenario)
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        snap = harness.snapshot()
    ladder = harness.ladders[-1]
    valuation_source = ladder.source_on(harness.today)
    # Not vacuous: the quote really found nothing, the valuator really converted.
    assert ladder.source_on(harness.today - timedelta(days=1)) == "none"
    assert valuation_source in (BANK, YAHOO)
    expected = f"{W} {source_note(valuation_source)}"
    assert snap.fx_disclosure == expected
    # S-4's count line is untouched (R4-17).
    assert [record.getMessage() for record in _book_records(caplog)] == [
        "fx quote unavailable while valued holdings used a rate: "
        f"pair=USDTWD quote_source=none valuation_source={valuation_source} "
        f"valuation_as_of={harness.today.isoformat()}"
    ]

    result = evaluate_alerts(
        _fire(tmp_path, harness), harness.load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert message.endswith(f" {expected}")
    assert message.count(W) == 1
    assert message.count(source_note(valuation_source)) == 1
    assert APPROVED_BRIDGE not in message

    ladder, today = _serve(api_harness, scenario)
    _hold_usd(api_harness.positions)
    notes: list[str] = _card(api_harness)["context_notes"]
    card_source = ladder.source_on(today)
    assert ladder.source_on(today - timedelta(days=1)) == "none"
    at = notes.index(W)
    assert UNAVAILABLE_PHRASE in notes[at - 1]
    assert notes[at:] == [W, source_note(card_source)]
    assert notes.count(W) == 1
    assert APPROVED_BRIDGE not in notes


def _hold_twd_lot_of_the_usd_symbol(store: PositionStore) -> None:
    # ``PositionInput`` carries no market/currency rule (ADR-0017 C3).
    store.create(
        PositionInput(
            symbol=SYMBOL,
            market="US",
            quantity=Decimal(3),
            avg_cost=Decimal(4500),
            currency="TWD",
            opened_at=OPENED,
            instrument_type="stock",
            note=None,
        )
    )


def test_r4_6_mixed_currencies_with_a_valued_usd_lot_end_to_end(
    tmp_path: Path, api_harness: ApiHarness
) -> None:
    """K-1 partly superseded (risk RK4-R1): the USD lot's value was converted."""
    scenario = Scenario(bank=_always)
    harness = _alerts(tmp_path, scenario)
    _hold_twd_lot_of_the_usd_symbol(harness.store)
    snap = harness.snapshot()
    valuation_source = harness.ladders[-1].source_on(harness.today)
    expected = f"{W} {source_note(valuation_source)}"
    assert snap.fx_disclosure == expected
    result = evaluate_alerts(
        _fire(tmp_path, harness), harness.load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    )
    assert len(result.events) == 1
    assert result.events[0].message.endswith(f" {expected}")

    ladder, today = _serve(api_harness, scenario)
    _hold_usd(api_harness.positions)
    _hold_twd_lot_of_the_usd_symbol(api_harness.positions)
    notes: list[str] = _card(api_harness)["context_notes"]
    at = notes.index(W)
    assert notes[at - 1 :] == [MIXED_CURRENCY_NOTE, W, source_note(ladder.source_on(today))]
    assert source_note(ladder.source_on(today - timedelta(days=1))) not in notes[:at]


def test_r4_6_scenario_9_same_shape_stays_silent(tmp_path: Path, api_harness: ApiHarness) -> None:
    """No open date: the holding is unvalued although its fx_now was found; the
    quote then finds nothing. Nothing was converted into a shown figure."""
    scenario = Scenario(bank=lambda call, day, today: call < 2, yahoo=_never)
    harness = _alerts(tmp_path, scenario, opened_at=None)
    snap = harness.snapshot()
    ladder = harness.ladders[-1]
    assert ladder.source_on(harness.today) == BANK  # not vacuous
    assert ladder.source_on(harness.today - timedelta(days=1)) == "none"
    assert snap.fx_disclosure is None

    _serve(api_harness, scenario)
    _hold_usd(api_harness.positions, opened_at=None)
    notes = _card(api_harness)["context_notes"]
    assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE, W))


# --- W4-T8: 2c at the API response layer (S-2 tripwire) ----------------------------


def test_w4_t8_2c_insufficient_response_pairs_no_fx_quote_with_the_scope_note(
    api_harness: ApiHarness,
) -> None:
    """S-2 tripwire (risk RK4-R7, W4-T8): 回風控重審 S-2 if this pairing ever
    reaches a visible surface.

    With no usable close the card is ``insufficient_data`` and no quote is
    resolved, so ``context_notes`` carries ``NO_FX_QUOTE_NOTE`` ("本次沒有取得
    任何匯率報價") right before W-RK4-1 and the valuator's sentence, while
    ``position_market_value_twd`` was converted. Today the page renders only the
    insufficient panel for this status; if that branch starts rendering
    ``context_notes`` or ``portfolio_context``, or ``/api/advice`` gains another
    consumer, this pairing goes back to risk-compliance.
    """
    today = _today()
    ladder = Scenario(bank=_always).ladder(today)
    clock = _clock(today)
    # The valuator prices the holding; the card's own load finds no bar at all.
    valued: dict[Market, FakePriceService] = {
        "TW": api_harness.price_service,
        "US": _us_service(today),
    }
    carded: dict[Market, FakePriceService] = {
        "TW": api_harness.price_service,
        "US": FakePriceService(),
    }
    valuator = PositionValuator(market_services=valued, fx_provider=ladder, clock=clock)
    cached = PositionValuator(
        market_services=valued, fx_provider=ladder, clock=clock, price_mode="cache_only"
    )
    app.dependency_overrides[get_market_resolver] = lambda: carded
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_cached_valuator] = lambda: cached
    app.dependency_overrides[get_fx_provider] = lambda: ladder
    _hold_usd(api_harness.positions)

    body = api_harness.client.get(f"/api/advice/{SYMBOL}", params={"market": "US"}).json()
    assert body["status"] == "insufficient_data"
    assert body["portfolio_context"]["position_market_value_twd"] > 0  # converted
    notes: list[str] = body["context_notes"]
    at = notes.index(W)
    assert notes[at - 1 :] == [
        NO_FX_QUOTE_NOTE.format(currency="USD"),
        W,
        source_note(ladder.source_on(today)),
    ], "回風控重審 S-2"


# --- W4-T9 / RK4-C5: mismatched rows trigger nothing (real valuator path) -----------


def test_w4_t9_a_mismatched_row_valued_for_real_lends_no_sentence_elsewhere(
    tmp_path: Path,
) -> None:
    """RK4-R12 (R12-a) and RK4-C5 (a): an X-3 type-B row valued by the real
    valuator. Bank of Taiwan only answers a window that reaches today -- the
    valuator's fx_now, were it asked -- and Yahoo every other: if KX-A2 ever
    stopped short-circuiting the row, its Bank of Taiwan rate would surface as
    a second source on another symbol's push and turn this test red."""
    today = _today()
    store = PositionStore(db_path=tmp_path / "positions.db")
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal(100),
            avg_cost=Decimal(15),
            currency="USD",
            opened_at=OPENED,
            instrument_type="stock",
            note=None,
        )
    )
    tw = FakePriceService()
    tw.seed("2330", recent_bars(trending_closes(200, start=500.0), symbol="2330"))
    us = FakePriceService()
    us.seed(
        "MSFT",
        recent_bars(
            trending_closes(200, start=100.5),
            symbol="MSFT",
            market="US",
            end=today - timedelta(days=1),
        ),
    )
    resolver: dict[Market, FakePriceService] = {"TW": tw, "US": us}
    scenario = Scenario(bank=lambda call, day, today: day >= today, yahoo=_always)

    def snapshot(symbol: str, market: Market) -> tuple[SymbolSnapshot, _RecordingLadder]:
        ladder = scenario.ladder(today)
        snap = build_snapshot(
            symbol,
            market,
            resolver=dict(resolver),
            store=store,
            valuator=PositionValuator(
                market_services=dict(resolver), fx_provider=ladder, clock=_clock(today)
            ),
            budget=RiskBudget(),
            fx_provider=ladder,
            today=today,
        )
        return snap, ladder

    # Another symbol's push: a candidate whose quote was applied (Yahoo).
    other, ladder = snapshot("MSFT", "US")
    quote_source = ladder.source_on(today - timedelta(days=1))
    assert quote_source == YAHOO  # not vacuous
    assert other.fx_disclosure == source_note(quote_source)
    assert BANK_NOTE not in (other.fx_disclosure or "")

    # The mismatched symbol's own push: nothing converted, nothing stated.
    own, _ = snapshot("2330", "TW")
    assert own.fx_disclosure is None
    assert W not in (own.reason or "")

    # Same summary through the book layer for both symbols' cards.
    summary = build_summary(
        store,
        PositionValuator(
            market_services=dict(resolver),
            fx_provider=scenario.ladder(today),
            clock=_clock(today),
        ),
    )
    row = summary.positions[0]
    assert row.valuation.missing == [CURRENCY_MARKET_MISMATCH]
    cards: tuple[tuple[str, Market, str], ...] = (("2330", "TW", "TWD"), ("MSFT", "US", "USD"))
    for symbol, market, currency in cards:
        book = build_book_context(
            summary,
            symbol=symbol,
            market=market,
            close=600.0,
            currency=currency,
            atr=4.0,
            fx=_quote(YAHOO, rate=None),
        )
        notes = book_notes(book)
        assert book.fx_disclosure is None
        assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE, W))


# --- the 2a count line (R4-17) ------------------------------------------------------


def test_r4_17_the_2a_line_is_logged_where_it_was_and_nowhere_new(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        _build(_cell(SCOPED, "2a-unavailable-quote"))
    assert [record.getMessage() for record in _book_records(caplog)] == [
        "fx quote unavailable while valued holdings used a rate: "
        f"pair=USDTWD quote_source={YAHOO} valuation_source={BANK} valuation_as_of=2026-10-08"
    ]
    # Mixed currencies, O-1, a mismatched row and 2c never call it.
    for params, wanted in (
        (SCOPED, "2c-no-quote"),
        (SCOPED, "mixed-currencies-usd-lot-ok"),
        (SCOPED, "o1-held-split-sources"),
        (SCOPED, "o1-held-same-source"),
        (SILENT, "mismatch-type-b-hand-built-ok"),
        (SILENT, "mismatch-type-a-hand-built-ok"),
    ):
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
            _build(_cell(params, wanted))
        assert _book_records(caplog) == [], wanted


# --- W4-T10: the longest push still fits one message --------------------------------


def test_w4_t10_worst_case_scoped_push_is_at_most_2000_characters(tmp_path: Path) -> None:
    """All five caps violated with the largest figures and longest names the
    inputs allow, W-RK4-1, the longest source sentence and a degraded data layer."""
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
        atr=9_876.5432,
        sector=sector,
        sector_market_value_twd=876_543_210_987.0,
        kelly=kelly_inputs(0.61, 1.87, age_days=29),
    )
    checks = evaluate_limits(RiskBudget(), context)
    assert [check.status for check in checks] == ["violated"] * len(LIMIT_IDS)
    longest = max(METHODOLOGY, key=len)

    def load(_symbol: str, market: Market) -> SymbolSnapshot:
        return SymbolSnapshot(
            symbol=symbol,
            market="US",
            limits=checks,
            fx_disclosure=f"{W} {longest}",
            data_disclosure=(
                f"資料來自 {DataStatus.CACHED_STALE.value} 層（twse_openapi）。 "
                f"{RECENT_ATTEMPT_FAILED_REASON} "
                f"{MIXED_SOURCES_REASON.format(sources='yfinance、alpha_vantage、finmind')}"
            ),
        )

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    add_rule(alerts, limit_rule(limit_id="any", symbol=symbol, market="US"))
    result = evaluate_alerts(alerts, load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC))
    assert len(result.events) == 1
    text = format_message(result.events[0])
    assert W in text
    assert len(text) <= 2000, len(text)


# --- W4-T11 / RK4-R9: the premises the wording rests on ------------------------------


def test_w4_t11_tripwire_ladder_rungs_and_currencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """回風控重審 W-RK4-1、W-RK5-1 if this fails: RK2-T6's premises, restated
    with this wording's failure message (two rungs, one foreign currency)."""
    monkeypatch.setattr(deps, "_default_yfinance", lambda: None)
    ladder = deps._default_fx_provider.__wrapped__()
    assert isinstance(ladder, FxRateLadder), BACK_TO_RISK
    try:
        rungs = (ladder._primary.source_id, ladder._backup.source_id)
    finally:
        ladder.close()
    assert rungs == (BANK, YAHOO), BACK_TO_RISK
    assert set(typing.get_args(Currency)) == {"TWD", "USD"}, BACK_TO_RISK


def test_rk4_r9_one_fx_now_source_per_pair_within_one_summary(tmp_path: Path) -> None:
    """回風控重審 W-RK4-1、W-RK5-1 if this fails (risk RK4-R9): the valuator asks
    each ``(pair, date)`` once per pass, so every ``ok`` row of a pair carries the
    same fx_now source. Bank of Taiwan answers the first lookup only, so the
    open-date lookups after it land on Yahoo -- a pass that asked fx_now again
    per row would show it here. Also the premise ADR-0015 W11's cache wiring must
    keep (see the module docstring)."""
    today = _today()
    store = PositionStore(db_path=tmp_path / "positions.db")
    us = FakePriceService()
    for offset, symbol in enumerate(("AAPL", "MSFT", "NVDA")):
        us.seed(symbol, recent_bars(trending_closes(200, start=100.5), symbol=symbol, market="US"))
        store.create(
            PositionInput(
                symbol=symbol,
                market="US",
                quantity=QUANTITY,
                avg_cost=Decimal(150),
                currency="USD",
                opened_at=OPENED + timedelta(days=30 * offset),
                instrument_type="stock",
                note=None,
            )
        )
    ladder = Scenario(bank=lambda call, day, today: call == 1).ladder(today)
    summary = build_summary(
        store, PositionValuator(market_services={"US": us}, fx_provider=ladder, clock=_clock(today))
    )
    ok = [p for p in summary.positions if p.valuation.status == "ok" and p.valuation.fx]
    assert len(ok) == 3  # not vacuous
    by_pair: dict[str, set[str]] = {}
    for position in ok:
        assert position.valuation.fx is not None
        by_pair.setdefault(position.valuation.fx.pair, set()).add(position.valuation.fx.source)
    assert all(len(sources) == 1 for sources in by_pair.values()), BACK_TO_RISK
    # Not vacuous: the ladder really did answer differently after the first call.
    open_sources = {p.valuation.fx_open.source for p in ok if p.valuation.fx_open is not None}
    assert open_sources == {YAHOO}


# --- RK4-C4 (b): a rate never travels under the ladder's "none" ----------------------


@pytest.mark.parametrize(
    ("bank", "yahoo", "answered"),
    [
        pytest.param(_always, _always, BANK, id="primary-answers"),
        pytest.param(_never, _always, YAHOO, id="backup-answers"),
        pytest.param(_never, _never, None, id="both-fail"),
    ],
)
def test_rk4_c4_ladder_rates_never_come_from_none(
    bank: Callable[[int, date, date], bool],
    yahoo: Callable[[int, date, date], bool],
    answered: str | None,
) -> None:
    """回風控重審 W-RK4-1 if this fails (risk RK4-C4): ``source_note`` is empty
    for ``"none"`` only, so a quote with a rate and no sentence -- the test-only
    cell above -- stays test-only only while ``"none"`` never carries a rate."""
    today = _today()
    ladder = FxRateLadder(
        primary=_BankRung(lambda call, day: bank(call, day, today)),
        backup=_YahooRung(lambda call, day: yahoo(call, day, today)),
    )
    result = ladder.get_daily_rates("USDTWD", today - timedelta(days=7), today)
    if result.rates:
        assert result.source != "none", "回風控重審 W-RK4-1"
        assert source_note(result.source) != "", "回風控重審 W-RK4-1"
        assert result.source == answered
    else:
        assert answered is None
        assert result.source == "none"
