# 風控五項整改（第 1～4 項與 5-BT）收尾交件

- 審查者：frontend-engineer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
風控五項整改（第 1～4 項與 5-BT）已收尾，已 push 到 `origin/fix/stock-desk-risk-remediation`。HEAD 為 48c5209e7d5f761d1afacc24d96ef1d595730f73。
- 5 個既有 commit 逐條對照定稿，沒有缺漏。
- 未提交的 `componentWordingScan.test.ts` 判定是收尾的一部分，已併入新 commit 48c5209。
  - 內容：決策卡 fixture 的 `disclaimer` 由舊句換成 3-S 定稿字面，屬 C-2「字面更新」。對應定稿指名的 :2278（現為 :2299）。
  - 這是 C-2 grep 中最後一處舊免責字面。
- 我另補了一處 C-15 缺漏：`limitNotices.ts` 的 `EXCLUDED_LIMIT_ID`、`NOTICE_ACTIONS` 兩個常數補上「風控 2026-10-26 定稿；失效條件 T#」註解。
- 沒有碰 5-K、禁用詞清單、`allowedContexts`、`findBareRealtimeClaims`。沒有 merge 或 push 到 product/stock-desk。
- 有兩件事要請你決定（見「待決事項」）：根目錄 README.md:33 仍有舊句；00631L 的 2-R 字面讀起來矛盾。

## 各部門回報（frontend-engineer）
### 定稿表逐項落點
路徑前綴：F = `apps/stock-desk/frontend/app/`，B = `apps/stock-desk/backend/`。

| 項目 | 落點 |
|---|---|
| 字面常數集中處 | `F lib/riskRemediationWording.ts`；1-L 在 :22，1-X 在 :25 |
| 1-L／1-X | `F position/[symbol]/UnvalidatedNotice.tsx:12-24`（`<details>`，`text-sm text-neutral-400`）。渲染處：`DecisionCard.tsx:226`（candidate）、`:246`（held）；`OperationSummaryPanel.tsx:203`（candidate）、`:288`（held）。兩處信心 chip 已移除 |
| 2-V／2-M／2-R／2-O、被擋句 | 邏輯 `F lib/limitNotices.ts`（`buildLimitNotices`）；呈現 `DecisionCard.tsx:258`（`LimitNoticeBlock`），掛載於 `:495`。順序為違反、被擋句、2-R、2-O |
| 3-S | 前端 `DecisionCard.tsx:504`。後端 `B app/advice/engine.py:66` 的 `DISCLAIMER`。R3 指引句已移除 |
| 3-F | `F layout.tsx:22` 的 `SITE_FOOTER_DISCLAIMER`；`apps/stock-desk/README.md:6` 同步 |
| 3-N | `B app/alerts/notify.py:64`（`ALERT_DISCLAIMER_LINE`），`:76` 用於推播最後一行 |
| K-1／K-2 | `F position/[symbol]/KeyLevelsPanel.tsx:50`（K-1）、`:305`（K-2） |
| 4-Q／4-E | `F position/[symbol]/StopQualifier.tsx:42`。用於 `DecisionCard.tsx:484` 與 `KeyLevelsPanel.tsx:499` |
| 4-T | 階梯組標題 `KeyLevelsPanel.tsx:402`；詳細內停利卡 `:596`；`F lib/keyLevelsVisuals.ts:105` 的 `target-2r` 已改 `isHeadline: false` |
| 4-附 | `OperationSummaryPanel.tsx:303`，以 rule id 比對；`F lib/operationSummary.ts` 新增 `topMatchedRuleId` |
| 停利移出 | 決策卡的停利格與 `targetDistance` 已移除（四格變三格）；`KeyLevelsPanel` 主視圖停利大字已移除 |
| 5-BT | `F backtest/BacktestReportView.tsx:611` 起（標題、第 1 點、第 2 點）；圖說 `F lib/backtestCurveWording.ts:60` |
| 連動 xref | `F lib/entryObservationWording.ts:63`、`F lib/sectionTaglines.ts:35` |
| 連動 confidenceMeaning | `OperationSummaryPanel.tsx` 兩處不渲染（API 欄位保留） |

### C-1～C-13、C-15 自檢
- C-1：通過。
  - 這批沒有改動 `FRONTEND_FORBIDDEN_TERMS`、`shared/forbidden-terms.json`、`BANNED_PHRASES`、`allowedContexts`、`findBareRealtimeClaims`。
  - 唯一例外條目在 `kellyBannedLiteralsFrontend.test.ts`：3-F 逐字含「最近一次收盤」，與 Kelly 禁字掃描撞字，所以只對 `riskRemediationWording.ts` 這一句整句開例外。
  - 這個例外不是動 `allowedContexts`，但它動到了守門測試，請 qa 特別看一眼。
