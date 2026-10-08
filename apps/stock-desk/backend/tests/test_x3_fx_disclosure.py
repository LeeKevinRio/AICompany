"""KX-10 (risk X3-R1): an FX source's methodology only where its rate was applied.

Task X-3 (``work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md``,
KX-10 section, design S4): the standing disclosure of an FX source
(``SOURCE_NOTES`` / ``GENERIC_SOURCE_NOTE``) may appear in a card's
``context_notes`` and a snapshot's ``fx_disclosure`` if and only if
``_resolve_fx`` took its applying branch with that very quote.

The fixture behind T10-1..T10-3 is an X-3 type-A row: a US holding stored as
TWD, carded off its USD daily series. The caller resolves a USDTWD quote for
the bars, the book layer treats the holding as TWD and applies 1.0, and before
KX-10 the card still carried the quote's methodology sentence -- a disclosure
for a conversion that never happened. These tests assert **only** that no such
sentence appears: not the valuation status, the ratios, the close or
``fx_to_twd`` (as KX-P1 did for PR-0), so X-3c can land without rewriting them
(X3-R8 forbids asserting the X-3 behaviour itself).

T10-4 keeps the consistent books byte-for-byte where they were; XS-2 (risk
review second part, suggested) pins the engine's guards for observation O-1.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.advice.book import FX_APPLIED_NOTE, FxQuote, book_notes, build_book_context
from app.advice.limits import RiskBudget
from app.alerts.engine import EvaluationResult, SymbolSnapshot, evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.data.interface import DataStatus, Market
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import FxInfo, PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from app.services.fx import resolve_fx_quote
from app.services.fx_notes import GENERIC_SOURCE_NOTE, SOURCE_NOTES
from tests.alerts_helpers import add_rule, limit_rule, price_rule, signal_rule
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    recent_bars,
    serve_us_market,
    trending_closes,
)
from tests.conftest import ApiHarness
from tests.test_advice_book import _fx, _position, _summary

#: Every methodology sentence a source can contribute.
METHODOLOGY = (*SOURCE_NOTES.values(), GENERIC_SOURCE_NOTE)
#: The fixed head of the applied-rate sentence, before its first placeholder.
APPLIED_HEAD = FX_APPLIED_NOTE.split("{", 1)[0]

SYMBOL = "AAPL"
#: 100.5 + 0.5 x 199: the latest close of the US series is 200.
US_CLOSES = trending_closes(200, start=100.5)


class _CountingFx(FxRateProvider):
    """Base for the providers below: counts lookups so a test can show the
    quote really was resolved (and then not applied)."""

    source_id = "bank_of_taiwan"

    def __init__(self) -> None:
        self.calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls += 1
        return self._answer(pair, end)

    def _answer(self, pair: str, end: date) -> FxRateResult:
        raise NotImplementedError


class AppliedFx(_CountingFx):
    """USDTWD 31.5 from Bank of Taiwan, dated on the window's end."""

    def _answer(self, pair: str, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=Decimal("31.5"), as_of=now, source="bot")],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


class NamedUnavailableFx(_CountingFx):
    """A named source that had nothing: ``rate=None`` with a non-empty note."""

    def _answer(self, pair: str, end: date) -> FxRateResult:
        return FxRateResult(
            rates=[], status=DataStatus.UNAVAILABLE, as_of=datetime.now(UTC), source=self.source_id
        )


class GenericUnavailableFx(_CountingFx):
    """The harness's unavailable provider, counted: a source with no entry in
    ``SOURCE_NOTES``, so its quote carries ``GENERIC_SOURCE_NOTE``."""

    source_id = UnavailableFxProvider.source_id

    def _answer(self, pair: str, end: date) -> FxRateResult:
        return UnavailableFxProvider().get_daily_rates(pair, end, end)


PROVIDERS = [
    pytest.param(AppliedFx, id="usdtwd-applied"),
    pytest.param(NamedUnavailableFx, id="named-source-unavailable"),
    pytest.param(GenericUnavailableFx, id="generic-source-unavailable"),
]


def _assert_no_methodology(texts: list[str]) -> None:
    for text in texts:
        for sentence in METHODOLOGY:
            assert sentence not in text


def _us_service(*symbols: str) -> FakePriceService:
    service = FakePriceService()
    for symbol in symbols:
        service.seed(symbol, recent_bars(US_CLOSES, symbol=symbol, market="US"))
    return service


