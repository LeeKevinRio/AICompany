# ADR-0035 補充四（切面規格）與 N-171 評估、ADR-0039 草稿

- 審查者：tech-architect
- 日期：2026-11-03
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：ADR-0035 補充四（切面規格）與 N-171 評估、ADR-0039 草稿

## 一、本次結論

兩份文字都寫好了，可以直接貼：A 是 ADR-0035 補充四，B 是 ADR-0039（proposed）。

**1. 補充四（切面規格）**
- 切面以單獨一個 PR 合併。分支 `feat/stock-desk-today-seam-n182` 送 PR 時，head 只能含切面 commit。N-182 會改行為和字面，要另開 PR。
- 和 11-01 的條件相比有 10 處出入（見下方對照表），主要四點：
  - 切面多帶 `DirectiveLine.entry_before_exit_note`、`LabeledBatch`／`labeled_batches`，以及 `_settle_pending`。
  - `_lines` 的 `labeled_batches` 改成 keyword-only、必填。
  - rebase 改成 merge。
  - 「不改切面形狀」改寫成「固定項／擁有項」：允許各分支加自己的加法欄位。
- 這些都還在 CEO #102「只動結構、不改行為」的範圍內，我判斷不需要 CEO 重新裁示。

**2. PM 指出的三點，全部確認**
- **N171-C2 已過時：確認。** 覆蓋判定在判準 Z 之後的唯一來源，是 `exit_line_still_covers` 本身。
- **unauthored 路徑以空序列呼叫會全部判為涵蓋：確認，並細化。** 預定執行日不早於今天（`execution_date >= as_of`）的列，結果和有 K 線時相同；會誤判的只有預定執行日已過（`< as_of`）的列，這些改標「無法分類」。
- **我的設計解決不了「結算後才重送、走到 EMPTY」：確認。** 改由群組 B 處理。

**3. N-171 的主要技術決定**
- 欄位：群組 A 依分類分成三個清單（仍涵蓋／已不涵蓋／無法分類），加一組區塊層級的句子。
- 判準 Z 用的 K 線：用**結算自己載入的那一份序列**，經切面的 `_settle_pending` 取得。這樣同一份回應裡，結算區掛 N1 的列和「已不涵蓋」清單必然一致。
- 每一列都列出，不去重。批數、股數放在後端渲染的句子裡，股數取批次的剩餘股數，不翻倍。
- PRD 的 FR-3「一批一行」我沒有採為 API 形狀，送風控 F-8 決定。

**4. 群組 B：可同包，不建議拆案**
- 資料已經在 R16 日誌裡（`settled=1`、`settled_at`、`settled_open_price`）。讀取時計算即可，不新增任何狀態，也不寫入。
- 規模約群組 A 的四成，難點在字面，不在程式。
- B 分兩段：
  - B1：結算後的常駐清單，在 A 合併之後做。
  - B2：EMPTY 支的附加句。要等 N-168 合併，因為兩者都改出清鎖內的讀取。

**5. 需要 CEO 裁示一題**：保留期的起算日（見第四段）。

## 二、各部門回報

### tech-architect（本人，唯讀）

**PRD T-1～T-9 答覆**（詳見 ADR-0039 附錄 C）

| 題 | 答覆 |
|---|---|
| T-1 | 共用的是覆蓋判定本身（`exit_line_still_covers`）。`evaluate_today` 的第二次載入（`service.py:1154`）用同一個載入器、同一個視窗，但和結算判 N1 用的不是同一份；載入一次成功、一次失敗時，同一份回應會自相矛盾。所以改用結算自己的 `loaded`（切面 S-2.4）。 |
| T-2 | 三個清單：`pending_exit_directives`、`stale_exit_directives`、`unclassified_exit_directives`，加 `pending_exit_notes`。分類由「列在哪個清單」表達，前端不做判斷。 |
| T-3 | 寫一個純函式 `classify_exit_line(bars=None)`：預定執行日不早於今天的判為涵蓋；早於今天的判為無法分類。unauthored 照舊不載入 K 線。空序列呼叫標 VETO。 |
| T-4 | 確認排除：`_read_logged` 排除 `UNKEYED_RULE_IDS`（`store.py:236`、`:427-438`）。目前只有常數層的測試，要補一條端到端守門測試（N171-T3）。 |
| T-5 | 見 ADR-0039 Decision 10。保留期由純函式 `settled_exit_retained` 判定：`as_of <= calendar.shift(settled_on, 20)`。不存狀態，沒有關閉機制。 |
| T-6 | 一律經 `_lines(..., labeled_batches=evaluation.labeled_batches)` 建立。我把 W-B2L 的套用範圍擴大到另兩個清單，待風控確認。 |
| T-7 | 可以實作，但 API 改成逐列、不去重。「一批一行」若被風控選中，再以加法欄位補上。 |
| T-8 | 單一讀取點 `read_in_flight()`：一個 DEFERRED transaction，只有 SELECT，和 N-168 的清單讀同一個快照。 |
| T-9 | NB-6 面板屬於出清畫面包，目前不在 product 工作樹裡（grep 不到 `EXIT_RESULT_UNCONFIRMED_RETRY` 的前端鏡射）。改字時，常數、前端鏡射、逐字守門與字面絆線測試要放在同一個 commit。 |

**補充四與 11-01 條件（`work/reviews/2026-11-01-ADR0034補充一-tech-architect.md`「P1」1～5）的出入**

| # | 11-01 條件 | 補充四 | 性質 |
|---|---|---|---|
| 1 | 三個預設 `[]` 欄位 | 同上，另加 `DirectiveLine.entry_before_exit_note`、`LabeledBatch`、`labeled_batches`、`types.ts` 對應宣告 | 增加 |
| 2 | 同一個 conn、同一個快照的單一讀取點 | 具名為 `read_in_flight`；DEFERRED `BEGIN…COMMIT`；兩個 stub；**unauthored 路徑也要呼叫一次** | 精確化，並擴及 unauthored |
| 3 | `_lines(directives, labeled_batches)`，傳空集合 | keyword-only、必填，型別 `Sequence[LabeledBatch]`，傳 `()` | 型別改變。W-B2L 有 `{entry_date}`，只用集合裝不下 |
| 4 | 無 | `_settle_pending`／`SettlementRun` | 新增。N-168 的 W-B3 和 N-171 都要碰這個函式 |
| 5 | 切面之後不改切面形狀 | 分成固定項與擁有項，允許加法欄位 | 放寬並明確化 |
| 6 | 後合者 rebase 之後重跑 CI | 後合者 `git merge origin/product/stock-desk`，在 merge 後的 head 跑完整 CI | 依公司規則修正 |
| 7 | qa 實查同一讀取點 | 擴充為 QB-1～QB-9 | 擴充 |
| 8 | 任一條件不成立就回原順序 | 定義何謂「原順序」，判準 R-1～R-5，另列「不構成回退」的情況 | 精確化 |
| 9 | 無 | 切面 PR 不得夾帶 N-182 | 新增 |
| 10 | 無 | N-171 其餘欄位（stale／unclassified／notes／B）歸 N-171 擁有，不放進切面 | 說明 |

**應經手但尚未經手**
- risk-compliance-officer：見第四段的風控清單，字面全部未定稿。
- CEO：保留期起算日，以及 ADR-0039 由 proposed 轉 accepted 的核可。
- dev-lead：依 A 調整切面 PR，目前在本機只看到分支剛建立。
- product-manager：PRD 要改版成 v0.2，至少涵蓋這幾條：
  - FR-3 與 AC-N171-5 的「一批一行」改為逐列；
  - AC-N171-11 依 T-3 細化；
  - M2 的不變式改用三個清單的聯集。

其他部門（art-lead、frontend-engineer、data-engineer、devops-sre、qa-*、tech-writer 等）：本次未參與（純評估）。

### A：ADR-0035 補充四（檔頭行與全文）

