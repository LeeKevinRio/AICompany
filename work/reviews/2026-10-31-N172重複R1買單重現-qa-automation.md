# N-172（F5）排程日重複評估重複寫入 R1 買單重現

- 審查者：qa-automation
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**N-172（F5）重現成立。** 推定現象與實測完全一致，目前沒有任何去重機制。

- 在排程日（週二）重複評估，同一批次（2330 第 1 批）每呼叫一次就多寫一列 R1 buy。
- T+1（週三）結算時，每一列都各自成交。批次 `shares` 只有一次的量（666），帳冊現金卻被扣 N 次。
- 對照組（非排程日重跑、結算後重跑）不重複。重複只發生在「排程日當天、批次仍是 planned、買單尚未到期結算」的窗口。
- 去重機制不存在。我查過以下幾處，都沒有擋重複：
  - `playbook_directives` 沒有 UNIQUE 約束（`store.py:129` 起的 CREATE TABLE，grep UNIQUE 無結果）。
  - `record_directives`（`store.py:784-824`）每次無條件 INSERT。
  - `record_schedule`（`store.py:759-782`）每次無條件 INSERT。這點只從讀碼確認，沒有量測 `playbook_schedule` 的列數。
  - `evaluate_today`（`service.py:614-685`）沒有「當日已評估」判斷。
  - 引擎只看 `batch.status == "planned"`（`engine.py:699-711`）。
  - `claim_directive`（`store.py:883-898`）只防「同一列被結算兩次」，不防「同一批次有兩列」。
  - `settle_pending`（`service.py:272-301`）對每一列各自 claim、各自 `settle`，不看批次是否已被前一列成交。
- 唯一的防重放是 `claim_directive` 的 `settled = 0` 條件，作用在列層級而非批次層級。這正是現有測試 `test_settling_twice_does_not_deduct_twice` 沒抓到的原因。

## 各部門回報

- **qa-automation（本人）**
  - 寫了一支重現測試，放 scratchpad，**未 commit**。
  - 沒有修任何產品 code。
  - DB 用 `tmp_path`，沒碰 `data/*.db`，沒讀 `.env`，沒打外網。
  - 工作樹 `wt-n172` 已用 `git worktree remove --force` 移除，`git worktree list` 已確認不在清單內。
  - 工作樹內的 `.venv` 是 `uv run --frozen` 建的，隨工作樹一併移除。
  - 主 repo 的 `git status` 顯示 `work/prd/2026-10-29-出清後回饋畫面-N164N165.md` 有修改。這不是我改的。
- **證據來源版本**：`origin/product/stock-desk` = `e5948fd`。
- **HTTP 路徑的時鐘固定方式**：`GET /today` 路由呼叫 `service.evaluate_today()` 時沒帶日期，會用真實時鐘（2026-10-31 是週六）。
  - 測試用 `ClockedService` 子類只補預設 `today`，其餘全是正式 code。
  - 路由與回應 mapping 都走正式程式。
  - 這是測試手法，不是產品行為。

## 驗證

### 實測值

測試設定：2330，全程收盤與開盤皆 100，資金 1,000,000。「只買一次」的預期是 666 股、扣 66,600，現金 933,400。這與 `test_playbook_settlement.py` 的既有數字一致。

| 情境 | 實測 |
|---|---|
| 週二 `evaluate_today` 呼叫 1 次後，R1 buy 列數 / pending 數 | 1 / 1 |
| 週二呼叫 2 次後，R1 buy 列數 / pending 數 | 2 / 2 |
| 結算前批次狀態 / 現金 | `planned` / 1,000,000 |
| 週三結算 `executed` / `missed` | 2 / 0 |
| 兩列結算後狀態 | id 1、id 2 皆 `executed`、`settled=1`、shares 666 |
| 批次 `shares` / `remaining_shares` / `status` | 666 / 666 / `open` |
| 現金 | 866,800（預期 933,400，多扣 66,600） |
| 帳冊隱含股數（扣款 133,200 ÷ 100） | 1,332 股，批次只記 666 股 |
| 週二連續呼叫 5 次，列數 | [1, 2, 3, 4, 5] |
| 5 次呼叫後週三結算 `executed` | 5 |
| 5 次呼叫後批次 `shares` | 666 |
| 5 次呼叫後現金 | 667,000，扣 333,000 = 5.0 倍單次扣款 |
| HTTP：`GET /today` 連續 3 次，DB 列數 | [1, 2, 3] |
| HTTP：每次回應 body 內的 R1 buy 行數 | [1, 1, 1] |
| HTTP：週三 `GET /today` 的 `settlement.executed` | 3 |
| HTTP：批次 `shares` / `status` | 666 / `open` |
| HTTP：現金 | 800,200，扣 199,800 = 3 倍 |
| 對照：週一（非排程日）重跑 3 次，R1 列數 / pending | 0 / 0 |
| 對照：週二 1 次、週三結算後再重跑週三 2 次，列數 / 現金 | 1 / 933,400（重跑前後不變） |
| 對照：單次呼叫 | 1 列 / 666 股 / 現金 933,400 |

