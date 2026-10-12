# tech-architect F-9 第二次評估（風控裁定之工程影響；ADR-0024 修改清單 R-1～R-37）

- 唯讀讀碼評估，coordinator 自 agent 回報原文轉存（2026-10-12）。M-1～M-15 原文另見同目錄 `ADR-0024-M1-M15-tech-architect核對.md`。

## 本次結論

1. **F9W-4／F9W-12 的 attempt log 標記**：在 `price_bars_attempt_log` 加兩個可為 NULL 的欄位，`rejection`（`unit_mismatch`｜`unit_missing`）與 `rejection_at`。只有在 `rejection_at == last_attempt_at` 且該次提問晚於最後一次完整成功時，標記才算數。遷移比照 repo 既有的 `PRAGMA table_info`＋`ALTER TABLE ADD COLUMN` 做法，不回填資料。與 ADR-0009、0010、0019 都相容，ADR-0009 是「部分修訂」，只在檔頭加一行指標。
   - F9W-4 分兩半落地。(a)「同一次回覆不得改用快取」不需改 schema，放進 F-9b。(b)「冷卻期與標記延續」連同 F9W-12 的 C／C′ 版，另拆 **F-9b2**，列為 F-9c 合併前的硬性前提。
2. **F9W-11（新 missing token＋整書成因組）**：工程成本低，後端約 5 個檔、前端 1 個常數加測試，**可以隨 F-9b 一起落地**。所以風控例外的條件一（「無法隨 F-9b 落地」）不成立，我不出具這項評估，例外不適用。F-9b 真正卡住的是兩項字面：新成因句的改寫重審、庫存頁新標籤。
3. **ADR-0024 修訂**：完整清單見下方「三」，共 37 條，可交 tech-writer 一次套用。重要限制：**我先前的 M-1～M-15 原文，這次在 repo 和 scratchpad 都找不到**（全 repo grep `M-1[0-5]` 為 0；scratchpad 只有風控裁定這一份待落檔文件）。這份清單是我重新完整審過草稿後產出的。coordinator 若手上有 M 原文，請逐條對照：本清單沒涵蓋的 M 條照原文併入；兩者衝突時以本清單為準，因為它已納入風控裁定。
4. **F9W-13 方向子句**：讀碼確認，兩個函式都只看估值狀態、產業和是否為本標的，不看成因。所以「偏高」只在選中 D-a 時成立。更正字句與 6 個測試見下方「四」。
5. **PR 順序**：F-9a（進行中，併入 F9W-15）→ F-9b（範圍擴大）→ F-9b2（新增）→ F-9c → F-9d／F-9e。F-9c 合併前有 6 項硬性前提，見下方「五」。

## 各部門回報

### tech-architect（唯讀讀碼評估）

#### 評估摘要
- **採用的方案**：
  - 標記放在 attempt log，用雙欄加等值比對（方案 E）。
  - 新增估值缺漏 token（方案 I）。
  - F9W-4 拆兩段：(a) 放 F-9b，(b) 放 F-9b2。
  - 新增內部欄位 `ProviderResult.rejection`。W-d 分流本來就需要它，估值器共用同一個欄位。它不序列化進 API。
  - yfinance role 1 缺值時改成空字串原樣傳給服務層，由服務層判定 W-c′。這修訂了 D-6 原本「adapter 自己回 UNAVAILABLE」的寫法。理由是只保留一道閘門、一個字面出口，標記也只由服務層寫入。
- **否決的方案**：程序內記憶標記、單欄標記、新開一張表、沿用 `price`／`price_not_queried` token、併入 X-3c token。

#### 方案比較

**標記怎麼存**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **E：attempt log 加 `rejection`＋`rejection_at`（採用）** | 和冷卻判斷讀同一列；`delete_by_source`（ADR-0009 R-5）、`clear_attempt` 刪整列時標記自動一起清掉；加欄遷移有先例（`directory/store.py`、`kelly/store.py`、ADR-0019 D-3） | ADR-0009 D-3 的語意要擴充，需要在 ADR-0009 加修訂指標 | 舊版程式（或部署過程中 scheduler／API 兩個寫入程序版本不一致，ADR-0005 P-1）只更新 `last_attempt_at`，會留下屬於舊提問的標記。用 `rejection_at == last_attempt_at` 才算有效來防 |
| H：只加一欄 `last_rejection` | 少一欄 | 上一列所說的過期標記會讓 C 版「最近一次」這句話不屬實 | 否決 |
| F：新開 `price_bars_rejection_log` 表 | 不動既有表 | 兩張表要保持同步；`delete_by_source`、`clear_attempt`、diagnose 都要跟著改 | 兩表分歧後留下過期標記；否決 |
| G：程序內記憶 | 不用改 schema | API 與 scheduler 是兩個程序，重啟就消失；scheduler 觸發的 W-c，API 看不到 | 冷卻期內會回快取，直接違反 F9W-4；否決 |

**整書 token**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **I：新 token（採用）** | 語意正確；成本低 | 多一組成因句和一個標籤要送審 | 送審排程 |
| J：沿用 `price`／`price_not_queried` | 不用改 | 風控 F9W-11 不接受：沒問過來源卻顯示「查無」，語意相反 | 否決 |
| K：併入 `currency_market_mismatch` | — | X-3c 是指持倉紀錄不一致、使用者可以更正，語意不同 | 否決 |

**F9W-4／F9W-12 放哪個 PR**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 全部放 F-9b | 一次審完 | F-9b 已經包含閘門、准入、W-d、新 token、前端；再加遷移和冷卻三個分支，審查面太大；C′ 還沒核可，會卡住 F-9b | — |
| **(a) 放 F-9b、(b) 放 F-9b2（採用）** | (a) 不需改 schema，和 W-c 判定在同一個函式，放 F-9b 最便宜；F-9b2 專心處理遷移和冷卻，可以等 C′ 核可 | 多一個 PR | F-9b2 若沒合，F-9c 會被擋（已列為硬性順序） |
| 全部延到 F-9c | — | F-9c 本身要連網實證，再混進 schema 改動不妥 | 否決 |

#### 一、F9W-4／F9W-12 設計（含各處修改點）

