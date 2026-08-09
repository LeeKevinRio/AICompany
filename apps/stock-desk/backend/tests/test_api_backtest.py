"""API tests for ``POST /api/backtest`` (walk-forward, offline fakes only)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.api.backtest import BUY_AND_HOLD_NOTE, UNVERIFIED_RATES_NOTE
from app.backtest.strategies import STRATEGY_IDS
from tests.api_helpers import oscillating_closes, recent_bars
from tests.conftest import ApiHarness

_END = date(2026, 7, 20)
_START = _END - timedelta(days=600)


def _seed(harness: ApiHarness, count: int = 400, symbol: str = "2330") -> None:
    harness.price_service.seed(
        symbol, recent_bars(oscillating_closes(count), symbol=symbol, end=_END)
    )


def _request(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "strategy": "ma_cross",
        "start": _START.isoformat(),
        "end": _END.isoformat(),
        "train_size": 200,
        "test_size": 60,
    }
    body.update(overrides)
    return body


def test_backtest_returns_a_walk_forward_report(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    response = api_harness.client.post("/api/backtest", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    report = body["report"]
    # In-sample and out-of-sample are reported separately, never blended.
    assert set(report) == {"in_sample", "out_of_sample"}
    for segment in report.values():
        assert set(segment) == {"strategy", "buy_and_hold"}


def test_each_segment_carries_the_full_metric_block(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    report = api_harness.client.post("/api/backtest", json=_request()).json()["report"]
    metrics = report["out_of_sample"]["strategy"]
    assert set(metrics) >= {
        "label",
        "start_date",
        "end_date",
        "observations",
        "total_return",
        "cagr",
        "annualized_volatility",
        "sharpe",
        "sortino",
        "max_drawdown",
        "max_drawdown_peak_date",
        "max_drawdown_trough_date",
        "win_rate",
        "profit_factor",
        "num_trades",
        "num_closing_trades",
        "turnover",
    }
    assert metrics["label"] == "out_of_sample:strategy"


def test_buy_and_hold_benchmark_is_present_and_flagged_gross_of_cost(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness)
    body = api_harness.client.post("/api/backtest", json=_request()).json()
    assert body["report"]["out_of_sample"]["buy_and_hold"]["label"] == (
        "out_of_sample:buy_and_hold"
    )
    assert BUY_AND_HOLD_NOTE in body["notes"]


def test_unverified_rates_are_disclosed_on_every_report(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    body = api_harness.client.post("/api/backtest", json=_request()).json()
    assert body["rates_verified"] is False
    assert body["cost_model"]["verified_on"] is None
    assert UNVERIFIED_RATES_NOTE in body["notes"]


def test_cost_overrides_are_applied_to_the_run(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    cheap = api_harness.client.post("/api/backtest", json=_request()).json()
    expensive = api_harness.client.post(
        "/api/backtest",
        json=_request(cost={"tw_broker_fee_rate": 0.05, "tw_tax_rate_stock": 0.05}),
    ).json()
    assert expensive["cost_model"]["tw_broker_fee_rate"] == 0.05
    # Higher costs cannot make the strategy end richer than lower costs.
    assert (
        expensive["report"]["out_of_sample"]["strategy"]["end_equity"]
        <= cheap["report"]["out_of_sample"]["strategy"]["end_equity"]
    )


def test_folds_are_reported_and_do_not_overlap(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    folds = api_harness.client.post("/api/backtest", json=_request()).json()["folds"]
    assert folds
    for fold in folds:
        # The test window sits strictly after its own train window.
        assert fold["test_start"] >= fold["train_stop"]
    for earlier, later in zip(folds, folds[1:], strict=False):
        assert later["test_start"] >= earlier["test_stop"]


def test_too_little_history_is_200_insufficient_not_a_single_split(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, count=100)
    response = api_harness.client.post("/api/backtest", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["report"] is None
    assert "不以單一切分代替" in body["reason"]


def test_train_size_below_the_strategy_warmup_is_refused(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    body = api_harness.client.post(
        "/api/backtest", json=_request(train_size=30, test_size=30)
    ).json()
    assert body["status"] == "insufficient_data"
    assert "暖身" in body["reason"]


def test_no_bars_at_all_is_200_insufficient(api_harness: ApiHarness) -> None:
    body = api_harness.client.post("/api/backtest", json=_request()).json()
    assert body["status"] == "insufficient_data"
    assert body["data"]["bar_count"] == 0


def test_unknown_strategy_is_422(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    response = api_harness.client.post("/api/backtest", json=_request(strategy="secret_sauce"))
    assert response.status_code == 422
    assert "未知的 strategy" in response.text


def test_every_shipped_strategy_produces_the_same_report_shape(
    api_harness: ApiHarness,
) -> None:
    # AC-10.4 / AC-11.4: only the strategy logic differs; the envelope, the
    # in/out-of-sample split, the cost model and the disclosures do not.
    _seed(api_harness)
    baseline = api_harness.client.post("/api/backtest", json=_request()).json()
    for strategy_id in STRATEGY_IDS:
        body = api_harness.client.post(
            "/api/backtest", json=_request(strategy=strategy_id)
        ).json()
        assert body["status"] == "ok", strategy_id
        assert body["strategy"] == strategy_id
        assert set(body) == set(baseline)
        assert body["report"].keys() == baseline["report"].keys()
        for segment, segment_report in body["report"].items():
            assert segment_report.keys() == baseline["report"][segment].keys()
            assert (
                segment_report["strategy"].keys()
                == baseline["report"][segment]["strategy"].keys()
            )
        assert body["cost_model"] == baseline["cost_model"]
        assert body["notes"] == baseline["notes"]
        assert body["folds"] == baseline["folds"]


def test_new_strategies_actually_trade_on_an_oscillating_path(
    api_harness: ApiHarness,
) -> None:
    # A strategy that never takes a position would pass the shape test above
    # while measuring nothing, so pin that each new one does trade.
    _seed(api_harness)
    for strategy_id in ("rsi_reversal", "breakout"):
        report = api_harness.client.post(
            "/api/backtest", json=_request(strategy=strategy_id)
        ).json()["report"]
        assert report["out_of_sample"]["strategy"]["num_trades"] > 0, strategy_id


def test_new_strategies_report_insufficient_data_without_enough_history(
    api_harness: ApiHarness,
) -> None:
    # AC-10.5 / AC-11.5: too short for one fold is still a 200 + insufficient.
    _seed(api_harness, count=100)
    for strategy_id in ("rsi_reversal", "breakout"):
        body = api_harness.client.post(
            "/api/backtest", json=_request(strategy=strategy_id)
        ).json()
        assert body["status"] == "insufficient_data"
        assert body["report"] is None
        assert "不以單一切分代替" in body["reason"]


def test_end_before_start_is_422(api_harness: ApiHarness) -> None:
    response = api_harness.client.post(
        "/api/backtest", json=_request(start="2026-01-01", end="2025-01-01")
    )
    assert response.status_code == 422
    assert "end 不可早於 start" in response.text


def test_out_of_range_cost_override_is_422(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    response = api_harness.client.post(
        "/api/backtest", json=_request(cost={"tw_broker_fee_rate": 3})
    )
    assert response.status_code == 422
    locs = [tuple(err["loc"]) for err in response.json()["detail"]]
    assert ("body", "cost", "tw_broker_fee_rate") in locs
