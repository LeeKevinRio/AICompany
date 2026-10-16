# tech-architect：T1-01 Totals no_data 改 null 影響面評估、T1-02 估值狀態判定設計（2026-10-16）

> 轉存：coordinator，逐字。coordinator 定案（CEO 可推翻）：
> 1. T1-02 依 B-8 建議另立 ADR，編號 ADR-0028（ADR-0027 已保留給 R-106～R-116 的預測紀錄帳）。
> 2. Q-A1：空帳的總額也回 null（與 A-1 已顯示「—」一致），不新增 `empty` 狀態；PM 可推翻。
> 3. T1-12 依附件 A-5 在獨立 worktree 開發；合併仍待 CEO 對 Codex 的決定。

---

## 1. 本次結論

T1-01、T1-02 兩項評估都做完了，dev-lead 可以照下面的檔案與函式動工。另有 7 個開放問題要 PM、風控、CEO 確認（列在附件 A-6、B-7），這些問題不卡 T1-12 後端開工。

- **T1-01（Q-7 的答案）**
  - 後端實際讀 `Totals` 金額的地方只有兩處：`advice/book.py::_book_equity` 和 `api/settings.py::_review_reported_net_worth`。警示、風險上限、advice 卡、`/limits` 都是經由 `_book_equity` 間接讀到。playbook 自己算市值，不讀 `Totals`。目前沒有匯出功能，也沒有 shared schema。
  - 建議做法：`no_data` 時五個金額欄位全部回 null，`cost_twd` 也一起回 null，空帳也算在內；`status` 的語意不變。
  - 上面兩個消費者改成從逐檔欄位加總，不再讀 `totals`，所以內部行為逐位不變，也沒有任何地方「把 null 當 0」。
  - 不需要新 ADR，因為 ADR-0025 D-12 與 AV-16 已經做了決定，寫進 PR 說明即可。
- **T1-02**
  - 狀態判定放在一個新的純函式模組，由 summary 層呼叫。依據是「實際用到的那根日線日期」對照「交易所當地時鐘與交易日曆」。時間切點全部參數化，休市日曆抽象成官方與觀察兩種來源，並且在 import graph 上隔離所有盤中報價模組（AV-1）。
  - PRD 的四種狀態不夠用：至少還要加「資料落後」和「當日暫定」兩種，否則會把三天前的收盤標成「前一收盤」，或把盤中的暫定 bar 標成「收盤」。
  - 我建議 T1-02 立 ADR，編號由 coordinator 分配，避開 0026。

## 2. 各部門回報

- **tech-architect（本人）**：讀了 ADR-0009／0014／0016／0019／0025、PRD §5–§6、A-1 的 qa 報告。也讀了 `summary.py`、`valuation.py`、`book.py`、`limits.py`、`settings.py`、`net_worth.py`、`calendar.py`、`freshness.py`、`intraday_session.py`、`quote_params.py`、`services/market.py`，前端 `types.ts`、`SummaryCards.tsx`（main 與 A-1 worktree 兩版）、`format.ts`，以及所有含 `totals` 的後端測試。
  - 沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。
  - 沒有碰 ADR-0026 和 T-1～T-5，那部分是另一位 tech-architect 的範圍。
- **其他部門**（product-manager、dev-lead、frontend-engineer、data-engineer、qa-reviewer、qa-e2e、risk-compliance-officer、creative-lead、tech-writer、devops-sre 等）：本次未參與，這是純評估任務。
  - 附件 B 的狀態字面之後一定要經過 creative-lead 起草、風控逐字審（PV-1），本次只定內部代稱，沒有寫任何使用者面字面。

## 3. 驗證

- **我做了什麼、沒做什麼**：結論全部來自 Read 與 Grep，每條都附〔事實：檔案:行號〕。我沒有跑 pytest、vitest、tsc（唯讀），也沒有 Codex 第二意見。
- **qa-reviewer 可以怎麼核對**：
  - 附件 A-1 的消費者清單：用 Grep 搜 `\.totals\.` 和 `build_summary` 重現。
  - 附件 A-5 與 B-6 的約束：逐條都能用測試或 grep 檢查。
- **需要 CEO 親自確認的方向**：
  1. 空帳（零持倉）的總額也顯示「—」：現況就是這樣顯示（A-1 已遮罩），API 會跟著改成 null。
  2. 附件 B 新增的「資料落後」「當日暫定」兩種狀態是否接受（Q-B2）。

## 4. 下一步

