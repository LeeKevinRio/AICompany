# #68 排程台 × 第 1 條揭露組合點評估（含 ADR-0031 草案）

- 審查者：tech-architect
- 日期：2026-10-28
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 評估摘要

1. **組合點採用 API 層，不新增頂層 `app/disclosures/` 套件。** 做法比照 Kelly 的既有先例（ADR-0006 D-8、`app/api/kelly_wording.py:7-14`）：
   - 字面和百分比格式化放在新的零依賴模組 `app/api/playbook_cap1_wording.py`，不 import 任何 `app.*`。
   - 第 1 條設定值由 `app/api/deps.py` 新增的依賴 `get_cap1_weight() -> Decimal | None` 提供。
   - 組合由 `app/api/playbook.py` 完成，結果注入回應欄位 `cap1_disclosure`。
   - 否決三個位置：放在 `app.playbook` 內會違反 R4；新開頂層套件沒有先例，也沒有額外好處；另開獨立 endpoint 留作備案。
2. **只放在 `GET /rule-set` 不夠，`GET /today` 也必須帶。** 前端只在 `mode === "unconfirmed"` 時才抓取並渲染規則集（`frontend/app/playbook/page.tsx:107`、`lib/playbookView.ts:321`）。CEO 已確認規則集，所以只放在 `/rule-set` 的揭露他永遠看不到。結論：`/today`、`/rule-set`、`/confirm-rules` 三個回應都帶同一份組合結果；畫面放哪裡由風控定。
3. **能同時讀 `RuleParams` 與 `max_position_weight` 的只有 API 層。** 原因是 `app.settings` 自己就 import `app.advice.limits`（`app/settings/store.py:36`、`models.py:38`、`migrations.py:67`），任何讀 settings 的模組都會遞移碰到 `app.advice`。邊界測試早已把 `app.api.deps` 認定為唯一允許的遞移路徑（`tests/test_playbook_boundary.py:47-52`），所以 settings 只能從 deps 進來，router 不得直接 import `app.settings`。
4. **AV-13 的成立方式是後端出整句加上前端哨兵測試。** 後端下發已代入數字的完整句子，前端只照順序渲染，不比較、不換算、不拼句。
5. **需要新 ADR，不修訂 ADR-0025 條文。** 草案暫編 ADR-0031（見附錄），定位是落實 ADR-0025 風控待辦第 6 項（`docs/adr/0025-…:611`）中「排程台 × 第 1 條」這一部分，通用的三種聲音規格仍待風控。
6. **另開分支，不併進第一批。** 但如果風控裁定「D-2 修訂與揭露必須同時生效」，就只能合併出貨，理由見 Q4。

## 方案比較（Q1：組合點）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A. `app.playbook`（service 或 wording）讀 settings | 字面和排程台放在一起 | 遞移碰到 `app.advice`，`test_the_playbook_never_reaches_the_advice_package`（`test_playbook_boundary.py:81-87`）直接紅燈 | R4「違反即豁免自始不成立」。**否決** |
| B. 新頂層 `app/disclosures/` 套件 | 名字直觀 | 沒有先例，多一個套件要守；它若讀 settings，同樣碰到 advice，最後還是得由 API 層組合 | 和 C 等價但更複雜。**否決** |
| **C. API 層注入（採用）**：零依賴的 wording 模組，加 deps 提供值，再由 router 組合 | 有 Kelly D-8 先例；router 不新增 `app.settings` import；揭露和規則集放在同一份回應，可以保證一定出現；playbook 套件完全碰不到第 1 條 | router 手上會有一個第 1 條的數字 | 有人日後拿這個數字去夾股數（即 quant 的 (b)），要靠 B-1 不變性測試加識別字禁令擋住 |
| D. 獨立 endpoint `GET /api/disclosures/…` | playbook router 完全不動 | 前端多一個請求與失敗狀態；「一定出現」要靠前端記得去抓；兩次讀取可能拿到不同版本 | 風控若裁定 playbook router 不得持有第 1 條的值，就改用此案（備案） |

