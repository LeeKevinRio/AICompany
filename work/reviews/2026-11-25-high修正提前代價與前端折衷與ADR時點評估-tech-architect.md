# high 修正提前到登記前合併的代價、只改前端的折衷、ADR 時點

- 審查者：tech-architect
- 日期：2026-11-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：high 修正提前到登記前合併的代價、只改前端的折衷、公司行動與還原口徑 ADR 的時點

全程唯讀，只用了 Read、Glob、Grep，搜尋都列了明確路徑。沒有讀 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，沒有看 `.claude/worktrees/`，也沒有寫檔或執行任何指令。主工作樹在 `product/stock-desk`，下文的行號都以它為準。CEO 可見字面一律標「字面待風控定稿」。

---

## 本次結論

1. **「登記之前」實際上只能是「CG-2 合併 commit M 之前」。**
   - M 到登記完成這段，任何 `app/` 變動都會讓 R-1 STOP，而且落在 #156 期間。
   - 所以 high 修正想在登記前合併，只有兩個時點：
     - 甲：在 CEO 跑驗收（G_acc）之前；
     - 乙：在 G_acc 之後、M 之前。
   - 兩個時點都要讓 CG-2 重釘 `app/` tree id，RC-511 也會被打破，M-9 要重開，退役鏈和接線鏈都要重新同步（第 1 點表格）。
   - 乙另外會讓補充六 6(d) 的「harness 通過」失效，CEO 要在新 head 重跑。
   - 我們無法知道會落在甲還是乙。CEO 11-16 已被請求執行一次（追蹤清單:567），到今天沒有回貼，所以團隊不知道他跑過沒有。
2. **新發現 A，跟提前合併無關，現在就要處理。** 補充六 6(d) 的允許差異清單，字面上不含前端原始碼，也不含 main 同步帶進來的非文件檔（例如 `scripts/validate_agents.py`）。
   - T-3（`6cd7d25`，11-22）是前端變更。CEO 的 G_acc 如果早於它，依字面這次驗收已經失效。
   - 之後的前端折衷、以及 product 要 `merge origin/main`（追蹤清單:799 第 (4) 點），也都受同一條字面拘束。
   - 這需要一則讀法補充，送風控（第 3 節草案）。
3. **新發現 B，限制 H1 的實作位置。** `code_digest` 範圍會 import 三個範圍外的模組：`app/data/interface.py`、`app/data/freshness.py`、`app/advice/banned_phrases.py`。
   - 出處：`outlook/inputs.py:53-55`、`forecast/recorder.py:81-83`、`forecast/definitions.py:63`。
   - 改這三檔，harness 的行為會變，但 `code_digest` 不會變。不論在什麼時點，H1 偵測都不得寫在 `PriceBar` 或 freshness 裡。
4. **只改前端的折衷都做得到，限制如下（第 2 點）：**
   - RC-650：前端目前拿不到任何「檢查有沒有跑」的訊號。所以「拿不到就不顯示放心句」在 α2 之前，等於永遠不顯示。唯一的代理訊號是同頁的持倉摘要查詢失敗，涵蓋範圍很窄。
   - H1：前端拿到的日線視窗和後端一樣是 540 天。關鍵價位可以直接拒算；決策卡的「動作」是後端算的，前端只能加註或隱藏。推播、排程台、回測都不受影響。
   - RC-695：前端可以比照 T-3 收起技術分析區。後端讀碼結果：RSI、量能 z-score 遇到壞 bar **都不拒算**，`/api/signals` 也沒有任何 usable 檢查。
5. **ADR 時點（第 3 點）：** H1 與 H4/M4 建議各立一份 ADR（代稱 ADR-δ、ADR-ε）。它們只是文件，現在就可以起草、落檔，不動任何釘點。實作要等各自的 ADR 落檔之後。
6. **CEO 取捨：要不要讓後端 `app/` 修正提前到登記前，需要 CEO 決定。** 理由有二：會延後登記（也就延後預測紀錄帳開始累積準確度證據），而且可能要 CEO 重跑驗收或暫緩執行。只做前端折衷不需要 CEO 決定。四個選項的對稱事實在第 4 點，交風控擬題目。