1. **coordinator**：把附件 A、B 落檔到 `work/`。附件 B 決定要不要轉 ADR，並分配編號。
2. **dev-lead 與 frontend-engineer**：依附件 A-5 開 T1-12。後端可以先上，不必等 A-1 合併：main 的 `formatMoney(null)` 本來就顯示「—」，見 A-4。
3. **data-engineer**：T1-07 除了原本的查證項目，再加一項——各日線來源在盤中或收盤剛結束時，會不會回傳「當日、尚未定案」的 bar，以及各來源的定案時間（附件 B-7 的 Q-B7）。這是一個潛在的資料正確性風險。

---

# 附件 A：T1-01 `Totals` 在 `no_data` 時改為 null 的影響面評估（回答 Q-7）

## A-0 評估摘要

- **採用**：`Totals` 的五個金額欄位改為 `Decimal | None`。
  - `status == "no_data"` 時五個都回 null，含零持倉的空帳；其他狀態都不是 null。這個對應關係用 model validator 強制。
  - 內部的兩個消費者改讀新的 helper `valued_market_value_twd(positions)`，逐檔加總，空集合的和為 0；完整性另由既有旗標表達。
- **否決**：
  - (i) 把 null 一路傳進 `PortfolioContext`：會改變風控已核可的原因句，影響面大。
  - (iii) 讀取端寫 `None → 0`：字面上就違反 AC-B4b-3。

## A-1 消費者完整清單

**後端 production code**

| # | 消費者 | 讀 `totals` 的方式 | 處置 |
|---|---|---|---|
| 1 | `app/advice/book.py::_book_equity` | `float(summary.totals.market_value_twd)`〔事實：book.py:575-583〕。被 L988（`_book_level_notes`，只取 count）、L1183（`build_book_level_context`）、L1294（`build_book_context`）呼叫；equity 再寫進 `total_equity_twd`，也寫進 `gross_exposure_twd`（當 net_worth 存在時）〔事實：book.py:1196、1199、1397、1404〕 | **要改**：改用 helper（A-5 B2） |
| 2 | `app/api/settings.py::_review_reported_net_worth` | `float(summary.totals.market_value_twd)`〔事實：settings.py:352〕 | **要改**：改用 helper（A-5 B3）。`valued_count == 0` 已經走「無已估值部位」分支〔事實：net_worth.py:101-102〕，回存的 yardstick 已是 None〔事實：settings.py:359〕 |
| 3 | `app/advice/limits.py`（五條上限、`notional_caps`） | 不直接讀 totals，只讀 context 的 `total_equity_twd`／`gross_exposure_twd`。`None` 和 `≤0` 都走 not_evaluable〔事實：limits.py:832、969、1188、1302、1550-1552〕。總曝險先檢查 `gross_exposure_twd is None`，再檢查 `book_fully_valued`〔事實：limits.py:1270-1278〕 | 不適用（經由 #1 間接）。**不改**，詳見 A-3 |
| 4 | `app/advice/book_limits.py`（`/api/portfolio/limits` 整書彙總） | 呼叫 `build_book_level_context`／`build_book_context`〔事實：book_limits.py:379、528〕 | 不適用（經由 #1） |
| 5 | `app/alerts/snapshot.py`（警示、推播） | `build_summary` → `build_book_context`〔事實：snapshot.py:130-142〕 | 不適用（經由 #1） |
| 6 | `app/api/advice.py`（advice 卡） | `_book_freshness_notes` 只讀 positions〔事實：advice.py:130-141〕；caps 經由 `build_book_context`〔事實：advice.py:167、189〕 | 不適用 |
| 7 | `app/api/portfolio.py` | `/summary` 原樣回傳〔事實：portfolio.py:106-125〕；`/limits` 經由 #4〔事實：portfolio.py:150、180-189〕 | 序列化會自動變成 null，不必改程式 |
| 8 | playbook | 自己用 snapshot 的收盤乘股數計算〔事實：playbook/engine.py:207-219〕，不 import summary | 不適用 |
| 9 | 匯出、shared schema | 目前沒有匯出端點。`apps/stock-desk/shared/` 只有 `forbidden-terms.json`、`market-currency.json`。沒有 OpenAPI 快照 | 不適用（Phase 2 匯出的約束見 A-5 C4） |

**前端**

| # | 消費者 | 現況 | 處置 |
|---|---|---|---|
| 10 | `SummaryCards.tsx` | main 版直接 `formatMoney(totals.market_value_twd…)`〔事實：main SummaryCards.tsx:71、96、109、127〕；A-1 版依 `status === "no_data"` 遮罩成 null〔事實：worktree SummaryCards.tsx:63-71〕 | 保留 A-1 的遮罩，當作縱深防禦；只更新註解 |
| 11 | `types.ts::PortfolioTotals` | 金額宣告為 `string`〔事實：types.ts:257-265〕 | 改成 `string \| null` |
| 12 | 其他 | `page.tsx` 只是把 totals 往下傳〔事實：page.tsx:55-57〕。`totals.cost_twd` 沒有任何前端讀者（Grep 確認）。`keyLevelsAnchor.ts:8`、`oneLinerWording.ts:118-140` 只在註解裡提到 | 不適用 |

