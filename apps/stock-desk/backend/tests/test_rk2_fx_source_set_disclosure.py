"""RK-2 (d): every FX source behind one context's figures is disclosed, in order.

Task RK-2
(``work/dispatch/2026-10-08-任務單-RK-2-警示與決策卡匯率來源揭露與實際換算來源不一致.md``):
the quote the book layer applies (caps 4's numerator, ``FX_APPLIED_NOTE``) and
the valuator's ``fx_now`` (caps 1, 2, 3, 5 and cap 4's denominator) are two
independent lookups through a ladder with no memory, so they can land on
different sources -- Bank of Taiwan answering one call and not the other
(4a / 4b), or a long holiday that one lookup window spans and the other does
not (5, deterministic). Before this change only the quote's methodology
sentence was shown; 4b (a Bank of Taiwan sentence on Yahoo-converted figures)
is the dangerous direction.

The disclosure is now ``[quote's note, valuator's note]`` deduplicated by
source id, the valuator's taken only from ``ok`` rows of the same pair whose
rate is not ``UNAVAILABLE`` (RK2-R1). When exactly two distinct sources remain
the risk-approved bridge sentence follows them (RK2-R2 / RK2-R2a). The test
names carry the RK2-T numbers of the risk review
``work/reviews/2026-10-08-RK-2-銜接句逐字審與X-10核對-風控審查.md``.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import typing
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

import pytest

from app.advice import book as book_module
from app.advice.book import FX_APPLIED_NOTE, FxQuote, book_notes, build_book_context
from app.advice.limits import LIMIT_IDS, PortfolioContext, RiskBudget, evaluate_limits
from app.advice.loader import BANNED_PHRASES
from app.alerts.engine import UNEVALUATED_LIMITS_NOTE, SymbolSnapshot, evaluate_alerts
from app.alerts.notify import format_message
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api import deps
from app.api.deps import get_cached_valuator, get_fx_provider, get_market_resolver, get_valuator
from app.data.interface import DataStatus, Market
from app.data.providers.fx import FxRate, FxRateLadder, FxRateProvider, FxRateResult
from app.data.service import MIXED_SOURCES_REASON, RECENT_ATTEMPT_FAILED_REASON
from app.main import app
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.portfolio.valuation import FxInfo, PositionValuator
from app.positions.models import Currency, PositionInput
from app.positions.sectors import TWSE_SECTORS
from app.positions.store import PositionStore
from app.services import fx_notes
from app.services.fx_notes import GENERIC_SOURCE_NOTE, SOURCE_NOTES, source_note
from tests.advice_helpers import book_position, book_summary, kelly_inputs, reported_net_worth
from tests.alerts_helpers import add_rule, limit_rule
from tests.api_helpers import FakePriceService, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

#: The wording risk-compliance approved verbatim (RK2-R2 with RK2-R2a, 2026-10-08).
#: Kept here as a literal on purpose: RK2-T1 compares the production constant
#: against it, so an edit to either side is a red test, not a silent drift.
APPROVED_BRIDGE = (
    "此處數字混用兩個來源的匯率，緊接在前的兩項來源說明依序對應價格與 ATR 的換算、"
    "持倉市值與總資產；「本次台灣銀行來源不可用」僅適用於部分查詢。"
)
#: The two locked methodology sentences, byte for byte (RK2-T2; fx_notes.py 2026-09-19).
LOCKED_BANK_NOTE = (
    "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；"
    "該端點與 CSV 欄位格式未經本環境線上查證（verified=false）。"
)
LOCKED_YAHOO_NOTE = (
    "匯率取自 Yahoo Finance 的每日收盤價（非台灣銀行官方牌告），"
    "為本次台灣銀行來源不可用時的備援；其口徑與台銀即期中價不同，"
    "換算結果可能與官方牌告有落差。該端點未公開文件化，"
    "幣別代號（如 TWD=X）與欄位格式均未經本環境線上查證（verified=false）。"
)

BANK = "bank_of_taiwan"
YAHOO = "yfinance_fx"
BANK_NOTE = SOURCE_NOTES[BANK]
YAHOO_NOTE = SOURCE_NOTES[YAHOO]
METHODOLOGY = (*SOURCE_NOTES.values(), GENERIC_SOURCE_NOTE)
APPLIED_HEAD = FX_APPLIED_NOTE.split("{", 1)[0]
BOOK_LOGGER = "app.advice.book"

SYMBOL = "AAPL"
OPENED = date(2024, 1, 2)
#: Distinctive figures, so a log line leaking any of them would be visible.
QUANTITY = Decimal(137)
BANK_RATE = Decimal("31.47")
YAHOO_RATE = Decimal("31.23")
US_CLOSES = trending_closes(200, start=100.5)


# --- a ladder whose rungs answer on a script -----------------------------------


class _ScriptedRung(FxRateProvider):
    """One rung of the test ladder: has a rate for ``day`` iff ``has(call, day)``.

    ``call`` counts this rung's own calls from 1, which is how "the N-th lookup
    flips the source" is expressed; ``day`` is how "this source only has
    postings before / from some date" is.
    """

    rate: ClassVar[Decimal]

    def __init__(self, has: Callable[[int, date], bool]) -> None:
        self._has = has
        self.calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls += 1
        call = self.calls
        now = datetime.now(UTC)
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        rates = [
            FxRate(pair=pair, date=day, rate=self.rate, as_of=now, source=self.source_id)
            for day in days
            if self._has(call, day)
        ]
        status = DataStatus.FRESH if rates else DataStatus.UNAVAILABLE
        return FxRateResult(rates=rates, status=status, as_of=now, source=self.source_id)


class _BankRung(_ScriptedRung):
    source_id = BANK
    rate = BANK_RATE


class _YahooRung(_ScriptedRung):
    source_id = YAHOO
    rate = YAHOO_RATE


class _RecordingLadder(FxRateLadder):
    """The production ladder, recording which source answered each window end."""

    def __init__(self, primary: FxRateProvider, backup: FxRateProvider) -> None:
        super().__init__(primary=primary, backup=backup)
        self.answers: list[tuple[date, str]] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        result = super().get_daily_rates(pair, start, end)
        self.answers.append((end, result.source))
        return result

    def source_on(self, end: date) -> str:
        """The source that actually answered the lookup ending on ``end`` (RK2-T4)."""
        sources = {source for answered, source in self.answers if answered == end}
        assert len(sources) == 1, self.answers
        return sources.pop()


Has = Callable[[int, date, date], bool]


def _always(call: int, day: date, today: date) -> bool:
    return True


def _never(call: int, day: date, today: date) -> bool:
    return False


@dataclass(frozen=True)
class Scenario:
    """How each rung answers; ``today`` is the valuator's date, the bars end a day earlier."""

    bank: Has
    yahoo: Has = _always
    #: What the scenario is built to produce -- a precondition, not the oracle:
    #: the expected sentences are derived from the recorded answers (RK2-T4).
    quote_source: str | None = None
    valuation_source: str | None = None

    def ladder(self, today: date) -> _RecordingLadder:
        bank, yahoo = self.bank, self.yahoo
        return _RecordingLadder(
            primary=_BankRung(lambda call, day: bank(call, day, today)),
            backup=_YahooRung(lambda call, day: yahoo(call, day, today)),
        )


