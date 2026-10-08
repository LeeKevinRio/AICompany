"""PR-0: cap 4 on the advice card when the book layer withheld the close and ATR.

``build_book_context`` withholds the close and the ATR *together* when a
holding has no usable rate or is spread over several currencies, and puts a
placeholder ``fx_to_twd=1.0`` in the context. The advice endpoint used not to
pass its ATR to the builder, and ``build_advice`` then filled the signals' ATR
back in -- so cap 4 was computed at the placeholder rate, on the very card
whose FX note says no 1.0 rate is substituted.

Each case below goes through ``GET /api/advice`` (C-4) and checks the same
invariant: on an ``ok`` response, ``portfolio_context.close is None`` implies
``portfolio_context.atr is None`` and a cap 4 that is neither ``passed`` nor
``violated``. Each also checks that the sentence explaining *why* is on the
card (R0-3 (a)), since cap 4's own sentence only says the ATR is missing.

Spec: ``work/dispatch/2026-10-07-任務單-PR-0-決策卡第4條ATR回填繞過book層撤下.md``
(tech-architect C-1 to C-5; risk-compliance R0-3, R0-4).
"""

from __future__ import annotations

import json
import re
import string
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.advice.book import (
    FX_PAIR_MISMATCH_NOTE,
    FX_UNAVAILABLE_NOTE,
    MIXED_CURRENCY_NOTE,
    NO_FX_QUOTE_NOTE,
    UNVALUED_DIRECTION_OWN_AND_OTHERS,
    UNVALUED_DIRECTION_OWN_ONLY,
    UNVALUED_DIRECTION_READS_HIGH,
    UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW,
    UNVALUED_DIRECTION_TARGET_SYMBOL,
)
from app.api.deps import (
    get_cached_valuator,
    get_fx_provider,
    get_market_resolver,
    get_valuator,
)
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.main import app
from app.portfolio.valuation import PositionValuator, PriceService
from app.positions.models import Market, PositionInput
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness

#: The three FX notes: whichever of them the card's lookup produced, one of
#: them has to be on the card (R0-3 (a)).
FX_NOTES = (NO_FX_QUOTE_NOTE, FX_UNAVAILABLE_NOTE, FX_PAIR_MISMATCH_NOTE)
#: The wording R0-4 replaced: it must not appear on any card.
RETIRED_PHRASE = "價格類上限"


class _FlatFx(FxRateProvider):
    """Quotes one flat rate for every day in the requested window."""

    source_id = "bank_of_taiwan"

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[
                FxRate(pair=pair, date=end, rate=Decimal("31.5"), as_of=now, source=self.source_id)
            ],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


def _matches(note: str, template: str) -> bool:
    """Whether ``note`` is ``template`` rendered with some values."""
    pattern = "".join(
        re.escape(literal) + (".+?" if field is not None else "")
        for literal, field, _, _ in string.Formatter().parse(template)
    )
    return re.fullmatch(pattern, note) is not None


def _assert_withheld(body: dict[str, Any]) -> dict[str, Any]:
    """The PR-0 invariant on an ``ok`` card; returns cap 4."""
    assert body["status"] == "ok"
    context = body["portfolio_context"]
    cap4: dict[str, Any] = next(
        c for c in body["advice"]["limits_check"] if c["id"] == "per_trade_loss"
    )
    if context["close"] is None:
        assert context["atr"] is None
        assert cap4["status"] not in {"passed", "violated"}
    assert RETIRED_PHRASE not in json.dumps(body, ensure_ascii=False)
    return cap4


def _assert_cap4_is_the_atr_sentence(cap4: dict[str, Any]) -> None:
    assert cap4["status"] == "not_evaluable"
    assert cap4["observed"] is None
    assert cap4["detail"].startswith("缺少 ATR(14)")


def _has_fx_note(notes: list[str]) -> bool:
    return any(_matches(note, template) for note in notes for template in FX_NOTES)


@pytest.fixture
def us_market(api_harness: ApiHarness) -> Iterator[FakePriceService]:
    """A US leg on the same fake: bars for AAPL in USD, valued at no rate."""
    service = api_harness.price_service
    service.seed("AAPL", recent_bars(trending_closes(200), symbol="AAPL", market="US"))
    app.dependency_overrides[get_market_resolver] = lambda: {"TW": service, "US": service}
    _valuators(service, UnavailableFxProvider())
    yield service


def _valuators(service: FakePriceService, fx: FxRateProvider) -> None:
    """Both valuators (live and the card's cache-only one) on ``fx``."""
    markets: dict[Market, PriceService] = {"TW": service, "US": service}
    app.dependency_overrides[get_valuator] = lambda: PositionValuator(
        market_services=markets, fx_provider=fx
    )
    app.dependency_overrides[get_cached_valuator] = lambda: PositionValuator(
        market_services=markets, fx_provider=fx, price_mode="cache_only"
    )


def _seed_2330(api_harness: ApiHarness) -> None:
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))


def _aapl() -> dict[str, object]:
    return position_payload(symbol="AAPL", market="US", currency="USD", quantity="100")


