# Stock Desk — C5「Kelly 準則輸入計算」PRD

**撰寫者**：product-manager
**撰寫日期**：2026-08-19
**狀態**：draft（待 tech-architect 技術評估、risk-compliance-officer 文案審查、CEO 優先序裁決）
**對應機會清單條目**：C5「Kelly 準則輸入計算」

## 變更紀錄

- 2026-08-19：依 ADR-0006 修正 profit_factor≠b 與 FR-3 時效錨點（product-manager 執行，來源為 tech-architect 升級事項，見 `work/stock-desk-C5-Kelly-架構評估.md`「升級 CEO/PM 事項」與 `docs/adr/0006-stock-desk-kelly-輸入來源與模組邊界.md` D-4／D-5）。
- 2026-08-19：依風控批審＋D9 §3.3 補齊 FR-5 欄位（product-manager 執行，來源為 `work/reviews/2026-08-19-C5-Kelly-文案批審.md`「三、整批缺漏」第 2 點與 `work/stock-desk-C5-Kelly-D9-量化意見.md` §3.3 第 3、4、7 點；欄位真相來源見 `docs/adr/0006-stock-desk-kelly-輸入來源與模組邊界.md` D-2／D-6）。FR-5 顯示欄位列舉由「策略名／OOS 起訖／完整回合數／費率未查證／除權息狀態」擴充補入：獲利回合數 `n_win`、虧損回合數 `n_loss`、跨界排除回合數 `oos_excluded_boundary_trips`、期末未平倉回合數 `oos_open_trip_at_end`、樣本觀測數 `oos_observations`、p 的 Wilson 95% 區間；相應驗收條件同步補一組。顯示措辭仍待 risk-compliance-officer 定稿，本次僅補欄位與 AC，不涉及文案。

> **輸入契約缺口聲明**：本 PRD 依指示應以 `work/機會清單.md` C5 條目為第一手來源，但該檔案於目前分支（HEAD 710e500）與 `work/` 目錄下皆不存在（僅找到 `work/stock-desk-已知限制與後續.md`）。本 PRD 改以下列已驗證來源重建需求：
> - `work/stock-desk-已知限制與後續.md` 第 5 項（Kelly 準則輸入無來源）與其優先序建議（P1 第 5 順位）。
> - 程式碼實地確認：`apps/stock-desk/backend/app/advice/limits.py`（第 5 條上限邏輯、`kelly_fraction_cap`/`kelly_position_cap` 現況）、`apps/stock-desk/backend/app/backtest/`（回測指標、走前測試分段）、`apps/stock-desk/backend/app/settings/net_worth.py` 與 `apps/stock-desk/frontend/app/settings/NetWorthSection.tsx`（帳戶淨值的時效性先例，FR-9）。
> 若機會清單原文與本 PRD 有出入，請以機會清單為準並回頭更新本文件（見開放問題 Q1）。

---

## 背景與目標

### 現況（程式碼實地確認）

