"""API tests for ``GET /api/advice/{symbol}``: card shape, context, disclosures."""

from __future__ import annotations

from app.advice.book import EQUITY_BASIS_NOTE, GROSS_EXPOSURE_NOTE
from app.advice.engine import DISCLAIMER
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness


def _seed_bars(harness: ApiHarness, symbol: str = "2330", count: int = 200) -> None:
    harness.price_service.seed(symbol, recent_bars(trending_closes(count), symbol=symbol))


def test_advice_returns_the_build_advice_card_verbatim(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["status"] == "ok"
    card = body["advice"]
    # Every key the engine promises is present, unrenamed.
    assert set(card) >= {
        "symbol",
        "action",
        "quantity_range",
        "matched_rules",
        "counterarguments",
        "invalidation_conditions",
        "confidence",
        "confidence_meaning",
        "rules_version",
        "disclaimer",
        "limits_check",
        "action_weights",
        "direction_weights",
        "evaluation",
    }
    assert card["disclaimer"] == DISCLAIMER
    assert len(card["limits_check"]) == 5


def test_advice_marks_a_held_symbol_and_lists_its_position_ids(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    created = api_harness.client.post("/api/positions", json=position_payload()).json()
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["held"] is True
    assert body["position_ids"] == [created["id"]]
    context = body["portfolio_context"]
    assert context["quantity"] == 1000.0
    assert context["position_market_value_twd"] > 0.0


def test_advice_works_for_a_candidate_the_user_does_not_hold(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness, symbol="2454")
    body = api_harness.client.get("/api/advice/2454").json()
    assert body["status"] == "ok"
    assert body["held"] is False
    assert body["position_ids"] == []
    context = body["portfolio_context"]
    # A candidate is zero position / zero quantity, not a fabricated holding.
    assert context["position_market_value_twd"] == 0.0
    assert context["quantity"] == 0.0
    assert context["position_cost_twd"] is None


def test_candidate_skips_the_position_rules_by_naming_the_missing_fields(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness, symbol="2454")
    card = api_harness.client.get("/api/advice/2454").json()["advice"]
    skipped_fields = {
        field
        for entry in card["evaluation"]["skipped_rules"]
        for field in entry["missing_fields"]
    }
    # Nothing is held anywhere, so the book has no equity and this symbol has no
    # weight in it. The rules reading position weight must be skipped with the
    # field named, not evaluated against a fabricated 0%.
    assert "position.weight" in skipped_fields


def test_advice_states_its_equity_assumption_and_the_omitted_exposure(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/advice/2330").json()
    assert EQUITY_BASIS_NOTE in body["context_notes"]
    assert GROSS_EXPOSURE_NOTE in body["context_notes"]
    # And the cap itself reports not_evaluable rather than a forced 100%.
    gross = next(c for c in body["advice"]["limits_check"] if c["id"] == "gross_exposure")
    assert gross["status"] == "not_evaluable"


def test_advice_without_price_data_is_200_insufficient(api_harness: ApiHarness) -> None:
    response = api_harness.client.get("/api/advice/9999")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["advice"] is None
    assert "沒有可用的日線資料" in body["reason"]


def test_advice_uses_the_stored_risk_budget(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_position_weight": 0.99}}
    )
    body = api_harness.client.get("/api/advice/2330").json()
    weight_cap = next(
        c for c in body["advice"]["limits_check"] if c["id"] == "single_position_weight"
    )
    assert weight_cap["threshold"] == 0.99


def test_advice_never_emits_a_target_price(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    card = api_harness.client.get("/api/advice/2330").json()["advice"]
    forbidden = {"target_price", "price_target", "score", "rating", "expected_return"}
    assert forbidden.isdisjoint(card)


def test_advice_for_a_market_without_an_adapter_says_so(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/advice/AAPL", params={"market": "US"}).json()
    assert body["status"] == "insufficient_data"
    assert "沒有 US 市場的行情來源" in body["reason"]
