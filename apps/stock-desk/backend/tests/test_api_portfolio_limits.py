"""API tests for ``GET /api/portfolio/limits`` (FR-8).

The endpoint's job is to wire real inputs -- stored positions, settings, bars,
FX -- into :func:`app.advice.book_limits.evaluate_book_limits`. These tests
therefore check the wiring and the response shape; the aggregation rules
themselves are pinned in ``test_advice_book_limits.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.advice.limits import LIMIT_IDS, NO_NET_WORTH_DETAIL
from app.settings.models import NetWorthSettings
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness


def _limits(harness: ApiHarness) -> dict[str, dict[str, Any]]:
    body = harness.client.get("/api/portfolio/limits").json()
    return {check["limit_id"]: check for check in body["limits"]}


def _hold(harness: ApiHarness, symbol: str, quantity: str, **overrides: object) -> None:
    """Seed bars for ``symbol`` and record a holding of it."""
    harness.price_service.seed(symbol, recent_bars(trending_closes(200), symbol=symbol))
    harness.client.post(
        "/api/positions",
        json=position_payload(symbol=symbol, quantity=quantity, avg_cost="100", **overrides),
    )


def test_limits_reports_the_five_caps_in_order(api_harness: ApiHarness) -> None:
    _hold(api_harness, "2330", "1000")
    body = api_harness.client.get("/api/portfolio/limits").json()
    assert [check["limit_id"] for check in body["limits"]] == list(LIMIT_IDS)
    for check in body["limits"]:
        assert check["status"] in {"passed", "violated", "not_evaluable"}
        assert check["detail"]
        assert set(check) == {
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
        }
    assert body["notes"]
    assert body["as_of"]


def test_an_empty_book_reports_every_cap_as_not_evaluable(api_harness: ApiHarness) -> None:
    checks = _limits(api_harness)
    assert {check["status"] for check in checks.values()} == {"not_evaluable"}
    assert all(check["observed"] is None for check in checks.values())


def test_the_worst_holding_is_named_with_its_real_observed_weight(
    api_harness: ApiHarness,
) -> None:
    # Two holdings priced from the same series: 800 shares against 200 is 80% of
    # the valued book, and that is the number the cap has to report.
    _hold(api_harness, "2330", "800")
    _hold(api_harness, "2454", "200")
    cap = _limits(api_harness)["single_position_weight"]
    assert cap["worst_symbol"] == "2330"
    assert cap["status"] == "violated"
    assert cap["observed"] is not None and abs(cap["observed"] - 0.8) < 1e-9
    assert cap["evaluated_count"] == 2


def test_the_stop_loss_cap_is_computed_from_each_holdings_own_atr(
    api_harness: ApiHarness,
) -> None:
    _hold(api_harness, "2330", "800")
    cap = _limits(api_harness)["per_trade_loss"]
    # The seeded series has a real ATR(14), so this cap is evaluated rather than
    # reported as "no signal" -- which is the whole point of FR-8 for cap 4.
    assert cap["status"] in {"passed", "violated"}
    assert cap["observed"] is not None
    assert cap["worst_symbol"] == "2330"


def test_a_holding_with_no_bars_is_excluded_from_the_stop_loss_cap(
    api_harness: ApiHarness,
) -> None:
    _hold(api_harness, "2330", "800")
    # Recorded but never seeded: no bars, so no price and no ATR for it.
    api_harness.client.post(
        "/api/positions", json=position_payload(symbol="2454", quantity="200", avg_cost="100")
    )
    checks = _limits(api_harness)
    cap = checks["per_trade_loss"]
    assert cap["worst_symbol"] == "2330"
    assert [entry["symbol"] for entry in cap["excluded"]] == ["2454"]
    assert cap["excluded"][0]["reason"]
    # A holding that could not be valued is not a holding that passed.
    assert cap["status"] != "not_evaluable"
    assert "未納入本條上限的比較" in cap["detail"]


def test_gross_exposure_flips_once_a_fresh_net_worth_is_reported(
    api_harness: ApiHarness,
) -> None:
    _hold(api_harness, "2330", "1000")
    assert _limits(api_harness)["gross_exposure"]["detail"] == NO_NET_WORTH_DETAIL

    current = api_harness.settings.load()
    api_harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=99_000_000.0,
                    updated_at=datetime.now(UTC).isoformat(),
                )
            }
        )
    )
    cap = _limits(api_harness)["gross_exposure"]
    assert cap["status"] == "passed"
    assert cap["observed"] is not None and cap["observed"] > 0.0
    assert cap["worst_symbol"] is None


def test_an_expired_net_worth_does_not_produce_a_silent_pass(
    api_harness: ApiHarness,
) -> None:
    _hold(api_harness, "2330", "1000")
    stale = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    current = api_harness.settings.load()
    api_harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=99_000_000.0, updated_at=stale
                )
            }
        )
    )
    cap = _limits(api_harness)["gross_exposure"]
    assert cap["status"] == "not_evaluable"
    assert cap["observed"] is None


def test_the_sector_cap_uses_the_industry_the_user_filed(api_harness: ApiHarness) -> None:
    _hold(api_harness, "2330", "800", sector="半導體業")
    _hold(api_harness, "2882", "200", sector="金融保險業")
    cap = _limits(api_harness)["sector_weight"]
    assert cap["status"] == "violated"
    assert "半導體業" in cap["detail"]
    assert cap["worst_symbol"] is None
    assert cap["evaluated_count"] == 2


def test_an_unfiled_industry_is_reported_as_such_not_as_a_pass(
    api_harness: ApiHarness,
) -> None:
    _hold(api_harness, "2330", "1000")
    cap = _limits(api_harness)["sector_weight"]
    assert cap["status"] == "not_evaluable"
    assert [entry["symbol"] for entry in cap["excluded"]] == ["2330"]
    assert "尚未填寫產業別" in cap["excluded"][0]["reason"]


def test_every_priced_holding_carries_its_data_provenance(api_harness: ApiHarness) -> None:
    _hold(api_harness, "2330", "800")
    body = api_harness.client.get("/api/portfolio/limits").json()
    assert [source["symbol"] for source in body["sources"]] == ["2330"]
    data = body["sources"][0]["data"]
    assert data["bar_count"] > 0
    assert data["source"] == "fake"
