# ADR-δ 草案第一次修訂（依 RC-900～RC-908）

- 審查者：tech-architect
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. ADR-δ 草案已依風控 RC-900～RC-908 和 dev-lead 的前提查證改完。下面附上修訂後的完整草案和逐項修訂對照表。風控否決的三處都已照它給的替代規則或替代文字改寫：
   - 5.1「建議卡其餘內容」那一格；
   - 2.4 第 4 點的引擎閘門；
   - 第 8 節的 CEO 題目，照錄 RC-906。
2. 我自己做的三個選擇：
   - **Decision 3 登記後「規則」那一列選 (b)**：只要有任何規則因為日線原因被跳過，規則條件就判 unavailable。理由有三：
     - 不必改 API，可以在 B-2 一起落地，不用等 F-4；
     - 不必在前端推斷被跳過規則的方向；
     - 以現行規則來看，兩條回撤規則在 `gap` 時一定被跳過，所以 (a) 能多分辨出來的情形實際上不存在。
   - **`compute_signals` 維持不改，在呼叫端套用**。查證後這已經和 digest 無關，純粹是設計取捨。我的理由是：改在裡面，會讓排程台、回測這些不在本 ADR 範圍的消費端靜默改變行為。漏套用的風險，用 `build_advice` 的必填參數加上 AST 測試來擋。
   - **H_f 的邊界**：可疑那一對的兩根 bar 都被該欄位的計算讀到，才算受影響。視窗連續時，等價於 k ≤ W_f − 2，其中 k 是可疑那一天之後還有幾根。
3. 2.4 第 4 點有一處讀法要請風控確認。RC-905 寫的是「照現有的優先順序輸出防禦型動作」，我讀成「防禦方向內權重最重的動作，不管建構方向的權重是否更重」。另外我新加了一條：判定不是 usable 時，後端的 `quantity_range` 也回 None。這條比風控要求的嚴。兩點都在對照表標了「待風控確認」。
4. CEO 題目要等 coordinator 確認 2.4 第 4 點已照 RC-905 寫入之後才能送出。我這版已經寫入，但還是要先經風控核對。

## 發現

### 修訂對照表

| # | 來源 | 修訂位置 | 改成什麼 |
|---|---|---|---|
| 1 | RC-900 第 1 點 | 5.1「決策卡／操作摘要」列；6.2 F-T7 | 持有卡維持 T2。F-T7 補 `take_profit`、`stop_loss`、持有 `add`、「只有 `concentration_watch` 命中的 `hold`」四種 fixture，最後一種要斷言標題被換掉 |
| 2 | RC-900 第 2 點 | 5.1 新增「候選卡組成句」列；Options D 加註 | 候選卡採 T3：`compositionText` 加 `supportiveDisclaimer`，以及 `notSupportiveText`，換成 W-10。「進場評估」、未持有徽章、`UnvalidatedNotice` 保留。決策卡 `MainSlot` 和操作摘要 `SummaryBody` 兩處都改 |
| 3 | RC-900 第 3 點 | 5.1 新增「依據行、失效條件行、依規則標籤」列 | 標題被換掉時，以下都不顯示：「依據」行連同回撤附註（`OperationSummaryPanel.tsx:298-308`）、失效條件行連同揭露句（`DecisionCard.tsx:571-590`）、`RULE_SOURCE_CHIP`。suggested 項目採納 |
| 4 | RC-900 第 4 點 | 同上列 | 防禦型標籤保留時，「依據」和失效條件行照常顯示 |
| 5 | RC-900 第 5 點 | 5.1 新增「必須照常顯示的元素」列 | 五個元素在任何狀態下都照常顯示，不得移除或弱化 |
| 6 | RC-900 第 6 點；RC-907 第 4 點 | 5.1「數量區間」列；新增 5.6 W 編號表 | `unusable`／`gap` 時一律不顯示數量區間，`restoresComplianceWarning` 跟著一起不顯示，說明句指派為 W-5。後端 2.4 第 4 點另加 `quantity_range = None`（待風控確認） |
| 7 | RC-900 第 7 點 | 5.1「操作摘要」列 | 操作摘要 `<details>` 裡的反面論點和失效條件清單保留，由 W-6 加註涵蓋 |
| 8 | RC-900 第 8 點 | 4 節；K-12；F-T5 | 所有消費端用窮舉的 switch 加 `never` 檢查；runtime 遇到未知值時，比照 `unusable` 處理 |
| 9 | RC-900 第 9 點 | 5.7 新增；K-13 | 登記後前端的 T2 照樣保留，要拿掉必須另外送風控 |
| 10 | RC-900 第 10 點 | 5.1 技術分析、關鍵價位、進場觀察三列 | 照原案，已核可 |
| 11 | RC-901 第 3 點 (a) | 5.1 新增「命中規則（N 條）」列 | 不顯示數字，也不顯示「目前沒有規則命中。」，改用 W-12（W-7 系列） |
| 12 | RC-901 第 3 點 (b) | 5.1 新增「建議卡本體說明行」列 | 卡片本體最上方加 W-13，不得包在 `<details>` 裡。命中規則清單、方向權重、跳過清單保留 |
| 13 | RC-901 第 3 點 (c) | 5.1 新增「cap 4 列」 | 不得顯示為通過，改成無法評估，或附 W-14 |
| 14 | RC-901 第 3 點 (d) | 5.1 新增「候選卡頁尾覆蓋度句」列；Decision 2.8 | 不顯示百分比，改用 W-15。F-4 如果採 S2，要改寫「因依賴持倉資料而被跳過」這個成因，送風控 |
| 15 | RC-902 第 2 點 (a)～(c) | 5.3 | F-1 的觸發檔案擴大為 RC-902 列的 8 支；F-1 最晚在 F-2 或 F-3 開分支之前合併；W 字面沒定稿時，碰到觸發檔案的 PR 不得搶先合併 |
| 16 | RC-902 第 1、3～5 點 | 5.3 | F-2 進來時要重跑 F-T7；F-1 範圍含 RC-900 第 2、3、6 點和 RC-901 第 3 點；快照要在改動前產生基準，不得 `-u`；F-1 不夾帶其他語意，numstat 要能逐檔對帳 |
| 17 | RC-903 第 1 點 | Consequences；未決事項 | OHLC 頻率查證暫緩，F-2 不等它，PM 登記追蹤；要放寬只能走 `bars-verdict-v2` |
| 18 | RC-903 第 2 點 | 1.3 V-4；6.2 F-T3 | 前端也要求 volume 是整數；golden fixture 加 volume 缺值和空字串的案例，預期 `unusable`；未決事項刪掉 volume 驗證那一項 |
| 19 | RC-903 第 4 點 | 1.6；6.2 F-T9 新增 | `gap` 時關鍵價位和進場觀察只出現 W-2、W-3 的 gap 版，不得出現 RC-860 的句子，用渲染測試鎖住 |
| 20 | RC-903 第 5 點；RC-907 第 6 點 | 1.5(d) | 嚴格度排序補上 `empty`：`unusable`＝`empty` ＞ `gap` ＞ `usable` |
| 21 | RC-904 第 2 點 | F-T5 | 鎖住簽名只有一個參數，而且是允許清單寫法 |
| 22 | RC-904 第 3 點 | 4 節 | 新註解必須保留 (a)～(f) 六項語意，逐項列出 |
| 23 | RC-904 第 4 點 | 4 節 | `DecisionCard.tsx:410-415` 的長度檢查在 F-2 保留；`computeKeyLevels` 自己的長度檢查也保留 |
| 24 | RC-904 第 5 點 | 4 節 | `dailyBarsUsability.ts:13-19`、`:37-40` 兩段註解都要改寫 |
| 25 | RC-905 第 1 點；RC-907 第 3 點 | 2.4 第 4 點，整點改寫；新增 2.5 H_f 邊界 | 判定不是 usable 時，至少一條防禦型命中才輸出防禦型動作，信心上限 low；其他情形一律 `insufficient_data`；命中、跳過、上限清單照列。H_f 邊界明文規定（2.5 第 2 點）。B-2 測試涵蓋所有組合（6.1） |
| 26 | RC-905 第 2 點 | 2.4 第 4 點；K-11 | `bars_verdict` 是必填參數。B-2 要列出全部呼叫端，每個呼叫端要嘛傳真實判定，要嘛依第 7 節書面豁免。不得寫死 `"usable"`，用 AST 測試擋 |
| 27 | RC-905 第 3 點 | 2.6；新增「變更紀錄」節；與既有 ADR 的關係 | 不升 `rules_version`；`evaluation` 帶 `bars_verdict_version`；本 ADR 末加變更紀錄；ADR-0030 的 `rules_version` 指 outlook 規則檔，和 advice 規則集無關（依 grep 推得） |
| 28 | RC-905 第 4 點 | Options B；2.4 S2 前提 (a)～(d)；S1 條件 | 更正 S1 和 S2 的實際差別。列出 S2 轉 accepted 前要成立的四個前提，其中 (b) 是待查前提。S1 的 `reason` 改用 W-16 |
| 29 | RC-906 | 第 8 節 | 題目照錄 RC-906 原文，並加上送出條件 |
| 30 | RC-907 第 1 點 | Options B；第 8 節 | 刪除「依成本算的停損」 |
| 31 | RC-907 第 2 點 | Decision 3 表格，登記後「規則」列 | 選 (b)，理由寫在表下 |
| 32 | RC-907 第 5 點 | 5.1 | 同第 2、3、6、11～14 項 |
| 33 | RC-907 第 7 點；dev-lead | Context 第 6 點；2.1；2.2；2.7 | Context 改成兩層描述；刪除「如果在」的備案；2.2、2.7 改用已查證的理由，並寫明設計取捨 |
| 34 | RC-907 第 8 點；dev-lead | 未決事項 | 刪掉 volume 驗證、code_digest import 圖、S2 可評估規則數三項 |
| 35 | RC-908 第 2 點 | 6.2 F-T10 新增 | suggested 採納：交叉比對 `ruleDirection` 和 `DEFENSIVE_ACTIONS` 在五種動作上的結果相同 |
| 36 | dev-lead 下一步第 2 點 | K-5 | import 圖測試明列 `app.data.quality`、`app.signals`、`app.advice.context`、`app.advice.engine`、`app.barverdict`，沿用 `tests/import_graph.py` |
| 37 | dev-lead 本次結論第 4 點 | Context 第 6 點；2.1 | 寫明 digest 不涵蓋遞移 import 到的檔案，這也是不得改 `interface`、`freshness` 的理由 |

