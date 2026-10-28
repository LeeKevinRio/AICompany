# ADR-0031：stock-desk 排程台與第 1 條並存揭露的組合點與邊界

- 狀態：accepted（CEO #69，2026-10-28 核可，含風控五項修改）
- 日期：2026-10-28
- 決策者：tech-architect（草案，`work/reviews/2026-10-28-排程台第1條揭露組合點評估-tech-architect.md` 附錄）；CEO #69（2026-10-28）核可，含風控五項修改（`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` #69）。實質決定已由 CEO #68 裁定，本 ADR 只定架構。
- 審查：風控 2026-10-28 #68 裁決補充（`work/reviews/2026-10-28-#68裁決補充-R4解讀與出貨方式-風控.md`，R4-1～R4-6 與第 6 節五項修改已納入）；修訂 D-2 經 CEO #70 與風控 2026-10-28 N-151 標籤掃描授權與 #70 D-2 改寫（`work/reviews/2026-10-28-N151標籤掃描授權與#70D2改寫-風控.md`）定稿，生效全文見 `work/reviews/快市排程-風控前置意見.md` 末節「D-2 修訂」。
- 適用範圍：僅 product/stock-desk 產品線。
- 與既有 ADR 的關係：
  - **補充 ADR-0025（accepted）**，不修訂條文；部分落實其風控待辦第 6 項，只涵蓋「排程台 × 第 1 條」，engine／plan／playbook 三種聲音並存的通用揭露規格仍未結。
  - 沿用 ADR-0006 D-8「api 是唯一組裝點」的先例。
- 編號說明：落檔時主 checkout 的 `docs/adr/` 最後一份為 ADR-0030，`docs/` 內 grep `0031` 無結果。
- 標註約定：本檔為 tech-architect 草案加風控定稿的轉錄。程式路徑相對於 `apps/stock-desk/backend/`；引用的檔案行號為草案 2026-10-28 的快照，會隨 commit 漂移，tech-writer 落檔時未重新驗證。落檔：coordinator 依 tech-writer 成品轉檔（tech-writer 會話無 Bash）。

---

## Context（背景）

- CEO #68（2026-10-28）：第 1 條不約束排程台，股數不變，在規則集層級加靜態算式揭露。
- 排程台每檔佔排程台總資產 `deploy_ratio / n_targets`（預設參數下 14%）；第 1 條以庫存已估值市值為分母（`app/advice/limits.py`）；兩者分屬不同帳冊。
- `app.settings` 本身 import `app.advice.limits`（`settings/store.py:36`、`models.py:38`、`migrations.py:67`），讀第 1 條設定值的模組都會遞移碰到 `app.advice`。R4 守門要求 `app.playbook` 不可達 `app.advice`，遞移路徑只允許 `app.api.deps`（`tests/test_playbook_boundary.py:47-52`）。
- 前端只在 `mode === "unconfirmed"` 時抓取並渲染規則集（`frontend/app/playbook/page.tsx:107`），已確認的使用者看不到 `/rule-set`。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A. `app.playbook` 內讀 settings | 字面與排程台放一起 | 遞移碰到 `app.advice`，邊界測試紅燈 | 違反 R4，豁免自始不成立。**否決** |
| B. 新頂層 `app/disclosures/` 套件 | 名字直觀 | 無先例；讀 settings 仍碰 advice，最後仍須 API 層組合 | 與 C 等價但更複雜。**否決** |
| **C. API 層注入（採用）** | 有 Kelly D-8 先例；揭露與規則集同一份回應；playbook 套件碰不到第 1 條 | router 手上會有第 1 條的數字 | 日後被拿去夾股數；以不變性測試加識別字禁令擋 |
| D. 獨立 endpoint | playbook router 不動 | 前端多一個請求與失敗狀態；兩次讀取可能版本不同 | 備案：風控不同意 C 的 R4 解讀時改用 |

## Decision（決策）

1. 組合點在 API 層：零依賴字面模組 `app/api/playbook_cap1_wording.py`，加 `deps.get_cap1_weight` 提供值，由 `app/api/playbook.py` 組合。
2. `/today`、`/rule-set`、`/confirm-rules` 回應都帶 `cap1_disclosure`（形狀見 C-2）；數字取自同一份回應實際使用的 `RuleParams` 版本。
3. 不計算兩個比例的大小關係，揭露無條件出現；兩邊分母不同帳冊，比較沒有意義。
4. 揭露是即時組合，不落任何表，不成為 `RuleParams` 欄位，不進入任何指令。
5. 前端只照順序渲染後端給的整句與預先格式化的字串，不比較、不換算、不拼句（AV-13）。
6. 出貨：D-2 修訂現在生效，揭露另開 `fix/stock-desk-playbook-cap1-disclosure`；第一批 `fix/stock-desk-cap1-10pct` 以測試 ③ strict xfail 先合併（CEO #71；風控補充裁定第 5 節）。

## Consequences（後果）