---

## 各部門回報（tech-architect）

### 第 1 點：high 修正在登記前合併的代價

**釘點與流程的事實**
- 流程順序：
  1. CEO 跑驗收，產生 G_acc；
  2. CG-2 合併，產生 M；
  3. RC-507 (1)～(6) 核對；
  4. 預檢通知；
  5. #156（預檢到登記完成）；
  6. 登記紀錄 commit；
  7. 退役 PR 合併；
  8. 接線 PR。
- RC-507 (2)：`M:apps/stock-desk/backend/app` 必須等於 `d631a75a4aba2ace76c44e8647d1bd11180662d5`。
  - 這個值是 CG-2 head `cc9e302` 的 app tree。
  - product 從那時到現在都沒改過 `app/`（11-16 之後只合併了文件、前端與測試，追蹤清單:726～798）。
- RC-511：CG-2 分支之後只能新增 `work/reviews/` 的 `A`。RC-516 寫明「M-9 不重開、RC-511 照舊」。
- 補充六 6(d)（ADR-0030:663-667）：從 `git_head` 到 CG-2 合併時的 head，只允許列舉的那幾種差異，其餘差異都會讓通過失效，「須在新 head 重跑」。
- 補充七附記三 R-1（ADR-0030:913-923）：預檢與登記時，`HEAD:…/app` 的 tree id 要等於常數。coordinator 人工核對「合併 commit 與 `git_head` 之間 `app/` 沒有 diff」。
- CG-2 的 `test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout` 會隨 M 進入 product，到退役 PR 才刪除。這段期間 product 上任何 `app/` 變動都會讓 CI 變紅（11-19 dev-lead 交件第 79 行、追蹤清單:732）。
- 驗收操作說明第 1 步是先執行 `dev-up.bat` 拉到最新版（`work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md:17`）。所以 CEO 如果還沒跑，之後再跑，就會含進已合併的修正。

**逐項代價**（甲：G_acc 之前合併；乙：G_acc 之後、M 之前合併。工時是推論，以 11-21 重釘那一輪為參照：dev-lead、qa、風控、coordinator 往返一天）