- `app/advice/limits.py` 定義第 5 條上限「分數 Kelly 部位上限」（`kelly_fraction`），需要 `PortfolioContext.win_rate`（勝率 p）與 `PortfolioContext.payoff_ratio`（盈虧比 b）兩個輸入。兩欄位型別已存在（第 235-236 行），但**全系統沒有任何路徑會賦值**：`app/advice/book.py` 建構 `PortfolioContext` 時從未設定這兩欄，因此 `_check_kelly_fraction` 恆回 `not_evaluable`，訊息固定為「缺少勝率或盈虧比，無法計算 Kelly 部位上限（目前沒有資料來源提供這兩項輸入）」（limits.py:453）。
- `kelly_fraction_cap`（預設 0.25，上界 0.25）與 `kelly_position_cap`（預設 0.10，上界 0.10）兩個政策參數已存在且已由風控與 CEO 於 2026-07-26 書面核准為硬上限（limits.py:70-85 註解），**本次不涉及調整這兩個上界**，只涉及「有沒有 p、b 可以套用它們」。
- 回測模組（`app/backtest/report.py`）已產出 `win_rate`、`profit_factor`（總獲利／總虧損）等標準指標，且**強制樣本內／樣本外分列**（`WalkForwardReport.in_sample` / `out_of_sample`），`out_of_sample` 明確標註為「the honest performance measure」。**注意：`profit_factor` 不是 Kelly 的 b（盈虧比／payoff ratio）**——`b = payoff_ratio = mean(獲利) / mean(|虧損|)`，而 `profit_factor = (p/(1-p))×b`，兩者僅在勝率 p=0.5 時相等；當 p>0.5 時 PF>b，若誤用 PF 當 b 會高估 f\*、放寬第 5 條上限，與風控保守原則相反（見 ADR-0006 D-5）。依 ADR-0006，`report.py` 將新增 `payoff_ratio` 欄位（由開發實作），本 PRD 以下所有指涉 Kelly 的 b 之處一律引用 `payoff_ratio`，不得使用 `profit_factor`。
- **與背景資料不符之處須先澄清**：任務背景提及回測「三策略」，但 `app/backtest/strategies.py` 目前僅實作 `ma_cross` 一種策略（`STRATEGY_IDS = ("ma_cross",)`），該檔案 docstring 明寫「it is a textbook example, not a recommendation」。這與已知限制文件第 8 項（回測策略僅 ma_cross，列為 P2 待辦）一致。本 PRD 以**現況（僅 1 策略）**為準撰寫，若機會清單設想的是策略擴充後的狀態，請 CEO 於開放問題 Q6 裁決排期關係。
- 帳戶淨值（FR-9，`app/settings/net_worth.py` + `NetWorthSection.tsx`）已建立「使用者自報數字＋時效性狀態」的先例可供比照：三段式新鮮度 `fresh` / `ageing`（7 天）/ `expired`（30 天），以及「系統絕不靜默修正使用者輸入，只回拒絕或警示」的立場。
- 風控列管（已知限制第 10 項）：「勝率」二字在 `limits.py:453, 461` 目前只出現在 `not_evaluable` 的固定文案與尚未被任何真實數字觸發的 f-string 模板中。一旦 `win_rate` 從恆 `None` 變成有真實數值，這兩處文案會第一次真正對使用者顯示具體百分比，**列管條件即被觸發**，需 risk-compliance-officer 在功能上線前重新審查。

### 目標

讓第 5 條「分數 Kelly 部位上限」從恆 `not_evaluable` 的裝飾性上限，轉為在使用者提供（或授權使用回測所得）勝率與盈虧比後可真正評估、可攔下交易的有效風控上限——同時不越界變成一句「建議倉位」的投資建議。

---

## 使用者與情境

- **持有/追蹤特定標的的使用者**，希望第 5 條上限不再永遠顯示「無法評估」，想知道系統是否認可他目前（或想加碼）的部位大小落在 Kelly 的保守額度內。
- **曾對某標的執行過回測的使用者**，回測報告已經算出樣本外的 `win_rate`／`payoff_ratio`，不想再手算一次盈虧比、手動換算成 Kelly 分數。
- **從未回測、憑自己交易經驗估計勝率的使用者**，想直接填入自己估計的 p、b。
- **風控／稽核視角**：需要確認任何顯示出來的「勝率」數字，其來源、樣本區間、時效性都清楚可追溯，不會被誤讀成系統對未來的預測或背書。

---

## 範圍內 / 範圍外

### 範圍內

1. 定義 Kelly 輸入（p、b）的資料模型與來源類型（回測帶入 / 手動輸入 / 手動調整過的回測帶入）。
2. 設定頁新增 Kelly 輸入管理區塊；個股頁第 5 條上限旁揭露來源與時效狀態、提供前往設定頁的捷徑。
3. 時效性規則（比照淨值先例：7 天提醒、30 天失效）。
4. `app/advice/book.py` 接線，讓 `PortfolioContext.win_rate` / `payoff_ratio` 能在輸入存在且未過期時被賦值，使第 5 條上限真正可評估。
5. 新增揭露文案（回測來源的「歷史模擬非預測」揭露、手動輸入的「系統不查核真實性」揭露），並定義送審流程。
6. Kelly 數字「部位上限、非建議倉位」的定性邊界規範。