**後端測試**

- 會因 null 而失敗、必須改的：
  - `test_portfolio_summary.py:146`
  - `test_unusable_fx_f1b.py:845`
  - `test_x3c_currency_market_mismatch.py:358`
  - fixture：`advice_helpers.py:284-310`（`book_summary` 在沒有 valued rows 時）、`test_unusable_close_f1.py:285-298`（`_empty_summary`）
- 不改、但必須維持綠燈（這就是 partial／complete 的回歸證據）：
  - `test_portfolio_summary.py:149-181、211-231、248-257`
  - `test_unusable_fx_f1b.py:922-946`
  - `test_x3c…:955、1198`
  - `test_demo_seed.py:256`
  - `test_api_advice.py:145-180`
  - `test_api_settings.py:160-163`
  - `test_advice_book.py:108-121`
  - `test_portfolio_coverage_wiring.py:600`

## A-2 null 語意（逐欄位）

| 欄位 | `no_data`（含空帳） | `partial` | `complete` | 理由 |
|---|---|---|---|---|
| `market_value_twd` | null | 只加總 ok 列（不變） | 全部加總（不變） | AV-16：輸入缺值時輸出 null |
| `unrealized_pnl_twd` | null | 不變 | 不變 | 由市值減成本導出，任一邊是 null 結果就是 null |
| `asset_contribution_twd` | null | 不變 | 不變 | 同上 |
| `fx_contribution_twd` | null | 不變 | 不變 | 同上 |
| `cost_twd` | **null（回答 PRD Q-7 後半）** | 不變 | 不變 | 見下方說明 |
| `status` | 仍為 `no_data` | `partial` | `complete` | 語意不變，見 A-4 |

`cost_twd` 也回 null 的理由：

- 它與市值屬於同一個加總範圍，都是只加 ok 列〔事實：summary.py:228-238〕；非 ok 列的逐檔 `cost_twd` 本來就是 None〔事實：summary.py:90-96、valuation.py:315-318〕。
- 市值是 null、成本卻有數字，這種組合會誘使新消費者自行相除。
- 目前沒有任何讀者，改成 null 的代價是零。

空帳的說明：`_totals_status` 在 `ok == 0` 時回 `no_data`，空帳也包括在內〔事實：summary.py:259-261〕；A-1 也已經讓空帳的四格顯示「—」。照 D-12 字面「no_data → null」並維持「null 與 no_data 一對一」，就不必新增 status 值。（另一案是新增 `empty` 狀態，會改到 status 列舉和風控核可的橫幅，見 A-6 Q-A1。）

## A-3 內部消費者的三個方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) `_book_equity` 回傳 `float \| None`，null 一路傳下去 | 語意最純 | 有 net_worth 時，`no_data` 帳的總曝險原因句會從「帳不完整」〔事實：limits.py:1272-1278〕變成「缺少組合總市值」〔事實：limits.py:1270-1271〕（原因是檢查順序）；空帳的總曝險會從 passed 0% 變成 not_evaluable；要改 `_sector_unclassified_note` 的型別〔事實：book.py:877〕 | 動到風控已核可的字面與判定，要重新送審 |
| (ii) **採用**：新增 `valued_market_value_twd`，逐檔加總 ok 列 | 消費者不再讀顯示用的欄位；內部行為逐位不變，因為加數相同、順序相同，見 A-5 證明 5；不必改 `limits.py` | 「顯示用總額」和「內部分母」從此成為兩個概念，要在 docstring 寫明 | 低。新消費者若又讀 `totals`，會被 grep 守門擋下（A-5 C1） |
| (iii) 讀取端寫 `x if x is not None else 0` | 改一行就好 | 違反 AC-B4b-3，也把不變式藏了起來 | 否決 |

為什麼 (ii) 不算「把 null 當 0」：

- 它根本不讀 totals。它的 0 是「已估值部位這個空集合的和」，不是在替一個缺漏的值補數字。
- 帳是否完整，另由 `book_fully_valued`、`valued_count`、`numerator_complete` 表達〔事實：book.py:586-592、988-989；limits.py:1545-1547〕。
- 往下游走，任何 ≤0 的 equity 都會變成 not_evaluable，總曝險另外受 `book_fully_valued` 把關。所以沒有任何 0 會以比率或金額的形式流到輸出端，AV-16 在輸出端成立。

## A-4 對 ADR-0016 漲跌欄與 `status` 語意的影響