| 項目 | 甲 | 乙 | 要重做的審查與工作 | 工時 |
|---|---|---|---|---|
| RC-507 (2) `d631a75a…` | 失效 | 失效 | CG-2 分支 merge product 之後，重釘 `scripts/cg2_register.py` 的 tree 常數與 `tests/test_cg2_register_values.py`；RC-507 (2) 的字面值由風控改發 | dev-lead 小；風控 小 |
| RC-511 | 違反 | 違反 | merge 會帶進 `app/` 與 scripts 的差異，需要風控書面撤銷或改寫 RC-511，並推翻 RC-516「M-9 不重開」 | 風控 小（是一道閘門） |
| M-9 | 重開 | 重開 | qa 重做 M-9 補充最終審查；風控重做 M-2、M-3、M-6 與 RC-495 核對；`review_refs` 加兩條新固定檔名，所以要再一個 commit（這段期間 `test_the_review_refs_all_exist_at_head` 紅燈，屬原設計）；coordinator 在新 M 上重跑 RC-507 (1)～(6) | 中（每一輪） |
| 補充六 6(d)，以及 CEO 要不要重跑 | 不受影響 | 通過失效，CEO 要在新 head 重跑 | 乙：要一則重跑通知（字面待風控定稿）；回貼依 6(a)～(c) 重新判讀（devops-sre 或 dev-lead 執行，qa 判讀）；CEO 互動一次，經過時間無法預估。甲乙之分在回貼前觀測不到；想確定是甲，就得先問 CEO 跑過沒有，或請他暫緩執行（都是 CEO 互動，字面待風控定稿） | 團隊 小；CEO 端 大（時間不可控） |
| CG-2 要不要重釘 | 要 | 要 | 同第一列。CG-2 head 的 `code_digest` `fc94ada3…` 在約束成立時預期不變，要重算核對 | 小 |
| 補充七附記三 R-1 | 常數重釘後成立 | 同左 | 規則本身不改。**限制**：所有登記前要合併的修正，都要在重釘開始之前進 product；之後再多一支，以上各列整輪重來 | 0（但限制排程） |
| 退役鏈分支 1（`e51ac00`） | 要重新同步 | 同左 | 同步重釘後的 CG-2 head，會在 `cg2_register.py` 與 cg2 測試上再遇到 modify/delete 衝突，同 11-21。依 11-21 裁示第 (1) 點保留刪除即可，不需新補充；tree id `185c424b…` 作廢重算；product `code_digest` `1599c21c…` 預期不變，要重算；qa 重審 S-19a、S-22 | dev-lead 小；qa 中 |
| 退役鏈分支 2（`54cd836`） | 不受影響 | F10 的 `<G_acc>` 那一格要用新的 G_acc | 填值與 qa 核對 | 小 |
| 接線鏈（`feat/nm5-wiring` `526201c`、`test/f2-short-window-carryover` `05534b6`） | 要重新同步 | 同左 | 同步新的 CG-2 head；`code_digest` `32725eb8…` 原本就是暫定值，最終 head 本來就要重算，沒有額外成本；tree `4dc141b2…` 作廢（沒有常數釘它）。α2 與接線都會改 `app/scheduler.py`，有衝突風險；這個風險在登記後才合併時也存在，提前只是提早處理。W-7 零差異證據要重產 | 小～中 |
| 修正本身的審查 | 不論時點都要做，但甲、乙會讓它排上登記的關鍵路徑 | 同左 | α1：中（ADR-α 未落檔、三處讀法風控未回）。α2：大（新表、API、E 四種變體、推播字面、art-lead、qa-e2e 375／1280）。PR-3：大（讀碼基準還沒重定；RC-673 行為變更通知要在合併前送達並確認收到，又是一次 CEO 互動；RC-674 D-a3 逐字審）。H1 偵測：中（還沒有規格，要先有 ADR-δ，門檻要 data-engineer 查證）。H2：中（新 reason code 與句子要風控；golden 要重產，和 RC-556 同一批 golden 檔重疊；Kelly 端未知 code 回 `None`，`kelly_wording.py:590-612`，已存成 `adjusted` 的舊列不會被回溯更正，屬推論） | 合計數週（推論，沒有估算基礎） |
| 登記與預測紀錄帳的起點 | 延後 | 延後 | 延後的長度等於上面各列加總。帳的閘門延後多久，準確度證據就晚多久開始累積 | — |

- 只提前 RC-650（α1 + α2）時：重釘、M-9、退役與接線重新同步這幾列照樣要走一輪；只有「修正本身」那一列縮成 α1 中、α2 大。
- 照現行順序（登記、退役之後才合併）：以上各列都是 0。代價是 high 問題會留在畫面上，時間等於「CEO 回貼 → CG-2 → 登記 → 退役」，沒有上限可以估。

**任何登記前合併的後端修正都要遵守的約束（qa 可逐條檢查）**
1. `git diff <base> HEAD` 對下列路徑必須為空：
   - `app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py`；
   - 加上遞移 import 集合：`app/data/interface.py`、`app/data/freshness.py`、`app/advice/banned_phrases.py`、`app/__init__.py`、`app/data/__init__.py`、`app/advice/__init__.py`。
2. `uv.lock`、harness 三檔、`backend/scripts/pipeline_acceptance_real.py`、`pipeline-acceptance.bat`、兩份凍結文件、所有 `.gitattributes` 零差異。
3. 每支修正都是獨立 PR，全部在 CG-2 重釘開始之前合併。重釘之後到登記完成，product 的 `app/` 零變動。
4. 每支附合併前後用同一支 `canonical.code_digest` 算出的值，兩者相等。
5. 退役鏈遇到 modify/delete 衝突時，依 11-21 裁示第 (1) 點保留刪除；如果衝突出現在被刪除檔以外，停下來升級 tech-architect。