- 好處：playbook 套件完全碰不到第 1 條，歸屬語豁免的前提不變；已確認的使用者每次進頁都看得到揭露；揭露是否出現由契約測試保證，不靠前端記得去抓。
- 壞處：playbook router 手上有一個第 1 條的數字，只能靠不變性測試與白名單守住；`/today` 回應多一個欄位，`PlaybookEvaluation` 要帶出配置參數。
- 分母差異的說明：揭露以 1÷n_targets 的條件例示說明（「庫存只有排程台的 n 檔且各檔市值相同時，每檔約佔 …」），不讀庫存、不宣稱實際比例，在所寫條件下必然成立（風控補充裁定第 4 節）。
- 前提：風控確認 `max_position_weight` 屬使用者設定、不在 R4 排除範圍內（已確認，風控補充裁定第 1 節，附 R4-1～R4-6）；日後撤回則改採 D 案並修訂本 ADR。

## 對實作的約束

**後端結構**
- **C-1** `app/api/playbook_cap1_wording.py` 只能 import 標準函式庫、`decimal`、`pydantic`、`typing`，不得 import 任何 `app.*`。純函式 `compose(*, rules_version: int, deploy_ratio: Decimal, n_targets: int, cap1_weight: Decimal | None) -> PlaybookCap1Disclosure`，參數全為 keyword-only、無預設值；字面所需的 `batches_per_target`、`deploy_ratio_pct` 等參數可依此增列，規則相同。
- **C-2** `PlaybookCap1Disclosure` 欄位：`rules_version: int`（只供對賬，前端不得顯示）；`title: str`（後端下發，固定為「排程台每檔規模與第 1 條上限」，前端不得自寫）；`lines: list[str]`（風控核可整句，數字已代入，永遠不得為空）；`per_target_pct: str | None`（如 `"14%"`）；`cap1_pct: str | None`（如 `"10%"`）；`per_target_book_pct: str | None`（可選；句子本身仍放在 `lines`）。不得有任何比較結果、旗標或狀態欄位（如 `exceeds`、`status`）。
- **C-3** 百分比格式：每檔佔比 = `deploy_ratio / n_targets × 100`，Decimal 計算，ROUND_HALF_UP 到小數一位，去掉結尾 `.0`，加 `%`；第 1 條 = `Decimal(str(max_position_weight)) × 100`，規則相同。`n_targets ≤ 0` 或第 1 條讀不到時，對應 pct 欄位為 `None`（AV-16，不得為 0），`lines` 只替換對應該句為風控定稿的缺值句，其他句照常輸出；不得以 10% 或任何預設值頂替，不得把 `n_targets` 原始值插進句子。`cap1_disclosure` 欄位本身永遠不是 null。風控補充裁定已撤回「`{cap1_pct}` 須與 `format_percent` 輸出逐字相同」的要求。
- **C-4** `app/api/deps.py` 新增 `get_cap1_weight() -> Decimal | None`：讀 `_default_settings_store().load().risk_budget.max_position_weight`，與建議卡同一來源（`api/advice.py:183`）；**任何讀取或驗證例外（不限 `sqlite3.Error`）一律回傳 `None` 並改用缺值句，不得讓 `/today`、`/rule-set`、`/confirm-rules` 失敗或延遲（R4-4）**；不得每次請求新建 `SettingsStore`（建構子會跑 S2 遷移，`settings/store.py:97-107`）。
- **C-5** `today`、`rule_set`、`confirm_rules` 回應都帶 `cap1_disclosure`；`rules_version`、`deploy_ratio`、`n_targets` 必須來自同一份回應實際使用的 `RuleParams` 版本。`/today` 建議由 `PlaybookEvaluation` 帶出其用的 `deploy_ratio`、`n_targets`、`version`（未確認路徑也要帶），不得在 router 另呼叫 `rule_set_status()` 讀第二遍。
- **C-6** router 不得直接 import `app.settings.*`；第 1 條的值只能經 `Depends(get_cap1_weight)` 進入，且只能傳給 `compose`。
- **C-7** 揭露不得寫入任何表（AV-11）；不得做成 `RuleParams` 欄位（`store.py:586` 讀舊資料會被套用）；不得進入 directive 或 batch。

**邊界測試（`tests/test_playbook_boundary.py`）**
- **T-1** router 直接 import 不得含 `app.settings`。
- **T-2** router 直接 import 的 `app.*` 白名單固定為 `app.api.common`、`app.api.deps`、`app.playbook`、`app.playbook.wording`、`app.playbook.models`、`app.playbook.service`、`app.api.playbook_cap1_wording`；新增須改此測試。
- **T-3** `playbook_cap1_wording` 的 `imported_modules` 無任何 `app.*`。
- **T-4** 以 `_identifiers` 掃 `app/playbook/*.py`，不得出現 `max_position_weight`、`RiskBudget`、`risk_budget`、`cap1_weight`、`playbook_cap1_wording`，另加 `get_cap1_weight`（R4-3）。
- **T-5** playbook 遞移掃描再加禁區 `app.settings`、`app.api`，各給明確錯誤訊息。

