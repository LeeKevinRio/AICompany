# 畫面簡潔易懂盤點（product-manager，只讀）

- 日期：2026-11-25
- 對象：`product/stock-desk` 主工作樹的 `apps/stock-desk/`（`frontend/app/` 與後端面向使用者字面）
- 方法：只用 Read、Glob、Grep。沒有改任何檔（本檔是唯一產出），沒有 commit。沒讀 `.env*`、`backend/data/`、`.claude/worktrees/`。
- 守則：不擬新字面。「建議方向」只講改什麼、移到哪、合併什麼。新字面交 creative-lead 起草、risk-compliance-officer 逐字審。
- 字數：「約 N 字」是目測，供排序用，不是量測值。
- 標記
  - 【前端獨立】只動 `frontend/app/`，不動 backend `app/`，可在正式登記前處理。
  - 【後端】要動 backend `app/`（含後端字面）。
  - 【涉及風控核可句，需風控判定】建議合併或移位的對象含風控核可過的句子。本檔不建議刪除任何一句。
- 已在追蹤、只列出處、不重新分析：RC-556 除權息三句（`api/backtest.py:138-155` 一帶 `DIVIDEND_*_NOTE`）、RC-596 殘留 (iii)、RC-652 狀態 E。RC-693、RC-695、RC-650/654 是 CEO 指定的已知例，列在對應類別的開頭，再補同類。

## 範圍說明（誠實揭露沒讀到的）

讀過的：首頁（`page.tsx`、`SummaryCards`、`RiskGauge`、`AlertStatusStrip`、`SectorMomentumCard`）、個股頁（`page.tsx`、`DecisionCard`、`OperationSummaryPanel`、`KeyLevelsPanel`、`EntryObservationPanel`、`TechnicalIndicatorsPanel` 的 chips 與卡頭、`StopQualifier`、`UnvalidatedNotice`）、回測頁（`BacktestForm`、`BacktestReportView`、`EventStudySection`）、設定頁（`SettingsForm`、`KellyInputsSection`、`KellyDisclosuresPanel`）、`frontend/app/lib/*Wording.ts`、後端 `api/backtest.py`、`api/backtest_wording.py`、`advice/limits.py`、`advice/book.py`、`advice/engine.py`、`api/kelly_wording.py`（取樣）。

沒讀完的：`AdviceCardView`／`LimitsCheckList` 本體、`TechnicalIndicatorsPanel` 七張卡內文、`PriceLadder`、庫存頁（只讀 `inventoryWording.ts`，看起來乾淨）、`playbook/`、槓桿專章、`AlertRulesSection`、`DataSourcesSection` 全文、`backend/app/playbook/wording.py`、`api/sectors_wording.py`、`gate_wording.py`。這些可能還有同類問題，下一輪補。

## 對 CEO 的總評（一段）

CEO 每天看到的畫面，句子本身大多合規，問題是三件事疊在一起。一，同一件事在同一屏講兩到四次（個股頁的決策卡與操作摘要幾乎是同一張卡）。二，標示和實際算法對不上，尤其回測頁（H2、H3、M3 都落在這裡）。三，工程詞直接露在畫面上（`verified_on 為 null`、`app/backtest/report.py`、`POST /api/backtest`、`not_evaluable`、`K_observed`）。「預測正確」那一半由 quant 負責，但回測頁上有三處標示會讓 CEO 以為驗證做得比實際完整，這三處我排在 P0。

---

## P0（CEO 可能因此誤判、或看到自相矛盾／壞掉的畫面）

### P0-1　回測「已還原除權息」過度宣稱（對應 quant H2）

- 位置：`backend/app/api/backtest.py:120-124`（`DIVIDEND_ADJUSTED_NOTE`）；呈現在 `frontend/app/backtest/BacktestReportView.tsx:659-680`（notes 清單，預設可見）
- 現行字面：「本回測已還原除權息：價格序列以官方除權息參考價／前一日收盤價為調整因子（交易所未公布參考價時，改以息值／權值回推同一數量）做還原（back-adjustment），報酬已含現金股利與配股，Buy & Hold 對照同步還原。」（約 105 字）
- 問題
  - CEO 讀到「已還原」「報酬已含現金股利與配股」，會理解成整段回測區間的股利都算進去了。實際上除權息資料只從開始同步那天起累積（quant H2），只要區間內有一筆事件就標「已還原」；含配股的事件整筆被略過，文案仍寫「含配股」。
  - 同一格底下的「除權息資料最近同步時間：…」是唯一的線索，但沒有說「同步起點以前沒算」。CEO 不會把兩者連起來。
  - 這句的長度與括號內的工程說明（參考價回推、back-adjustment）也讓人讀不完，而讀不完就只剩「已還原」三個字被記住。
- 建議方向：先由後端決定「已還原」成立的條件（覆蓋整個區間才叫已還原；否則另一種標示，並說明覆蓋起訖與略過筆數）。字面部分交 creative-lead 拆成「結論一句＋覆蓋範圍一句」，括號內的方法說明移進詳細。
- 動到 backend `app/`：**是**（`api/backtest.py`、`dividends/adjust.py`）。不是前端獨立。
- 備註：事件研究共用同一判斷（`api/event_study.py:28,172`），同步處理。

### P0-2　回測的出場規則和個股頁的停損停利用同一個詞「基準價」，其實錨點不同（對應 quant H3）

- 位置：後端 `api/backtest.py:100-109`（`FIVE_CONDITIONS_NOTE`，預設可見於 notes）；前端個股頁 `lib/riskRemediationWording.ts:121-122`、`KeyLevelsPanel.tsx:139,146-147`
- 現行字面
  - 回測：「…收盤跌破「開倉基準價 − 2×ATR(14)」與「開倉基準價 × 0.92」中較緊者（ATR 無法計算時只用後者）、收盤觸及開倉基準價 × 1.2、或收盤低於 MA60，任一觸發即全數出場。以上為本回測的固定衡量設定，不是操作建議。」（整句約 190 字）
  - 個股頁：「停損參考與停利參考以最新收盤 {x}（{d}）為基準計算」「基準價（最新收盤）」