### 範圍外（非目標）

1. **不**新增交易日誌模組、**不**從實際成交歷史回溯計算勝率（已知限制文件提出的另一條路徑，需求更大，留待未來獨立評估）。
2. **不**調整 `kelly_fraction_cap` / `kelly_position_cap` 的預設值或硬上界（0.25 / 0.10 已由風控與 CEO 書面核准，非本次事項）。
3. **不**新增回測策略（RSI、突破等，屬已知限制第 8 項，獨立機會，非 C5 範圍）。
4. **不**對使用者手動輸入的 p、b 做自動合理性攔阻或警示（例如比照淨值「遠高於帳面 10 倍」的兩段式規則）——本期僅接受輸入並揭露「系統不查核」，是否需要合理性防呆留待開放問題 Q4 決議後另立需求。
5. **不**支援逐筆交易或逐次進出場的獨立 Kelly 計算，粒度僅到「標的（＋來源策略）」。
6. **不**讓 Kelly 相關文案出現任何「建議你買到／加碼到此數字」的語句——這是紅線而非未來可加的功能，見風險章節。
7. **不**支援使用者跨標的批次貼上勝率／盈虧比等試算表匯入功能（本期僅逐標的手動輸入或回測帶入）。

---

## 功能需求（逐條編號）

### FR-1　Kelly 輸入的資料模型與來源類型

系統須能為每一標的儲存一組 Kelly 輸入：`win_rate`（0~1）、`payoff_ratio`（>0），並標記來源類型：
- `backtest`：來自某次回測報告的樣本外（out-of-sample）段 `win_rate` / `payoff_ratio`（即 Kelly 的 b；`payoff_ratio ≠ profit_factor`，見背景說明，不得誤用），須保留可追溯的來源資訊（哪次回測、哪個策略、哪個時間區段、產出時間）。
- `manual`：使用者直接輸入的估計值。
- `backtest_overridden`：以 `backtest` 帶入後被使用者手動修改過的數值，須同時保留「原始回測值」與「使用者調整後值」以便追溯，且顯示上須清楚標示「回測預填，使用者已調整」而非單純標成 `backtest`。

若同一標的存在多次回測結果，資料模型須能明確表達「目前生效的是哪一筆」，避免多筆結果互相覆蓋卻無法追溯（同一標的、不同策略／不同回測執行時間的結果不得混淆張冠李戴）。具體資料表 schema（例如是否以 `(symbol, strategy_id)` 為鍵）留給 tech-architect 決定，本 PRD 只框定「必須可追溯、不可混淆」的行為要求。

### FR-2　輸入方式：混合模式（回測帶入＋可覆寫）

系統提供三種輸入路徑，且彼此不互斥：
1. **從回測帶入**：僅當使用者曾對該標的執行過回測，且該回測報告的樣本外段有效（`out_of_sample.strategy.win_rate` 與 `payoff_ratio` 皆非 `None`）、且該回測**尚未過期**（見 FR-3）時，設定頁提供「帶入此標的最近一次回測結果」的操作，帶入後數值可再編輯。
2. **手動輸入**：無回測或使用者選擇不使用回測時，直接於設定頁輸入 p、b。
3. **編輯已帶入的值**：帶入後的數值可被覆寫，覆寫後來源轉為 `backtest_overridden`（見 FR-1）。

### FR-3　時效性規則（比照淨值 7 天／30 天先例）

Kelly 輸入比照 `app/settings/net_worth.py` 已建立的先例分為三段新鮮度狀態，惟計齡起點依來源而異（依 ADR-0006 D-4，取代原「以輸入或最近一次帶入回測結果的時間為基準」的說法）：
- `manual`：以使用者填寫（儲存）當下的日期計齡，即 `updated_at`（server 戳記，等同使用者輸入當下的 as_of 日期）。
- `backtest` / `backtest_overridden`：以該筆回測樣本外（out-of-sample）區段的**結束日 `oos_end_date`** 計齡，**不**以回測執行（產出）時間或使用者點擊「帶入」的時間計齡——避免同一份舊樣本區間被反覆重跑或重複帶入時，誤判為「新鮮」。