```
- 補充四（tech-architect 2026-11-03，回應 CEO #102）：Decision 12 中 N-171 與 N-168 的實作順序，在切面以單獨 PR 先合併的前提下改為可並行；切面規格（欄位、單一讀取點 `read_in_flight`、`_settle_pending`、`_lines` helper、`types.ts`、守門測試）、合併順序（不 rebase，後合者 merge 最新 product 並在 merge 後的 head 重跑完整 CI）、回到原順序的判準與 qa-reviewer BLOCKING 項，以補充四為準；N172-C8 對 `settle_pending` 的限制視為 N-172a 的範圍約束，補充四 S-2.4 的零行為結構搬移不構成衝突。全文見 `work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md`「A」節；本檔原文不改（比照補充一～三先例，CEO 可推翻改為另立取代 ADR）。

# ADR-0035 補充四：Decision 12 的並行條件與 `/today` 切面規格

- 日期：2026-11-03
- 決策者：tech-architect（規格）；CEO #102（2026-11-03，放行並行，前提為切面先合）
- 性質：補充 ADR-0035 Decision 12，不取代；ADR-0035 原文不改。細化 ADR-0034 補充一 S-3 第 4、6、8 點與 S-4 的實作面，不改其語意。
- 依據：`work/reviews/2026-11-01-ADR0034補充一-tech-architect.md`「P1：並行實作的條件」1～5；決策包 #102；ADR-0039（N-171，proposed）。
- 程式位置是 2026-11-03 工作樹 `product/stock-desk` 的快照（切面尚未落地），會漂移，請以內容定位。

## S-1 Decision 12 的變更
1. N-171 與 N-168 的**實作**改為可並行，前提是 S-2 的切面已以單獨 PR 合進 `product/stock-desk`。其餘排序不變。
2. **合併**仍逐一進行（S-5）。N-168 另受 ADR-0034 補充一 S-4 第 2 點的 UI 閘門約束；本補充不放寬該閘門。
3. Decision 12 的原理由（兩案都在 `evaluate_today` 結算之後讀取、碰同一個函式）由切面吸收：共用面一次定形，之後各自只改自己擁有的部分（S-3）。
4. S-6 任一判準成立，即回到原順序。CEO #102 已預先授權此回退，不需重新裁示。

## S-2 切面規格（一個 PR，只動結構）

### 2.1 範圍
- 只動：`backend/app/api/playbook.py`、`backend/app/playbook/models.py`、`backend/app/playbook/service.py`、`backend/app/playbook/store.py`、`frontend/app/lib/types.ts`，以及新增的測試檔。
- 零 diff：`wording.py`、`engine.py`、`_MIGRATIONS`／`_init_schema`、所有前端元件、所有既有字面。
- 不改行為：
  - 既有 API 欄位的值、DB 寫入、K 線載入的次數與參數都不變；
  - 新增的 JSON 鍵一律為 `[]` 或 `null`。

### 2.2 欄位
(a) `TodayResponse`（api）與 `PlaybookEvaluation`（models）各加三個欄位，預設為空：
- `pending_exit_directives`：N-171（ADR-0039 Decision 1）。
- `entry_before_exit_directives`：N-168 的 W-B1 類（ADR-0034 補充一 S-3 第 6 點）。
- `entry_before_exit_blocked_directives`：N-168 的 G1 擋下類。
- 型別：api 為 `list[DirectiveLine]`，models 為 `list[Directive]`。

(b) `DirectiveLine` 加 `entry_before_exit_note: str | None = None`（ADR-0034 補充一 S-3 第 4 點）。切面中恆為 None。

(c) `models.py` 新增 `LabeledBatch`：
- frozen；欄位 `symbol: str`、`batch_no: int`、`entry_date: date`；
- 表示帶 W-B2 標示的批次；`entry_date` 供 W-B2L 的 `{entry_date}` 使用。
- `PlaybookEvaluation` 與 `EmergencyExitResult` 各加 `labeled_batches: tuple[LabeledBatch, ...] = ()`。切面中恆為空。

(d) `types.ts`：
- `PlaybookDirectiveLine` 加 `entry_before_exit_note?: string | null`；
- `PlaybookTodayResponse` 加 (a) 的三個欄位，型別 `PlaybookDirectiveLine[]`，**宣告為 optional**，缺鍵一律視為 `[]`；
- 註解寫明擁有者與 ADR 條號。

### 2.3 單一讀取點
(a) `PlaybookStore.read_in_flight() -> InFlightRead`：
- 開一個 connection，執行 `BEGIN`（DEFERRED，不取寫鎖）；
- 依序呼叫 `_read_pending_exits(conn)`、`_read_entry_before_exit(conn)`，然後 `COMMIT`；
- 例外處理照 C-11：`in_transaction` 時才 ROLLBACK，然後原樣 raise；
- 兩者在同一個 read transaction 內，讀到同一個快照；
- 只允許 SELECT。

(b) `InFlightRead(NamedTuple)` 只有兩個欄位：
- `exits: PendingExitRead`（N-171 擁有）；
- `entries: EntryBeforeExitRead`（N-168 擁有）。
- 切面中兩個 `_read_*` stub 回傳空值，不執行任何 SELECT。

(c) 呼叫時點：
- authored 路徑：在 `_settle_pending` 之後、`list_batches()` 之前，呼叫一次；
- unauthored 路徑：在 `_unauthored_evaluation` 內呼叫一次，照舊不結算、不載入；
- 每次 `evaluate_today` 恰好呼叫一次。

(d) service 的兩個 stub：
- `_pending_exit_lines(...)` 回傳 `[]`（N-171 擁有）；
- `_entry_before_exit_lines(...)` 回傳 `([], [])`（N-168 擁有）；
- 結果寫入 2.2(a) 的欄位。

### 2.4 `_settle_pending`
- 新增 `PlaybookService._settle_pending(as_of) -> SettlementRun`。`SettlementRun(NamedTuple)` 有兩個欄位：
  - `result: SettlementResult`；
  - `loaded: Mapping[str, LoadedSeries]`：結算本身載入的序列；沒有待結算列時為空。
- `settle_pending()` 的簽名與回傳不變，內容改為 `return self._settle_pending(as_of).result`。
- `evaluate_today` 改呼叫 `_settle_pending`，並把 `run.loaded` 傳給 N-171 的 stub。
- 理由：
  - ADR-0039 Decision 3 要求判準 Z 的分類，用結算判 N1 時的同一份序列；
  - N-168 的 W-B3 也要改這個函式的 warnings。
- N172-C8 是 N-172a 的範圍約束（比照 ADR-0035 對 0033 C-10 的判定）。本項是零行為差異的結構搬移，不構成衝突。

### 2.5 `_lines` helper
- 簽名：`_lines(directives: Sequence[Directive], *, labeled_batches: Sequence[LabeledBatch]) -> list[DirectiveLine]`。
  - `labeled_batches` 為 keyword-only、必填、無預設值。
- 切面中，body 一律設 `entry_before_exit_note=None`。套用規則（ADR-0034 補充一 S-3 第 4 點）由 N-168 實作。
- 呼叫點：
  - `/today` 的 `directives` 與 2.2(a) 的三個清單：`labeled_batches=evaluation.labeled_batches`；
  - 出清回應的 `directives`、`pending_directives`：`labeled_batches=result.labeled_batches`；
  - rebalance：`labeled_batches=()`。
- `app/` 內，`DirectiveLine(` 只准出現在 `_lines` 裡。

## S-3 擁有權
**固定項**：後續任何 PR 都不得改名、改型別、改簽名、改呼叫次數。
1. 2.2 的三個欄位、`entry_before_exit_note`、`LabeledBatch`、`labeled_batches`；
2. `read_in_flight`、`InFlightRead` 的兩個欄位、單一 transaction、每次 evaluate 只呼叫一次；
3. `_settle_pending`／`SettlementRun`；
4. `_lines` 的簽名，以及它是唯一的建構點；
5. 2.2(d) 的 `types.ts` 宣告。

**擁有項**：由擁有者自行修改。
- N-171：`PendingExitRead`、`_read_pending_exits`、`_pending_exit_lines` 的內容與簽名；ADR-0039 新增的欄位。
- N-168：`EntryBeforeExitRead`、`_read_entry_before_exit`、`_entry_before_exit_lines`；`_lines` 內的套用規則；`labeled_batches` 的取值；ADR-0034 補充一列出的其他欄位與 migration。

**允許**：任一方新增自己的加法欄位。相鄰行的文字衝突在 merge 時解決，不構成回退。

## S-4 守門測試（隨切面 PR 落地，之後常駐）
- SEAM-T1：authored、unauthored、出清後三種情境：
  - `/today` 都有 2.2(a) 的三個鍵，值為 `[]`；
  - `directives` 每一列的 `entry_before_exit_note` 為 null；
  - 出清回應的 `directives`、`pending_directives` 也一樣。
- SEAM-T2：同上情境，回應去掉新鍵之後與切面前的期望值相同。既有測試的斷言只准因「新增鍵」而改；這類改動要在 PR 內逐條列出。
- SEAM-T3：用 spy 證明 `read_in_flight` 每次 `evaluate_today` 恰好呼叫一次（兩條路徑都要測）；authored 路徑上的呼叫在 `_settle_pending` 之後。
- SEAM-T4：用 `set_trace_callback` 證明 `read_in_flight` 期間只有 `BEGIN`、SELECT、`COMMIT`。N-171、N-168 填入查詢之後，這條測試仍須通過。
- SEAM-T5：AST 掃描 `app/`，`DirectiveLine(` 只出現在 `_lines` 內；`_lines` 的 `labeled_batches` 是 KEYWORD_ONLY 且沒有預設值。
- SEAM-T6：`settle_pending(today=d)` 等於 `_settle_pending(d).result`；`POST /settle` 的既有測試不改斷言。
- SEAM-T7：unauthored 零痕跡的既有測試（不載入、不結算、不寫入）不改斷言。
- SEAM-T8：前端 typecheck 與 test 綠燈；用缺新鍵的舊回應 fixture 渲染排程台，不出錯。

## S-5 合併順序與 CI
1. 切面以單獨 PR 合併。分支 `feat/stock-desk-today-seam-n182` 送 PR 時，head 只含切面 commit。N-182 從含切面的 product 另開 PR。
2. 順序：切面 → N-182 → {N-171-A、N-168} 並行實作、逐一合併 → N-171-B1 → N-171-B2（ADR-0039 Decision 11）。N-171-A 與 N-168 誰先過自己的閘門，誰就先合。
3. 不 rebase。後合併的一方要做到：
   - 在自己的分支執行 `git merge origin/product/stock-desk`，逐檔處理衝突，並在 PR 說明；
   - 在 merge 之後的 head 上，重跑 `.github/workflows/stock-desk.yml` 的全部 job 並全綠：
     - backend：ruff check、ruff format --check、mypy、pytest（覆蓋率 ≥ 90）；
     - compose；
     - frontend：typecheck、test、build；
   - qa-reviewer（含 Codex 第二意見）重審 merge commit 的衝突處理，並重查 S-7；
   - product 若在此期間又前進，重做以上步驟。
4. N-182 若先於 N-168 合併，ADR-0034 補充一 S-1 第 3 點要求的「G1 擋下類」單一來源，就由 N-182 建立；N-168 必須引用它。

## S-6 回到原順序的判準
**原順序**：N-171-A 先合併。在那之前，N-168 不再修改下列部分：
- S-3 的固定項；
- `evaluate_today`、`_settle_pending`、`_to_response`。

N-168 只做非共用部分：migration、`settle()` 的 C-B6、wording、出清鎖內的戳記。N-171-A 合併之後，N-168 merge product 再繼續。

**回退判準**，任一條成立即回退：
- R-1：切面 PR 尚未合併，或已被 revert，而某一方需要改共用面。
- R-2：qa-reviewer 判定切面 PR 有行為差異，且無法在該 PR 內消除。
- R-3：後續某個 PR 必須改 S-3 固定項才能完成。這時該 PR 停住，由 tech-architect 出補充修正規格。
- R-4：在 `/today` 路徑上，於 `read_in_flight` 之外讀取在途資料，或在 `_lines` 之外建構 `DirectiveLine`，且未在該 PR 內修正。
- R-5：後合者 merge product 時，衝突落在 S-3 固定項上。

**判定流程**：qa-reviewer 在審查中提出；coordinator 記入追蹤清單並通知 dev-lead。不需要 CEO 重新裁示。

**不構成回退**：
- N-171 因字面或 NB-6 回審延後；
- N-168 因 UI 閘門延後；
- 非固定項的文字衝突。

## S-7 qa-reviewer BLOCKING 檢查項
**切面 PR**：
- QB-1：diff 只在 2.1 允許的檔案內；`wording.py`、`engine.py`、`_MIGRATIONS` 零 diff。
- QB-2：SEAM-T1～T8 存在且全綠；既有斷言的每一處改動，都可以歸因到新增鍵。
- QB-3：不含 N-182，也不含任何 N-171／N-168 的行為。
- QB-4：CI 全綠。

**N-182、N-171、N-168 的每一個 PR**：
- QB-5：分支從含切面的 product 長出；已 merge 最新 product；CI 在 merge 之後的 head 上全綠。
- QB-6：S-3 固定項零 diff。
- QB-7：實查 N-171 與 N-168 的清單出自同一次 `read_in_flight`。在 `evaluate_today` 的呼叫鏈上，沒有第二個在途讀取點：
  - grep `_read_exit_state`、戳記欄位、`pending_directives(` 的使用處。
- QB-8：SEAM-T4、T5 仍然綠燈。
- QB-9：N-168 另查 ADR-0034 補充一 S-4 第 2 點；N-171 另查 ADR-0039 附錄 A 的 BLOCKING 項。

## S-8 與 2026-11-01 條件的差異
- 增加：`entry_before_exit_note`、`LabeledBatch`／`labeled_batches`、`_settle_pending`。
- 單一讀取點擴及 unauthored 路徑。
- `_lines` 的參數改為 keyword-only、必填，型別改為 `Sequence[LabeledBatch]`。
- 「不改形狀」改為固定項／擁有項，並允許加法欄位。
- rebase 改為 merge。
- 回退判準精確化。
- 切面 PR 不得含 N-182。
```

### B：ADR-0039 全文

```
# ADR-0039：stock-desk `/today` 常駐揭露待執行與近期已結算的出清指令（補充 ADR-0033，不取代）

- 狀態：proposed
- 日期：2026-11-03
- 決策者：
  - tech-architect（草案）；
  - CEO #98～#101（2026-11-03，範圍）；
  - CEO #102（並行，見 ADR-0035 補充四）；
  - 風控逐字定稿：**尚未經手**。
- 與既有 ADR 的關係：
  - **ADR-0033**：補充，不取代，原文不改。C-4（經 CEO #87／#89 判準 Z 收窄）是謂詞來源；C-7 不變。
  - **ADR-0034 補充一**：引用 S-3、S-4。Decision 9 擴大 S-3 第 5 點的套用範圍，需風控確認。
  - **ADR-0035 補充四**：依其切面實作；只改切面 S-3 列為 N-171 擁有的部分。
  - **ADR-0037**：區塊不讀、也不寫 receipt store。
  - **ADR-0036**：保留給 N-172b／N-176，本 ADR 不涉入。
- 來源（`work/` 下）：
  - PRD `prd/2026-11-01-待執行出清指令常駐揭露-N171.md` v0.1；
  - [TA-4xx] `reviews/2026-10-31-4xx重複列N171N174評估-tech-architect.md` Q3；
  - [TA-P1] `reviews/2026-11-01-ADR0034補充一-tech-architect.md`；
  - 決策包 #98～#102；
  - 風控 `reviews/2026-11-01-ADR0037殘留與r32-風控.md` C-3；
  - 風控 `reviews/2026-10-31-N166已知限制與NB6合併後字面-風控.md`（渲染 `pending_directives` 須列全部覆蓋列，或先送審）。
- 程式位置是 2026-11-03 工作樹 `product/stock-desk` 的快照，請以內容定位。全部為讀碼判定，未執行。
- 字面規則：本檔只寫識別名與資訊要素，不寫面向使用者的文字。

## Context（背景）

1. **問題**：出清指令只存在於出清那一次的回應裡。
   - 重新整理、關分頁、送出中離開頁面、回 500 之後，使用者都看不到指令（問題 1）。
   - 回應遺失、結算後才重送時，會走 EMPTY，使用者被誤導（問題 2）。
   - 風控以書面接受這個殘留，直到 N-171 上線。

2. **現況**（讀碼）：
   - **覆蓋判定**：`service.py:237-261` 的 `exit_line_still_covers(directive, bars)`。
   - **候選列**：`store.py:1203-1220` 的 `_read_exit_state`（`rule_id='EMERGENCY' AND action='sell' AND settled=0`），同時讀 open 且 `remaining_shares>0` 的批次。
   - `plan_emergency_exit`（`service.py:298-401`）逐批、逐列套用判準 Z；非 open 批次上的列不回報（`:389-390`）。
   - **結算**：`settle_pending`（`:594-721`）只為 `execution_date <= as_of` 的待結算列載入 K 線（`:628`、`:638`），並用同一份序列判 N1（`:694`、`:761-821`）；沒有待結算列時不載入（`:629-635`）。
   - `evaluate_today` 另外載入一次所有批次的標的（`:1154`）。
   - **unauthored**（`:1048-1119`）：不結算、不載入、不寫入。
   - `/today` 的 `directives` 出自 `_read_logged`（`store.py:427-438`），排除 `UNKEYED_RULE_IDS`（`:236`）。
   - **已結算列**：`claim_directive`（`store.py:1270-1279`）寫入 `settled=1`、`settled_at`（UTC ISO）、`settled_open_price`、`status`。EMERGENCY 沒有價帶，永遠判 executed（`engine.py:1338-1339`）。

3. **PM 指出的三點，tech-architect 確認**：
   (1) [TA-4xx] N171-C2 的「`settled=0`、不加 execution_date」已過時。覆蓋判定是「候選列 SQL 加上逐列判準 Z」，需要日 K。
   (2) unauthored 以空序列呼叫時，全部會判為涵蓋。
       - `execution_date >= as_of` 的列，結果與有 K 線時相同：視窗止於 as_of，不可能有晚於預定執行日的 bar。
       - 會誤判的只有 `execution_date < as_of` 的列。
   (3) 只做結算前的欄位，解決不了結算後重送走 EMPTY 的情況。[TA-4xx] 已自述它只在 T+1 結算前成立。

4. **限制**：
   - R10、R16、EX-2、EX-5；
   - ADR-0033 C-3、C-9、C-10；
   - `GET /today` 不新增寫入；
   - 題 9 零痕跡；
   - ADR-0037 FE-C2、VETO-1、VETO-3、VETO-5；
   - 風控「全部覆蓋列」附帶條件。

## Options（選項比較）

### 一、群組 A 的形狀
| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (a) 單一清單，只列仍涵蓋的列（[TA-4xx] 原案） | 最小 | 不再涵蓋的舊列看不到，違反 CEO #100 與風控 C-3「全部」 | 使用者從沒看過的指令消失 | 不採 |
| (b) 單一清單，在 `DirectiveLine` 加分類欄位 | 欄位少 | `DirectiveLine` 也用於帳冊與出清回應，分類語意外溢 | 帳冊端誤用 | 不採 |
| (c) 依分類分三個清單，加區塊層級的渲染句 | 前端不做判斷；逐列呈現，與 `pending_directives` 一致 | 欄位較多 | 低 | **採用** |
| (d) 以批次為單位的群組物件 | 直接支援 FR-3「一批一行」 | 在風控 F-8 之前就定死呈現方式 | 呈現若改，就要改形狀 | 不採；F-8 若選此呈現，再以加法欄位補上 |

### 二、判準 Z 使用的 K 線（T-1）
| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (i) 另寫 `settled=0` 謂詞 | 簡單 | 判準 Z 之後，已不等於覆蓋判定 | 與出清的判定分歧 | **VETO** |
| (ii) 用 `evaluate_today` 的第二次載入 | 已經有 | 與結算判 N1 用的不是同一份序列 | 兩次載入一成一敗時，同一份回應自相矛盾 | 不採 |
| (iii) 用結算自己的序列（經 `_settle_pending`） | 與 N1 必定一致 | 要做結構搬移 | 由切面以零行為搬移承擔 | **採用** |
| (iv) unauthored 也載入 K 線 | 可以分類 | 違反題 9 零痕跡 | — | **VETO** |

### 三、unauthored 路徑（T-3）
| 方案 | 結論 |
|---|---|
| (u1) 以空序列呼叫判準 Z：`execution_date < as_of` 的列被誤判為涵蓋 | **VETO** |
| (u2) 全部不分類：連可以證明的涵蓋也不講 | 不採 |
| (u3) 不需 K 線就能判定的照判，其餘標「無法分類」 | **採用** |
| (u4) 不揭露：違反 CEO #99 | 否決 |

### 四、群組 B（T-5）
| 方案 | 結論 |
|---|---|
| (B-α) `/today` 讀取時計算，列出保留期內的已結算出清列。不新增狀態，資料已在 R16 日誌 | **採用** |
| (B-β) 後端存「已看過／關閉」狀態：違反 CEO #101，GET 也不得寫入 | 否決 |
| (B-γ) 只做 EMPTY 附加句：使用者不重送就看不到 | 不採為主方案，保留為 B2 |
| (B-δ) 把已結算列併入群組 A：「待執行」與「已判定」混在一起 | **VETO** |

## Decision（決策）

1. **欄位**：皆為加法欄位、預設為空；`PlaybookEvaluation` 同名同義；`types.ts` 同步，宣告 optional，缺鍵視為空。
   - 群組 A：
     - `pending_exit_directives: list[DirectiveLine]`：仍涵蓋的列（切面已定義此欄位）。
     - `stale_exit_directives: list[DirectiveLine]`：判準 Z 下已不再涵蓋、仍未結算的列。
     - `unclassified_exit_directives: list[DirectiveLine]`：只在 unauthored 路徑出現；authored 路徑恆為 `[]`。
     - `pending_exit_notes: list[str]`：三個清單全空時為 `[]`。
   - 群組 B：
     - `settled_exit_directives: list[SettledExitLineResponse]`，元素欄位為 `directive_id`、`line`、`open_price`、`settled_on`（ISO 日期）、`directive`。
     - `settled_exit_notes: list[str]`。

2. **候選列與 open 批次**：
   - `_read_pending_exits(conn)` 呼叫 `PlaybookStore._read_exit_state(conn)`，取得 `open_batches` 與候選列。
   - 不得另寫 EMERGENCY 候選列的 SQL。
   - 只保留 (symbol, batch_no) 屬於 `open_batches` 的列。其他列（非 open 批次上的舊重複列）不進群組 A，與 `plan_emergency_exit` 一致。

3. **分類**：唯一來源是純函式 `classify_exit_line(directive, bars: Sequence[PriceBar] | None, *, as_of) -> Literal["covering", "stale", "unclassified"]`。
   - `bars` 不是 None 時：`exit_line_still_covers(directive, bars)` 為真即 covering，否則 stale。不得另加任何條件。
   - `bars` 為 None（只限 unauthored）時：`execution_date >= as_of` 為 covering，否則 unclassified。
   - authored 路徑：`bars = run.loaded.get(symbol, NOTHING_LOADED).bars`，`run` 是同一次 `/today` 的 `_settle_pending` 結果。
     - 因此，batch 為 open 時，`settlement.unsettled` 中掛 N1／N1b 的列，就等於 `stale_exit_directives` 的列。
     - 不在 `run.loaded` 裡的標的，視為空序列，判為 covering。這與出清的降級方向相同。
   - `plan_emergency_exit` 不改。

4. **去重與排序**：
   - 每一列都列出，不去重。
   - 清單依 symbol、batch_no、execution_date、id 遞增排序。
   - 批數依 (symbol, batch_no) 去重計算。
   - 股數取讀取點當下該批次的 `remaining_shares`，逐批加總；不得以各列的 `shares` 加總（N171-C4、ADR-0034 補充一 S-2）。
   - 若風控 F-8 選擇「一批一行」，另加加法欄位 `pending_exit_batch_lines: list[str]`，三個清單不改。

5. **`pending_exit_notes` 的識別名**（逐字與順序由風控定稿）：
   - `PENDING_EXIT_BLOCK_NOTE`（F-1）：任一清單非空時。資訊要素為批數、股數、歸屬、本系統不下單、以券商回報為準。
   - `PENDING_EXIT_PAST_DUE_NOTE`（F-2）：任一列 `execution_date < as_of` 時。逐列列出 symbol、batch_no、預定執行日。
   - `PENDING_EXIT_STALE_NOTE`（F-3）：`stale_exit_directives` 非空時。
   - `PENDING_EXIT_UNCLASSIFIED_NOTE`（F-5）：`unclassified_exit_directives` 非空時。不得宣稱需要日 K 才能確認的狀態。
   - 全空時，不渲染任何字面（FR-10，待 F-4）。

6. **讀取與一致性**：
   - 一律出自切面的 `read_in_flight()`，與 N-168 的清單在同一個 read transaction 內。
   - N-171 不新增任何寫入，也不新增任何 K 線載入。

7. **unauthored**：照舊不結算、不載入、不寫入；分類一律用 `bars=None`。

8. **不依賴模式、不含 buy**：不得由 mode 或 `emergency_until` 推導；清單不含 buy 列。

9. **W-B2L**（ADR-0034 補充一 S-3 第 5 點）：
   - 群組 A 的三個清單一律經 `_lines(..., labeled_batches=evaluation.labeled_batches)` 建立。套用規則由 N-168 實作；N-171 不判斷、不渲染 W-B2L。
   - 套用範圍從 `pending_exit_directives` 擴大到 `stale_exit_directives`、`unclassified_exit_directives`，待風控確認。
   - 群組 B 不帶 W-B2L，待風控確認。
   - N-171 先合併時，`entry_before_exit_note` 恆為 null，畫面上沒有空位（AC-N171-21）。

10. **群組 B**：
   - **來源**：`rule_id='EMERGENCY' AND action='sell' AND settled=1 AND status='executed' AND settled_at IS NOT NULL` 的列。
     - 在 `_read_pending_exits` 內、同一個 transaction 讀取。
     - 下界為 `settled_at >= as_of − LOOKBACK_DAYS` 個日曆日，只是一個超集合，精確篩選在後面。
   - **保留期**：
     - 常數 `SETTLED_EXIT_RETENTION_TRADING_DAYS = 20`，放在 service，不放 `RuleParams`（CEO #101）。
     - `settled_on` 是 `settled_at` 的 UTC 日期。
     - 列出條件為 `as_of <= calendar.shift(settled_on, 20)`，由純函式 `settled_exit_retained` 判定。
   - **交易日曆**：
     - authored 路徑用 `evaluate_today` 的同一份 calendar；
     - unauthored 路徑用 `TradingCalendar(())`。這條路徑會把休市日當成交易日，是已知偏差。
   - 不存任何狀態，沒有關閉機制，每次讀取時計算。
   - 每一列都列出，依 settled_on、symbol、batch_no、id 排序。
   - `settled_exit_notes` 的識別名為 `SETTLED_EXIT_BLOCK_NOTE`（F-7）。
   - **B2**：EMPTY 支在「存在保留期內的已結算出清列」時，附加 `EMERGENCY_EXIT_EMPTY_SETTLED_NOTE`。
     - EMPTY 本文不改，不新增第四支 message。
     - 判定在出清的鎖內進行，由 `_read_exit_state` 多讀一項。

11. **分階段與閘門**（CEO #98）：
   - **A**：
     - 風控 F-1～F-6、F-8、F-9 定稿；
     - NB-6 回審通過；
     - 前端在 ADR-0037 出清畫面包合進 product 之後才做；
     - A 不受 B 阻擋。
   - **B1**：在 A 合併之後；需 F-7 定稿。
   - **B2**：在 N-168 合併之後；需 F-7 的附加句定稿。
   - 結論：**可同包，不建議拆案**。

12. **與切面（ADR-0035 補充四）的關係**：
   - N-171 只改自己擁有的 `PendingExitRead`、`_read_pending_exits`、`_pending_exit_lines`，以及本 ADR 的加法欄位。
   - 不改補充四 S-3 的固定項。
   - 合併規則依補充四 S-5、S-6。

13. **NB-6**（T-9）：
   - 風控回審通過前不得合併。
   - 若要改字：`wording.py` 常數、前端鏡射、逐字守門測試、字面絆線測試放在同一個 commit，並與 N-171 同一個 PR。
   - 禁用詞掃描要納入新常數。
   - N164N165 PRD 由 PM 改版到 v5.5。

14. **T-4**：確認 `directives` 排除 EMERGENCY，並補一條端到端守門測試。

15. **約束與測試**：以附錄 A、附錄 B 為準。

## Consequences（後果）

**好處**：
- 四條回應遺失的路徑，在結算前都看得到指令；結算後 20 個交易日內也看得到。
- 分類結果與出清、結算一致。
- 不新增狀態，也不新增寫入。

**代價**：
- `/today` 多 6 個欄位。
- 風控有十多項字面要定稿。
- 切面多一項結構搬移。

**壞處與殘留**：
- `/today` 失敗時看不到區塊。
- 超過 20 個交易日後，群組 B 消失。這個天數沒有數據依據（CEO #101）。
- 逐列呈現時，重複列可能被讀成兩筆；由標題句的去重計數緩解，F-8 決定最終呈現。
- unauthored 路徑上，預定執行日已過的列只能標「無法分類」；群組 B 的日曆在休市日有偏差。
- 結算載入失敗時，已不涵蓋的列會被判為涵蓋（降級方向與出清相同）。
- 長期無法結算的列（F7／N-176、F6）會一直留在清單上。
- `settled_at` 為 NULL 的舊列不會出現在群組 B。
- B2 要等 N-168 合併。

**規模估計**：
- A：後端 S～M（約 20 條測試），前端 M。
- B1：後端 S（約 8 條測試），前端 S。
- B2：S（約 4 條測試）。

**被約束的事**：見附錄 A。

## 待決
- 風控：F-1～F-11；Decision 2、4、9、10 的確認項。
- CEO：
  - 本 ADR 轉 accepted；
  - 保留期起算日（建議用結算當日，即 `settled_at` 的日期）。
- PM：PRD v0.2，修改 FR-3、AC-N171-5、AC-N171-11、M2。
- art-lead：A-1 版面規範。

## 附錄 A：N171-C 約束（修訂版；qa-reviewer 逐條檢查，皆為 BLOCKING）
- C1：欄位為加法欄位、預設空；`types.ts` 宣告 optional；前端收到缺鍵的回應不出錯。
- C2′：
  - 候選列只來自 `_read_exit_state`；
  - 分類只經 `classify_exit_line`，判準 Z 只用 `exit_line_still_covers`；
  - authored 路徑用 `_settle_pending` 的序列；
  - 不另寫 EMERGENCY 謂詞，不呼叫 `pending_directives(on_or_before)`，不加 execution_date 條件。
- C3：不由 mode 或 `emergency_until` 推導。
- C4′：逐列列出，不去重；批數依批次去重；股數取批次 `remaining_shares`；不得加總列的股數。
- C5：不含 buy 列。
- C6：字面只放 `wording.py`；store 不 import wording；風控核可前不得合併。
- C7：
  - 前端不經過 `DirectiveLedger` 渲染；
  - `RuleSetConfirmPanel` 的前提有守門測試；
  - 渲染 `entry_before_exit_note`；
  - 不讀、不寫 receipt store 與 mutation。
- C8：NB-6 回審通過前不得合併。
- C9：只經 `read_in_flight` 讀取；讀取過程零寫入。
- C10：unauthored 路徑不載入、不結算、不寫入。
- C11：非 open 批次上的列不進群組 A。
- C12：群組 B 不存狀態、沒有關閉機制；保留期常數不可由使用者設定；已結算列不得進群組 A。
- C13：`directives` 不含 EMERGENCY。
- C14：欄位為空時不新增任何字面（待 F-4）。
- C15：`DirectiveLine` 只能經 `_lines` 建立。
- C16：B2 不改 EMPTY 本文，不新增 message 分支。

## 附錄 B：測試清單
- T1：DB 沒有出清列時，各欄位為空；其餘鍵與切面基準相同。
- T2：出清兩個批次後的同一天，兩列都在 `pending_exit_directives`，`notes` 非空。
- T3：同上情境，`directives` 不含 EMERGENCY（T-4）。
- T4：同一份 DB 由新的 service 實例連續讀兩次，回應相同（模擬重新整理、第二個分頁）。
- T5：凍結期已過、列仍未結算時照列；模式為凍結、但所有列都已結算時為空；`emergency_until` 延後不影響內容。
- T6：R1 待成交買單永遠不進這些清單。
- T7：N-166 前的重複列（同一批次、兩個預定執行日）兩列都列；批數為 1；股數等於 `remaining_shares`。
- T8：在同一次呼叫內已結算的列，不在群組 A。
- T9：trace 證明 N-171 的路徑沒有任何 INSERT／UPDATE／DELETE。
- T10：判準 Z 舊列與新列並存時，舊列在 stale、新列在 covering。用第二次載入回傳不同資料的 resolver，證明分類用的是結算那一份序列，且與 N1 一致。
- T11：載入失敗或序列為空時，列判為 covering，不會漏列。
- T12：unauthored 路徑：
  - `execution_date >= as_of` 的列判為 covering，`execution_date < as_of` 的列判為 unclassified；
  - resolver 從未被呼叫；零寫入。
- T13：任一列已過預定執行日時，才出現 PAST_DUE 句（字面 blocked）。
- T14：非 open 批次上的列被排除。
- T15：
  - 重送走 ALREADY_PENDING 時，內容不變；
  - 隔日重送時，內容不變；
  - EX-3（凍結期間新出現的 open 批次再出清）時，新增一列。
- T16：`classify_exit_line` 帶入序列時，結果與 `exit_line_still_covers` 等價；`bars=None` 的捷徑，在所有日期不晚於 as_of 的序列上與它等價（property test）。
- T17：SEAM-T3、T4、T5 仍綠。
- T18：字面逐字鏡射，並 grep 確認 `wording.py` 之外沒有出現。
- T19：前端：
  - 區塊位置與獨立性；
  - 原始碼不 import receipt store 與 mutation；
  - 欄位為空、或 `/today` 失敗時不渲染；
  - 渲染 `entry_before_exit_note`。
- T20：qa-e2e 實機驗證 AC-N171-12 的四條路徑。
- TB1：保留期邊界：`shift(settled_on, 20)` 當天仍列出，隔天不列。
- TB2：保留期內遇休市日，以交易日計算。
- TB3：unauthored 路徑使用 weekday fallback。
- TB4：讀取群組 B 零寫入；schema 不變。
- TB5：`settled_at` 為 NULL 的列被排除。
- TB6：
  - 有保留期內的已結算出清列時，EMPTY 支附加句子，本文不變；
  - 沒有時不附加。
- TB7：已結算的重複列逐列列出。

## 附錄 C：T-1～T-9 答覆對照
- T-1：Decision 3、Options 二。
- T-2：Decision 1、5。
- T-3：Decision 3、7。
- T-4：Decision 14。
- T-5：Decision 10、11。
- T-6：Decision 9。
- T-7：Decision 4。
- T-8：Decision 6。
- T-9：Decision 13。
```

## 三、驗證

**讀過的文件**
- PRD N-171 全文。
- 我的兩份前次評估全文（4xx、ADR-0034 補充一）。
- ADR-0033、ADR-0035 全文；ADR-0001 模板。
- 決策包 #98～#102。
- 追蹤清單 N-171～N-182。
- 風控 N-168 裁示的 W-B 系列；ADR0037 殘留裁示 C-3 與「全部覆蓋列」條件（grep）。

**讀過的程式**（工作樹 `product/stock-desk`）
- `service.py`：`:230-409`、`:555-821`、`:1040-1362`。
- `store.py`：`:125-171`、`:225-296`、`:420-554`、`:603`、`:1150-1362`。
- `api/playbook.py`：`:60-570`。
- `data/calendar.py`：`shift`、`trading_days_between`。
- `engine.py`：`settle_directive`。
- `types.ts`：`:1730-1996`。
- `.github/workflows/stock-desk.yml`。

**沒驗證到的事**
- 分支 `feat/stock-desk-today-seam-n182`：本機 reflog 只看到它在 `de7bc03` 建立，看不到遠端有沒有 commit。所以「dev-lead 已開工的內容」與補充四的差異，我是對照 11-01 的條件文字，不是對照實際 diff。
- 群組 B 的規模、保留期的日曆行為，都是讀碼推論，沒有執行。

**本次限制**：沒有執行任何程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

**建議 CEO 親自確認**：保留期的起算日（見下方 CEO 題）。

## 四、下一步

**需 CEO 裁示（1 題）**

| # | 問題 | 選項 | 建議預設 |
|---|---|---|---|
| CEO-1 | #101 的「結算日起 20 個交易日」，起算日要用哪一天？ | (a) 系統結算當日，即 `settled_at` 的 UTC 日期；(b) 預定執行日，即用來判定的那個開盤日 | **(a)**。群組 A 的清單是在系統結算那一刻才消失的。用 (a)，能保證清單消失之後，B 至少可見 20 個交易日；行情晚到時，(b) 的可見期會被吃掉。 |

**告知事項（不需裁示）**：補充四比 #102 的文字多了幾項結構（見出入表）。是否回報 CEO 由 coordinator 判斷；我判斷仍在 #102 的範圍內。

**需風控定字面或確認**
1. F-1：`PENDING_EXIT_BLOCK_NOTE`。
2. F-2：`PENDING_EXIT_PAST_DUE_NOTE`。
3. F-3：`PENDING_EXIT_STALE_NOTE`，以及新舊兩列並存時的呈現方式。
4. F-4：空狀態。我建議不渲染任何字面。
5. F-5：`PENDING_EXIT_UNCLASSIFIED_NOTE`。
6. F-6：NB-6 第 2 句的回審（連同第 1、3 句），並附兩種畫面。
7. F-7：`SETTLED_EXIT_BLOCK_NOTE`、`EMERGENCY_EXIT_EMPTY_SETTLED_NOTE`。字面若提到期間，要和 CEO-1 的結果一致。
8. F-8：
   - 逐列呈現或一批一行；
   - C-3 的切分是否接受：未結算歸 A、20 個交易日內的已結算歸 B、超過之後不揭露。
9. F-9：與回執橫幅並存時的呈現。
10. Decision 9：W-B2L 擴大到 stale 與 unclassified 兩個清單；群組 B 不帶 W-B2L。
11. Decision 2：非 open 批次上的未結算舊重複列不進群組 A。
12. 排序改用 symbol、batch、日期；出清回應用的是 id。
13. 群組 B 是否列出 N-166 之前、已結算、實際移動 0 股的重複列（N2）。

**交接**
1. coordinator：
   - 把 A 的檔頭行貼進 ADR-0035；
   - 把 B 交 tech-writer 落檔為 `docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md`；
   - 本報告存為 `work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md`。檔頭行引用的是這個路徑，若改名要同步。
2. dev-lead：依補充四 S-2 調整切面 PR，只含切面，不含 N-182。重點在出入表的第 1～4、9 項。
3. 風控與 PM：依上列清單處理；PM 出 PRD v0.2。

### 相關檔案
- /home/user/AICompany/work/prd/2026-11-01-待執行出清指令常駐揭露-N171.md
- /home/user/AICompany/work/reviews/2026-11-01-ADR0034補充一-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-31-4xx重複列N171N174評估-tech-architect.md
- /home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md
- /home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md
- /home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md
- /home/user/AICompany/docs/adr/0037-stock-desk-排程台出清流程的狀態擁有層.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/types.ts
- /home/user/AICompany/.github/workflows/stock-desk.yml


---

（coordinator 2026-11-04 附加：tech-architect 對補充四的釐清一，原文轉存自 `work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md`）

## 釐清一（tech-architect 2026-11-04，回應 N-182 交件解讀點 2、3）

- 性質：釐清 S-2.3(c)、S-3、S-5 第 4 點與 S-7。不改任何固定項，不改 S-6 的判準。
- 依據：`work/reviews/2026-11-04-切面與N182交件-dev-lead.md` 解讀點 2、3；`work/reviews/2026-11-04-N182審查-qa-reviewer.md` 第 5、6 項。

### E-1 先行建立者（S-3、S-5 第 4 點）
1. S-5 第 4 點的情況已成立：N-182 先於 N-168 合併，由 N-182 建立 ADR-0034 補充一 S-1 第 3 點要求的「G1 擋下類」單一來源。N-182 因此是下列項目的**先行建立者**：
 - (a) `EntryBeforeExitRead.blocked` 欄位，名稱、型別與預設值以 N-182 合併時為準；
 - (b) `_read_entry_before_exit` 內填入 `blocked` 的查詢；
 - (c) store 常數 `BATCH_LEFT_PLANNED_SQL`，以及 `claim_directive`、`batch_blocking_claim`、`_read_entry_before_exit` 三處對它的直接引用。
2. 擁有權不移轉：(a)(b) 仍是 N-168 的擁有項；(c) 屬於 G1（ADR-0035 Decision 6′），不歸任何一方擁有。
3. N-168 對上列項目**只能擴充、不得改寫**：
 - 可以：
   - 在 `EntryBeforeExitRead` 新增欄位；
   - 在 `_read_entry_before_exit` 新增查詢；
   - 在 `blocked` 的查詢多選欄位，但列集合不變；
   - 在 service 端從 `blocked` 再篩出自己的清單。例如 `/today` 的 `entry_before_exit_blocked_directives` 只列已打 L4 戳記的列（ADR-0034 補充一 S-3 第 6 點）。
 - 不可以：
   - 把 `blocked` 改名、改型別或移除；
   - 改變 `blocked` 的列集合條件。列集合是待成交買單（風控 2026-11-01 共用定義：`action='buy' AND settled=0 AND status='pending'`）中符合 `BATCH_LEFT_PLANNED_SQL` 的列；
   - 另寫一份「批次已非 planned」的條件；
   - 讓 W-B6b、ENTRY、A 的排除改讀 `blocked` 以外的來源；
   - 改動 `tests/test_playbook_pending_entry_blocked.py` 的既有斷言。
 - W-B6 與 W-B6b 必須互斥（風控 2026-11-01 必改 3），而且必須以 `blocked` 或 `BATCH_LEFT_PLANNED_SQL` 切分，不得另外判斷。
4. N-168 若必須改寫上列項目才能完成，PR 先停住，由 tech-architect 出補充修正規格。(a)(b) 不是固定項，所以這種情況**不構成** S-6 的回退判準；但沒有補充就改寫，視同違反 S-5 第 4 點。
5. S-3「允許」條款中「自己的加法欄位」，指在自己的擁有項上、或在自己 ADR 定義的回應欄位上新增欄位，**不包括**在他方擁有項上加欄位。他方的擁有項，只有在 S-5 第 4 點這類有明文授權的情況下，才能由別人先行建立，並受本節第 3 點約束。
6. N-182 不填 `entry_before_exit_blocked_directives`，它恆為 `[]`；也不改 `_entry_before_exit_lines` 的回傳。這兩項連同 W-B6、W-B1d，仍由 N-168 實作。

### E-2 兩份快照（S-2.3(c)）
1. 判定：已知限制，接受，不修。
2. 理由：
 - 批次狀態只會離開 planned，不會回到 planned。所以 `read_in_flight` 讀到的 `blocked`，只會比 commit 鎖內的實際狀態少，不會多。
 - 單一請求內碰不到這個落差：
   - 本次評估在 commit 內能改變批次狀態的，只有 `batch_skipped`，而且只隨本次寫入的 R 系列列套用（N172-C5）；
   - ENTRY 與 A 計入的買單，是同一 symbol、同一預定執行日已記錄的 R1 買單。K2 會擋下本次對這個 symbol 的任何 R 系列新列，所以這個 symbol 的批次在 commit 內不會變動；
   - `apply_effects` 不套用 `batch_skipped`，也不套用成交類 effect。
 - 實際的觸發只有並發：在 `read_in_flight` 之後、commit 讀 logged 之前，另一個請求的結算讓同一批次的另一筆買單成交（planned → open）。這歸入 F2／N-169 的並發窗口殘留，下一次 `/today` 會修正。
3. 不採的修法：
 - 在鎖內重讀 blocked：**VETO**。
   - 這是 `read_in_flight` 之外的在途讀取，違反 R-4；
   - 而且 W-B6b 和 ENTRY／A 的排除會出自兩份快照，同一列可能兩邊都不出現，違反風控「互斥，合起來剛好是全部」。
 - commit 後依 effects 重算：不採。它只處理上面說的單一請求內碰不到的情況，對並發沒有作用。
4. 若日後必須消除這個殘留，唯一與本補充相容的方向，是把 `read_in_flight` 的呼叫時點移到 `commit_evaluation` 之後：
 - 因為狀態單向變動，較晚的快照只會往「帳冊不會判定」的方向偏，而這個方向是正確的；
 - 這要改 S-2.3(c)，須由 tech-architect 另出補充，評估對 N-168、N-171 的影響之後才能動。
5. 接受此限制的條件，N-182 合併前要完成，qa-reviewer 列為 BLOCKING：
 - (a) `same_day_warnings` 的 docstring 寫明此限制：觸發只有並發，單一請求內由 K2 排除；
 - (b) 新增一條守門測試：同一 symbol、同一預定執行日已有已記錄的 R1 待成交買單時，即使引擎本次對這個 symbol 產出 R3 skip，`evaluate_today` 之後這個 symbol 各批次的 status 仍與呼叫前相同；而且回應中 ENTRY／W-B6b 的分類，與呼叫結束後依 DB 重新計算的分類相同。

### E-3 S-7 增列檢查項
- QB-10（N-168 的 PR）：
- E-1 第 3 點逐條檢查；
- `store.py` 內「批次是否為 planned」的 SQL 比較，只出現在 `BATCH_LEFT_PLANNED_SQL`；
- `tests/test_playbook_pending_entry_blocked.py` 的既有斷言零改動。
- QB-11（N-182 的 PR）：
- E-1 第 6 點；
- `blocked` 的列集合等於 E-1 第 3 點所述的集合；
- E-2 第 5 點的 docstring 與守門測試存在且綠燈。


---

（coordinator 2026-11-04 附加：tech-architect 對補充四的釐清二，原文轉存自 `work/reviews/2026-11-04-ADR0035補充四釐清二-tech-architect.md`）

## 釐清二（tech-architect 2026-11-04，SEAM 守門測試常駐後的合法行為差異）

- 性質：釐清 S-4（SEAM-T1、T2、T4、T5）與 S-7，並依 S-3 補定兩個未列入擁有權的共用面（E-11）。不改任何固定項，不改 S-6 判準，不改 golden。
- 依據：`work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md` 第二段 D 的規格缺口預告；`work/reviews/2026-11-04-切面審查-qa-reviewer.md` 對 golden 錄製來源的意見；ADR-0034 補充一、補充二（`work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md`）；ADR-0039 v2 與補充一。
- 程式位置：2026-11-04 工作樹 `product/stock-desk`（含切面合併 `5c2d3e1`、出清畫面包、`d7e1756`；不含 N-182），請以內容定位。

### E-4 斷言分類
1. SEAM 測試裡的斷言分成兩類：
 - (a) 不變式斷言：常駐，之後任何 PR 都不得改。
 - T1：每個今日回應都有 2.2(a) 的三個鍵；`directives`、`pending_directives` 與三個清單的每一列都有 `entry_before_exit_note` 鍵；每個情境都有可檢查的列。
 - T2：去掉時鐘鍵與已登記的新增鍵之後，回應等於「golden 套用已核准差異」的結果（E-6）。
 - T3、T6、T7 全部。
 - T4：只有 `BEGIN`、SELECT、`COMMIT`；讀取失敗時 ROLLBACK 並原樣 raise。
 - T5：AST 掃描；`labeled_batches` 為 KEYWORD_ONLY 且無預設值；`line.line == wording.directive_line(...)`；service 欄位預設為空。
 - T8 全部。
 - (b) 切面期斷言：描述的是 stub 狀態，擁有者填入後必然改變。
 - T1 的「三個清單值為 `[]`」與「`entry_before_exit_note` 為 null」；
 - T2 golden 中既有欄位的值；
 - T4 `test_t4_the_read_is_begin_selects_commit` 最後一行 `read == InFlightRead(exits=PendingExitRead(), entries=EntryBeforeExitRead())`；
 - T5 `test_t5_the_line_is_never_touched_and_the_note_stays_null` 的 note 為 None 斷言。
2. S-4 SEAM-T2 的「既有斷言只准因新增鍵而改」只約束切面 PR 本身。切面之後的 PR：切面期斷言只能依 E-6、E-7 調整，不變式斷言一律零改動。
3. 只改測試裝置、不改斷言與 fixture 的變更不算斷言改動，但要在 PR 說明列出。例如 `d7e1756` 為 SEAM-T8 包上 `ExitReceiptStoreProvider`。
4. 違反本釐清屬 BLOCKING，在該 PR 內修正，不構成 S-6 回退。只有在必須改固定項時，才依 R-3 處理。

### E-5 golden 凍結
1. `apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json` 以 `5c2d3e1` 的內容為準，逐位元凍結：
 - 不得重錄，不得手改，不得增刪情境或回應；
 - 重新格式化、重新排序、改縮排，都算修改。
2. T2 增加一條斷言：golden 的 sha256 等於常數 `GOLDEN_SHA256`。
 - 常數取 `git show 5c2d3e1:<上列路徑>` 的雜湊，在 E-10 的機制 PR 中寫入；
 - 寫入之後不得修改。
3. 理由：
 - golden 是切面前的基準。在改過的程式上重錄，T2 就是自己比自己，夾帶的非預期差異看不出來。
 - SEAM-T8 把它當成「缺新鍵的舊回應」fixture。重錄會帶入新鍵，T8 就失去意義。
 - 並行的分支若各自重錄，會在同一份檔案上衝突，而且無法有意義地解。
 - 錄製來源 `31753cb` 只有在檔案不變時，才能被重新驗證。
4. 需要新情境時，寫在擁有者自己的測試，不加進 golden。
5. 本釐清不授權任何重錄。若真的需要（例如 migration 讓 golden 情境無法重建），PR 先停住，由 tech-architect 另出補充。

### E-6 核准差異登記
1. 位置：`apps/stock-desk/backend/tests/golden/seam/approved/`，一個擁有者一個 JSON 檔：`n168.json`、`n171a.json`，之後 B1、B2 各自加檔。
 - PR 只能改自己的檔。
 - N-182 不建檔。
2. 檔案內容：
 - `owner`。
 - `added_keys`：本案新增的回應鍵。每項含 `key`，以及 `source`（定義它的 ADR 條號）。
 - `filled`：本案填入的切面期項目，可以是：
 - `today_lists`：三個清單中的哪幾個；
 - `note`；
 - `in_flight`：`exits` 或 `entries`。

 每項含 `source`，以及 `test`（以精確值斷言其內容的測試 node id）。
 - `deltas`：既有欄位值的差異。每項含：
 - `id`（例如 `N168-D1`）；
 - `source`：定稿依據，寫 ADR 條號或風控文件加句名；
 - `approval`：E-7 的核准出處；
 - `scenario`、`body`、`path`：`path` 是由鍵與索引組成的陣列；
 - `op`：`replace`、`insert`、`remove` 三選一；
 - `before`：replace、remove 必填，為 golden 在該路徑的原值；
 - `after`：replace、insert 必填，為完整的最終值。
3. T2 的比對步驟：
 1) 確認 golden 的 sha256（E-5 第 2 點）。
 2) 依檔名順序讀入全部登記檔，檢查格式，並確認 `id` 不重複。
 3) 刪除鍵 = 時鐘鍵 ∪ 切面的四個鍵 ∪ 全部的 `added_keys`。`added_keys` 的名稱不得出現在 golden 的任何深度。
 4) 期望值 = golden 的複本，依檔案順序、再依檔內順序套用 `deltas`：
 - replace、remove：當下的值必須等於 `before`；
 - insert：索引不得超過 list 長度；
 - 路徑最後一段是 `message` 時，只准 replace，而且 `after` 必須以 `before` 開頭（ADR-0034 C-B5：只能附加）。
 5) 斷言：實際回應去掉刪除鍵之後，等於期望值。