### 第 2 點：只改前端的折衷

共同限制：
- 前端合併不動 RC-507 與 R-1 的釘點（兩者只看 backend `app/`）。
- 但受上面「新發現 A」的 6(d) 讀法拘束。讀法定案之前，前端折衷要合併在 G_acc 之前才確定不影響驗收；而 G_acc 觀測不到。
- 不在 #156 期間合併。
- 新字面都要經 creative-lead 起草，字面待風控定稿；每項都要 qa 加 qa-e2e（375／1280）。

**RC-650：首頁狀態 B**
- 前端現在拿得到的訊號，以及各自的意思：
  - `GET /api/alerts`：規則的數量、啟用與否、建立和修改時間。沒有檢查紀錄。
  - `GET /api/alerts/events`：`items` 加 `as_of`。`as_of` 是 API 回應的時間（`api/alerts.py:186-187`），不是檢查時間。
  - `GET /api/settings`：`alerts.enabled`、`evaluation_interval_minutes`、`cooldown_minutes`、`notify_webhooks`（`types.ts:1306-1311`）。
  - `usePortfolioSummary`（首頁 `page.tsx:15` 已經在查）：它和警示快照的帳本段呼叫同一個 `build_summary(store, valuator)`（`api/portfolio.py:134`、`alerts/snapshot.py:130`）。持倉無法讀取時，兩邊同樣失敗（dev-lead 11-22 實測帳本 500；這次沒有重驗摘要端點）。
  - `/health`：只代表 backend API 活著，不代表排程（`main.py:90-101`）。
  - `POST /api/alerts/evaluate`：有副作用，會把觸發的事件寫進 DB（`engine.py:472`），也受冷卻影響，不能拿來當被動探針。
  - 結論：**沒有任何訊號代表「排程輪跑過了」。**
- 折衷 F1（不看訊號）：狀態 B 拿掉放心句，連「查詢時間」一起拿掉或改標。
  - 涵蓋所有成因。順帶處理 RC-654 的「查詢時間不是檢查時間」。
  - 限制：
    - 正常時也看不到放心句；
    - 沒辦法告訴 CEO「檢查失敗了」（那是狀態 E，要 α2）；
    - 推播不受影響；
    - α2 落地時字面要再換一次，風控要審兩輪。
- 折衷 F2（代理訊號）：摘要查詢 `isError` 時，不顯示 B，改顯示一行中性句。
  - 限制：
    - 只涵蓋同時讓摘要失敗的成因（持倉無法讀取）。匯率、Kelly、`evaluate_limits`、行情段失敗、排程根本沒跑，都涵蓋不到；
    - 查詢時點和排程輪時點不同；
    - 狀態列要多讀一個 query（共用 cache，不會多發請求）。
- F1、F2 可以一起做。工時各為中。

**H1：前端偵測單日跳空**
- 事實：
  - `/api/bars` 和後端建議卡用同一個 540 天視窗（`api/signals.py:45` `DEFAULT_LOOKBACK_DAYS = OBSERVATION_LOOKBACK_DAYS`；`PriceChart.tsx:34`）。所以前端看得到後端回撤用的同一段日線。
  - 前端知道市場別。前端拿不到除權息日（這次沒逐一查是否有任何前端查詢帶除權息日，**未查證**），也不知道標的適用哪種漲跌幅制度。
- 關鍵價位：可以拒算。`computeKeyLevels` 是純前端計算（`keyLevels.ts:101-106`），可以比照 T-3 加跳空條件後回 null。
  - 限制：沿用現有的無資料句會造成歸因不準（RC-598 第 2 點、RC-693 同型），要另立原因代號和新句子（字面待風控定稿）。