# Lookup order within one context (one USD holding opened on ``OPENED``): the
# valuator's fx_now (window ends today), its fx_open (ends on OPENED), then the
# quote for the bars (ends on the last bar, yesterday).
MIXED = [
    pytest.param(
        Scenario(bank=lambda call, day, today: call < 3, quote_source=YAHOO, valuation_source=BANK),
        id="4a-valuation-bank-quote-yahoo",
    ),
    pytest.param(
        Scenario(
            bank=lambda call, day, today: call >= 2, quote_source=BANK, valuation_source=YAHOO
        ),
        id="4b-valuation-yahoo-quote-bank",
    ),
    pytest.param(
        # The last Bank of Taiwan posting is 8 days back: today's window is the
        # first one to fall wholly inside the gap, the bar date's still reaches it.
        Scenario(
            bank=lambda call, day, today: day <= today - timedelta(days=8),
            quote_source=BANK,
            valuation_source=YAHOO,
        ),
        id="5-today-window-wholly-after-last-bank-posting",
    ),
    pytest.param(
        # Postings resume today after a gap covering the whole bar-date window.
        Scenario(
            bank=lambda call, day, today: day >= today,
            quote_source=YAHOO,
            valuation_source=BANK,
        ),
        id="5-bank-postings-resume-today-bar-window-wholly-in-gap",
    ),
]
CONSISTENT = [
    pytest.param(Scenario(bank=_always, quote_source=BANK, valuation_source=BANK), id="both-bank"),
    pytest.param(
        Scenario(bank=_never, quote_source=YAHOO, valuation_source=YAHOO), id="both-yahoo"
    ),
]
#: 4b, used where a single mixed scenario is enough.
FOUR_B = Scenario(bank=lambda call, day, today: call >= 2)


# --- fixtures ------------------------------------------------------------------


def _today() -> date:
    return date.today()


def _clock(today: date) -> Callable[[], datetime]:
    return lambda: datetime.combine(today, time(12), tzinfo=UTC)