**schema 與遷移（F-9b2，`cache.py`）**
- `_CREATE_ATTEMPT_LOG_SQL`（L89-96）的表不重建。`_init_schema`（L168-175）之後加一段遷移：
  - 先用 `PRAGMA table_info(price_bars_attempt_log)` 檢查，缺欄才在 `BEGIN IMMEDIATE` 內再檢查一次。
  - 然後 `ADD COLUMN rejection TEXT`、`ADD COLUMN rejection_at TEXT`，可為 NULL、不設 DEFAULT。
  - **不回填**：F-9b2 之前 W-c 不可能觸發，所以 NULL 就是正確值。
  - 重複初始化、兩個 `PriceBarCache` 指向同一個檔案時，都不得出現 duplicate column 錯誤（比照 ADR-0019 K-7／T-10）。
- `record_attempt`（L322-334）簽章改成 `record_attempt(symbol, market, *, at=None, rejection=None)`。用 keyword 參數加預設值，既有呼叫點不必改。
  - `ON CONFLICT` 時三欄一起覆寫：`rejection_at` 在有標記時等於 `at`，沒有標記時兩欄都寫 NULL。**不得用 COALESCE**。
- 新增 `last_attempt(symbol, market) -> AttemptRecord | None`，內含 at、rejection 兩欄，以及「標記是否有效」的判斷。`last_attempt_at` 保留為薄包裝。
- 讀到未知的 rejection 值：記 ERROR，視同沒有標記。這只可能來自手動改庫，退回的是 F-9b2 之前的行為。
- `delete_by_source`、`clear_attempt` 不用改，它們刪整列。

**標記語意（依 F9W-12）**
- **何時設定**：該次梯子「至少一層 W-c 或 W-c′，且沒有任何一層取得可用資料」時，`service.py` L241 的 `record_attempt` 帶入標記。有 W-c 層就記 `unit_mismatch`，優先於 W-c′。
- **何時清除**：成功路徑（L184）和一般失敗路徑都把標記寫成 NULL。
- **有效條件**：`rejection_at == last_attempt_at`，且 `last_attempt_at > fetch_log.last_fetched_at`（或沒有 fetch log）。後者就是 ADR-0019 K-3 允許的 R-8／D-8 比對。

**`service.py` 修改點**
- `_try_provider`（L476-519）：改回傳結構化結果（result、reason、rejection）。W-c、W-c′ 的分類用 D-5 的 `classify_currency`。`{provider}` 只能填 adapter 的 `source_id`。現在 L501 在沒有 `source_id` 時會退回類別名稱，產生 W-c 時不得走這條退路（F9W-3）。
- `get_daily_bars` 迴圈（L175-242），F-9b 處理：
  - 彙整各層的 rejection。
  - 有 W-c 時，`_fall_back_to_cache` 加參數 `serve_cache=False`：不呼叫 `cache.get`，直接回 `UNAVAILABLE`、`bars=[]`，reason 用 `_combine_reasons` 合併，並帶 `rejection="unit_mismatch"`。
  - W-c 層之後如果有層成功、原本要做增量合併（L186-203），改向該層要整段 `[start, end]`，不讀回快取頭段。現行美股梯子是 AV 在前、yfinance 在後，這種情形不可達，但規則要寫死，避免日後調換順序就破功。
- `_try_session_fresh_cache`（L312-443），F-9b2 處理：在 L323 之後、所有分支之前，加**單一前置守門**。這樣不依賴 ADR-0019 D-1 會改寫的分支結構。
  - **有效 W-c 標記、在冷卻期內**：不論快取有沒有列，一律回 `UNAVAILABLE`、`bars=[]`、C 版字面（`{minutes}` 取 `rejection_at`）、`rejection="unit_mismatch"`。這同時取代 L346-356（無快取）、L379-385 與 L420-426（以 `RECENT_ATTEMPT_FAILED_REASON` 回快取）三處，也擋住 L438 的一般快取服務分支。例如以舊 end 查歷史區間時，判定為 HAS_LATEST 的情形。
  - **有效 W-c 標記、在冷卻期外**：回 None，強制走梯子，不服務快取。
  - **有效 W-c′ 標記**：沒有快取時回 C′ 版（待送審），帶 `rejection="unit_missing"`。有快取時照現行 R-8 處理（F9W-4 明訂 W-c′ 不套用）。
- `get_cached_bars`（L244-283），F-9b2 處理：只**讀**標記，ADR-0010 R-2 禁止的是寫入。有效 W-c 標記時回 `UNAVAILABLE`，帶 `rejection`，reason 為 None。目前唯一的消費者是 cache_only 估值器，它不顯示 UNAVAILABLE 的 reason；日後若要顯示，要另行送審。
  - 這一點比風控字面要求得嚴：風控只點名 live 路徑。理由是 cache-only 讀到的是同一批可疑的舊列。

**估值器 live 路徑**
- `valuation.py` L454 呼叫的是 `service.get_daily_bars`，所以服務層修好之後自動涵蓋。alerts snapshot（`snapshot.py` L111 走 `load_bars`）也一樣。
- 估值器本身只為 F9W-11 而改。

**與既有 ADR 的相容性**
- **ADR-0009（accepted）**：D-3 的 attempt log 語意擴充；R-8／D-8 在 W-c 標記序列上的行為改變。算「部分修訂」，比照 ADR-0019 先例，只在 ADR-0009 檔頭加一行指標。
- **ADR-0010（proposed）**：R-1、R-2 不變（只讀不寫）；揭露點 5 對非 W-c 序列不變。
- **ADR-0019（proposed）**：
  - 現況尚未實作，`coverage_reaches`／`tail_fetched_at` 只出現在 `tests/test_adr0019_pending.py` 的 xfail。
  - 兩者改不同的表，各自遷移，前置守門也不依賴它的分支結構，所以先後順序都可以。
  - 但兩者都會動 `_try_session_fresh_cache`、`_fall_back_to_cache`、`_init_schema`，後合的那個 PR 負責 rebase，並重跑 ADR-0019 T-5（REFETCH 不得帶 `RECENT_ATTEMPT_FAILED_REASON`）。

#### 二、F9W-11 影響面與成本

