# ADR-0040：stock-desk 排程台把「資料層判定已含最新交易日」的快取日線視為可用（R6 重新解讀；限定範圍豁免 N172-C3、C-B11）

- 狀態：accepted（CEO #110，2026-11-07 書面核可；範圍為本文加風控 [風控-0040] 條件，明文涵蓋 Decision 12「範圍延伸」一列與 Decision 5 的 TOTAL_DEPLOY 重算行為）
- 補充一（tech-architect 2026-11-07，回應 `work/reviews/2026-11-07-N190停止點QB17-dev-lead.md`）：ADR-0039 T15 的 QB-17 例外（E-1）、QB-20 事後查核的口徑（E-2）、`SETTLED_SINCE_RULE_IDS` 的定義者與對 N-188 的約束（E-3），以本檔末「補充一」節為準；本文不改。不擴大 CEO #110 的核可範圍；CEO 可推翻。
- 日期：2026-11-05（同日第一次修訂：併入 [風控-0040] C-1～C-10 與 N-168 合併後的時序，見文末「修訂紀錄」）
- 決策者：
  - tech-architect（草案、第一次修訂）
  - CEO #108（2026-11-05）：核可方向 (乙)，條件依風控 [風控-1105] B-5 選項 1。本文轉 accepted 另需 CEO 書面核可（見「待決」）
  - risk-compliance-officer：
    - R6 重新解讀的條件；N190-I、B-2、B-4 逐字定稿；
    - 2026-11-05 對本文 CONDITIONAL APPROVE（[風控-0040]）：C-1～C-4 為轉 accepted 前必須併入的條件（本版已併入）；C-5 三句、A-5(a) 通知、上線後更新通知逐字定稿。
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
  - [風控-0040] `2026-11-05-ADR0040與補充五修正一審查-風控.md`（C-1～C-10、A-1～A-9；C-5 三句與兩則 CEO 通知逐字）
  - [風控-N168] `2026-11-05-N168終審-風控.md`（T3 回審觸發條件）
  - [M1] `2026-11-05-ADR0035補充五修正一-tech-architect.md`（M1-3）
  - 實測腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n190/test_n190.py`、`test_n190_sched.py`。這是 session 暫存檔，不是永久檔，QB-7 要求移植進 repo。
- 程式位置：worktree bf03a9c 的快照。N-168 已於 2026-11-05 以 9253032 合入 product，行號可能位移，請以內容定位。全部是讀碼判定，未執行。
- 字面規則：本檔只寫識別名，不抄字面。
  - 產品內字面逐字以風控定稿為準，只放在 `wording.py`。
  - 給 CEO 的通知由 coordinator 從風控原檔逐字轉送，不進 repo 程式。

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
   - cache-only（:471-486，`get_cached_bars`；playbook 不使用：`load_bars`／`load_market_benchmark` 走 `get_daily_bars`）。
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

### 五、release 閘門的落實方式（[風控-0040] C-3）

| 方案 | 結論 |
|---|---|
| **(r1) P-A、P-B 在同一個 PR 內分組 commit，以 merge commit 或 squash 合入 product** | **採用**（與 r2 擇一） |
| **(r2) P-A、P-B 先各自合進 N-190 整合分支，再由整合分支一次 merge 進 product** | **採用**（與 r1 擇一） |
| (r3) P-A 先合進 product，P-A 本身帶 B-1 三句，P-B 落地時移除 | 只當例外 |
| (r4) P-A 先合進 product、不帶 B-1（原 QB-14） | 否決。product 上會出現違反 Decision 11 的可部署 commit |
| 以 rebase-and-merge 逐筆合入 | 否決。P-A 的 commit 會單獨出現在 product 的 first-parent 上，等同 r4 |

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

   **ttl 為 None 的路徑（[風控-0040] C-4）**：正式路徑上，送進 `is_usable` 的 `cached_stale` snapshot 必須帶非 None 的 `is_within_ttl`。
   - 為 None 時，判定仍是不可用（悲觀方向）。
   - 但缺漏句的「依鐵律⑤」歸因會再次成為誤歸因，也就是 N-190 靜默回來。
   - 由 QB-4(c)(d) 釘住。
2. **位置與簽名**：
   - 唯一的定義是 `app/playbook/engine.py` 的 `is_usable(status: str, source: str, *, is_within_ttl: bool | None) -> bool`。keyword 必填、沒有預設值，所以呼叫點漏傳會直接報錯。
   - 原常數 `USABLE_DATA_STATUSES` 可以改名為 live 集合，engine.py:55-57 錯誤的前提註解要改寫。
   - 呼叫點共 7 個，都只加 `is_within_ttl=<snapshot>.is_within_ttl`（行號以 bf03a9c 為準，合入 9253032 後依內容定位）：
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
5. **其他呼叫點同步適用**（[風控-0040] A-7 APPROVE）：
   - S3 組合未實現（engine.py:239）；
   - rebalance（service.py:1272）：TTL 內的快取不再造成 `insufficient_data`。公式不改，但 TOTAL_DEPLOY 的重算行為會改變（以前因快取而不算的日子，現在會算）。CEO 對本文的書面核可必須明文涵蓋這一點。
   - `same_day_warnings`（service.py:583）。
   這三處用同一個 `is_usable`，不得另立例外。[風控-1105] B-3「S3 若會產生 sell 列，PR 停下來送風控」維持。
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
9. **(甲) 的收窄規格**（取代 N190-C8、C9 的觸發部分；N190-C9「整句移除；稍早有指令列時 A 句照常出現」保留；其餘不變）：
   1. 記號表：新表（表名由 dev-lead 定），欄位為 `kind`、`subject`、`execution_date`、`data_date`、`created_at`。
      - 不設 UNIQUE、不設 PK 索引，避開 N172-C9 的疑義。
      - 在 `commit_evaluation` 的同一個 `BEGIN IMMEDIATE` 內，以「不存在才 INSERT」寫入；同一個鎖內先讀出「本次寫入前就已存在」的記號，經 `EvaluationCommit` 的加法欄位帶出。
      - `commit_evaluation` 加 keyword 參數 `marks=()`。
      - 持鎖期間零 I/O（ADR-0033 C-3）。不 DELETE。
   2. `kind="SP"`（[風控-0040] C-2）：只在 engine 該次**確實評估了這檔的 S/P** 時，寫入 (symbol, `evaluation.execution_date`, `snapshot.data_date`)。
      - 判定由 service 內的純函式 `sp_evaluated(symbol_batches, snapshot)` 做。三個條件同時成立才為真：
        - snapshot 存在；
        - 用同一個 `is_usable` 判為可用；
        - 該檔至少一個 batch 滿足 engine 的 S/P 批次閘門：`status == "open"`、`cost is not None`、`remaining_shares > 0`。
      - 這個閘門和 engine.py:420（`_evaluate_batch_exits`）同義，也和 S2 用的 `_symbol_average_cost`（engine.py:213）是同一個判斷條件。暫停、黑名單只影響 R（engine.py:1254），不影響 S/P。
      - `symbol_batches` 必須是同一次交給 engine 的那一份 batch 列表。
      - 結果：
        - 只有 planned 批次、沒有持股，或只有 cost 為 NULL 的 open 批次時，沒有 SP 記號；
        - 未持有的標的沒有 SP 記號，保留原 `DATA_GAP_NOTE`；有 A 句時照常加 A 句（N-172a 解讀點 (c)）；
        - cost 為 NULL 的 open 批次會讓 engine.py:1203 判為持有、渲染 HOLDING 句，但因為沒有記號，HOLDING 句保留原句。
      - 等價性由 QB-12 的表格測試釘住。
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
      不成立時保留原句（之後依 Decision 16 第 1 點，由 C-5 變體接手）。
   5. SP 的句子組合（[風控-1105] B-4；[風控-0040] C-1）。下面的「S/P sell 列」指 logged 中該 symbol、rule_id 屬於 `SETTLED_SINCE_RULE_IDS` 的 sell 列：
      - 記號存在、**沒有** S/P sell 列：B-4 句取代 HOLDING 句的位置。順序：有 A 句時是 B-4 → A → B；只有 B 句時是 B-4 → B。
      - 記號存在、**有** S/P sell 列：**HOLDING 句不渲染**（N190-C9），A 句照常出現，B 句接在 A 之後；不渲染 B-4。
      - 記號不存在：保留原 HOLDING 句。
      - `if not orders and not decisions: continue` 不得讓 (甲) 被跳過。
      - 句子的定位與替換用結構化欄位，不比對字串（QB-11）。
   6. M1 照 [風控-1105] B-2：只取代 `INDEX_DATA_GAP_NOTE` 的 status 分支，不取代 insufficient_data 分支。`FAST_MARKET_CARRIED_NOTE` 保留；`INDEX_DATA_GAP_DEFER_NOTE` 照現行過濾。
   7. 授權：本 ADR 授權 `GET /today` 新增記號寫入，補充 ADR-0039「GET /today 不新增寫入」這條限制（該限制原本只約束 ADR-0039 自己的範圍），也補充 ADR-0035 `commit_evaluation` 鎖內的內容。記號寫入不影響 K1、K2。
10. **B-1 移除與走不到的證明**（[風控-0040] A-1 APPROVE）：
    - B-1 的觸發條件是 `cached_stale` ∧ `is_within_ttl is True` ∧ 來源屬可用集合。依 Decision 1，這三項合起來就是 `is_usable` 為真。
    - engine 只在 `not is_usable` 時才產生 `DATA_GAP_NOTE`／`DATA_GAP_HOLDING_NOTE`（engine.py:1197-1207）與 `INDEX_DATA_GAP_NOTE` 的 status 分支（:263-266）。
    - 兩個條件互斥，所以 B-1 要替換的原句不會出現，B-1 走不到。
    - 因此三句都不實作；QB-13 用性質測試釘住這個互斥。
    - 這一點成立的前提是 Decision 11 的 release 閘門。
11. **交付單位與 release 閘門**（[風控-0040] C-3）：
    - P-A：(i) ＋ N190-I ＋ (甲)（SP、M1 記號）＋ B-2 ＋ B-4。
    - P-B：(乙)（Decision 1～6）。
    - **不變式**：product 的 first-parent 歷史上，不得存在「含 P-A、不含 P-B、也不含 B-1 三句」的 commit。
    - **合入方式**：P-A 與 P-B 以**同一次 merge** 進 product，二選一：
      - (r1) 同一個 PR 內分組 commit（P-A 在前、P-B 在後），以 merge commit 或 squash 合入；
      - (r2) 先各自合進 N-190 整合分支，再由整合分支一次 merge 進 product。
      - 兩種都**不得**用 rebase-and-merge。
    - **例外**：P-A 必須先合時，P-A 本身要帶 B-1 三句（恢復 [風控-1105] B-1 的時程）；P-B 的 PR 移除這三句。
    - **回滾**：
      - 不得只回滾 P-B 而保留 P-A，除非同一個回滾 commit 補回 B-1 三句；
      - P-A 與 P-B 一起回滾時，另受 Decision 14 第 4 點約束。
    - devops-sre 把不變式、合入方式、回滾規則列入 release-flow。
12. **對 accepted ADR 的豁免與補充清單**：

| ADR／條文 | 性質 | 內容 |
|---|---|---|
| ADR-0035 N172-C3（engine.py 零 diff），以及 Decision 3、Consequences「engine 不改」 | **豁免（限定範圍）** | 只限 engine.py 內 `is_usable` 的定義（含上方常數與註解），以及 5 個呼叫點新增的引數。其餘一行都不准改（QB-1） |
| ADR-0034 C-B11（R、S、P 的 engine 邏輯不改） | **豁免（限定範圍）** | 同上。規則本身零改動；只有資料可用閘門改變，結果是被評估的情況變多 |
| CEO #108「只限 `is_usable` 與 snapshot／`LoadedSeries` 的欄位」 | **範圍延伸（待 CEO 書面明文核可）** | `services/index.py` 的 `LoadedBenchmark` 加同一個欄位（QB-2 釘住）；service.py 的 `same_day_warnings`、rebalance 兩個呼叫點一併適用。風控判為可接受的延伸（[風控-0040] A-8），但只有 CEO 能正式延伸 |
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
    - **N-168：已於 2026-11-05 以 9253032 合入 product，狀態 done。** 原本「誰先就緒誰先合」的問題已經定案：N-168 先合，N-190 是後合的一方。
      - N-190 分支（或 (r2) 的整合分支）若從 9253032 之前的 product 開出，合入 product 前必須 merge 最新的 product（不 rebase），跑完整 CI 與 seam golden，由 qa-reviewer 審 merge commit 裡的衝突解法。
      - 衝突熱點：`evaluate_today` 的載入與回傳區塊、`same_day_warnings`、`wording.py`、`tests/golden/seam/approved/`、settlement warnings、`models.py`、`store.py` 的 `commit_evaluation`。
      - QB-1 的 `<base>` 是 N-190 最後一次 merge 進來的 product commit，所以 N-168 的改動不計入 QB-1。
      - 事後查核（取代原「N-168 若對 engine.py 有 diff 就停下」）：qa-reviewer 在 N-190 PR 審查時，確認 `git diff 9253032^1 9253032 -- app/playbook/engine.py` 為空。不為空時送 TA 判斷是否違反 C-B11。
      - N-190 必須在 N-168 之後的**下一個** release 上線。否則觸發 [風控-N168] T3(a)，W-B3「會照常評估」送回風控。
    - 整體順序：N-190（P-A ＋ P-B，同一次 merge、同一個 release）→ N-177a → 第三包。
      - 第三包內容：N-188 ＋ N-189 的 D1、D2 ＋ W-B2LS 回審 ＋ B-3 的 EMERGENCY 反方向缺口。
      - 第三包緊接在 N-177 之後；它原本的前提「N-168 合併」已經滿足。
    - **N-177a**（[風控-0040] A-3 APPROVE 位置改讀）：
      - (乙) 會讓被預載的持有標的再度每天重發 S2，也讓黑名單起算日跟著往後推（A-5）。[風控-1105] A-1 的內部通知已經涵蓋這個現象。
      - **A-1 送達是 N-190 部署的必要條件**：coordinator 必須書面確認 A-1 通知已送達 CEO，並附送達日期。
      - [風控-1105] A-2 條件一的位置改讀為「緊接 N-190 這個 release 之後」，風控已確認。「緊接」的定義：N-190 release 之後的**下一個** release 必須含 N-177a，中間不得夾其他功能 release（hotfix 除外）。
      - N-177a 若沒趕上，(c) 依 A-2 條件一回復為 required；同時觸發 [風控-N168] T3(b)。偵測閘門不變。
      - 不以 N-177a 卡住 N-190，因為不上 N-190，這些標的連 S1 停損都不會評估。
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
    - `Directive` 或 store 指令表新增欄位（不在 CEO 的範圍內；另案見 Decision 16 第 4 點）；
    - 實作 B-1 三句（Decision 11 的例外與回滾規則除外）；
    - (d4) 的額外條件；
    - P-A 不帶 B-1 而先於 P-B 進入 product 的 first-parent；以 rebase-and-merge 合入 P-A／P-B；只回滾 P-B 而不補回 B-1；
    - 以 rebase 吸收最新 product（含 N-168），只能用 merge；
    - 前端從 `data_status` 或「這列存在」推斷 ttl，或把傳給徽章的 `isWithinTtl` 寫死為 true（[風控-0040] A-6 R-5 條件）。
16. **後續單與期限（[風控-0040] C-5～C-10；都不擋 N-190 的 P-A／P-B，各自只受期限約束；編號對照見「修訂紀錄」）**：
    1. **C-5：缺漏句的 ttl 變體**（dev-lead，期限第三包）。
       - 問題：同一頁上，可執行的指令列記 `cached_stale`，另一檔的缺漏句又寫「資料狀態為 cached_stale…依鐵律⑤當日不產生指令」。組合起來有誤導空間。
       - 字面：三個變體句，識別名暫稱 C5-持有、C5-未持有、C5-指數。逐字從 [風控-0040] A-6「C-5 三句逐字定稿」抽取，用程式比對。常數名由 dev-lead 定，只放在 `wording.py`。
       - 觸發（全部用結構化欄位）：本次 snapshot 存在，`status == "cached_stale"`、`is_within_ttl is not True`、`source != DEMO_SOURCE`，而且 (甲)／B-4／B-2 都不成立。
       - 優先順序：(甲) > C-5 變體 > 原句。
       - 實作：在 service 整句替換、佔原句的位置，不比對字串。
         - C5-持有取代 `DATA_GAP_HOLDING_NOTE`，C5-未持有取代 `DATA_GAP_NOTE`；兩者的選擇用和 engine.py:1203-1205 同義的持有判斷條件（純函式加表格測試）。
         - C5-指數只取代 `INDEX_DATA_GAP_NOTE` 的 status 分支，不取代 `insufficient_data` 分支。
         - 只限 `/today` 的評估路徑；原常數不改；engine 零 diff。
       - 三句不含 B-1 獨有片段，不影響 QB-13。
    2. **C-6：R-4 的產品內防護**（TA 提案，P1，期限第三包）。
       - 內容：「評估時點已晚於預定執行日開盤」的結構化揭露。
       - 開盤時刻（VS-2）尚未查證，而且 playbook 不得自行計算交易日（Decision 15），所以判定來源要由資料層提供，屬 ADR-0009 修訂。
       - 字面由 creative-lead 擬稿，送風控定稿。可能涉及 CEO 範圍時，先送 CEO。
    3. **C-7：R-2 的資料層小單**（data-engineer，P2）：
       - 任何改動 `is_within_ttl` 語意的 diff，都要回 TA 與風控；
       - QB-4(c) 的契約測試不得刪除或弱化。
    4. **C-8：R-5 帳冊徽章**（風控暫行接受）：
       - 前端約束由 QB-21 釘住，常態適用，不限於 N-190；
       - 讓 `Directive` 帶 ttl 屬於 Decision 15 禁止的範圍，另開單送 CEO 核可範圍，期限隨 C-5。
    5. **C-9：R-10 修正**（TA 提案，期限第三包）。
       - 問題：P-1 落在排程日、M1 記號已存在時，新寫入的順延列帶 `INDEX_GAP_DEFER_NOTE`，「M1 今日未評估」為假，而且會累計順延次數。
       - 修正若涉及 engine 或 K2，要另出 ADR 送 CEO 核可。
    6. **C-10：部署前後的 CEO 通知**（coordinator）：
       - 部署前必須完成：
         - A-1 送達的書面確認，附送達日期（Decision 13）；
         - R-4 操作事實通知送達 CEO。識別名「A5a 操作事實通知」，逐字見 [風控-0040] A-5(a)。
       - 部署完成當日：送出「上線後更新通知」，取代先前的 B-5 範圍補充句。識別名「上線後更新通知」，逐字見 [風控-0040]「送 CEO 時要一併說明的事項」第 9 點。

## Consequences（後果）

**好處**
- 停損主路徑恢復，不再取決於誰先載入：scheduler 預載、個股頁、訊號頁先載入，都不再遮蔽 S/P。
- M1、防守翻轉、快市恢復評估；R 不再因快取而順延、累計次數直到被跳過。
- rebalance 與 S3 恢復運作。
- 15:10 預載後，`/today` 通常不必再打 live。
- ADR-0035「停損時效不退步」重新成立。

**代價**
- engine 有限定範圍的 diff；`GET /today` 新增記號寫入；指令列上的 `cached_stale` 變多。
- rebalance 的 TOTAL_DEPLOY 重算行為改變（Decision 5）。
- release 必須是 P-A 與 P-B 同一次 merge；分開上線要多做 B-1 三句再移除。
- 部署多了兩個前置條件（A-1 送達確認、A5a 通知），部署當日要送更新通知。

**殘留**（風控已逐項裁示，[風控-0040]）
- R-1：ttl False 的窗口（P-1～P-3）仍然不產生指令。這符合 R6，因為資料確實少一個交易日。同一 data_date 的重新載入由 (甲) 揭露。
  - 「live 回應但沒有最新 bar 判為 fresh 可用，同一批 bar 從快取讀出卻不可用」的不對稱是既有的資料層語意，另案處理：devops-sre 查證 TWSE 公布時間與排程 15:10 的時點；data-engineer 與 TA 評估 cutoff 之後的冷卻（屬 ADR-0009 修訂）。
- R-2：降級路徑的 `is_within_ttl` 判定不含 S3-1 的正向證據（data/service.py:1004-1013）。13:30～15:00 之間，若來源全部失敗，而同市場已有別的序列取得 T 的 bar，T-1 的快取仍會判為 ttl True 而可用。
  - 風控：**不列為阻擋項**。理由是頻率低、`data_reason` 會寫入指令列並在帳冊顯示，錯誤方向和 first-touch 相同。
  - 條件見 Decision 16 第 3 點（C-7）。
- R-3：P-4（稍早可用、本次 unavailable）保留原句。風控接受。
- R-4：在早上、或 13:30～15:00 評估時，依據的是 T-1 的資料，預定執行日是當天。若開盤後才看到，帳冊仍會以當天開盤價判定成交（R10）。
  - 這是既有的 first-touch 行為（ADR-0035「週三早上窗口」）。(乙) 讓它不再取決於誰先載入：前一晚沒開 `/today` 的日子都會出現。
  - 風控：不擋 N-190，但會造成帳冊與實際持股持久分歧，不能只記為殘留。處理分兩段：
    - 部署前送 CEO 的 A5a 操作事實通知（C-10）；
    - 產品內防護（C-6）。
- R-5：指令帳冊的徽章（DirectiveLedger.tsx:69-76）傳入的 `isWithinTtl=null`，所以 `cached_stale` 列會顯示「快取資料…可能未含最近交易日」。
  - 風控：**暫行接受**，字面為真。
  - 條件見 Decision 16 第 4 點（C-8）與 QB-21。
- R-6：qa 新現象 5（M1 defer 列顯示 fresh）是設計如此：指令列的狀態記的是該檔自己的 snapshot。風控接受。
- R-7：TW 的公布時間未查證，過度宣稱窗口最多 30 分鐘（ADR-0009 D-2）。行為與 first-touch 相同。風控接受。
- R-8：歷史不修復。N-190 期間未評估的停損日、累計過高的 R 順延次數、被跳過的批次都會保留。#106 的回溯檢查只列出這些項目；任何修復都由 CEO 逐項裁示，不做自動遷移。
- R-9：頭段是 demo、尾段是真實資料的混源序列，來源判定只看最後一列。這與現行 fresh 增量抓取的情況相同，不是新問題。風控接受。
- R-10：P-1 落在排程日、M1 記號已存在時，同一預定執行日稍早沒有 R 列的標的，仍可能被記一次 M1 順延（K2 的既有語意）。
  - 新寫入的順延列帶 `INDEX_GAP_DEFER_NOTE`，「M1 今日未評估」在這種情況下為假，而且會計次。
  - 風控：**暫行接受**（方向是少買、次數比現況少）。修正見 Decision 16 第 5 點（C-9）。
- R-11：記號表不刪資料，量級是「標的數 × 交易日」，很小。風控接受。
- R-12：N-188、N-189、N-177 的 S2 重發、黑名單起算日，都隨著遮蔽解除而恢復發生，期限依 Decision 13。
- R-13：C-5 上線前（第三包），同頁「可執行列記 `cached_stale`」與「缺漏句寫 cached_stale 不產生指令」並存，組合起來有誤導空間；每句單獨看都為真。

## 待決

- **CEO 書面核可**：見回報的「CEO 書面核可的最終事項清單」。
  - 核可範圍是本文加上 [風控-0040] 的條件。
  - 必須明文列出 Decision 12 的「範圍延伸」一列，以及 Decision 5 的 TOTAL_DEPLOY 重算行為。
- **風控**：
  - C-1～C-4 已併入，依 [風控-0040] 不必再審一輪；
  - 只需確認「修訂紀錄」中 C-6～C-10 的編號對照。
- **coordinator**：
  - Decision 16 第 6 點（C-10）的兩項部署前條件與部署當日通知；
  - 開單：C-5（dev-lead）、C-6（TA）、C-7（data-engineer）、C-8 的 Directive ttl 範圍（送 CEO）、C-9（TA）。
- **dev-lead**：依附錄 A、附錄 B 實作；合入方式依 Decision 11。
- **data-engineer**：另案處理三件事：
  - `interface.py:36` 過時的 docstring；
  - `LoadedBenchmark.meta()` 沒有輸出 ttl（屬 ADR-0005 D-2 的缺口）；
  - R-2（C-7，P2）。
- **devops-sre**：
  - 查證 TWSE 公布時間與開盤時刻（VS-2，C-6 的前提）；
  - 把 Decision 11 的不變式、合入方式、回滾規則，以及 Decision 14 第 4 點列入 release-flow。

## 附錄 A：N190-QB 約束清單（qa-reviewer 列為 BLOCKING）

本清單取代 N190-C1、C11；保留 N190-C2～C7、C10。N190-C8、C9 的觸發部分依 QB-11 修訂；N190-C9「整句移除；稍早有指令列時 A 句照常出現」保留。

- QB-1：`git diff <base>..HEAD -- app/playbook/engine.py` 只能出現兩類 hunk，其餘一律 BLOCKING：
  - `is_usable` 的定義、其上方的常數與註解；
  - engine.py:239、:263、:322、:1128、:1197 這 5 處各加一個 `is_within_ttl=` 引數。
  - `<base>` 是 N-190 最後一次 merge 進來的 product commit（Decision 13）。
- QB-2：
  - `app/data/**`、`app/services/market.py`、`app/api/**`、前端：零 diff；
  - `app/services/index.py`：只有 `LoadedBenchmark` 加欄位，以及 `load_market_benchmark` 兩個回傳分支的照抄；
  - `meta()` 零 diff。
- QB-3：`is_usable` 窮舉真值表測試，結果必須符合 Decision 1。涵蓋：
  - status：fresh、backup、cached_stale、unavailable、未知值；
  - source：twse、yfinance、`demo_synthetic`、none；
  - ttl：True、False、None。
- QB-4：單一實作，四部分：
  - (a) AST 或 grep 檢查：`app/playbook/**` 不引用 Decision 15 列出的符號；
  - (b) `is_within_ttl` 只從載入結果原樣傳遞；
  - (c) 資料層契約測試（只加測試）：
    - 用真實的 `MarketDataService` 與固定時鐘；
    - 涵蓋 Context 4 的**三個出口**：layer 0、降級、cache-only（`get_cached_bars`）；
    - 斷言：凡是 `CACHED_STALE` 且 `is_within_ttl` 為 True，`max(bar.date) >= expected_session(policy_for(market), requested_end=end, now=clock())` 都成立。
    - 這組測試不得刪除或弱化（C-7）。
  - (d) T1～T14 的整合情境另外斷言：凡是送進 `is_usable` 的 `cached_stale` snapshot，`is_within_ttl is not None`。以測試內的 spy 包住 `is_usable` 記錄引數，不改產品碼（C-4）。
- QB-5：不得有旗標。`is_usable` 的簽名逐字等於 Decision 2；不讀環境變數、設定或 `RuleParams`。
- QB-6：TTL 情境下，指令列的 `data_status == "cached_stale"`、`source` 照抄；`DataStatus` 仍然只有 4 個值。
- QB-7：附錄 B 的測試都在 repo 的 `tests/` 內，不得用 `FakePriceService`。必須使用：
  - `tests/market_service_helpers.py` 的 `equity_service`、`index_service`；
  - tmp `PriceBarCache`、固定時鐘；
  - 真實的 `PlaybookService`、`PlaybookStore`；
  - 真實的 `scheduler.refresh_market_data`，以及 `get_bars`／`get_signals` 函式。
- QB-8：三種負向情況（過時、unavailable、demo）每一種都有具名測試，個股與指數各一條：
  - 結果：不產生指令；`rules_fully_evaluated` 為 False；照舊產生缺漏句；指數沿用前一狀態，排程日順延。
  - 過時要涵蓋 CHECKED_RECENTLY 與 R-8 兩種。
  - demo 要涵蓋經 `app.demo` seed 產生的快取，以及合成的 `cached_stale`＋ttl True＋demo snapshot。
- QB-9：N190-C2，用呼叫次數測試釘住。
- QB-10：N190-C4～C7 不變。
- QB-11：(甲) 依 Decision 9：
  - 寫入與讀取在同一個鎖內；
  - 渲染條件逐項用結構化欄位判定；
  - 句子組合依 Decision 9 第 5 點：記號存在且有 S/P sell 列時，HOLDING 句不出現、B-4 不出現、A 句出現、B 句在 A 之後；
  - 不得比對字串；
  - 記號表沒有 UNIQUE。
- QB-12：兩組等價表格測試：
  - `m1_evaluated` 與 `_defense_transition` 三個分支等價；
  - `sp_evaluated` 與 engine 的 S/P 閘門等價（engine.py:420 與 :213 的判斷條件），表格至少涵蓋：
    - 只有 planned；
    - open 但 `remaining_shares == 0`；
    - open 但 cost 為 NULL；
    - 合格 open 批次加暫停；
    - 合格 open 批次加黑名單；
    - S2 觸發；
    - 不可用 snapshot；
    - snapshot 為 None。
- QB-13：
  - `wording.py` 中，B-1 獨有的片段「資料層判定這份快取仍在有效期間內」出現 0 次（Decision 11 的例外與回滾規則除外）；
  - 性質測試：任意 `cached_stale`＋ttl True＋非 demo 的 snapshot，engine 都不會為它產生 `DATA_GAP_*` 或 `INDEX_DATA_GAP_NOTE` 的 status 分支。
- QB-14：release 閘門（Decision 11）：
  - PR 說明寫明 Decision 11 的不變式與所採的合入方式（r1 或 r2）；
  - 合入後，product first-parent 上 P-A 與 P-B 由同一個 merge commit（或同一個 squash commit）帶入；不得用 rebase-and-merge；
  - 若走例外（P-A 先合）：P-A 的 diff 內 `wording.py` 含 B-1 三句，P-B 的 diff 移除；
  - 任何只 revert P-B 的回滾 PR，必須在同一個 commit 補回 B-1 三句，否則 BLOCKING。
- QB-15：`PLAYBOOK_MARKET == "TW"` 守門測試。
- QB-16：N190-C10。seam golden 的差異依 approved 逐條登記，不得重錄。
- QB-17：既有的 `cached_stale` 測試斷言不改，因為 ttl 為 None 時仍然不可用。若必須改，PR 停下來送 TA。涵蓋：
  - `test_playbook_acceptance.py` :506、:553、:567、:797、:804；
  - `test_playbook_same_day_anchors.py` :242-321；
  - ADR-0039 的 T15。
- QB-18：Decision 14 的四條；`_settle_pending` 零 diff。
- QB-19：rebalance：TTL 內的快取可以計算；ttl False 時為 `insufficient_data`。
- QB-20：N-168 合併後的整合（Decision 13）：
  - N-190 分支（或整合分支）合入 product 前，已 merge 含 9253032 的最新 product，方式是 merge、不得 rebase；
  - merge commit 的衝突解法經 qa-reviewer 審過；
  - merge 之後重跑完整 CI 與 seam golden，全綠；
  - 確認 `git diff 9253032^1 9253032 -- app/playbook/engine.py` 為空，不為空時送 TA。
- QB-21：前端徽章 ttl（C-8；常態適用，任何改到前端的 PR 都要檢查）：
  - 傳給 `DataMetaStatusBadge` 的 `isWithinTtl`，在指令帳冊路徑上不得為 `true` 字面；
  - 不得由 `data_status` 或「這列存在」推導；
  - 在 Directive 帶 ttl 的另案經 CEO 核可前，維持 `null`。

## 附錄 B：測試清單（全部依 QB-7；T1～T14 另加 QB-4(d) 的斷言）

- T1：[qa-1104] 的 (a)，到期列：評估沿用結算序列，batch 2 的 S1 照常評估。
- T2：(b2) 對照組重新載入：可用；沒有缺漏句，也沒有 A 句；`directives` 與第一次相同。
- T3：(c) 休市日連續 5 日，含休市當天 16:00：
  - 每日都有評估；
  - 卡住的列附 N190-I；
  - 沒有輪替現象。
- T4：S1（15:10 預載）：16:00 產生 S1，`data_status` 為 cached_stale。這是翻轉 N190-C11「scheduler 預熱」的具名測試，改為斷言通過。
- T5：S1-neg：不變。
- T6：S1′-a：不可用（負向，過時）。
  - 若早上已評估過這檔的 S/P（`sp_evaluated` 為真），出 B-4；沒有則保留原句。
- T7：S1′-b：17:00 可用。
- T8：S1′-c：15:30 的行為釘住；16:15 的指數 ttl False，M1 不評估（負向）。
- T9：S2-bars、S2-signals：可用；M1 照常評估。
- T10：S3-R：不順延，計數為 0。另加一組現金充足的變體，證明 R1 確實會進場。
- T11：S3-def：防守開啟，S1 用 0.93 門檻。
- T12：S3-sector 的短、長、cold 三種窗口。
- T13：P-1：早上可用、15:30 ttl False、同一 data_date：
  - 沒有 S/P sell 列時出 B-4；
  - 有 S/P sell 列時，HOLDING 句不出現、B-4 不出現、A 句出現、B 句接在 A 之後；
  - 只有 planned 批次、或只有 cost 為 NULL 的 open 批次時，沒有 SP 記號，保留原句；
  - 指數出 B-2；
  - 沒有記號時保留原句。
- T14：P-4：unavailable 時保留原句。
- T15：QB-3、QB-4（含 (c) 的三個出口與 (d) 的 spy 斷言）、QB-8、QB-12、QB-13、QB-14、QB-15、QB-19、QB-21 的對應測試或檢查。

## 修訂紀錄

### 2026-11-05 第一次修訂（tech-architect；依 [風控-0040] 與 N-168 合併）

C-1～C-5 的編號出自 [風控-0040] 本文。C-6～C-10 在 [風控-0040] 中只以「C-5～C-10」的範圍寫法出現，沒有逐項命名；下表的 C-6～C-10 對照是 TA 依該檔「下一步」第 1 點的開單順序**暫定**，待風控確認。條文依內容撰寫，編號若需調整，不影響條文。

| 項目 | 內容（出處） | 改動位置 |
|---|---|---|
| C-1 | HOLDING 句的一致性：記號存在且有 S/P sell 列時，HOLDING 不渲染（N190-C9），A 照常，B 接在 A 後（A-2） | Decision 9 前言、第 5 點；QB-11；T13；附錄 A 前言 |
| C-2 | SP 記號條件改為 engine 確實評估了 S/P，以 `sp_evaluated` 判定並做等價表格測試（A-2） | Decision 9 第 2 點；QB-12；T6；T13 |
| C-3 | release 閘門漏洞：同一次 merge、P-A 先合須帶 B-1、不得只回滾 P-B（A-1） | Options 五；Decision 11；Decision 15；QB-13；QB-14 |
| C-4 | ttl 為 None 的路徑：契約測試涵蓋三個出口；整合情境斷言 ttl 不為 None（A-6） | Context 4（補 cache-only 出口名稱）；Decision 1 末段；QB-4(c)(d)；附錄 B 前言、T15 |
| C-5 | 缺漏句 ttl 變體三句，期限第三包（A-6「C-5 三句逐字定稿」） | Decision 16 第 1 點；殘留 R-13 |
| C-6（暫定） | R-4 產品內防護，TA 提案，P1，期限第三包（A-5(b)） | Decision 16 第 2 點；殘留 R-4；待決 |
| C-7（暫定） | R-2 不列阻擋項；資料層小單 P2；改 ttl 語意回 TA 與風控；QB-4(c) 不得弱化（A-4） | Decision 16 第 3 點；QB-4(c)；殘留 R-2 |
| C-8（暫定） | R-5 暫行接受；前端不得推斷或寫死 ttl；Directive 帶 ttl 另案送 CEO（A-6） | Decision 15；Decision 16 第 4 點；QB-21；殘留 R-5 |
| C-9（暫定） | R-10 暫行接受，TA 修正提案期限第三包（「其他殘留」） | Decision 16 第 5 點；殘留 R-10 |
| C-10（暫定） | A5a 操作事實通知部署前送達；A-1 送達書面確認；部署當日更新通知（A-5(a)、A-3、「送 CEO 事項」第 5、9 點） | Decision 13；Decision 16 第 6 點；Consequences 代價 |
| 其他：A-3 | N-177a「緊接」的定義、沒趕上時回復 required | Decision 13 |
| 其他：A-7 | rebalance 的 TOTAL_DEPLOY 重算行為要 CEO 明文涵蓋；B-3 的 S3 sell 停下規則維持 | Decision 5；Consequences 代價 |
| 其他：A-8 | 範圍延伸要 CEO 明文核可 | Decision 12 新增一列；待決 |
| 其他：殘留裁示 | R-3、R-6、R-7、R-9、R-11 接受；R-8 由 CEO；R-12 依期限 | Consequences 殘留 |
| 其他：N-168 已合併 | N-168 已於 2026-11-05 以 9253032 合入 product；N-190 改為後合方，用 merge 吸收；QB-1 base 定義；事後查核 engine diff；[風控-N168] T3(a)(b) | 標頭「程式位置」；Decision 2；Decision 13；Decision 15；QB-1；QB-20 |

不在本 ADR 的範圍：[風控-0040] 的 M-1、M-2 屬 ADR-0035 補充五修正一，另行併入該文件。

### 2026-11-07 補充（coordinator 依風控確認加註，原文不改）

- 風控 `work/reviews/2026-11-07-N177實作規格審查與C6至C10確認-風控.md` B 節：確認上表 C-6～C-10 的對照，以該裁示為這組編號的正式定義，上表「暫定」「待風控確認」字樣由本補充取代。
- 風控澄清句（逐字）：「C-10 的兩項部署前條件是 N-190 部署的必要條件（Decision 13）；『不擋 P-A／P-B』只指開發與合併。」

## 補充一：N-190 實作停止點的裁示（2026-11-07）

- 日期：2026-11-07
- 決策者：tech-architect。依據：QB-17「若必須改，PR 停下來送 TA」、Decision 13「不為空時送 TA 判斷」。兩處都授權 TA 裁示，本補充只記錄裁示結果。
- 來源：`work/reviews/2026-11-07-N190停止點QB17-dev-lead.md`
- 性質：補充本文，不改本文。標「取代」或「改為」的地方，以本補充為準。不擴大 CEO #110 的核可範圍，不改任何產品行為與字面。CEO 可推翻。
- 程式位置：`fix/stock-desk-n190-usable-cache` 分支 086c223 的快照，以內容定位。全部是讀碼判定，未執行。
- 用語：本 ADR 附錄 B 也有一條「T15」。為避免混淆，下文把 ADR-0039 附錄 B 的 T15 記為 39-T15，也就是 `tests/test_playbook_pending_exit_block.py::test_t15_classification_follows_the_series_the_settlement_judged_n1_on`。

### E-1 39-T15 與 Decision 7 (i) 的衝突（QB-17 的例外）

1. 判定：
   - 39-T15 要守的不變式是 ADR-0039 Decision 3／N171-C2″：authored 路徑上，`/today` 區塊的分類用的是同一次請求 `_settle_pending` 載入的序列（`run.loaded`），所以與 N1 一致（風控 P-1）。
   - `assert len(prices.calls) >= 2` 不是這個不變式，而是測試的前提檢查：確認情境裡「第二次載入」真的存在，分類才分得出用的是哪一份序列。它描述的是 (i) 之前 `evaluate_today` 會重新載入的實作細節，也就是 ADR-0039 Options 二 (ii) 的前提。
   - (i) 之後：
     - 能被判為不涵蓋的列，一定是到期列（`execution_date <= as_of`），它們的 symbol 一定在 `run.loaded`，評估沿用同一個物件；
     - 未到期的列，在任何序列上都由 `exit_line_still_covers` 判為仍涵蓋。
     - 因此同一請求內「結算與評估看到不同序列」已經無法構造。產品層的不變式由 ADR-0039 Decision 3 與本 ADR 的 (i) 兩道機制同時保證，比原先強。
   - 但只把前提翻成 `== 1`，39-T15 會變成 QB-9 的重複，失去「證明用的是結算那一份」的能力：`evaluate_today` 把評估的 `loaded` 誤接給 `_pending_exit_lines` 時，在 (i) 下結果相同，測試抓不到；(i) 日後若回退，這個誤接就會變成實際錯誤。

2. 准改範圍：只限 39-T15 這個測試函式，加上 `_ShiftingPrices` 的 docstring。QB-17 對其他測試照舊。
   - (a) `assert len(prices.calls) >= 2` 改為 `assert len(prices.calls) == 1`。旁註寫明：自 ADR-0040 Decision 7 (i) 起，結算與評估從構造上就是同一份序列。
   - (b) 原第 698 行註解改寫成與 (a) 相符的敘述。
   - (c) 新增接線斷言：
     - 用 monkeypatch 包住 `book.service._settle_pending`，取得回傳的 `run`；
     - 包住 `service_module._pending_exit_lines`，記錄 `loaded` 引數；
     - 斷言 `_pending_exit_lines` 恰好被呼叫一次，而且 `loaded is run.loaded`。必須用 `is`，不得用 `==`。
   - (d) 新增前提斷言：`run.loaded["2330"].bars` 的日期不含 WEDNESDAY。這是 N1b 的前提，原本只寫在註解裡。
   - (e) 原第 700～703 行的四條斷言逐字不改。`_ShiftingPrices` 的程式不改；docstring 可以補一句：「(i) 之後，同一請求內不會要求第二次回答；保留作為回退 (i) 時的絆線。」
   - (f) 不得把 39-T15 移到 `tests/n190_helpers.py`，也不得換成其他 fake。fixture 零 diff。39-T15 不屬本 ADR 附錄 B，QB-7 不適用於它。

3. 回退：日後若回退 (i)（依 Decision 13 必須回 TA 與風控），(a) 恢復為 `>= 2`，(c)(d) 保留。

4. 不需要的事項：產品碼 diff；修改 ADR-0039 v2 本文或其補充一；重錄 golden；風控回審（字面、行為都不變，不變式只變強）。

5. 檢查（qa-reviewer，BLOCKING）：
   - `tests/test_playbook_pending_exit_block.py` 的 diff，hunk 只落在 39-T15 函式內與 `_ShiftingPrices` 的 docstring；
   - 原第 700～703 行的四條斷言逐字存在；
   - (c) 用 `is`，並斷言呼叫次數恰好為 1；
   - PR 說明引用本節。

### E-2 QB-20 事後查核的口徑（修正 Decision 13 的「事後查核」與 QB-20 第 4 小點）

1. 判定：9253032 對 `app/playbook/engine.py` 的 diff，是在 `_snapshot_rows` 的 `BatchSnapshot(...)` 呼叫內，新增 2 行註解加 1 行 `entry_before_exit_on=batch.entry_before_exit_on,`。這**不違反** ADR-0034 C-B11。理由：
   - ADR-0034 C-B8 及其補充一 S-3 第 3 點明文要求 `BatchSnapshot` 帶出標示，engine 只照抄 `BatchState`。這 3 行就是該授權的實作。
   - C-B11 管的是 R、S、P 的判斷邏輯。這個欄位在 engine.py 只出現在這一處，不被任何條件讀取。W-B2、W-B2L 由 service 渲染，engine 不設定。
   - C-B8 與 C-B11 同屬 ADR-0034 附錄 C。把 C-B11 讀成禁止 C-B8，清單就會自相矛盾。
   - 原本寫「為空」，是本 ADR 起草時漏算 C-B8，錯在條文，不是 N-168 越界。

2. QB-20 第 4 小點改為：
   「確認 `git diff 9253032^1 9253032 -- app/playbook/engine.py` 只含 ADR-0034 C-B8 授權的照抄 hunk，也就是以下四項全部成立：
   - (a) 每個 hunk 都落在 `_snapshot_rows` 的 `BatchSnapshot(...)` 呼叫內；
   - (b) 新增行只有 `entry_before_exit_on=batch.entry_before_exit_on,` 與 `#` 註解行；刪除行為 0；
   - (c) 在 9253032 與 N-190 的 HEAD 上，engine.py 中 `entry_before_exit_on` 恰好出現 1 次（即上述 kwarg），`entry_before_exit_label`、`entry_before_exit_note`、`exit_stamped_on` 都出現 0 次；
   - (d) 這個 kwarg 的值是 `batch.entry_before_exit_on` 原樣，不經任何運算或條件。
   任一項不成立時，送 TA 判斷是否違反 C-B11。」

3. Decision 13「事後查核」一句改讀為：「qa-reviewer 在 N-190 PR 審查時，依補充一 E-2 第 2 點確認 9253032 對 engine.py 的 diff 只含 C-B8 照抄。」

4. QB-1 的 `<base>` 定義不變。N-168 的 hunk 本來就不計入 QB-1，本節不影響 QB-1。

### E-3 `SETTLED_SINCE_RULE_IDS` 的定義者（補充 Decision 9 第 5 點、N190-I；對 N-188 有約束）

1. 確認：
   - N-190 在 `app/playbook/store.py` 定義唯一一份 `SETTLED_SINCE_RULE_IDS: tuple[str, ...] = ("S1", "S2", "P1", "P2", "P3")`。值與順序等於 ADR-0035 補充五 X-1 第 1 點，與補充五修正一不衝突。
   - 位置理由：store 是唯一兩邊都能引用的模組。service（N190-I、本 ADR 的 (甲)）引用 store；N-188 的 `_read_settled_since` 在 store 內；store 不得 import wording（N172-C7）。
   - 定義者比照修正一 M1-2 第 1 點「先合者定義、後合者引用」：N-190 先合，由 N-190 定義。
   - 修正一 M1-1 條件 A 的運維探針依規定不 import app，所以必須寫字面。這不算第二份定義，由 N188-T20（[風控-0040] M-1）斷言探針 SQL 的 rule_id 字面等於本常數。

2. 對 N-188 的約束（併入 QB-18 檢查）：
   - 必須引用 `app.playbook.store.SETTLED_SINCE_RULE_IDS`。
   - `app/**` 內不得再定義第二份，也不得另寫這五個 rule_id 的 tuple、set 或 SQL `IN (...)` 字面。SQL 的 placeholders 由本常數產生。
   - 補充五 X-6 第 5 點與 QB-18.6 所稱的 `SETTLED_SINCE_*`，指 `wording.py` 的字面常數（`SETTLED_SINCE_SYMBOL_NOTE`、`SETTLED_SINCE_BATCH_NOTE` 及其組成常數），**不含** `SETTLED_SINCE_RULE_IDS`。QB-18.6 的 AST 或 grep 檢查必須排除這個名稱，不得因它定義在 store.py、或在 service 被引用而判為 BLOCKING。

3. 增減 rule_id 屬於補充五 X-1 的修訂，要回 TA 與風控。這會同時影響 N190-I、(甲)／B-4 的「S/P sell 列」、N-188，以及條件 A 的探針。

4. 檢查（qa-reviewer，BLOCKING）：
   - `app/**` 內 `SETTLED_SINCE_RULE_IDS =` 的指派恰好 1 次，在 `app/playbook/store.py`；
   - `app/**` 內沒有其他恰好由這五個 rule_id 組成的字面集合；
   - `scripts/n172_duplicate_probe.py` 屬 N-172 的既有分類，不在範圍內。