def _us_service(today: date) -> FakePriceService:
    service = FakePriceService()
    service.seed(
        SYMBOL, recent_bars(US_CLOSES, symbol=SYMBOL, market="US", end=today - timedelta(days=1))
    )
    return service


def _hold_usd(store: PositionStore, *, opened_at: date | None = OPENED) -> None:
    store.create(
        PositionInput(
            symbol=SYMBOL,
            market="US",
            quantity=QUANTITY,
            avg_cost=Decimal(150),
            currency="USD",
            opened_at=opened_at,
            instrument_type="stock",
            note=None,
        )
    )


def _hold_twd(store: PositionStore, symbol: str = "2330") -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market="TW",
            quantity=Decimal(100_000),
            avg_cost=Decimal(500),
            currency="TWD",
            opened_at=OPENED,
            instrument_type="stock",
            note=None,
        )
    )


@dataclass
class _Alerts:
    """The alert path of one test: fresh ladder per snapshot load, as a tick has."""

    store: PositionStore
    resolver: dict[Market, FakePriceService]
    scenario: Scenario
    today: date
    ladders: list[_RecordingLadder]

    def snapshot(self) -> SymbolSnapshot:
        ladder = self.scenario.ladder(self.today)
        self.ladders.append(ladder)
        return build_snapshot(
            SYMBOL,
            "US",
            resolver=dict(self.resolver),
            store=self.store,
            valuator=PositionValuator(
                market_services=dict(self.resolver),
                fx_provider=ladder,
                clock=_clock(self.today),
            ),
            budget=RiskBudget(),
            fx_provider=ladder,
            today=self.today,
        )

    def load(self, symbol: str, market: Market) -> SymbolSnapshot:
        return self.snapshot()


def _alerts(
    tmp_path: Path,
    scenario: Scenario,
    *,
    opened_at: date | None = OPENED,
    with_twd: bool = False,
) -> _Alerts:
    today = _today()
    store = PositionStore(db_path=tmp_path / "positions.db")
    _hold_usd(store, opened_at=opened_at)
    resolver: dict[Market, FakePriceService] = {"US": _us_service(today)}
    if with_twd:
        _hold_twd(store)
        tw = FakePriceService()
        tw.seed("2330", recent_bars(trending_closes(200, start=500.0), symbol="2330"))
        resolver["TW"] = tw
    return _Alerts(store=store, resolver=resolver, scenario=scenario, today=today, ladders=[])


def _fire(tmp_path: Path, harness: _Alerts, *rules: dict[str, object]) -> AlertStore:
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    for rule in rules or (limit_rule(limit_id="any", symbol=SYMBOL, market="US"),):
        add_rule(alerts, rule)
    return alerts


def _serve(api_harness: ApiHarness, scenario: Scenario) -> tuple[_RecordingLadder, date]:
    """Route the card, the overview and ``/limits`` through one scripted ladder."""
    today = _today()
    ladder = scenario.ladder(today)
    services: dict[Market, FakePriceService] = {
        "TW": api_harness.price_service,
        "US": _us_service(today),
    }
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


def _card(api_harness: ApiHarness) -> dict[str, typing.Any]:
    body: dict[str, typing.Any] = api_harness.client.get(
        f"/api/advice/{SYMBOL}", params={"market": "US"}
    ).json()
    assert body["status"] == "ok"  # not vacuous: a card was produced
    return body


def _expected_pair(ladder: _RecordingLadder, today: date) -> tuple[str, str, str, str]:
    """``(quote source, valuation source, quote note, valuation note)`` as they happened."""
    quote_source = ladder.source_on(today - timedelta(days=1))
    valuation_source = ladder.source_on(today)
    return (
        quote_source,
        valuation_source,
        source_note(quote_source),
        source_note(valuation_source),
    )


def _applied_index(notes: list[str]) -> int:
    indices = [index for index, note in enumerate(notes) if note.startswith(APPLIED_HEAD)]
    assert len(indices) == 1, notes
    return indices[0]


def _book_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == BOOK_LOGGER]


# --- RK2-T1 / T2: the wording itself -------------------------------------------


def test_rk2_t1_the_bridge_constant_is_the_approved_wording() -> None:
    bridge = book_module.FX_MIXED_SOURCES_NOTE
    assert bridge == APPROVED_BRIDGE
    assert len(bridge) == 72
    source = inspect.getsource(book_module)
    marker = source.index("FX_MIXED_SOURCES_NOTE = (")
    header = source[source.rindex("\n\n", 0, marker) : marker]
    assert "風控核可文案,修改須重新送審(2026-10-08)" in header
    assert "work/reviews/2026-10-08-RK-2-銜接句逐字審與X-10核對-風控審查.md" in header
    # It lives in the book layer, never next to the locked sentences.
    assert APPROVED_BRIDGE not in inspect.getsource(fx_notes)
    assert not hasattr(fx_notes, "FX_MIXED_SOURCES_NOTE")