三段狀態定義（天數門檻不變）：
- `fresh`：計齡起點至今 0～7 天內。
- `ageing`：7～30 天，顯示「建議更新」提示，但不影響第 5 條上限的評估（仍視為有效輸入）。
- `expired`：超過 30 天，**視同未輸入**——`_check_kelly_fraction` 須回退為 `not_evaluable`，且理由文案明確區分「從未輸入」與「輸入已過期」兩種情況（例如：manual 來源「Kelly 輸入已過期（上次更新於 35 天前），需重新確認後才能評估本條上限」；backtest 來源「Kelly 輸入已過期（樣本外區段結束於 35 天前），需重新確認後才能評估本條上限」），不得與「從未輸入」共用同一句話。

### FR-4　個股頁揭露

`position/[symbol]/LimitsCheckList.tsx` 第 5 條上限旁，當該標的存在（非過期的）Kelly 輸入時，須顯示：
- 來源徽章：回測帶入 / 手動輸入 / 回測帶入（已調整）。
- 時效狀態徽章：沿用淨值頁的三色分級視覺（`fresh` / `ageing` / `expired`）。
- 一個前往設定頁對應區塊的捷徑連結，供使用者查看／編輯。

### FR-5　回測來源的誠實揭露文案（風控前置審查項）

當 Kelly 輸入來源為 `backtest` 或 `backtest_overridden` 時，設定頁與個股頁皆須顯示等價於以下語意的句子（**確切措辭須經 risk-compliance-officer 審定，本 PRD 僅給定語意邊界**）：

> 此勝率／盈虧比來自 [某年某月某日] 執行的「[策略名稱]」樣本外（out-of-sample）回測結果，是歷史模擬表現，不代表未來勝率，也不是對本次交易結果的預測。

此揭露義務對應已知限制文件第 10 項 suggested 事項之一（「回測報告缺一行常駐警語」，原列為 suggested、非 required）。**本功能上線後，該揭露義務對 Kelly 輸入這條路徑必須從 suggested 升級為 required**，因為此時回測數字不再只是參考資訊，而是直接驅動一條會攔下交易的風控上限。

**FR-5 顯示欄位列舉（2026-08-19 依風控批審＋quant D-9 §3.3 第 3、4、7 點補齊）**

當 Kelly 輸入來源為 `backtest` 或 `backtest_overridden` 時，除上述揭露句外，設定頁與個股頁該筆輸入的明細區塊須同時顯示以下欄位（確切顯示措辭、單位與排版由 risk-compliance-officer 定稿，本 PRD 僅列欄位與其資料真相來源，真相來源依 ADR-0006 D-2／D-6）：

1. 策略名稱（`strategy_id`）。
2. OOS 起訖日期（`oos_start_date` / `oos_end_date`）。
3. 完整回合數（`oos_round_trips`，即 D-9 所稱 `n`）。
4. **獲利回合數（`n_win` / `oos_win_trips`）**。
5. **虧損回合數（`n_loss` / `oos_loss_trips`）**。
6. **跨界排除回合數（`oos_excluded_boundary_trips`）**，即進出場橫跨 IS/OOS 邊界而被排除於 p、b 計算之外的回合計數；顯示措辭不得暗示「排除是保守做法」（D-9 §2.4／§5.1：實測樣本量極低，證據不支持任何方向性結論，是否措辭符合此限制由風控審定）。
7. **期末未平倉回合數（`oos_open_trip_at_end`）**，即 OOS 區段結束時仍未平倉、未產生回合報酬率的回合計數。
8. **樣本觀測數（`oos_observations`）**。
9. **p 的 Wilson 95% 區間（`p_ci_low` ～ `p_ci_high`）**；當該區間所推導之 `ci_includes_no_edge` 為真（即對應的 f\* bootstrap 區間下界 ≤0）時，須連動顯示「此區間涵蓋『沒有優勢』的可能」語意的句子（確切措辭同樣待風控定稿）。
10. 費率未查證揭露（當 `rates_verified=false` 時顯示）。
11. 除權息還原狀態（`dividend_reason_code` / `adjust_dividends`）。