**需要風控確認的 R4 解讀**：`RiskBudget.max_position_weight` 是使用者設定，不是建議引擎的輸出。R4 排除的是 `action`、`confidence`、`weight`、`matched_rules`、`direction_weights`（`test_playbook_boundary.py:3-8`）。這個值經 API 層注入揭露欄位，不會流入任何規則輸入或指令股數。這是 C 案的前提；風控不同意就改用 D 案。

## 決策（ADR 草案）

全文見附錄。重點如下：
- 不計算「14% 是否 ≥ 10%」，揭露無條件出現。兩邊分母不同帳冊，比較結果沒有意義；條件式顯示本身就是 quant 第 3 節 (c) 所說的假精度。quant 的測試「佔比 ≥ 第 1 條時揭露一定出現」因此自然成立。
- 揭露是即時組合，從不寫入資料庫（AV-11）。

## 對實作的約束（逐條可檢查）

**後端結構**
- **C-1** 新增 `app/api/playbook_cap1_wording.py`。只能 import 標準函式庫、`decimal`、`pydantic`、`typing`，不得 import 任何 `app.*`。對外提供純函式 `compose(*, rules_version: int, deploy_ratio: Decimal, n_targets: int, cap1_weight: Decimal | None) -> PlaybookCap1Disclosure`，參數全部 keyword-only、沒有預設值。
- **C-2** `PlaybookCap1Disclosure` 的欄位：
  - `rules_version: int`
  - `lines: list[str]`：風控核可的整句，數字已代入
  - `per_target_pct: str | None`：例如 `"14%"`
  - `cap1_pct: str | None`：例如 `"10%"`

  不得有任何比較結果、旗標或狀態欄位（例如 `exceeds`、`status`）。
- **C-3** 百分比的格式化規則：
  - 每檔佔比 = `deploy_ratio / n_targets × 100`，用 Decimal 計算，ROUND_HALF_UP 到小數一位，去掉結尾的 `.0`，加上 `%`。
  - 第 1 條 = `Decimal(str(max_position_weight)) × 100`，格式化規則相同。
  - `n_targets ≤ 0` 或第 1 條讀不到時，對應的 pct 欄位為 `None`（AV-16），`lines` 換成讀取失敗的句子（字面由風控定）。欄位本身永遠不是 null。
- **C-4** `app/api/deps.py` 新增 `get_cap1_weight() -> Decimal | None`：
  - 讀 `_default_settings_store().load().risk_budget.max_position_weight`，和建議卡同一個來源（`api/advice.py:183`）。
  - 遇到 `sqlite3.Error` 時回傳 `None`。
  - 不得每次請求新建 `SettingsStore`：建構子會跑 S2 遷移（`settings/store.py:97-107`）。
- **C-5** `app/api/playbook.py` 的 `today`、`rule_set`、`confirm_rules` 回應都帶 `cap1_disclosure`。
  - `rules_version`、`deploy_ratio`、`n_targets` 必須來自同一份回應實際使用的 `RuleParams` 版本。
  - `/today` 的建議做法是讓 `PlaybookEvaluation` 帶出它用的 `deploy_ratio`、`n_targets`、`version`，未確認路徑也要帶。這是 playbook 內部資料，沒有第 1 條的成分。
  - `/today` 不得在 router 另呼叫一次 `rule_set_status()` 讀第二遍。
- **C-6** router 不得直接 import `app.settings.*`。第 1 條的值只能透過 `Depends(get_cap1_weight)` 進入，而且只能傳給 `compose`。
- **C-7** 揭露不得寫入任何表（AV-11）。不得做成 `RuleParams` 欄位（否則 `store.py:586` 讀舊資料時會被套用），不得進入 directive 或 batch。