| 層 | 改動 | 規模 |
|---|---|---|
| `app/data/interface.py` `ProviderResult` | 新增 `rejection: Literal["symbol_not_admitted","unit_mismatch","unit_missing"] \| None = None`。W-d 本來就需要它；不進 `LoadedBars.meta()`（`services/market.py` L88-102） | 小 |
| `app/data/service.py` | 准入拒絕（兩個入口）、W-c／W-c′ 無可用資料、C／C′ 冷卻回覆時設定 rejection | 隨 F-9b／F-9b2 一起做 |
| `app/services/market.py` `load_bars` L167-176 | `result.rejection` 不為 None 時，`reason=result.reason` 原樣傳出，不接 `NO_BARS_REASON`、不走 `with_provider_reason` | 小 |
| `app/portfolio/valuation.py` `_resolve_price` L446-456 | rejection 不為 None 時回新 token（live 與 cache_only 相同），取代 `price`／`price_not_queried` | 小 |
| 同上，`value_position` L373-377 | **建議**：拿到新 token 後比照 X-3c（`_currency_market_mismatch`），不再查匯率。`missing == [新 token]` 剛好一個，`fx`／`fx_open` 為 None；同步更新 `Valuation.fx_open` docstring（L258-264）列出的「None only where nothing was asked」清單 | 小 |
| `app/advice/book.py` `_book_level_notes` L976-1005 | 計數優先序改為：mismatched（X-3c）＞新 token＞`price_not_queried`＞asked，各組互斥；`asked = 未估值 − mismatched − 新組 − not_queried`；新增成因常數（等字面）；陳述順序建議 W4 → W5 → (b) → 新組，不動 X-3c「最後陳述」的既有核可順序，待風控確認 | 小 |
| 方向子句、`UnvaluedComposition`、`SYMBOL_UNVALUED_NOTE` | 不改。它們只看 `status != "ok"`；`SYMBOL_UNVALUED_NOTE` 不講成因，對被拒列也屬實（這也回答了 creative-lead 第九節第 6 點「未納入的標的」那個問題） | 0 |
| 前端 `valuationWording.ts` `MISSING_LABELS` | 新增一個 key；`valuationWording.test.ts` L18 鍵集合、開頭不得為「查無」／「本次未查」的斷言、禁詞掃描都要更新；`types.ts` `missing: string[]` 不用改 | 1 行＋測試 |
| `PositionsTable.tsx` L75-103 | 預設走一般分支（「資料不足」badge 加小字標籤），不用改 code。若 art-lead／風控要做成 X-3c 那種醒目晶片，因為上面已建議 `missing` 剛好一個，可以加一個精確形狀判斷函式 | 0～小 |

- **成本**：後端約 40-60 行，加約 10 個後端測試和 3 個前端測試。
- **風險**：
  - X-3c 既有的三組計數測試要改成四組。只能延伸，不能放寬。
  - qa-e2e 要在庫存頁 375／1280 驗新標籤。
- **能否隨 F-9b 落地**：可以。卡住的是 T-11（成因句改寫重審）和 T-12（庫存頁標籤）兩項字面。我不出具「無法落地」的評估，所以暫時沿用例外不適用，跟 F-9a 盤點數字是多少無關。

#### 三、ADR-0024 完整修改清單（交 tech-writer 一次套用）

來源標註：〔F9W-x〕是風控 2026-10-12 裁定；〔TA2〕是本次 tech-architect 評估（A 類，依讀碼）。