def _hold(store: PositionStore, symbol: str, currency: str) -> None:
    # ``PositionInput`` carries no market/currency rule (ADR-0017 C3): the only
    # way to build the legacy row the write doors now refuse.
    store.create(
        PositionInput(
            symbol=symbol,
            market="US",
            quantity=Decimal(100),
            avg_cost=Decimal(150),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )


def _precondition_quote_has_a_note(provider: FxRateProvider) -> None:
    """Not vacuous: the quote the caller resolves does carry a sentence to leak."""
    quote = resolve_fx_quote(provider, currency="USD", on=date.today())
    assert quote is not None
    assert quote.source_note != ""


# --- T10-1: book unit ------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        pytest.param(_fx(), id="applied-test-note"),
        pytest.param(
            _fx(None, status=DataStatus.UNAVAILABLE, as_of=None), id="unavailable-test-note"
        ),
        pytest.param(
            _fx(
                None,
                status=DataStatus.UNAVAILABLE,
                as_of=None,
                source="yfinance_fx",
                source_note=SOURCE_NOTES["yfinance_fx"],
            ),
            id="unavailable-yfinance",
        ),
        pytest.param(
            _fx(
                None,
                status=DataStatus.UNAVAILABLE,
                as_of=None,
                source="fake_fx_unavailable",
                source_note=GENERIC_SOURCE_NOTE,
            ),
            id="unavailable-generic",
        ),
    ],
)
def test_t10_1_a_twd_stored_us_holding_carries_no_methodology(quote: FxQuote) -> None:
    assert quote.source_note != ""  # not vacuous
    summary = _summary(_position(1, SYMBOL, market="US", currency="TWD", price="200"))
    book = build_book_context(
        summary,
        symbol=SYMBOL,
        market="US",
        close=200.0,
        currency="USD",
        atr=4.0,
        fx=quote,
    )
    notes = book_notes(book)
    assert quote.source_note not in notes
    _assert_no_methodology(notes)
    assert not any(note.startswith(APPLIED_HEAD) for note in notes)
    assert book.fx_disclosure is None


# --- T10-2: the advice card ------------------------------------------------


@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_t10_2_the_card_of_a_twd_stored_us_holding_carries_no_methodology(
    api_harness: ApiHarness, provider_class: type[_CountingFx]
) -> None:
    provider = provider_class()
    _precondition_quote_has_a_note(provider)
    provider.calls = 0
    serve_us_market(
        tw_service=api_harness.price_service,
        us_service=_us_service(SYMBOL),
        fx_provider=provider,
    )
    _hold(api_harness.positions, SYMBOL, "TWD")

    body = api_harness.client.get(f"/api/advice/{SYMBOL}", params={"market": "US"}).json()
    # Not vacuous: a card was produced off the USD series, and its rate was asked for.
    assert body["status"] == "ok"
    assert provider.calls > 0
    _assert_no_methodology(body["context_notes"])


# --- T10-3: the alert snapshot and what the engine makes of it --------------


def _snapshot(
    store: PositionStore, service: FakePriceService, provider: FxRateProvider
) -> SymbolSnapshot:
    return build_snapshot(
        SYMBOL,
        "US",
        resolver={"US": service},
        store=store,
        valuator=PositionValuator(market_services={"US": service}, fx_provider=provider),
        budget=RiskBudget(),
        fx_provider=provider,
    )


def _evaluate(
    store: PositionStore,
    service: FakePriceService,
    provider: FxRateProvider,
    alerts: AlertStore,
) -> EvaluationResult:
    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return _snapshot(store, service, provider)

    return evaluate_alerts(alerts, load, now=datetime(2026, 10, 8, 6, 0, tzinfo=UTC))


@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_t10_3_an_alert_on_a_twd_stored_us_holding_carries_no_methodology(
    tmp_path: Path, provider_class: type[_CountingFx]
) -> None:
    provider = provider_class()
    _precondition_quote_has_a_note(provider)
    store = PositionStore(db_path=tmp_path / "positions.db")
    _hold(store, SYMBOL, "TWD")
    service = _us_service(SYMBOL)

    snap = _snapshot(store, service, provider)
    assert snap.fx_disclosure is None

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    add_rule(alerts, limit_rule(limit_id="any", symbol=SYMBOL, market="US"))
    result = _evaluate(store, service, provider, alerts)
    # Neither fired nor skipped is asserted: X-3c turns this from one to the other.
    assert result.outcomes  # not vacuous
    texts = [outcome.reason or "" for outcome in result.outcomes]
    texts += [event.message for event in result.events]
    _assert_no_methodology(texts)
    # XS-2 on this fixture: no applied-rate sentence reaches any outcome either.
    assert not any(APPLIED_HEAD in text for text in texts)


# --- T10-4: consistent books are unchanged -----------------------------------


def test_t10_4_a_usd_holding_still_discloses_the_rate_it_was_converted_with(
    api_harness: ApiHarness,
) -> None:
    provider = AppliedFx()
    service = _us_service(SYMBOL)
    serve_us_market(tw_service=api_harness.price_service, us_service=service, fx_provider=provider)
    _hold(api_harness.positions, SYMBOL, "USD")

    notes = api_harness.client.get(f"/api/advice/{SYMBOL}", params={"market": "US"}).json()[
        "context_notes"
    ]
    applied = FX_APPLIED_NOTE.format(
        pair="USDTWD",
        rate="31.5",
        status="fresh",
        source="bank_of_taiwan",
        as_of=date.today().isoformat(),
    )
    disclosure = SOURCE_NOTES["bank_of_taiwan"]
    assert notes.count(applied) == 1
    assert notes.count(disclosure) == 1
    assert notes[notes.index(applied) + 1] == disclosure

    snap = _snapshot(api_harness.positions, service, provider)
    assert snap.fx_disclosure == disclosure