- 決策卡：
  - 停損格來自 `computeKeyLevels`（`DecisionCard.tsx:343`），會跟著拒算。
  - 動作與命中規則（例如 `deep_drawdown_stop`）是後端算的。前端只能加註，或者隱藏回撤類規則的動作（`OperationSummaryPanel.tsx:32` 已經有 `DRAWDOWN_RULE_IDS`）。
  - 隱藏會讓畫面和後端輸出、推播不一致；加註不會。畫面上已經有一句常駐的通用揭露（`TechnicalIndicatorsPanel.tsx:540`「分割、減資、反分割等公司行動未處理」），這次新增的是「偵測到」才出現的條件式加註。
- 共同限制：
  - 警示推播、排程台 S1／P2 指令、回測、事件研究、Kelly 都不受影響；
  - 只適用台股；
  - 誤判方向是多拒算。依知識、**未查證**：沒有漲跌幅限制的標的（國外成分 ETF、新上市頭幾天），以及除權日的原始價收盤對收盤，都可能超過門檻；
  - 門檻要和既有兩個定義對齊或說明差異：ADR-0016 F7（台股 |pct| 嚴格大於 11）、`sectors/definition.py:69-70`（0.10 + 0.01）。quant 建議的約 10.5% 和兩者都不同。
- 工時：中。

**RC-695：技術分析區**
- 前端：可行。技術分析區用的資料有兩個來源：
  - 圖表與一句結論吃 `/api/bars`（`page.tsx:384-404`）；
  - 指標列與指標面板吃 `/api/signals`。
  - 可以對 `bars.data.bars` 套 T-3 同一條判斷（任一根非有限或 ≤ 0），條件成立時把圖、一句結論、指標列、指標面板整組收起，改用新句子（字面待風控定稿）。H1 的跳空條件可以共用同一個判斷函式。
  - 限制：
    - 後端照樣回 `status="ok"` 的數值；
    - 建議卡的命中規則照樣用這些數值，因為建議卡只檢查最新一根（quant M1）；
    - 前端只能「不顯示」，不能更正。
  - 工時：中。
- 後端讀碼（RC-695 要求查的部分）：
  - **RSI**（`technical.py:136-186`）：只檢查根數（`len(bars) < period + 1`），不檢查值。
    - close 為 0 或負數時照算，`status="ok"`，數值失真。
    - close 為 NaN 時，`np.where(delta > 0, …)` 會把 NaN 變化量當成 0，照樣算出值（推論，未實測）。
    - inf 的情形沒有實測。
  - **量能 z-score**（`technical.py:403-451`）：只用 volume。壞的 close 不影響它。
    - volume 為 NaN 時，含這根的 20 根視窗都變 NaN；`last_defined`（`frame.py:97-102`）會回傳更早一天的值，而且 `status="ok"`。也就是說，畫面可能把舊值當成今天的值（推論，未實測）。
    - PriceBar 是否接受非有限的 volume，**未查證**。
  - `bars_to_frame`（`frame.py:32-59`）不過濾任何值；`/api/signals`（`api/signals.py:96-124`）只看「有沒有 bars」。
  - 結論：**兩者都不會拒算。**

### 第 3 點：H1、H4、M4 的 ADR 與時點

**評估摘要**：立兩份 ADR，不和 ADR-α、ADR-β 合併。兩份都只是文件，起草與落檔不動 `app/`。6(d) 允許文件差異，R-1 只看 `app/` 與兩份凍結文件，所以現在就可以排；只要避開 #156 期間合併。

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) 一份 ADR 涵蓋公司行動和還原口徑 | 只審一次 | H1 偵測是過渡措施，可以很快定；口徑選擇牽涉 quant 定義、規則語意與風控，會拖住 H1 | 中 |
| **(ii) ADR-δ（公司行動）與 ADR-ε（規則輸入口徑）分開（建議）** | H1 偵測可以先定；ADR-ε 可以從容處理 H3、M4 的一致性 | 兩份要互相引用 | 低 |
| (iii) 不立 ADR，任務單直接做 | 快 | 跨 signals、advice、playbook、backtest、前端 keyLevels 五個模組，又牽動 accepted 的 ADR-0016、ADR-0025 的前提；違反「跨模組邊界要有 ADR」的慣例 | 高，否決 |