| # | 位置 | 原句 | 新句 | 來源 |
|---|---|---|---|---|
| R-1 | 檔頭「狀態」第 2 子項（L5） | 「與字面相關的待決事項（W-a～W-d、風控兩題裁示、X-3c／X3-F7 確認）見文末「待決事項」；其結果是否列為 accepted 前提，來源（任務單）未載，**待 coordinator／CEO 確認**。」 | 「accepted 前提（風控 2026-10-12 第 6 題）：T-5～T-9 的裁示結果須已納入本 ADR（本修訂納入 F9W-4、F9W-9、F9W-11、F9W-12、F9W-13、F9W-14）；T-1～T-4 的逐字字面是 F-9b／F-9c 的合併前提，不是本 ADR 的核可前提。」 | F9W 第 6 題 |
| R-2 | 檔頭「來源與版本」新增一個子項 | （無） | 「風控裁定 F9W-1～F9W-16（2026-10-12，落檔路徑由 coordinator 定）；tech-architect 2026-10-12 第二次評估（風控裁定之工程影響，coordinator 轉錄）。」 | TA2 |
| R-3 | 關聯，ADR-0009 那一行（L24） | 「**ADR-0009**（日線快取以交易日判定新鮮度）：相容；D-8 清理指令依其 R-5 連帶刪 log。」 | 「**ADR-0009**（accepted）：**部分修訂**其 D-3 的 `price_bars_attempt_log` 語意（另記該次提問的拒收類別與其時間，見本 ADR D-9），以及 R-8／D-8 對『最近一次提問帶 W-c 標記』序列的行為（不以快取回覆、冷卻期內回 C 版）；其餘不變。比照 ADR-0019 先例，ADR-0009 只在檔頭『修訂』清單加一行指標。本 ADR D-8（清理指令）依其 R-5 連帶刪 log。」 | F9W-4、F9W-12、TA2 |
| R-4 | 關聯，新增 | （無） | 「**ADR-0010**（proposed）：相容。cache-only 讀取同樣先過准入與幣別閘門，並**讀取**（不寫）W-c 標記；R-1／R-2 不變；新 `Valuation.missing` token（D-7）與 R-5 的 `price`／`price_not_queried` 並列、不改其語意；揭露點 5 對非 W-c／W-c′ 序列不變。」 | TA2 |
| R-5 | 關聯，新增 | （無） | 「**ADR-0019**（proposed）：相容。兩案改不同的表、各自遷移，採同一種 `PRAGMA table_info`＋`BEGIN IMMEDIATE` 重新檢查的模式（ADR-0019 K-7）；W-c 標記只用 `attempted > last_fetched_at` 比對（ADR-0019 K-3 允許的 R-8／D-8 用途），且守門置於 `_try_session_fresh_cache` 所有分支之前；實作先後皆可，後合者負責 rebase。」 | TA2 |
| R-6 | 關聯，新增 | （無） | 「**ADR-0017 X3-F7**：方向子句前提補『已估值列的日線價格單位與市場一致』（不用『價格幣別』，F7-R5）；此前提在 Consequences 殘留 R-a～R-c 情形下不保證成立，CEO 須知悉。」 | F9W-13 |
| R-7 | 關聯，新增 | （無） | 「**ADR-0022／ADR-0023**：方向子句規則不變；被撤下的列以 `insufficient_data` 進入同一未估值集合，由 ADR-0022 Decision 5 規則選句。」 | F9W-13 |
| R-8 | 關聯，X-3c 那一行（L27） | 「…為不同軸（任務單所述），本 ADR 不重用其字面。」 | 句尾加「；整書成因另立一組（D-7），計數優先序 X-3c 先於本組。」 | F9W-11 |
| R-9 | Context 第 4 點（L44） | 「外幣價格會被當成 USD／TWD 灌進總資產，全書比率偏低（**不保守**）。」 | 「外幣價格會被當成 USD／TWD 灌進總資產；常見的外國掛牌（例：以便士、日圓報價）數值遠大於等值美元，使總資產虛增、全書比率偏低（**不保守**）；方向取決於該報價數值與市場幣別的比例，並非必然偏低。」 | TA2 |
| R-10 | Options 表 | 4 列、無優缺點 | 改成「方案／優點／缺點／風險」四欄。A、B、D 補上優缺點。C 補理由：「濾掉部分列會在序列內部造成缺口，並被當成完整序列使用；同批混入不同單位，本身就表示該批不可信。」並增列 E、H、F、G（標記存放）與 I、J、K（token）兩組，內容照本報告的方案比較表 | TA2 |
| R-11 | Decision 引言（L77） | 「以下 D-1～D-8 為…」 | 「以下 D-1～D-9 為…（D-9 為 2026-10-12 依風控裁定新增）」 | TA2 |
| R-12 | D-1（L81）句尾 | （無） | 加「閘門（預期幣別、准入函式、該市場字面）為 `MarketDataService` 的 keyword-only 必填建構參數，由組裝層注入。」 | TA2 |
| R-13 | D-2 全節（L83-85） | 現行一段 | 換成：「(1) `_try_provider` 的結果逐根以 D-5 `classify_currency` 分類：任一根宣告值非空且不等於預期幣別 → 該層為 W-c；否則任一根為空字串或只有空白 → W-c′。兩者都把整條序列視為該層拒答：不寫快取、不 `record_fetch`、照記 `record_attempt`。以原值比對，不轉大寫（`usd` 屬 W-c，見失效條件 7）。(2) **W-c 不得與價格並存**：同一次梯子任一 live 層為 W-c，該次回覆不以快取回價格——降級時不讀快取，直接回 `UNAVAILABLE`、`bars=[]`，reason 依 `_combine_reasons` 合併；W-c 層之後若有層成功且原本要做增量合併，改向該層要整段、不讀回快取頭段。經 `MarketDataService` 涵蓋 `load_bars` 全部消費者與 live 估值器。(3) **標記延續**：有效 W-c 標記（D-9）存在時，任何讀取路徑都不以快取回該序列價格——冷卻期內回 C 版；冷卻期外 layer 0 不服務快取、改走梯子；cache-only 回 `UNAVAILABLE`。(4) W-c′ 不套用 (2)(3)。(5) 快取讀取路徑同樣逐根檢查舊列，不符或空白就整條序列 fail-closed、不刪資料；原因句見 T-15。(6) 放寬 (2)(3) 須 CEO 明確同意並附 tech-architect 實證。」 | F9W-3、F9W-4、F9W-12、TA2 |
| R-14 | D-4 第 1 段（L93）「被拒代號：…」之後 | （無） | 加「准入在 `get_daily_bars` 與 `get_cached_bars` 兩個入口、任何快取讀取之前執行；被拒時回 `UNAVAILABLE`、`bars=[]`，reason 為 W-a 或 W-b 全文，`rejection=symbol_not_admitted`。W-a／W-b 只能由服務層准入發出；AV adapter 扣額度前的縱深檢查被拒時，不得產出 W-a／W-b（正常路徑不可達，若需使用者面字面須用既有核可句或另送審）。」 | F9W-7 |
| R-15 | D-4 指數句（L93）「指數服務**顯式「不檢查形狀、只檢查幣別」**。」 | 同左 | 「指數服務顯式『不檢查形狀、只檢查幣別』，但 **W-a、W-b、W-c、W-c′、C、C′ 皆不適用指數路徑**（`services/index.py` 兩處會接指數版 `NO_BARS_REASON` 並加前綴）：指數閘門不帶任何使用者面字面、不寫 W-c 標記；yfinance role 2 誠實回報前，指數幣別檢查不可觸發，以測試釘住；role 2 合併的前提是指數用字面另經 creative-lead 起草、風控逐字審。」 | F9W-9 |
| R-16 | D-4 台股（L98）句尾 | （無） | 加「樣式須與 W-b『數字後接英文字母 K』逐字對應並以測試釘住；F-9d 實證若不符，規則與 W-b 回風控重審。」 | F9W-8 |
| R-17 | D-5（L102）句尾 | （無） | 加「W-c／W-c′ 分流的唯一來源為 `classify_currency(bars, expected) -> ok｜mismatch｜missing`；`check_currency` 的『不符』等於 mismatch ∪ missing，以等價測試釘住。」 | F9W-3、TA2 |
| R-18 | D-6 標題（L104） | 「D-6 adapter 只回報上游宣告幣別或經 admission 保證之值，缺值不補」 | 「D-6 adapter 回報上游宣告的幣別；尚未讀取上游宣告的 adapter 以市場幣別為**假設值**；缺值不補」 | F9W-14 |
| R-19 | D-6 內文（L106） | 「缺值時 role 1 回 UNAVAILABLE、不補市場預設。」 | 「缺值時以空字串原樣放入 `PriceBar.currency`、不補市場預設，由服務層閘門判定 W-c′；adapter 不自行回 UNAVAILABLE、不產出使用者面原因句（單一閘門，D-1）。」 | TA2 |
| R-20 | D-6 新增一段 | （無） | 「TWSE／TPEx／FinMind／Alpha Vantage 與 yfinance role 2 寫入的 `currency` 是依市場寫死的假設值，**不是**上游宣告，也**不受**准入保證：准入只排除特定代號形狀、降低外國掛牌混入的機會，無法確認任一回傳的價格單位（單一字母外國字尾仍可通過）。role 1 改讀 `meta.currency` 屬 F-9c，**須在 F-9b 與 F-9b2 皆合併之後**；F-9c 重錄真實 fixture 須確認 USD／TWD 實際寫法，發現變體回風控。」 | F9W-3、F9W-14 |
| R-21 | D-7 標題（L110） | 「D-7 不新增 DataStatus 與 API token」 | 「D-7 不新增 DataStatus 與 API 狀態值；新增一個估值缺漏 token 與整書成因組」 | F9W-11 |
| R-22 | D-7 內文（L112-117） | 現行 | 換成：「資料層回 `UNAVAILABLE`、bars 清空，API 外層照既有路徑回 `insufficient_data`。`ProviderResult` 新增內部欄位 `rejection`（`symbol_not_admitted`｜`unit_mismatch`｜`unit_missing`｜None），只供 `load_bars` 的 W-d 分流與估值器使用，**不得**序列化進 `LoadedBars.meta()` 或任何 API 回應。`Valuation.missing` 新增一個 token（名稱由實作定，不面向使用者），涵蓋准入拒絕、W-c、W-c′（含 C／C′ 冷卻回覆），live 與 cache_only 相同，取代 `price`／`price_not_queried`、不並存；建議該列不查匯率，`missing` 只有這一個 token。整書成因另立一組，不計入 `asked`；計數優先序 X-3c＞本組＞`price_not_queried`＞asked，各組互斥；陳述順序 W4 → W5 → (b) → 本組（待風控確認）。成因句、庫存頁標籤由 creative-lead 起草送風控，未核可前不得合併 F-9b。W-d：W-a、W-b、W-c、W-c′、C、C′ 即完整 reason；准入拒絕或任一層為 W-c／W-c′ 時，`load_bars` 不接 `NO_BARS_REASON`、不走 `with_provider_reason`；W-c 與其他層原因並列時走 `_combine_reasons`。既有 token 不變；不得重用 `CURRENCY_MARKET_MISMATCH_NOTE`／`_CAUSE`。風控『暫時沿用』例外：tech-architect 評估新 token 可隨 F-9b 落地，例外條件一不成立。本檔不收錄字面。」 | F9W-6、F9W-11、TA2 |
| R-23 | D-8（L121）句尾 | （無） | 加「（suggested）清理指令可另列帶有效 W-c 標記的序列，只列不刪，供 CEO 判斷。」 | TA2 |
| R-24 | 新增 D-9（在 D-8 之後） | （無） | 「### D-9 attempt log 記錄拒收類別。`price_bars_attempt_log` 新增 `rejection TEXT`（`unit_mismatch`／`unit_missing`／NULL）與 `rejection_at TEXT`。有效條件：`rejection_at == last_attempt_at`，且 `last_attempt_at` 晚於 fetch log 的 `last_fetched_at`（或沒有 fetch log）。設定：該次梯子至少一層 W-c 或 W-c′、且沒有任何一層取得可用資料時寫入，有 W-c 就記 `unit_mismatch`；其他提問一律寫 NULL。遷移：缺欄時在 `BEGIN IMMEDIATE` 內重新檢查後 ADD COLUMN，不回填；重複初始化與同檔雙實例不得報錯。只有 `get_daily_bars` 寫入；layer 0 與 `get_cached_bars` 只讀（ADR-0010 R-2）。`delete_by_source`、`clear_attempt` 刪整列，不另處理。讀到未知值：記 ERROR、視同無標記。冷卻字面：W-c → C 版（風控核可）；W-c′ 且無快取 → C′ 版（待審）；W-c′ 且有快取 → 照 ADR-0009 R-8 附 `RECENT_ATTEMPT_FAILED_REASON`（待風控確認）；`{minutes}` 取 `rejection_at`。」 | F9W-4、F9W-12、TA2 |
| R-25 | 實作約束表（L125-136）之後增列 | （無） | C-11～C-29，原文照本報告「對實作的約束」 | 各 F9W、TA2 |
| R-26 | 好處第 2 點（L145） | 「任務單：F-9b 後 F7-R12 (ii) 殘留對**可偵測情形**關閉（**須風控確認**）。」 | 「F7-R12 (ii) 殘留**只部分關閉**：F-9b 後關閉 2 字母以上字尾的美股代號、台股『數字＋K』（未實證）；F-9c 後（且 F9W-4 已落地）關閉 yfinance 新抓、宣告與市場不符的資料。其餘見壞處 R-a～R-c。」 | F9W-14 |
| R-27 | 好處第 4 點（L147） | 「不新增 DataStatus 與 API token（D-7）。」 | 「不新增 DataStatus 與 API 狀態值（D-7）；新增的 `ProviderResult.rejection` 為內部欄位、不進 API。」 | F9W-11 |
| R-28 | 壞處 3（L154） | 「**冷卻期內原因句變籠統**：…此項能否接受須風控裁示（見待決事項）。」 | 「**冷卻期原因句**：W-c 標記序列回 C 版、W-c′ 回 C′ 版（F-9b2）。F-9c 合併前，W-c 不可觸發，暫時沿用 `COOLDOWN_NO_CACHE_REASON`／`RECENT_ATTEMPT_FAILED_REASON`（A 版）可以接受；B 版不採。」 | F9W-12 |
| R-29 | 壞處 4（L155） | 「…既有測試的實際牽動範圍，任務單**未載**，**待查證**…」 | 「現況 `MarketDataService(` 建構點 48 處、分布 9 檔（`deps.py` 3 處，其餘為測試，其中 `test_service.py` 32 處）；建議閘門參數為 keyword-only 必填，測試以單一 helper 建構，避免無關 diff。」 | TA2（grep） |
| R-30 | 壞處 6（L157） | 「…**待 tech-architect 確認**是否另案。」 | 「不另案處理行事曆本身：F-9b 後被閘門擋下的列不再寫入（D-3），既有汙染由 F-9e 清理；殘留 R-a、R-b 仍會汙染，數量由 F-9a 盤點交 CEO 知悉。」 | TA2 |
| R-31 | 壞處，新增 R-a～R-c、標記不黏著、四組計數 | （無） | 「**R-a** Alpha Vantage 供應的單一字母外國字尾代號（AV 寫死 USD，閘門看不出）；**R-b** 寫死幣別的 adapter 寫入的舊快取列（快取閘門只比對宣告值，看不出；F-9e 清不到未被准入涵蓋者）；**R-c** 准入未涵蓋的其他樣式。F-9a 盤點單一字母字尾清單，交 CEO 逐一人工確認。**W-c 標記不黏著**：下一次一般失敗會覆寫標記，之後的降級路徑可能再以快取回覆該序列（附既有原因句）；若盤點顯示此類序列存在，再評估『隔離』（只由成功提問或清理指令解除，需新字面）。被拒列不再計入『缺價格或匯率』，X-3c 既有三組計數測試改為四組。」 | F9W-14、F9W-15、TA2 |
| R-32 | 被此決策約束的事（L162-164）增列 | （無） | 「新增任何可能以快取回價格的讀取路徑，須先檢查 D-9 標記；新增的 adapter 須有 `source_id`（W-c／W-c′ 的 `{provider}` 只取它）。」 | F9W-3、F9W-4 |
| R-33 | 與既有 ADR 的關係表（L170-176） | ADR-0009 那列「相容」 | ADR-0009 改為「部分修訂（D-9、D-2 (2)(3)）」；增列 ADR-0010「相容」、ADR-0019「相容（先後皆可）」、ADR-0017 X3-F7「補前提」、ADR-0022／0023「規則不變」，說明欄照 R-3～R-7 | TA2 |
| R-34 | 失效條件（L182 註記與第 5 項） | 註記「…非 tech-architect 原文，待 tech-architect 確認增刪」；第 5 項「風控否決任一新字面（W-a～W-d）或不接受冷卻期原因句遺失 → 重審 D-7 與 F-9b 範圍。」 | 註記改為「1～6 經 tech-architect 2026-10-12 確認；7～11 為 tech-architect 增列」。第 5 項改為「風控否決任一新字面（W-a、W-b、W-c、W-c′、C、C′、新成因句、新標籤）→ 重審 D-7／D-9 與對應 PR 範圍。」 | TA2 |
| R-35 | 失效條件增列 7～11 | （無） | 7.「F-9c 實證 `meta.currency` 出現大小寫或其他變體 → 重審 D-2 分類規則與 W-c 字面（回風控）。」8.「F-9d 實證『數字＋K』非外幣計價或有其他樣式 → 准入規則與 W-b 回風控。」9.「單一字母字尾盤點出外國掛牌持倉 → 重審 D-4 美股白名單（考慮已知外國交易所字母清單）與 D-9 是否改為黏著。」10.「指數幣別檢查要觸發 → 指數字面送審、重審 D-4 指數段。」11.「CEO 放寬 F9W-4 → 重審 D-2 (2)(3)。」 | F9W-3、F9W-4、F9W-8、F9W-9、F9W-15 |
| R-36 | 尚缺的事實表 | 第 1 列 | 第 1 列加「（含 USD／TWD 實際寫法）」；增列第 8 列「AV 對 `.L` 等單一字母外國字尾的實際反應」（F-9d），第 9 列「單一字母字尾序列與持倉清單」（F-9a 合併後由 CEO 本機盤點） | F9W-3、F9W-14、F9W-15 |
| R-37 | PR 拆分表、硬性順序、風險與相依（L215-232）、待決事項（L238-251） | 現行 | PR 表與硬性順序換成本報告「五」的內容。風險與相依 L230 換成本報告「四」的更正句；L231「已估值列的價格幣別與市場一致」改為「已估值列的日線價格單位與市場一致」，並加「此前提在殘留 R-a～R-c 下不保證成立，CEO 須知悉」；L232 換成 R-26 的內容。待決事項：T-1 核可 alt-1、T-2 核可第二句 alt-2、T-3 核可（美／台）、T-4 核可（不另立基底句、不加前綴；保守退路未核可）、T-5 裁示另立成因組、T-6 裁示 C 版、T-7 更正（見「四」）、T-8 同意（用詞「日線價格單位」）、T-9 部分關閉（F9W-14）。新增 T-11 整書成因句改寫重審（F-9b 前）、T-12 庫存頁新標籤（F-9b 前）、T-13 C′ 版（F-9b2 前）、T-14 C 版是否分市場兩句（suggested）、T-15 快取舊列幣別不符 fail-closed 的原因句（F-9b 前；若 F-9a 盤點為 0，可由 CEO 列為殘留）、T-16 指數用字面（role 2 合併前）、T-17 W-c′ 有快取時沿用 `RECENT_ATTEMPT_FAILED_REASON`（風控）、T-18 新組陳述順序（風控）。表尾句改為「已核可 W-a、W-b、W-c（美／台）、W-c′（美／台）、C，共 7 句」 | F9W 全、TA2 |

