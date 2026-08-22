"""The manual half of ``/api/kelly-inputs``: write, read, clear, and ageing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.kelly.models import (
    KELLY_SOFT_NOTICE_DAYS,
    KELLY_STALE_AFTER_DAYS,
    KellyAttemptRecord,
    KellyInputRecord,
)
from tests.conftest import ApiHarness


def _put(client: TestClient, symbol: str = "2330", **body: float) -> dict[str, Any]:
    payload = {"win_rate": 0.55, "payoff_ratio": 1.8}
    payload.update(body)
    response = client.put(f"/api/kelly-inputs/{symbol}", json=payload)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def test_a_manual_pair_is_stored_and_read_back(api_harness: ApiHarness) -> None:
    written = _put(api_harness.client, win_rate=0.6, payoff_ratio=2.5)

    read = api_harness.client.get("/api/kelly-inputs/2330")

    assert read.status_code == 200
    item = read.json()["item"]
    assert (item["win_rate"], item["payoff_ratio"]) == (0.6, 2.5)
    assert item["source"] == "manual"
    assert item["strategy_id"] is None
    assert written["item"] == item


def test_a_fresh_input_reports_its_age_and_anchor(api_harness: ApiHarness) -> None:
    body = _put(api_harness.client)

    assert body["age_days"] == 0
    assert body["freshness"] == "fresh"
    # A manual input anchors on its own write stamp (D-4). The two fields are
    # serialised by different paths ("+00:00" here, "Z" for the model field),
    # so they are compared as moments rather than as strings.
    assert datetime.fromisoformat(body["anchored_at"]) == datetime.fromisoformat(
        body["item"]["updated_at"]
    )


def test_the_write_stamp_is_the_servers(api_harness: ApiHarness) -> None:
    """A client cannot backdate an input into looking fresher than it is."""
    response = api_harness.client.put(
        "/api/kelly-inputs/2330",
        json={
            "win_rate": 0.55,
            "payoff_ratio": 1.8,
            "updated_at": "2020-01-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 422
    assert api_harness.kelly_inputs.get("2330", "TW") is None


@pytest.mark.parametrize("win_rate", [0.0, 1.0, -0.2, 1.5])
def test_a_win_rate_outside_the_open_unit_interval_is_a_422(
    api_harness: ApiHarness, win_rate: float
) -> None:
    response = api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": win_rate, "payoff_ratio": 1.8}
    )

    assert response.status_code == 422
    assert "勝率" in response.text
    assert api_harness.kelly_inputs.get("2330", "TW") is None


@pytest.mark.parametrize("payoff_ratio", [0.0, -1.5])
def test_a_non_positive_payoff_ratio_is_a_422(
    api_harness: ApiHarness, payoff_ratio: float
) -> None:
    response = api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.55, "payoff_ratio": payoff_ratio}
    )

    assert response.status_code == 422
    assert "賠率" in response.text
    assert api_harness.kelly_inputs.get("2330", "TW") is None


def test_a_refused_write_leaves_the_stored_pair_standing(api_harness: ApiHarness) -> None:
    """約束 6: refused, not clamped -- and the previous value is not disturbed."""
    _put(api_harness.client, win_rate=0.55, payoff_ratio=1.8)

    refused = api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 1.4, "payoff_ratio": 1.8}
    )

    assert refused.status_code == 422
    assert "不會自行調整" in refused.text
    stored = api_harness.kelly_inputs.get("2330", "TW")
    assert stored is not None and stored.win_rate == 0.55


def test_an_unknown_field_is_refused(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/kelly-inputs/2330",
        json={"win_rate": 0.55, "payoff_ratio": 1.8, "source": "backtest"},
    )

    assert response.status_code == 422


def test_reading_an_input_that_was_never_entered_is_a_404(api_harness: ApiHarness) -> None:
    response = api_harness.client.get("/api/kelly-inputs/2330")

    assert response.status_code == 404
    assert "2330" in response.json()["detail"]


def test_the_market_is_part_of_the_key(api_harness: ApiHarness) -> None:
    api_harness.client.put(
        "/api/kelly-inputs/AAPL?market=US", json={"win_rate": 0.6, "payoff_ratio": 2.0}
    )

    assert api_harness.client.get("/api/kelly-inputs/AAPL?market=US").status_code == 200
    assert api_harness.client.get("/api/kelly-inputs/AAPL").status_code == 404


def test_the_symbol_is_normalised_on_the_way_in(api_harness: ApiHarness) -> None:
    body = _put(api_harness.client, symbol="aapl")

    assert body["item"]["symbol"] == "AAPL"
    assert api_harness.client.get("/api/kelly-inputs/AAPL").status_code == 200


def test_editing_an_imported_pair_keeps_the_import(api_harness: ApiHarness) -> None:
    """約束 4: the source becomes ``backtest_overridden``, the numbers survive."""
    api_harness.kelly_inputs.upsert(
        KellyInputRecord(
            symbol="2330",
            market="TW",
            win_rate=0.6,
            payoff_ratio=2.0,
            source="backtest",
            backtest_win_rate=0.6,
            backtest_payoff_ratio=2.0,
            strategy_id="ma_cross",
            oos_start_date="2025-01-02",
            oos_end_date="2026-06-30",
            oos_round_trips=24,
        )
    )

    item = _put(api_harness.client, win_rate=0.52, payoff_ratio=1.4)["item"]

    assert item["source"] == "backtest_overridden"
    assert item["win_rate"] == 0.52
    assert item["backtest_win_rate"] == 0.6
    assert item["backtest_payoff_ratio"] == 2.0
    assert item["strategy_id"] == "ma_cross"
    assert item["oos_round_trips"] == 24


def test_an_imported_row_ages_from_the_end_of_its_out_of_sample_segment(
    api_harness: ApiHarness,
) -> None:
    """D-4: anchoring on the run time would let a re-run of an old window pass."""
    oos_end = (datetime.now(UTC) - timedelta(days=45)).date().isoformat()
    api_harness.kelly_inputs.upsert(
        KellyInputRecord(
            symbol="2330",
            market="TW",
            win_rate=0.6,
            payoff_ratio=2.0,
            source="backtest",
            backtest_win_rate=0.6,
            backtest_payoff_ratio=2.0,
            strategy_id="ma_cross",
            oos_end_date=oos_end,
        )
    )

    body = api_harness.client.get("/api/kelly-inputs/2330").json()

    assert body["anchored_at"].startswith(oos_end)
    assert body["age_days"] == 45
    assert body["freshness"] == "expired"


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [
        (0, "fresh"),
        (KELLY_SOFT_NOTICE_DAYS - 1, "fresh"),
        (KELLY_SOFT_NOTICE_DAYS, "ageing"),
        (KELLY_STALE_AFTER_DAYS - 1, "ageing"),
        (KELLY_STALE_AFTER_DAYS, "expired"),
        (KELLY_STALE_AFTER_DAYS + 90, "expired"),
    ],
)
def test_a_manual_input_ages_from_its_write_stamp(
    api_harness: ApiHarness, age_days: int, expected: str
) -> None:
    api_harness.kelly_inputs.upsert(
        KellyInputRecord.manual(
            symbol="2330", market="TW", win_rate=0.55, payoff_ratio=1.8
        ),
        now=datetime.now(UTC) - timedelta(days=age_days),
    )

    body = api_harness.client.get("/api/kelly-inputs/2330").json()

    assert body["age_days"] == age_days
    assert body["freshness"] == expected


def test_an_expired_input_is_still_returned(api_harness: ApiHarness) -> None:
    """Entered long ago and never entered are different states."""
    api_harness.kelly_inputs.upsert(
        KellyInputRecord.manual(
            symbol="2330", market="TW", win_rate=0.55, payoff_ratio=1.8
        ),
        now=datetime.now(UTC) - timedelta(days=400),
    )

    response = api_harness.client.get("/api/kelly-inputs/2330")

    assert response.status_code == 200
    assert response.json()["item"]["win_rate"] == 0.55


def test_delete_clears_the_input_and_then_reports_it_gone(api_harness: ApiHarness) -> None:
    _put(api_harness.client)

    first = api_harness.client.delete("/api/kelly-inputs/2330")
    second = api_harness.client.delete("/api/kelly-inputs/2330")

    assert first.status_code == 204
    assert second.status_code == 404
    assert api_harness.client.get("/api/kelly-inputs/2330").status_code == 404


def test_delete_leaves_the_import_attempt_log_alone(api_harness: ApiHarness) -> None:
    """約束 35 / 約束 26 (7): clearing an input must not lower ``K_observed``."""
    for spec in ("a" * 64, "b" * 64):
        api_harness.kelly_attempts.append(
            KellyAttemptRecord(
                symbol="2330",
                market="TW",
                strategy_id="ma_cross",
                request_spec='{"symbol":"2330"}',
                spec_hash=spec,
                outcome="rejected",
                reason_code="low_round_trips",
            )
        )
    _put(api_harness.client)
    before = api_harness.kelly_attempts.k_observed("2330", "TW")

    assert api_harness.client.delete("/api/kelly-inputs/2330").status_code == 204

    assert before == 2
    assert api_harness.kelly_attempts.k_observed("2330", "TW") == 2
    assert api_harness.kelly_attempts.k_distinct_specs("2330", "TW") == 2


def test_the_import_endpoint_is_not_served_yet(api_harness: ApiHarness) -> None:
    """The backtest import path is a separate change; no stub stands in for it.

    A route that accepted p/b in a request body would let the backtest badge be
    attached to numbers the server never computed (約束 31).
    """
    response = api_harness.client.post(
        "/api/kelly-inputs/2330/import-backtest", json={"win_rate": 0.9}
    )

    assert response.status_code == 404