**邊界測試擴充（`tests/test_playbook_boundary.py`）**
- **T-1** router 的直接 import 不得含 `app.settings`（比照 `:90-94`）。
- **T-2** router 直接 import 的 `app.*` 白名單固定為：`app.api.common`、`app.api.deps`、`app.playbook`、`app.playbook.wording`、`app.playbook.models`、`app.playbook.service`、`app.api.playbook_cap1_wording`。要新增必須改這個守門測試，改動本身就會觸發審查。
- **T-3** `app.api.playbook_cap1_wording` 的 `imported_modules` 裡沒有任何 `app.*`。
- **T-4** 用 `_identifiers`（`:97-114`）掃 `app/playbook/*.py`，不得出現 `max_position_weight`、`RiskBudget`、`risk_budget`、`cap1_weight`、`playbook_cap1_wording`。
- **T-5** playbook 套件的遞移掃描再加兩個禁區 `app.settings`、`app.api`，各自給出明確的錯誤訊息。

**行為測試（新檔，例如 `tests/test_api_playbook_cap1_disclosure.py`）**
- **B-1 不變性**：第 1 條覆寫為 0.05、0.10、0.50、None 四組時：
  - `/today` 的 `directives`、`snapshot`，以及 `/rule-set` 的 `rules`、`params`、`attribution` 必須逐字相同。
  - 兩個 tmp DB 用同一個 fixture 跑完 `/today`，所有 `playbook_*` 表的 dump 必須相同。

  這一條同時證明 AV-11 成立，以及「排程台不會因此調整股數」。
- **B-2 一定出現**：五種 mode（含 unconfirmed）的 `/today`，加上 `/rule-set`、`/confirm-rules`，`cap1_disclosure.lines` 都不得為空。預設參數下要分別含 `"14%"` 與第 1 條當前值的字串。
- **B-3 版本一致**：`cap1_disclosure.rules_version` 必須等於同一份回應所用參數的 `version`。
- **B-4**：`/confirm-rules` 和 `/today` 之後，任何 playbook 表的任何欄位值都不得含揭露句。
- **B-5**：`test_playbook_rebalance.py:162-194` 改成只釘住算式：佔比 = `deploy_ratio / n_targets`，並修正 docstring `:165-167` 的錯算。拿掉對 `RiskBudget` 的 import（`:24`）。「一定出現」改由 B-2 承擔。

**前端（AV-13）**
- **F-1 哨兵測試**：fixture 的 `lines` 用 `["SENTINEL-A","SENTINEL-B"]`、pct 用 `"X%"`。斷言區塊內渲染的文字正好是這些字串、順序一致，沒有任何額外的數字。這證明前端沒有自己重算。
- **F-2 靜態掃描**：揭露元件的檔案內不得出現 `deploy_ratio`、`n_targets`、`max_position_weight`、`params`、`parseFloat`、`Number(`、`toFixed`，也不得用 template literal 包住揭露欄位。現有的 `RuleSetConfirmPanel.tsx:147` 會在後端字串外面拼句，這次不得比照。
- **F-3**：`types.ts` 裡這些欄位的型別只能是 `string`、`string[]`、`string | null`。
- **F-4**：揭露的渲染不得以 mode 或任何比較結果為條件。confirmed 和 unconfirmed 各寫一則渲染測試。涉及 UI，要加 qa-e2e 實機驗收。

## Q3：ADR

- 需要新 ADR（ADR-0031，proposed）。理由：這次新增了跨套件的組合點、擴張 R4 守門範圍，並且定了「不比較、無條件揭露」的規則。這些是架構決策，放在任務單裡不夠。
- 不修訂 ADR-0025 原文，照 ADR-0027 的慣例（`0025:11`）只加指標。核可後由 tech-writer 處理兩處：
  - ADR-0025 檔頭加一行「補充：ADR-0031」。
  - `:611` 行尾加註〔部分落實：排程台×第 1 條，見 ADR-0031；三種聲音通用規格仍待風控〕。
- 編號提醒：ADR-0030 只在主 checkout 的 `docs/adr/`，worktree 裡最新的是 0029。落檔時由 tech-writer 以產品線實況確認編號。

## Q4：分支

