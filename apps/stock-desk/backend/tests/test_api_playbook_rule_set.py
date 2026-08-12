"""規則集確認與資本設定入口: ``GET /rule-set`` and ``POST /confirm-rules``.

The 歸屬語情境 1 block (風控 R2) is the state a fresh book starts in: no user
record, so no rule-driven directive and the blocking sentence instead of the
歸屬語. Until these two endpoints existed the block had no exit that a user could
reach -- :meth:`PlaybookStore.confirm_rule_set` and :meth:`set_capital` had no
caller outside the tests -- which is what this suite pins:

* the read endpoint states the thresholds without adopting anything;
* the write endpoint lifts the block, and ``GET /today`` stops blocking;
* it is idempotent (no version per click) and it cannot carry a threshold, so
  鐵律④ is not routed around by re-confirming;
* the capital lands with its timestamp and its own source (CEO 裁決 D-2).

Offline by construction, like :mod:`tests.test_api_playbook`: both ladders are
:class:`tests.api_helpers.FakePriceService` instances.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_playbook_service
from app.main import app
from app.playbook import wording
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars

HISTORY = 40


@dataclass
class Harness:
    client: TestClient
    store: PlaybookStore


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    """A book **without** an authorship record -- the state a user first sees."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII"))
    service = PlaybookService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    app.dependency_overrides[get_playbook_service] = lambda: service
    with TestClient(app) as client:
        yield Harness(client=client, store=store)
    app.dependency_overrides.clear()


def test_rule_set_states_the_thresholds_without_claiming_authorship(
    harness: Harness,
) -> None:
    """讀規則集不等於採用規則集: the GET writes nothing and says so on the body."""
    body = harness.client.get("/api/playbook/rule-set").json()

    assert body["user_authored"] is False
    # A system default has a version and a date of its own; neither is the
    # user's, so neither is reported as one (裁決: 禁推斷頂替).
    assert body["rules_version"] is None
    assert body["rules_effective_date"] is None
    assert body["attribution"] == wording.ATTRIBUTION_NO_USER_RULES
    assert harness.store.rule_set_authorship(date.today()).user_authored is False
    # Reading twice still leaves no record behind.
    assert harness.client.get("/api/playbook/rule-set").json()["user_authored"] is False


def test_rule_set_sends_every_threshold_and_every_rendered_rule_sentence(
    harness: Harness,
) -> None:
    """摘要用後端下發資料渲染: 句子已渲染完成, 門檻逐欄可見."""
    body = harness.client.get("/api/playbook/rule-set").json()

    rule_ids = [item["rule_id"] for item in body["rules"]]
    assert rule_ids == list(wording.RULE_TEXT)
    # A sentence still holding a placeholder would push rendering onto the client.
    assert not [item for item in body["rules"] if "{" in item["text"]]
    texts = {item["rule_id"]: item["text"] for item in body["rules"]}
    assert texts["S1"].startswith("S1 單批停損")
    assert "×0.90" in texts["S1"]

    fields = {item["field"]: item["value"] for item in body["params"]}
    assert fields["s1_ratio"] == "0.90"
    assert fields["r3_max_defers"] == "3"
    assert fields["emergency_freeze_trading_days"] == "20"
    # 版本與生效日是來源資訊, 由專屬欄位 fail-closed 地回答, 不混進門檻清單。
    assert "version" not in fields
    assert "effective_date" not in fields


def test_today_blocks_until_the_rule_set_is_confirmed(harness: Harness) -> None:
    """歸屬語情境 1: 確認前不產生規則驅動指令, 且模式自成一態."""
    body = harness.client.get("/api/playbook/today").json()

    assert body["mode"] == "unconfirmed"
    assert body["attribution"] == wording.ATTRIBUTION_NO_USER_RULES
    assert body["directives"] == []