- 問題
  - 兩邊都叫「基準價」，一個是進場當天的價（固定不動），一個是最新收盤（每天上移）。CEO 看到回測寫「收盤觸及基準價 × 1.2」會以為個股頁的「停利參考」就是這樣被驗證的。實際上個股頁的停利永遠高於收盤、不可能被收盤觸及（`keyLevels.test.ts:145` 也釘住這點），而回測的停利是可以觸發的。
  - 這句已經說明「本報告不是該面板六條的歷史表現」（條件那一半），但沒有對出場那一半做同樣的切割。
  - 190 字單句，條件、出場規則、聲明三件事擠在一起。
- 建議方向：最少把「開倉基準價」與個股頁「基準價（最新收盤）」在字面上區分開，並明講「回測錨定進場價，個股頁錨定最新收盤，兩者不同」。這一句要新擬，交 creative-lead，風控逐字審。長句拆成三句（涵蓋哪五條／出場規則／聲明），出場規則移進詳細。
- 動到 backend `app/`：**是**（`api/backtest.py` 字面；quant 另建議 `strategies.py` 錨定與 parity test）。不是前端獨立。

### P0-3　「樣本外（未參與任何參數選擇）」讓回測看起來比實際嚴謹，同頁事件研究卻說自己「不是樣本外」（對應 quant M3）

- 位置
  - 輸入欄：`frontend/app/backtest/BacktestForm.tsx:246`「樣本內天數」、`:259`「樣本外天數」
  - 報告：`BacktestReportView.tsx:704`「Walk-forward 折數：{n}（樣本內取第一折的訓練窗，樣本外為所有折測試窗銜接）」、`:716`「樣本內（in-sample）」、`:725`「樣本外（out-of-sample，未參與任何參數選擇）」
  - 圖：`lib/backtestCurveWording.ts:18`「樣本切分線：左為樣本內，右為樣本外，未參與任何參數選擇」
  - 頁首：`lib/eventStudyWording.ts:39`「…附同期 Buy & Hold 對照與樣本內／外分列結果。」
  - 事件研究（同一頁、後端）：`backend/app/backtest/event_study.py:372,382`「前半（樣本內）」「後半（樣本外）」；`:445-446`「…所以後半不是「模型的樣本外」，只是同一組固定門檻在另一段期間的穩定度檢查。」
  - Kelly 說明（設定頁）：`api/kelly_wording.py:176-181`，已有較誠實的「『樣本外』在本系統中只代表資料的時間區段位置」
- 問題
  - 「樣本內天數／樣本外天數」是輸入欄，CEO 會理解成「用前面 N 天訓練、後面 N 天驗證」，也就是有擬合。實際沒有任何擬合，等於把期間切兩半（quant M3）。
  - 「未參與任何參數選擇」這句本身為真，但放在「樣本外」旁邊，讀起來像是「通過了嚴格的樣本外驗證」。「Walk-forward 折數」更強化這個印象。
  - 事件研究與回測在同一頁，用同樣的「樣本內／外」標籤，一個說「這不是樣本外」，一個說「這是樣本外」。CEO 沒辦法判斷該信哪一個。
  - 沒有任何地方提醒「可以反覆換期間挑出好看的樣本外」（quant 另指出執行無紀錄，那是算法面，不在本檔）。
- 建議方向：全站統一一種說法（時間前後兩段、固定規則、沒有擬合），輸入欄、段落標題、圖例、事件研究四處同步改。這一輪不擬字，交 creative-lead。「Walk-forward」「in-sample」「out-of-sample」英文名詞建議降到詳細。
- 動到 backend `app/`：**部分**。前端獨立可動的：`BacktestForm.tsx:246,259`、`BacktestReportView.tsx:704,716,725`、`backtestCurveWording.ts:18`、`eventStudyWording.ts:39`。要動後端的：`event_study.py:372,382` 的期間名稱與 `kelly_wording.py` 的對齊。標示對齊不用等後端，但事件研究兩個段名不改，同頁仍會自相矛盾，所以兩邊要同批。【涉及風控核可句，需風控判定】`backtestCurveWording.ts`、`BacktestReportView.tsx:725` 都是風控逐字審過的字面。

### P0-4　「壞值／算不出來」被說成「資料不足」或畫出離譜數字（RC-693、RC-695 與同類）

已知例（只列出處）

- RC-693：`lib/entryObservationWording.ts:92`「目前資料不足，六條條件均無法判定。」、`:107`（range 條件的 qualifier）「未滿 60 根日線或區間最高最低價相同時，本條無法判定。」
- RC-695：`position/[symbol]/page.tsx:398-404`，技術分析一句結論 `buildTechOneLiner` 用 `bars.data.bars[last].close` 直接格式化，壞值時印「近 N 根日線，收盤 -1.00。」

同類（新發現）