觀察：
- 呼叫 N 次，列數與扣款都是 N 倍，呈線性成長。
- 單看回應 body，使用者每次只看到 1 行 R1，看不出重複。重複只存在 DB（`playbook_directives`、pending、`/today` 的 `settlement`）。
- `shares` 欄位沒有被加總，所以批次 `shares` 與現金扣款在帳上互相對不起來。
- 風險面：現金扣兩次，鐵律①（現金餘額）會讀到偏低的值。

### 前端 react-query 何時重複觸發 `/today`

依據：
- `frontend/app/lib/queries.ts:411-418`：`usePlaybookToday` 只設 `queryKey: ["playbook-today"]`、`enabled`、`retry: 1`。沒有設 `staleTime`、`refetchOnWindowFocus`、`refetchInterval`。
- `frontend/app/providers.tsx:8`：`new QueryClient()`，沒有 defaultOptions。
- `frontend/next.config.ts:14`：`reactStrictMode: true`。

react-query 預設值是 `staleTime: 0`、`refetchOnWindowFocus: true`、`refetchOnMount: true`、`refetchOnReconnect: true`。以下情境會重打 `/today`：

1. **視窗或分頁重新取得焦點**：資料立刻視為 stale，每次切回分頁都會再打一次。
2. **元件重新掛載**：離開 `/playbook` 再回來，會 refetch。
3. **網路重連**：會 refetch。
4. **`useConfirmPlaybookRules` 成功**（`queries.ts:440-448`）：`invalidateQueries(["playbook-today"])`。
5. **`useEmergencyExit` 成功**（`queries.ts:457-463`）：同上。
6. **開發模式下 StrictMode 的 effect 雙跑**：我是依預設行為推論的，沒有實機量測。
7. **多個分頁或多個視窗**：各自獨立觸發。
8. **`retry: 1`**：請求失敗時會自動重試一次。這只在後端先寫入、後回 5xx 的情況下才會多寫一輪。這點我沒有重現，只是依 `retry: 1` 的設定列出。

結論：使用者在週二當天切換分頁、切回、換分頁，每次都會多寫一列。這是「正常使用就會觸發」，不需要特殊操作。

以上是讀碼與預設值推論，沒有跑前端。我沒有量測實際打了幾次。

### pytest 原文輸出

指令：`cd <worktree>/apps/stock-desk/backend && .venv/bin/python -m pytest <scratchpad>/test_n172_repro.py -p no:cacheprovider -rA -s -q --rootdir=.`

（以下是我最後一次完整跑的輸出，把 traceback 內的 `E` 行與 locals 行略去，只保留 `FAILED` 摘要。）