佐證清單：tech-writer 為每條新增內容補上 B 類來源列（風控裁定與本次評估）。

#### 四、F9W-13 方向子句

**行為確認（讀碼）**
- `book.py::_symbol_direction`（L1009-1044）：
  - 本標的有自己的未估值列時，只有它 → D-d1，還有其他標的 → D-d2。
  - 卡片沒有產業 → D-a。
  - 同產業或產業未知的缺口 → D-P。
  - 其他 → D-a。
- `_book_direction`（L1047-1076）：
  - 沒有可比較的產業 → D-a。
  - 有產業未知的未估值列，或回報產業 Y 內有未估值列 → D-P。
  - 其他 → D-a。
- 共同點：都只讀 `UnvaluedComposition`（由 `_unvalued_composition` L798-829 以 `status != "ok"` 建立）、`sector_numerator_gaps` 和 `unvalued_lots_in_sector`，**不讀 `missing` token、不看成因**。

**任務單更正字句**（取代任務單 L54「X-3c 為不同軸…送風控）。」整句；ADR-0024 L230-231 照 R-37 同步）：

> 「X-3c 為不同軸，F-9 不重用其字面。被 F-9 撤下的列（准入拒絕、W-c、W-c′）以 `status=insufficient_data` 進入與其他未估值列相同的未估值集合（`UnvaluedComposition`）；方向子句由既有規則（`book.py::_symbol_direction`／`_book_direction`，只看估值狀態、產業歸屬與是否本標的，不看成因）選出 D-a／D-P／D-d1／D-d2，『偏高』只在選中 D-a 時成立，並非一律成立（風控 F9W-13 更正）。X3-F7 前提補『已估值列的日線價格單位與市場一致』；此前提在 F9W-14 所列殘留情形下不保證成立，須 CEO 知悉。」