4. 禁止事項：
 - 萬用字元、正規表示式、謂詞，或任何「忽略此欄」的寫法；
 - 把既有鍵登記成 `added_keys`，藉刪除鍵略過差異；
 - `after` 等於 `before` 的空差異；
 - 不同擁有者的差異落在同一個 list 或同一個葉節點。遇到這種情況，PR 停住，由 tech-architect 裁定；
 - 用整個 list 的 replace 代替逐元素的 insert／remove。差異一律寫在會變動的最小路徑上；字串整條 replace，不做子字串修補。
5. 每筆登記的差異都必然會被用到：用不到的差異會讓期望值與實際回應不符，T2 轉紅。
6. 切面期斷言的調整方式：
 - T1：登記在 `filled` 的清單或 note，不再斷言為 `[]`／null；「鍵存在」照舊斷言。沒有登記的照舊斷言為空。
 - T4：最後一行改成只對沒登記在 `filled.in_flight` 的部分，斷言等於預設值。BEGIN、SELECT、COMMIT 的斷言不動。
 - T5：只有 N-168 可以改 `test_t5_the_line_is_never_touched_and_the_note_stays_null` 的 note 斷言：
 - 改為 W-B2L 規則的期望值；
 - 另加一個「未標示批次的 note 為 None」案例；
 - `line.line` 的斷言一字不動。
 - `filled` 的 `test` 必須在 golden 的同一組情境上，以精確值斷言填入的內容。