```
FF
[OBSERVE 2 calls] R1 buy rows after call 1: 1
[OBSERVE 2 calls] R1 buy rows after call 2: 2
[OBSERVE 2 calls] pending after call 1/2: 1 2
[OBSERVE 2 calls] batch status before settle: planned
[OBSERVE 2 calls] cash before settle: 1000000
[OBSERVE 2 calls] Wednesday executed/missed: 2 0
[OBSERVE 2 calls] rows after settle (id, shares, status, settled): [(1, 666, 'executed', 1), (2, 666, 'executed', 1)]
[OBSERVE 2 calls] batch shares/remaining/status: 666 666 open
[OBSERVE 2 calls] cash: 866800.0  expected-if-once: 933400  deducted: 133200.0  ledger-implied shares: 1332.0
.
[OBSERVE N calls] R1 rows after calls 1..5: [1, 2, 3, 4, 5]
[OBSERVE N calls] Wednesday executed: 5
[OBSERVE N calls] batch shares: 666  cash: 667000.0  deducted: 333000.0  multiple of one buy: 5.0
.F
[OBSERVE HTTP] R1 buy rows in DB after GET 1..3: [1, 2, 3]
[OBSERVE HTTP] R1 buy lines inside each response body: [1, 1, 1]
[OBSERVE HTTP] Wednesday settlement executed: 3
[OBSERVE HTTP] batch shares/status: 666 open  cash: 800200.0  deducted: 199800.0
....
=================================== FAILURES ===================================
_________________ test_schedule_day_replay_expected_one_r1_row _________________
../../../../test_n172_repro.py:110: AssertionError   (assert 2 == 1)
________________ test_t_plus_1_expected_book_equals_single_buy _________________
../../../../test_n172_repro.py:122: AssertionError   (assert Decimal('866800.0') == (Decimal('1000000') - Decimal('66600')))
____________________ test_get_today_twice_expected_one_row _____________________
../../../../test_n172_repro.py:203: AssertionError   (assert 2 == 1)
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED ::test_observe_rows_and_book_after_two_calls
PASSED ::test_observe_rows_grow_one_per_extra_call
PASSED ::test_observe_get_today_rows_and_book
PASSED ::test_control_non_schedule_day_replay_writes_no_r1
PASSED ::test_control_replay_after_settlement_does_not_duplicate
PASSED ::test_control_single_tuesday_call_is_correct
FAILED ::test_schedule_day_replay_expected_one_r1_row - AssertionError: asser...
FAILED ::test_t_plus_1_expected_book_equals_single_buy - AssertionError: asse...
FAILED ::test_get_today_twice_expected_one_row - AssertionError: assert 2 == 1
3 failed, 6 passed, 1 warning in 4.81s
```

後續再跑一次只看摘要，結果相同：`3 failed, 6 passed, 1 warning in 1.61s`。

另外，基準確認：同一份 worktree 上既有的 `tests/test_playbook_settlement.py` 為 `10 passed in 0.47s`，所以環境與 fixture 沒問題。

- **3 個 FAILED**：這是刻意的。它們斷言「正確行為（只買一次）」，缺陷存在時就會紅，我沒有弱化斷言。
- **6 個 PASSED**：3 個 `observe`（釘住並印出現在這個有缺陷的實測值）加 3 個 `control`（對照組）。
- 修好 F5 之後，3 個 `expected` 測試會轉綠，3 個 `observe` 測試會轉紅（它們釘的是缺陷值）。
- 轉成正式測試時，`observe` 三支應該改寫或刪除。

### 測試檔

路徑：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/test_n172_repro.py`

這個檔案依賴 `app.*` 與 `tests.api_helpers`、`tests.playbook_helpers`，需要在 `apps/stock-desk/backend` 目錄下以專案的 venv 執行（`uv run --frozen python -m pytest <檔案路徑> ...`）。完整內容如下：

```python
"""N-172 / F5 reproduction: repeated evaluation on a schedule day re-issues R1 buys.

Scratch file, NOT part of the repo. Run from ``apps/stock-desk/backend``::

    python -m pytest <this file> -p no:cacheprovider -rA -s

Structure
---------
* ``test_*_expected_*``      assert the CORRECT behaviour ("buy once"). They FAIL
                             while the defect exists. No assertion is weakened.
* ``test_observe_*``         pin the OBSERVED numbers (they pass while the defect
                             exists) and print them, so the report quotes
                             measured values rather than estimates.
* ``test_control_*``         non-schedule-day / already-settled replays. These must
                             pass: they show where duplication does NOT happen.

Offline: fake price services, DB under ``tmp_path``, every call pins ``today``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_weight, get_playbook_service
from app.main import app
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.playbook_helpers import confirm_rule_set

SERIES_END = date(2026, 8, 14)  # Friday
MONDAY = date(2026, 8, 10)  # not a schedule day
TUESDAY = date(2026, 8, 11)  # schedule day (T)
WEDNESDAY = date(2026, 8, 12)  # T+1, not a schedule day
HISTORY = 40

START_CASH = Decimal("1000000")
ONE_BUY_SHARES = 666  # same figure as tests/test_playbook_settlement.py
ONE_BUY_COST = Decimal("100") * ONE_BUY_SHARES  # 66,600


class ClockedService(PlaybookService):
    """Pins the clock for the HTTP path only.

    ``GET /today`` calls ``service.evaluate_today()`` with no argument, i.e. the
    real clock (2026-10-31 is a Saturday). This subclass supplies the default
    ``today`` and changes nothing else; the route, response mapping and every
    store call are production code.
    """

    pinned: date = TUESDAY

    def evaluate_today(self, *, today: date | None = None):  # type: ignore[override]
        return super().evaluate_today(today=today or self.pinned)


@dataclass
class Harness:
    service: ClockedService
    store: PlaybookStore
    prices: FakePriceService


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(cash=START_CASH, total_deploy=Decimal("1000000"), source="initial")
    service = ClockedService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    yield Harness(service=service, store=store, prices=prices)


def r1_buys(h: Harness, batch_no: int = 1) -> list[dict]:
    return [
        row
        for row in h.store.directive_log()
        if row["rule_id"] == "R1" and row["action"] == "buy" and row["batch_no"] == batch_no
    ]


def book(h: Harness) -> tuple[int, int, str, Decimal]:
    batch = h.store.get_batch("2330", 1)
    assert batch is not None
    return batch.shares, batch.remaining_shares, batch.status, h.store.portfolio_state().cash


# --- service level: evaluate_today -------------------------------------------


def test_schedule_day_replay_expected_one_r1_row(harness: Harness) -> None:
    """Expected: two evaluations on Tuesday queue ONE R1 buy for batch 1."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=TUESDAY)
    assert len(r1_buys(harness)) == 1