| # | 位置 | 現行字面 | 問題 |
|---|---|---|---|
| a | `KeyLevelsPanel.tsx:298-299`（觸發：`lib/keyLevels.ts:106`，任何一根 close／high／low 非有限或 ≤ 0，整段拒算） | 「目前沒有可用的日線資料，本面板無法計算任何關鍵價位。」 | 這個面板只在日線 `ok` 時才渲染，所以這句出現時，同一頁技術分析底下的 `page.tsx:456-461` 正在印「共 N 根日線（…）」。同屏一邊說有 N 根、一邊說沒有可用日線，CEO 看不出原因是「其中混有壞值」。 |
| b | `DecisionCard.tsx:349-351`（`levels === null`） | 收盤、停損參考、股數三格直接印「—」，沒有任何原因句 | 程式碼註解已承認：LM-116 的「—」定義只限關鍵價位面板，決策卡這顆「—」沒有解釋（追蹤編號 S-1）。壞值時，決策卡是「—」，技術分析一句結論卻印「收盤 -1.00」，同頁兩種結果。 |
| c | `DataMetaStatusBadge.tsx:128,163`（`status === "unavailable"` 的徽章） | 「資料不足」 | 後端 `unavailable` 是「所有來源都拿不到」，不是「日線根數不夠」。CEO 讀到「資料不足」會想成「歷史太短」，不會想到「來源掛了」。同一個詞又是 `InsufficientPanel`、操作摘要、六項條件的說法。 |
| d | `InsufficientPanel.tsx:9`、`lib/operationSummary.ts:367`、`BacktestReportView.tsx:555` | 後端沒給 reason 時的備援字面「資料不足，無法計算。」 | 備援句沒有原因，卻用「資料不足」當原因。 |
| e | `position/[symbol]/TechnicalIndicatorsPanel.tsx:316,437,462` 的「最新值：…」 | 直接印後端算的 RSI、ATR、z 值 | 視窗中段有壞值時，後端指標照算（quant M1），畫面沒有任何標示。前端做不到，要後端先把壞值擋下來。 |

- 建議方向
  - 同一個「資料有問題」來源，畫面上所有顯示收盤或指標的位置採同一個判斷口徑（前端已有 `computeKeyLevels` 的整段拒算，技術分析一句結論、決策卡、六項條件三處對齊它）。
  - 原因句要分清三種：沒有資料、根數不夠、資料含壞值。新字面交 creative-lead。
  - 決策卡的「—」補原因句：新字面，單項風控確認。LM-117 已明文禁止未經單項確認就搬到決策卡。
  - 徽章「資料不足」改用能分辨「來源取不到」的詞（新字面）。
- 動到 backend `app/`：a、b、c、d 為【前端獨立】；e 為【後端】（quant M1，把 usable 判斷擴到整個視窗）。RC-693／695 本體已在追蹤。

### P0-5　首頁風險儀表第 5 條：主列顯示「通過／已違反」，「算出的數字不可靠」藏在詳細

- 位置
  - 主列：`components/RiskGauge.tsx:167-172`（狀態 chip）、`:183-185`（觀察值／上限）
  - 詳細：`RiskGauge.tsx:102-104` 印 `CAP5_SUNSET_UNRELIABLE_NOTE`（`lib/cap1SunsetWording.ts:43`）
  - 決策卡：`lib/limitNotices.ts:19-29, 81`（第 5 條 `violated` 時照樣列入「已違反第 5 條上限：…」，沒有帶這句）
  - 設定頁：`lib/cap1SunsetWording.ts:31`（`KELLY_SUNSET_LEAD_TEMPLATE`）
- 現行字面
  - 主列：`第 5 條・分數 Kelly 部位上限　[通過]　x%／y%`
  - 詳細才有：「計算方式有誤，算出的數字不可靠。」
  - 決策卡：「已違反第 5 條上限：分數 Kelly 部位上限 {observed}（上限 {threshold}）」
- 問題：「計算方式有誤」（約 12 字）是對這一列最重要的限定，卻只在展開後才看得到。CEO 在首頁和決策卡看到的是一個正常的「通過」或「已違反」，而這個判定連提供者自己都說不可靠。這是「主視圖給的結論」和「詳細裡的但書」方向不一致。
- 建議方向：把已核可的這一句（不新擬）跟著第 5 條的狀態 chip 一起走，也就是移位或加標，而不是留在詳細。決策卡的違反列同理。【涉及風控核可句，需風控判定】：該句是風控日落期間字面表的逐字句，只動出現位置，字面不動。
- 動到 backend `app/`：否。【前端獨立】
- 備註：這項與 RC-596 殘留 (iii) 可能重疊（我沒有該單的內容）。登記時請由 PM 對一下，重疊就併單。

---

## P1（CEO 每天都會碰到，造成負擔或輕度誤導）

### P1-1　個股頁：決策卡與操作摘要幾乎是同一張卡

- 位置：`position/[symbol]/DecisionCard.tsx:229,237-249`、`position/[symbol]/OperationSummaryPanel.tsx:101-117,203,280-289`
- 現行字面（兩處都出現）：動作大字（如「續抱參考」／候選為「進場評估」）＋「依規則」chip＋「未經歷史驗證」（可展開）＋「資料截至 MM-DD」徽章＋狀態 chip。操作摘要再多一行「依據：{規則名}」。
- 問題：CEO 往下捲，第一張卡和第二張卡的標題列長得一樣。`OperationSummaryPanel.tsx:35-68` 的註解承認這是 CEO 要求「股數與警示只留一處」後的殘留，主視圖只剩重複的動作字與一行依據。
- 建議方向：把兩張卡的主視圖合為一張（動作字、依規則、依據一行、未經歷史驗證各出現一次），操作摘要保留的只有「詳細」摺疊內容（反面論點、失效條件、資料來源）。【涉及風控核可句，需風控判定】：未經歷史驗證 chip、資料截至徽章都是核可句，只合併位置，不刪字。
- 動到 backend `app/`：否。【前端獨立】

### P1-2　個股頁：一張決策卡裡有四到五句講「同一件事」或「同一種免責」