**任務單其他也要同步的地方**：
- L17：「不新增 DataStatus 或 API token」改照 R-21。
- L30：缺值處理改照 R-19。
- L55：F-7 殘留改照 R-26。
- L44-51 拆 PR 表改照「五」。

**要加的測試**（後端，F-9b）：
1. 被撤下列（帶新 token）出現在 `UnvaluedComposition`，且 `composition.total()` 等於整書未估值數。
2. 被撤下列是本標的自己的列、而且是唯一的未估值列 → D-d1；同時還有其他標的未估值 → D-d2。
3. 被撤下列屬於別的標的、和卡片同產業 → D-P；產業未知 → D-P。
4. 被撤下列屬於別的標的、在其他產業，卡片有產業 → D-a（「比率會因此偏高。」）。
5. 整書範圍：回報產業 Y 為 None → D-a；被撤下列在 Y 內 → D-P。
6. 同一本帳同時有 X-3c、新組、not_queried、asked 各一列：四句成因各自的 count 正確、互斥，方向子句只選一次、四句共用。

#### 五、PR 拆分與順序（更新）

| PR | 內容 | 前提／審查 |
|---|---|---|
| **F-9a**（進行中） | 原範圍，加上 F9W-15（suggested，採納）：列出所有通過准入、帶單一字母字尾的快取序列與持倉（只列代號與計數，A／B／C 等常見類別字母只標註、不判斷），交 CEO 人工確認 | qa-reviewer＋Codex |
| **F-9b**（範圍擴大） | 服務層閘門與 `classify_currency`；兩個入口的准入；`ProviderResult.rejection`；`load_bars` W-d；F9W-4 (a) 同次回覆不讀快取；W-a、W-b、W-c、W-c′ 常數；新 token、整書成因組、前端標籤（F9W-11）；方向子句測試（F9W-13）；deps 接線（含指數閘門無字面，F9W-9）；AV 縱深檢查（F9W-7）；消費端字串表（F9W-10）。建議分 commit：介面 → 閘門 → 准入 → W-d → 估值器 → 成因組 → 前端 → deps | 字面 T-11、T-12、T-15 核可；建議 ADR-0024 修訂版經 CEO 核可；qa-reviewer＋Codex＋風控＋qa-e2e（K 線區、操作摘要、首頁風險上限「詳細」、庫存頁，375／1280） |
| **F-9b2**（新增） | D-9 標記欄位與遷移；layer 0 前置守門（C／C′、冷卻期外強制走梯子）；`get_cached_bars` 讀標記；F9W-12 測試 | 在 F-9b 之後；C′（T-13）核可；若採 T-14 須送審；qa-reviewer＋Codex＋風控（字面） |
| **F-9c** | yfinance role 1 讀 `meta.currency`，缺值傳空字串；role 2 排除 | 見下方硬性前提 |
| **F-9d** | 原範圍，加 AV 對 `.L` 的反應（F9W-14）；「數字＋K」實證結果回風控（F9W-8） | 需連網 |
| **F-9e** | 原範圍，（suggested）可列出帶 W-c 標記的序列 | CEO 本機執行 |