- **漲跌欄**：沒有影響。
  - `change` 是逐列由 `ChangeScreen` 算的；F1 只看現價可不可得，不看 `valuation.status`〔事實：ADR-0016:100〕。
  - 所以「`no_data` 帳裡某一列有漲跌、但 totals 是 null」是合理的組合：漲跌是同幣別相除，不是 TWD 金額。
  - D-3 註記說「照常回應估值與 totals」〔事實：ADR-0016:95〕，指的是不回 500，改成 null 後仍然成立。K-4（下游不讀 `.change`）和 `change_mode` 都不受影響。
  - 建議加一個測試：一筆 US 列有現價但缺匯率，斷言 `totals` 是 null，同時該列 `change` 可以不是 null。
- **`status`**：語意不變，仍然只代表涵蓋範圍，不代表新鮮度〔事實：summary.py:46-53〕。null 是由 status 推導出來的，不是新的狀態。
- **待 tech-writer 跟進**：ADR-0014（proposed）D-6 寫「`Totals` 欄位與 `status` 語意不變（`summary.py:27-44`）」〔事實：ADR-0014:185〕。ADR-0014 日後要轉 accepted 時需要勘誤，改成「金額欄位依 ADR-0025 D-12 於 `no_data` 時為 null；status 語意不變」，行號也已經過時。這不算衝突，因為 accepted 的 ADR-0025 優先。
- **上線順序上的安全性**：main 前端目前沒有 A-1，但 `formatMoney(null)` 回「—」、`pnlColorClass(null)` 回中性灰〔事實：format.ts:159、259〕。後端先改成 null，畫面也不會出現 "null"、"NaN" 或 NT$0；只差 TS 型別要對齊。

## A-5 對實作的約束（逐條可檢查，交 dev-lead／frontend-engineer）

**B. 後端**

- **B1** `app/portfolio/summary.py`
  - (a) `Totals` 的五個金額欄位改成 `Decimal | None`（L57-61）。
  - (b) 加 `@model_validator(mode="after")`：`status == "no_data"` ⇔ 五個欄位全是 None，違反就 raise。
  - (c) `build_summary` 在 L240-247 改成：`ok_count == 0` 時五個都給 None，否則運算式逐字不變。
  - (d) 新增公開函式 `valued_market_value_twd(positions: Sequence[SummaryPosition]) -> Decimal`：只加 `valuation.status == "ok" and market_value_twd is not None` 的列，空集合回 `Decimal(0)`。docstring 要寫明：「內部分母，不是顯示用總額；完整性由呼叫端另外判斷。」
  - (e) 更新 `Totals` docstring 的 null 語意。
- **B2** `app/advice/book.py::_book_equity`（L575-583）：改成 `float(valued_market_value_twd(summary.positions))`，回傳型別與三個呼叫端都不動；docstring L578-579 同步更新。
- **B3** `app/api/settings.py::_review_reported_net_worth`（L352）：同 B2；L353-359 不動。
- **B4** 不准修改：`advice/limits.py`、`book_limits.py`、`alerts/snapshot.py`、`api/advice.py`、`api/portfolio.py`、`playbook/**`。qa 用 `git diff --stat` 檢查。

**C. 邊界守門**

- **C1** 新增 grep 或 AST 測試：`app/**/*.py` 裡，除了 `app/portfolio/summary.py`，不得出現 `\.totals\.(cost_twd|market_value_twd|unrealized_pnl_twd|asset_contribution_twd|fx_contribution_twd)`。
- **C2** 新增等值測試：在 partial 與 complete 的 fixture 上，`totals.market_value_twd == valued_market_value_twd(positions)`，而且 `_book_equity(summary)[0] == float(totals.market_value_twd)`。這是內部行為逐位不變的證明。
- **C3** Phase 3 的 `app/plan`、`app/forecast`、`app/outlook` 不得讀 `Totals` 的金額欄位。要用帳的市值，必須用 helper，並一起讀完整性旗標（C1 的 grep 會涵蓋）。
- **C4** Phase 2 匯出（NP-B3a）若要輸出總額，必須保留 null，不得寫成 0 或空字串的數字。

**T. 測試（對應 AC-B4b-1～3）**

