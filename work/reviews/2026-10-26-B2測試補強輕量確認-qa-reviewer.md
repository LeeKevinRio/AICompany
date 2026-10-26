# B2 測試補強最後一輪輕量確認

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

# B2 測試補強最後一輪輕量確認（qa-reviewer，2026-10-26）

範圍：HEAD 2ca0031，staged 23 檔，全在 `apps/stock-desk/backend/` 下。本輪只改 4 個測試檔。我逐段讀過 4 個檔的新增與修改段落，再交叉讀了被測的 `app/forecast/definitions.py:97-120`、`app/dirdef/rules.py` 的 `RULE_TEXT_FIELDS`，以及 `tests/dirdef_helpers.py` 的 `rule_data` 預設值。CI 我沒跑也不能跑，8023 passed 的數字是 dev-lead 交件所述，我未獨立驗證。

## Codex 第二意見

Codex 第二意見未執行（環境不可用），依 CEO #53 合併前補跑。`codex --version` 回 exit 127，`command not found`。

## 逐項結果

### F-1（medium）：已處理，反例格咬得到
- `tests/test_forecast_boundaries.py:910`（claims）、`:922`（volatility）、`:930`（basket）三處都改成 `_dirdef_import_violations(source, _module_name(path))`。
- `_module_name`（`:185-190`）以 `APP_ROOT.parent` 為基準，會算出 `app.outlook.basket` 這類真實模組名。
- 新反例格 `test_a_relative_import_outside_dirdef_resolves_to_its_own_package`（`:576-580`）：
  - `from .basket import x` 在 `app.outlook.volatility` 解析成 `app.outlook.basket`，判違規。
  - 在 `app.forecast.claims` 解析成 `app.forecast.basket`，判違規。
  - 若退回舊的 `app.dirdef.probe` 預設基準，這兩格會變成合規而轉紅。
- `_resolve`（`:463-471`）的換算我手算過，非 package 取 `parts[:-1]`，package 取 `parts`，結果正確。

### F-2（medium）：已處理，新格確實分辨得出數值與字串排序
- `tests/test_outlook_basket.py:324-331`，資料為 `[v1.10(0.95), v1.2(0.92)]`。
- 數值排序：v1.2 先，凍結值 0.92，沒有退步，結果 `[]`，斷言成立。
- 字串排序：`"dirdef-v1.10"` 排在 `"dirdef-v1.2"` 前，凍結值 0.95，v1.2 被判退步，結果 `["dirdef-v1.2"]`，斷言轉紅。
- 與交件附的暫改字串排序實證（`['dirdef-v1.2'] == []` 失敗）一致。
- 舊格 `:312-321` 維持不變。

### F-4（low）：已處理，順序測試咬得到
- `tests/test_forecast_definitions.py:225-237`：以 `dirdef-v9.0` 為鍵登記，兩個雜湊都是 `"f"*64`。
- 斷言 `match="definition_version"`、`"sha256" not in str(caught.value)`，且快取為空。
- 實作 `definitions.py:106-109` 的版本檢查在 logic 雜湊檢查（`:110`）之前，訊息為 "carries a different definition_version"，不含 sha256。
- 若有人把 logic 雜湊檢查調到前面，訊息會變成 `definition_logic_sha256`，這格會轉紅。

### F-5（low）：已處理，與欄位集合連動
- `tests/test_dirdef_rules.py:524-540` 三張表：
  - `RULE_TEXT_CHANGES`：改值後雜湊不變。
  - `RULE_LOGIC_CHANGES`：改值後雜湊改變。
  - `COMPARISON_CHANGES`：條件葉節點的 field、op、value、ref 各一格。
- 守門格 `:543-549`：
  - 三張表的鍵分別等於 `RULE_TEXT_FIELDS`、`OutlookRule.model_fields − RULE_TEXT_FIELDS`、`OutlookComparison.model_fields`。
  - `OutlookRuleSet.model_fields == {"version", "rules"}`。
  - 日後新增欄位而沒補格，這格會轉紅。
- 各格的改值確實不同於 fixture 預設：
  - id 預設 `index_momentum`，改為 `renamed_rule`。
  - direction 預設 bullish，改為 bearish。
  - weight 預設 0.5，改為 0.6。
  - 葉節點基準為 `ret_5d / gt / 0.0`，各欄位改值都不同；`ref` 格會先移除 `value`，避免兩者並存。