第 4～9 項（`n_win`、`n_loss`、跨界排除回合數、期末未平倉回合數、`oos_observations`、p 的 Wilson 95% 區間）為本次新補入，對應風控批審「三、整批缺漏」第 2 點所指「D9 §3.3 第 3/4/7 點顯示欄位未被 FR-5 列舉涵蓋」；第 1～3、10、11 項為原列舉範圍，本次未變動。上述欄位缺一即視為 FR-5 未完成，不得以「揭露句本身已含摘要語意」替代逐項顯示。

### FR-6　手動輸入來源的揭露文案（風控前置審查項）

當來源為 `manual` 時，須顯示等價於以下語意的句子（措辭同樣待風控審定）：

> 此勝率／盈虧比為你自行輸入的估計值，系統不會查核其真實性；若與實際狀況不符，本條上限的判定將隨之失真。

此立場比照 `net_worth.py` 對自報淨值「系統不會自行調整這個數字」的既有原則。

### FR-7　`app/advice/book.py` 接線：第 5 條上限轉為可評估

`PortfolioContext` 建構時，若該標的存在未過期的 Kelly 輸入（FR-1～FR-3），須將 `win_rate` / `payoff_ratio` 賦值；若不存在或已過期，維持 `None`（沿用現有「輸入缺失 → `not_evaluable`，絕不捏造」的慣例，`limits.py` 核心判斷邏輯 `_check_kelly_fraction` 不需改動判斷規則本身，只需要有真實輸入來源）。

### FR-8　定性邊界：Kelly 上限，非建議倉位

所有與本功能相關的文案與 UI 元件，**不得**出現任何暗示「建議持有／加碼到 Kelly 算出的數字」的語句。既有 `limits.py` 文案「以勝率…計算…Kelly 部位上限」已維持「上限」語氣，須作為本次新增所有文案的用詞基準：只陳述「最多不超過多少」，不陳述「應該持有多少」。此邊界為紅線，不因輸入來源（回測或手動）而放寬。

---

## 驗收條件（Given/When/Then）

**FR-1／FR-7：第 5 條上限可評估**
- Given 某標的已有一筆未過期、來源為 `manual` 的 Kelly 輸入（p=0.55, b=1.8）
  When 系統為該標的評估風控上限
  Then 第 5 條「分數 Kelly 部位上限」回傳 `passed` 或 `violated`（不得為 `not_evaluable`），且 `observed` / `threshold` 皆為非 `None` 的數值。

**FR-2：從回測帶入**
- Given 使用者對某標的執行過一次含樣本外段的回測，`out_of_sample.strategy.win_rate=0.48`、`payoff_ratio=1.6`（Kelly 的 b，非 `profit_factor`），且該回測產出時間為 3 天前
  When 使用者在設定頁對該標的點擊「帶入此標的最近一次回測結果」
  Then Kelly 輸入被填入 p=0.48、b=1.6，來源標記為 `backtest`，且畫面顯示可再編輯的欄位。

**FR-2（覆寫）**
- Given 上一步驟帶入的 Kelly 輸入已存在
  When 使用者將 p 從 0.48 改為 0.50 並儲存
  Then 來源標記轉為 `backtest_overridden`，且系統仍保留原始回測值（p=0.48）供追溯查詢。

**FR-3：時效性 — ageing**
- Given 某標的 Kelly 輸入來源為 `manual`，其 `updated_at`（使用者填寫當下的 as_of 日期）為 10 天前
  When 使用者查看該標的設定頁區塊或個股頁第 5 條上限
  Then 顯示「建議更新」（ageing）狀態徽章，且第 5 條上限仍以現有數值正常評估（非 `not_evaluable`）。
