# ADR-0040：stock-desk 排程台把「資料層判定已含最新交易日」的快取日線視為可用（R6 重新解讀；限定範圍豁免 N172-C3、C-B11）

- 狀態：proposed（CEO 書面核可本文後改為 accepted）
- 日期：2026-11-05
- 決策者：
  - tech-architect（草案）
  - CEO #108（2026-11-05）：核可方向 (乙)，條件依風控 [風控-1105] B-5 選項 1。本文轉 accepted 另需 CEO 書面核可（見「待決」）
  - risk-compliance-officer：R6 重新解讀的條件；N190-I、B-2、B-4 逐字定稿
- 適用範圍：僅 product/stock-desk。程式路徑相對於 `apps/stock-desk/backend/`。
- 與既有 ADR 的關係：
  - 限定範圍豁免 ADR-0035 N172-C3 與 ADR-0034 C-B11，範圍見 Decision 12。
  - 補充 ADR-0003、0005、0009、0010、0015、0033、0035、0039。
  - 不取代任何 ADR。既有 ADR 原文不改（ADR-0001）。
- 來源簡稱（皆在 `work/reviews/` 下）：
  - [qa-1104] `2026-11-04-N190實測-qa-automation.md`
  - [qa-1105] `2026-11-05-N190預載情境實測-qa-automation.md`
  - [TA-1105] `2026-11-05-N190修正方向評估-tech-architect.md`
  - [風控-1104] `2026-11-04-N190重裁-風控.md`（N190-I 逐字）
  - [風控-1105] `2026-11-05-N177修復與N190字面裁示-風控.md`（B-1～B-5）
  - [M1] `2026-11-05-ADR0035補充五修正一-tech-architect.md`（M1-3）
  - 實測腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/test_n190.py`、`test_n190_sched.py`。這是 session 暫存檔，不是永久檔，QB-7 要求移植進 repo。
- 程式位置：worktree bf03a9c 的快照，請以內容定位。全部是讀碼判定，未執行。
- 字面規則：本檔只寫識別名，逐字以風控定稿為準，只放在 `wording.py`。

## Context（背景）

1. **R6 的本意**：stale／unavailable／demo 不得輸出可執行指令，目的是不讓過時的資料驅動指令。實作把「過時」等同於 `status == "cached_stale"`（engine.py:55-65）。依據的前提是「cached_stale 代表沒有 live 來源回應」。
2. **根因**：
   - (a) ADR-0009 D-4 讓 TW 也開了 layer 0 之後，`cached_stale` 多了一種意思：「快取已經含最新交易日，所以沒去問來源」。engine 的前提因此失效。
   - (b) `LoadedSeries`（service.py:117-125、:947-949）把 `is_within_ttl` 丟掉了，違反 interface.py:104-107「consumer 必須兩個欄位一起讀」。
   - (c) 指數的 `LoadedBenchmark`（services/index.py:315-407）根本沒有這個欄位。
   - 一般規律：某一檔在某一個交易日，只有全系統第一次打到 live 的那次載入，會產生可用的序列。
3. **實測**（[qa-1104]、[qa-1105]）：

| 情境 | 載入結果 | 現況後果 | 本 ADR 之後 |
|---|---|---|---|
| (a) 到期列，同請求載入兩次 | 結算 fresh；評估 cached_stale，ttl True | S/P 不評估 | 可用（評估另沿用結算序列） |
| (b2) 同日重新載入 | cached_stale，ttl True | 不實警示 | 可用 |
| (c) 休市日，連續 5 日 | 結算 fresh；評估 cached_stale | 每天都不評估，輪替 | 休市後的各日：可用；休市日當天 16:00：靠 Decision 7 的 (i) |
| S1：15:10 排程預載（已公布） | cached_stale，ttl True，live 0 次 | S1 不評估 | 可用 |
| S1′-a：15:10 未公布 | cached_stale，ttl False，最後 bar 是前一日 | 不評估 | 仍不可用（資料確實少一個交易日） |
| S1′-b：16:30 排程補抓 | ttl True | 不評估 | 可用 |
| S1′-c：指數冷卻被鎖 | 指數 ttl False | M1 不評估 | 仍不可用 |
| S2：個股頁、訊號頁先載入 | ttl True | 不評估 | 可用 |
| S3-R／S3-def／sector：指數先被載入 | 指數 ttl True | M1 不評估，R 順延並計次，防守沒進 | 可用 |
| S3-sector-cold | backup | 無影響 | 不變 |

   CEO 回報：持倉簿與 playbook 的標的有重疊，scheduler 有開。所以 S1 是每天都會發生的主路徑。
4. **`is_within_ttl` 的語意**（讀碼確認）：`CACHED_STALE` 只從三處回傳，三處都只在 `judge()` 判為 `HAS_LATEST_SESSION` 時才給 `is_within_ttl=True`：
   - layer 0（data/service.py:848-852）；在 S3-1 改判為 REFETCH 的情況下，不會走到這裡；
   - 全部來源失敗後的降級（:996-1013）；
   - cache-only（:471-486；playbook 不使用）。
   R-8 分支一律給 False（:789-795、:830-836）。live rung 一律為 None。`judge()` 的 `HAS_LATEST_SESSION` 等價於 `max(bar.date) >= expected_session(policy, requested_end, now)`（freshness.py:184）。
5. **限制**：
   - ADR-0005：:324 否決第五個 `DataStatus`；I-3 規定揭露只能往悲觀方向，快取結果維持 `CACHED_STALE`。
   - ADR-0015 C1、C-4：命中不得改標成 FRESH 或 BACKUP。
   - ADR-0003 約束 7。
   - N172-C3、C-B11：engine 零 diff。
   - CEO #108 的條件：指令列照實記 `cached_stale`；不得用 runtime 旗標；過時、unavailable、demo 三種一律不產生指令，各有測試；另立 ADR 豁免，範圍只限 `is_usable` 與 snapshot／`LoadedSeries` 的欄位。
   - [M1] M1-3 第 5 點的四條約束。

## Options（選項比較）

### 一、根治方向

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| **(乙) engine 接受 cached_stale ∧ ttl True ∧ 非 demo** | 根治 S1、S2、S3、(a)、(b2)；不增加 live 呼叫；指令列照實記錄 | engine 有限定 diff；重新評估變多 | N-188／N-189／N-177 的遮蔽解除 | **採用（CEO #108）** |
| (vi) playbook 專用旗標，讓 ladder 跳過 layer 0 | engine 零 diff | 要修訂 ADR-0009 D-4；每次重新載入都打 TWSE；US 會燒 AV 額度 | 撞上限流、R-8 冷卻，反而增加資料缺漏 | 不採 |
| 只做 (i) 沿用結算序列 | 改動小 | 修不到 S1、S2、S3、(b2) | 停損主路徑每天失效 | 不採（只當配件） |
| 只靠揭露 | — | 停損長期失效 | — | 風控 VETO（長期方案） |
| (ii) 改標 fresh，或新增 status | — | 指令列會誤述資料狀態 | 違反 ADR-0005、ADR-0015 | 風控 VETO，TA 否決 |

### 二、第④項條件（最新 bar 是 `judge()` 判定的最新交易日）的實作

| 方案 | 結論 |
|---|---|
| **(d1) 直接用資料層 `judge()` 的判定結果，也就是 `is_within_ttl`，原樣傳遞** | **採用**。同一份實作、同一個時鐘、同一次判定 |
| (d2) playbook 自己用 `expected_session(...)` 重算 | 否決。這就是第二份判定；playbook 拿不到資料層的 `now`，時間點不同，兩次判定可能不一致 |
| (d3) `ProviderResult` 新增「已含最新交易日」欄位 | 否決。要動 `app/data/**`，而且和 D-5 的 `is_within_ttl` 重複 |
| (d4) 再加「`snapshot.data_date` 等於本次 T」 | 不採。重新載入會和 first-touch 的 fresh 判定不一致（同一批 bar，fresh 可用、快取不可用），等於重造 (b2)；而且不在 CEO 的條件內 |

### 三、指數的欄位傳遞

| 方案 | 結論 |
|---|---|
| **(x1) `LoadedBenchmark` 加 `is_within_ttl: bool \| None = None`，`load_market_benchmark` 的兩個回傳分支都照抄 `result.is_within_ttl`；`meta()` 不變** | **採用** |
| (x2) playbook 直接呼叫 `IndexSeriesService` | 否決。會繞過 `load_market_benchmark` 的揭露與降級，形成第二條路徑 |
| (x3) 一併改 `meta()` 對外輸出 | 不在本 ADR。會改 API，另案處理 |

### 四、第一包各項

| 項目 | 處置 | 依據 |
|---|---|---|
| (i) 評估沿用 `run.loaded` | **保留，required** | Decision 7、8：(a′) 路徑，(乙) 修不到 |
| N190-I | **保留，required** | (乙) 解除 N-189(a) 的遮蔽 |
| (甲) 記號與 B-4 | **保留，收窄** | Decision 8、9 |
| B-2（`INDEX_DATA_GAP_NOTE` 併入 (甲)） | **保留，收窄；另寫 M1 記號** | Decision 9 第 3 點 |
| B-1 三句 | **移除，不實作** | Decision 10 |

## Decision（決策）

1. **可用判定（R6 的 ADR-0040 解讀）**：一份 snapshot（`MarketSnapshot` 或 `IndexSnapshot`）可以產生可執行指令，若且唯若：
   - (a) `source != DEMO_SOURCE`。可用來源集合就是現行 `is_usable` 的同一集合，不另立；而且
   - (b) `status in {"fresh", "backup"}`；或
   - (c) `status == "cached_stale"` 且 `is_within_ttl is True`。

   `is_within_ttl` 為 None 或 False、status 為 unavailable 或其他值時，一律不可用。CEO #108 的四項條件對應如下：
   - ①：(c) 的 status；
   - ②：(c) 的 ttl；
   - ③：(a)；
   - ④：與 ② 是資料層的同一個判定（Context 4），以 (d1) 實作，並由 QB-4 的契約測試釘住「② ⇒ ④」。
2. **位置與簽名**：
   - 唯一的定義是 `app/playbook/engine.py` 的 `is_usable(status: str, source: str, *, is_within_ttl: bool | None) -> bool`。keyword 必填、沒有預設值，所以呼叫點漏傳會直接報錯。
   - 原常數 `USABLE_DATA_STATUSES` 可以改名為 live 集合，engine.py:55-57 錯誤的前提註解要改寫。
   - 呼叫點共 7 個，都只加 `is_within_ttl=<snapshot>.is_within_ttl`：
     - engine.py:239（S3 未實現）、:263（M1）、:322（快市）、:1128（`index_usable`）、:1197（S/P／R）；
     - service.py:583（`same_day_warnings`）、:1272（rebalance）。
   - 不收 market、clock、旗標或 `RuleParams`。
3. **`is_within_ttl` 的傳遞路徑**（全程原樣傳遞，不得改寫或推導）：
   - 個股：`ProviderResult.is_within_ttl` → `LoadedBars.is_within_ttl`（services/market.py，既有）→ `LoadedSeries.is_within_ttl`（新，第五欄，預設 None；`NOTHING_LOADED` 不變；在 `_load_symbol_bars` 填入）→ `build_market_snapshot(..., is_within_ttl=...)` → `MarketSnapshot.is_within_ttl`（新，預設 None）→ `is_usable`。
   - 指數：`ProviderResult` → `IndexSeriesService` 原樣傳遞（既有）→ `LoadedBenchmark.is_within_ttl`（新，(x1)）→ `_load_index_bars` → `LoadedSeries` → `build_index_snapshot` → `IndexSnapshot.is_within_ttl`（新）→ `is_usable`。
   - 「最新交易日」**不另外傳遞**。它的判定只在資料層的 `judge()` 做一次，結果就是 `is_within_ttl`。`snapshot.data_date`（最後一根 bar）照舊，供字面與 (甲) 的鍵使用。之後若需要顯示「預期交易日」，必須由資料層提供（屬 ADR-0009 修訂），playbook 不得自己算。
   - snapshot 不序列化到 API，所以 `types.ts` 零 diff。
4. **指數（^TWII）也適用**：
   - 指數 ttl True 時：
     - M1 照常評估，防守可以翻轉；
     - 快市照常量測並 `save_fast_market`；
     - 排程日 `index_gap_defer` 不成立，R 不因指數順延。
   - `disclosed_status` 不變：TTL 內的快取仍然是 `cached_stale`，不升級成 backup（ADR-0005 I-3）。
   - 指數 ttl False 時（S1′-c）照舊不可用，M1 沿用前一狀態。
5. **其他呼叫點同步適用**：
   - S3 組合未實現（engine.py:239）；
   - rebalance（service.py:1272）：TTL 內的快取不再造成 `insufficient_data`；
   - `same_day_warnings`（service.py:583）。
   這三處用同一個 `is_usable`，不得另立例外。
6. **US ladder**：
   - 判定式與市場無關，`is_within_ttl` 由資料層依各市場的 policy 判定。
   - 本 ADR 只核定 TW（`PLAYBOOK_MARKET == "TW"`，service.py:86），以守門測試釘住。
   - 若改成 US，必須重開本 ADR，原因有三：
     - 冷卻 24 小時，CHECKED_RECENTLY 的窗口較長，(甲) 的路徑會更常出現；
     - 18:00 的 cutoff 未查證，過度宣稱的窗口約 2 小時（ADR-0009 D-2）；
     - 指數改用 ^GSPC。
   - 不得因為改市場而在 `is_usable` 加入 market 參數。
7. **第一包的處置**：
   - **(i) 保留**：`evaluate_today` 對 `run.loaded` 裡有的 symbol 一律沿用，不論狀態；沒有的才另外載入（N190-C2）。
     - 理由是 (a′) 路徑：結算那次載入時快取缺少預期交易日，於是打 live，但來源還沒有新的交易日（15:00 到公布前、未建模的休市日），回 FRESH；同一個請求的評估載入落在冷卻期內，變成 CHECKED_RECENTLY、ttl False，即使有 (乙) 仍然不可用。
     - qa (c) 的 8/13 屬於這個情況。
     - (i) 同時是 [M1] M1-3 第 2 點的前提。
   - **N190-I 保留**：(乙) 之後，有卡住的到期 S/P 列的標的會照常評估，次日會再出同批賣單（N-189(a)）。N190-I 是較早那一列上的揭露。N190-C4～C7 不變；「較晚 sell 列」不含 EMERGENCY（[風控-1105] B-3）。
   - **(甲)、B-4、B-2 保留，依 Decision 9 收窄。**
   - **B-1 移除**：依 Decision 10。
8. **「同一 data_date 稍早評估過、本次卻不可用」的路徑判定（[風控-1105] B-5 第 3 點）**：(乙) 之後仍然存在，所以 (甲) 不能取消。
   - P-1：15:00 之後、TWSE 公布之前。稍早（15:00 前，或 15:00 後第一次 live 回應）已用資料日 D 評估過；之後在冷卻期內讀快取，判為 CHECKED_RECENTLY、ttl False，資料日仍是 D。排程 15:10 的檢查會把 15:10～16:10 整段鎖住（[qa-1105] S1′-a）。其中「早上可用 → 下午不可用」是 (乙) 新造成的。
   - P-2：未建模的休市日。休市日 15:00 之後、以及次一平日 15:00 之前，預期交易日是休市日，永遠等不到。每個冷卻窗只有第一次 live 回應可用。
   - P-3：來源失敗（R-8）。預期交易日晚於 D，而且最近一次提問失敗，ttl 為 False。
   - P-4：稍早可用，本次 unavailable（快取被 ADR-0024 拒收，或列被刪）。這時沒有 snapshot，也沒有 data_date，(甲) 無從比對，保留原句，列為殘留 R-3。
   - 同一個請求內的 P-1、P-2，由 (i) 消除。
9. **(甲) 的收窄規格**（取代 N190-C8、C9 的觸發部分；其餘不變）：
   1. 記號表：新表（表名由 dev-lead 定），欄位為 `kind`、`subject`、`execution_date`、`data_date`、`created_at`。
      - 不設 UNIQUE、不設 PK 索引，避開 N172-C9 的疑義。
      - 在 `commit_evaluation` 的同一個 `BEGIN IMMEDIATE` 內，以「不存在才 INSERT」寫入；同一個鎖內先讀出「本次寫入前就已存在」的記號，經 `EvaluationCommit` 的加法欄位帶出。
      - `commit_evaluation` 加 keyword 參數 `marks=()`。
      - 持鎖期間零 I/O（ADR-0033 C-3）。不 DELETE。
   2. `kind="SP"`：該檔在 `book` 內有 batch，而且用同一個 `is_usable` 判為可用時寫入 (symbol, `evaluation.execution_date`, `snapshot.data_date`)。
   3. `kind="M1"`：只在 `index is not None`、`is_usable(index…)` 為真、`index.monthly_line is not None` 三者都成立時，寫入 ("^TWII", execution_date, `index.data_date`)。
      - 判定由 service 內的純函式 `m1_evaluated(index)` 做，並以表格測試證明它與 `_defense_transition` 的三個分支等價。
      - 不能用 `fast_market_measured_on` 推斷，原因有兩個：
        - `monthly_line is None` 時，快市照樣量測並寫入 measured_on（engine.py:268-272 對照 :322）；
        - measured_on 記的是本次評估的 data_date（service.py:1635），不是指數自己的資料日。
   4. 渲染條件（收窄，全部用結構化欄位判定）：本次 snapshot 存在，而且同時滿足：
      - `status == "cached_stale"`；
      - `is_within_ttl is not True`；
      - `source != DEMO_SOURCE`；
      - 存在 (kind, subject, execution_date, 本次 `snapshot.data_date`) 相同的既存記號。
      不成立時保留原句。
   5. SP 照 [風控-1105] B-4 的規則：
      - logged 中沒有該 symbol 屬於 `SETTLED_SINCE_RULE_IDS` 的 sell 列時，B-4 句取代 HOLDING 句的位置；
      - 順序：有 A 句時是變體 → A → B；只有 B 句時是變體 → B；
      - `if not orders and not decisions: continue` 不得讓 (甲) 被跳過；
      - 有 S/P sell 列時，保留 HOLDING 句加 A 句。
   6. M1 照 [風控-1105] B-2：只取代 `INDEX_DATA_GAP_NOTE` 的 status 分支，不取代 insufficient_data 分支。`FAST_MARKET_CARRIED_NOTE` 保留；`INDEX_DATA_GAP_DEFER_NOTE` 照現行過濾。
   7. 授權：本 ADR 授權 `GET /today` 新增記號寫入，補充 ADR-0039「GET /today 不新增寫入」這條限制（該限制原本只約束 ADR-0039 自己的範圍），也補充 ADR-0035 `commit_evaluation` 鎖內的內容。記號寫入不影響 K1、K2。
10. **B-1 移除與走不到的證明**：
    - B-1 的觸發條件是 `cached_stale` ∧ `is_within_ttl is True` ∧ 來源屬可用集合。依 Decision 1，這三項合起來就是 `is_usable` 為真。
    - engine 只在 `not is_usable` 時才產生 `DATA_GAP_NOTE`／`DATA_GAP_HOLDING_NOTE`（engine.py:1197-1207）與 `INDEX_DATA_GAP_NOTE` 的 status 分支（:263-266）。
    - 兩個條件互斥，所以 B-1 要替換的原句不會出現，B-1 走不到。
    - 因此三句都不實作；QB-13 用性質測試釘住這個互斥。
    - 這一點成立的前提是 Decision 11 的 release 閘門。
11. **交付單位與 release 閘門**：
    - P-A：(i) ＋ N190-I ＋ (甲)（SP、M1 記號）＋ B-2 ＋ B-4。
    - P-B：(乙)（Decision 1～6）。
    - 兩者必須在同一個 release。**P-B 不得單獨上線**，因為它會新增 P-1 的不實句。
    - P-A 若單獨上線，必須帶 B-1 三句（恢復 [風控-1105] B-1 的時程），並在 P-B 落地時移除。
    - 分支從最新的 product 開，**不得併入 N-168**。
12. **對 accepted ADR 的豁免與補充清單**：

| ADR／條文 | 性質 | 內容 |
|---|---|---|
| ADR-0035 N172-C3（engine.py 零 diff），以及 Decision 3、Consequences「engine 不改」 | **豁免（限定範圍）** | 只限 engine.py 內 `is_usable` 的定義（含上方常數與註解），以及 5 個呼叫點新增的引數。其餘一行都不准改（QB-1） |
| ADR-0034 C-B11（R、S、P 的 engine 邏輯不改） | **豁免（限定範圍）** | 同上。規則本身零改動；只有資料可用閘門改變，結果是被評估的情況變多 |
| ADR-0035 Decision 4、5，補充二（A、B 句），補充五 | 補充 | (甲) 變體的位置與順序依 Decision 9；`EvaluationCommit` 與 `commit_evaluation` 加法擴充 |
| ADR-0035 N172-C9 | 補充（無衝突） | 記號表不設 UNIQUE |
| ADR-0039 Decision 3、「GET /today 不新增寫入」 | 補充 | (i) 把 `run.loaded` 的沿用擴大到評估；記號寫入的授權 |
| ADR-0005 決策四、D-2、I-3、:324 | 補充（無衝突） | 新的 consumer 兩個欄位一起讀，符合 D-2；不新增 status、不改標；`LoadedBenchmark` 帶上欄位 |
| ADR-0009 D-4、D-5、D-2、S3-1 | 補充（無衝突） | 記錄 D-4 讓 playbook 的前提失效；採用 D-5 的語意；繼承 D-2 的過度宣稱窗口；S3-1 在降級路徑的缺口列為殘留 R-2 |
| ADR-0015 C1、C-4 | 補充（無衝突） | 一致：不把命中改標成 FRESH 或 BACKUP |
| ADR-0003 約束 7 | 補充（無衝突） | 指令列照實記 `cached_stale` |
| ADR-0010 D-4（公布後預熱） | 補充 | 預熱從此對 playbook 有益 |
| ADR-0033 C-3 | 無衝突 | 鎖內只有 DB 讀寫 |
| ADR-0004 | 無衝突 | 規則語意不變 |
| ADR-0036（保留中） | 不涉入 | N-189(a) 解除遮蔽之後，K3／N-176 的必要性提高，交 ADR-0036 |

13. **時序**：
    - N-168：分支已完成，待驗收與合併。N-190（P-A、P-B）另開獨立分支，不併入 N-168。
      - 誰先就緒誰先合。後合的一方 merge 最新 product（不 rebase），跑完整 CI 與 seam golden，由 qa-reviewer 審 merge commit 裡的衝突解法。
      - 衝突熱點：`evaluate_today` 的載入與回傳區塊、`same_day_warnings`、`wording.py`、`tests/golden/seam/approved/`、settlement warnings、`models.py`、`store.py` 的 `commit_evaluation`。
      - N-168 若對 engine.py 有任何 diff，PR 停下來送 TA（違反 C-B11）。
    - 整體順序：N-190（P-A ＋ P-B，同一個 release）→ N-177a → 第三包（N-188 ＋ N-189 的 D1、D2 ＋ W-B2LS 回審 ＋ B-3 的 EMERGENCY 反方向缺口），第三包緊接在 N-177 之後。第三包要等 N-168 合併。
    - **N-177a**：
      - (乙) 會讓被預載的持有標的再度每天重發 S2，也讓黑名單起算日跟著往後推（A-5）。[風控-1105] A-1 的內部通知已經涵蓋這個現象，必須在 N-190 部署前送達 CEO。
      - 建議 N-177a 在偵測結果出來後，與 N-190 同一個 release，或緊接其後。不以 N-177a 卡住 N-190，因為不上 N-190，這些標的連 S1 停損都不會評估。
      - [風控-1105] A-2 條件一的位置「緊接 N-190 第一包之後」，改讀為「緊接 N-190 這個 release 之後」，送風控確認。
    - **N-188、N-189 的頻率**（風控 [風控-1105] B-5 第 2 點已書面接受，期限是第三包緊接在 N-177 之後）：
      - N-188：依 [M1] M1-3，note 出現的總次數會從接近 0 回到正常水準，單一列被觸發的機率不變。前提是 (i) 已上線，本 ADR 讓這個前提成立。日後若回退 (i)，觸發會增加（方向是多觸發，字面仍為真），必須回 TA 與風控。
      - N-189(a)：遮蔽解除。每一次休市或開盤價晚到的事件，約多一張同批賣單；由 N190-I（較早列）與 D1（第三包）揭露。
      - N-189(b)／D2：重新載入時會真的重新評估，同日新的 K1 變多，頻率上升。
      - 建議第三包現在就並行開發，N-177a 一合併就接著合。
14. **[M1] M1-3 第 5 點的約束**（違反任何一條，就回 TA 與風控）：
    1. `list_batches()`（service.py:1616）不得移到載入序列之前。:1616 到 `commit_evaluation` 之間，不得加入取資料或任何網路 I/O。(甲) 記號的計算只能是純計算，寫入在鎖內。
    2. 不得新增任何改動 `playbook_batches` 股數或 cash 的路徑。
    3. 不得改 `_settle_pending` 取開盤價的方式；`_settle_pending` 零 diff。
    4. N-188 部署之後，ADR-0040 的 build 必須包含 N-188；不含 N-188 的 build 一律視為回滾，適用 [M1] M1-1 第 5 點的部署條件。
    - 前提：M1-3 第 2 點要求「第一包（沿用結算序列）已上線」。本 ADR 保留 (i)，而且與 (乙) 同一個 release，所以前提成立。
15. **禁止事項**：
    - runtime 旗標、環境變數、`RuleParams` 開關；
    - 改寫 `data_status`／`source`，或新增 `DataStatus`；
    - playbook 引用 `judge`、`expected_session`、`latest_completed_session`、`Verdict`、`policy_for` 或 `*_POLICY`；
    - engine.py 在 QB-1 以外的 diff；`app/data/**` 的任何 diff；
    - `Directive` 或 store 指令表新增欄位（不在 CEO 的範圍內）；
    - 實作 B-1 三句（Decision 11 的例外除外）；
    - (d4) 的額外條件；
    - 併入 N-168。

## Consequences（後果）

**好處**
- 停損主路徑恢復，不再取決於誰先載入：scheduler 預載、個股頁、訊號頁先載入，都不再遮蔽 S/P。
- M1、防守翻轉、快市恢復評估；R 不再因快取而順延、累計次數直到被跳過。
- rebalance 與 S3 恢復運作。
- 15:10 預載後，`/today` 通常不必再打 live。
- ADR-0035「停損時效不退步」重新成立。

**代價**
- engine 有限定範圍的 diff；`GET /today` 新增記號寫入；指令列上的 `cached_stale` 變多。

**殘留**（給風控與 CEO 看）
- R-1：ttl False 的窗口（P-1～P-3）仍然不產生指令。這符合 R6，因為資料確實少一個交易日。同一 data_date 的重新載入由 (甲) 揭露。
  - 「live 回應但沒有最新 bar 判為 fresh 可用，同一批 bar 從快取讀出卻不可用」的不對稱是既有的資料層語意，另案處理：devops-sre 查證 TWSE 公布時間與排程 15:10 的時點；data-engineer 與 TA 評估 cutoff 之後的冷卻（屬 ADR-0009 修訂）。
- R-2：降級路徑的 `is_within_ttl` 判定不含 S3-1 的正向證據（data/service.py:1004-1013）。13:30～15:00 之間，若來源全部失敗，而同市場已有別的序列取得 T 的 bar，T-1 的快取仍會判為 ttl True 而可用。頻率低。建議另開資料層小單（ADR-0009 修訂），由風控決定是否列為阻擋項。
- R-3：P-4（稍早可用、本次 unavailable）保留原句。
- R-4：在早上、或 13:30～15:00 評估時，依據的是 T-1 的資料，預定執行日是當天。若開盤後才看到，帳冊仍會以當天開盤價判定成交（R10）。
  - 這是既有的 first-touch 行為（ADR-0035「週三早上窗口」）。(乙) 讓它不再取決於誰先載入：前一晚沒開 `/today` 的日子都會出現。
  - 要風控裁示是否另立揭露或防護。
- R-5：指令帳冊的徽章（DirectiveLedger.tsx:69-76）傳入的 `isWithinTtl=null`，所以 `cached_stale` 列會顯示「快取資料…可能未含最近交易日」。方向是悲觀、有保留的說法，但列在 TTL 內時略有誤導。
  - 要讓 `Directive` 帶上 ttl，必須擴大範圍，另案處理。
  - 列入風控回審。
- R-6：qa 新現象 5（M1 defer 列顯示 fresh）是設計如此：指令列的狀態記的是該檔自己的 snapshot。
- R-7：TW 的公布時間未查證，過度宣稱窗口最多 30 分鐘（ADR-0009 D-2）。行為與 first-touch 相同。
- R-8：歷史不修復。N-190 期間未評估的停損日、累計過高的 R 順延次數、被跳過的批次都會保留。#106 的回溯檢查只列出這些項目；任何修復都由 CEO 逐項裁示，不做自動遷移。
- R-9：頭段是 demo、尾段是真實資料的混源序列，來源判定只看最後一列。這與現行 fresh 增量抓取的情況相同，不是新問題。
- R-10：P-1 落在排程日時，同一預定執行日稍早沒有 R 列的標的，仍可能被記一次 M1 順延（K2 的既有語意）。次數比現況少。
- R-11：記號表不刪資料，量級是「標的數 × 交易日」，很小。
- R-12：N-188、N-189、N-177 的 S2 重發、黑名單起算日，都隨著遮蔽解除而恢復發生，期限依 Decision 13。

## 待決

- **CEO 書面核可**：見回報的「需要 CEO 書面核可的事項」。
- **風控**：
  - 確認 B-1 移除（Decision 10、11）；
  - 確認 (甲) 收窄的條件（Decision 9）；
  - 確認 N-177a 的位置改讀（Decision 13）；
  - R-2 是否列為阻擋項；
  - R-4 的裁示；
  - 回審 R-5 的帳冊徽章、`DATA_GAP_*`（現在只剩過時、unavailable、demo 三種情況，「依鐵律⑤」的歸因是否已恢復為真）、A 句、`FAST_MARKET_*`；
  - 確認 rebalance 與 S3 同步適用（Decision 5）。
- **dev-lead**：依附錄 A、附錄 B 實作。
- **data-engineer**：另案處理三件事：
  - `interface.py:36` 過時的 docstring；
  - `LoadedBenchmark.meta()` 沒有輸出 ttl（屬 ADR-0005 D-2 的缺口）；
  - R-2。
- **devops-sre**：查證 TWSE 公布時間；把 Decision 11 的 release 閘門與 Decision 14 第 4 點列入 release-flow。

## 附錄 A：N190-QB 約束清單（qa-reviewer 列為 BLOCKING）

本清單取代 N190-C1、C11；保留 N190-C2～C7、C10。N190-C8、C9 依 QB-11 修訂。

- QB-1：`git diff <base>..HEAD -- app/playbook/engine.py` 只能出現兩類 hunk：
  - `is_usable` 的定義、其上方的常數與註解；
  - engine.py:239、:263、:322、:1128、:1197 這 5 處各加一個 `is_within_ttl=` 引數。
  其餘一律 BLOCKING。
- QB-2：
  - `app/data/**`、`app/services/market.py`、`app/api/**`、前端：零 diff；
  - `app/services/index.py`：只有 `LoadedBenchmark` 加欄位，以及 `load_market_benchmark` 兩個回傳分支的照抄；
  - `meta()` 零 diff。
- QB-3：`is_usable` 窮舉真值表測試，涵蓋：
  - status：fresh、backup、cached_stale、unavailable、未知值；
  - source：twse、yfinance、`demo_synthetic`、none；
  - ttl：True、False、None。
  結果必須符合 Decision 1。
- QB-4：單一實作，三部分：
  - (a) AST 或 grep 檢查：`app/playbook/**` 不引用 Decision 15 列出的符號；
  - (b) `is_within_ttl` 只從載入結果原樣傳遞；
  - (c) 資料層契約測試（只加測試）：用真實的 `MarketDataService` 與固定時鐘，涵蓋 layer 0、降級兩條路徑；凡是 `CACHED_STALE` 且 `is_within_ttl` 為 True，`max(bar.date) >= expected_session(policy_for(market), requested_end=end, now=clock())` 都成立。
- QB-5：不得有旗標。`is_usable` 的簽名逐字等於 Decision 2；不讀環境變數、設定或 `RuleParams`。
- QB-6：TTL 情境下，指令列的 `data_status == "cached_stale"`、`source` 照抄；`DataStatus` 仍然只有 4 個值。
- QB-7：附錄 B 的測試都在 repo 的 `tests/` 內，並且使用：
  - `tests/market_service_helpers.py` 的 `equity_service`、`index_service`；
  - tmp `PriceBarCache`、固定時鐘；
  - 真實的 `PlaybookService`、`PlaybookStore`；
  - 真實的 `scheduler.refresh_market_data`，以及 `get_bars`／`get_signals` 函式。
  不得用 `FakePriceService`。
- QB-8：三種負向情況（過時、unavailable、demo）每一種都有具名測試，個股與指數各一條：
  - 結果：不產生指令；`rules_fully_evaluated` 為 False；照舊產生缺漏句；指數沿用前一狀態，排程日順延。
  - 過時要涵蓋 CHECKED_RECENTLY 與 R-8 兩種。
  - demo 要涵蓋經 `app.demo` seed 產生的快取，以及合成的 `cached_stale`＋ttl True＋demo snapshot。
- QB-9：N190-C2，用呼叫次數測試釘住。
- QB-10：N190-C4～C7 不變。
- QB-11：(甲) 依 Decision 9：
  - 寫入與讀取在同一個鎖內；
  - 渲染條件逐項用結構化欄位判定；
  - 不得比對字串；
  - 記號表沒有 UNIQUE。
- QB-12：`m1_evaluated` 與 `_defense_transition` 三個分支等價的表格測試。
- QB-13：
  - `wording.py` 中，B-1 獨有的片段「資料層判定這份快取仍在有效期間內」出現 0 次（Decision 11 的例外除外）；
  - 性質測試：任意 `cached_stale`＋ttl True＋非 demo 的 snapshot，engine 都不會為它產生 `DATA_GAP_*` 或 `INDEX_DATA_GAP_NOTE` 的 status 分支。
- QB-14：PR 說明寫明 Decision 11 的 release 閘門；P-B 的 PR 必須以 P-A 已合併為前提。
- QB-15：`PLAYBOOK_MARKET == "TW"` 守門測試。
- QB-16：N190-C10。seam golden 的差異依 approved 逐條登記，不得重錄。
- QB-17：既有的 `cached_stale` 測試斷言不改，因為 ttl 為 None 時仍然不可用：
  - `test_playbook_acceptance.py` :506、:553、:567、:797、:804；
  - `test_playbook_same_day_anchors.py` :242-321；
  - ADR-0039 的 T15。
  若必須改，PR 停下來送 TA。
- QB-18：Decision 14 的四條；`_settle_pending` 零 diff。
- QB-19：rebalance：TTL 內的快取可以計算；ttl False 時為 `insufficient_data`。
- QB-20：分支不含 N-168 的 commit；合併規則依 Decision 13。

## 附錄 B：測試清單（全部依 QB-7）

- T1：[qa-1104] 的 (a)，到期列：評估沿用結算序列，batch 2 的 S1 照常評估。
- T2：(b2) 對照組重新載入：可用；沒有缺漏句，也沒有 A 句；`directives` 與第一次相同。
- T3：(c) 休市日連續 5 日，含休市當天 16:00：
  - 每日都有評估；
  - 卡住的列附 N190-I；
  - 沒有輪替現象。
- T4：S1（15:10 預載）：16:00 產生 S1，`data_status` 為 cached_stale。這是翻轉 N190-C11「scheduler 預熱」的具名測試，改為斷言通過。
- T5：S1-neg：不變。
- T6：S1′-a：不可用（負向，過時）。
  - 若早上已評估過，出 B-4；沒有則保留原句。
- T7：S1′-b：17:00 可用。
- T8：S1′-c：15:30 的行為釘住；16:15 的指數 ttl False，M1 不評估（負向）。
- T9：S2-bars、S2-signals：可用；M1 照常評估。
- T10：S3-R：不順延，計數為 0。另加一組現金充足的變體，證明 R1 確實會進場。
- T11：S3-def：防守開啟，S1 用 0.93 門檻。
- T12：S3-sector 的短、長、cold 三種窗口。
- T13：P-1：早上可用、15:30 ttl False、同一 data_date：
  - 出 B-4；
  - 有 S/P sell 列時出 HOLDING ＋ A；
  - 指數出 B-2；
  - 沒有記號時保留原句。
- T14：P-4：unavailable 時保留原句。
- T15：QB-3、QB-4、QB-8、QB-12、QB-13、QB-15、QB-19 的對應測試。