def test_rk2_t2_the_quoted_phrase_is_part_of_the_locked_yahoo_sentence() -> None:
    quoted = re.findall("「(.+?)」", APPROVED_BRIDGE)
    assert quoted == ["本次台灣銀行來源不可用"]
    assert quoted[0] in SOURCE_NOTES[YAHOO]
    assert SOURCE_NOTES[BANK] == LOCKED_BANK_NOTE
    assert SOURCE_NOTES[YAHOO] == LOCKED_YAHOO_NOTE


# --- RK2-T3 / T4 / T10: the mixed groups, end to end ------------------------------


@pytest.mark.parametrize("scenario", MIXED)
def test_rk2_t3_t4_t10_alert_snapshot_and_fired_message(tmp_path: Path, scenario: Scenario) -> None:
    harness = _alerts(tmp_path, scenario)
    snap = harness.snapshot()
    ladder = harness.ladders[-1]
    quote_source, valuation_source, quote_note, valuation_note = _expected_pair(
        ladder, harness.today
    )
    # Not vacuous: the scenario produced the split it was built for.
    assert (quote_source, valuation_source) == (scenario.quote_source, scenario.valuation_source)

    joined = f"{quote_note} {valuation_note} {APPROVED_BRIDGE}"
    assert snap.fx_disclosure == joined
    # RK2-T4: the converted-with sentence on the snapshot names the quote's source.
    assert f"來源 {quote_source}" in (snap.reason or "")

    result = evaluate_alerts(
        _fire(tmp_path, harness), harness.load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert message.endswith(f" {joined}")
    for sentence in (quote_note, valuation_note, APPROVED_BRIDGE):
        assert message.count(sentence) == 1  # RK2-T10


@pytest.mark.parametrize("scenario", MIXED)
def test_rk2_t3_t4_t10_advice_card_context_notes(
    api_harness: ApiHarness, scenario: Scenario
) -> None:
    ladder, today = _serve(api_harness, scenario)
    _hold_usd(api_harness.positions)

    notes: list[str] = _card(api_harness)["context_notes"]
    quote_source, valuation_source, quote_note, valuation_note = _expected_pair(ladder, today)
    assert (quote_source, valuation_source) == (scenario.quote_source, scenario.valuation_source)

    at = _applied_index(notes)
    # RK2-T4: the converted-with sentence and the first source sentence agree.
    assert f"來源 {quote_source}" in notes[at]
    assert notes[at + 1 : at + 4] == [quote_note, valuation_note, APPROVED_BRIDGE]
    for sentence in (quote_note, valuation_note, APPROVED_BRIDGE):
        assert notes.count(sentence) == 1  # RK2-T10


# --- RK2-T5: when the bridge is attached (book unit) ------------------------------


def _usd(
    position_id: int,
    *,
    source: str,
    note: str | None = None,
    priced: bool = True,
    data_status: DataStatus = DataStatus.FRESH,
    pair: str = "USDTWD",
    symbol: str = SYMBOL,
    as_of: str | None = "2026-10-08",
) -> SummaryPosition:
    """A USD row whose valuator rate came from ``source``."""
    row = book_position(
        position_id,
        symbol,
        market="US",
        currency="USD",
        quantity="10",
        avg_cost="150",
        price="200" if priced else None,
        fx_to_twd="31.5",
    )
    fx = FxInfo(
        pair=pair,
        as_of=as_of if data_status is not DataStatus.UNAVAILABLE else None,
        source=source,
        data_status=data_status,
        source_note=source_note(source) if note is None else note,
    )
    return row.model_copy(update={"valuation": row.valuation.model_copy(update={"fx": fx})})


def _quote(source: str, *, note: str | None = None, rate: float | None = 31.5) -> FxQuote:
    return FxQuote(
        pair="USDTWD",
        rate=rate,
        as_of="2026-10-07" if rate is not None else None,
        source=source,
        status=DataStatus.FRESH if rate is not None else DataStatus.UNAVAILABLE,
        source_note=source_note(source) if note is None else note,
    )


def _book(
    summary: PortfolioSummary,
    quote: FxQuote | None,
    *,
    symbol: str = SYMBOL,
    market: Market = "US",
    currency: str = "USD",
    close: float = 200.0,
) -> tuple[str | None, list[str]]:
    book = build_book_context(
        summary,
        symbol=symbol,
        market=market,
        close=close,
        currency=currency,
        atr=4.0,
        fx=quote,
    )
    return book.fx_disclosure, book_notes(book)


def _fx_tail(notes: list[str]) -> list[str]:
    """The applied-rate sentence and everything the disclosure appended after it."""
    at = _applied_index(notes)
    tail = [notes[at]]
    for note in notes[at + 1 :]:
        if note in METHODOLOGY or note == APPROVED_BRIDGE:
            tail.append(note)
        else:
            break
    return tail


def test_rk2_t5_two_distinct_sources_attach_the_bridge() -> None:
    disclosure, notes = _book(book_summary(_usd(1, source=YAHOO)), _quote(BANK))
    assert disclosure == f"{BANK_NOTE} {YAHOO_NOTE} {APPROVED_BRIDGE}"
    assert _fx_tail(notes)[1:] == [BANK_NOTE, YAHOO_NOTE, APPROVED_BRIDGE]


def test_rk2_t5_distinct_ids_sharing_one_sentence_are_still_two_items() -> None:
    """S-1: two unknown sources share ``GENERIC_SOURCE_NOTE``; deduplicating by the
    sentence would hide the mix, so the source id decides and both items stay."""
    disclosure, notes = _book(book_summary(_usd(1, source="fx_other")), _quote("fx_one"))
    assert disclosure == f"{GENERIC_SOURCE_NOTE} {GENERIC_SOURCE_NOTE} {APPROVED_BRIDGE}"
    assert _fx_tail(notes)[1:] == [GENERIC_SOURCE_NOTE, GENERIC_SOURCE_NOTE, APPROVED_BRIDGE]


def test_rk2_t5_one_source_id_is_one_item_whatever_its_sentences() -> None:
    disclosure, notes = _book(
        book_summary(_usd(1, source=BANK), _usd(2, source=BANK, symbol="MSFT")), _quote(BANK)
    )
    assert disclosure == BANK_NOTE
    assert _fx_tail(notes)[1:] == [BANK_NOTE]
    # The same id carrying a different sentence is still the same source.
    disclosure, _ = _book(book_summary(_usd(1, source=BANK, note="另一句。")), _quote(BANK))
    assert disclosure == BANK_NOTE


def test_rk2_t5_no_bridge_unless_exactly_two_items_remain() -> None:
    # A quote without a sentence of its own leaves one item: no "兩項" to point at.
    disclosure, notes = _book(book_summary(_usd(1, source=YAHOO)), _quote(BANK, note=""))
    assert disclosure == YAHOO_NOTE
    assert APPROVED_BRIDGE not in notes
    # Three distinct sources: the sentence says "兩個來源", so it is not attached.
    disclosure, notes = _book(
        book_summary(_usd(1, source=YAHOO), _usd(2, source="fx_other", symbol="MSFT")),
        _quote(BANK),
    )
    assert disclosure == f"{BANK_NOTE} {YAHOO_NOTE} {GENERIC_SOURCE_NOTE}"
    assert APPROVED_BRIDGE not in notes


# --- RK2-T7: where neither a second sentence nor the bridge may appear ------------


def test_rk2_t7_scenario_9_unvalued_rows_contribute_no_sentence() -> None:
    """RK2-R1: a valuator rate on rows that are not ``ok`` was multiplied into nothing."""
    summary = book_summary(_usd(1, source=BANK, priced=False))
    assert summary.positions[0].valuation.status == "insufficient_data"
    disclosure, notes = _book(summary, _quote(YAHOO))
    assert disclosure == YAHOO_NOTE
    assert BANK_NOTE not in notes
    assert APPROVED_BRIDGE not in notes


def test_rk2_t7_scenario_2b_and_foreign_pairs_contribute_no_sentence() -> None:
    unavailable = _usd(1, source="none", note="", data_status=DataStatus.UNAVAILABLE)
    other_pair = _usd(2, source=BANK, pair="JPYTWD", symbol="MSFT")
    disclosure, notes = _book(book_summary(unavailable, other_pair), _quote(YAHOO))
    assert disclosure == YAHOO_NOTE
    assert APPROVED_BRIDGE not in notes
    # An UNAVAILABLE rate is excluded on its own, not only through the row's
    # status: here a hand-built ``ok`` row carries one with a sentence.
    stale = _usd(3, source="fx_other", data_status=DataStatus.UNAVAILABLE, symbol="NVDA")
    assert stale.valuation.status == "ok"
    disclosure, notes = _book(book_summary(stale), _quote(YAHOO))
    assert disclosure == YAHOO_NOTE
    assert GENERIC_SOURCE_NOTE not in notes


def test_rk2_t7_unapplied_branches_stay_silent_whatever_the_book_used() -> None:
    """R2-3: TWD, K-1 and 2a keep ``None`` even beside a valued foreign row."""
    mixed_book = [_usd(1, source=BANK), _usd(2, source=YAHOO, symbol="MSFT")]
    twd = book_position(3, "2330")
    # A TWD symbol, in a book whose USD rows were converted (O-3: not this PR).
    disclosure, notes = _book(
        book_summary(*mixed_book, twd),
        _quote(YAHOO),
        symbol="2330",
        market="TW",
        currency="TWD",
        close=600.0,
    )
    assert disclosure is None
    assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE))
    # K-1: the symbol's lots span two currencies.
    twd_lot = book_position(4, SYMBOL, market="US", currency="TWD", price="6000")
    disclosure, notes = _book(book_summary(_usd(1, source=BANK), twd_lot), _quote(YAHOO))
    assert disclosure is None
    assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE))
    # 2a: the quote had no rate; the valuator's sentence is not added in its place.
    disclosure, notes = _book(book_summary(_usd(1, source=BANK)), _quote(YAHOO, rate=None))
    assert disclosure is None
    assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE))


