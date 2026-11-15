# NM-5 第五批白名單審查

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
程式碼審查結論：PASS。BLOCKING_ISSUES=false。
- 我沒有跑測試，`11699 passed` 未經重現。
- Codex 不可用：`codex --version` 回 command not found。依 CEO #58 記為「單家審查」。
- diff 共 4 檔，read 全文後逐項對照 C1～C5。

## 各部門回報（逐項對照 BLOCKING 判準）

1. C1 成立
   - `MISSING_CODES` 只在 `engine.py:111-120` 定義一次。
   - 內容依序為 `E_BARS_SHORT`、`E_PRICE_UNUSABLE`、`*get_args(VolatilityMissingCode)`、`E_PIT_UNVERIFIED`，共五個 code，不含 `E-ADJ-COVERAGE`。
   - 我用 grep 查過，`app/` 內沒有第二份 `MISSING_CODES` 定義。
   - `tests/` 引用 `E_ADJ_COVERAGE` 都是 `from app.outlook.basket import`，沒有字串副本。
   - `test_outlook_missing_codes.py:50-62` 的 AST 測試掃整個 `app/`，確認 owner 只有 `outlook/engine.py`。

2. C2 成立
   - `engine.py:404-417` 的比對與 `_item` 第一參數都改用 `E_VOL_SHORT`、`E_VOL_DEGENERATE`，這兩個常數 import 自 `volatility.py:51-52`。
   - engine 內共五個 `_item(` 呼叫（363、386、401、406、416 行），第一個參數都是集合內名稱。
   - `test_outlook_missing_codes.py:98-100` 斷言呼叫數恰為 5。
   - `test_outlook_missing_codes.py:119-122` 有四個牙齒反例：字串字面值、`sigma.missing_code` 屬性、`E_ADJ_COVERAGE`、關鍵字引數形式。
   - 前三個會被判為不在集合；第四個是 `args` 為空而被當成 `Constant(None)`，同樣不通過。反例有效。

3. C2 行為等價成立（讀碼確認）
   - `E_VOL_SHORT` 與 `E_VOL_DEGENERATE` 的值就是原字串（`volatility.py:51-52`）。
   - 原本傳 `sigma.missing_code`，現在傳同值的常數。
   - `required` 與 `available` 的計算、`elif` 順序、`found` 的 append 順序都沒動。
   - 邏輯沒有分歧。harness 輸出雜湊與 a2c2f38 相同的說法，與讀碼結果一致，但我沒有重現雜湊。

4. C3 成立
   - 集合成員、`E-VOL-*` 至多一個、順位不遞減，另外加了「同一 code 不重複」，都在 `test_outlook_missing_codes.py:131-143` 的 `missing_list_problems` 檢查。
   - 合成案例共約 20 個，其中 degenerate、六根 bar、「四列同時」、PIT 各有專門的案例。
   - `:176` 斷言 `seen == set(MISSING_CODES)`，所以若案例沒產出全部五個 code，測試會失敗，不是空轉。
   - `:178-190` 有四個牙齒反例。

5. C4 成立
   - `forecast_pipeline_harness.py:89` 從 `app.outlook.engine` import `MISSING_CODES`。
   - 失敗種類為 `missing_code_not_in_set`（`:348`、`:496-497`）。
   - 失敗只記 `where`，格式為 `claim_id T=data_as_of`（`test_forecast_pipeline_harness.py:296`）。這次沒有新增標籤或筆數欄位，符合 D-4。
   - 反例有效：
     - `test_forecast_pipeline_harness.py:235-252` 三個 param，其中一個是正例（全集合不失敗）。
     - `:275-300` 把 ledger 的 `missing_json` 竄改成 `E-ADJ-COVERAGE`，斷言 harness 失敗、`where` 正確、摘要的「失敗種類：」行含該 kind。
   - 竄改只對測試用的 tmp ledger 執行，不碰正式 DB。

6. C5 成立
   - diff 只有四個檔：`app/outlook/engine.py` 和三個 `tests/` 檔。
   - `main.py`、`scheduler.py`、`rules/**`、`dirdef/**`、`baselines.py`、`store.py` 零 diff。
   - engine 的改動只是常數引用與新增一個 tuple，沒有規則或定義的內容異動，規則雜湊與定義雜湊不受影響。
   - 沒有寫死的 `code_digest`。

## 凍結後待辦（非 BLOCKING）
- `app/outlook/baselines.py:49-50` 另外定義了 `E_BARS_SHORT` 與 `E_PRICE_UNUSABLE`，`engine.py:105-106` 也各自有一份。
  - 這是既有的重複，且這次 TA 裁示不要求處理。
  - 若日後有人改了其中一份，`MISSING_CODES` 與 baselines 的 reason 可能不一致。
  - 建議凍結後由 engine 改為 import baselines 的常數。
- `test_forecast_pipeline_harness.py:71` import 了 `test_forecast_report` 的私有函式 `_tamper`。這會在測試檔之間造成耦合，建議日後移到共用 helper。
- `store.py:143` 的 `VOLATILITY_MISSING_PREFIX = "E-VOL-"` 是既有的字串前綴，不屬 C1 範圍，一併記錄。

## 驗證
- 已讀：4 檔 diff、`engine.py` 第 325-430 行與 import 區、`volatility.py` 的常數。
- 已查：grep 全 backend 的 `E-VOL-*`、`_item(` 與各 code 字面值。
- 未做：測試執行，所以測試通過與雜湊相等都沒有重現；Codex 第二意見因工具缺席沒做。

唯讀權限判準常數：未觸及。我審查的是固定的 commit 範圍（a2c2f38..9f45cb2），沒有跑 staged 版的兩道機械檢查，改以 diff 的檔案清單確認。四個檔案裡沒有 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的異動。

## 下一步
- 交 CEO／coordinator，這一段可算通過；測試與雜湊由有執行環境的一方重跑並確認。
- 上面兩項「凍結後待辦」記入待辦清單。

相關路徑：
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/outlook/engine.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/test_outlook_missing_codes.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/forecast_pipeline_harness.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/test_forecast_pipeline_harness.py

BLOCKING_ISSUES=false