**建議另開 `fix/stock-desk-playbook-cap1-disclosure`，從第一批 HEAD 長出，等第一批合併後再合併。** 理由：
1. 第一批是收緊風險的變更（第 1 條改 10%、Kelly 凍結），而且它上線的日子就是 5-K 30 天倒數的起點。把揭露綁進去，等於拖延所有收緊措施。
2. 衝突在 15% 時代就已存在：以第 1 條的分母計算是 20%，見 quant 報告 `:12`。第一批沒有新增任何曝險，只是讓衝突在測試裡現形。
3. 揭露要走另一條審查流程：風控逐字核字面、前端加 qa-e2e、ADR 送 CEO 核可。這也符合一個 commit 一個語意。
4. 揭露會讀 S2 遷移後的設定值，所以必須以第一批為基底。

第一批的紅燈測試怎麼處置，由風控和 qa 定。我的架構偏好如下：
- 第一批先修 docstring、改成釘住算式。這部分是純事實，不涉及 D-2。
- 原本的 `<= cap` 斷言改為 `xfail(strict=True)`，reason 寫「CEO #68；揭露於上述分支落地；D-2 修訂待風控簽核」。揭露分支落地時就移除這個標記，並由 B-2 接手。
- 不得靜默轉綠。

**例外**：如果風控裁定 D-2 修訂要和揭露同時生效（D-2 屬「缺一裁定不成立」，見 `work/reviews/快市排程-風控前置意見.md:41,49-50`），第一批就必須維持紅燈等揭露，這時只能合併出貨。

## 交接
- ADR-0031 草案：交 tech-writer 落檔，交 CEO 核可。
- R4 解讀（C 案的前提）、揭露位置與字面、無條件揭露、D-2 修訂：交風控。
- C、T、B、F 各條約束：交 dev-lead 與 frontend-engineer 遵循，qa-reviewer 逐條核對。

本次只用 Read、Glob、Grep 讀檔，沒有改任何檔案，沒有讀 `.env`，也沒有碰 `data/*.db`。

---

## 附錄：ADR-0031 草案