### E-7 核准權責
1. 差異的依據只能是已定稿的來源：accepted 或已核可補充的 ADR 條文，或風控的逐字定稿加上它的渲染條件。依據沒有寫到的差異，一律不核准。
2. E-8 列出的差異，由本釐清預先核准類別。
 - `after` 的精確值由 qa-reviewer 對照依據逐字核對。
 - 字面類差異另以風控合併前的逐字核可為準（ADR-0034「合併前仍須經逐字核可紀錄」）。
3. E-8 以外的差異：
 - PR 先停住，dev-lead 送 tech-architect；
 - tech-architect 在 `work/reviews/` 下以書面逐一 `id` 核准，`approval` 欄寫那份檔案的路徑；
 - 屬於 `remove`，或會改變面向使用者既有揭露的，另需 risk-compliance-officer 書面確認。
4. qa-reviewer（含 Codex 第二意見）是每個 PR 的閘門，QB-12 列為 BLOCKING。
5. 不需要 CEO 裁示。差異若與 accepted ADR 衝突，以 ADR 為準並退回，不得以登記差異繞過。

### E-8 N-168 的預先核准清單（依讀碼預測，以實際 diff 為準）
golden 中只有 `after_exit` 情境會被 N-168 改到。這個情境的設定是：
- 批次 1 為 planned，帶一筆 2026-08-12 的 R1 待成交買單；
- 8/11 出清批次 2、3；
- 8/12 結算時，這筆買單成交。