**行為測試（新檔，如 `tests/test_api_playbook_cap1_disclosure.py`）**
- **B-1 不變性**：第 1 條覆寫為 0.05、0.10、0.50、None，另加 TIGHT 與 LOOSE 兩組（`RiskBudget` 全欄位由最嚴到最寬，定義見風控 N-151／#70 裁決第二項第 3 點）；`/today` 的 `directives`、`snapshot`、`page_summary`、`warnings`、`attribution`、`mode_reason`，`/rule-set` 的 `rules`、`params`、`attribution`，以及所有 `playbook_*` 表的 dump 必須逐字相同。
- **B-2 一定出現**：五種 mode（含 unconfirmed）的 `/today`、`/rule-set`、`/confirm-rules`，`lines` 都不得為空；預設參數下含 `"14%"` 與第 1 條當前值字串。矩陣含 `n_targets` = 11、7、5 與第 1 條 = 0.25，證明顯示與否和大小關係無關。
- **B-3** `rules_version` 等於同一份回應所用參數的 `version`。
- **B-4** `/confirm-rules` 與 `/today` 之後，任何 playbook 表的任何欄位值都不得含揭露句。
- **B-5** `test_playbook_rebalance.py` 改為只釘住算式（佔比 = `deploy_ratio / n_targets`），修正 docstring，移除對 `RiskBudget` 的 import（見 PD-8）。

**前端（AV-13）**
- **F-1** 哨兵測試：fixture 的 `title`、`lines` 與 pct 用哨兵字串，斷言區塊內渲染文字正好是這些字串且順序一致，沒有額外數字。
- **F-2** 揭露元件檔內不得出現 `deploy_ratio`、`n_targets`、`max_position_weight`、`params`、`parseFloat`、`Number(`、`toFixed`，也不得用 template literal 包住揭露欄位（不得比照 `RuleSetConfirmPanel.tsx:147`）。
- **F-3** `types.ts` 中這些欄位型別只能是 `string`、`string[]`、`string | null`。
- **F-4** 渲染不得以 mode 或任何比較結果為條件；confirmed 與 unconfirmed 各一則渲染測試；涉及 UI，須 qa-e2e 實機驗收。

**R4 條件（風控補充裁定第 1 節；缺一則 C 案不成立，改走 D 案）**
- **R4-1** router 中第 1 條的值只能當 `compose(...)` 的參數，不得出現在任何 `if`、比較、運算、log 或回應的其他欄位（AST 斷言為 suggested，「不得分支、不得運算」為 required）。
- **R4-2** B-1 不變性測試在揭露分支綠燈才可合併（矩陣含 TIGHT 與 LOOSE 兩組，見 B-1）。
- **R4-3** T-1～T-5 全部落地。
- **R4-4** 第 1 條讀取失敗不得讓三個端點失敗或延遲（見 C-4）；補測試：settings 讀取丟例外時 `/today` 仍回 200 且 directives 不變。
- **R4-5** `/confirm-rules` 不得因第 1 條的值拒絕確認、也不得改變寫入的參數；測試名稱明寫。
- **R4-6** 建議端（advice、settings、portfolio）的 API 回應一個字都不得改變（修訂 D-2 第 (4) 項）。

**契約摘要（PD）**
- PD-1 `playbook_cap1_wording` 不 import 任何 `app.*`（AST）。
- PD-2 router 直接 import 的 `app.*` 以白名單固定，不含 `app.settings`（AST）。
- PD-3 `app/playbook/*.py` 不得出現 `max_position_weight`、`RiskBudget`、`risk_budget`、`cap1_weight`（識別字掃描）。
- PD-4 第 1 條取 0.05、0.10、0.50、None 與 TIGHT、LOOSE 時，指令、快照、規則條文與參數、playbook 各表 dump 都相同。
- PD-5 每種 mode 與三個端點的 `cap1_disclosure.lines` 都不為空；`rules_version` 與同一份回應的參數版本一致。
- PD-6 回應裡沒有比較結果或狀態欄位；缺值輸出 null，不輸出 0（AV-16）。
- PD-7 前端哨兵測試：渲染結果等於後端字串；元件內不出現換算、parse 或拼句。
- PD-8 原斷言於第一批刪除（風控 2026-10-28 簽核修訂 D-2）；揭露存在性由 B-2 承擔，第一批以 strict xfail 占位。

## 待決

- 風控四項（R4 解讀、揭露位置與逐字字面、無條件揭露、D-2 修訂）：**已裁**（風控 2026-10-28 #68 裁決與補充裁定；D-2 修訂另經 N-151／#70 改寫）。
- CEO 核可本 ADR：**已核可**（CEO #69，2026-10-28）。
- 第 2～5 條上限的適用範圍：CEO #70 已裁（2026-10-28）：比照第 1 條，不約束；見修訂 D-2 第 (6) 項。第 2 條、第 4 條若需專屬算式揭露，另開編號、經風控審查。
- N-155 揭露須在 #62 第二批（5-K）合併前結案，否則風控否決第二批（CEO #71；風控補充裁定第 5 節）。
- 未結：ADR-0025 風控待辦第 6 項的通用規格（engine／plan／playbook 三種聲音並存）。