- 位置：`DecisionCard.tsx:229/249`（未經歷史驗證 chip）、`:525`（3-S 免責）、`:261-293`（限制區塊）、`lib/quantityAbsenceWording.ts:64`、`backend/app/advice/engine.py:386,397`
- 現行字面（持有、加碼被上限擋下時，同一張卡）
  1. 股數格：「加碼參考被風險上限擋下」
  2. 後端 blocked_notices：「加碼建議被第 1 條上限（單一標的佔比上限）擋下。」
  3. 2-V：「已違反第 1 條上限：單一標的佔比 {x}（上限 {y}）」
  4. 2-R：「「續抱參考」不代表你的部位在上限內；目前超過上限只會把加碼參考改為續抱參考，不會改成減碼參考。」
  5. 3-S 免責：「依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。」（約 62 字）
  6. 另有 chip「未經歷史驗證」，與 3-S 內的「未經歷史驗證」重複；全站頁尾 `riskRemediationWording.ts:104-107`（約 130 字）又講一次「還沒用歷史資料驗證過」「日線收盤資料、非即時」
- 問題：1、2、3 是同一事實（加碼被擋）三種寫法；5 和 6 的 chip 重疊；5 和全站頁尾重疊。3-S 約 62 字，已超過一屏好讀的長度。
- 建議方向：不刪任何一句，只提「同一事實只在最上層講一次，其餘改成指向」的結構：把 1、2、3 合成一個區塊；chip 與 3-S 擇一常駐、另一個併入。【涉及風控核可句，需風控判定】全部 6 句都是風控逐字審過的句子。
- 動到 backend `app/`：否（`engine.py` 的 blocked_notices 句式保留，前端只做整併呈現）。【前端獨立】

### P1-3　回測頁：圖之前堆了 7 到 9 塊聲明，圖本身被壓到最後

- 位置：`BacktestReportView.tsx:593-680`（順序：示範資料警告 → 5-BT 假設框〔2 點〕→ 歷史統計免責框 → 費率未查證警示 → notes 清單〔B&H、費率、五項、已還原、還原方法、同步時間〕→ 圖）
- 現行字面（節錄）
  - `:610-616`「先看以下假設：前兩項可能讓結果偏樂觀」＋兩點
  - `:633-635`「本回測報告呈現的所有數字皆屬歷史統計描述，不代表未來會重演。」
  - `:642-643`「費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證（verified_on 為 null），報告數字應視為待查證狀態。」
  - 後端 `api/backtest.py:88-92`：「費率（手續費、證交稅、規費）尚未經主要來源查證（verified_on 為 null），本報告的成本相關數字應視為待查證狀態。」
  - `lib/backtestCurveWording.ts:60-61`（圖說）：「本圖同上方提醒：僅為歷史統計描述，不代表未來會重演；成交與滑價假設見上方。」
- 問題
  - 費率未查證同時出現兩次：前端警示框（`:642`）＋後端 notes（`api/backtest.py:473`，費率未查證時一定附加）。兩句幾乎同字，連「verified_on 為 null」都一起重複。
  - 歷史統計免責在圖上方講一次，圖說又講一次；Buy & Hold「未計成本」在 notes（`api/backtest.py:88`）、每張表底下（`BacktestReportView.tsx:338-340`，兩段各一次）、欄位標題共三到四次。
  - 5-BT 標題寫「前兩項可能讓結果偏樂觀」，下一個框又說「報告數字應視為待查證狀態」，CEO 要判斷哪個影響大，沒有排序。
- 建議方向：同一個聲明只在圖上方講一次，其餘改為指向；聲明按「影響結論的程度」排序，次要的（同步時間、費率明細）移進詳細。【涉及風控核可句，需風控判定】風控 2026-10-26 明定 5-BT 位置在圖之前（`BacktestReportView.tsx:602-608`），所以這項只能是合併，不能把 5-BT 移到圖之後。
- 動到 backend `app/`：部分。重複的費率句要動後端 notes 才能去掉；前端的整併與排序不用。

### P1-4　回測頁：每個樣本段重複整組長句，且全部預設展開

- 位置：後端 `api/backtest_wording.py`（由 `BacktestReportView.tsx:279-285,316-318,507-523,708` 渲染，樣本內與樣本外各一份）
- 現行字面（兩段完全相同的）：
  - `SAMPLE_COUNT_REMINDER`（`:131-136`，約 105 字）
  - `COST_AND_SETTINGS_NOTE`（`:153-158`，約 105 字）
  - `DETAIL_OPENING`（`:159-162`，約 70 字）
  - `EXCLUDED_ROUND_TRIPS_NOTE`（`:144-150`，約 170 字）
  - 表內定義列：獲利因子（約 100 字）、盈虧比（約 80 字）、最長連續虧損（約 170 字）、在場時間比例（約 240 字）
  - `UNATTRIBUTED_TAIL_PRESENT`（`:177-182`，約 110 字）
- 問題：一次回測，上述長句在畫面上至少出現兩輪，每句 70 到 240 字。其中「獲利因子」與「盈虧比」兩列的定義互相說「不可互換」，CEO 要先讀懂這兩個詞的差別才讀得懂表。
- 建議方向：同一句相同的聲明在頁面上只渲染一次（放在兩段表格之前，說明「兩段皆適用」）；定義列預設收合。【涉及風控核可句，需風控判定】`SAMPLE_COUNT_REMINDER`（L-10）風控明訂「每一段都要常駐」（`BacktestReportView.tsx:284`，F11-R-10），F11-W-34 也要求三處來源行逐字一致。所以這項需要風控先同意「頁面層級一次」是否滿足原條件，我不能自行決定。
- 動到 backend `app/`：否（前端渲染層級）；若風控要求改句式才動後端。

### P1-5　畫面直接露出工程詞與開發路徑