| id | 路徑 | op | 依據 | 內容 |
|---|---|---|---|---|
| N168-D1 | `after_exit.exit.message` | replace | ADR-0034 W-B1；補充二 RESULT 支組合順序 | golden 原文之後附加 W-B1 |
| N168-D2 | `after_exit.exit_repeat.message` | replace | 同上，ALREADY_PENDING 支 | golden 原文之後附加 W-B1 |
| N168-D3 | `after_exit.today.warnings[1]` | remove | 補充二 P4、P5：W-B6 列過的列從 ENTRY 排除，全部被排除時 ENTRY 不渲染 | 移除 `SAME_DAY_EARLIER_ENTRY_NOTE` 那一句 |
| N168-D4 | `after_exit.today.warnings[1]` | insert | ADR-0034 W-B6；補充二 P4（緊接 FROZEN_NOTE） | W-B6 |
| N168-D5 | `after_exit.today_next_day.settlement.warnings[1]` | insert | ADR-0034 W-B3（緊接 SETTLEMENT_SUMMARY） | W-B3 |

- 依序套用 D3、D4 之後，`after_exit.today.warnings` 為 [FROZEN_NOTE, W-B6]。
- 預期不會出現在 golden 中的句子與值：
- W-B1b、W-B6b：沒有批次已非 planned 的買單；
- W-B1d：每個批次只有一列；
- W-B1p：預定執行日沒有過期；
- W-B2／W-B2L 的非 null 值：golden 中沒有標示批次上的賣出列。