- Given 某標的 Kelly 輸入來源為 `backtest`，其 `oos_end_date` 為 10 天前（不論該筆回測實際執行或帶入的時間為何）
  When 使用者查看該標的設定頁區塊或個股頁第 5 條上限
  Then 顯示「建議更新」（ageing）狀態徽章，且第 5 條上限仍以現有數值正常評估（非 `not_evaluable`）。

**FR-3：時效性 — expired**
- Given 某標的 Kelly 輸入來源為 `manual`，其 `updated_at` 為 35 天前
  When 系統評估該標的第 5 條上限
  Then 回傳 `not_evaluable`，理由文案明確寫出「已過期」與（以 `updated_at` 起算的）距今天數，且與「從未輸入」的文案不同。
- Given 某標的 Kelly 輸入來源為 `backtest`，其 `oos_end_date` 為 35 天前
  When 系統評估該標的第 5 條上限
  Then 回傳 `not_evaluable`，理由文案明確寫出「已過期」與（以 `oos_end_date` 起算的）距今天數，且與「從未輸入」的文案不同。

**FR-3（回測時效以 `oos_end_date` 為準，非執行或帶入時間）**
- Given 使用者對某標的點擊「帶入」，server 依 ADR-0006 D-3 當場重新執行回測並取得其樣本外（out-of-sample）結果，該次樣本外區段的結束日 `oos_end_date` 為 40 天前（即使這次回測是今天才重新算出）
  When 系統計算該筆 Kelly 輸入的新鮮度
  Then 新鮮度以 `oos_end_date`（40 天前）計算為 `expired`，而非以「今天執行／帶入」的時間重新起算為 `fresh`。

**FR-4：個股頁揭露**
- Given 某標的存在來源為 `backtest`、狀態為 `fresh` 的 Kelly 輸入
  When 使用者開啟該標的個股頁
  Then 第 5 條上限旁顯示「回測帶入」來源徽章、「已更新」時效徽章，以及前往設定頁的連結。

**FR-5／FR-6：揭露文案顯示（措辭定稿前以語意驗收）**
- Given 某標的 Kelly 輸入來源為 `backtest`
  When 使用者於設定頁或個股頁查看該輸入
  Then 顯示回測揭露句（載明回測日期、策略名稱、樣本外字樣、「不代表未來勝率」字樣），且該句最終文案已取得 risk-compliance-officer 書面核准記錄。
- Given 某標的 Kelly 輸入來源為 `manual`
  When 使用者查看該輸入
  Then 顯示「系統不會查核其真實性」揭露句，且同樣取得風控核准記錄。

**FR-5：回測來源顯示欄位完整性（2026-08-19 依風控批審＋D9 §3.3 補齊）**
- Given 某標的 Kelly 輸入來源為 `backtest` 或 `backtest_overridden`，且該筆輸入依 ADR-0006 D-2 已落地完整樣本結構（`oos_round_trips`＝12、`oos_win_trips`＝7、`oos_loss_trips`＝5、`oos_excluded_boundary_trips`＝1、`oos_open_trip_at_end`＝1、`oos_observations`＝20、`p_ci_low`＝0.31、`p_ci_high`＝0.68 皆非 `None`）
  When 使用者於設定頁或個股頁查看該筆 Kelly 輸入的回測來源明細
  Then 畫面須同時顯示策略名稱、OOS 起訖日期、完整回合數、獲利回合數（`n_win`＝7）、虧損回合數（`n_loss`＝5）、跨界排除回合數（＝1）、期末未平倉回合數（＝1）、樣本觀測數（`oos_observations`＝20）、p 的 Wilson 95% 區間（0.31～0.68）、費率未查證揭露（若 `rates_verified=false`）與除權息還原狀態，缺任一欄位即視為 FR-5 未完成、不得上線。
- Given 上述同一筆輸入的 `ci_includes_no_edge` 為真（即對應 f\* bootstrap 區間下界 ≤0）
  When 使用者查看 p 的 Wilson 95% 區間
  Then 同畫面須連動顯示「此區間涵蓋『沒有優勢』的可能」語意的句子（確切措辭待 risk-compliance-officer 定稿），不得只顯示區間數字而省略此語意句。