- C-2：通過。釘字面測試的修改全部是換字面或新增斷言，沒有刪了不補的。逐檔標註見下節。
- C-3：通過。
  - 2-R：`test_advice_engine.py:535,546`（違反上限只把 add 改 hold，其餘動作不變）。
  - 4-E：`riskRemediationItem4.test.ts:99-146`（2 倍、0.92、14、取較高者）。
  - 5-BT：`test_backtest_engine.py:77,95,109`（第 t 根同根收盤成交、滑價預設 0）。
  - 5-K 那條屬 5-K，不在本批。
- C-4：通過。held 與 candidate 恆顯示；no_action 與 no_price 不顯示；用 `<details>`；字級對比不弱於舊 chip；兩處 chip 都移除。
- C-5：通過。排除第 5 條；1 條用 2-V、2 條以上用 2-M；在主畫面且不在 `<details>`；2-O 不論有無違反都顯示；null 不印「—」。
- C-6：通過。只限 held；動作須屬 hold／reduce／take_profit／stop_loss；`insufficient_data` 與 add 不顯示；被擋句排在 2-R 之前。
- C-7：通過。四種 kind 都顯示；`text-sm text-neutral-300`；不在 `<details>`；有前後端 parity 測試，兩側互讀；`InlineDisclaimer` 保留。
- C-8：通過。頁尾 `text-sm text-neutral-400`；README 同步。
- C-9：前提成立，證據在下節。
- C-10：通過。停損為「—」不顯示；`text-xs text-neutral-400`；依 `atr14 === null` 二選一；用 `<details>`。
- C-11：通過。
- C-12：通過。只在 `drawdown_protection`、`deep_drawdown_stop` 時顯示，同一行。
- C-13：通過。常駐，在 `data_warning` 之後、`EquityCurveChart` 之前，`text-sm`；標題與第 2 點依 `slippage_bps === 0` 選句。
- C-15：補完。除上述兩個常數外，其餘新常數原本就有標註。
- C-14 與 C-16：屬 5-K，本批未做。

### C-9 證據
警示股價只用日線收盤：
- `B app/alerts/snapshot.py:111`：`load_bars(...)`
- `snapshot.py:121-122`：`latest = max(loaded.bars, ...)`、`close = float(latest.close)`
- `B app/services/market.py:171`：`service.get_daily_bars(...)`
- 守門測試 `B tests/test_alerts_notify.py:100-101`：斷言 `snapshot.py` 含 `load_bars(` 與 `latest.close`。同檔以 AST 檢查 `app/alerts` 不 import 盤中報價模組（ADR-0014），也不使用 `QuoteProvider` 等名稱。
- 我另外 grep `app/alerts` 與 `scheduler.py`，沒有 intraday／realtime／`get_quote`。FX 匯率有另外的揭露句，不在 C-9 範圍。
- 限制：這是我讀程式與測試得到的證據，不是 dev-lead 的書面確認。C-9 原文要求 dev-lead 書面確認，仍須補。

### C-2 grep：剩餘出現處
範圍：全 repo，排除 `work/`、`event_study.py`、Kelly 相關檔案、`node_modules`、`.next`。

「研究與教育用途」「非投資建議」「不構成投資建議」
- 出貨面（使用者會看到）：只剩根目錄 `README.md:33`。
  - 內容：「所有建議畫面常駐「本工具為研究與教育用途，非投資建議」。」
  - 這是倉庫文件，不是應用畫面；定稿只指名 `apps/stock-desk/README.md:6`。
  - 要改需要新字面，我不准寫，所以沒動，見「待決事項」。
- 註解：`KeyLevelsPanel.tsx:48,303` 與 `engine.py:64`，是說明舊字面已被取代的註解，不渲染。
- 否定式測試：`riskRemediationWording.test.ts:35,161`、`backtestAssumptionsDisclosure.test.ts:69`、`riskRemediationItem4.test.ts:89`、`limitNotices.test.ts:168`、`test_advice_wording.py:134,146`、`test_alerts_notify.py:58,64`。這些都是 `not.toContain` 或註解，守的是舊字面不得回來。
- `componentWordingScan.test.ts:751,837`：註解。
- `eventStudy.test.ts:120`：事件研究字面，屬 `event_study.py` 範圍。
- 過往 ADR（`docs/adr/0004`、`0025`、`0027`、`0029`）：歷史紀錄，不出貨。
- `event_study.py:423`、`test_event_study_wording.py:131`、`golden/event_study/*.json`：依定稿延到下一批（D-11）。