def test_rk2_t7_a_candidate_with_no_same_currency_holding_has_one_item() -> None:
    disclosure, notes = _book(book_summary(book_position(1, "2330")), _quote(BANK))
    assert disclosure == BANK_NOTE
    assert APPROVED_BRIDGE not in notes


def test_rk2_a_candidate_beside_a_usd_holding_discloses_the_denominator_source() -> None:
    """R2-4's set is the book's: a candidate's caps divide by the whole book's
    equity, so another USD row's source is multiplied into its figures too."""
    disclosure, _ = _book(book_summary(_usd(1, source=YAHOO, symbol="MSFT")), _quote(BANK))
    assert disclosure == f"{BANK_NOTE} {YAHOO_NOTE} {APPROVED_BRIDGE}"


@pytest.mark.parametrize(
    "valuation_source",
    [
        pytest.param(YAHOO, id="split-sources"),
        # RK4-R11-T: the same cell with one source on both sides.
        pytest.param(BANK, id="same-source"),
    ],
)
def test_rk2_o1_cell_an_unusable_close_carries_no_source_sentence(
    caplog: pytest.LogCaptureFixture, valuation_source: str
) -> None:
    """O-1 cell (risk RK4-R11 (b)): an unusable close carries no source sentence.

    The close is unusable, so the price and ATR are withheld and the applied
    quote converts nothing. With split sources the quote's sentence plus the
    bridge would claim a "混用" and a "價格與 ATR 的換算" that did not happen,
    so neither the quote's sentence, the valuator's nor the bridge is attached
    -- in either the snapshot field or the card notes. The same holds when both
    lookups landed on one source (risk RK4-R11-T). The applied-rate
    sentence itself (``fx_note``, risk S-3) is out of this PR's scope and stays.
    The (B) branch and W-RK4-1 are left to PR-RK4a.
    """
    summary = book_summary(_usd(1, source=valuation_source))
    # ``None`` is what production hands over: the snapshot screens the close
    # through ``usable_price`` first (risk RK2-L1).
    closes: tuple[float | None, ...] = (None, 0.0, -1.0, float("nan"))
    for close in closes:
        with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
            book = build_book_context(
                summary,
                symbol=SYMBOL,
                market="US",
                close=close,
                currency="USD",
                atr=4.0,
                fx=_quote(BANK),
            )
        assert book.context.close is None
        assert book.context.atr is None
        assert book.fx_disclosure is None
        notes = book_notes(book)
        assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE))
        assert book.fx_note is not None and book.fx_note in notes  # S-3: unchanged
    # Nothing was mixed into any figure, so no mixed-source line either.
    assert _book_records(caplog) == []


