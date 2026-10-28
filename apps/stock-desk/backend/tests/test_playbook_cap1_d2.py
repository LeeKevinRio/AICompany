"""Revised D-2 (CEO #68): cap 1 does not constrain the 排程台, and says so.

風控 2026-10-28 #68 裁決（D-2 修訂／N-155 揭露規格）, 第 2.4 節, and its follow-up
(``2026-10-28-#68裁決補充-R4解讀與出貨方式-風控.md`` 第 4、5 節):

* 測試 ② -- the directives ``evaluate_today`` produces are identical whatever
  cap 1 is set to (0.05 or 0.50). Revised D-2 (2) is in force from batch one,
  so it needs a test now; a clamp added later turns this red.
* 測試 ③ -- the conflict disclosure (N-155) is present, verbatim, in the
  ``cap1_disclosure`` field of the ``/today`` and ``/rule-set`` responses.
  Landed on ``fix/stock-desk-playbook-cap1-disclosure`` (ADR-0031, CEO #69),
  which removed the strict-xfail placeholder in the same PR as the ruling
  required; the full matrix (B-2: every mode, every endpoint, n_targets 11 / 7
  / 5 against cap 1 at 10% and 25%) is ``tests/test_api_playbook_cap1_disclosure.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.advice.limits import RiskBudget
from app.api import deps
from app.api.deps import get_playbook_service
from app.main import app
from app.playbook.models import RuleParams
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from app.settings.models import AppSettings
from app.settings.store import SettingsStore
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.playbook_helpers import batch as make_batch
from tests.playbook_helpers import confirm_rule_set

#: A Thursday trading day: a 排程日, so the rule set issues entries as well as
#: exits and the shares of both kinds are compared.
EVALUATION_DAY = date(2026, 8, 13)
HISTORY = 40

Line = tuple[str, int | None, str, int]


def _seed_playbook(db: Path) -> PlaybookService:
    """One fixed book: a stop-loss, a take-profit, two entries and a deferral."""
    store = PlaybookStore(db_path=db)
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=EVALUATION_DAY))
    store.ensure_batches(["2330", "2317", "2454"], batches_per_target=3)
    store.save_batch(make_batch(cost="100", shares=300))
    store.save_batch(make_batch(symbol="2454", cost="100", shares=300))
    prices.seed(
        "2330", recent_bars([100.0] * (HISTORY - 1) + [85.0], symbol="2330", end=EVALUATION_DAY)
    )
    prices.seed("2317", recent_bars([100.0] * HISTORY, symbol="2317", end=EVALUATION_DAY))
    prices.seed(
        "2454", recent_bars([100.0] * (HISTORY - 1) + [121.0], symbol="2454", end=EVALUATION_DAY)
    )
    store.set_capital(cash=Decimal("1000000"), total_deploy=Decimal("700000"), source="initial")
    return PlaybookService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )


def _lines_with_cap1(root: Path, cap1: float, monkeypatch: pytest.MonkeyPatch) -> list[Line]:
    """Evaluate the fixed book with cap 1 stored at ``cap1``, where production reads it.

    The settings are written into the same database file the playbook uses, and
    ``STOCK_DESK_DB_PATH`` points there, so a playbook path that started reading
    the risk budget -- directly or through ``app.api.deps`` -- would see it.
    """
    root.mkdir()
    db = root / "stock-desk.db"
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))
    deps._default_settings_store.cache_clear()
    try:
        SettingsStore(db).save(AppSettings(risk_budget=RiskBudget(max_position_weight=cap1)))
        assert deps.get_settings_store().load().risk_budget.max_position_weight == cap1
        evaluation = _seed_playbook(db).evaluate_today(today=EVALUATION_DAY)
    finally:
        deps._default_settings_store.cache_clear()
    return [(d.symbol, d.batch_no, d.action, d.shares) for d in evaluation.directives]


def test_the_directives_do_not_depend_on_the_cap_1_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """修訂 D-2 (5) 測試 ②: cap 1 at 0.05 and at 0.50 yields the same lines."""
    tight = _lines_with_cap1(tmp_path / "cap-005", 0.05, monkeypatch)
    loose = _lines_with_cap1(tmp_path / "cap-050", 0.50, monkeypatch)

    assert tight == loose
    # Not vacuous: buys sized by the rule set, sells, and a deferral, each
    # carrying a share count the comparison covers.
    actions = {action for _, _, action, _ in tight}
    assert {"buy", "sell"} <= actions
    assert any(shares > 0 for _, _, action, shares in tight if action == "buy")


# --- 測試 ③: the disclosure is present, verbatim, in its own field ------------------

#: The stored cap-1 value: not the 10% default, so a disclosure that read the
#: default instead of the store would not match.
STORED_CAP1 = 0.12

#: 風控 2026-10-28 #68 裁決補充 第 4 節 定稿, filled with the default rule set
#: (70%, 5, 3 -> 約 14% of total assets, 約 20% of the book) and the stored cap 1.
#: Percentages follow that section's rule: Decimal, ROUND_HALF_UP to one place,
#: a trailing ``.0`` dropped, then ``%``; the slots never carry 「約」.
DISCLOSURE_TITLE = "排程台每檔規模與第 1 條上限"
DISCLOSURE_LINES = (
    "依此規則集的參數（部署比例 70%、5 檔均分、每檔分 3 批），每檔標的的預定投入金額為 "
    "TOTAL_DEPLOY ÷ 5，約為計算 TOTAL_DEPLOY 當時排程台總資產（含現金）的 14%；實際股數依"
    "各批進場時的收盤價換算，實際成本與日後市值的佔比可能與此數不同。",
    "第 1 條・單一標的佔比上限目前設定為 12%，分母是庫存的已估值部位市值（不含現金，即設定頁"
    "所稱的「總資產」）。排程台與庫存是兩套獨立帳冊，上述兩個百分比的分母不同，不能直接比較大小。",
    "如果你也把排程台的持股記入庫存，第 1 條會以庫存的分母計算這些持股的佔比：例如庫存只有排程台"
    "的 5 檔且各檔市值相同時，每檔約佔 20%；達到或超過第 1 條設定值時，個股頁會顯示該檔已達或"
    "超過上限。",
    "排程台計算股數時不讀取第 1 條或其他任何一條風險上限的設定，也不會因這些上限調整任何一批的"
    "股數；兩邊各自計算，本系統不會自動調和兩者的結果。",
)


@dataclass
class _Client:
    client: TestClient


@pytest.fixture
def disclosure_client(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_Client]:
    confirmed: bool = request.param
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    if confirmed:
        confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII"))
    service = PlaybookService(
        store=store, market_resolver={"TW": prices}, index_resolver={"TW": index, "US": index}
    )
    settings = SettingsStore(tmp_path / "settings.db")
    settings.save(AppSettings(risk_budget=RiskBudget(max_position_weight=STORED_CAP1)))
    app.dependency_overrides[get_playbook_service] = lambda: service
    # The real ``deps.get_cap1_weight`` reads the process-wide store; point that
    # store at this test's settings rather than overriding the dependency.
    monkeypatch.setattr(deps, "_default_settings_store", lambda: settings)
    with TestClient(app, headers=CLIENT_HEADERS) as client:
        yield _Client(client=client)
    app.dependency_overrides.clear()


def test_the_expected_disclosure_uses_the_default_rule_set() -> None:
    """The numbers written into ``DISCLOSURE_LINES`` are the defaults' (not a guess)."""
    params = RuleParams(effective_date=date(2026, 1, 1))
    assert params.deploy_ratio == Decimal("0.70")
    assert (params.n_targets, params.batches_per_target) == (5, 3)
    assert params.deploy_ratio / params.n_targets == Decimal("0.14")
    assert Decimal(1) / params.n_targets == Decimal("0.2")


@pytest.mark.parametrize(
    ("disclosure_client", "path"),
    [(True, "/api/playbook/today"), (False, "/api/playbook/rule-set")],
    indirect=["disclosure_client"],
    ids=["today-confirmed", "rule-set-unconfirmed"],
)
def test_the_conflict_disclosure_is_served_verbatim(disclosure_client: _Client, path: str) -> None:
    """修訂 D-2 (5) 測試 ③: title and ①～④, verbatim, in ``cap1_disclosure``."""
    response = disclosure_client.client.get(path)
    assert response.status_code == 200
    body = response.json()
    disclosure = body["cap1_disclosure"]
    assert disclosure["title"] == DISCLOSURE_TITLE
    assert disclosure["lines"] == list(DISCLOSURE_LINES)
    assert (disclosure["per_target_pct"], disclosure["cap1_pct"]) == ("14%", "12%")
    assert disclosure["per_target_book_pct"] == "20%"
    # In its own field only: not folded into the §6 sentences or the warnings.
    rest = {key: value for key, value in body.items() if key != "cap1_disclosure"}
    assert DISCLOSURE_TITLE not in json.dumps(rest, ensure_ascii=False)