**FR-8：定性邊界（負向驗收）**
- Given 任何與 Kelly 輸入相關的新增文案（設定頁、個股頁、API 回應）
  When qa-reviewer／risk-compliance-officer 審查文案
  Then 不得出現「建議」「應該買到」「最佳倉位」等暗示具體操作建議的字詞；違反者視為 `BLOCKING_ISSUES`，不得上線。

---

## 風險與依賴

### 風險

1. **「勝率」措辭列管觸發**：`limits.py:453, 461` 的「勝率」字樣目前受風控列管，僅在輸入恆為 `None` 的前提下才被視為安全的占位文案。本功能一旦讓 `win_rate` 真正帶有數值，等同解除列管前提，**FR-5／FR-6 揭露文案與既有 `_check_kelly_fraction` 輸出文案都必須在上線前重新送 risk-compliance-officer 審查**，不能沿用「反正目前恆為 not_evaluable 所以安全」的舊結論。
2. **回測勝率 ≠ 未來勝率**：Kelly 準則的數學前提是「重複、同分布的下注」，用歷史回測（尤其樣本內）的勝率直接當作對「這一筆、這一刻」交易的統計輸入，本質上是把「策略歷史表現」偷換成「這次下注的機率」。即使限定只用樣本外（out-of-sample）段，仍只是降低過擬合風險，不消除「歷史不代表未來」的根本限制。FR-5 的揭露文案是這個風險的必要（非充分）緩解措施。
3. **Kelly 數字被誤讀為投資建議**：Kelly 上限一旦顯示具體股數／金額，使用者容易將其理解為「系統建議我加碼到這裡」，而非「系統認為不該超過這裡」。這牴觸 CLAUDE.md 最高原則 5（面向使用者的建議類文案需風控審查，且系統定位上不做投資建議）。FR-8 的定性邊界是紅線，qa-reviewer／risk-compliance-officer 審查時須專項檢查。
4. **標的與策略張冠李戴**：若資料模型或 UI 邏輯設計不慎，可能把 A 標的、A 策略的回測勝率誤套用到 B 標的的 Kelly 輸入上，產生具體卻錯誤的風控判斷（比「無法評估」更危險，因為它看起來像是有依據的）。FR-1 明訂「可追溯、不可混淆」為強制要求。
5. **使用者藉手動輸入規避風控（gaming）**：手動輸入不設任何合理性防呆（範圍外第 4 項），使用者可填入樂觀到不合理的勝率／盈虧比，讓第 5 條上限形同虛設卻仍顯示「passed」而非「not_evaluable」，觀感上比現況（誠實地顯示無法評估）更糟。此風險目前刻意先不擋（避免本期範圍過大），但需 CEO／風控在開放問題 Q4 明確拍板是否可接受，以及未來是否要補防呆。
6. **背景資訊與程式碼現況落差**：任務背景提及回測「三策略」，程式碼現況僅有 `ma_cross` 一種。若 C5 的原始構想是建立在「多策略可選」的前提上，本 PRD 目前僅能以「單一策略」的現況設計；一旦已知限制第 8 項（回測策略擴充）先於或同時推進，FR-1 的資料模型是否要提前預留 `strategy_id` 維度，需要 tech-architect 評估（見開放問題 Q6）。

### 依賴

- tech-architect：資料模型 schema（是否含 `strategy_id`、儲存於何處：`app/settings` 或新模組）、`app/advice/book.py` 接線方式的技術評估。
- dev-lead：後端 API（新增/查詢/編輯 Kelly 輸入、過期判定邏輯）、`book.py` 接線實作。
- frontend-engineer：設定頁新區塊、個股頁 `LimitsCheckList.tsx` 揭露元件。
- risk-compliance-officer：FR-5／FR-6 揭露文案定稿審查、`_check_kelly_fraction` 既有文案的重新審查、FR-8 定性邊界的審查基準訂定。
- qa-reviewer／qa-e2e：依本 PRD 驗收條件把關，FR-8 的負向驗收尤其需要專項檢查（不得出現建議性字詞）。

---

## 開放問題（待 CEO 或其他部門回答）

