"""ADR-0023 6-a: W-a2 and D-5 with own lots, built through the formal API only.

Before this file the only W-a2 coverage was a hand-assembled context
(``test_adr0023_own_unvalued.py``) or a stubbed ``build_summary`` whose cap 4
was W-a1. tech-architect's reachability assessment
(``work/reviews/2026-10-08-tech-architect-第4條W-a2可達性與F-6修法評估.md``,
question 1) found a route that needs no stub and no direct DB write: two lots
of the same US symbol, one with an ``opened_at`` and one without. The lot with
no open date has no ``fx_open``, so it is ``insufficient_data`` (``missing`` is
``["fx_open"]``), while the dated lot is ``ok``. The book is then single
currency, the rate resolves, close and ATR survive, and ``own_lots`` is 1.

Everything is created through ``POST /api/positions``, ``PUT /api/settings``
and ``PUT /api/kelly-inputs``; the card is read through ``GET /api/advice``.
The "reference book" in each test is the same book with the unvalued lot
deleted through ``DELETE /api/positions/{id}``: it is what the card said before
the lot was added, so the expected W-a2 detail is the reference detail plus the
approved W-a2 sentence, rebuilt from the constant in ``app.advice.limits``
(never retyped).

Premise for cap 4 (reported, not worked around): ``trending_closes(200)`` ends
at a close of 199.5 with an ATR(14) of 0.5, so the reference ratio is about
0.5%, under the default ``max_loss_per_trade`` of 1%. The reference book
therefore *passes* cap 4 and the lot cannot produce W-a2 on it. The tests lower
``max_loss_per_trade`` through the formal ``PUT /api/settings`` (the route the
architect's fixture note allows) so that the reference ratio reaches the cap;
``test_the_reference_book_violates_cap_4`` asserts that premise explicitly.

Spec: ADR-0023 Decision 4 (and its 2026-10-08 note); risk-compliance
``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md``
R-P3-1 (observed rule), R-P3-2 (observed equals the computed ratio and
``format_percent(observed)`` is in the detail; D-5 with own lots has
``observed is None`` and ``threshold == allowed``).
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, TypeVar

import pytest

from app.advice.book import (
    FX_PAIR_MISMATCH_NOTE,
    FX_UNAVAILABLE_NOTE,
    MIXED_CURRENCY_NOTE,
    NO_FX_QUOTE_NOTE,
)
from app.advice.limits import (
    LIMIT_NAMES,
    OWN_UNVALUED_NOT_EVALUABLE_DETAIL,
    OWN_UNVALUED_VIOLATED_DETAIL,
    RiskBudget,
    format_percent,
)
from app.alerts.engine import SymbolSnapshot
from app.alerts.snapshot import build_snapshot
from app.api.kelly import kelly_inputs_for
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import PositionValuator, PriceService
from app.positions.models import Market
from tests.api_helpers import (
    FakePriceService,
    position_payload,
    recent_bars,
    serve_us_market,
    trending_closes,
)
from tests.conftest import ApiHarness

T = TypeVar("T")

#: The flat USDTWD rate the stub quotes; the card must apply exactly this.
FX_RATE = "31.5"
#: Low enough that the reference book's cap 4 ratio (about 0.5%) reaches it.
LOW_MAX_LOSS_PER_TRADE = 0.002
FX_FAILURE_NOTES = (NO_FX_QUOTE_NOTE, FX_UNAVAILABLE_NOTE, FX_PAIR_MISMATCH_NOTE)

WEIGHT = "single_position_weight"
LOSS = "per_trade_loss"
KELLY = "kelly_fraction"


class _FlatFx(FxRateProvider):
    """Quotes one flat USDTWD rate for every day in the requested window."""

    source_id = "bank_of_taiwan"

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[
                FxRate(pair=pair, date=end, rate=Decimal(FX_RATE), as_of=now, source=self.source_id)
            ],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


def _w_a1(limit_id: str) -> str:
    return OWN_UNVALUED_NOT_EVALUABLE_DETAIL.format(name=LIMIT_NAMES[limit_id])


def _w_a2(limit_id: str) -> str:
    return OWN_UNVALUED_VIOLATED_DETAIL.format(name=LIMIT_NAMES[limit_id])


def _matches(note: str, template: str) -> bool:
    """Whether ``note`` is ``template`` rendered with some values."""
    pattern = "".join(
        re.escape(literal) + (".+?" if field is not None else "")
        for literal, field, _, _ in string.Formatter().parse(template)
    )
    return re.fullmatch(pattern, note) is not None


class _Book:
    """The two AAPL lots as the formal ``POST /api/positions`` created them."""

    def __init__(self, harness: ApiHarness, service: FakePriceService) -> None:
        self.harness = harness
        self.service = service
        client = harness.client
        dated = client.post("/api/positions", json=_aapl("100", "2024-01-02"))
        undated = client.post("/api/positions", json=_aapl("10", None))
        assert dated.status_code == 201, dated.text
        assert undated.status_code == 201, undated.text
        assert dated.json()["opened_at"] == "2024-01-02"
        assert undated.json()["opened_at"] is None
        self.dated_id: int = dated.json()["id"]
        self.undated_id: int = undated.json()["id"]

    def advice(self) -> dict[str, Any]:
        response = self.harness.client.get("/api/advice/AAPL", params={"market": "US"})
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        assert body["status"] == "ok"
        return body

    def drop_the_unvalued_lot(self) -> None:
        response = self.harness.client.delete(f"/api/positions/{self.undated_id}")
        assert response.status_code == 204

    def full_and_reference(self, fetch: Callable[[], T]) -> tuple[T, T]:
        """``fetch`` on the two-lot book, then on the same book minus the unvalued lot."""
        full = fetch()
        self.drop_the_unvalued_lot()
        return full, fetch()


def _aapl(quantity: str, opened_at: str | None) -> dict[str, object]:
    return position_payload(
        symbol="AAPL", market="US", currency="USD", quantity=quantity, opened_at=opened_at
    )


@pytest.fixture
def book(api_harness: ApiHarness) -> _Book:
    """AAPL bars, a USDTWD rate, a cap 4 the reference book reaches, then both lots."""
    service = api_harness.price_service
    service.seed("AAPL", recent_bars(trending_closes(200), symbol="AAPL", market="US"))
    serve_us_market(tw_service=service, us_service=service, fx_provider=_FlatFx())
    saved = api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_loss_per_trade": LOW_MAX_LOSS_PER_TRADE}}
    )
    assert saved.status_code == 200, saved.text
    return _Book(api_harness, service)


def _put_kelly(book: _Book, win_rate: float, payoff_ratio: float) -> None:
    saved = book.harness.client.put(
        "/api/kelly-inputs/AAPL",
        params={"market": "US"},
        json={"win_rate": win_rate, "payoff_ratio": payoff_ratio},
    )
    assert saved.status_code == 200, saved.text


def _limit(body: dict[str, Any], limit_id: str) -> dict[str, Any]:
    check: dict[str, Any] = next(c for c in body["advice"]["limits_check"] if c["id"] == limit_id)
    return check


def _assert_card_premise(full: dict[str, Any], reference: dict[str, Any]) -> None:
    """The route is the one under test: own=1, close/ATR kept, rate applied, no FX failure."""
    context = full["portfolio_context"]
    assert context["unvalued"]["own_lots"] == 1
    assert full["held"] is True
    assert context["book_fully_valued"] is False
    assert context["close"] is not None
    assert context["atr"] is not None
    assert context["fx_to_twd"] == float(FX_RATE)
    notes = full["context_notes"]
    assert MIXED_CURRENCY_NOTE not in notes
    for template in FX_FAILURE_NOTES:
        assert not any(_matches(note, template) for note in notes), template
    # The reference book is the same card with nothing unvalued.
    assert reference["portfolio_context"]["unvalued"]["own_lots"] == 0
    assert reference["portfolio_context"]["book_fully_valued"] is True
    assert reference["portfolio_context"]["close"] == context["close"]
    assert reference["portfolio_context"]["atr"] == context["atr"]
    assert reference["portfolio_context"]["fx_to_twd"] == context["fx_to_twd"]


def _assert_w_a2(full: dict[str, Any], reference: dict[str, Any], limit_id: str) -> None:
    """R-P3-1 / R-P3-2: reference detail + W-a2, observed is the computed ratio."""
    before = _limit(reference, limit_id)
    after = _limit(full, limit_id)
    assert before["status"] == "violated", "premise: the reference book breaches this cap"
    assert before["observed"] is not None
    assert after["status"] == "violated"
    assert after["detail"] == before["detail"] + _w_a2(limit_id)
    assert after["observed"] == before["observed"]
    assert format_percent(after["observed"]) in after["detail"]
    assert after["threshold"] == before["threshold"]
    assert _w_a1(limit_id) not in after["detail"]


def test_the_formal_post_path_builds_one_valued_and_one_unvalued_lot(book: _Book) -> None:
    """Premise: the second lot (no ``opened_at``) is missing exactly ``fx_open``."""
    response = book.harness.client.get("/api/portfolio/summary")
    assert response.status_code == 200, response.text
    lots = {position["id"]: position for position in response.json()["positions"]}
    assert lots[book.dated_id]["valuation"]["status"] == "ok"
    assert lots[book.undated_id]["valuation"]["status"] == "insufficient_data"
    assert lots[book.undated_id]["valuation"]["missing"] == ["fx_open"]


def test_the_reference_book_violates_cap_4(book: _Book) -> None:
    """Premise: with only the dated lot, cap 4 is a plain breach (no W-a1, no W-a2)."""
    book.drop_the_unvalued_lot()
    reference = book.advice()
    context = reference["portfolio_context"]
    cap = _limit(reference, LOSS)
    assert context["unvalued"]["own_lots"] == 0
    assert context["close"] is not None and context["atr"] is not None
    assert cap["status"] == "violated"
    assert cap["threshold"] == LOW_MAX_LOSS_PER_TRADE
    assert cap["observed"] == pytest.approx(2 * context["atr"] / context["close"])
    assert cap["observed"] >= cap["threshold"]
    assert _w_a1(LOSS) not in cap["detail"] and _w_a2(LOSS) not in cap["detail"]
    # And the default budget would not have breached: the premise needed the setting.
    assert cap["observed"] < RiskBudget().max_loss_per_trade


def test_cap_4_keeps_a_breach_with_w_a2_on_the_formal_path(book: _Book) -> None:
    """R-P3-1 / R-P3-2 for cap 4, the cap with no prior formal-path coverage."""
    full, reference = book.full_and_reference(book.advice)
    _assert_card_premise(full, reference)
    _assert_w_a2(full, reference, LOSS)
    # The ratio is the dated lot's alone: the unvalued 10 shares are not in it.
    assert full["portfolio_context"]["quantity"] == 100.0


def test_cap_1_keeps_a_breach_with_w_a2_on_the_formal_path(book: _Book) -> None:
    """R-P3-1 / R-P3-2 for cap 1: AAPL is the only valued holding, so 100%."""
    full, reference = book.full_and_reference(book.advice)
    _assert_card_premise(full, reference)
    _assert_w_a2(full, reference, WEIGHT)
    assert _limit(full, WEIGHT)["observed"] == 1.0
    assert format_percent(1.0) in _limit(full, WEIGHT)["detail"]


def test_cap_5_keeps_a_breach_with_w_a2_on_the_formal_path(book: _Book) -> None:
    """R-P3-1 / R-P3-2 for cap 5 with a positive edge (win rate 0.6, payoff 2.0)."""
    _put_kelly(book, 0.6, 2.0)
    full, reference = book.full_and_reference(book.advice)
    _assert_card_premise(full, reference)
    _assert_w_a2(full, reference, KELLY)


def test_d5_with_own_lots_reports_no_observed_and_no_w_a2(book: _Book) -> None:
    """R-P3-1 / R-P3-2 second half: a non-positive edge on a short numerator.

    Win rate 0.3 and payoff 1.0 give f* below 0, so the allowance is not
    positive (D-5). The status, detail and threshold are the reference book's
    word for word; only ``observed`` goes from the weight to ``None``, and W-a2
    is not attached.
    """
    _put_kelly(book, 0.3, 1.0)
    full, reference = book.full_and_reference(book.advice)
    _assert_card_premise(full, reference)
    before = _limit(reference, KELLY)
    after = _limit(full, KELLY)
    assert before["status"] == "violated"
    assert before["observed"] is not None, "premise: without own lots the weight is reported"
    assert after["status"] == "violated"
    assert after["observed"] is None
    assert after["detail"] == before["detail"]
    assert _w_a2(KELLY) not in after["detail"]
    assert _w_a1(KELLY) not in after["detail"]
    assert after["threshold"] == before["threshold"]
    assert after["threshold"] is not None and after["threshold"] <= 0.0


def test_the_alert_snapshot_keeps_cap_4_as_a_breach_with_w_a2(book: _Book) -> None:
    """The alert path (``build_snapshot``) agrees with the card on the same book."""
    harness = book.harness
    market_services: dict[Market, PriceService] = {"TW": book.service, "US": book.service}

    def snapshot() -> SymbolSnapshot:
        return build_snapshot(
            "AAPL",
            "US",
            resolver=market_services,
            store=harness.positions,
            valuator=PositionValuator(market_services=market_services, fx_provider=_FlatFx()),
            budget=harness.settings.load().risk_budget,
            fx_provider=_FlatFx(),
            kelly=kelly_inputs_for(harness.kelly_inputs, "AAPL", "US"),
        )

    full, reference = book.full_and_reference(snapshot)
    assert full.price_cap_cause is None
    assert full.close is not None
    before = next(check for check in reference.limits if check.id == LOSS)
    after = next(check for check in full.limits if check.id == LOSS)
    assert before.status == "violated"
    assert before.observed is not None
    assert after.status == "violated"
    assert after.detail == before.detail + _w_a2(LOSS)
    assert after.observed == before.observed
    assert format_percent(after.observed) in after.detail
    assert after.threshold == before.threshold
