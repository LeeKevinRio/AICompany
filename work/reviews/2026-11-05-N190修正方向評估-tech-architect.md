# N-190 修正方向評估

- 審查者：tech-architect
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-190 修正評估（tech-architect，唯讀；已採用風控 11-04 重裁）

## 一、本次結論

**根因**
- data 層把 layer 0 命中標成 `CACHED_STALE`，這是設計，不是 bug：
  - ADR-0005 已否決第五個 `DataStatus`（:324）；
  - ADR-0009 D-5 用 `is_within_ttl` 二次限定狀態；
  - ADR-0015 C1 否決把快取改標成 `FRESH`。
- 缺陷在 playbook 這個 consumer：
  - engine.py:55-57 把 R6 的前提寫成「cached_stale 代表沒有 live source 回應」。ADR-0009 D-4 讓 TW 也開 layer 0 之後，這個前提就失效了。layer 0 的意思其實是「快取已經有最新交易日，所以沒去問」。
  - `LoadedSeries`（service.py:117-125、:947-949）把 `is_within_ttl` 丟掉了，違反 interface.py:104-107「consumer 必須兩個欄位一起讀」。
- 實測的 (a)、(c) 是一般規則的特例。一般規則是：**某檔在某個交易日，只有「全系統第一個打到 live 的那次載入」會產生可用序列**。

**新發現（讀碼推論，未執行，必須先實測）**
- compose 預設有 scheduler（compose.yaml:31-46）。台北 15:10、16:30、18:30 會用同一條 ladder，替持倉簿裡的每一檔抓 540 天（scheduler.py:155、:283-303）。這個範圍涵蓋 playbook 的 180 天（service.py:83）。
- 推論：只要 playbook 的標的也在持倉簿裡，而且 TWSE 在 15:10 前已公布，之後當天每一次 `/today`（包括第一次）的結算載入和評估載入都會是 `cached_stale`。這幾檔的 S/P 可能**每天都不評估**，不管有沒有到期列。
- 個股頁、訊號頁等其他 consumer 先載入過，結果也一樣。
- 指數 `^TWII` 也一樣：訊號頁、族群卡（scheduler.py:445-460）載入過之後，`/today` 的指數就是 `cached_stale`。後果：
  - M1 不評估、沿用前一狀態；
  - 排程日 R 系列順延並計入次數；
  - 該進防守時沒進，S1 門檻沒有改成 0.93（engine.py:430）。
- **後果：第一包（沿用結算序列）對這些情況完全無效**，因為結算那次載入本身就已經是快取。

**方向**
- 第一包照風控重裁：(i) 沿用結算序列 + N190-I + 用 (甲) 修 (b2)。
- (ii) 改標 `fresh` 或新增 status：**否決**。
- (iii) 重新解讀 R6，也就是 (乙)：放第二包，要風控書面裁示、CEO 書面知悉，並另出 ADR 明文豁免 engine 零 diff。
- 但如果上面的新發現實測成立，主路徑只有第二包修得好。風控把第二包排在第三包之後的前提就要重裁。

## 二、各部門回報（tech-architect）