- **T1** 契約測試：全缺價時 JSON 五個欄位是 `null`、`status == "no_data"`（AC-B4b-1）。空帳同樣是 null（改 `test_portfolio_summary.py:146`）。
- **T2** 驗證 validator 雙向擋得住：`no_data` 卻有數字、`partial` 卻是 None，兩種都要 raise。
- **T3** 回歸：A-1 列出的「不改且維持綠燈」測試，函式本體不得修改（AC-B4b-2）。qa 用 `git diff` 確認。
- **T4** 消費者測試（AC-B4b-3）：
  - (a) 帳裡有持倉、全部缺價、有自報淨值：`/api/portfolio/limits` 和 `/api/advice/{s}` 的總曝險為 not_evaluable，detail 以 `GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` 開頭（與現況相同）；caps 1／2／4／5 為 not_evaluable。
  - (b) 空帳加自報淨值：總曝險結果釘住現況（不在本案判斷它對不對）。
  - (c) `PUT /api/settings` 在 `no_data` 帳上：notes 帶 `NET_WORTH_NO_VALUED_BOOK_NOTE`、yardstick 為 None。
  - (d) 警示 snapshot 在 `no_data` 帳上不拋例外（可以沿用 `test_unusable_fx_f1b.py:826-832` 的模式）。
- **T5** 修正 fixture：`advice_helpers.py::book_summary`、`test_unusable_close_f1.py::_empty_summary` 在沒有 valued rows 時改成 None。

**F. 前端**

- **F1** `types.ts:257-265`：五個金額改成 `string | null`，註解寫「null iff status no_data」。
- **F2** `SummaryCards.tsx`：保留 A-1 的 status 遮罩，只更新 L63-66 的註解。
- **F3** A-1 測試 `summaryCardsNoDataTotals.test.ts`：
  - 新增「payload 金額為 null」的案例；
  - `complete` 全 0 的斷言改成 `toBe("NT$0")`（吸收 qa-reviewer 的 non-blocking 建議）；
  - 斷言畫面不含 `null`、`NaN`。
- **F4**（non-blocking）`summaryBanner.test.ts` 等測試裡的 no_data fixture 改用 null，反映真實契約。
- **F5** qa-e2e 在 375 與 1280 寬度實機驗收 AC-B4b-4。

**D. 文件**：API 契約變更**不需要新 ADR**（ADR-0025 D-12 與 AV-16 已經決定）。PR 說明必須包含：

- 五個欄位改前／改後的 JSON 對照；
- 空帳的行為；
- A-1 的消費者表；
- 為什麼採 (ii)；
- T1～T4 的結果。

## A-6 開放問題

- **Q-A1（PM）**：空帳 null 的做法（本文建議）是否接受？
  - 另案是新增 `status = "empty"`：會改到 status 列舉、前端 `SummaryStatus` 和橫幅邏輯。
  - 順帶揭露一個既有狀況，不是本案造成的：空帳目前會顯示 no_data 橫幅「所有部位皆無法估值，總計無法計算。」〔事實：oneLinerWording.ts:140〕。要不要另外處理由 PM 決定，改字面需要風控審查。

---

# 附件 B：T1-02 估值狀態判定規則設計（對應 AC-B5a-1～6）

## B-0 評估摘要

- **採用**：判定依據是「證據優先、時鐘為輔」。
  - 「收盤」只在手上確實有當日、而且已定案的日線時才給；其餘情況一律顯示實際用到的那根 bar 的日期。
  - 判定放在新的純函式模組 `app/data/close_state.py`（暫名），由 `build_summary` 逐列呼叫。前端只把列舉值對應到字面，不自己看時間（ADR-0014 D-7(d)）。
- **否決**：
  - 只靠時鐘推算：會把「抓不到資料」標成「收盤」。
  - 放在 `valuation.py`：違反 ADR-0014 I-10「估值器不判斷時段」〔事實：ADR-0014:443〕。
  - 由前端推算：違反 ADR-0014 D-7(d)〔事實：ADR-0014:206〕。
  - 重用 `intraday_session.classify_session`：那是報價領域的模組，參數 P-6（13:25）是 MIS 的試撮避讓點，不是交易所收盤時間〔事實：quote_params.py:46-50〕；重用會讓日線標籤依賴盤中報價模組，碰到 AV-1 的精神。

## B-1 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A（採用）**：後端純函式，用 bar 日期加交易所時鐘加可替換日曆，per-row 輸出列舉 | 可以用字面時間戳做表格驅動測試；前端零推算；日曆來源可替換 | 要新增 API 欄位；PRD 四種狀態不夠用，要加兩種 | 參數未查證之前不能出貨（B-3） |
| B：只靠時鐘判斷時段 | 簡單 | 抓取失敗或資料落後時仍會標「收盤」 | 過度宣稱，違反 PV-6 精神 |
| C：前端依 `price.as_of` 和瀏覽器時鐘推算 | 不用改後端 | 違反 ADR-0014 D-7(d)；重蹈 B1／N1 的時區與假日錯誤〔事實：tradingCalendar.ts:5-28〕 | 否決 |
| D：重用 `intraday_session` | 少一份定義 | 依賴報價模組；13:25 的語意不對 | 否決 |