def test_t10_4_a_symbol_held_in_two_currencies_discloses_no_rate() -> None:
    summary = _summary(
        _position(1, SYMBOL, market="US", currency="USD", price="200"),
        _position(2, SYMBOL, market="US", currency="TWD", price="6000"),
    )
    book = build_book_context(
        summary, symbol=SYMBOL, market="US", close=200.0, currency="USD", atr=4.0, fx=_fx()
    )
    assert book.fx_disclosure is None
    _assert_no_methodology(book_notes(book))


def test_t10_4_the_applied_branch_hands_back_the_quote_it_applied() -> None:
    quote = _fx()
    summary = _summary(
        _position(1, SYMBOL, market="US", currency="USD", price="200", fx_to_twd="31.5")
    )
    book = build_book_context(
        summary, symbol=SYMBOL, market="US", close=200.0, currency="USD", atr=4.0, fx=quote
    )
    assert book.fx_disclosure == quote.source_note
    notes = book_notes(book)
    assert notes[notes.index(book.fx_note or "") + 1] == quote.source_note


# --- T10-5: (ii-a), not (ii-b) -----------------------------------------------


def test_t10_5_a_twd_stored_us_card_beside_a_valued_usd_holding_states_no_source() -> None:
    """Task RK-4 R4-3 / RK4-R1: (B) reads this symbol's own lots only. Another
    holding's converted value (O-3) puts no methodology on a type-A card -- the
    whole-book reading (ii-b) was vetoed for exactly this card (RK4-R8)."""
    other = _position(2, "MSFT", market="US", currency="USD", price="200", fx_to_twd="31.5")
    other = other.model_copy(
        update={
            "valuation": other.valuation.model_copy(
                update={
                    "fx": FxInfo(
                        pair="USDTWD",
                        as_of="2026-07-24",
                        source="bank_of_taiwan",
                        data_status=DataStatus.FRESH,
                        source_note=SOURCE_NOTES["bank_of_taiwan"],
                    )
                }
            )
        }
    )
    summary = _summary(_position(1, SYMBOL, market="US", currency="TWD", price="200"), other)
    for quote in (_fx(), _fx(None, status=DataStatus.UNAVAILABLE, as_of=None)):
        book = build_book_context(
            summary, symbol=SYMBOL, market="US", close=200.0, currency="USD", atr=4.0, fx=quote
        )
        assert book.fx_disclosure is None
        _assert_no_methodology(book_notes(book))


def test_t10_5_the_card_of_a_twd_stored_us_holding_beside_a_valued_usd_one(
    api_harness: ApiHarness,
) -> None:
    provider = AppliedFx()
    serve_us_market(
        tw_service=api_harness.price_service,
        us_service=_us_service(SYMBOL, "MSFT"),
        fx_provider=provider,
    )
    _hold(api_harness.positions, SYMBOL, "TWD")
    _hold(api_harness.positions, "MSFT", "USD")

    # Not vacuous: the other holding was valued and converted with a sentence.
    rows = api_harness.client.get("/api/portfolio/summary").json()["positions"]
    msft = next(row for row in rows if row["symbol"] == "MSFT")
    assert msft["valuation"]["status"] == "ok"
    assert msft["valuation"]["fx"]["source_note"] in METHODOLOGY

    body = api_harness.client.get(f"/api/advice/{SYMBOL}", params={"market": "US"}).json()
    assert body["status"] == "ok"
    _assert_no_methodology(body["context_notes"])


# --- XS-2: observation O-1 stays behind the engine's guards ------------------


def test_xs2_an_applied_rate_on_an_unusable_close_reaches_no_outcome(tmp_path: Path) -> None:
    """O-1 (risk second part: accepted, low): a consistent US/USD holding whose
    latest close is unusable still takes the applying branch, so the snapshot's
    ``reason`` carries the applied-rate sentence. The price rule, the signal
    rule and the risk-limit rule must each keep it out of what they report."""
    closes = list(US_CLOSES)
    closes[-1] = 0.0
    service = FakePriceService()
    service.seed(SYMBOL, recent_bars(closes, symbol=SYMBOL, market="US"))
    provider = AppliedFx()
    store = PositionStore(db_path=tmp_path / "positions.db")
    _hold(store, SYMBOL, "USD")

    snap = _snapshot(store, service, provider)
    assert APPLIED_HEAD in (snap.reason or "")  # O-1 is really in play

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    for payload in (
        price_rule(above=False, threshold=150.0, symbol=SYMBOL, market="US"),
        signal_rule(field="drawdown.current", op="lt", value=-0.5, symbol=SYMBOL, market="US"),
        limit_rule(limit_id="any", symbol=SYMBOL, market="US"),
        limit_rule(limit_id="per_trade_loss", symbol=SYMBOL, market="US"),
    ):
        add_rule(alerts, payload)
    result = _evaluate(store, service, provider, alerts)
    assert len(result.outcomes) == 4
    texts = [outcome.reason or "" for outcome in result.outcomes]
    texts += [event.message for event in result.events]
    assert not any(APPLIED_HEAD in text for text in texts)