| 位置 | 現行字面 | 備註 |
|---|---|---|
| `BacktestReportView.tsx:339` | 「Buy & Hold 為同期間、未計交易成本的被動持有基準（見後端 `app/backtest/report.py` 文件說明）。」 | 檔案路徑露在畫面，CEO 無法使用。【前端獨立】；刪括號屬減字，仍請風控過目 |
| `BacktestReportView.tsx:642-643` 與 `api/backtest.py:89-92` | 「…（verified_on 為 null）…」 | 兩處重複、都是欄位名。前端【前端獨立】、後端【後端】 |
| `api/backtest.py:138-142`（`DIVIDEND_NOT_SYNCED_NOTE`，RC-556 範圍） | 「（未執行 uv run python -m app.dividends.sync）」 | 指令列字串露在畫面。只列出處，歸 RC-556 |
| `api/backtest.py:161-164`（`DIVIDEND_DISABLED_NOTE`） | 「本次依請求關閉除權息還原（adjust_dividends=false）…」 | API 參數名；歸 RC-556 範圍 |
| `backend/app/backtest/event_study.py:442` | 「含成本的版本請看 walk-forward 回測報告（POST /api/backtest, strategy=five_conditions）。」 | API 路由露在畫面。【後端】 |
| `event_study.py:429`、`lib/sectorMomentumWording.ts:127` | 「…離線示範資料（demo_synthetic）…」 | 內部代碼。【後端】／【前端獨立】 |
| `settings/SettingsForm.tsx:463` | 「每一項數字都是分數（例如 0.15 = 15%），與後端 `app/advice/limits.py` 的 RiskBudget 欄位一一對應。」；標題 `:460`「風險預算（RiskBudget）」、`:491`「費率（回測 CostModel）」 | 路徑與型別名。【前端獨立】 |
| `advice/limits.py:367,412,453`、`advice/book.py:134,153`、`api/settings.py:150` | 「…回報 not_evaluable，無法判定是否違反。」「…該上限會回報 not_evaluable…」「…維持 not_evaluable（無法評估）。」 | 狀態代碼被當成句子的一部分。這些句出現在風險儀表詳細、建議卡、設定頁說明。【後端】，並且全是風控核可句，需風控判定 |
| `settings/KellyInputsSection.tsx:71` 與 `lib/cap1SunsetWording.ts:31` | 「Kelly 輸入」「win_rate／payoff_ratio 輸入」 | 英文欄位名當說明（`KellyInputsSection.tsx:63-70` 註解說明是為了避開某個禁用詞，才用英文欄位名）。這是風控約束造成的結果，不是疏忽，要改需風控同意 |
| `api/kelly_wording.py:116-120,133,161,276` | 「K_observed」「K_distinct_specs」「（422）」 | 見 P1-8 |
| `components/PendingAlertsPanel.tsx:11-13` | 警示事件下方印 `close: 123　rsi14.last: 71.2` 的原始鍵名 | 前端已有 `signalFieldLabel`（`lib/format.ts:493`）可以把鍵名轉成「最新收盤價」等現成標籤，不需新字面。【前端獨立】 |
| `settings/DataSourcesSection.tsx:65,70` | 「…以測試替身通過自動化測試；尚未以真實 API key 對外部服務實際發送過請求。需設定環境變數…」 | 工程師的語言。【前端獨立】需風控過目（原註解標「字面待風控覆核」） |

- 動到 backend `app/`：見表中各列標記。其中純前端、不需新字面、可先做的是：`PendingAlertsPanel.tsx` 鍵名轉標籤、`SettingsForm.tsx:463` 去路徑、`BacktestReportView.tsx:339` 去路徑。

### P1-6　同一概念的不同說法（item 4 對照表）

CEO 要的是「算不出來」「資料有問題」「沒有這筆」三種狀態有一致的詞。現況：

| 概念 | 目前說法（出處） |
|---|---|
| 某條上限算不出來 | 「無法評估」（`lib/format.ts:334` 狀態 chip；`riskRemediationWording.ts:86`）；後端詳細句同時用「不計算」（`limits.py:411,442`）、「暫不評估」（`kelly_wording.py:333-335,379-381`）、「不提供」、「維持 not_evaluable」 |
| 六項條件某條算不出來 | 「無法判定」（`entryObservationWording.ts:26`），底下 qualifier 又寫「資料不足」（`:123,128`）、「無法取得」（`:118`） |
| 某部位算不出市值 | 「無法估值」（`oneLinerWording.ts:130,140`）；原因行另有「查無價格資料」「本次未查價格」「幣別與市場不符」「代號或價格單位不採用」（`valuationWording.ts:22-33`）；後端句用「無法估值」（`book.py:191`）與「不採用」（`gate_wording.py`） |
| 資料來源取不到／日線不足 | 「資料不足」（`DataMetaStatusBadge.tsx:128,163`、`InsufficientPanel.tsx:9`、`adviceWording.ts:53` 動作字、`format.ts:344,353` 狀態字） |
| 某格算不出 | 「無法計算」（`decisionCardWording.ts:76`、`KeyLevelsPanel.tsx:110,229,299`）、「未提供股數」（`adviceWording.ts:221`）、「不附交易股數」（`quantityAbsenceWording.ts:61`） |
| 「—」的意思 | 六項條件：「代表無法判定」（`entryObservationWording.ts:65`）；關鍵價位：「沒有可顯示的數字」（`KeyLevelsPanel.tsx:68-69`）；決策卡：沒有定義（S-1） |
| 「不估值」 | 前後端字面中沒有找到「不估值」這個詞（相近的是「不計算」「不採用」「暫不評估」） |