實際出現上述任何一項，或出現 D1～D5 以外的差異（例如 message 另外附加了 S10、W-B7），都算 E-8 以外，依 E-7 第 3 點處理。
- `added_keys`：`entry_before_exit_on`、`entry_before_exit_label`（ADR-0034 補充一 S-3 第 3 點）。
- `BatchSnapshot.entry_before_exit_note`，以及出清回應的兩個清單，與切面鍵同名，已經被刪除，不需要登記。
- `filled`：
- `today_lists` 的 `entry_before_exit_directives`：golden 中，`after_exit.today` 應有批次 1 的那 1 列；
- `entry_before_exit_blocked_directives` 可登記也可不登記；登記時，`test` 要斷言 golden 中為 `[]`；
- `in_flight` 的 `entries`；
- T5 的 note 斷言依 E-6 第 6 點調整。
- authored、unauthored 兩個情境：零差異。

### E-9 適用範圍
1. 本釐清適用於切面之後的每一個 PR。
2. N-171-A：
 - `deltas` 必須為空：N-171-A 只填新鍵（ADR-0039 補充一 T21：`warnings` 與 N-172a 錨點測試不改斷言）。出現任何差異，依 E-7 第 3 點停住。
 - `added_keys`：ADR-0039 Decision 1 的頂層新鍵，目前是 `pending_exit_block`。只登記最外層的鍵，不登記 `rows`、`text`、`notes`、`title`、`lead` 這類內層名稱；例如 `title` 已經出現在 golden 的 `cap1_disclosure` 裡。
 - `filled`：
 - `today_lists` 的 `pending_exit_directives`：golden 中，`after_exit.today` 應有批次 2、3 兩列，`unauthored.today_after_exit` 應有批次 1 一列，其餘今日回應為 `[]`；
 - `in_flight` 的 `exits`。
 - N-171-A 不改 T5。
 - `POST /settle` 改走 `settle_on_request` 之後，SEAM-T6「`POST /settle` 的既有測試不改斷言」照舊適用。若有任何既有斷言要改，依 E-7 第 3 點逐條送核。
3. N-171-B1、B2：比照 N-171-A。
 - B1 登記 `settled_exit_block`；
 - B2 的 B-4 只附加在 EMPTY 支，golden 中沒有 EMPTY 支，預期零差異。
4. N-182：
 - `deltas`、`added_keys`、`filled` 都為空，不建登記檔；T1、T2、T4、T5 零改動。
 - T2 在 N-182 上仍綠，原因是 N-182 的行為只對「批次已非 planned 的待成交買單」生效，而 golden 的 9 個回應中沒有這種列：
 - `after_exit.today` 唯一的買單在批次 1，而批次 1 仍是 planned。所以 ENTRY／A 的排除集合是空的，句子與 golden 相同，W-B6b 也不渲染。
 - `after_exit.today_next_day` 的買單，在同一次呼叫的 `_settle_pending` 中已經成交。`read_in_flight` 在結算之後才執行，讀到時這筆已不是待成交。
 - authored 情境的買單都在 planned 批次上。
 - unauthored 情境沒有買單，N-182 也不在這條路徑上計算（風控 2026-11-04 第 8 點 (b)）。
 - `refused_by_g1` 不進 API。
 - 所以 T2 綠燈只證明 N-182 沒有外溢到 golden 情境，不證明 N-182 正確。N-182 的正確性由 `tests/test_playbook_pending_entry_blocked.py` 負責。
 - N-182 merge product 之後，T2 必須在登記為空的情況下仍綠。若轉紅，不得用登記差異解決，要視為 merge 引入的回歸，先查明原因。

### E-10 機制落地
1. 下列項目以單獨一個 test-only PR 落地：讀取登記檔；依 E-6 改寫 T1、T2、T4；寫入 sha256 釘選。
 - 只動 `tests/test_playbook_today_seam.py`、`tests/seam_helpers.py`，以及 `tests/golden/seam/approved/` 目錄（初始不放任何擁有者檔）；
 - `app/` 零 diff，golden 零 diff。
2. 時點：
 - 在 N-171-A 送 PR 之前合進 product；
 - N-171-A、N-168 merge 含此 PR 的 product 之後，再加自己的登記檔。
3. 若 N-171-A 完成時機制 PR 尚未合併：
 - N-171-A 可以作為先行建立者，把機制放在自己 PR 內一個獨立、只含測試的 commit；
 - N-168 對機制只能加自己的登記檔，不得改寫（比照 E-1 第 3 點）。
4. qa-reviewer 驗收：
 - 登記為空時，T1～T8 全綠，且 T2 的判定和改寫前等價；
 - 變異測試，下列每一項都要讓 T2 轉紅：
 - 暫時改動任一回應的既有欄位值；
 - 登記一筆 `before` 錯誤的差異；
 - 登記一筆空差異；
 - 登記一個和 golden 撞名的 `added_keys`。
 - 變異測試做完要還原，並在交件說明中列出。

### E-11 N-168 與 N-171-A 並行的共用面（補 S-3）
1. `PlaybookStore._read_exit_state`／`EmergencyExitState`：
 - 現況：
 - N-171-A 在 `read_in_flight` 內呼叫它（ADR-0039 Decision 2）；
 - N-168 要在出清鎖內讀待成交買單（C-B1），並帶出批次標示（ADR-0034 補充一 S-3 第 7 點）；
 - B2 之後還要多讀一項；
 - S-3 沒有把它列為任何一方的擁有項。
 - 裁定：列為共用面，不歸任何一方，比照 `BATCH_LEFT_PLANNED_SQL`。
 - 只准加法：可以在 `EmergencyExitState` 加有預設值的欄位；
 - 既有三個查詢的條件與排序不變；
 - 隨 C-B7 經 `_BATCH_SELECT` 增加的批次欄位，不算改條件。
 - N-168 在出清鎖內讀待成交買單的查詢，**不得**放進 `_read_exit_state`。要放在另一個函式，由 `commit_emergency_exit` 用同一個 conn、在同一個 transaction 內呼叫。
 - 理由：放進去的話，N-171 的 `read_in_flight` 會經由 `exits` 帶出 N-168 的買單資料，同一份回應裡的買單就有兩個來源。
 - `/today` 上：N-171 只用 `exits` 的 open 批次與出清列；N-168 的清單只出自 `entries`。
2. `plan_emergency_exit`／`classify_exit_batches`：
 - `classify_exit_batches` 由 N-171-A 抽出，行為零差異（ADR-0039 Decision 3），歸 N-171 擁有。
 - N-168 不得把買單或 W-B1 的邏輯加進 `classify_exit_batches`，也不得加進 `plan_emergency_exit` 的覆蓋與分支判定（C-B2）。
 - N-168 在出清路徑上的改動，限於兩處：
 - `commit_emergency_exit` 內的戳記寫入與買單讀取；
 - `emergency_exit` 在 commit 之後組 message 與 `labeled_batches`。
 - 兩邊在同一段程式上的文字衝突，由後合併的一方解決。出清回應的既有斷言，只准出現 E-8 的 D1、D2。