程式碼行號都以 worktree bf03a9c 為準：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n190/apps/stock-desk/backend/app/`。

### 1. 根因

**`cache_first` 下 layer 0 一律標 `CACHED_STALE`**
- 位置：data/service.py:848-853、:856-884。
- 這是設計。ADR-0005 決策四與 ADR-0009 D-5 明定 layer 0 回 `CACHED_STALE`，新鮮與否交給 `is_within_ttl` 表達。
- `judge()` 判 `HAS_LATEST_SESSION` 時，`current=True`（:852），代表資料已經含最新一個已公布的交易日。所以 data 層有說真話，只是要讀兩個欄位才看得到。
- 有一處文件已經過時：interface.py:36 寫「cached_stale -- all live providers failed」，ADR-0009 之後已不成立。這處屬 data 層，不放第一包。

**engine 只採 `fresh`／`backup` 的原意**
- 風控 R6 原文是「stale/unavailable/demo 不得輸出可執行指令」（`work/reviews/快市排程-風控前置意見.md:12`），本意是不讓**過時**的資料驅動指令。
- 實作把「過時」等同於 `status == cached_stale`。註解（engine.py:55-57）明白排除 TTL 內的快取，理由就是那個已經失效的前提。
- 結論：這是設計前提失效造成的整合缺陷，不是 data 層的 bug，也不是有意的產品取捨。

**觸發條件**
- 一次 `/today` 裡會載入兩次：結算（service.py:1046）和評估（service.py:1579）。
- 第二次載入命中 layer 0，因為第一次剛寫了 fetch log。
- 推廣到一般情況：同一交易日內，任何比 `/today` 評估更早的載入（另一個請求、另一個頁面、scheduler）都會造成同樣的結果。

**受影響的其他路徑**（同一個述詞，讀碼結果）
- `rebalance`（service.py:1272）會變成 insufficient_data；
- 指數 M1 與快市判定（engine.py:263、:322、:1128）。

### 2. 修正方向比較

| 方向 | 影響範圍 | 與 accepted ADR | 測試 | CEO |
|---|---|---|---|---|
| **(i) 評估沿用 `run.loaded`**（第一包） | 只動 `evaluate_today`；個股頁等其他 consumer 不受影響。只修「結算那次就是 first-touch」的情況，也就是實測的 (a)、(c)。**修不到** (b2)、scheduler／其他頁面先載入、指數 | 不衝突。先例是 ADR-0039 Decision 3。engine、`_settle_pending`、`settle()` 都零 diff。順帶關掉 N-189 評估中的路徑 3（同一請求兩次載入結果不同） | 真實 ladder 跑 (a)、(c)、輪替；每檔每次請求只呼叫 ladder 一次 | 不需要（風控已判定不改規則） |
| (ii) layer 0 改標 `fresh`，或新增 status | 全站：所有徽章、估值、警示、回測、前端字面測試（`dataMetaStatusBadge.test.ts`）、e2e 夾具；`Directive.data_status` 會把快取說成即時 | **衝突**：ADR-0005 :59（只能往悲觀方向調）、:324（否決第五個 status）；ADR-0015 C1、C-4；ADR-0003 約束 7 | — | 需要，但 **TA 否決**，不建議送 |
| (iii)／(乙) engine 接受「`cached_stale` ∧ `is_within_ttl=True` ∧ 非 demo」 | `MarketSnapshot`／`IndexSnapshot` 加欄位、`LoadedSeries` 帶上 `is_within_ttl`、改 engine 的 `is_usable`；指令列的 `data_status` 照實保留 `cached_stale`。可以修 (b2)、scheduler、其他頁面先載入、指數，也就是根治 | 違反 N172-C3、C-B11 的 engine 零 diff，要另立 ADR 明文豁免；R6 要風控書面重新解讀 | 加上「scheduler 先暖快取再 `/today`」與指數情境 | 風控說 CEO 書面知悉；TA 建議新 ADR 送 CEO 核可，因為要豁免 accepted ADR 的約束 |
| (vi) 補列：playbook 專用旗標，讓 ladder 跳過 layer 0 | data 層 API 擴充；engine 零 diff，R6 前提字面成立；但每次重新載入都對每檔打一次 TWSE | 修訂 ADR-0009 D-4，而它正是為了消除這種每次點擊的成本才定的 | 同上，另加 live 呼叫次數 | 需要（修訂 accepted ADR） |

**否決清單**
- 在 service 把 snapshot 的 `data_status` 改寫成 `fresh`，用來繞過 engine：否決。指令列會誤述資料狀態。
- 用 runtime 旗標切換 R6：否決。

### 3. 第二次請求的 `cached_stale`

**與 ADR-0035 的關係**
- ADR-0035 二-3 第 4 點設計 A 句時，把「第二次評估資料不可用」當作例外。在 cache_first 下，同一日的重新載入**幾乎一定**是 `cached_stale`。所以 A 句和 DATA_GAP 會變成重新載入的常態畫面。
- ADR-0035 否決 (d1) 的理由是「停損時效不退步」：第一次缺資料、補到資料後整天不再評估，就是退步。現在的情況是：資料經由別的 consumer 補回來，`/today` 卻仍判 `cached_stale`、不評估，這正是 (d1) 那種退步。
- 第一包修不到這一點，只有第二包可以。

**現行揭露是否為真**

| 情境 | 判定 |
|---|---|
| (a)、(c) 首次請求 | 「無法評估」的核心事實為真；「依鐵律⑤」的歸因誤導。第一包修好後這兩種情況就不會再出現 |
| (b2) 稍早已評估過 | 「今日無法依規則評估」**不實**，第一包用 (甲) 修 |
| scheduler 或其他頁面先載入 | 核心事實為真，歸因誤導，**而且第一包不會讓它消失**。風控「現在不改字面，因為第一包會從根本修掉」的前提在這個情境不成立，要風控重判 |
| A 句 | 字面為真，但「稍早這檔資料可用時」暗示本次資料不可用，其實兩次是同一批 bar，略有誤導，交風控 |
| `INDEX_DATA_GAP_NOTE` 在重新載入時 | 「M1 今日未評估」與 (b2) 同類不實。已有結構化記號 `fast_market_measured_on`（store.py:909-928），只在實際量測時寫入。建議風控決定是否併入第一包的 (甲) |

**(甲)／(乙) 的選擇：第一包採 (甲)，(乙) 放第二包。**
- (甲) 一定要有一個持久化的結構化記號。現在沒有任何資料能證明「稍早沒有產生指令列、但有評估過」。
- 設計：新增 `(symbol, execution_date, data_date)` 的「S/P 已用可用資料評估」紀錄，在 `commit_evaluation` 的同一把鎖、同一個 transaction 內寫入；同一次鎖內也讀出「本次寫入前就已存在」的集合，經 `EvaluationCommit` 加法欄位帶出。
- 這是 `GET /today` 新增的寫入。ADR-0039 的限制寫有「GET /today 不新增寫入」，雖然只約束 ADR-0039 自己的範圍，仍要 TA 出 ADR-0035 補充明文授權，並請風控確認。

### 4. 第一包範圍、組句位置與合併順序

**第一包範圍**
1. 評估沿用 `run.loaded`：`run.loaded` 裡有的 symbol 一律沿用，不論狀態；沒有的才另外載入。
   - 不加「只沿用成功的」條件，理由：載入失敗後，第二次載入落在 R-8 冷卻期內，不會再問 live（data/service.py:705-712、:825-836），重載拿不到新東西。一律沿用還能保證結算與評估看到同一份序列。
2. N190-I。
3. (甲)：記號 + 抑制 (b2) 的不實句 + creative-lead 擬的變體句（風控定稿）。

**N190-I 可行性：可以。**
- `evaluate_today` 回傳前，`settlement`（:1573）和 `commit.logged`（:1636、:1666）都在手上。
- 但它**不能**放進 `_settle_pending`：那時還沒有 logged，而且 `POST /settle` 不得渲染。
- 組句位置：在 `commit` 之後、`model_copy` 之前，用一個純函式改寫 `settlement`。
  - 被選中那一列的字串變成 `reason + N190-I`；
  - `settlement.warnings` 裡同一索引的鏡像項目同步替換。根據 service.py:1109，前 `len(unsettled)` 項就是各列的 reason。
  - S/P 列不會有 N1（N1 只給 EMERGENCY），所以不會有順序衝突。

**與 N-168 的合併順序**（依 coordinator：已 push 的分支不 rebase）
- 第一包從最新 product 開獨立分支，不含 N-168 的 commit，也不併入 N-168 的 PR。
- 誰先就緒誰先合。**後合的一方 merge 最新 product**，跑完整 CI 與 seam golden，由 qa-reviewer 審 merge commit 裡的衝突解法。
- 衝突熱點：`evaluate_today` 的回傳區塊、`same_day_warnings`、`wording.py`、`tests/golden/seam/approved/`、settlement warnings。N-168 S3 定了 SUMMARY → W-B3 → N2 的順序；N190-I 只改各列 reason 及其鏡像，不插入、不重排，兩者互不干擾。

**整體時序**
- 第一包 → N-177（S2 同列揭露最遲緊接其後）→ 第三包（N-188 + N-189(D1/D2) + W-B2LS 回審，要等 N-168 合進 product）→ 第二包（與第三包同時或之後）。
- 「N-190 與 N-188／N-189(D1) 同包」：規模大（要動 store 的在途述詞、`InFlightRead` 切面、`_lines` 的 R-3、前端同列欄位、三句以上字面），而且會被 N-168 卡住。風控已改成分包，我同意。
- 例外：若新發現實測成立，第二包解決的是主路徑，風控要重裁第二包與第三包的先後。
- N-177：修法可能要動 `settle()`，牴觸 N172-C8，另案評估。

### 5. US ladder
- 機制與市場無關。在 US policy 下（冷卻 24 小時、cutoff 18:00）一樣成立，CHECKED_RECENTLY 的窗口還更長。
- 但 playbook 目前只用 TW（service.py:86 `PLAYBOOK_MARKET = "TW"`），指數 `^TWII` 也走 TW policy，所以**目前不適用**。
- 建議加一條守門測試釘住 `PLAYBOOK_MARKET == "TW"`；一旦改了，就要重開 US 的評估。

### 6. 對實作的約束（qa-reviewer 可逐條檢查，第一包）

- **N190-C1**：`engine.py`、`app/data/**`、`settle()`、`_settle_pending` 零 diff。
- **N190-C2**：`evaluate_today` 對每一檔最多呼叫市場 ladder 一次。`run.loaded` 裡的 symbol 不得再載入（用呼叫次數測試釘住）。
- **N190-C3**：指令列的 `data_status`／`source` 照 ladder 實際回傳的值，不得改標。不得新增 `DataStatus`。不得用旗標切換。
- **N190-C4**：N190-I 只在 `evaluate_today` 組，`POST /settle` 與 `settle_pending` 的回應逐位元不變。組句只讀同一回應的 `settlement.unsettled` 與 `commit.logged`，不得另外讀 store、不得在途讀取、不得動 `_lines`。
- **N190-C5**：觸發條件全部用結構化欄位判斷，不得比對字串：
  - 舊列：`action='sell'`、rule_id 屬於只定義一次的 S/P 常數（EMERGENCY 除外，`S3` 是否會產生賣出列由 dev-lead 查證）、reason 起頭是該列的 `SETTLEMENT_NO_OPEN_PRICE` 渲染結果；
  - 較晚列：`execution_date` 比舊列晚、`action='sell'`，且同一批（任一方是 S2 時改看同 symbol）。
- **N190-C6**：字面只放 `wording.py`，逐字照風控定稿。股數照抄原始整數。項目依 (`execution_date`, `batch_no`) 遞增排列，以「、」連接。要有禁用詞斷言。
- **N190-C7**：`settlement.warnings` 的鏡像項目與該列 reason 必須相等（斷言）。不得插入或重排 warnings。
- **N190-C8**：(甲) 的記號只在 `commit_evaluation` 的鎖內寫入。寫入條件是 engine.py:1197 資料缺漏分支的補集，用同一個 `is_usable`，而且該檔有 batch。「稍早已評估」只認本次寫入前就存在、`data_date` 相同的紀錄。
- **N190-C9**：(b2) 的抑制在 `same_day_warnings` 進行，用該檔該狀態的完整模板渲染結果整句移除。稍早有指令列時 A 句照常出現；稍早沒有時渲染定稿的變體句。不得讓一檔什麼都不顯示。稍早從未用可用資料評估過時，原句保留。
- **N190-C10**：seam golden 的差異依 `approved/<owner>.json` 逐條登記，不得重錄。
- **N190-C11**（BLOCKING 測試）：全部用真實 ladder（`equity_service`、`index_service`、tmp `PriceBarCache`、固定時鐘），涵蓋：
  - (a)、(b2)、(c) 連續 5 日，以及輪替現象；
  - backups（primary 失敗、backup 回應 → 沿用 `BACKUP`）；
  - 15:00 前的請求；
  - 「scheduler 式 540 天預熱後再 `/today`」：用明確命名的測試釘住第一包**不修**的現況，第二包時翻轉；
  - 指數走真實 ladder 時重新載入的行為；
  - `PLAYBOOK_MARKET == "TW"` 守門。

## 三、驗證

- 全部是讀碼判定，我沒有執行任何東西。qa 的實測只涵蓋 (a)、(b2)、(c)，指數用的是 fake。
- 讀過的程式碼：
  - data/service.py :170-509、:650-1043
  - data/freshness.py 全文
  - data/interface.py :30-130
  - data/cache.py :233-341
  - playbook/engine.py :40-111、:1185-1214
  - playbook/service.py :100-199、:355-629、:930-1232、:1240-1290、:1540-1691
  - playbook/store.py :60-149、:785-815、:895-934
  - playbook/wording.py :245-379
  - services/market.py :147-218
  - services/index.py :300-409
  - api/deps.py :85-344
  - scheduler.py :1-160、:283-462
  - compose.yaml（grep）
- 讀過的文件與測試：
  - ADR-0005、0009、0015、0034、0035、0039 相關段落（grep 加上部分段落全文）
  - 測試腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/test_n190.py`
  - qa 實測、TA N-189 評估、風控兩份裁示、追蹤清單 :262-355
- 未查證：
  - 正式環境 API 與 scheduler 是否用同一個 DB 檔；
  - playbook 的標的與持倉簿是否重疊；
  - TWSE 的實際公布時間；
  - alerts tick 的載入範圍；
  - `rules_fully_evaluated` 有哪些 consumer。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 四、下一步

1. **qa-automation（最急）**：用真實 ladder 實測以下兩種情況：
   - 先用 540 天範圍在台北 15:10 載入（等同 `refresh_market_data`），再在 16:00 打 `/today`；
   - 指數換成真實 `index_service`，先由另一個 consumer 載入，再打 `/today`（排程日看 R 順延與防守翻轉）。
2. **risk-compliance-officer**：
   - 實測成立的話，重裁第二包與第三包的先後；
   - 重判 scheduler 情境下「依鐵律⑤」的歸因要不要先改字面；
   - 決定 `INDEX_DATA_GAP_NOTE` 是否併入 (甲)；
   - 確認 N190-I 的「較晚 sell 列」是否包含 EMERGENCY；
   - 僅有 B 句（順延／跳過紀錄）時，變體句要怎麼處理。
3. **coordinator**：
   - 在送 CEO 的通知裡補一句：實際範圍可能比「前一天有指令的標的」更廣，正在實測；
   - 請 CEO 或 PM 提供事實：playbook 的標的與持倉簿是否重疊。
4. **tech-architect**：出 ADR-0035 補充（第一包：沿用序列、N190-I 組句點、(甲) 記號的寫入授權）。第二包另立 ADR，等風控裁示 (乙)。
5. **creative-lead**：擬 (甲) 的變體句送風控。
6. **dev-lead**：補充落檔後依 N190-C1～C11 開工，分支從最新 product 開，不併入 N-168。
7. **CEO**：第一包不需要裁決。第二包若採 (乙) 或 (vi)，因為要豁免或修訂 accepted ADR，要送 CEO。