- 問題：「無法評估」「無法判定」「無法估值」「資料不足」「無法計算」五個詞各管一塊，彼此意思重疊，沒有一張對照告訴 CEO 差別在哪。最容易誤會的是「資料不足」：既指「來源取不到」，也指「日線根數不夠」，也用在動作字（`HELD_ACTION_LABELS.insufficient_data` = 「資料不足」）。
- 建議方向：先由 PM 與 creative-lead 定一張「狀態詞表」（哪幾個狀態、各用哪個詞），再由風控審這張表而不是逐句審；之後各處依詞表替換。這是跨前後端、跨風控核可句的大整併，建議單獨立案，不要夾在 P0 修正裡。【涉及風控核可句，需風控判定】
- 動到 backend `app/`：**是**（`limits.py`、`book.py`、`kelly_wording.py` 等後端字面）。前端部分【前端獨立】可先對齊 `format.ts:334`、`entryObservationWording.ts:26` 與徽章。

### P1-7　首頁警示狀態列：同類的歸因問題（RC-650／RC-654 已知；以下為同類補充）

已知例（只列出處）：`lib/oneLinerWording.ts:75`「{n} 條規則已設定，目前沒有待處理警示」＋ `:83-85`「查詢時間：{t}」（`AlertStatusStrip.tsx:105-106`）。

同類
- 同一句的「N 條規則已設定」把停用的規則一起算（`oneLinerWording.ts:68-73` 的註解說這是刻意的）。全部規則都停用時，仍讀到「5 條規則已設定，目前沒有待處理警示」，CEO 會以為 5 條規則都在跑。
- `components/RiskGauge.tsx:239`「判定產生時間：…」（詳細內）是伺服器回應時間，不是行情時間。字面寫「判定產生」，容易讀成「這個判定是那個時間算出來的」。（程式註解 `RiskGauge.tsx:272-275` 自己也承認這是風控退修的附帶。）
- `lib/adviceWording.ts:354-357`（`NON_REALTIME_NOTICE`）寫死「資料約每 24 小時更新一次、警示評估約每 60 分鐘評估一次」，但設定頁的警示排程間隔是可由使用者改的（`settings/SettingsForm.tsx:193` `evaluation_interval_minutes`）。使用者改成 15 分鐘後，這句就錯了。這句放在個股頁頁尾的資料來源組。
- 建議方向：以上三項都是「句子宣稱的事」和「畫面上實際的來源」對不上，處理方式與 RC-650/654 一致，可併單。字面交 creative-lead。第三項若要依設定值代入，要動後端或把值傳到前端。
- 動到 backend `app/`：第一、二項【前端獨立】；第三項若改成代入設定值，需要確認是否要動後端字面（`NON_REALTIME_NOTICE` 在前端，值從 settings 取，前端可做）。【涉及風控核可句，需風控判定】

### P1-8　設定頁 Kelly 區：預設展開的句子又長又帶演算法符號

- 位置：`settings/KellyInputsSection.tsx:75`（lead）；`settings/KellyDisclosuresPanel.tsx:191-244`（8 段並列）；後端 `api/kelly_wording.py`
- 現行字面（節錄）
  - lead（`lib/cap1SunsetWording.ts:31`，約 190 字）：「第 5 條「分數 Kelly 部位上限」使用的 win_rate／payoff_ratio 輸入。新增與修改已暫停（手填與從回測帶入皆同）；刪除仍可使用。已存在的輸入仍照原方式參與第 5 條，直到各自滿 30 天過期為止。第 5 條的計算方式有誤，算出的數字不可靠；它只會讓該標的的上限比沒有第 5 條時更嚴或相同，不會更寬。刪除某筆輸入後，該標的不再受第 5 條限制，只受其他上限限制，上限可能因此比刪除前寬。」
  - `kelly_wording.py:86-91`：「此次估計的 f*（Kelly 公式算出的比例，尚未套用上限）的 95% 區間為…」
  - `kelly_wording.py:115-120`：「…已記錄 {k_observed} 次回測帶入嘗試（K_observed）——這個數字含被系統拒絕（422）的嘗試…」
  - `kelly_wording.py:176-181`：「本系統的 walk-forward 是把資料依時間先後分段…」
- 問題
  - lead 一句約 190 字，包含五個不同的資訊（暫停、既有輸入照用、過期天數、計算有誤、刪除的後果），CEO 讀完仍不知道「我現在該不該動這一區」。
  - 第 5 條在三個地方用三個名字：風險儀表「分數 Kelly 部位上限」（`format.ts:438`）、設定欄位「分數 Kelly 上限」「Kelly 部位硬上限」（`SettingsForm.tsx:140,146`）、lead「分數 Kelly 部位上限」。設定頁有兩個很像的 Kelly 欄位，CEO 不知道哪個才是第 5 條。
  - 單一標的查詢後，預設就展開 6 到 8 段 100 到 200 字的揭露，符號有 f*、p、K_observed、K_distinct_specs、422、OOS。
- 建議方向：整區預設只留「現況一句＋我該做什麼」，其餘揭露整組收進詳細。三個名字併成一個。這一區正在落日（`cap1SunsetWording.ts:13-14` 註解：5-K 批會撤掉 lead），若短期內要撤，優先把「不要重新設計」記進登記單，只修最不合理的重複。【涉及風控核可句，需風控判定】
- 動到 backend `app/`：否（先做前端收合與名稱一致）；若要改句式則動 `api/kelly_wording.py`。

### P1-9　首頁「總資產（市值）」其實不含現金

- 位置：`components/SummaryCards.tsx:96`「總資產（市值）」；後端 `advice/book.py:127-130`、前端 `settings/SettingsForm.tsx:98,107,129,147`
- 現行字面：首頁大字標籤「總資產（市值）」；設定頁與建議卡一再補上限定語「總資產(已估值部位市值,不含現金)」；另有「帳戶總淨值」（使用者自填，`NetWorthSection.tsx:131`）
- 問題：首頁最大的一個數字叫「總資產」，但它是持倉市值，不含現金；設定頁又有一個要使用者自填的「帳戶總淨值」。一般人讀「總資產」會當成含現金，三個分母並存，CEO 沒有任何一處明白告知首頁這個數不含現金（括號裡只有「市值」兩字）。
- 建議方向：首頁標籤與其他處用同一個名稱與同一個限定語；這是命名問題，交 creative-lead 與風控。
- 動到 backend `app/`：否（首頁標籤在前端）。【前端獨立】【涉及風控核可句，需風控判定】