3. W-B2L 的單一來源：
 - `PendingExitRow` 與群組 B 各行的 `entry_before_exit_note`，只能從 `_lines` 產生的 `DirectiveLine.entry_before_exit_note` 複製（ADR-0039 Decision 9）。
 - `app/` 內，`ENTRY_BEFORE_EXIT_NOTE` 只能在 N-168 的套用規則中被引用，而這個規則只由 `_lines` 呼叫。N-171 不得讀取 `labeled_batches` 自行判斷。
 - 後合併的一方，在 merge 之後補一條整合測試：標示批次上的出清列，在 `pending_exit_directives` 與對應的 `PendingExitRow` 上，帶有相同的 W-B2L。
4. SEAM 登記檔：依 E-6 第 1 點各寫各的檔，不構成衝突。
5. 下列交集已有規則，不是新的衝突點：
 - `_to_response`、`TodayResponse`、`types.ts`：各加各的加法欄位，相鄰行衝突在 merge 時解決（S-3「允許」）；
 - `same_day_warnings`：只有 N-168 會改（ADR-0039 補充一 T21）；N-182 建立的部分受 E-1 約束；
 - `_settle_pending`：只有 N-168 改 warnings（W-B3）；N-171-A 不動（ADR-0039 補充一 S-3 第 3 點）。
6. N-168 內部的同一快照要求：ENTRY 排除 W-B6 列時，用的是同一次 `read_in_flight` 的 `entries` 的 directive id 集合，不得在鎖內另讀戳記（R-4，與 E-2 第 3 點同理）。

### E-12 S-7 增列檢查項
- QB-12：適用於切面之後的每一個 PR，含 N-182、N-171-A／B、N-168 與 E-10 的機制 PR。
 - golden 零 diff：`git diff 5c2d3e1 <merge 後 head> -- apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json` 為空，且 `GOLDEN_SHA256` 未改。
 - PR 只改自己的登記檔。
 - 每筆差異都符合以下各項：
 - 在 E-8 清單內，或附有 E-7 第 3 點的書面核准；
 - `source` 指向已定稿的條文；
 - `after` 與定稿逐字相符，由 qa 用情境的值手算渲染結果核對；
 - message 差異只有附加；
 - `remove` 有明文的移除規則。
 - `added_keys` 都是擁有者 ADR 所定義的回應鍵，只登記最外層，且與 golden 不撞名。
 - `filled` 的每一項都有以精確值斷言內容的測試，而且這些測試在 golden 情境上執行。
 - E-4 第 1 點 (a) 的不變式斷言零 diff：逐行檢查 `tests/test_playbook_today_seam.py` 的 diff。
 - PR 說明逐條列出差異 id、新增鍵、切面期斷言的調整，並與登記檔一一對應。
 - N-182：登記為空；T1、T2、T4、T5 零改動；在 merge 後的 head 上綠燈。
- QB-13：適用於 N-168 與 N-171-A 的 PR。
 - E-11 第 1 點：`_read_exit_state` 既有三個查詢的條件與排序零 diff；N-168 的出清鎖內買單查詢不在 `_read_exit_state` 裡。
 - E-11 第 2 點：`classify_exit_batches` 與 `plan_emergency_exit` 的覆蓋判定沒有讀取買單。
 - E-11 第 3 點：
 - grep `ENTRY_BEFORE_EXIT_NOTE`，在 `app/` 內只出現在 `_lines` 的套用規則中；
 - N-171 各行的 note 只從 `DirectiveLine` 複製；
 - 後合併的一方已補上整合測試。
 - E-11 第 6 點。


（coordinator 2026-11-04 附加：釐清三原文轉存自 `work/reviews/2026-11-04-ADR0035補充四釐清三-tech-architect.md`）

## 釐清三（tech-architect 2026-11-04，回應 `work/reviews/2026-11-04-N182補件交件-dev-lead.md` 第四段第 3 點）：`_settle_pending` 開頭的 `pending_directives(on_or_before=as_of)` 與 `_with_stale_exit_notes` 內的 `pending_directives()` 屬於結算自身的讀取，不是 R-4 的在途讀取點；條件是這類讀取只出現在 `_settle_pending` 及其呼叫的 helper 內，結果只進 `SettlementResult`，不得被 N-171、N-168、N-182 的任何在途清單、W-B6／W-B6b、ENTRY／A 的排除所引用；在結算內為在途清單新增讀取，仍屬 R-4；qa-reviewer 依 QB-7 grep 時，以這兩處為僅有的白名單，第三處即 BLOCKING。


---

（coordinator 2026-11-04 附加：釐清四原文轉存自 `work/reviews/2026-11-04-ADR0035補充四釐清四-tech-architect.md`）

## 釐清四（tech-architect 2026-11-04，N-171-A 後端交件的 commit 順序、NB-6 原子單位、固定項註解與 merge N-182）

- 性質：釐清 S-3、S-6 的 R-5、S-7 的 QB-6，以及釐清二 E-10 第 2、3 點；E-14 另外釐清 ADR-0039 v2 Decision 13 的原子單位。不改任何固定項，不改 S-6 的判準本身，不改 golden。
- 依據：`work/reviews/2026-11-04-N171A後端交件-dev-lead.md` 解讀點 1、2、7；ADR-0039 v2 Decision 1、11、13 與補充一 S-1 第 4 點、S-7 第 2 點；釐清二 E-6、E-9、E-10、E-11。
- 程式位置：2026-11-04 工作樹 `product/stock-desk`（已含 N-182）；N-171-A 分支的 commit 依交件所列，由 qa-reviewer 以 `git diff` 核對。

### E-13 機制 commit 的位置（E-10 第 2、3 點）
1. E-10 要求機制先合，或以獨立 commit 先行建立，目的是：機制要在擁有者尚未填入任何切面期項目、也尚未新增任何回應鍵的程式狀態上建立和驗收。這樣「登記為空時與改寫前等價」與變異測試才有意義，機制也不會被寫成遷就本案的填入值。
2. 因此，「N-171-A 的 feat commit」指會改變 golden 情境中任何回應的 commit，也就是：填入 2.2(a) 的清單、填入 `InFlightRead` 的任一部分、新增回應鍵，或改變既有欄位值。只改動 golden 情境以外路徑的 commit，或行為零差異的 commit，不在此列。
3. N-171-A 分支的順序 `0f02cf3`（refactor）→ `909899b`（C17′）→ `01e99cb`（機制）→ `460413d`（區塊），依第 2 點可以接受。以下條件由 qa-reviewer 列為 BLOCKING：
 - (a) `git diff 0f02cf3^ 909899b -- apps/stock-desk/backend/tests/test_playbook_today_seam.py apps/stock-desk/backend/tests/seam_helpers.py apps/stock-desk/backend/tests/golden/` 為空。
 - (b) `git diff --stat 909899b 01e99cb` 只列出 E-10 第 1 點的三個路徑；`app/` 與 golden 零 diff。
 - (c) `approved/n171a.json` 首次出現在 `460413d`。
 - (d) `909899b` 沒有改 `POST /settle` 既有測試的斷言（SEAM-T6、E-9 第 2 點末項）。golden 的 9 個回應中沒有 `POST /settle`，C17′ 不在 golden 情境內。
 - (e) dev-lead 在 `0f02cf3`、`909899b`、`01e99cb` 上各跑一次 SEAM-T1～T7，結果附在 PR 說明；qa-reviewer 只核對紀錄與 diff。
4. 不得以 rebase、互動式改寫或 force push 調整已推送的順序。
5. 機制在 N-171-A 的 PR 內，N-168 的合併因此依賴 N-171-A 先合。若 N-168 先通過自己的閘門：
 - dev-lead 從 `origin/product/stock-desk` 開新分支，`git cherry-pick 01e99cb`，以單獨的 test-only PR 先合，等同回到 E-10 第 2 點的原路徑；N-171-A 之後再 merge product。
 - cherry-pick 到新分支不是 rebase，也不改動任何已推送的分支。
 - N-168 不得自帶一份機制。

### E-14 NB-6 的原子單位（ADR-0039 Decision 13）
1. Decision 13 要求放在同一個 commit 的，是 NB-6 第 2 段的四件東西：後端常數、前端鏡射、逐字守門測試、字面絆線測試。目的是在任何一個 commit 上，前後端的第 2 段都不會是不同版本。區塊本體不在這個單位內；區塊與 NB-6 的關係，由「在 N-171 的同一個 PR 內」約束。
2. 區塊 `460413d` 與 NB-6 `508a976` 分成兩個相鄰的 commit，可以接受，不要求合併。以下條件列為 BLOCKING：
 - (a) `508a976` 同時含有：`wording.py` 的 `EXIT_RESULT_UNCONFIRMED_BADGE`、`playbookView.ts` 的 `EXIT_FAILURE_WORDING.body[1]`、後端守門測試、`exitWordingMirror.test.ts`、字面絆線測試。
 - (b) `git diff 0f02cf3^ 460413d` 沒有動到上列常數與鏡射。也就是說，`460413d` 上前後端都是第一版，彼此一致。
 - (c) 第二版指向區塊。從 `508a976` 起到前端元件 commit 之前，分支上的字面指向一個尚未渲染的區塊。因此：
 - 前端區塊元件必須 commit 在同一條分支，進同一個 PR（Decision 11）；
 - 在元件完成、S-A～S-D 完成、風控書面終核完成之前，分支不得合進 product，也不得部署。
 - (d) PR 以 merge commit 合進 product。不 squash，因為 squash 會抹掉 E-13 要求的獨立機制 commit；也不 cherry-pick 個別 commit 進 product 或任何部署分支。
3. 不採的做法：若要讓每個 commit 都同時含區塊與第二版，在不 rebase、不 force push 的前提下，唯一的做法是從 `01e99cb` 另開新分支，以 `git cherry-pick --no-commit 460413d 508a976` 合成一個 commit，再重做 merge 與整個審查，舊分支棄用。成本高，安全上沒有增益，不採。

### E-15 固定項上的註解（S-3、QB-6、2.2(d)）
1. S-3 的固定項約束的是契約：名稱、型別、預設值、簽名、呼叫次數，以及 2.2(d) 要求的「註解寫明擁有者與 ADR 條號」。描述欄位內容的註解文字不屬於契約，但必須與 accepted ADR 一致。QB-6「固定項零 diff」依以下口徑判定：
 - 在 `git diff 5c2d3e1 <head>` 中，落在固定項宣告上的每一個 `-`／`+` 行，去掉前導空白後都以 `#`（Python）或 `//`（TypeScript）開頭；
 - 名稱、型別、預設值、簽名零 diff；
 - 擁有者與 ADR 條號仍然寫在註解裡。
2. 誰可以改：
 - 固定欄位的擁有者行，也就是緊接在該欄位宣告上方、寫 `Owner ...` 的那幾行：由該欄位的擁有者修改，只能改成 accepted ADR 已寫明的語意，不得新增語意。
 - 三個清單共用的說明段，也就是第一個 `Owner` 行之前的那段：由讓它變得不正確的那個 PR 修改。
 - 他方欄位的擁有者行：一律不改。
3. 本次裁定：
 - (a) `models.py` 與 `types.ts` 中，`pending_exit_directives` 的擁有者行寫的是「unsettled EMERGENCY sells that still cover」。這和 ADR-0039 v2 Decision 1「三類都含」不符，是 v1 的殘留，**要改**。
 - 在 N-171-A 的 PR 內，以一個只改註解的 `docs:` commit 落地，並在交給 frontend-engineer 之前完成。
 - 改後要寫明：三類都含；只限 open 批次；排序；這是原始資料，不得用來渲染文字（ADR-0039 補充一 S-1 第 4 點、C22）。
 - (b) `api/playbook.py` 的擁有者行只寫「Owner N-171 (ADR-0039 Decision 1).」，沒有不符的描述，不改。
 - (c) `types.ts` 共用說明段的 "No view renders them yet." 描述的是三個清單。對 `pending_exit_directives` 來說這句永遠成立，所以 N-171-A 不改，改由 (a) 的擁有者行寫明「不渲染」是永久的。日後 N-168 的 PR 若讓畫面渲染它的任一清單，由 N-168 改這一句。