def test_rk2_t7_scenario_9_end_to_end(tmp_path: Path, api_harness: ApiHarness) -> None:
    """No open date: the holding is unvalued although its fx_now was looked up
    (on Bank of Taiwan, first call); the quote then lands on Yahoo."""
    scenario = Scenario(bank=lambda call, day, today: call < 2)
    harness = _alerts(tmp_path, scenario, opened_at=None)
    snap = harness.snapshot()
    ladder = harness.ladders[-1]
    assert ladder.source_on(harness.today) == BANK  # not vacuous
    assert ladder.source_on(harness.today - timedelta(days=1)) == YAHOO
    assert snap.fx_disclosure == YAHOO_NOTE

    _serve(api_harness, scenario)
    _hold_usd(api_harness.positions, opened_at=None)
    notes = _card(api_harness)["context_notes"]
    assert _fx_tail(notes)[1:] == [YAHOO_NOTE]
    assert APPROVED_BRIDGE not in notes


def test_rk2_t7_scenario_2b_end_to_end(tmp_path: Path, api_harness: ApiHarness) -> None:
    """Both rungs fail the valuator's fx_now; Yahoo answers the quote."""
    scenario = Scenario(bank=_never, yahoo=lambda call, day, today: call != 1)
    harness = _alerts(tmp_path, scenario)
    snap = harness.snapshot()
    assert harness.ladders[-1].source_on(harness.today) == "none"  # not vacuous
    assert snap.fx_disclosure == YAHOO_NOTE

    _serve(api_harness, scenario)
    _hold_usd(api_harness.positions)
    notes = _card(api_harness)["context_notes"]
    assert _fx_tail(notes)[1:] == [YAHOO_NOTE]
    assert APPROVED_BRIDGE not in notes