- `test_forecast_boundaries.py:664` 已把 `("RULE_TEXT_FIELDS", "dirdef/rules.py")` 補進單一定義清單。
- `_definitions`（`:159-175`）涵蓋 `AnnAssign`，而 `rules.py:60` 是唯一的帶註記賦值；其他出現處（`:30` 的 docstring、`:211` 的使用）都不算綁定，所以計數為 1。

### F-6（low）：已處理
- `_dirdef_import_violations` 新增 `is_package` 關鍵字參數並傳給 `_resolve`（`:495-512`）。
- `:540-541` 依 `path.name == "__init__.py"` 帶入。
- 新格 `:583-587`：
  - 以 package 身分解析 `from .rules` 為合規。
  - 以非 package 身分解析為 `["app.rules"]`，判違規。
  - 這證明參數確實有作用。

## 上一輪 PASS 結論未被破壞
- `git diff --stat`（未 stage）只有一個 `work/dispatch/` 追蹤清單，與上一輪相同。`apps/` 與 `docs/` 沒有未 stage 的變更，staged 也沒有 `docs/` 的檔案。
- staged 清單仍是 23 檔，與交件所述一致。
- 我沒有上一輪的逐檔行數快照可機械比對 `app/` 的 diff。這項依據是：staged 檔案清單與上一輪相同、`apps/` 無未 stage 變更、`app/` 下被我抽讀的段落與上一輪結論一致（`definitions.py:97-120` 的檢查順序、`rules.py` 的 `RULE_TEXT_FIELDS`）。
- 閘門不變式（登記表為空、沒有 job／route／store、`forecast/__init__.py` 不 import）屬於 `app/` 與 `test_forecast_gate_closed.py`，本輪都沒動。

## 新引入的問題
沒有 critical 或 high，也沒有 medium。

- [low，不擋] F-1 的新反例格只覆蓋 `from .X import y` 這一種寫法。`from . import basket` 在 outlook 下會解析成 base `app.outlook`，仍會判為非 dirdef 而違規，結果正確，只是沒有專屬格。
- 殘留項沒有變：F-3（ADR 缺 `copy`／`include`／`exclude` 字面）與 F-7 已登記為 N-146，屬 ADR 字面，不在本批。

## 唯讀權限判準常數

未觸及。
- 判準一：staged 23 檔（`git diff --cached --stat`）全在 `apps/stock-desk/backend/` 下，沒有 `scripts/validate_agents.py`。未 stage 的只有 `work/dispatch/` 追蹤清單。
- 判準二：我的 Bash 權限不含 `grep`，所以用 Grep 工具對 4 個測試檔做等效搜尋，搜 `READONLY_AGENTS|READONLY_ALLOWED_BASH`。我讀過的段落沒有命中，沒有 shadow 定義。
- 上一輪已對整個 `apps/stock-desk` 做過同樣搜尋，0 筆。本輪沒有新增 `app/` 或 `scripts/` 變動。

## 結論
PASS，可 commit。F-1、F-2、F-4、F-5、F-6 逐項處理，新反例格咬得到違規。

commit 前的條件：
1. CI 由 coordinator 獨立執行並綠燈。
2. 依 CEO #53 在合併前補跑 Codex（本次環境不可用）。
3. commit 拆分方式沿用上一輪建議（ADR 一個 commit、程式一個 commit，同一次 push）。若 ADR 已在 HEAD 2ca0031，只需提交程式這一份，並帶上本輪與上一輪的審查檔、dev-lead 交件。

BLOCKING_ISSUES=false

## 我實際執行過的 Bash 指令（全數自我揭露）
沒有帶 `cd`。
1. `codex --version`：exit 127，`command not found`。
2. `git diff --cached --stat`
3. `git diff --stat`

沒有用到 `git show`、`git log`、`sed`、`grep`、`cat`、`python`、`pytest`、`uv`，沒有任何寫入。其餘都用 Read、Grep、Glob。沒有讀 `.env`，沒有碰 `*.db`。CI 沒有跑。

## 相關檔案（絕對路徑）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_boundaries.py（F-1：`:910`、`:922`、`:930`、`:576-580`；F-6：`:495-512`、`:540-541`、`:583-587`；單一定義清單 `:664`）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_outlook_basket.py（F-2：`:324-331`）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_definitions.py（F-4：`:225-237`）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_dirdef_rules.py（F-5：`:524-579`）
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/definitions.py（`:97-120`，只讀核對）
- /home/user/AICompany/work/reviews/2026-10-26-B2修正批與ADR補字複審-qa-reviewer.md
- /home/user/AICompany/work/reviews/2026-10-26-B2測試補強交件-dev-lead.md