4. 建議文字（英文；可依行寬換行，語意不得增減；`types.ts` 用 `//:`，內容相同）：
     #: Owner N-171 (ADR-0039 Decision 1): every unsettled EMERGENCY sell on an open
     #: batch -- covering, stale and unclassified alike -- by symbol, batch_no,
     #: execution_date, id. Raw data: no view renders text from it (補充一 S-1 第 4 點).
5. 合併衝突：各擁有者改各自的擁有者行，相鄰行在 merge 時可能產生文字衝突。
 - 不構成 S-6 的 R-5：衝突區塊裡只有註解行有差異；或固定項的程式行兩邊都沒改，只是落在衝突區塊之內。解法是：固定項的程式行與 `5c2d3e1` 逐位元相同，各擁有者行取自各自的分支，並在 PR 說明列出。
 - 構成 R-5：任一邊改到了固定項的程式行。

### E-16 N-171-A merge 含 N-182 的 product（S-5 第 3 點的具體檢查）
1. 固定項
 - N-182 在 `app/` 的改動位置：
 - `store.py`：`BATCH_LEFT_PLANNED_SQL`、`EntryBeforeExitRead.blocked`、`_read_entry_before_exit`、claim 路徑；
 - `service.py`：`g1_blocked_entries`、`same_day_warnings`、`evaluate_today` 傳入 `blocked`；
 - `wording.py`：W-B6b。
 N-182 沒有碰 `models.py`、`api/playbook.py`、`types.ts` 的固定宣告。
 - `store.py` 中，`PendingExitRead`（N-171）、`EntryBeforeExitRead`（N-168／N-182）、`InFlightRead`（固定）、`_read_pending_exits`、`_read_entry_before_exit` 交錯排列，衝突區塊可能跨過 `InFlightRead`。依 E-15 第 5 點處理：`InFlightRead` 與 `read_in_flight` 必須與 `5c2d3e1` 逐位元相同。
2. 單一讀取點
 - 兩條路徑各只有一處 `self._store.read_in_flight()`。
 - N-171 的區塊只讀 `in_flight.exits`，N-182 的 `blocked` 只讀 `in_flight.entries`，兩者用的是同一個 `in_flight`。
 - SEAM-T3 綠燈。
3. SEAM-T4
 - merge 之後，`_read_entry_before_exit` 會實際執行 SELECT。對沒有登記在 `filled.in_flight` 的 `entries`，T4 仍斷言為預設值。
 - 若轉紅，視為 merge 引入的回歸。不得把 `entries` 加進 `n171a.json` 的 `filled`：E-6 第 1 點規定只能改自己的登記檔，而 `entries` 也不屬於 N-171。停住，送 tech-architect。
4. SEAM-T2：登記檔只有 `n171a.json`（`deltas: []`）時，必須綠燈。轉紅時依 E-9 第 4 點末項處理，不得以登記差異解決。
5. 字面掃描
 - merge 之後，N-171-A 的整檔掃描（`test_c6_*`、`test_i_*`、「應」的豁免）與 N-182 的守門測試，會互相掃到對方新增的常數。
 - 任一條轉紅時，停住：字面問題送風控，掃描範圍問題送 tech-architect。
 - 不得改對方的字面，不得改對方測試的斷言（`tests/test_playbook_pending_entry_blocked.py` 受 E-1 第 3 點保護），也不得自行收窄掃描範圍或放寬白名單。
6. E-11／QB-13
 - `_read_exit_state` 的三個查詢，與 `5c2d3e1` 零 diff；
 - `_read_pending_exits` 不讀買單，也不引用 `BATCH_LEFT_PLANNED_SQL`；
 - QB-7：`app/` 內的 `pending_directives(` 只有釐清三白名單上的兩處；`settle_on_request` 不直接呼叫它。
7. merge 之後的 head
 - 重跑 S-5 第 3 點的全部 job；
 - qa-reviewer（含 Codex）重審 merge commit 的衝突處理，以及 S-7、QB-12、QB-13、QB-14。

### E-17 S-7 增列檢查項
- QB-14（N-171-A 的 PR）：
 - E-13 第 3 點 (a)～(e)；
 - E-14 第 2 點 (a)～(d)；
 - E-15 第 1、3、5 點；
 - E-16 全部。


---

（coordinator 2026-11-04 附加：釐清五原文轉存自 `work/reviews/2026-11-04-N171A結算句golden差異核准-tech-architect.md`）

## 釐清五（tech-architect 2026-11-04，`SETTLEMENT_NOTHING_PENDING` 改寫在 SEAM golden 上的差異登記與字面替換連動）

- 性質：釐清 E-6、E-7 第 3 點、E-9 第 2 點、E-11 第 5 點與 E-12 QB-12；E-20 訂定「字面替換的連動」處理規則，適用切面之後每一個 PR。不改任何固定項，不改 S-6 判準，不改 golden，不授權重錄。
- 依據：`work/reviews/2026-11-04-N171A最終字面終核-風控.md` 第二節逐條意見第 1 項（required）與第四節第 2 點；ADR-0039 Decision 17、附錄 A C18、附錄 B T21、補充一 S-3 第 3、4 點；補充四 SEAM-T6；釐清二 E-5～E-9、E-11；釐清三；釐清四 E-13、E-14。
- 核准檔：`work/reviews/2026-11-04-N171A結算句golden差異核准-tech-architect.md`。

### E-18 擁有者與範圍
1. `SETTLEMENT_NOTHING_PENDING` 的改寫是 N-171-A 的合併條件，差異登記在 `approved/n171a.json`，不另立擁有者檔。
2. E-9 第 2 點「`deltas` 必須為空」改為：`n171a.json` 的 `deltas` 恰好是 N171A-D1～D3 三筆，經 E-7 第 3 點核准。出現第四筆時，仍依 E-9 第 2 點停住。
3. 範圍只限 `wording.py` 中這一個常數的值：
 - 常數名不改；
 - 新值是一個不含佔位符的靜態字串，在 `settlement.warnings` 中仍只佔一個元素；
 - `_settle_pending`（含輸出這句的分支與其條件）、`settle_pending`、`settle_on_request` 零 diff；
 - 不新增讀取、分支或日期判斷。
 若定稿需要佔位符、條件變體、拆成多個元素，或需要知道「有沒有未到期的列」，就超出本釐清：PR 停住，送 tech-architect。這類需求會觸及補充一 S-3 第 3 點、SEAM-T6 與釐清三。
4. 與既有條文不衝突：
 - ADR-0039 Decision 17、C18、T21 所稱的 `warnings`，是 `/today` 頂層的 `TodayResponse.warnings`，不含 `settlement.warnings`。頂層 `warnings` 仍須零 diff。
 - 補充一 S-3 第 3 點與 E-11 第 5 點約束的是 `_settle_pending` 的程式與新增句子。替換既有常數的值，只在本條範圍內例外；N-171-A 不得以此為由，在結算 warnings 上新增、移除或重排任何句子。
 - 補充一 S-3 第 4 點「不得同時有 `SETTLEMENT_NOTHING_PENDING`」以識別名約束，改值之後照樣成立。
5. 不採獨立先行 PR：機制 `01e99cb` 在 N-171-A 的 PR 內。先行 PR 須先走 E-13 第 5 點，三個 PR 串行，安全上沒有增益。

### E-19 三筆差異與落地方式
1. 三筆差異如下：

 | id | scenario | body | path | op | before |
 |---|---|---|---|---|---|
 | N171A-D1 | after_exit | today | ["settlement","warnings",0] | replace | "T+1 結算：目前沒有待結算指令。" |
 | N171A-D2 | authored | today | ["settlement","warnings",0] | replace | 同上 |
 | N171A-D3 | authored | today_again | ["settlement","warnings",0] | replace | 同上 |

 - `after` 為風控逐字核可的定稿，三筆相同。
 - `source` 寫風控終核與逐字核可檔的路徑。
 - `approval` 寫核准檔的路徑。
2. 原子單位：只在風控逐字核可檔存在之後，以**一個 commit** 同時落地以下三件：
 - (a) `wording.py` 該常數的值，以及它的 `#:` 註解；註解寫明輸出條件與風控出處；
 - (b) `n171a.json` 的三筆 `deltas`：`after` 逐字等於定稿，`source` 已填入核可檔路徑；
 - (c) `tests/test_playbook_wording.py` 新增這個常數的逐字守門測試。
 該 commit 上 SEAM-T1～T8 全綠。`approved/` 下不得留有任何佔位符。不得 rebase、不得 force push；PR 仍以 merge commit 合併（E-14 第 2 點 (d)）。
3. 預期不受影響：`after_exit.today_next_day`、`after_exit.exit`、`after_exit.exit_repeat`、`unauthored` 的三個回應。實際 diff 多出或少掉任何一處，PR 停住。
4. 與 N-168 的關係：N168-D5 在 `after_exit.today_next_day.settlement.warnings`，與 D1～D3 不在同一個 list。N-168 若在 D1～D3 所在的 list 上出現差異，依 E-6 第 4 點停住，由 tech-architect 裁定。

### E-20 字面替換的連動（測試）
1. 以識別名引用常數的斷言：零 diff，自動跟著變，不算斷言改動。
2. 該常數本身的逐字守門測試（斷言常數等於某個字面）：新增，或只把字串字面整條換掉，都屬於字面替換的連動，不算 SEAM-T6 或 E-4 所指的斷言改動。要放在 E-19 第 2 點的同一個 commit，並在 PR 說明列出。
3. 其他測試若以完整字面寫死舊句：只准把舊字串整條換成新定稿。斷言的欄位、運算子、位置與筆數都不得改。放在同一個 commit，並在 PR 說明逐條列出。
4. 以子字串、前綴、關鍵詞或否定式（例如 `in`、`not in`、`startswith`）斷言舊句內容的，屬於語意斷言，不得當成連動處理，依 E-7 第 3 點送核。
5. golden 不適用本條，只能依 E-6 登記。
6. 前端目前沒有這句的鏡射，`SettlementPanel` 原樣渲染。以識別名指涉的註解不必改。日後若新增鏡射，比照 Decision 13 的原子單位。
7. 字面整檔掃描與禁用詞測試（含 `test_c6_*`、`test_i_*`）若轉紅：停住送風控，不得收窄掃描範圍或放寬白名單。

### E-21 `POST /settle` 現況（讀碼）
- SEAM-T6 所指的既有測試（`test_api_playbook.py` 的 settle 三條，以及 `/today` 結算那一條）都不斷言 `warnings`，零 diff。
- N-171-A 新增的 `test_playbook_settle_on_request.py` 以識別名引用（`:111`、`:214`），零 diff。
- `:376-381` 是 `SETTLEMENT_UNAUTHORED_NOTE` 的逐字守門測試，不是本句，不改。
- 寫死本句的地方只有 golden 那 3 處。

### E-22 S-7 增列檢查項
- QB-15（N-171-A 的 PR）：
 - `n171a.json` 的 `deltas` 恰好是 N171A-D1～D3，內容與 E-19 第 1 點逐欄一致；`after` 與風控核可檔逐字相同；`approved/` 下 grep `<<` 為 0。
 - E-19 第 2 點的三件東西在同一個 commit。
 - `service.py` 中 `_settle_pending`、`settle_pending`、`settle_on_request` 零 diff。該 commit 的 `wording.py` diff 只有這個常數與它的註解。常數名不變，`app/` 內 grep `SETTLEMENT_NOTHING_PENDING` 的命中數與改動前相同。
 - golden 零 diff，`GOLDEN_SHA256` 未改；頂層 `warnings` 零 diff（C18）。
 - 測試 diff 只有 E-20 第 2、3 點所允許的部分；`test_api_playbook.py` 零 diff。
 - PR 說明列出 D1～D3 與 E-20 的每一處連動。