## B-2 輸入（全部注入，函式內部不做 I/O、不讀時鐘）

| 輸入 | 來源 | 說明 |
|---|---|---|
| `now: datetime`（tz-aware） | **與估值器同一次時鐘讀值** | 估值器的 `today` 取自 `self._clock().date()`，預設是 UTC〔事實：valuation.py:343、382〕；`build_summary` 另外又讀一次 `datetime.now(UTC)`〔事實：summary.py:206〕。約束：一次 build 只能有一個瞬間 |
| `market` | position | TW 或 US |
| `price_date: date \| None` | `PriceInfo.as_of`，也就是該列實際用到的 bar 日期〔事實：valuation.py:509-516〕 | None 代表沒有標籤 |
| `price_kind` | `PriceInfo.price_kind`〔事實：valuation.py:221-223〕 | 只處理 `daily_close` |
| `acquired_at: datetime \| None` | 該序列的 `ProviderResult.as_of`，即 ADR-0019 D-4／D-5 的單一取得時間基準〔事實：ADR-0019:100-105〕 | 用來判斷是否定案。透過 `PositionValuation` 的內部欄位傳遞（比照不序列化的 `change_basis`〔事實：valuation.py:320-327〕），**不得**讀 `tail_fetched_at`〔事實：ADR-0019:157〕，也不序列化 |
| `calendar: SessionCalendar` | 新的 protocol（B-4） | `is_session(day)`、`previous_session(day)`、`basis ∈ {official, observed}` |
| `hours: MarketHours` | 新的參數模組（B-3） | 每個市場一組 |

## B-3 時間切點參數化（數值等 T1-07 補入）

新增 `app/data/market_hours.py`（暫名）。只用純常數，不讀環境變數（比照 `quote_params.py` 的規矩〔事實：quote_params.py:9-18〕）。每個參數都附 `verified_on: date | None` 與出處欄位。

| 編號 | 參數 | TW | US | 說明 |
|---|---|---|---|---|
| VS-1 | 交易所時區 | `Asia/Taipei` | `America/New_York` | 直接引用 `freshness.policy_for(m).timezone`〔事實：freshness.py:109-121〕，不另抄一份 |
| VS-2 | `session_open` | 待 T1-07（現有程式寫 09:00，標示為交易所事實、未查證〔事實：quote_params.py:29-32〕） | 待 T1-07 | 早於此時刻為「開盤前」。Phase 3 的 AV-17 `recorded_after_next_open` 必須共用同一個常數 |
| VS-3 | `session_close` | 待 T1-07（現有程式註解寫 13:30，未查證〔事實：quote_params.py:46-49〕） | 待 T1-07 | 刻意與 ADR-0014 的 P-6（13:25）分開：13:25～13:30 在兩邊都顯示前一收盤，結果一致 |
| VS-4 | `close_final_after` | **預設引用** `TW_POLICY.publish_cutoff`（現值 15:00，未查證〔事實：freshness.py:106-111；ADR-0009:52-54〕） | 引用 `US_POLICY.publish_cutoff` | 日期為 D 的 bar，只有 `acquired_at` ≥ D 當地的 VS-4，才算定案收盤。必須引用同一個常數，不得複製；改這個值要連同 ADR-0009 D-2 一起修訂〔事實：ADR-0009:149〕。若 T1-07 證明各來源的定案時間不同，再升級成 (market, source) 鍵（ADR-0009 已列管同一議題〔事實：ADR-0009:148〕） |
| VS-5 | 官方日曆涵蓋年度 | 待 T1-07／T1-13 | 無來源（D-9 只列 TWSE〔事實：ADR-0025:455〕） | 超出涵蓋範圍就退回 observed，並揭露 |

**出貨閘門**：任一參數的 `verified_on` 還是 None，T1-17 就不得合併（PV-6，PRD Phase 1 出口條件第 4 點）。

## B-4 日曆抽象與 `data/calendar.py` 的關係

- 新增 `SessionCalendar` protocol，以及兩個實作：
  - `ObservedSessionCalendar`：包裝現有的 `TradingCalendar`，資料來自 `PriceBarCache.market_trading_days`〔事實：services/market.py:34-42〕。
    - 過去的日子**只採觀察到的事實**，不用週一至週五規則推算。`previous_session(D)` 等於「已觀察到、且早於 D 的最大交易日」，與 `observed_days_after` 和 C4 的取捨一致〔事實：calendar.py:139-154；services/market.py:122-137〕。
    - 今天還沒有 bar，所以「今天是不是交易日」只能用週一至週五規則判斷〔事實：calendar.py:74-85〕。
  - `OfficialSessionCalendar`：由 T1-13（NP-B5b）實作，查得到就回官方答案，查不到（年度未公布、來源失敗）就交給 observed，並把 `basis` 標為 observed（F-6，AC-B5a-5）。