**F-9c 合併前的硬性前提**：
1. F-9b 已合併，含 F9W-4 (a) 與 F9W-11。
2. F-9b2 已合併，含 F9W-4 (b) 與 F9W-12。
3. C′ 字面已核可。
4. 真實 fixture 已確認 USD／TWD 寫法（F9W-3）。
5. role 2 已排除；若要納入，指數字面 T-16 須先核可。
6. ADR-0024 已 accepted。

ADR-0019 的實作與 F-9b2 先後都可以，後合者負責 rebase。

#### 對實作的約束（C-11～C-29，逐條可檢查）

- **C-11**：fake primary 回 W-c、快取裡有幣別正確的舊列時 → 回 `UNAVAILABLE`、`bars=[]`，不回傳任何快取列；live 估值器在同一情境得到新 token。
- **C-12**：F-9b 合併時 W-c 不可觸發。deps 建構的每個正式 adapter 用既有 fixture 斷言 `currency == MARKET_CURRENCY[market]`；F-9c 前，yfinance `_parse_result` 不讀 `meta.currency`。
- **C-13**：`LoadedBars.reason` 以完全相等釘住六種情境：W-a 單獨、W-b 單獨、W-c 單獨、W-c＋AV 原因句、W-c′、C 版。
- **C-14**：`{provider}` 只取 `source_id`；provider 沒有 `source_id` 時，不得產生 W-c／W-c′（測試）。
- **C-15**：AV 縱深檢查的程式路徑不出現 W-a／W-b 常數（grep 加測試）。
- **C-16**：台股准入 regex 與「數字後接英文字母 K」逐字對應；正、反例各至少 4 個，C-7 清單照舊。
- **C-17**：指數服務不寫標記、不帶 W-c 字面；`services/index.py` 不引用 W-c、W-c′、C、C′ 常數（grep）；role 2 不可觸發（測試）。
- **C-18**：`LoadedBars.meta()` 鍵集合不變；任何 API schema 都不出現 `rejection`。
- **C-19**：新 token 在 live／cache_only × 准入／W-c／W-c′ 六種組合下各有一測；`missing` 不同時出現 `price` 或 `price_not_queried`；若採「不查匯率」建議，斷言 `missing` 長度為 1、`fx`／`fx_open` 為 None、匯率 provider 零呼叫。
- **C-20**：計數優先序與互斥（「四」的測試 6）；新組不計入 `asked`；陳述順序釘住。
- **C-21**：方向子句測試 1～5（「四」）。
- **C-22**：`MISSING_LABELS` 的鍵集合測試更新；新標籤不以「查無」或「本次未查」開頭；禁詞掃描通過。
- **C-23**（F-9b2）：遷移測試：舊 schema 加欄後兩欄為 NULL；第二次初始化不改變任何值；同檔兩個實例不報 duplicate column。
- **C-24**（F-9b2）：`rejection_at != last_attempt_at` 時視同無標記；只更新 `last_attempt_at` 的舊式寫入不會留下有效標記。
- **C-25**（F-9b2）：冷卻期內的有效 W-c 標記：
  - 無快取，以及有快取的三種分支（無 coverage、REFETCH、一般服務）→ 皆回 C 版、`bars=[]`，不出現 `RECENT_ATTEMPT_FAILED_REASON`。
  - 冷卻期外 → provider 被呼叫。
  - cache-only → `UNAVAILABLE`，並帶新 token。