def test_t_plus_1_expected_book_equals_single_buy(harness: Harness) -> None:
    """Expected: after Wednesday settlement the book equals a single buy."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)  # /today settles first

    shares, _remaining, status, cash = book(harness)
    assert status == "open"
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - ONE_BUY_COST


def test_observe_rows_and_book_after_two_calls(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    harness.service.evaluate_today(today=TUESDAY)
    rows_after_1 = len(r1_buys(harness))
    pending_after_1 = len(harness.store.pending_directives())
    harness.service.evaluate_today(today=TUESDAY)
    rows_after_2 = len(r1_buys(harness))
    pending_after_2 = len(harness.store.pending_directives())
    batch_before_settle = harness.store.get_batch("2330", 1)
    assert batch_before_settle is not None
    cash_before_settle = harness.store.portfolio_state().cash

    wed = harness.service.evaluate_today(today=WEDNESDAY)
    assert wed.settlement is not None
    shares, remaining, status, cash = book(harness)
    after_settle_rows = [
        (r["id"], r["shares"], r["status"], r["settled"]) for r in r1_buys(harness)
    ]
    with capsys.disabled():
        print("\n[OBSERVE 2 calls] R1 buy rows after call 1:", rows_after_1)
        print("[OBSERVE 2 calls] R1 buy rows after call 2:", rows_after_2)
        print("[OBSERVE 2 calls] pending after call 1/2:", pending_after_1, pending_after_2)
        print("[OBSERVE 2 calls] batch status before settle:", batch_before_settle.status)
        print("[OBSERVE 2 calls] cash before settle:", cash_before_settle)
        print("[OBSERVE 2 calls] Wednesday executed/missed:", wed.settlement.executed,
              wed.settlement.missed)
        print("[OBSERVE 2 calls] rows after settle (id, shares, status, settled):",
              after_settle_rows)
        print("[OBSERVE 2 calls] batch shares/remaining/status:", shares, remaining, status)
        print("[OBSERVE 2 calls] cash:", cash, " expected-if-once:", START_CASH - ONE_BUY_COST,
              " deducted:", START_CASH - cash, " ledger-implied shares:",
              (START_CASH - cash) / Decimal("100"))
    # Pin the observed (defective) outcome.
    assert (rows_after_1, rows_after_2) == (1, 2)
    assert (pending_after_1, pending_after_2) == (1, 2)
    assert wed.settlement.executed == 2
    assert (shares, remaining, status) == (ONE_BUY_SHARES, ONE_BUY_SHARES, "open")
    assert cash == START_CASH - 2 * ONE_BUY_COST


def test_observe_rows_grow_one_per_extra_call(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    counts = []
    for _ in range(5):
        harness.service.evaluate_today(today=TUESDAY)
        counts.append(len(r1_buys(harness)))
    wed = harness.service.evaluate_today(today=WEDNESDAY)
    assert wed.settlement is not None
    shares, _remaining, _status, cash = book(harness)
    with capsys.disabled():
        print("\n[OBSERVE N calls] R1 rows after calls 1..5:", counts)
        print("[OBSERVE N calls] Wednesday executed:", wed.settlement.executed)
        print("[OBSERVE N calls] batch shares:", shares, " cash:", cash,
              " deducted:", START_CASH - cash, " multiple of one buy:",
              (START_CASH - cash) / ONE_BUY_COST)
    assert counts == [1, 2, 3, 4, 5]
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - 5 * ONE_BUY_COST


# --- HTTP level: GET /api/playbook/today -------------------------------------


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: harness.service
    app.dependency_overrides[get_cap1_weight] = lambda: Decimal("0.10")
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_today_twice_expected_one_row(harness: Harness, client: TestClient) -> None:
    """Expected: two ``GET /today`` on Tuesday queue ONE R1 buy."""
    assert client.get("/api/playbook/today").status_code == 200
    assert client.get("/api/playbook/today").status_code == 200
    assert len(r1_buys(harness)) == 1


def test_observe_get_today_rows_and_book(
    harness: Harness, client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    body_rows = []
    counts = []
    for _ in range(3):
        response = client.get("/api/playbook/today")
        assert response.status_code == 200
        body = response.json()
        counts.append(len(r1_buys(harness)))
        body_rows.append(
            len(
                [
                    d
                    for d in body["directives"]
                    if d["directive"]["rule_id"] == "R1" and d["directive"]["action"] == "buy"
                ]
            )
        )
    # T+1: Wednesday's GET /today settles then evaluates.
    harness.service.pinned = WEDNESDAY
    wed_body = client.get("/api/playbook/today").json()
    shares, _remaining, status, cash = book(harness)
    with capsys.disabled():
        print("\n[OBSERVE HTTP] R1 buy rows in DB after GET 1..3:", counts)
        print("[OBSERVE HTTP] R1 buy lines inside each response body:", body_rows)
        print("[OBSERVE HTTP] Wednesday settlement executed:", wed_body["settlement"]["executed"])
        print("[OBSERVE HTTP] batch shares/status:", shares, status, " cash:", cash,
              " deducted:", START_CASH - cash)
    assert counts == [1, 2, 3]
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - 3 * ONE_BUY_COST


# --- controls ----------------------------------------------------------------


def test_control_non_schedule_day_replay_writes_no_r1(harness: Harness) -> None:
    """Monday (not 週二／四) never produces R1, however often it is replayed."""
    for _ in range(3):
        harness.service.evaluate_today(today=MONDAY)
    assert r1_buys(harness) == []
    assert harness.store.pending_directives() == []


def test_control_replay_after_settlement_does_not_duplicate(harness: Harness) -> None:
    """Tuesday once, Wednesday settles; Wednesday replays add nothing."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)
    before = (len(r1_buys(harness)), book(harness))
    harness.service.evaluate_today(today=WEDNESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)
    after = (len(r1_buys(harness)), book(harness))
    assert before == after
    assert before[0] == 1
    assert before[1][3] == START_CASH - ONE_BUY_COST