**ADR-δ（公司行動偵測與排除，草案要點）**
- Context：
  - ADR-0025（accepted）D-9 與 D-12 把「公司行動偵測」列為 Phase 1 交付（ADR-0025:459、:497），但沒有實作（quant H1）；
  - 已有三個不同的跳空定義：ADR-0016 F7、sectors 保險、dirdef 的 `SPLIT_SUSPECT_ABS_RETURN`（在 `code_digest` 範圍內，不得 import）。
- Decision 要回答：
  - 單一標的門檻與它的來源，要說明和 F7、sectors 為什麼一致或不一致；
  - 只適用哪些市場與商品；
  - 每個消費端要拒算還是明示排除，包括建議卡規則、警示、排程台、回測、事件研究、前端關鍵價位；
  - 拒算後的欄位依 ADR-0021 不得被當成 quiet；
  - 實作位置禁止 `data/interface.py` 與 `data/freshness.py`；
  - 正式來源由 data-engineer 依 `data-source-integration` 查證（ADR-0025 D-9 候選：TWSE／TPEx 公告，未查證）。
- 時點：先於任何 H1 偵測 PR（不論前端或後端）。

**ADR-ε（規則輸入用原始價還是含息價，草案要點）**
- Context：
  - `dividends/adjust.py:11-17` 規定風險上限用原始價，ADR-0016 引用了這條邊界；
  - ADR-0025:390 的預測結果用還原價；
  - 頁面條件用原始價，回測與事件研究預設用還原價（M4）；
  - H3 錨點不一致。
- Decision 要逐一指定每個消費端的口徑：
  - 估值與風險上限：維持原始價；
  - 規則的回撤、MA60、位階、RSI；
  - 排程台停損與移動停利，以及成本要不要扣除已領股利；
  - 回測與事件研究，要和頁面做 parity test。
  - 明訂**不及於 `code_digest` 範圍**。
- 前置條件：
  - quant 寫「含息報酬路徑」的定義；
  - data-engineer 確認除權息資料從哪一天開始有覆蓋（同 H2）；
  - product-manager 確認範圍；
  - 風控判定規則語意變更算不算建議內容變更（風控有否決權）。
  - 規則集要升版（ADR-0004）。
- 時點：先於任何 H4、M4、H3 (a) 的實作；H3 (b)（只揭露）可以先做，但不得和 ADR-ε 的方向矛盾。

**範圍外提醒**：quant 的 L4、L5 寫「正式登記前」處理。
- L4 改 `app/outlook`，在 `code_digest` 範圍內。登記前做的話，驗收要重跑、CG-2 要重釘，已登記的雜湊也可能受影響。
- L5 要改事先宣告。那份文件已凍結，受 RC-507 (3) 與 M-2 拘束。
- 兩者都不在本次評估內，要另案處理。

**新發現 A 的補充草案（代稱「補充六附記四」，交 tech-writer；送風控之前不落檔）**
- Context：6(d) 的允許清單沒有涵蓋前端原始碼，也沒有涵蓋 main 同步帶進來的非文件檔。T-3（`6cd7d25`）已經在 11-22 合併；product 也還沒 merge `e1349aa`。
- 選項：
  - (r1) 照字面：上述差異會讓通過失效。如果回貼的 `git_head` 早於 `6cd7d25`，CEO 要重跑。
  - (r2) 窄幅寬於字面：`apps/stock-desk/frontend/**`，以及 main 同步帶進來、不在 `apps/stock-desk/backend/` 底下的檔，列為允許差異。
    - 條件：backend 零差異；harness 與一鍵檔的 import 圖觸及不到這些檔（以測試或 `git diff --name-only` 證明）；
    - CEO 可推翻。
- 我傾向 (r2)，理由是 harness 與一鍵檔都不執行前端。但這是放寬，送風控判定；判定之前照 (r1) 處理。