- **C-26**（F-9b2）：W-c′ 標記：無快取 → C′；有快取 → 照現行 R-8 行為。
- **C-27**（F-9b2）：成功提問與一般失敗提問都把標記寫成 NULL；W-c 與 W-c′ 同時出現時記 `unit_mismatch`。
- **C-28**：PR 說明附上 W-a 在每個消費端最終顯示的字串表（F9W-10）。
- **C-29**：每個常數依 C-9 註明風控核可出處並引用本次裁定；PR 說明引用本裁定與 F7-R10（F9W-16）。

### 給其他部門（經 coordinator 轉達）
- **tech-writer**：一次套用上面的 R-1～R-37。M-1～M-15 請 coordinator 先提供原文，對照後一併套用。
- **creative-lead**：T-11（64 字成因句依 (a)～(e) 改寫）、T-12（庫存頁標籤）、T-13（C′ 版）；（suggested）T-14；T-15（快取舊列不符的原因句，或待 F-9a 盤點後由 CEO 列為殘留）；T-16（指數用字面，不急）。
- **risk-compliance-officer**：待確認 T-17、T-18；另有 cache-only 也套用 W-c 標記，這比裁定字面更嚴，請知悉。
- **CEO**：
  - 本次修訂把 ADR-0009 列為「部分修訂」，需要核可。
  - X3-F7 前提在殘留 R-a～R-c 下不保證成立。
  - 我不出具 F9W-11 例外所需的評估，所以 F-9b 會等字面核可。

## 驗證

- **讀碼核對**（皆為 product/stock-desk 工作樹現況）：
  - `app/data/service.py` 全檔：L61-69 常數；L175-242 梯子；L244-283 cache-only；L312-443 layer 0，含 L333-357、L366-385、L414-426 三個冷卻分支；L476-519 `_try_provider`（L501 退回類別名稱）；L521-571 `_fall_back_to_cache`。
  - `app/data/cache.py`：L38-96 三張表的 DDL；L168-175 `_init_schema`，無遷移機制；L322-334、L380-407、L505-533。
  - `app/data/interface.py` L87-127；`app/data/quality.py` L40-123。
  - `app/portfolio/valuation.py` L30-139、L248-269、L342-479、L591-614。
  - `app/advice/book.py` L186-302、L798-845、L952-1076；`app/advice/limits.py` L723-757、L1121-1162；`app/advice/book_limits.py` 的 `SYMBOL_UNVALUED_NOTE` 用法。
  - `app/services/market.py` L45-194；`app/services/index.py` L74、L200-210、L255-266、L377-386。
  - `app/api/deps.py` L90-185；`app/alerts/snapshot.py` 的 `load_bars` 用法。
  - 前端 `valuationWording.ts` 全檔、`PositionsTable.tsx` L69-104、`types.ts` L183。
  - ADR-0009 L1-139、ADR-0010 全文、ADR-0019 全文、ADR-0017 X3-F2／F3／F7。
- **grep 事實**：
  - `MarketDataService(` 共 48 處、9 檔。
  - `.missing` token 在後端只有 `book.py` 一個消費者。
  - `coverage_reaches`／`tail_fetched_at` 只出現在 `tests/test_adr0019_pending.py`，ADR-0019 尚未實作。
  - `admission`／`check_currency` 尚未出現在 data 層，F-9a 還沒落地到這個工作樹。
  - 既有加欄遷移的先例在 `directory`、`kelly`、`positions`、`dividends`、`playbook` 各 store。
  - `M-1[0-5]` 全 repo 0 筆。
- **推論，未實證**：
  - 美股梯子「W-c 之後還有層成功」目前不可達，這是依 `deps.py` L102-107 的順序推得。
  - 外國報價使比率「多半偏低」是依常見報價單位推論，沒有實測。
- **未做的事**：沒有執行任何測試；沒有連網；沒有讀 `.env` 或 `backend/data/*.db`；沒有改任何檔案（唯讀）。
- **主要待查證**：
  - M-1～M-15 原文（需 coordinator 提供）。
  - 風控裁定落檔後的路徑。

## 下一步

1. **coordinator**：
   - 把風控裁定落檔到 `work/reviews/`。
   - 提供 M-1～M-15 原文給 tech-writer，與 R-1～R-37 對照合併後一次套用到 `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`。
   - 依「四」更正 `/home/user/AICompany/work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md` 的 L54、L17、L30、L55 與拆 PR 表。
2. **creative-lead → 風控**：T-11、T-12、T-15 是 F-9b 的關鍵路徑；T-13 是 F-9b2 的關鍵路徑。
3. **dev-lead／data-engineer**：
   - F-9a 併入 F9W-15 清單。
   - F-9b 可以先依 C-11～C-22 開工，字面先用占位常數，核可前不合併。
   - F-9b2 在 F-9b 之後疊上去開發。
4. **CEO**：
   - 核可 ADR-0024 修訂版，包含對 ADR-0009 的部分修訂。
   - 知悉 X3-F7 前提的殘留、W-c 標記不黏著這項殘留，以及 F-9c 的 6 項硬性前提。
   - F-9a 合併後在本機跑盤點，依單一字母字尾清單逐一確認。
5. **qa-reviewer**：審 F-9b／F-9b2 時逐條勾 C-11～C-29，並用 `componentWordingScan` 複核禁詞。

相關檔案（絕對路徑）：
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/pending-docs/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md`
- `/home/user/AICompany/docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md`
- `/home/user/AICompany/work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/cache.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/interface.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/market.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/advice/book.py`
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/valuationWording.ts`
- `/home/user/AICompany/apps/stock-desk/frontend/app/components/PositionsTable.tsx`
- `/home/user/AICompany/docs/adr/0009-stock-desk-日線快取以交易日判定新鮮度.md`
- `/home/user/AICompany/docs/adr/0010-stock-desk-整書估值的資料新鮮度與單一請求的-io-預算.md`
- `/home/user/AICompany/docs/adr/0019-stock-desk-日線-coverage-判定與取得時間單一基準.md`