def test_confirming_lifts_the_block_and_records_the_capital(harness: Harness) -> None:
    """確認後: authorship 成立、資本落 timestamp+source、/today 不再阻斷."""
    response = harness.client.post(
        "/api/playbook/confirm-rules", json={"capital": "1000000"}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["user_authored"] is True
    assert body["rules_version"] == 1
    assert body["rules_effective_date"] == date.today().isoformat()
    assert body["attribution"] == wording.ATTRIBUTION_NOTE.format(
        RULE_SET_DATE=date.today().isoformat()
    )
    # TOTAL_DEPLOY = 資本額 × deploy_ratio of the version in force (CEO 裁決一).
    assert Decimal(body["cash"]) == Decimal("1000000")
    assert Decimal(body["total_deploy"]) == Decimal("700000.00")
    assert body["total_deploy_source"] == "user_confirmation"
    assert body["total_deploy_set_at"] is not None

    state = harness.store.portfolio_state()
    assert state.total_deploy_set_at is not None
    assert state.total_deploy_source == "user_confirmation"
    assert harness.store.rule_set_authorship(date.today()).user_authored is True

    after = harness.client.get("/api/playbook/today").json()
    assert after["mode"] != "unconfirmed"
    assert after["attribution"] != wording.ATTRIBUTION_NO_USER_RULES
    assert after["rules_effective_date"] == date.today().isoformat()


def test_deploy_ratio_pct_is_rendered_from_the_active_deploy_ratio(
    harness: Harness,
) -> None:
    """④ 資金用途句的比例由後端渲染: 渲染數字 == active_params, 且自帶 %."""
    body = harness.client.get("/api/playbook/rule-set").json()

    active = harness.store.active_params(date.today())
    assert body["deploy_ratio_pct"] == wording.ratio_pct(active.deploy_ratio) + "%"
    assert body["deploy_ratio_pct"] == "70%"
    # The client substitutes this string as it stands: no scaling on the client
    # (the ratio itself is never sent for this sentence) and no unit of its own.
    assert not body["deploy_ratio_pct"].startswith("0.")
    # 確認之後仍是同一支換算, 不會因為寫入而漂掉。
    after = harness.client.post(
        "/api/playbook/confirm-rules", json={"capital": "1000000"}
    ).json()
    assert after["deploy_ratio_pct"] == body["deploy_ratio_pct"]


def test_confirming_twice_adds_no_rule_version(harness: Harness) -> None:
    """冪等: 重複送出不會一次一版把規則集往前推, 資本仍逐次落檔."""
    first = harness.client.post(
        "/api/playbook/confirm-rules", json={"capital": "1000000"}
    ).json()
    second = harness.client.post(
        "/api/playbook/confirm-rules", json={"capital": "1200000"}
    ).json()

    assert second["rules_version"] == first["rules_version"] == 1
    assert second["rules_effective_date"] == first["rules_effective_date"]
    assert harness.store.next_version() == 2  # exactly one row was ever written
    # The capital entry point stays open: the later figure replaces the earlier
    # one and carries its own timestamp and source, rather than being ignored.
    assert Decimal(second["cash"]) == Decimal("1200000")
    assert Decimal(second["total_deploy"]) == Decimal("840000.00")
    assert harness.store.portfolio_state().total_deploy_source == "user_confirmation"


def test_a_confirmation_cannot_carry_a_threshold_change(harness: Harness) -> None:
    """鐵律④: 確認只是採用「現行」規則集, 送門檻進來也不會被採用."""
    body = harness.client.post(
        "/api/playbook/confirm-rules",
        json={"capital": "1000000", "s1_ratio": "0.50", "r3_max_defers": 99},
    ).json()

    fields = {item["field"]: item["value"] for item in body["params"]}
    assert fields["s1_ratio"] == "0.90"
    assert fields["r3_max_defers"] == "3"
    assert harness.store.active_params(date.today()).s1_ratio == Decimal("0.90")


@pytest.mark.parametrize("capital", ["0", "-1"])
def test_a_non_positive_capital_is_refused(harness: Harness, capital: str) -> None:
    """資本額必須為正數: 0 或負數不是這套規則集能運作的帳本."""
    response = harness.client.post(
        "/api/playbook/confirm-rules", json={"capital": capital}
    )

    assert response.status_code == 422
    assert harness.store.rule_set_authorship(date.today()).user_authored is False