`CONFIDENCE_PREFIX`
- 唯一定義：`F lib/adviceWording.ts:239`，已加註「孤兒常數，沒有元件使用」。
- 其餘都是測試：
  - `adviceWording.test.ts:46,76,204,208`：仍逐字釘住舊字面。
  - `decisionCard.test.ts`（:25、:626、:642 起）與 `operationSummary.test.ts`（:29、:832 起）：用於 `not.toContain` 與 regex 反向斷言。
  - `componentWordingScan.test.ts:1698,1749`：斷言 `{CONFIDENCE_PREFIX}` 不出現在元件裡。
  - `riskRemediationWording.test.ts:62-64`：斷言元件程式碼不引用它。
- 出貨元件沒有使用它。

### 釘字面測試逐檔標註
- `operationSummary.test.ts`：
  - 字面更新：fixture 與斷言的 disclaimer 換成 3-S；信心 chip 改為 `UNVALIDATED_LABEL`。
  - 行為新增：`OP_DETAILS` 邊界；「no_action 與 no_price 不渲染」；`confidenceMeaning` 改為 `not.toContain`。
- `ruleInvalidationDisclosure.test.ts`：
  - 字面更新：fixture 的 disclaimer。
  - 行為新增：「不在任何 `<details>` 內」換成等價且更嚴的逐 block 檢查。
- `decisionCard.test.ts`：
  - 字面更新：fixture 的 disclaimer；信心行測試換成 1-L／1-X；停利格移出（四格變三格，`lg:grid-cols-3`）；「—」計數 3 變 2 與 4 變 3；「無 `<details>`」換成逐 block 檢查。
  - 行為新增：`UNVALIDATED_LABEL` 恆顯示、no_action 與 no_price 不顯示。
- `componentWordingScan.test.ts`：
  - 字面更新：K-1、K-2、`ADVICE_CARD_XREF_TO_SUMMARY`、`ENTRY_E2_XREF`、頁尾句（3-F）、R3 位置換成 3-S、信心 chip 與 `confidenceMeaning` 斷言、停利大字斷言、fixture disclaimer。
  - 行為新增：`SCANNED_FILES` 加入 4 個新檔。
- `keyLevelsHoldingUnknown.test.ts`：
  - 字面更新：大字由兩個變一個；結構由兩欄 grid 變單一停損區塊。
  - 行為新增：停損為「—」不顯示 4-Q。
- `keyLevelsVisuals.test.ts`：字面更新（`target-2r` 的 `isHeadline` 改 false）。
- `backtestCurveWording.test.ts`：字面更新（圖說）。
- `kellyBannedLiteralsFrontend.test.ts`：行為新增（單句例外加上過期檢查）。
- 後端：
  - `test_advice_wording.py`：字面更新（`DISCLAIMER`）；行為新增（不含否認句、與前端常數 parity）。
  - `test_alerts_notify.py`：字面更新（3-N）；行為新增（只讀日線的守門）。
  - `test_advice_engine.py`、`test_backtest_engine.py`：行為新增。
- 新檔（行為新增）：`riskRemediationWording.test.ts`、`riskRemediationItem4.test.ts`、`limitNotices.test.ts`、`backtestAssumptionsDisclosure.test.ts`。
- `test_advice_limits.py`、Kelly API 測試、`RiskGauge`、`SettingsForm`、`KellyImportDialog` 屬 5-K，未動。

## 驗證
完整 CI 全部通過，目錄為 `apps/stock-desk/frontend` 與 `apps/stock-desk/backend`，在 commit 48c5209 之前就跑完；最後那個 commit 只改註解與測試 fixture 之外無程式變更（前端 CI 在 limitNotices 註解修改之後才跑）。
原始輸出存於 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/`：`fe_typecheck.txt`、`fe_vitest.txt`、`fe_build.txt`、`be_lint.txt`、`be_mypy_ci.txt`、`be_pytest.txt`。

前端
- `npm run typecheck`：`tsc --noEmit`，`TYPECHECK_EXIT=0`。
- `npx vitest run`：
  ```
  Test Files  86 passed (86)
        Tests  2409 passed (2409)
  VITEST_EXIT=0
  ```
- `npm run build`：
  ```
  ✓ Compiled successfully in 18.4s
  ✓ Generating static pages using 3 workers (8/8) in 699ms
  BUILD_EXIT=0
  ```
  路由：`/`、`/_not-found`、`/backtest`、`/icon.svg`、`/playbook`、`/position/[symbol]`、`/positions`、`/settings`。

後端
- `uv run ruff check .`：`All checks passed!`
- `uv run ruff format --check .`：`437 files already formatted`
- `uv run mypy app tests`（`strict = true` 設在 pyproject）：`Success: no issues found in 432 source files`
- `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：
  ```
  TOTAL                                       19119    500    97%
  Required test coverage of 90% reached. Total coverage: 97.38%
  ========== 8089 passed, 2 xfailed, 18 warnings in 1708.68s (0:28:28) ==========
  PYTEST_EXIT=0
  ```