def test_rk2_t7_scenario_2a_end_to_end(
    tmp_path: Path, api_harness: ApiHarness, caplog: pytest.LogCaptureFixture
) -> None:
    """The valuator converted on Bank of Taiwan; the quote found nothing at all.
    No sentence is added in the quote's place (R2-3; RK-4 decides that), but
    the occurrence is logged once (S-4)."""
    scenario = Scenario(bank=lambda call, day, today: call < 3, yahoo=_never)
    harness = _alerts(tmp_path, scenario)
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        snap = harness.snapshot()
    assert harness.ladders[-1].source_on(harness.today) == BANK  # not vacuous
    assert snap.fx_disclosure is None
    records = _book_records(caplog)
    assert [record.getMessage() for record in records] == [
        "fx quote unavailable while valued holdings used a rate: "
        f"pair=USDTWD quote_source=none valuation_source={BANK} "
        f"valuation_as_of={harness.today.isoformat()}"
    ]

    _serve(api_harness, scenario)
    _hold_usd(api_harness.positions)
    notes = _card(api_harness)["context_notes"]
    assert not any(sentence in notes for sentence in (*METHODOLOGY, APPROVED_BRIDGE))


def test_rk2_t7_the_two_non_violation_messages_carry_no_disclosure(tmp_path: Path) -> None:
    """``缺少輸入`` (every watched cap unevaluable) and ``部分未評估`` (quiet with
    a reason) never carried the FX disclosure; a mixed snapshot must not change that."""
    harness = _alerts(tmp_path, FOUR_B, with_twd=True)
    snap = harness.snapshot()
    assert snap.fx_disclosure is not None and APPROVED_BRIDGE in snap.fx_disclosure

    alerts = _fire(
        tmp_path,
        harness,
        limit_rule(limit_id="gross_exposure", symbol=SYMBOL, market="US"),
        limit_rule(limit_id="any", symbol=SYMBOL, market="US"),
    )
    result = evaluate_alerts(alerts, harness.load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC))
    statuses = sorted(outcome.status for outcome in result.outcomes)
    assert statuses == ["quiet", "skipped"]
    assert result.events == []
    reasons = [outcome.reason or "" for outcome in result.outcomes]
    assert any("缺少輸入" in reason for reason in reasons)
    assert any(reason.startswith(UNEVALUATED_LIMITS_NOTE.split("{", 1)[0]) for reason in reasons)
    for reason in reasons:
        assert not any(sentence in reason for sentence in (*METHODOLOGY, APPROVED_BRIDGE))


def test_rk2_t7_limits_and_overview_never_carry_the_bridge(api_harness: ApiHarness) -> None:
    """S-3: ``/limits`` keeps only ``.context`` (no sentence at all), and the
    overview's ``fx_disclosures`` is the summary's own list, not the book's."""
    _serve(api_harness, FOUR_B)
    _hold_usd(api_harness.positions)

    limits = api_harness.client.get("/api/portfolio/limits")
    assert limits.status_code == 200
    assert APPROVED_BRIDGE not in limits.text
    assert not any(sentence in limits.text for sentence in METHODOLOGY)

    summary = api_harness.client.get("/api/portfolio/summary")
    assert summary.status_code == 200
    disclosures = summary.json()["fx_disclosures"]
    assert disclosures  # not vacuous: the overview does disclose its rate
    assert APPROVED_BRIDGE not in disclosures
    assert APPROVED_BRIDGE not in summary.text


# --- RK2-T11: a consistent book is byte-for-byte what it was ----------------------


@pytest.mark.parametrize("scenario", CONSISTENT)
def test_rk2_t11_consistent_books_are_unchanged(
    tmp_path: Path, api_harness: ApiHarness, scenario: Scenario
) -> None:
    harness = _alerts(tmp_path, scenario)
    snap = harness.snapshot()
    note = SOURCE_NOTES[typing.cast(str, scenario.quote_source)]
    assert snap.fx_disclosure == note
    result = evaluate_alerts(
        _fire(tmp_path, harness), harness.load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    )
    assert len(result.events) == 1
    message = result.events[0].message
    assert message.endswith(f" {note}")
    assert message.count(note) == 1
    assert APPROVED_BRIDGE not in message

    ladder, today = _serve(api_harness, scenario)
    _hold_usd(api_harness.positions)
    notes = _card(api_harness)["context_notes"]
    assert ladder.source_on(today) == ladder.source_on(today - timedelta(days=1))
    at = _applied_index(notes)
    assert notes[at + 1] == note
    assert notes[at + 2 :] == [n for n in notes[at + 2 :] if n not in METHODOLOGY]
    assert APPROVED_BRIDGE not in notes
    assert notes.count(note) == 1