### 修訂後的 ADR-δ 草案全文

```markdown
# ADR-δ：stock-desk 日線壞值與跳空的判定與處置

- 狀態：proposed（第一次修訂，2026-11-26，依 RC-900～RC-908 與 dev-lead 前提查證）
- 日期：2026-11-26
- 決策者：
  - tech-architect：草案、第一次修訂
  - risk-compliance-officer：第 5 節「前端過渡期」、RC-882、RC-883 各點、2.4 第 4 點的審查，有否決權。行為審查見 RC-900～RC-908，修訂過的段落待核對
  - CEO：第 8 節，以及本 ADR 轉 accepted
- 編號：暫用「ADR-δ」，由 tech-writer 落檔時取號，不佔用既有編號。建議檔名 slug：`stock-desk-日線壞值與跳空的判定與處置`
- 適用範圍：只限 product/stock-desk。後端路徑相對於 `apps/stock-desk/backend/`，前端路徑相對於 `apps/stock-desk/frontend/`
- 題名變更：quant 前置定義原題為「公司行動偵測與排除」。本 ADR 把「壞值」和「跳空（疑似公司行動）」合成一套判準。公司行動在回測、事件研究、排程台的處置，不在本 ADR 範圍（見 Decision 7）
- 來源（皆在 `work/` 下）：
  - [Q] `reviews/2026-11-25-ADR-δ-ε前置定義-quant.md`
  - [DL] `reviews/2026-11-26-後端日線壞值行為調查-RC872-RC883-dev-lead.md`
  - [DL2] `reviews/2026-11-26-ADR-δ前提查證-code_digest-import圖-dev-lead.md`
  - [RC88x] `reviews/2026-11-26-PR-β-risk-gate-RC880至RC885-風控.md`
  - [RC87x] `reviews/2026-11-26-PR-α-risk-gate-RC870至RC876-風控.md`
  - [RC90x] `reviews/2026-11-26-ADR-δ草案行為審查-RC900至RC908-風控.md`
  - [CEO] `dispatch/2026-11-26-CEO決策-高優先問題排程維持原本順序.md`
- 字面規則：本檔只定**行為**（顯示、不顯示、附加說明）和識別名，**不定字面**。字面以 W-n 佔位（編號表見 5.6），由 creative-lead 起草、風控逐字審

## Context（背景）

1. **現況是兩套判準，而且彼此不一致。**
   - 前端：`evaluateDailyBarsUsability`（`app/lib/dailyBarsUsability.ts:41-47`）只要整批中任一根的 close、high、low 非有限或 ≤ 0，就判整批不可用。它不檢查 open、high<low、volume 和日期。
   - 後端：`/api/advice` 只檢查最新一根的收盤價（`app/api/advice.py:207`，`usable_price`），其他日線照常拿去算指標（`:208`）。
   - `PriceBar` 只驗證 volume 為 `int` 且 ≥ 0，以及 `as_of`、字串欄位；OHLC 的正值和一致性完全沒驗（[DL2] D 節，`data/interface.py:65,77-82`）。
   - `quality._check_ohlc_consistency`（`app/data/quality.py:167-189`）有寫，但它所在的 `check_price_bars` 沒有接進 `api/`。
2. **放心型誤導已經實測重現**（[DL] §2）：
   - 持有、乾淨資料的卡是 `reduce`／high／12/12/2/1.0。
   - 只把第 -30 根的收盤價改成 0，就變成 `hold`／medium／12/12/0/1.0。前端因此顯示「續抱參考」「命中 0 條」「資料完整度 100.00%」。
   - 原因有三：
     - `data_completeness`（`engine.py:364`）只看規則輸入欄位是否為 None；
     - `_as_float`（`context.py:97-101`）不濾 NaN 和 Infinity；
     - 0 條命中且完整度 ≥ `MIN_COMPLETENESS_FOR_ACTION`（0.5，`engine.py:113`）時走 `hold`（`:366-375`）。
3. **規則集現況**（[DL2] E 節，`rules/default.yaml` 1.1.0）：
   - 12 條規則裡，只有 `concentration_watch`（`position.weight`）不靠歷史日線。
   - 沒有任何一條規則只靠 close，也沒有任何一條規則依成本計算停損。
   - 所有防禦型規則（第 4～10 條）都要用到歷史日線。
4. **跳空（疑似公司行動）**：[Q] δ-1 定義了門檻 c = 10% + 1%，比較用嚴格大於，套用在相鄰兩根的收盤對收盤。[Q] δ-5 建議偵測到之後逐欄位拒算，記為 skipped 並附原因，不得當成 quiet，也不截斷視窗。
5. **風控要求本 ADR 明定的事**：RC-882 第 4～6 點、RC-883 第 1、3 點、RC-900～RC-907。
6. **時程與範圍限制**：
   - (a) CEO 決定（[CEO]）四項 high 問題的後端修正排在正式登記之後；dev-lead 不開登記前的 `app/` 修正。
   - (b) ADR-0030 補充六附記四（RC-721 Q-1～Q-8）：
     - 允許登記前的差異落在 `apps/stock-desk/frontend/`（類 A，不得是 `.py`，也不得是 Q-3 列的檔名）。
     - `apps/stock-desk/shared/` 在登記前只能屬於類 0（Q-4），所以**登記前不得在 `shared/` 新增檔案**。
   - (c) `code_digest` 範圍分兩層（[DL2] A～C 節）：
     - **digest 涵蓋的檔案**：`app/forecast`、`app/outlook`、`app/dirdef` 三個套件的全部 `*.py`，加上 `app/data/session_calendar.py`（`forecast/canonical.py:77-78,214-249`）。digest 只對這些檔案取雜湊，不追 import。
     - **會被 import 但不在 digest 內的檔案**：`app/data/interface.py`、`app/data/freshness.py`、`app/advice/banned_phrases.py`，以及 `app`、`app.data`、`app.advice` 三個 `__init__`。改了這些檔案，digest **不會變**，但 outlook 和 forecast 的語意會被改變，而跨 commit 的重算偵測不到。所以這一層比 digest 本身更不能碰。
     - **已查證不在兩層內的模組**：`app/data/quality.py`、`app/signals/*`、`app/advice/context.py`、`app/advice/engine.py`（[DL2] 本次結論第 1～3 點）。
   - (d) 實作限制（[Q] 範圍聲明）：
     - 新模組不得 import `app.dirdef`、`app.sectors`、`app.data.session_calendar`，也不得被上述兩層的任何模組 import；
     - 偵測器不得寫在 `PriceBar`（`interface.py`）或 `freshness.py`。

## Options（選項比較）

### A. 判準的唯一來源放哪一層

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A1 只有後端判定，前端只讀 | 只有一份實作 | 要等登記後才做得了；`/api/bars` 和 `/api/advice` 是不同請求，各自要帶判定 | 過渡期前端沒有東西可用 |
| A2 規格寫在 ADR，前後端各自實作，以 golden fixture 加雙邊契約測試對齊 | 前端現在就能做；後端修好之後前端仍保留一層防線（RC-865 第 1 點） | 兩份實作 | 漂移，靠契約測試擋 |
| A3 只做前端 | 改動最少 | 後端 API 照樣輸出放心型結論 | 根因不除 |
| **A4（採用）：壞值用 A2；跳空在過渡期用 A2，登記後改成 A1** | 壞值有雙層防線；跳空需要的除權息事件和交易日曆只有後端有 | 過渡期前端的跳空判斷比較粗 | 過渡期偽陽性比較多，方向是 fail-closed |

### B. 日線不可用時，後端建議卡回什麼（登記後）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| S1 整張卡回 `insufficient_data`，`advice=None` | 最簡單；沿用既有的「沒有價格」路徑 | 卡片變成 `advice=None`，這張卡上的**風險上限檢查清單**（含持股比重是否超過上限）和**集中度提醒**都會消失。決策卡的 `no_price` 分支不畫上限區塊 | `reason` 字面如果籠統，使用者分不出這和平常的缺資料有何不同（要用 W-16） |
| S2 逐欄位拒算，並套用 2.4 第 4 點的替代規則 | 保留 cap 1～3（依部位計算）和 `concentration_watch`；cap 4 無法評估；符合 ADR-0021 的 skipped 語意 | 改動比較多。照 2.4 第 4 點，標題和 S1 一樣是「資料不足」；持有卡最多只剩 1/12 可評估，候選卡 0/12 | 實際收益取決於 2.4 的前提 (b)、(c)；如果 `position.weight` 也吃到壞的 bar，S2 就只比 S1 多一份上限清單 |
| S3 卡片維持 ok，只加註 | 改動最小 | 後端仍會輸出 `hold`／medium／100% | 只能當過渡期的現況，不能當終態 |

- 兩案在標題層面相同，差別只在上限清單和集中度提醒（RC-905 第 4 點）。
- tech-architect 傾向 S2，理由是上限清單本身就是風控揭露，留著比較好。但實際多保留的東西很少，所以交 CEO 決定（第 8 節）。

### C. `data_completeness`

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **D1（採用）定義不改；受影響的欄位改回 None；evaluation 加註判定狀態和判定版本** | 定義穩定 | 數字的意思仍然是「輸入欄位可得的比例」 | 低 |
| D2 重新定義成「乘上品質係數」 | 一個數字表達兩件事 | 混淆兩種概念 | 語意漂移 |
| D3 定義不改，也不把欄位改回 None，只另加品質欄位 | 改動小 | 壞資料下仍會顯示 100% | 放心型誤導 |

### D. 前端過渡期，決策卡標題與操作摘要

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| T1 保留標籤，附加說明 | 改動最小 | 「續抱參考」仍是標題 | 已實測會被壞值翻出來（不接受，RC-900 第 1 點） |
| **T2（持有卡採用）非防禦型標籤換成無判定說明；防禦型保留並加註** | 壓掉放心型和建構型標籤，防守訊號保留 | 依方向分流 | 多一次可能不必要的減碼，用加註緩解 |
| **T3（候選卡採用）所有結論都換成無判定說明** | 候選卡沒有部位可保護，保留防禦標籤沒有價值；組成句本身就是放心句（`adviceWording.ts:151-153`） | — | 低 |

### E. 入場閘門怎麼表示「0 根」（RC-882 第 6 點三案）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) 閘門多收一個 bar 數參數 | 共用函式的契約不變 | 閘門有兩個輸入 | 呼叫端可能漏傳 |
| **(ii)（採用，RC-904 核可）共用判定新增 `empty` 狀態** | 判定本身就能回答；代理可以拿掉 | 觸及 RC-872 第 3 點 | 低 |
| (iii) 擴大 `page.tsx` 的範圍 | — | 判斷散落在頁面 | 違反 RC-767 |

### F. open 要不要納入

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| O1 不納入 | 不變 | 和後端 quality 的定義不一致 | 判準不一致 |
| O2 只要求有限且 > 0 | 簡單 | 抓不到 open 落在區間外 | 中 |
| **O3（採用，RC-903 核可）有限、> 0，而且落在 [low, high]，等號放行** | 和 `quality._check_ohlc_consistency` 同一套定義 | 會多拒算 | 偽陽性率待查證 |

### G. 後端在哪裡套用判定

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| G1 改 `compute_signals`，讓它接收判定、在內部拒算 | 所有消費端自動一致 | 排程台、回測等本 ADR 範圍外的消費端會被**靜默**改變行為，越過第 7 節的邊界，也可能牽動 ADR-0040 的 engine 零差異約束 | 範圍外的行為改變沒有經過審查 |
| **G2（採用）在呼叫端用單一函式套用；`build_advice` 的判定參數必填** | 每個消費端的處置都明示；範圍外的消費端不受影響 | 新增的消費端可能忘了套用 | 用必填參數加 AST 測試擋（K-11） |

## Decision（決策）

### 1. 單一判準 `bars-verdict-v1`

**1.1 結果狀態**（前後端同名）：
- `usable`
- `unusable`：附原因列表，每筆含 date、field、code
- `gap`：附疑似跳空的相鄰對列表，依日期遞增；每筆含 (d₋, d)、觀測變動、是否有已知事件。字面要用的 `{d}`、`{x}`、`{k}` 依 RC-767 方案 P，取最近一筆
- `empty`：0 根

**1.2 判定順序固定**：
1. 0 根 → `empty`；
2. 整批套用 V 規則，任一根違反 → `unusable`；
3. 市場是 TW 才套用 G 規則，有疑似跳空 → `gap`；
4. 否則 → `usable`。
- 非 TW 市場永遠不判 `gap`。

**1.3 欄位層級規則 V**（整批判定；絕不丟掉壞的那幾根、改用剩下的計算）：
- **V-1**：close、high、low、open 都必須是有限數。
- **V-2**：close、high、low、open 都必須 > 0。
- **V-3**：high ≥ low，open 和 close 都落在 [low, high]，**等號放行**。這條和 `quality._check_ohlc_consistency` 是同一套定義。
- **V-4**：volume 必須存在、是有限整數，而且 ≥ 0；缺值或空字串判 `unusable`。這和後端 `PriceBar` 的驗證一致（`interface.py:65,77-82`）。
- **V-5**：日期嚴格遞增，不得重複。
- **V-6（明定不納入）**：未來日期、幣別不符、資料新鮮度。

**1.4 跳空規則 G（只限 TW）**：
- **G-1 常數**：c = 10% + 1%，嚴格大於。新模組自己定義常數，用測試交叉釘住它和 ADR-0016 F7、`sectors/definition.py:69-70` 相等。
- **G-2 精確比較**：對每一對相鄰 bar，判定 |P(d) − P(d₋)| × 100 > 11 × P(d₋)。後端用 `Decimal`，前端用 BigInt 縮放整數。
- **G-3 過渡期前端版**：只用原始收盤價，g 一律取 1。
- **G-4 登記後後端版**：照 [Q] δ-1 第 1～4 步（已知除權息事件改比參考價、因子不可用直接判疑似、g ≥ 2 用次方換算、日曆查不到時 g 取 1）。
- **G-5 適用與例外**：照 [Q] δ-3，查證之前一律照常套用。US 和 ^TWII 不適用。

**1.5 唯一來源與對齊方式**：
- 規範來源是本節條文；參考實作是登記後的後端模組（2.1）；前端唯一的實作是 `app/lib/dailyBarsUsability.ts`。
- 對齊方式：
  - (a) **golden fixture**：過渡期放在 `apps/stock-desk/frontend/app/lib/__tests__/fixtures/`；登記前**不得**放進 `shared/`。登記後搬到 `apps/stock-desk/shared/`，前後端都讀同一份檔，並釘住 SHA。
  - (b) 兩端都匯出 `BARS_VERDICT_VERSION = "bars-verdict-v1"`，契約測試斷言兩者相等。
  - (c) 判準任何一處變動，版本號就要升，fixture 也要同步更新，然後送風控。
  - (d) 登記後，前端最終採用的判定是兩端之中較嚴的那個，嚴格程度由嚴到寬是 **`unusable`＝`empty` ＞ `gap` ＞ `usable`**。`empty` 和 `unusable` 同屬不可用。兩端都屬不可用時，只有前端這批是 0 根才用 `empty`，其餘一律用 `unusable`。`gap` 只採後端的結果。

**1.6 `computeKeyLevels` 的 null 契約**：
- 判定狀態 ∈ {`empty`、`unusable`、`gap`} 時回 null，其他狀態絕不回 null。`gap` 這一項依 RC-804。
- 這個變動和日後任何再變動都要送風控（RC-882 第 2 點），由 F-T2 鎖住。
- `gap` 時，關鍵價位和進場觀察只能出現 W-2、W-3 的 gap 版，**不得**出現 RC-860 的「沒有可用日線」句。由 F-T9 鎖住（RC-903 第 4 點）。

### 2. 後端處置（登記後才實作，依 [CEO]）

**2.1 判定模組**：
- 新套件，名稱暫定 `app/barverdict/`，提供 `evaluate_daily_bars(bars, *, market, events, calendar) -> DailyBarsVerdict`，並匯出 `BARS_VERDICT_VERSION`。
- 不得寫在 `PriceBar`、`freshness.py`（見 Context 6(c)），不得 import `app.dirdef`、`app.sectors`、`app.data.session_calendar`，也不得被 Context 6(c) 那兩層的模組 import。
- V-3 呼叫 `quality.py` 公開化之後的 OHLC 一致性函式。這個函式就是現有的 `_check_ohlc_consistency`，改名公開，判斷邏輯不變。`quality.py` 已查證不在 digest 範圍內（[DL2]），可以修改。
- `quality.py` 維持「只偵測、只回報」，要不要拒算由判定模組決定。

**2.2 套用位置（採 Options G2）**：
- 在 api 層呼叫端套用：`api/bars.py`、`api/signals.py`、`api/advice.py`，以及另一支 PR 的 `alerts/snapshot.py`。
- 由同一個函式 `apply_bars_verdict(signals, verdict)` 把受影響的欄位改成 None 並附原因代號。
- `compute_signals` 不改。`app/signals/*` 已查證不在 digest 範圍內，所以這純粹是設計取捨。理由見 Options G：改在內部，會靜默改變第 7 節範圍外消費端的行為。

**2.3 各 endpoint**：
- `/api/bars`：維持 ok ⇔ 至少一根；新增 `bars_verdict` 欄位，只是附加，壞值時照樣回傳原始 bars。
- `/api/signals`：帶同一個 `bars_verdict`。`unusable` 時各指標回 `insufficient_data` 並附原因代號；`gap` 時依 2.5 逐欄位處理。
- `/api/advice`：在同一批 `loaded.bars` 上算判定，回應帶 `bars_verdict`。F-1 的最新收盤價守門（`advice.py:207`）保留。

**2.4 建議卡狀態（S1 或 S2，由 CEO 決定，見第 8 節）**

S2 的內容：
1. `unusable`：整批算出來的欄位（`FIELD_LABELS` 裡除了 `position.*` 以外的全部欄位）一律改成 None，原因代號 `daily_bars_unusable`。
2. `close` 只在最新一根本身通過全部 V 規則時保留，否則改成 None，走既有的 `insufficient_data` 路徑。依 [DL2] E 節，保不保留 close 都不會讓可評估的規則數增加，保留只是為了上限計算。
3. cap 4 的 ATR 跟著改成 None，走 ADR-0023 的 not_evaluable 路徑。
4. **引擎閘門（依 RC-905 第 1 點改寫）**：`build_advice` 新增 keyword-only 而且必填的 `bars_verdict` 參數。判定不是 `usable` 時：
   - (i) **至少一條防禦型規則命中**：輸出防禦方向內權重最重的動作，平手依 `ACTION_PRECEDENCE`。不論建構方向或中性方向的權重是否更重，都照這個規則輸出。`confidence` 上限為 `low`。
     - 這是對 RC-905「照現有的優先順序輸出防禦型動作」的讀法，**待風控確認**。
   - (ii) **其他所有情形**一律輸出 `insufficient_data`：0 條命中、只有中性規則命中（例如只有 `concentration_watch` 或 `volume_spike_watch`）、有建構型命中、建構型加中性。
   - (iii) `matched_rules`、`skipped_rules`、`limits_check`、`action_weights`、`direction_weights` 照常列在卡上，供追溯。
   - (iv) `quantity_range` 回 None。這是 tech-architect 新增的，比 RC-900 第 6 點只要求前端不顯示更嚴，**待風控確認**。
   - (v) 後面各道閘門（防禦降級、上限阻擋、預算預設）只作用在 `add`，而 (i)、(ii) 之後不會再有 `add`，所以照舊不需另外處理。
   - (vi) **呼叫端**：B-2 的 PR 說明要列出 `build_advice(` 在 `backend/app` 底下的全部呼叫端，包括 api、alerts snapshot，以及排程台、回測、事件研究裡如果有的話。每個呼叫端要嘛傳入真實判定，要嘛依第 7 節書面列出豁免依據。**不得寫死傳 `"usable"`**（K-11）。
5. 被跳過的規則，原因代號用 `daily_bars_unusable` 或 `corporate_action_suspected`，不得併入「缺少輸入欄位」（K-9）。原因字面是 W-9；`AdviceCardView.tsx:263` 的「因資料不足被跳過的規則」標題要一起送風控。

**S2 轉 accepted 之前要成立的前提（RC-905 第 4 點）**：
- (a) 上面第 4 點已寫入。（本版已寫入）
- (b) **待查前提**：`position.weight` 用的估值價格，是不是同一根壞掉的最新 bar（`app/portfolio/valuation.py`，dev-lead 並行查證中）。如果是，`concentration_watch` 也要拒算，S2 就只比 S1 多一份上限清單；查證結果出來後，以本 ADR 的補充更新。
- (c) 卡片因判定而變成 `insufficient_data` 時，前端走 `no_action` 分支，決策卡目前不畫上限區塊（`DecisionCard.tsx:442-445`）。F-4 要決定上限違規句是否仍留在主視圖，送風控。
- (d) 第 5 點的跳過原因，連同 W-9 和 `AdviceCardView.tsx:263` 的標題，送風控審。

**如果 CEO 選 S1**：判定不是 `usable` 時，整張卡回 `insufficient_data`、`advice=None`，`reason` 帶判定的原因代號，字面用 W-16，要說明是歷史日線有誤，不得沿用「資料不足，無法計算。」這類籠統句。第 1～5 點和 S2 的前提都不適用。

**2.5 跳空的逐欄位時距 H_f 與邊界**：
1. 只有可疑的那一對落在某欄位的有效範圍內，該欄位才拒算。不截斷視窗，也不只用事件之後的子視窗。
2. **邊界（明文規定）**：
   - 記號：
     - 視窗是 t₀ < … < tₙ，tₙ 是最新一根；
     - 可疑的那一對是 (t_{j−1}, t_j)，k = n − j，也就是可疑那一天之後還有幾根；可疑那一天就是最新一根時 k = 0；
     - R_f 是欄位 f 在 tₙ 的計算**實際讀到**的 bar 索引集合，包括 TR、漲跌幅所需的前一根收盤。
   - 規則：**{j−1, j} ⊆ R_f 時，該欄位受影響**。只讀到其中一根不算。例如均線視窗剛好從 t_j 開始，視窗內全是事件之後的價位，就不算受影響。
   - R_f 是連續視窗 [n − W_f + 1, n] 時，等價於 **k ≤ W_f − 2**。例如：MA20 的 W = 20，k ≤ 18 受影響；MA60 的 W = 60，k ≤ 58 受影響。
   - W_f 以實作實際讀到的範圍為準，不以指標名稱推定。由 B-4 的性質測試釘住：擾動第 i 根，欄位值會改變 ⇔ i ∈ R_f。
3. 遞迴類（Wilder RSI、Wilder ATR、MACD 的 EMA、KD 平滑）在 H_f 凍結之前，R_f 視為整個視窗；回撤一律是整個視窗。凍結的公式照 [Q] δ-5，數值等 dev-lead 用測試驗證「殘餘影響 < 1%」之後，以本 ADR 補充凍結。
4. 依第 2 點的邊界，[DL2] F 節「完整度剛好 0.5」那種情形對 `add` 已經沒有影響，因為 2.4 第 4 點 (ii) 判定不是 usable 時一律不輸出 `add`。邊界仍會影響防禦規則可不可以評估，所以 B-2 的測試照第 2 點的精確定義放置可疑的那一對（見 6.1）。
5. `unusable` 不做逐欄位處理，一律整批拒算。

**2.6 `data_completeness` 與版本**：
- 採 D1，定義不改。
- `evaluation` 新增 `bars_verdict_status` 和 `bars_verdict_version`（RC-905 第 3 點 (a)）。
- **不升 `rules_version`**：ADR-0004 的 `rules_version` 是規則 YAML 的 semver，本 ADR 不改規則檔。畫面印的是「本評估由固定規則集（版本 X）計算」，沒改規則檔卻升版，反而會誤導使用者以為規則變了。
- 判定為 `usable` 時，輸出由回歸鎖保證和現況逐欄相同（6.1）。
- 引擎行為的變動記在本 ADR 末的「變更紀錄」（RC-905 第 3 點 (b)）。

**2.7 `_as_float` 與 `last_defined`**：
- `_as_float` 遇到非有限值回 None（`context.py:97-101`）。
- `signals/frame.py:97-102` 的 `last_defined` 不改。它已查證不在 digest 範圍內，所以不改的理由是設計取捨：
  - 判定拒算加上 `_as_float` 過濾，就足以擋住 advice 這條路徑；
  - `/api/signals` 在 `unusable` 時已整體回 `insufficient_data`；
  - 改 `last_defined` 會影響範圍外的消費端。

**2.8 候選卡覆蓋度句（F-4）**：採 S2 的話，「因依賴持倉資料而被跳過」這個成因會變成假話，因為被跳過的大多是壞日線造成的。F-4 要改寫並送風控（RC-901 第 3 點 (d)）。

### 3. 動能、量能、規則三類的跳空處理（RC-882）

| 類別 | 過渡期（前端，判定 = `gap`） | 登記後（後端判定加 H_f） |
|---|---|---|
| 動能（RSI） | 一律 unavailable，由 `gap` 直接關閉閘門 | 依 2.5 判斷受影響時拒算，指標狀態帶 `corporate_action_suspected` |
| 量能（volume z） | 一律 unavailable，做法同上 | 依 2.5 判斷受影響時拒算；已知的配股或分割日也拒算 |
| 規則（防禦型沒有命中） | 一律 unavailable，做法同上 | **採 (b)**：`evaluation.skipped_rules` 裡只要有任何一條規則的原因是 `daily_bars_unusable` 或 `corporate_action_suspected`，就判 unavailable，不論那條規則是什麼方向 |

**為什麼選 (b)、不選 (a)「跳過項目補上 `action` 欄位」**（RC-907 第 2 點）：
1. `direction_weights` 只彙總命中的規則，跳過項目也沒有 `action`。(a) 要改 API 加欄位，只能放在 F-4；(b) 不改 API，B-2 就能落地。
2. (b) 不必在前端推斷被跳過規則的方向。規則集改版、方向對應改變時，也不會失準。
3. 以現行規則來看，兩條回撤規則（防禦型，R_f 是整個視窗）在 `gap` 時一定被跳過，所以 (a) 能多分辨出來的「只有非防禦規則被跳過」，在 `gap` 下不存在；在 `unusable` 下，所有歷史欄位都被跳過，也一樣不存在。
4. 兩者都是 fail-closed。代價是：日後如果出現只跳過中性規則的情形，(b) 會多判 unavailable。

### 4. 入場閘門與共用判定的介面（過渡期）

- 採 E(ii)：`DailyBarsUsability` 新增 `empty`、`gap`。
- `isBarsGateOpen` 只收判定一個參數，只有 `status === "usable"` 才開啟，拿掉 `levels`。
- **窮舉處理**：所有讀 `DailyBarsUsability.status` 的消費端，都用窮舉的 switch 加 `never` 檢查；runtime 遇到未知值的 default 分支比照 `unusable` 處理，不得落到 usable 的畫法（RC-900 第 8 點）。
- `entryObservation.ts:69-72` 換成新註解，**必須保留以下語意**（RC-904 第 3 點）：
  - (a) 允許清單：null、undefined、未知狀態都關閉；
  - (b) `empty` 是直接訊號；
  - (c) `gap` 依本 ADR 第 3 節關閉，不是由 `computeKeyLevels` 順帶決定；
  - (d) 這個檔不掃描任何 bar 值；
  - (e) 後端狀態只能讓結果更嚴；
  - (f) 後端修好之後閘門照樣保留，`:141-148` 那段不得刪。
- `dailyBarsUsability.ts:13-19`（「消費端判斷 `=== "unusable"`」）和 `:37-40`（「空陣列視為 usable」）兩段註解都要改寫，否則會和新契約矛盾。新註解要寫明入場閘門刻意採用允許清單。
- 兩處長度檢查保留，當雙重防線：
  - `DecisionCard.tsx:410-415` 的 `bars.length > 0`（RC-842 第 2 點）在 F-2 保留；要拿掉，必須在 F-2 裡單獨列出並送風控。
  - `computeKeyLevels` 自己的 `bars.length === 0` 檢查保留。
- 共用函式的簽名改成 `evaluateDailyBarsUsability(bars, market)`。

### 5. 前端過渡期（登記前可做，只動 `apps/stock-desk/frontend/`，符合附記四類 A）

**5.1 呈現矩陣**。表中「不變」表示和現在的 head 逐字、逐結構相同。「不可用」指 `unusable` 或 `gap`；`gap` 一律用各 W 的 gap 版。

| 呈現面 | `usable` | `unusable` | `gap` | `empty`／null |
|---|---|---|---|---|
| 技術分析區（`page.tsx`） | 不變 | 不變（RC-695） | K 線保留；指標數值、疊加線、指標卡、一句結論都不顯示；附 W-1 | null：不變；`empty`：收起，沿用 `TECHNICAL_SECTION_NO_DATA_STATEMENT`（RC-900 第 10 點核可） |
| 關鍵價位（`KeyLevelsPanel`） | 不變 | 不變 | 不計算，只附 W-2，不得出現 RC-860 的句子 | 不變 |
| 進場觀察六條 | 不變 | 不變（PR-β） | 六條都是 unavailable；面板只用 W-3，不得出現 RC-860 的句子 | 不變 |
| **持有卡**：決策卡標題、操作摘要標題（T2） | 不變 | 動作屬 defensive（從 `direction_weights` 讀），標籤保留，附現行第二行和 W-6；其他情形（含方向未知），標題換成 W-4，決策卡第二行改用 W-11 | 同左，gap 版 | 不變 |
| **候選卡**（`kind === "candidate"`）的組成句（T3） | 不變 | `compositionText` 加 `supportiveDisclaimer`，以及 `notSupportiveText`，一律換成 W-10。「進場評估」、未持有徽章、`UnvalidatedNotice` 保留。決策卡 `MainSlot` 和操作摘要 `SummaryBody` 兩處都改 | 同左，gap 版 | 不變 |
| 「依據：{規則名}」行連同回撤附註（`OperationSummaryPanel.tsx:298-308`）、決策卡失效條件行連同揭露句（`DecisionCard.tsx:571-590`）、`RULE_SOURCE_CHIP` | 不變 | 標題被換掉時（持有非防禦型、候選卡）**都不顯示**；防禦型標籤保留時**照常顯示** | 同左 | 不變 |
| 操作摘要 `<details>` 內的反面論點和失效條件清單 | 不變 | 保留，由 W-6 加註涵蓋 | 同左 | 不變 |
| **數量區間**（任何顯示 `quantity_range` 的地方），以及 `restoresComplianceWarning` | 不變 | **一律不顯示**，不論方向；改顯示 W-5。違規本身仍由 `LimitNoticeBlock` 顯示 | 同左 | 不變 |
| 建議卡 summary 的「命中 N 條」（`page.tsx:580`） | 不變 | 不顯示數字，改顯示 W-7 | 同左 | 不變 |
| 建議卡 details 的評估那一行（`AdviceCardView.tsx:254-259`） | 不變 | 整行不顯示，改顯示 W-8；候選卡同樣處理 | 同左 | 不變 |
| 建議卡「命中規則（N 條）」標題，以及 0 條時的「目前沒有規則命中。」（`AdviceCardView.tsx:172-175`） | 不變 | 不顯示數字，也不顯示「目前沒有規則命中。」，改用 W-12（W-7 系列） | 同左 | 不變 |
| 建議卡本體最上方的說明行 | 不存在 | 加一行 W-13，放在卡片本體，不得包在 `<details>` 裡。命中規則清單、方向權重、跳過清單保留，當作防禦標籤的追溯依據 | 同左 | 不存在 |
| 上限清單（`LimitsCheckList`）的 cap 4（依 ATR）那一列 | 不變 | 不得顯示為通過，改成無法評估，或附 W-14；其他各列不變 | 同左 | 不變 |
| 候選卡頁尾的覆蓋度句（`adviceWording.ts:181-187`，經 `operationSummary.ts:396-399,448` 進到 `PageFooterDisclosures`） | 不變 | 不顯示百分比，改用 W-15 | 同左 | 不變 |
| **任何狀態、任何方向都必須照常顯示**：`UnvalidatedNotice`、`OPERATION_REFERENCE_DISCLAIMER`、`StaleDataAlert`、`LimitNoticeBlock` 的違規句、`SettingsFallbackNoticeLine` | 不變 | 照常顯示，不得移除或弱化 | 同左 | 不變 |

**5.2 動作方向的判斷**：
- 只從卡片自己的 `direction_weights[].actions` 讀，卡片的 action 沒有出現在任何 defensive 項目裡，就視為非防禦型。
- 防禦型動作只會來自規則命中（`engine.py:366-406`，RC-900 已核對），所以這條規則不會誤傷真的防禦訊號。

**5.3 PR 切分與期限（RC-902）**：
- **F-1**：5.1 表中 `unusable` 欄的全部內容，含 RC-900 第 2、3、6 點和 RC-901 第 3 點。只用現有的 `usable`／`unusable` 判定。
  - **觸發檔案**：`AdviceCardView.tsx`、`page.tsx`、`DecisionCard.tsx`、`OperationSummaryPanel.tsx`、`operationSummary.ts`、`adviceWording.ts`、`oneLinerWording.ts`、`decisionCardWording.ts`、`LimitsCheckList.tsx`、`PageFooterDisclosures.tsx`。F-1 必須是下一支動到其中任一支檔的 PR。
  - **絕對期限**：不論有沒有其他 PR 碰到觸發檔案，F-1 最晚要在 F-2 或 F-3 開分支之前合併。
  - W 字面還沒定稿時，碰到觸發檔案的 PR 不得搶先合併，要等 F-1。
  - 決策卡整卡快照（RC-874）要隨 F-1 進來，在改動之前產生基準；沒有風控核可，不得 `-u`。
  - F-1 不夾帶其他語意，numstat 要能逐檔對帳。
- **F-2**：V-3～V-5、`empty` 狀態、閘門改成直接訊號、窮舉 switch、RC-873 鎖、RC-882 第 3 點的契約鎖、golden fixture。F-2 進來時要重跑 F-T7。
- **F-3（就是 PR-γ／H1）**：`gap` 狀態和 5.1 表中 `gap` 欄的全部內容、(g) 的測試、F-T9。
- F-2 最晚要和 F-3 一起進來。

**5.4 預期會改的檔**（實作前由 frontend-engineer 用 grep 確認）：
- `app/lib/` 底下：`dailyBarsUsability.ts`、`keyLevels.ts`、`entryObservation.ts`、`entryObservationWording.ts`、`oneLinerWording.ts`、`decisionCardWording.ts`、`operationSummary.ts`、`adviceWording.ts`
- `app/position/[symbol]/` 底下：`page.tsx`、`DecisionCard.tsx`、`OperationSummaryPanel.tsx`、`AdviceCardView.tsx`、`KeyLevelsPanel.tsx`、`LimitsCheckList.tsx`、`PageFooterDisclosures.tsx`
- 以及對應的測試
- `adviceWording.ts` 只能新增 W 常數，以及提供給呼叫端的選擇函式；`HELD_ACTION_LABELS` 和既有的已核可字面不改。

**5.5 必須零差異**：
- `app/lib/api.ts`、`queries.ts`、`types.ts`、`ruleDirection.ts`、`indicatorBands.ts`
- `apps/stock-desk/shared/`、`apps/stock-desk/backend/`、任何 `.py`
- `__snapshots__/`：沒有風控核可，不得 `-u`

**5.6 W 編號表**（連號；gap 版是同一個編號的變體，不另外編號）

| W | 呈現面 | 出處 |
|---|---|---|
| W-1 | 技術分析區 gap 說明 | 5.1 |
| W-2 | 關鍵價位 gap 說明 | 5.1 |
| W-3 | 進場觀察面板 gap 版 | 5.1 |
| W-4 | 持有卡非防禦型的標題替代句（決策卡、操作摘要） | 5.1 T2 |
| W-5 | 數量區間不顯示時的說明，不得借用「未提供股數」或 Q-a、Q-b | 5.1，RC-900 第 6 點 |
| W-6 | 操作摘要的附加說明（防禦標籤保留時；涵蓋 `<details>` 裡的反面論點和失效條件） | 5.1 |
| W-7 | 建議卡 summary 命中數的替代句 | 5.1 |
| W-8 | 建議卡 details 評估那一行的替代句 | 5.1 |
| W-9 | 後端跳過原因，連同 `AdviceCardView.tsx:263` 的標題 | 2.4 第 5 點 |
| W-10 | 候選卡組成句的替代句（T3） | 5.1 |
| W-11 | 標題被換掉時，決策卡第二行的版本 | 5.1 |
| W-12 | 「命中規則（N 條）」和「目前沒有規則命中。」的替代句（W-7 系列） | 5.1，RC-901 第 3 點 (a) |
| W-13 | 建議卡本體最上方的說明行 | 5.1，RC-901 第 3 點 (b) |
| W-14 | cap 4 列無法評估的說明 | 5.1，RC-901 第 3 點 (c) |
| W-15 | 候選卡頁尾覆蓋度句的替代句 | 5.1，RC-901 第 3 點 (d) |
| W-16 | 採 S1 時的 `reason` 字面，只在 CEO 選 S1 時需要 | 2.4 |

- F-1 要用的是 W-4～W-8、W-10～W-15，優先起草。

**5.7 登記後前端保留**：後端修好之後，前端的 T2、T3 和 5.1 各格處置照樣保留（RC-865 第 1 點、RC-900 第 9 點）；要拿掉，必須另外送風控。

### 6. 測試

**6.1 dev-lead 列的 13 項，以及後端的其他測試（全部放在登記後的後端 PR）**

| # | 內容 | PR | 備註 |
|---|---|---|---|
| 1～3、5、6 | ok ⇔ 有日線、FRESH 加空陣列、無來源／被拒絕／區間外、PriceBar 的 finite 和 volume 驗證、快取 NaN 列 | B-1（先寫特性測試） | 只釘住現況 |
| 4 | 最新收盤價為 0 時的不對稱 | B-1 先釘住現況，B-2 改成新的預期 | 新預期：`/api/bars` 是 ok 加 `unusable`；`/api/advice` 是 `insufficient_data` |
| 7、11、13 | 完整度的定義、候選卡最高 11/12、「沒命中就是續抱」的來源 | B-1 釘住；B-2 改寫第 13 項在判定不是 usable 時的預期 | — |
| 8 | context 出現 NaN／Inf | B-2 | — |
| 9、10 | 持有卡由 reduce 翻成 hold；壞值位置 × 欄位的參數化，含 RC-883 第 3 點的兩項 | B-2 | 依 CEO 選 S1 或 S2 定預期 |
| 12 | `/api/bars` 和 `/api/advice` 的判定一致 | B-2 的目標測試（現在會紅） | — |

- **RC-905 的組合測試（B-2，required）**：
  - 命中組合：{0 條命中、只有中性命中、只有建構型、建構型加中性、只有防禦型、防禦型加建構型、防禦型加中性}；
  - 判定狀態：{`unusable`、`gap`}；`gap` 依 2.5 第 2 點的精確邊界，放在讓完整度分別為 1/12、3/12、6/12 的三個位置，並各加一則邊界差一根的案例（k = W_f − 2 和 k = W_f − 1）。
  - 斷言：只有含防禦型的組合輸出防禦型動作，而且信心 ≤ low；其他組合都是 `insufficient_data`；命中、跳過、上限清單照列；`quantity_range` 是 None。
- **其他後端測試**：
  - golden fixture 契約測試；G-1 常數交叉相等；
  - OHLC 函式公開化前後結果相同；`apply_bars_verdict` 不改動輸入物件；
  - H_f 性質測試（B-4，2.5 第 2 點）；
  - 判定為 `usable` 時，引擎輸出和現況逐欄位相同（回歸鎖）；
  - `evaluation` 帶 `bars_verdict_version`；
  - K-11 的 AST 測試。
- 不在登記前加後端特性測試（理由同原稿：會加重 Q-2 的歸類負擔，也不符合 [CEO] 的意圖）。

**6.2 前端過渡 PR（vitest）**：
- **F-T1（RC-873）**：把九個禁用詞套用到 `dailyBarsUsability.ts` 所有匯出的字串常數，只掃常數值。
- **F-T2（RC-882 第 3 點）**：`computeKeyLevels` 回 null ⇔ 判定 ∈ {`empty`、`unusable`、`gap`}。
- **F-T3**：V 規則逐條正反例，含 volume 缺值和空字串（預期 `unusable`），以及 O = H = L = C 判 `usable`。
- **F-T4**：G 規則的 11% 邊界、非 TW、判定順序。
- **F-T5**：閘門簽名只有一個參數、允許清單；`gap`、`empty`、`unusable`、null、undefined、未知值都關閉；(g) 的 gap 案例；「ok 加 []」。
- **F-T6**：golden fixture 和 `BARS_VERDICT_VERSION`。
- **F-T7**：5.1 矩陣逐格測試。
  - fixture：持有 `hold`／medium／12/12/0/1.0、候選 `add`／12/11/1、持有 `reduce`、被降級的 `hold`、`take_profit`、`stop_loss`、持有 `add`、只有 `concentration_watch` 命中的 `hold`（斷言標題被換掉）。
  - 每格都斷言 5.1 最後一列的五個元素仍然存在。
  - `usable` 時逐字和現況相同。
  - F-2 進來時要重跑。
- **F-T8（RC-874）**：決策卡整卡快照。
- **F-T9（RC-903 第 4 點）**：`gap` 時關鍵價位和進場觀察只出現 W-2、W-3，不出現 RC-860 的句子（渲染測試）。
- **F-T10（RC-908 第 2 點）**：`ruleDirection` 和 `operationSummary.ts:189` 的 `DEFENSIVE_ACTIONS` 在五種動作上的結果相同。
- **e2e**：qa-e2e 在 375 和 1280 兩種寬度，涵蓋 5.1 每一欄。

### 7. 不在本 ADR 範圍

- **排程台**：要套用本判準，必須另立 ADR 申請 ADR-0040、N172-C3、C-B11 的豁免。排程台如果呼叫 `build_advice`，要依 2.4 第 4 點 (vi) 書面列出豁免依據。
- **回測、事件研究**：處置方式照 [Q] δ-5 的方向，另以補充定案；如果它們呼叫 `build_advice`，處理方式同上。
- **含息路徑**：交給 ADR-ε。

### 8. 需要 CEO 決定（照錄 RC-906 替代題目；AskUserQuestion，一題）

- **送出條件**：coordinator 先確認 2.4 第 4 點已照 RC-905 第 1 點寫入，而且風控已核對修訂段落。沒有採納的話，選項二的「標題一樣顯示資料不足，不會給續抱或加碼」就不成立，必須退回風控重寫。
- header：`日線錯價處理`
- question：`正式登記之後修後端時，如果某支股票過去的日線混進一筆明顯錯誤的價格（例如某天收盤價是 0），個股頁的建議卡要怎麼處理？`
- options：
  1. label：`整張卡只說資料不足`
     description：`只要歷史價格裡有錯，整張建議卡就不給任何結論，只說資料不足。連帶這張卡上的風險上限檢查清單（例如持股比重有沒有超過你設的上限）也不會出現。做法最單純、要改的地方最少；代價就是這份上限清單會從這張卡上消失。兩案都不會再在資料有錯時給出「續抱」結論或「資料完整度 100%」；正式登記前，個股頁兩案的處理相同。`
  2. label：`只停掉要用歷史價格的判斷`
     description：`要用到歷史價格的判斷全部不出，卡片註明是因為資料有誤而沒有評估；標題一樣顯示資料不足，不會給續抱或加碼。多保留下來的只有兩樣：風險上限檢查清單（其中依近期波動計算的那一條同樣無法評估），以及持股比重偏高的提醒。以現在的規則來看，12 條裡只有這條比重提醒不靠歷史價格，而它會不會也被同一筆錯價影響還在查證，所以實際多保留的東西不多；代價是要改的地方比較多、比較容易出錯。正式登記前，個股頁兩案的處理相同。`
  3. label：`先不決定`
     description：`後端這部分修正會停在設計階段，等你決定後才開工。正式登記前，個股頁照樣先用前端的過渡處理：歷史價格有錯時，不把「續抱」「加碼」和「命中 0 條」「資料完整度 100%」當成正常結果顯示，減碼、停損類的提醒保留並加註可能受影響。但後端算出來的結論本身維持原樣，個股頁以外會用到這份結論的地方沒有這層處理，而且這個狀態會一直延續到你做決定為止。`

## Consequences（後果）

**好處**
- 前後端對「日線可不可用」只有一套規範。
- 「壞資料卻顯示續抱參考、命中 0 條、完整度 100%」這條路徑，前端在登記前就能關掉，包括命中規則標題、cap 4、候選卡組成句和頁尾覆蓋度句這些換了位置的同類內容；後端在登記後根除。
- 判定不是 usable 時，後端只可能輸出防禦型動作或 `insufficient_data`，不可能輸出續抱或加碼。
- 入場閘門不再依賴另一支函式的實作細節。

**代價與壞處**
- **過渡期偽陽性（RC-908 第 1 點，交 PM）**：遇到分割或大額除息，關鍵價位、停損參考和指標可能連續約 540 天被收起。W-1、W-2 要讓使用者知道原因。
- **O3 和 V-4、V-5 會讓更多批次被判為不可用**。頻率查證暫緩，由 PM 追蹤；要放寬只能走 `bars-verdict-v2`，送風控。
- **T2**：留下的防禦標籤也可能來自壞值，靠 W-6 加註緩解；數量區間一律不顯示，避免用壞資料給出看似精確的股數。
- **S2 的實際收益很小**：持有卡最多 1/12，候選卡 0/12；還取決於前提 (b)、(c)。
- **規則條件採 (b)**：日後如果只跳過中性規則，也會多判 unavailable。
- 快取跳過 NaN 列造成 g = 2、門檻放寬，殘留的漏判照 [Q] δ-4 揭露。

**約束（逐條可檢查，交給 qa-reviewer）**
- K-1：前端只有 `dailyBarsUsability.ts` 一份 V 和 G 的判定。
- K-2：登記前任何 PR 的 diff 都不得含 `apps/stock-desk/backend/`、`apps/stock-desk/shared/` 或 `.py`。
- K-3：`isBarsGateOpen` 只收判定一個參數，而且是允許清單寫法。
- K-4：`computeKeyLevels` 的 null 條件 = {`empty`、`unusable`、`gap`}，由 F-T2 鎖住。
- K-5：import 圖測試沿用 `tests/import_graph.py` 的 `reachable_app_modules`／`offenders`，明列 `app.data.quality`、`app.signals`、`app.advice.context`、`app.advice.engine`、`app.barverdict` 都不得被 digest 範圍連到；`app.barverdict` 也不得 import `app.dirdef`、`app.sectors`、`app.data.session_calendar`。
- K-6：`compute_signals` 零差異；`interface.py`、`freshness.py`、`banned_phrases.py` 零差異。
- K-7：G-1 的常數交叉釘住；比較是十進位精確運算，用嚴格大於。
- K-8：`/api/bars` 維持 ok ⇔ 至少一根；`bars_verdict` 只是附加欄位。
- K-9：跳過原因用原因代號，不併入「缺少輸入欄位」，不得記為 quiet。
- K-10：5.5 列的檔案零差異；快照沒有風控核可不得 `-u`。
- K-11：`build_advice` 的 `bars_verdict` 是 keyword-only 必填參數，沒有預設值；AST 測試斷言 `backend/app` 裡沒有任何呼叫端傳字面值 `"usable"`；豁免的呼叫端列在第 7 節。
- K-12：前端讀 `DailyBarsUsability.status` 的地方都是窮舉 switch，有 `never` 檢查，default 分支比照 `unusable`。
- K-13：判定不是 usable 時，5.1 最後一列的五個元素都存在（F-T7 斷言）。

## 與既有 ADR 的關係

- **ADR-0030 補充六附記四**：不衝突。前端過渡 PR 屬於類 A；後端的 B 系列在登記之後才做。新模組和本 ADR 會改的後端模組都不在 digest 的兩層內（Context 6(c)）。
- **ADR-0030 的 `rules_version`**：依 grep，`:143`、`:151`、`:212` 指的是預測紀錄帳 claim 的規則版本，也就是 outlook 規則檔（補充六第 6 點 (d) 的 `h3.yaml`、`h5.yaml`），和 advice 的 `default.yaml` 無關。advice 引擎也不在 digest 內。所以本 ADR 不需要在預測紀錄帳另外記錄判定版本（RC-905 第 3 點 (c)；我沒有讀這幾行的上下文全文，屬於推定，請 qa 確認）。
- **ADR-0004（accepted）**：不升 `rules_version`，理由見 2.6，和 RC-905 第 3 點一致。
- **ADR-0016 F7（accepted）**：不衝突，F7 不改。
- **ADR-0040（accepted）**：兩者是不同軸。不改 `is_usable`，也不沿用這個名字。
- **ADR-0021、ADR-0023**：沿用。
- **ADR-ε**：共用因子定義，各自決定。
- 以上若和 accepted ADR 有衝突，一律以 accepted ADR 為準。目前沒有發現衝突。

## 未決事項

- **CEO**：第 8 節（等送出條件成立）。
- **risk-compliance-officer**：
  - 核對本次修訂過的段落；
  - 確認 2.4 第 4 點 (i) 的讀法和 (iv) 的新增；
  - W-1～W-16 的逐字審；
  - F-4 的上限違規句位置（S2 前提 (c)）；
  - 候選卡覆蓋度句的改寫（2.8）。
- **dev-lead**：
  - `position.weight` 的估值價格來源（S2 前提 (b)，並行查證中）；
  - H_f 凍結的數值，以及各欄位實際的 W_f（2.5）。
- **data-engineer**：
  - 各資料源 OHLC（含 open）不一致的頻率（暫緩，PM 追蹤）；
  - [Q] ε-5 第 1、2、5、6 點。
- **product-manager**：
  - 過渡期偽陽性可否接受；
  - F-1 的絕對期限；
  - 追蹤 OHLC 頻率查證。
- **tech-architect**：排程台套用判準的 ADR；回測和事件研究的補充。

## 變更紀錄

- 2026-11-26 第一次修訂：依 RC-900～RC-908、[DL2]。
  - 2.4 第 4 點的引擎閘門改用 RC-905 第 1 點的替代規則；
  - 新增 2.5 第 2 點的 H_f 邊界；
  - `evaluation` 增加 `bars_verdict_version`；
  - 5.1 擴大；W 編號整理成 W-1～W-16；
  - 第 8 節改用 RC-906。
- 引擎行為的變動（判定不是 usable 時的輸出規則）從這次起記在本節；`rules_version` 不升。
```

## 驗證

**這次讀過的檔案**（都在 `/home/user/AICompany/` 底下）

- `work/reviews/2026-11-26-ADR-δ草案行為審查-RC900至RC908-風控.md`，第 1-345 行全文。
- `work/reviews/2026-11-26-ADR-δ前提查證-code_digest-import圖-dev-lead.md`，第 1-124 行全文。
- `work/reviews/2026-11-26-ADR-δ草案-日線壞值與跳空的判定與處置-tech-architect.md`，只讀第 1-40 行，用來確認轉存的就是原稿。
- `docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`：Grep `rules_version`，命中第 143、151、212 行。

**沿用的內容**
- 風控核對過的前端行號，例如 `OperationSummaryPanel.tsx:298-308`、`DecisionCard.tsx:571-590`、`AdviceCardView.tsx:172-175`、`adviceWording.ts:151-153,181-187`，都直接引用 RC-900、RC-901。這些檔我沒有親自讀。
- 引擎各分支的行為，引用 RC-905 和 [DL2] 的推算。

**沒有查證的事項**
- `build_advice` 實際有哪些呼叫端。依限制我不能對 `apps/` 遞迴搜尋，所以寫成 B-2 PR 說明的義務，並由 K-11 測試擋住。
- ADR-0030 第 143、151、212 行的上下文全文。「預測紀錄帳的 `rules_version` 指 outlook 規則檔」屬於推定，已在草案裡標明。
- `position.weight` 的估值價格來源。dev-lead 正在並行查證，草案寫成待查前提。
- 各欄位實際的 W_f。草案只規定判斷規則，數值交給 B-4 的性質測試。

**遵守事項**：沒有寫檔、沒有執行指令；沒有讀 `.env*`、沒有碰 `backend/data/`；沒有對 `apps/` 搜尋。

## 下一步

1. **coordinator**：
   - 把本回報轉存到 `work/reviews/`；
   - 把修訂對照表和修訂後的段落送風控核對：Context 6、Options B／D／G、1.3 V-4、1.5(d)、1.6、2.1～2.8、Decision 3、4、5.1、5.3、5.6、5.7、6、第 8 節、K-5／K-11～K-13、與既有 ADR 的關係、未決事項、變更紀錄；
   - 風控核對通過、而且確認 2.4 第 4 點已寫入之後，才用第 8 節的題目送 CEO。
2. **risk-compliance-officer**：確認對照表第 25 項的讀法和新增，也就是 2.4 第 4 點的 (i) 和 (iv)。
3. **dev-lead**：`position.weight` 估值價格的查證結果送 tech-architect，用來更新 S2 前提 (b)。
4. **creative-lead**：風控核對通過後，照 5.6 起草，F-1 要用的 W-4～W-8、W-10～W-15 優先。
5. **frontend-engineer**：F-1 照 5.3 的觸發檔案和期限做。改動前先產生快照基準。
6. **product-manager**：登記 F-1 的絕對期限、過渡期偽陽性的判斷，以及 OHLC 頻率查證的追蹤。

**相關路徑**
- /home/user/AICompany/work/reviews/2026-11-26-ADR-δ草案-日線壞值與跳空的判定與處置-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-26-ADR-δ草案行為審查-RC900至RC908-風控.md
- /home/user/AICompany/work/reviews/2026-11-26-ADR-δ前提查證-code_digest-import圖-dev-lead.md
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