### 第 4 點：需要 CEO 做的取捨

**判斷**：
- 後端 `app/` 修正要不要提前到登記前，需要 CEO 決定。這會改變 CEO #154～#156 之後的登記時程，也可能要 CEO 重跑或暫緩驗收，而且 high 問題留在畫面上的時間要由 CEO 承擔。
- 只做前端折衷，以及補充六附記四的讀法，屬團隊與風控的範圍，不需要 CEO 決定。

**選項的事實（對稱列出，題目字面交風控擬，字面待風控定稿）**

| | 選項 1：維持現序，先做前端折衷 | 選項 2：登記前只合併 α1、α2（RC-650） | 選項 3：登記前合併五項 high | 選項 4：先不決定 |
|---|---|---|---|---|
| 登記時程 | 不變，取決於 CEO 回貼 | 延後 α1 + α2 的開發審查時間，再加一輪重釘（推論：一到數週） | 延後五項加一輪重釘的時間（推論：數週） | 等同選項 1 |
| 預測紀錄帳開始累積證據 | 不變 | 延後同上 | 延後同上 | 等同選項 1 |
| CEO 要做的事 | 不必另做 | 可能要重跑驗收或暫緩執行（取決於他跑過沒有，回貼前不知道） | 同選項 2，另加 PR-3 的行為變更通知要確認收到（RC-673） | 不必另做 |
| high 留在畫面上的時間 | 到「回貼 → CG-2 → 登記 → 退役」之後，沒有上限可以估；前端折衷只減輕畫面上的部分，推播與排程台不受影響 | RC-650 在登記前修正；其餘四項同選項 1 | 五項都在登記前修正 | 同選項 1 |
| 團隊重工 | 0 | 重釘一輪：RC-511、M-9、退役與接線重新同步（中） | 同選項 2；五項之中任何一項晚於重釘，就要再來一輪 | 0 |

另外有一個團隊內的結構性選項，不是 CEO 題目，但會影響選項 2、3 的成本：把 R-1 與 6(d) 的釘點從「整個 `app/` tree」收窄到「`code_digest` 範圍加遞移 import 集合」。
- 好處：之後範圍外的修正不必再重釘。
- 代價：一份 ADR 補充（性質是放寬，要風控審）、改 `cg2_register.py`（一樣會重開 M-9），而且需要測試證明 import 圖是完整的。

---

## 驗證

**讀過**
- `work/reviews/2026-11-25-預測正確性風險盤點-quant.md` 全文。
- 我的 11-22 三份檔全文：ADR-α 那份、RC-556 時點那份、PR-2／PR-3 那份。
- 追蹤清單第 560～568、725～801 行。
- ADR-0030 第 607～699、865～977 行，加上檔頭的 Grep。
- RC-690～RC-695 第 18～73 行。
- 驗收操作說明的 Grep 段落；11-19 接線交件第 30～104 行；CEO #154～#156 決策第 32～51 行；ADR-0025 第 380～399、450～499 行；ADR-0016 與 ADR-0018 的 Grep 段落。
- 程式：
  - `AlertStatusStrip.tsx` 全檔；
  - `api/alerts.py` 第 1～30、199～266 行；
  - `alerts/engine.py` 第 393～517 行；
  - `alerts/snapshot.py` 第 95～164 行；
  - `signals/technical.py` 第 1～200、403～452 行；
  - `signals/frame.py` 第 32～102 行；
  - `api/signals.py` 第 85～124 行；
  - `keyLevels.ts` 第 85～154 行；
  - `TechnicalIndicatorsPanel.tsx` 第 530～687 行；
  - 個股頁 `page.tsx` 第 380～429 行；
  - `kelly_wording.py` 第 580～619 行；
  - `main.py` 的路由與 health。