# --- RK2-R4: the mixed-source log line ---------------------------------------------


def test_rk2_r4_a_split_logs_pair_and_source_ids_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness = _alerts(tmp_path, FOUR_B)
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        harness.snapshot()
    ladder = harness.ladders[-1]
    quote_day = harness.today - timedelta(days=1)
    assert (ladder.source_on(quote_day), ladder.source_on(harness.today)) == (BANK, YAHOO)
    records = _book_records(caplog)
    assert [record.levelno for record in records] == [logging.WARNING]
    message = records[0].getMessage()
    assert message == (
        "fx sources differ within one context: pair=USDTWD "
        f"quote_source={BANK} quote_as_of={quote_day.isoformat()} "
        f"valuation_source={YAHOO} valuation_as_of={harness.today.isoformat()}"
    )
    for leaked in (SYMBOL, str(QUANTITY), str(BANK_RATE), str(YAHOO_RATE)):
        assert leaked not in message


@pytest.mark.parametrize("scenario", CONSISTENT)
def test_rk2_r4_a_consistent_book_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scenario: Scenario
) -> None:
    harness = _alerts(tmp_path, scenario)
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        harness.snapshot()
    assert _book_records(caplog) == []


# --- RK2-T6: the premises the bridge's wording rests on ----------------------------


def test_rk2_t6_tripwire_ladder_rungs_and_currencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """回風控重審 RK-2 銜接句 if this fails: the sentence names Bank of Taiwan as
    the one source that can be "unavailable" and assumes one foreign currency."""
    # Built unwrapped, with the shared yfinance adapter stubbed: no client is
    # shared with the process-wide singletons and nothing reaches the network.
    monkeypatch.setattr(deps, "_default_yfinance", lambda: None)
    ladder = deps._default_fx_provider.__wrapped__()
    assert isinstance(ladder, FxRateLadder), "回風控重審 RK-2 銜接句"
    try:
        rungs = (ladder._primary.source_id, ladder._backup.source_id)
    finally:
        ladder.close()
    assert rungs == (BANK, YAHOO), "回風控重審 RK-2 銜接句"
    assert set(typing.get_args(Currency)) == {"TWD", "USD"}, "回風控重審 RK-2 銜接句"


# --- RK2-T8: wording scans -------------------------------------------------------


def _shared_forbidden_terms() -> tuple[str, ...]:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "shared" / "forbidden-terms.json").read_text(encoding="utf-8"))
    return tuple(payload["guarantee"]) + tuple(payload["price_target"])


#: RK2-T8's own list on top of the three shared ones.
RK2_FORBIDDEN = (
    "官方",
    "較準",
    "可靠",
    "落差",
    "暫時",
    "已自動",
    "系統會",
    "修正",
    "恢復",
    "估值器",
    "snapshot",
    "梯子",
    BANK,
    YAHOO,
    "{",
    "}",
)


def test_rk2_t8_the_bridge_passes_every_wording_scan() -> None:
    terms = set(FRONTEND_FORBIDDEN_TERMS) | set(_shared_forbidden_terms()) | set(BANNED_PHRASES)
    assert terms  # not vacuous
    assert [term for term in sorted(terms) if term in APPROVED_BRIDGE] == []
    assert find_bare_realtime_claims(APPROVED_BRIDGE) == []
    assert [term for term in RK2_FORBIDDEN if term in APPROVED_BRIDGE] == []
    assert re.search(r"[0-9０-９]", APPROVED_BRIDGE) is None


# --- RK2-T9: the longest push still fits one message --------------------------------


def test_rk2_t9_worst_case_push_is_at_most_2000_characters(tmp_path: Path) -> None:
    """All five caps violated, with the largest figures and longest names the
    inputs allow, both locked sentences, the bridge and a degraded data layer."""
    symbol = "ABCDEFGHIJKL"  # longer than any listed ticker
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

    def load(_symbol: str, market: Market) -> SymbolSnapshot:
        return SymbolSnapshot(
            symbol=symbol,
            market="US",
            limits=checks,
            fx_disclosure=f"{BANK_NOTE} {YAHOO_NOTE} {APPROVED_BRIDGE}",
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
    assert APPROVED_BRIDGE in text
    assert len(text) <= 2000, len(text)