1. **【CEO】** `work/機會清單.md` 於目前分支找不到實體檔案，C5 的原始意圖與優先序無法直接核對。請 CEO（或維護該清單的角色）提供正確路徑或補齊該檔案；若本 PRD 與機會清單原文有出入，請指出差異，本 PRD 將據以修訂。
2. **【tech-architect】** Kelly 輸入的資料模型鍵值該用 `(symbol)` 還是 `(symbol, strategy_id)`？目前只有一個策略（`ma_cross`），但若未來策略擴充（已知限制第 8 項），現在的設計選擇會影響遷移成本。
3. **【CEO ／ tech-architect】** 若使用者尚未對某標的執行過回測，是否要求「先跑一次回測才能啟用 Kelly 上限」，還是本期就允許純手動輸入、完全不依賴回測？本 PRD 預設兩者並存（FR-2），但業務上是否有偏好需要確認。
4. **【risk-compliance-officer ／ CEO】** 手動輸入的 p、b 是否需要比照淨值先例的「合理性區間檢查」（例如勝率 > 90% 顯示警示但不拒絕）？本 PRD 目前列為非目標，但風險 5 已說明潛在的規避風控疑慮，需要明確決議是否本期就要補上，或留待下一版。
5. **【tech-architect ／ CEO】** 時效性規則的天數是否直接沿用淨值先例的「7 天提醒／30 天失效」，還是 Kelly 輸入（尤其回測衍生）需要不同的天數設定（例如回測更新頻率通常低於帳戶淨值變動頻率，30 天可能偏短或偏長）？
6. **【CEO】** 已知限制文件第 8 項（回測策略僅 `ma_cross`）與本次 C5 是否有排期依賴關係？若 C5 的效用高度仰賴「多策略可選」，是否應調整兩者的優先序或並行推動？
7. **【risk-compliance-officer】** FR-5／FR-6 的揭露文案本 PRD 僅給出語意邊界，確切措辭（含 `_check_kelly_fraction` 既有文案是否需要同步微調）需要風控與 tech-writer 協作定稿，請風控指派審查窗口與時程。

---

## 品質檢查清單（PM 自查）

- [x] 每條功能需求（FR-1～FR-8）皆有至少一組 Given/When/Then。
- [x] 範圍外（非目標）明確列出 7 項。
- [x] 開放問題皆指名對象（CEO / tech-architect / risk-compliance-officer）。
- [x] 未綁死技術實作細節（資料模型 schema 明確留給 tech-architect 決定）。
- [x] 未偷改或放寬驗收條件；FR-8 的負向驗收明訂 `BLOCKING_ISSUES` 後果。

---

## 協調人事實校正(2026-08-19)

PM 撰寫本 PRD 期間開發容器暫時回滾至舊版樹,以下兩點以現行 HEAD 為準更正:
1. `work/機會清單.md` **存在**於 product/stock-desk(C5 條目原文:「Kelly 準則輸入計算
   (勝率/盈虧比可從 backtest 或未來交易日誌提取),否則第 5 條上限長期形同虛設」,P2,
   與 B2 送審連動)——開放問題 1 銷項,PRD 重建之需求與原文一致。
2. 回測現況為**三策略**(ma_cross/rsi_reversal/breakout,FR-10/11 已交付)非僅 ma_cross
   ——開放問題 6 的排期依賴不存在,銷項。
其餘開放問題(2/3/4/5/7)維持有效,依序交 tech-architect/CEO/風控。

## CEO 裁決(2026-08-19)

- 開放問題 3:採**混合方案(c)**——回測樣本外帶入+可手動編輯並存,帶入值可追溯可改。
- 開放問題 5:時效**沿用淨值先例 7/30 天**(滿 7 天提醒、滿 30 天失效回 not_evaluable)。
- 開放問題 4:手動輸入**設合理性區間檢查**(p∈(0,1)、b>0,超出拒收不靜默 clamp,比照淨值三檔防呆先例)。
- 餘開放問題 2 交 tech-architect(資料模型鍵值)、7 交風控(FR-5/FR-6 揭露句+「勝率」列管重審)。