```
# ADR-0031：stock-desk 排程台與第 1 條並存揭露的組合點與邊界

- 狀態：proposed
- 日期：2026-10-28
- 決策者：tech-architect（草案）；待 CEO 核可（實質已由 CEO #68 裁定，本 ADR 只定架構）
- 適用範圍：僅 product/stock-desk
- 與既有 ADR：補充 ADR-0025，不修訂條文；部分落實 ADR-0025 風控待辦 6（:611），
  只涵蓋「排程台 × 第 1 條」，engine／plan／playbook 的通用規格仍待風控。
  沿用 ADR-0006 D-8「api 是唯一組裝點」的先例。

## Context
- CEO #68（2026-10-28）：第 1 條不約束排程台，股數不變，在規則集層級加靜態算式揭露。
- 排程台每檔佔排程台總資產 deploy_ratio/n_targets（預設 14%），第 1 條以庫存
  已估值市值為分母（app/advice/limits.py），兩者分屬不同帳冊。
- app.settings 本身 import app.advice.limits，凡是讀第 1 條設定值的模組都會遞移碰到
  app.advice；R4 守門要求 app.playbook 不可達 app.advice，router 只查直接 import，
  遞移路徑只允許 app.api.deps（test_playbook_boundary.py:47-52）。
- 前端只在未確認時渲染規則集（page.tsx:107），已確認的使用者看不到 /rule-set。

## Decision
1. 組合點在 API 層：零依賴的字面模組 app/api/playbook_cap1_wording.py，
   加上 deps.get_cap1_weight 提供值，由 app/api/playbook.py 組合。
2. /today、/rule-set、/confirm-rules 的回應都帶 cap1_disclosure，內容依 C-2 的形狀；
   數字取自同一份回應實際使用的 RuleParams 版本。
3. 不計算兩個比例的大小關係，揭露無條件出現；分母不同帳冊，比較沒有意義。
4. 揭露是即時組合，不落任何表，不成為 RuleParams 欄位，不進入任何指令。
5. 前端只照順序渲染後端給的整句與預先格式化好的字串。

## Consequences
- 好處：playbook 套件完全碰不到第 1 條，歸屬語豁免的前提不變；
  已確認的使用者每次進頁都看得到揭露；揭露是否出現由契約測試保證，
  不靠前端記得去抓。
- 壞處：playbook router 手上會有一個第 1 條的數字，只能靠不變性測試與白名單守住；
  /today 的回應多一個欄位，PlaybookEvaluation 要帶出配置參數；
  揭露不說明「以第 1 條分母計約 20%」（排程台看不到庫存，說了是假精度），
  使用者要自己理解分母不同。
- 前提：風控確認 max_position_weight 屬使用者設定、不在 R4 排除範圍內；
  風控不同意時，改採獨立 endpoint 方案，並修訂本 ADR。

## 對實作的約束
- PD-1 playbook_cap1_wording 不 import 任何 app.*（AST）。
- PD-2 router 直接 import 的 app.* 以白名單固定，不含 app.settings（AST）。
- PD-3 app/playbook/*.py 不得出現 max_position_weight、RiskBudget、risk_budget、
  cap1_weight（識別字掃描）。
- PD-4 第 1 條取 0.05、0.10、0.50、None 時，指令、快照、規則條文與參數、
  playbook 各表的 dump 都相同。
- PD-5 每種 mode 與三個端點的 cap1_disclosure.lines 都不為空；
  rules_version 與同一份回應的參數版本一致。
- PD-6 回應裡沒有比較結果或狀態欄位；缺值時輸出 null，不輸出 0（AV-16）。
- PD-7 前端哨兵測試：渲染結果等於後端字串；元件內不出現換算、parse 或拼句。
- PD-8 test_playbook_rebalance 改為釘住算式；D-2 修訂由風控簽核後才可移除原斷言。

## 待決
- 風控：R4 解讀、揭露的位置與逐字字面、無條件揭露、D-2 修訂。
- CEO：核可本 ADR。
```

**相關檔案**（worktree 為 `/home/user/AICompany/.claude/worktrees/agent-acd20375384d3db0b`）
- `<worktree>/apps/stock-desk/backend/tests/test_playbook_boundary.py:30-52,81-94,97-127`
- `<worktree>/apps/stock-desk/backend/app/settings/store.py:36,97-107,115-125`
- `<worktree>/apps/stock-desk/backend/app/settings/models.py:38`
- `<worktree>/apps/stock-desk/backend/app/settings/migrations.py:67`
- `<worktree>/apps/stock-desk/backend/app/api/playbook.py:44-56,152-183,201-238,310-335,338-369,400-429`
- `<worktree>/apps/stock-desk/backend/app/api/deps.py:236-237,392-399`
- `<worktree>/apps/stock-desk/backend/app/api/kelly_wording.py:7-14`
- `<worktree>/apps/stock-desk/backend/app/api/advice.py:183`
- `<worktree>/apps/stock-desk/backend/app/playbook/models.py:85-89`
- `<worktree>/apps/stock-desk/backend/app/playbook/service.py:472-489,607-623`
- `<worktree>/apps/stock-desk/backend/tests/test_playbook_rebalance.py:24,162-194`
- `<worktree>/apps/stock-desk/frontend/app/playbook/page.tsx:107`
- `<worktree>/apps/stock-desk/frontend/app/playbook/RuleSetConfirmPanel.tsx:63-64,146-148`
- `<worktree>/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md:11,515,550,552,611,636`
- `<worktree>/docs/adr/0006-stock-desk-kelly-輸入來源與模組邊界.md:210`
- `/home/user/AICompany/work/reviews/2026-10-26-排程台14%與第1條10%衝突分析-quant-researcher.md`（第 3 節，`:65-93`；這份檔只在主 checkout，worktree 裡沒有）
- `<worktree>/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md:82`
- `/home/user/AICompany/work/reviews/快市排程-風控前置意見.md:41,49-50`
