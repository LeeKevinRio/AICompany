"""Plan D: new Kelly input is frozen on the server (CEO #62, 2026-10-26).

Pins risk review 2026-10-26 condition D-1 against the default harness, which is
what production serves: manual ``PUT`` and ``import-backtest`` refuse with the
sunset table's ``detail`` and write nothing (the import not even an attempt),
``DELETE`` and every read stay open (第1條下修告知逐字審 實作約束 7(b)), inputs
already stored keep feeding cap 5, and the process-wide store refuses
``upsert`` as a second layer.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.api import deps
from app.api.kelly_wording import KELLY_IMPORT_PAUSED_DETAIL, KELLY_WRITES_PAUSED_LABEL
from app.kelly.freeze import KELLY_INPUT_WRITES_FROZEN, KellyInputWritesFrozenError
from app.kelly.models import KellyInputRecord
from app.kelly.store import KellyInputStore
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness


def _seed_pair(harness: ApiHarness, symbol: str = "2330") -> None:
    """An input stored before the freeze, written straight to the test store."""
    harness.kelly_inputs.upsert(
        KellyInputRecord.manual(symbol=symbol, market="TW", win_rate=0.6, payoff_ratio=2.0)
    )


def _import_body() -> dict[str, object]:
    end = date(2026, 10, 1)
    return {
        "symbol": "2330",
        "market": "TW",
        "strategy": "breakout",
        "start": (end - timedelta(days=400)).isoformat(),
        "end": end.isoformat(),
        "train_size": 120,
        "test_size": 60,
    }


def test_the_freeze_is_on() -> None:
    assert KELLY_INPUT_WRITES_FROZEN is True
    assert deps.get_kelly_input_writes_frozen() is True


def test_a_manual_write_is_refused_and_writes_nothing(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.55, "payoff_ratio": 1.8}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": KELLY_WRITES_PAUSED_LABEL}
    assert KELLY_WRITES_PAUSED_LABEL == "已暫停"
    assert api_harness.kelly_inputs.list_all() == []


def test_a_manual_write_over_a_stored_pair_leaves_it_standing(api_harness: ApiHarness) -> None:
    _seed_pair(api_harness)
    before = api_harness.kelly_inputs.get("2330", "TW")

    response = api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.4, "payoff_ratio": 1.1}
    )

    assert response.status_code == 409
    assert api_harness.kelly_inputs.get("2330", "TW") == before


def test_an_import_is_refused_before_it_is_logged_as_an_attempt(api_harness: ApiHarness) -> None:
    response = api_harness.client.post(
        "/api/kelly-inputs/2330/import-backtest", json=_import_body()
    )

    assert response.status_code == 409
    assert response.json() == {"detail": KELLY_IMPORT_PAUSED_DETAIL}
    assert KELLY_IMPORT_PAUSED_DETAIL == "暫停從回測帶入。"
    assert api_harness.kelly_attempts.k_observed("2330", "TW") == 0
    assert api_harness.kelly_inputs.list_all() == []


def test_delete_still_removes_a_stored_pair(api_harness: ApiHarness) -> None:
    """實作約束 7(b): the freeze does not reach DELETE, so「刪除仍可使用」holds."""
    _seed_pair(api_harness)

    response = api_harness.client.delete("/api/kelly-inputs/2330")

    assert response.status_code == 204
    assert api_harness.kelly_inputs.get("2330", "TW") is None


def test_reads_stay_open_and_name_the_paused_controls(api_harness: ApiHarness) -> None:
    _seed_pair(api_harness)

    assert api_harness.client.get("/api/kelly-inputs/2330").status_code == 200
    body = api_harness.client.get("/api/kelly-inputs/2330/disclosures").json()
    assert body["kelly_input"] is not None
    assert body["disclosures"]["writes_paused_label"] == KELLY_WRITES_PAUSED_LABEL
    # The import trigger's own label is unchanged; the front end shows the
    # paused label in its place while this field is set.
    assert body["disclosures"]["import_trigger_label"] == "執行回測並帶入"


def test_with_nothing_stored_the_controls_are_still_named_paused(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/kelly-inputs/2330/disclosures").json()
    assert body["kelly_input"] is None
    assert body["disclosures"]["writes_paused_label"] == KELLY_WRITES_PAUSED_LABEL


@pytest.mark.usefixtures("kelly_writes_open")
def test_with_writes_open_the_paused_label_is_absent(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/kelly-inputs/2330/disclosures").json()
    assert body["disclosures"]["writes_paused_label"] is None


def test_a_stored_pair_keeps_feeding_cap_5_during_the_sunset(api_harness: ApiHarness) -> None:
    """D: existing inputs keep participating until each expires."""
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    _seed_pair(api_harness)

    body = api_harness.client.get("/api/advice/2330").json()

    (check,) = [c for c in body["advice"]["limits_check"] if c["id"] == "kelly_fraction"]
    assert check["status"] in {"passed", "violated"}
    assert check["threshold"] == pytest.approx(0.1)


def test_a_store_built_refusing_writes_refuses_upsert_but_not_delete(tmp_path: Path) -> None:
    open_store = KellyInputStore(tmp_path / "kelly.db")
    open_store.upsert(
        KellyInputRecord.manual(symbol="2330", market="TW", win_rate=0.6, payoff_ratio=2.0)
    )
    frozen = KellyInputStore(tmp_path / "kelly.db", accept_writes=False)

    with pytest.raises(KellyInputWritesFrozenError):
        frozen.upsert(
            KellyInputRecord.manual(symbol="2317", market="TW", win_rate=0.5, payoff_ratio=1.5)
        )
    assert frozen.get("2317", "TW") is None
    assert frozen.get("2330", "TW") is not None
    assert frozen.delete("2330", "TW") is True


def test_the_process_wide_store_refuses_upsert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second layer of D-1: production's store, not only the routes."""
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(tmp_path / "stock-desk.db"))
    deps._default_kelly_input_store.cache_clear()
    try:
        store = deps.get_kelly_input_store()
        with pytest.raises(KellyInputWritesFrozenError):
            store.upsert(
                KellyInputRecord.manual(symbol="2330", market="TW", win_rate=0.6, payoff_ratio=2.0)
            )
    finally:
        deps._default_kelly_input_store.cache_clear()