def test_t1_legacy_lots_in_two_currencies_withhold_cap_4(api_harness: ApiHarness) -> None:
    """T1: one TW symbol, a TWD lot and a legacy USD lot (no API path writes one).

    This mixed-currency fixture contains an X-3 row (currency does not match
    market); valuation of that row is X-3c's scope. So only cap 4 and the
    note are asserted here -- neither that row's valuation state nor cap 1's
    figure (KX-P1).
    """
    _seed_2330(api_harness)
    for currency, quantity in (("TWD", 1000), ("USD", 100)):
        api_harness.positions.create(
            PositionInput(
                symbol="2330",
                market="TW",
                quantity=Decimal(quantity),
                avg_cost=Decimal(600),
                currency=currency,  # type: ignore[arg-type]
                opened_at=date(2024, 1, 2),
                instrument_type="stock",
                sector=None,
                note=None,
            )
        )
    body = api_harness.client.get("/api/advice/2330").json()
    cap4 = _assert_withheld(body)
    assert body["portfolio_context"]["close"] is None
    _assert_cap4_is_the_atr_sentence(cap4)
    assert MIXED_CURRENCY_NOTE in body["context_notes"]


def test_the_mixed_currency_note_is_the_approved_wording() -> None:
    """R0-4: pinned verbatim; the only change from before is the cap phrase."""
    assert MIXED_CURRENCY_NOTE == (
        "此標的的持倉橫跨多種計價幣別，無法決定單一匯率，價格與 ATR 相關的上限不計算。"
    )
    assert RETIRED_PHRASE not in MIXED_CURRENCY_NOTE


@pytest.mark.usefixtures("us_market")
def test_t2_a_us_holding_with_no_rate_beside_a_valued_tw_one(api_harness: ApiHarness) -> None:
    _seed_2330(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.post("/api/positions", json=_aapl())
    body = api_harness.client.get("/api/advice/AAPL", params={"market": "US"}).json()
    cap4 = _assert_withheld(body)
    assert body["held"] is True
    assert body["portfolio_context"]["total_equity_twd"] > 0.0
    assert body["portfolio_context"]["close"] is None
    _assert_cap4_is_the_atr_sentence(cap4)
    assert _has_fx_note(body["context_notes"])


@pytest.mark.usefixtures("us_market")
def test_t3_a_us_candidate_with_no_rate(api_harness: ApiHarness) -> None:
    _seed_2330(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/advice/AAPL", params={"market": "US"}).json()
    cap4 = _assert_withheld(body)
    assert body["held"] is False
    assert body["portfolio_context"]["total_equity_twd"] > 0.0
    assert body["portfolio_context"]["close"] is None
    _assert_cap4_is_the_atr_sentence(cap4)
    assert _has_fx_note(body["context_notes"])


def _t4_body(api_harness: ApiHarness, service: FakePriceService) -> dict[str, Any]:
    """The valuator has a rate, the card's own lookup does not (C-4 T4)."""
    _valuators(service, _FlatFx())
    body: dict[str, Any] = api_harness.client.get(
        "/api/advice/AAPL", params={"market": "US"}
    ).json()
    return body


def test_t4_the_valuator_has_a_rate_the_card_does_not(
    api_harness: ApiHarness, us_market: FakePriceService
) -> None:
    _seed_2330(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.post("/api/positions", json=_aapl())
    body = _t4_body(api_harness, us_market)
    cap4 = _assert_withheld(body)
    context = body["portfolio_context"]
    # The holding itself is valued (at 31.5); only the card's lookup failed.
    assert context["position_market_value_twd"] > 0.0
    assert context["unvalued"]["own_lots"] == 0
    assert context["book_fully_valued"] is True
    assert context["close"] is None
    _assert_cap4_is_the_atr_sentence(cap4)
    assert _has_fx_note(body["context_notes"])


def test_t4a_with_another_holding_unvalued_the_direction_names_no_own_lots(
    api_harness: ApiHarness, us_market: FakePriceService
) -> None:
    """R0-3 (b): cap 4 withheld, and the direction clause is D-a or D-P.

    (D-a3 is not in the product yet; it arrives with 6-b.)
    """
    _seed_2330(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.post("/api/positions", json=_aapl())
    # No bars anywhere for 2317: unvalued, and not this card's own lot.
    api_harness.client.post("/api/positions", json=position_payload(symbol="2317"))
    body = _t4_body(api_harness, us_market)
    cap4 = _assert_withheld(body)
    context = body["portfolio_context"]
    assert context["unvalued"]["own_lots"] == 0
    assert context["book_fully_valued"] is False
    _assert_cap4_is_the_atr_sentence(cap4)
    assert _has_fx_note(body["context_notes"])
    allowed = [UNVALUED_DIRECTION_READS_HIGH]
    if context["sector"] is not None:
        allowed.append(
            UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
                target=UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector=context["sector"])
            )
        )
    directions = [d for d in allowed if any(note.endswith(d) for note in body["context_notes"])]
    assert len(directions) == 1
    for own_clause in (UNVALUED_DIRECTION_OWN_ONLY, UNVALUED_DIRECTION_OWN_AND_OTHERS):
        assert not any(own_clause in note for note in body["context_notes"])


def test_a_card_with_a_usable_rate_still_computes_cap_4(
    api_harness: ApiHarness, us_market: FakePriceService
) -> None:
    """The fix withholds cap 4 only where the close was withheld (regression guard)."""
    _seed_2330(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.post("/api/positions", json=_aapl())
    _valuators(us_market, _FlatFx())
    app.dependency_overrides[get_fx_provider] = lambda: _FlatFx()
    body = api_harness.client.get("/api/advice/AAPL", params={"market": "US"}).json()
    cap4 = _assert_withheld(body)
    context = body["portfolio_context"]
    assert context["close"] is not None
    assert context["atr"] is not None
    assert cap4["status"] in {"passed", "violated"}
    tw = api_harness.client.get("/api/advice/2330").json()
    tw_cap4 = _assert_withheld(tw)
    assert tw["portfolio_context"]["atr"] is not None
    assert tw_cap4["status"] in {"passed", "violated"}