## 截圖與實機觀察
- 依 e2e-fallback 代跑：offline demo 資料（`source=demo_synthetic`，畫面資料為合成示範資料）。
  - DB：`STOCK_DESK_DB_PATH=.../remed/demo.db`。
  - 執行 `uv run python -m app.demo.seed` 時 DB 已有資料，輸出為「新增 0 筆、沿用既有 3 筆」，seed 具冪等性。
  - 後端 8200、前端 3200。為此用 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8200` 另外 `next build` 了一次，供截圖用；`.next` 已被 gitignore。
- 儀器來源（`provenance`）：
  - playwright：`/opt/node-tools/node_modules/playwright/index.js`
  - chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`
  - 前綴 `/opt/`，與既定前綴一致。
- 需要揭露的一點：後端 CORS 白名單寫死 `http://localhost:3000`，而本次被指定用 3200。我用 Chromium 啟動參數 `--disable-web-security` 解除瀏覽器端 CORS 檢查，沒有改應用。
- 行程已用 PID 停掉（uvicorn 5428、next-server 5437 等）；停後 8200、3200 皆無回應。
- 截圖目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/remed/`（本次產出 8 張）：
  - `2330-desktop.png`、`2330-desktop-expanded.png`（所有 `<details>` 展開，可看到 1-X 與 4-E）
  - `2330-mobile-375.png`
  - `00631L-desktop.png`、`00631L-desktop-expanded.png`
  - `00631L-mobile-375.png`
  - `backtest-result-desktop.png`、`backtest-result-mobile-375.png`
  - 同目錄的 `position-*.png`、`backtest-desktop-*.png`、`backtest-mobile-*.png` 是前一位在容器重開前留下的舊圖，不是本次產出，請勿與上列混用。
  - 代跑腳本是 `.../scratchpad/runner.js`，原始輸出是 `.../scratchpad/runner_out.txt`。
- 逐字畫面（取自 `runner_out.txt`）：
  - 2330 決策卡：「續抱參考」「未經歷史驗證」「固定算式・未還原價・可能無法依此價成交」；「已違反 2 條上限：」下列第 1、4 條；兩句「加碼建議被第 N 條上限…擋下。」；2-R；「另有 2 條上限無法評估，不代表已通過；見下方建議卡。」；3-S。
  - 00631L：「減碼參考」；「已違反 2 條上限：」；2-R；2-O；3-S；操作摘要「依據：目前回撤深於兩成以未還原價計算，回撤可能含除權息缺口」。
  - 價位階梯停利組標題為「停利參考（固定算式，非分析結果）」；主視圖只有停損大字。
  - 頁尾為 3-F 全文。
  - 回測框：「先看以下假設：前兩項可能讓結果偏樂觀」；第 1 點；「滑價設為 0 bps：…這裡沒有計入。」。量測值：`fontSize` 14px、顏色 `lab(84.92 0 -0.0000119209)`。
  - 兩個視口 `scrollWidth` 都等於 `innerWidth`（375），無橫向溢出。console 錯誤 `[]`，失敗請求 `[]`。
- 我只看了 3 張縮圖（`2330-desktop`、`00631L-mobile-375`、`backtest-result-desktop`）；其餘截圖以逐字文字確認。縮圖上版面無異常。

## 待決事項
1. 00631L 的 2-R 字面讀起來矛盾。
   - 動作本身就是「減碼參考」（規則得出）時，畫面出現：「「減碼參考」不代表你的部位在上限內；目前超過上限只會把加碼參考改為續抱參考，不會改成減碼參考。」
   - 這是定稿字面加上 C-6 允許 reduce 時顯示的結果，我照定稿實作，沒有自行改動。建議請風控確認 reduce、take_profit、stop_loss 時是否仍要顯示，或改字。
2. 根目錄 `README.md:33` 仍寫「所有建議畫面常駐「本工具為研究與教育用途，非投資建議」」。定稿沒有涵蓋它，需新字面或刪句的決定，請 creative-lead 或風控裁示。
3. C-9 仍需 dev-lead 書面確認（上面只是我的程式與測試證據）。
4. 4-附 在畫面上緊接規則名稱，只用 `ml-2` 分隔，innerText 中沒有分隔符號，讀起來像同一句。字面是定稿的，所以我沒改；若要加分隔需 art-lead 決定。
5. 5-K 未做，需等 CEO 對「停用會拿掉 10% 封頂」裁定後另開 PR。

HEAD：48c5209e7d5f761d1afacc24d96ef1d595730f73（`fix/stock-desk-risk-remediation`，已 push）。
這批 6 個 commit：7252b4a、89fae00、1af1fac、cf4b490、4fcc83a、48c5209。