def test_control_single_tuesday_call_is_correct(harness: Harness) -> None:
    """The happy path: one call, one row, one buy (matches the existing suite)."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)
    assert len(r1_buys(harness)) == 1
    assert book(harness)[0] == ONE_BUY_SHARES
    assert book(harness)[3] == START_CASH - ONE_BUY_COST
```

## 下一步

1. **重現成立，建議維持 medium-high。** 理由如下：
   - 正常瀏覽就會觸發，切分頁即可。
   - 現金帳會線性多扣，鐵律①會讀到偏低的現金。
   - 帳冊現金與批次股數永久對不上，沒有自癒路徑。
   - 嚴重度要不要上調，請 tech-architect／CEO 決定，我只交事實。
2. **交 tech-architect**：修法設計（例如引擎略過已有待成交買單的批次，或 `record_directives` 加去重，或結算時批次層級的 claim）。
   - 這會影響 N-168 A 案的 R 行為，請在 N-168 build 前定調。
   - 目前量測到的 `playbook_schedule` 重複寫入尚未驗證，修法評估時要一併看。
3. **交 dev-lead 實作**，修好後：
   - 這 3 支 `expected` 測試轉綠。
   - 3 支 `observe` 測試要改寫或刪除。
   - 3 支 `control` 保留。
   - 轉成正式測試前需要經 qa-reviewer 審查，我再把檔案整理進 repo 的 `tests/`。
4. **N-168 的影響**：待成交 R 買單的清單可能出現同一 (symbol, batch_no) 多列，揭露的股數加總必須依 F5 處置決定算法。
5. **已知缺口**（尚未覆蓋）：
   - 多標的、多批次的情境（本次只測 2330 第 1 批）。
   - 週四排程日、與 MISSED 重試路徑組合的情境。
   - 結算價落在限價帶外的情境（兩列可能一成交一 MISSED，行為未測）。
   - 前端實際重複觸發次數沒有實機量測，只有依預設值的推論。
   - 資料庫併發（兩個請求同時進來）沒有測，本次是序列呼叫。