### P1-10　個股頁主視圖的指標 chip 直接露出行話

- 位置：`position/[symbol]/TechnicalIndicatorsPanel.tsx:58-80`（`IndicatorOverviewChipsRow`，技術分析主視圖，不在詳細內）
- 現行字面：「RSI 低區帶（≤30）」「K 值中區帶（20–80）」「%B 高於上軌（>1）」「成交量接近近期平均（|z|<2）」
- 問題：主視圖直接看到 RSI、K 值、%B、|z|，沒有解釋；圖例句（`INDICATOR_OVERVIEW_LEGEND`）已被收進頁尾。成交量一條同時用了白話（「接近近期平均」）與符號（|z|<2），六項條件裡同一個指標卻叫「成交量 z」（`entryObservationWording.ts:34`），兩處說法不同。「區帶」也是只在這裡用的詞（其他處用「區間」「位階」）。
- 建議方向：主視圖 chip 只留白話，符號與門檻移進詳細或 tooltip；同一個指標在 chip 與六項條件裡用同一個名稱。字面交 creative-lead，【涉及風控核可句，需風控判定】（`componentWordingScan.test.ts` 逐字釘住）。
- 動到 backend `app/`：否。【前端獨立】

---

## P2（影響較小，可併入下一次修字）

### P2-1　停損停利兩套描述同一算法，用詞不同

- `KeyLevelsPanel.tsx:146-147`「大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。」 vs `riskRemediationWording.ts:122`「取「收盤減 2 倍 ATR（近 14 個交易日的平均波動幅度）」與「收盤的 92%」兩者中較高的一個。」
- 同一個算式，一處說「較緊」，一處說「較高」；一處寫「−8%」，一處寫「92%」；ATR 一處寫「2×ATR(14)」一處寫「2 倍 ATR（…平均波動幅度）」。兩句在同一個面板的不同層出現。
- 【前端獨立】【涉及風控核可句，需風控判定】

### P2-2　同一頁出現多個「近 N 根」，N 各不相同

- `page.tsx:398-404`「近 {全部根數} 根日線」（約 370 到 540）、`KeyLevelsPanel.tsx:85-101`「近 252 根日線位階」「近 252 根區間」、`entryObservationWording.ts:39`「近 {n} 根位階」、`KeyLevelsPanel.tsx:127`「近 60 日低點」、`TechnicalIndicatorsPanel.tsx` 內「近 N 日」。
- 另外 `page.tsx:456-461`「共 N 根日線（…）」與一句結論的「近 N 根日線」重複同一個數字。
- 【前端獨立】

### P2-3　位階 70% 同時是「區間上緣」也是「條件成立」

- `KeyLevelsPanel.tsx:213`「≥70%→標示「區間上緣」」，`entryObservationWording.ts:44`「≤ 70%」（成立）。位階正好 70% 時，同一頁一個說「上緣」、一個說「成立」。邊界案例，影響小，但 CEO 看到時會困惑。
- 【前端獨立】

### P2-4　兩個都叫「ATR(14)」的數字可能不同

- `KeyLevelsPanel.tsx:228`（簡單平均）與 `TechnicalIndicatorsPanel.tsx:437`（Wilder）。quant L7 已記錄；從 CEO 角度，同一頁兩個同名數字不同，需要標籤區分。
- 【前端獨立】標籤；【後端】若要統一算法。

### P2-5　關鍵價位頁尾仍留一組「已經不會發生」的算式

- `KeyLevelsPanel.tsx:259-271`（`KEY_LEVELS_BASIS_CLOSE_DISTANCE`）仍寫「最新收盤高於停利參考、或低於停損參考時，該項距離改為：…」。`lib/decisionCardWording.ts:44-51` 的註解已說明 R-6 之後「越過」情形不可能發生，相關句與揭露行已移除，這一組算式是遺漏。
- 位置在頁尾詳細內，CEO 很少看到，但是這句說明的是一個不存在的情況。
- 【前端獨立】【涉及風控核可句，需風控判定】

### P2-6　每個摺疊區各放一句「頁尾某某涵蓋…」的指引句

- `lib/footerDisclosureWording.ts:19-21,27-29`；使用處：`page.tsx:462`（技術分析）、`KeyLevelsPanel.tsx:610`、`EntryObservationPanel.tsx:205`、`OperationSummaryPanel.tsx:257-260,345-348`（操作摘要兩句）、`TechnicalIndicatorsPanel.tsx:144`。
- 每個詳細展開後最底下都有一句「頁尾「X」涵蓋本區資料來源、揭露事項與計算方式說明。」，個股頁展開一次看到三到五句同樣句式的指引。
- 【前端獨立】【涉及風控核可句，需風控判定】（風控 L5 要求每個有下沉句子的區塊要有）。

### P2-7　族群動能卡

- `lib/sectorMomentumWording.ts:528-529`（通過態主句，約 85 字）：「歷史：第 1 名族群其後 5 個交易日報酬高於等權全市場，{N} 次中 {k} 次（{p}%）；同期全部族群平均為 {q}%（兩者皆已扣來回成本）」
- `:455`「歷史統計尚待風控複審，本排行僅描述近 5 日的相對強弱。」把內部流程狀態當成給 CEO 的說明。
- 詳細中的「Wilson 法區間」「Bootstrap」（`SectorMomentumCard.tsx:438-449`）屬行話。
- 【前端獨立】／【後端】（`api/sectors_wording.py`，未讀）

### P2-8　設定頁的長欄位說明