- **不得**修改 `TradingCalendar` 的既有語意：playbook 依賴它的週一至週五 fallback〔事實：calendar.py:39-43〕。
- PRD NP-B5b 要求「日曆其餘邏輯使用同一來源」：Phase 3 的 `valid_until_session` 和 AV-17 也應該注入同一個 `SessionCalendar`。

## B-5 狀態機（由上往下，第一條成立就採用）

先定義：`local = now.astimezone(VS-1)`、`D = local.date()`、`t = local.time()`、`P = calendar.previous_session(D)`。若 `calendar.is_session(D)`，再依 t 分成三段：`t < VS-2` 為 `pre_open`；`VS-2 ≤ t < VS-3` 為 `in_session`；`t ≥ VS-3` 為 `post_close`。

| 規則 | 條件 | 內部狀態 | `reference_date` | 對應 AC |
|---|---|---|---|---|
| R0 | `price_date is None` | 不輸出（該列現價顯示「—」） | — | — |
| R1 | `price_kind != "daily_close"` | `not_applicable`（Phase 1 不可能出現，由 ADR-0014 負責） | — | AV-1 |
| R2 | `price_date > D` | `date_anomaly`（fail-closed，記 WARNING，不宣稱收盤） | price_date | — |
| R3 | 交易日且 `price_date == D`，而且 `acquired_at` 不是 None 且 ≥ D 的 VS-4 | `close` | D | B5a-3 |
| R3′ | 交易日且 `price_date == D`，但不滿足 R3 | `provisional_today`（**新增**：當日 bar 可能還沒定案） | D | — |
| R4a | 交易日、`pre_open`、`price_date == P` | `close`（最近一個已完成交易日的收盤；**待 PM 確認，Q-B1**） | P | — |
| R4b | 交易日、`in_session`、`price_date == P` | `prior_close_reference`，子原因 `in_session` | P | B5a-1 |
| R4c | 交易日、`post_close`、`price_date == P` | `prior_close_reference`，子原因 `after_close_pending`（可再以 VS-4 細分為「尚未公布」或「尚未取得」） | P | B5a-2 |
| R5 | 非交易日、`price_date == P` | `market_closed` | P | B5a-4 |
| R6 | 其他（`price_date < P`） | `lagging`（**新增**），附 `lag_sessions`：(price_date, P] 內的交易日數；observed 模式只數觀察到的日子，算不出來就給 null | price_date | — |

逐列輸出 `SummaryPosition.valuation_state`（新增、可為 None、只增不改）：`{state, sub_reason, reference_date, session_date: D, calendar_basis}`。

book 層級新增 `calendar_basis`（只要有一列是 observed，就標 observed），前端據此顯示「休市日以觀察資料推算」（AC-B5a-5）。

**AC-B5a-6**：PV-49 的條件是「盤中價接上之前」〔事實：PV 文件 L272〕，等同 `change_mode == "close_only"`（ADR-0016 D-8 的單一輸入〔事實：summary.py:119-122〕）。前端只依這一欄決定是否顯示常駐揭露，不另設旗標。

**已知限制（照實寫進 ADR 的 Consequences）**：

1. observed 模式下，「今天」若是平日的休市日，今天無法判定為休市，只能落在 R4b 或 R4c，顯示前一收盤並附日期。方向是保守的：不會宣稱收盤，也不會宣稱即時。
2. 官方年表不含颱風假之類的臨時休市：當天會落在 R4c；隔天 `P` 可能指向那個實際沒開市的日子，造成假的 `lagging`。這屬於低報新鮮度，方向保守。不得以「沒人有這天的 bar」反推休市，那是 ADR-0009 已否決的方案 E 負向推論〔事實：ADR-0009:37〕。
3. 官方日曆判定某天休市時，ADR-0009 的 `latest_completed_session` 仍只看週一至週五〔事實：freshness.py:83-89〕，所以同一列可能同時出現「休市」標籤和資料徽章「可能未含最近交易日」。Phase 1 不改 `judge()`；若要讓 freshness 吃官方假日表，屬於 ADR-0009 修訂〔事實：ADR-0009:149〕，建議在 T1-13 時另案評估。

## B-6 對實作的約束（逐條可檢查，交 dev-lead、frontend-engineer）