**Grep 結果**
- `app/forecast`、`app/outlook`、`app/dirdef` 對範圍外的 import 只有 `data.interface`、`data.freshness`、`data.session_calendar`、`advice.banned_phrases`。
- 這些模組本身沒有其他範圍外的 import；三個 `__init__.py` 都沒有 import。
- 主工作樹沒有 `d631a75a`、`185c424b`、cg2 腳本（CG-2 尚未合併）。
- `docs/adr` 沒有 `alert_tick_status`、`positions_unreadable`（ADR-α、ADR-β 尚未落檔）。
- ADR-0030 沒有前端相關字樣；`work/reviews` 也沒有 6(d) 對前端的讀法紀錄。
- `AlertStore` 用的是主 DB（`deps.py:247`、`store.py:104`）。

**沒有查證**
- 所有 git 狀態：product HEAD、各分支 head、T-3 合併的實際時間。
- CEO 是否已經跑過驗收。
- 持倉無法讀取時，摘要端點的實際狀態碼。
- 前端是否有任何查詢帶除權息日。
- PriceBar 能不能收非有限的 volume。
- RSI 在 inf 輸入下的行為。
- 0050 分割（quant 註明未查證）。
- 各類 ETF 的漲跌幅制度。
- 工時都是推論。

---

## 下一步

- **coordinator**：
  - 今天把新發現 A 轉風控，請風控判定補充六附記四的 (r1)／(r2)。CEO 回貼時，先核對 `git_head` 是否含 `6cd7d25`。
  - 讀法定案之前，暫緩 product 的 `merge origin/main`，也暫緩任何前端合併。
  - 11-28 檢查點加看本件。
- **risk-compliance-officer**：
  - 補充六附記四的讀法；
  - 依第 4 點擬 CEO 題目，四個選項的後果要對稱，含「先不決定」；
  - 如果 CEO 選 2 或 3，RC-511 與 RC-516 要怎麼改發；
  - 前端折衷 F1、F2、H1、RC-695 的新字面。
- **creative-lead**：等風控確認方向之後，起草 F1、F2、H1 加註、RC-695 收起句（字面待風控定稿）。
- **frontend-engineer**：讀法定案、字面定稿之後，F1 或 F2、H1、RC-695 各開獨立分支，共用 T-3 的判斷函式。
- **quant-researcher、data-engineer**：
  - ADR-δ 的門檻與適用範圍（對照 ADR-0016 F7、sectors 保險），以及公司行動來源查證；
  - ADR-ε 的含息路徑定義，以及除權息資料覆蓋的起點。
- **product-manager**：ADR-ε 的範圍，以及前端折衷的排程。
- **tech-architect（我）**：
  - 風控回覆後，定稿補充六附記四；
  - 起草 ADR-δ、ADR-ε；
  - PR-3 的讀碼基準重定照原計畫。
- **dev-lead**：在 CEO 選項定案之前，不開任何後端登記前合併的工作。
- **CEO**：本件需要一個取捨，題目由風控擬（第 4 點），字面待風控定稿。

**相關路徑**
- /home/user/AICompany/work/reviews/2026-11-25-預測正確性風險盤點-quant.md
- /home/user/AICompany/work/reviews/2026-11-22-警示一輪紀錄ADR與B修訂與D10取代草案-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-22-RC556改字時點裁示與R0-2盤點-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-22-規則草案定稿與PR2PR3脫離閘門評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-22-T3合併前字面零差異確認RC690至RC695-風控.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md
- /home/user/AICompany/work/dispatch/2026-11-20-CEO決策-照v0.32登記與收盤值已知限制.md
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md
- /home/user/AICompany/docs/adr/0016-stock-desk-持倉漲跌欄的計算基準與-fail-closed.md
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/definitions.py
- /home/user/AICompany/apps/stock-desk/backend/app/outlook/inputs.py
- /home/user/AICompany/apps/stock-desk/backend/app/signals/technical.py
- /home/user/AICompany/apps/stock-desk/backend/app/signals/frame.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/signals.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/alerts.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/snapshot.py
- /home/user/AICompany/apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/keyLevels.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/page.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/TechnicalIndicatorsPanel.tsx
