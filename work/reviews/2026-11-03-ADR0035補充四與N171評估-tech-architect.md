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