1. `close_state.py` 與 `market_hours.py` 的 import graph 不得碰到 `app.data.quote_params`、`app.data.intraday_session`、`app.data.quote_quality`、`app.services.quotes`、`app.data.providers.twse_mis`。寫法比照 `test_interface_quote.py:203-211`。
2. `valuation.py` 不得出現 VS 常數，也不得呼叫狀態判定（ADR-0014 I-10）。呼叫點只能在 `app/portfolio/summary.py::build_summary`。
3. 一次 build 只讀一次時鐘；用注入固定 clock 的測試，斷言估值器的 `today` 與判定用的 `now` 來自同一個值。
4. `valuation_state` 只供顯示：advice、alerts、kelly、playbook、signals、limits、outlook、plan、forecast 都不得讀它（grep 測試，比照 ADR-0016 K-4〔事實：ADR-0016:226〕）。
5. 表格驅動測試用字面時間戳，至少要涵蓋：
   - VS-2、VS-3、VS-4 各自前 1 秒與當下；
   - 週六；官方休市日；observed 模式；R2、R3′、R6；`intraday_quote`；
   - US 在 DST 切換日前後各一個案例。
   R0～R6 每條至少一例。
6. 前端：狀態元件只把列舉值對應到字面，元件裡不得出現 `new Date(`、`Date.now`、時段常數，也不得 import `tradingCalendar.ts`（grep 測試）。
7. 不得移除或取代既有的資料狀態徽章（`data_status`／`is_within_ttl`）：兩者描述不同的事，並列顯示。
8. 字面由 creative-lead 起草（T1-03）、風控逐字審，字面、掃描器、測試必須在同一個 commit（PV-1）。不寫死「前一」二字的狀態只有 R4b、R4c、R5（確定是前一個交易日）；`lagging` 不得使用「前一收盤」字樣。

## B-7 開放問題

- **Q-B1（PM）**：開盤前（R4a）要標「收盤（P 日）」還是「前一收盤參考」？本文建議前者，因為那是最新一個已完成的收盤。
- **Q-B2（PM、creative、風控）**：`lagging`、`provisional_today`、`date_anomaly` 是 PRD 四種狀態以外的新增狀態，需要字面。不加的話，R6 和 R3′ 會被迫用錯誤的標籤。
- **Q-B3（PM）**：AC-B5a-5 在 observed 模式下無法把「今天的平日休市」標成休市（B-5 限制 1）。請確認可以接受這種讀法。
- **Q-B4（PM、CEO）**：US 持股沒有官方休市日來源（D-9），只能永遠用 observed 並揭露。Phase 1 是否涵蓋 US？
- **Q-B5（風控、PM）**：AC-B5a-6 要求「不可收合」，與 CEO 2026-10-03 裁定 5（C3 基準句收進 `<details>`〔事實：ADR-0014:289〕）的關係是什麼？本文的讀法是：PV-49 揭露是新的常駐揭露，不是 C3，所以不收合。請確認。
- **Q-B6（tech-architect、T1-13 時處理）**：是否修訂 ADR-0009，讓 freshness 也使用官方假日表（B-5 限制 3）。
- **Q-B7（data-engineer、T1-07 加查）**：各日線來源（TWSE、TPEx、FinMind、yfinance、AV）在盤中或收盤後不久，會不會回傳日期為當日、但尚未定案的 bar？各來源的定案時間是什麼？
  - 我在 `app/data/` 找不到任何過濾盤中 bar 的程式（Grep 無結果）。yfinance 以時間戳的 UTC 日期當 bar 日期〔事實：yfinance.py:80-87〕。
  - 〔推論〕若有來源會回傳這種 bar，而它在盤中被寫進快取，過了 cutoff 之後 `judge()` 會因為「最後一根 ≥ 今天」判為 HAS_LATEST，不再重抓〔事實：freshness.py:160-161〕，暫定價就會一直留著。這是資料層的潛在正確性問題，修正位置應該在資料層（ADR-0009 修訂）；R3′ 只是縱深防禦。

## B-8 ADR 建議

建議立 ADR（編號由 coordinator 分配，避開 0026），標題暫定「Stock Desk 估值狀態判定與交易所時段參數」。

- **Context**：ADR-0025 D-12 Phase 1、PV-49、AC-B5a-1～6。
- **Options**：B-1 四個方案。
- **Decision**：B-2～B-6。
- **Consequences**：
  - 好處：標籤由證據驅動，前端零推算，日曆可替換。
  - 壞處：B-5 的三個已知限制；多了兩到三種狀態，要增加字面工作；參數查證之前不能出貨。
- **與既有 ADR 的關係**：
  - 不取代任何 ADR。
  - 引用 ADR-0009 D-2 的 cutoff，但不修改 ADR-0009。
  - 遵守 ADR-0014 D-7(d)、I-10、D-11。
  - 與 ADR-0019 一致：取得時間採 D-4／D-5 的單一基準，不讀 `tail_fetched_at`。
  - 是 ADR-0025 AV-1 的延伸。