- `settings/SettingsForm.tsx:115`（單一產業佔比上限的欄位說明，約 190 字，含五個條件）。欄位說明預設展開。
- 【前端獨立】【涉及風控核可句，需風控判定】（註解標「風控核可文案 2026-08-09」）

---

## 對 quant 盤點 H2／H3／M3 的 CEO 讀者評估（item 5）

| 項 | CEO 讀起來會不會誤會 | 理由 | 處理 |
|---|---|---|---|
| H2「已還原除權息」 | **會，高度** | 句子用肯定語氣、涵蓋「現金股利與配股」兩項，沒有任何「僅涵蓋同步後」的限定；唯一的線索是下方一行小字的同步時間，CEO 不會自行推出「同步前沒算」。同時事件研究共用同一判斷。 | P0-1。要後端先決定「已還原」的成立條件，再由 creative-lead 擬覆蓋範圍句。 |
| H3 回測錨定進場價 vs 個股頁錨定最新收盤 | **會，高度** | 兩邊都叫「基準價」，句子只說明自己的算式，沒有說「與個股頁不同」。CEO 最自然的讀法是「回測驗證了個股頁看到的停損停利」。實際上個股頁的停利永遠碰不到，回測的停利可以觸發。 | P0-2。至少字面上區分兩種基準，必要時由 quant 決定要不要把兩邊對齊（那是算法面，不是字面）。 |
| M3 樣本內／外 | **會，中到高** | 輸入欄、段落標題、圖例、頁首介紹、事件研究五處同時使用「樣本內／外」，且報告寫「未參與任何參數選擇」；事件研究卻明說「不是樣本外」。CEO 看到兩個互相衝突的說法，很可能選擇相信看起來更嚴謹的那個。另外「可以反覆換期間挑出好看的樣本外」這件事畫面上完全沒有提示。 | P0-3。同頁五處同批改；是否需要在畫面上加上「同標的已執行 K 次」的揭露，屬 quant M3 的算法面建議，不在本檔評估。 |

---

## 可在正式登記前先處理的【前端獨立】項（彙整）

只動 `frontend/app/`，不動 backend `app/`，也不需要新字面（或只是「減字」）。是否仍需風控過目，欄位內標明。

| 項 | 位置 | 做什麼（不擬字） | 風控 |
|---|---|---|---|
| P0-4 a | `KeyLevelsPanel.tsx:298-299` | 壞值與無資料分兩種情形顯示，不再說「沒有可用日線」；新字面另案 | 新字面需審 |
| P0-4 b | `DecisionCard.tsx:349-351` | 補原因句；新字面另案 | 單項確認 |
| P0-4 技術分析一句結論 | `page.tsx:398-404` | 改用與 `computeKeyLevels` 同一判斷（RC-695 本體，已在追蹤） | 無新字 |
| P0-5 | `RiskGauge.tsx:102-104,167-172`、`limitNotices.ts:81` | 把既有那句「算出的數字不可靠」移到第 5 條狀態 chip 同層、決策卡違反列同理 | 需風控判定（只動位置） |
| P1-1 | `DecisionCard.tsx`、`OperationSummaryPanel.tsx` | 主視圖合併，動作字與 chip 各出現一次 | 需風控判定（核可句移位） |
| P1-2 | `DecisionCard.tsx:229,249,261-293,525` | 加碼被擋的 3 句整併；chip 與 3-S 整併 | 需風控判定 |
| P1-5 | `PendingAlertsPanel.tsx:11-13` | 原始鍵名改用 `signalFieldLabel`（現有標籤，不新擬） | 免 |
| P1-5 | `SettingsForm.tsx:463` | 去掉後端路徑 | 免（減字） |
| P1-5 | `BacktestReportView.tsx:339` | 去掉括號內檔案路徑 | 請風控過目（減字） |
| P1-5 | `BacktestReportView.tsx:642-643` | 去掉「verified_on 為 null」（但後端 notes 同句還在，要同批處理才有感） | 新字面需審 |
| P1-6 | `format.ts:334`、`entryObservationWording.ts:26`、`DataMetaStatusBadge.tsx:128` | 等「狀態詞表」定案後對齊 | 需審 |
| P1-9 | `SummaryCards.tsx:96` | 首頁「總資產」標籤對齊 | 需審 |
| P2-1 / 2 / 3 / 5 / 6 | 見 P2 各項 | 小幅對齊或移位 | 多數需風控判定 |

動到 backend `app/` 的項目（不要在登記前處理）：P0-1、P0-2、P0-3 的事件研究段名、P1-3 的重複費率句、P1-5 的 `not_evaluable`／API 路由／`demo_synthetic`、P1-6 後端詞表、P1-8（若改句式）。

## 登記建議（給 PM 自己，之後再做）

1. P0-1、P0-2、P0-3 與 quant 的 H2、H3、M3 併成同一組工單，因為字面與算法要同批改；交 tech-architect 評估後端改動，creative-lead 起草，風控逐字審。
2. P0-4、P0-5 各自獨立立案。P0-5 與 RC-596 殘留 (iii) 先對照再決定是否併單。
3. P1-6「狀態詞表」建議單獨立案，先定詞表再全站替換，不要散在各單裡。
4. P1-1、P1-2、P1-3、P1-4 是「重複整併」類，一起交風控一次判定「合併是否滿足原核可條件」，比逐項送審有效率。

## 驗證

- 本檔所引行號均來自本次 Read／Grep 的輸出，抽查 `entryObservationWording.ts:92,107`、`oneLinerWording.ts:75,83`、`page.tsx:398-404`、`BacktestReportView.tsx:339,642,704,725`、`riskRemediationWording.ts:97,112,122`、`limits.py:367,412,453` 皆與現行字面相符。
- 「約 N 字」為目測。
- 未執行任何程式或測試；沒有改動任何程式碼或既有文件。
