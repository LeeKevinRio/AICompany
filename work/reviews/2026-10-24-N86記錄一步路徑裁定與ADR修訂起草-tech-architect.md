# N-86 Q-A～Q-H 裁定與 ADR-0027 記錄一步路徑批起草

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
Q-A 到 Q-H 都已裁定，ADR-0027 的修訂落字稿也起草好了（N86-1～N86-19）。我沒有寫檔、沒有跑指令，沒有讀 `.env`，也沒有碰 `*.db`。
- **Q-A 採甲′，也就是修改後的甲，不完全照 dev-lead 原案**：
  - 範圍快照只列「本 run 還有待寫 claim 的範圍」，已寫入的範圍不再列入。
  - 「已寫入」以（範圍, `claim_id`）為單位，`late=1` 也算已寫入，判定放在 A-25 交易內。
  - L837 不改成「跟 S 全部 run 的快照聯集比對」。改法是在 `forecast_run` 新增一欄 `no_pending_scopes_json`，記下這次沒列進快照的其餘範圍。L837 拿「快照 ∪ 這一欄」比對，揭露的意思和原本完全相同。
- **不需要改事先宣告**，quant 的 v0.29 不受影響；V27-02 的三點不變式也沒有被觸及。
- **CEO 層級全部是「否」**，各項都沒有放寬面。
- **送風控**：建議做逐字確認。原因有兩個：L837 是 §4.2 的揭露項；另外，相對「照字面整步中止」的讀法，缺日列會變少，要請風控確認這不算放寬。

## 各部門回報
- **tech-architect**：依 HEAD 版 ADR-0027（L 行號都是 HEAD 的）、事先宣告 L1836-1846（V27-02）、L1894-1902（V15-04），以及 `scheduler.py:647,672,686`，裁定如下。

### 一、Q-A～Q-H 逐題裁定

**Q-A（最優先）：修改採用甲，記為甲′**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 甲（dev-lead 原案：快照只含未寫範圍，L837 改成跟 S 全部 run 的聯集比對） | D-3 run_end、D-8、D-11.4 都不用改字；FL-76 (d) 自然成立；不加 outcome 值 | 聯集比對會改變 L837 的意思：22:10 寫完、23:10 前移出自選的標的會被算成「不一致」。若聯集也含之後的 run，又會遮掉真正的不一致 | §4.2 揭露的意思實質改變，要送風控實審 |
| **甲′（採用）：甲，加上 `forecast_run.no_pending_scopes_json`，「已寫入」以（範圍, `claim_id`）為單位** | 甲的優點全部保留；L837 跟「同一 run 讀到的完整範圍」比對，意思不變；新 claim 或 rules 只升 PATCH 時，不會撞 UNIQUE，也不會重複寫 | 多一個欄位和一組寫入驗證；快照的語意從「當下完整範圍」改成「本 run 要寫的範圍」 | 低。S 的快照聯集不變，理由在 N86-2「對既有條文的效果」 |
| 乙（快照列全部範圍，另加計數欄） | 快照的語意不變 | D-8 第 3 項會把「只跳過、沒寫入」的 run 當成決定 run，發生帳目矛盾就停擺；D-8、`basis_json`、D-11.4、run_end 驗證全部要改 | 改動面最大，可能碰到 V27-02 |
| 丙（全部已寫入時不寫 run，attempt 加值） | D-8 本來就不收這種 attempt | 部分已寫入的情形仍然要甲或乙；要加 outcome 值 | 不能單獨成案 |

**為什麼採甲′、不採原本的甲**：
- 只有快照本身能證明當時的排程範圍。庫存和自選不能事後還原（L847），所以不能拿事後資料重建這個範圍。
- 被排除的範圍，一定在較早某個 S 的 run 的快照裡（因為是那個 run 寫入的）。所以 S 的快照聯集跟「每次都列完整範圍」的讀法相同。這讓 D-8 N-64 句末、V27-02 第 1 點、D-11.4 `not_in_schedule` 都維持成立。
- 連帶效果：第 (1) 點不必加 outcome 值；`RecordStepResult` 正常返回時「有 T、沒有 run」仍然不會出現，這次把它明定為不變式。

**Q-B（G-3、G-4 閘門放哪裡）：修改採用**
- 放在前置段的一開始：開始列寫入之後、讀市場 DB 與判定候選 T 之前。
- 不成立時拋 `WriteGateClosedError`，寫 `error_before_run`（`candidate_t` 為 null），發 E-3d。
- 理由：
  - 維持 D-3 L284「每一次排程記錄一步恰好一列」開始列；
  - 不新增 outcome 值，也不新增 `reason` 值，所以不動事先宣告的九個值；
  - 閘門成立之前，不讀市場 DB，也不觸發 (ii) 的強制重抓（重抓會經 `service.py` 寫入）；
  - fail-closed，而且會被看見。
- 不採的放法：
  - 放在開始列之前：違反 L284；
  - 決定 T 之後正常返回：要加 outcome 值，還會連動 `reason`；
  - 逐範圍拒寫：閘門例外不在 `RECORD_SCOPE_REFUSAL_TYPES` 內，會整步 `error`。

**Q-C（市場 DB 沒有任何 ok bars run）：採用 fail-closed**
- 拋 `NoCandidateSessionError`，記 `error_before_run`（`candidate_t` 為 null），發 E-3d。
- 不放寬 `inputs_not_ready` 的「`candidate_t` 必須非 null」：那樣會破壞 D-8 依 (a) 歸屬的方式。

**Q-D（Q4 的「本次執行的 T」）：採用**
- Q4 所說的 T，必須四項 (i)～(iv) 都成立；`candidate_t` 只是稽核值。
- T 交回編排函式的方式：編排函式建立一個可變的進度物件（暫名 `RecordProgress`，只有欄位 `t`），傳給記錄一步；記錄一步在四項都成立的當下設定 `t`。
- 不採「在例外物件上掛屬性」：
  - 會違反 FL-74 (b)「except 區塊內只呼叫 end 寫入函式，並以不帶參數的 `raise` 結束」；
  - 等於去改別人的例外物件。

**Q-E（`inputs_not_ready` 的 end 寫入失敗）：採用「補寫」**
- 這次寫入屬於前置段，由前置段的 except 接住，補寫一列 `error_before_run`（`candidate_t` 為該候選 T），再往外拋。
- 兩種讀法的 `reason` 都是 `record_start_failed`。補寫後可以用 `candidate_t` 精確歸屬（D-8 的 (a)），不必依賴時間窗 (b)，還多留下 `error_class`。
- L287 會改字，使它和 L1047 一致。

**Q-F（FL-74 (b)「單一函式」與 FL-76 (p) 的 AST 條件）：採用**
- FL-74 (b) 的「單一函式」讀成「範圍迴圈所在的那個函式」，補字澄清。
- (p) 用結構辨識，不靠名稱：
  - 前置段函式 ＝ 唯一呼叫 `error_before_run` end 寫入函式的函式；
  - 範圍迴圈函式 ＝ 唯一呼叫中止用 run_end 寫入函式的函式；
  - 兩個 end 寫入函式各只有一個呼叫點。
- 另外補上 dev-lead 提的 c、e、f 三點：
  - A-25 commit 之後，前置段只回傳；
  - 範圍迴圈函式的第一個陳述式就是包住迴圈的 try；
  - 開始列的寫入不在任何 try 之內。
- 「重放執行函式不讀不寫」改用呼叫點白名單判定，重放執行函式還不存在時也測得到，不用 skip 或 xfail。

**Q-G（「已寫入」的判定單位）：採用（範圍, `claim_id`）**
- 判定的紀錄：`trigger=scheduled`、`data_as_of=T`、`supersedes_id IS NULL`，含 `late=1`。判定在 A-25 交易內。
- 用 `claim_id`、不用 M-6 鍵：rules 只升 PATCH 時 `claim_id` 不變、`rules_version` 會變，用 M-6 鍵會讓同一個 claim 寫兩筆。
- 範圍的寫入交易只寫待寫的 claim。
- N-84（新 claim 的缺日義務從哪一日開始）不在本批。

**Q-H（某個 `scope_kind` 在聯集中沒有任何範圍）：採用「沒有義務」**
- 有 S 的 run、但聯集裡沒有該 `scope_kind` 的範圍時，該 claim 在 S 沒有缺日列，也不算帳目矛盾。
- 這正是 V27-02 第 1 點字面的直接結果（聯集是空的就沒有列；有 run 就不寫 `'*'`），方向判為不變。
- 照實並陳：相對 D-8 第 2 點首句的字面讀法，這一天這個 claim 沒有列。這一點和 F-3 分母的關係併入 N-85。

### 二、ADR-0027 修訂落字稿

**通則**
- 錨點都已在 HEAD 用 Grep `-o` 實測，恰好 1 處。
- 新文字不含其他錨點。
- 落檔順序：N86-1 到 N86-17 依檔案順序套用，N86-18、N86-19（修訂紀錄）最後套用。修訂紀錄會引用被取代的原文，若先落修訂紀錄，錨點就不再唯一。
- 全部同一個 commit，不依附事先宣告的版次。

**N86-1｜D-1 `errors.py` 列（L238）｜句中接字｜補定義（不變：補登 D-8 已使用的 `GapAuditRunInconsistencyError`，它目前不在 D-1 列內；另新增兩個型別）｜CEO：否**
```text
old: `LabeledThresholdSnapshotIncompleteError`（N-46）；另有
new: `LabeledThresholdSnapshotIncompleteError`（N-46）、`GapAuditRunInconsistencyError`（N-64；D-8 第 2 點）、`NoCandidateSessionError`（N-86；D-7 第 3 點）、`WriteGateClosedError`（N-86；D-7 第 7 點 N-86 子點）；另有
```

**N86-2｜D-3，在 L282 錨點行之後插入新子點｜補定義（收緊：新增持久化與寫入驗證）｜CEO：否**
```text
錨點（保留）:   - （r2，A-29）`forecast_run` 與 `forecast_scope_snapshot`：在同一個交易內寫入（A-25）。
插入:
  - （N-86；tech-architect 2026-10-24；dev-lead 2026-10-24 查證第 (2) 點）**範圍快照只含本 run 尚未寫入的範圍**：
    - 記錄一步讀一次排程範圍的來源（大盤、族群、庫存、自選），得到本 run 的排程範圍。A-25 交易內再做兩次唯讀查詢：已登記的前瞻 claim（`forecast_claim_registry` 中 `kind = forward` 的列；下稱本 run 的 claim 集合），以及 `trigger = scheduled`、`data_as_of = T`、`supersedes_id IS NULL` 的既有紀錄的 (`scope_kind`, `scope_key`, `claim_id`)，含 `late = 1` 的紀錄。
    - **待寫**以（範圍, claim）為單位：本 run 的 claim 集合中，`scope_kind` 與該範圍相同、而該範圍還沒有它的既有紀錄的 claim，是該範圍的待寫 claim。以 `claim_id` 判定，所以 rules 只升 PATCH（D-10 第 2 點沿用原 claim）時不重寫。
    - **範圍快照**（`forecast_scope_snapshot`）只列至少有一個待寫 claim 的範圍；範圍的計算與寫入交易只寫入該範圍的待寫 claim。範圍快照因此是「本 run 要寫的範圍」，不再是「當下的完整排程範圍」；同一 T 的第一次執行兩者相同。
    - **新增欄位 `forecast_run.no_pending_scopes_json NOT NULL`**：本 run 的排程範圍中其餘的範圍（沒有待寫 claim，含所屬 `scope_kind` 沒有任何 claim 的範圍）。JSON 陣列，每一項恰為 `{scope_kind, scope_key, market, reason}`，與 `forecast_scope_snapshot` 的列同形，依 (`scope_kind`, `scope_key`, `reason`) 排序、不重複；沒有時為 `[]`。不含成本與股數（AV-9）。範圍快照與本欄的聯集，就是本 run 讀到的完整排程範圍。
    - **分割由寫入函式判定**：A-25 的寫入函式只接受排程範圍，在交易內自行分割，不接受呼叫端傳入分割結果。**寫入驗證**（任一項不成立就拒絕寫入，A-25 交易整個 rollback，依 D-7 第 7 點 N-66 子點記 `error_before_run`）：以與分割不同的純函式重算：範圍快照每一項至少有一個待寫 claim；本欄每一項沒有待寫 claim；兩者依 (`scope_kind`, `scope_key`) 不相交。
    - **對既有條文的效果**〔推論，已逐條核對〕：
      - 沒有 R_s 的（範圍, claim）不會因本子點被排除，所以 D-11.4 `not_in_schedule` 與 A-25「有快照、但不含這檔才算正面證據」不受影響。
      - 被排除的範圍，必定在寫入其紀錄的那個較早 S 的 run 的範圍快照內，所以 S 的全部 run 的範圍快照聯集（D-8 第 2 點 N-64 句末；事先宣告 §6.3「缺日」V27-02 第 1 點）與「每次都列完整範圍」的讀法相同。
      - D-3 `forecast_run_end` 的寫入驗證、D-7 第 7 點的 `outcome` 判定與 D-8 第 2 點 N-64、N-66 子點都以範圍快照計，不改字。範圍全部已寫入時範圍快照為空，run 照寫，end 為 `outcome = ok`、`scopes_done = scopes_missed = 0`。
      - D-3 `plan_coverage_log`「衍生計數」的不一致標的數改以完整排程範圍比對（同處 N-86 改字）。
    - **用途限制**：本欄不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定，也不是 D-8、D-11.4 所稱的範圍快照。只有 `validation.py` 的該不一致標的數與稽核工具可以讀；`audit.py`、`views`、API route 與匯出不讀（AST）。
    - 已寫入以 A-25 交易內的讀值為準。之後在範圍的寫入交易中仍撞到 M-6 的唯一索引時，`sqlite3.IntegrityError` 不在 `RECORD_SCOPE_REFUSAL_TYPES` 內，依 D-7 第 7 點 N-52 子點整步中止；不得在範圍內接住 `IntegrityError` 或「先查後跳過」。
```

**N86-3｜D-3 L287｜取代｜補定義（不變：`reason` 不變；end 列由「沒有」改為 `error_before_run`）｜CEO：否**
```text
old: 這是「記 `inputs_not_ready`」唯一的持久化處（D-8 第 2 點）。寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗。
new: 這是「記 `inputs_not_ready`」唯一的持久化處（D-8 第 2 點）。（N-86）寫入失敗時，這次寫入屬於前置段，由前置段的 `except Exception` 接住，盡力補寫 `outcome = error_before_run` 的 end（`candidate_t` 為該候選 T），再拋出原例外，記錄一步依 D-7 第 2 點標為失敗（D-7 第 7 點 N-86 子點）。
```

**N86-4｜D-3 L288｜句中接字｜補定義（不變）｜CEO：否**
```text
old: `candidate_t` 為已判定的候選 T，尚未判定時為 null；
new: `candidate_t` 為已判定的候選 T（N-86：D-7 第 3 點首句所取的 session，不論四項是否成立；只是稽核值，不是 D-7 第 2 點 Q4 的「本次執行的 T」），尚未判定時為 null；
```

**N86-5｜D-3 `plan_coverage_log` L837（§4.2 揭露項）｜取代｜不變（比對對象仍是同一 run 讀到的完整排程範圍）｜CEO：否；建議風控逐字確認**
```text
old: 與同一 run 的 `forecast_scope_snapshot`（`reason ∈ {holding, watchlist}`）不一致的標的數，在 §4.2 另列。
new: 與同一 run 讀到的完整排程範圍（該 run 的 `forecast_scope_snapshot` 與 `forecast_run.no_pending_scopes_json` 的聯集，`reason ∈ {holding, watchlist}`；N-86，D-3 `forecast_scope_snapshot` N-86 子點）不一致的標的數，在 §4.2 另列。
```

**N86-6｜D-7 第 2 點 Q4 句末（L956）｜句末接字｜補定義（收緊：決定 T 必須四項都成立）｜CEO：否**
```text
錨點（保留）: 記錄一步在決定 T 之後才失敗時，T 照樣存在，快照與 plan 只依本點其他前置條件。
接在句末: （N-86）「決定 T」指候選 T 的四項（第 3 點 (i)～(iv)）都已成立。D-3 `forecast_record_attempt_end.candidate_t` 只是稽核值，不是本點的 T：例如 (ii) 強制重抓時拋出例外，`candidate_t` 為該 session，本次執行仍沒有 T。編排函式只依第 7 點 N-86 子點的進度物件取得 T，不由例外物件、log 或 attempt 表取得。
```

**N86-7｜D-7 第 3 點（L964），接在錨點句之後、「候選 T 必須同時滿足四項：」之前｜補定義（收緊）｜CEO：否**
```text
錨點（保留）: **候選 T** ＝ 市場 DB 中最新一個有 ok bars run 的 session。
接字: （N-86）市場 DB 沒有任何 ok bars run 時沒有候選 T：記錄一步拋 `NoCandidateSessionError`（`app/forecast/errors.py`），依第 7 點 N-66 子點寫入 `outcome = error_before_run` 的 end（`candidate_t` 為 null），發 ADR-0029 E-3d；不得記 `inputs_not_ready`，也不得改用任何預設日期。
```

**N86-8｜D-7 第 7 點，在 L1050 錨點行之後、「8. **on-demand**」之前插入新子點｜補定義（收緊）｜CEO：否**
```text
錨點（保留）: 開始列本身寫不進去時（例如主 DB 無法寫入），該次執行仍記 `scheduler_down`，只能由 E-3d 與 log 察覺。
插入:
   - （N-86；tech-architect 2026-10-24；dev-lead 2026-10-24 查證）**記錄一步的函式結構、重試與執行期閘門**：
     - **函式結構**：記錄一步由入口函式依序呼叫前置段函式與範圍迴圈函式（名稱暫定）。入口函式沒有 `except Exception`，開始列的寫入在入口函式內、不在任何 try 之內；前置段函式返回之後，入口函式只能依其回傳值在 `inputs_not_ready` 時返回，否則立即呼叫範圍迴圈函式。前置段函式恰好一個 `except Exception`（本點 N-66 子點），包住開始列之後到 A-25 交易 commit 為止的全部程式（含執行期閘門、候選 T 的判定與重抓、`inputs_not_ready` 的 end 寫入）；A-25 交易 commit 之後，前置段函式只回傳。範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try；FL-74 (b) 所稱「記錄一步的單一函式」就是這個函式，不是指記錄一步只有一個函式。AST 辨識條件見 FL-76 (p)。
     - **重試與補跑遇到已寫入的範圍**：依 D-3 `forecast_scope_snapshot` N-86 子點，已寫入的範圍不列入範圍快照，範圍內只寫待寫 claim。全部已寫入時照寫 run 與 end（`outcome = ok`、0／0），`RecordStepResult` 的 `run_outcome = ok`、`failed` 為假，不發 E-3d。本點 N-52 子點的封閉清單不變；`forecast_record_attempt_end.outcome` 不加值。
     - **執行期閘門**（D-14「recorder 執行期強制」）：前置段一開始、讀取市場 DB 與判定候選 T 之前，呼叫 D-14 的閘門函式一次（與 G-7 on-demand 同一個）；G-3、G-4 或 dirdef 欄位任一不成立時拋 `WriteGateClosedError`（`app/forecast/errors.py`），依本點 N-66 子點寫 `error_before_run`（`candidate_t` 為 null），發 E-3d。閘門不成立時不讀市場 DB，也不觸發第 3 點 (ii) 的強制重抓。不得把閘門檢查放在開始列之前，也不得以正常返回略過。
     - **T 的交回**：編排函式建立可變的進度物件（名稱暫定 `RecordProgress`，只有欄位 `t`，初值 None），以關鍵字參數傳給記錄一步。記錄一步在候選 T 四項都成立的當下、任何之後可能拋例外的步驟之前設定 `t`，之後不改。記錄一步正常返回或拋出例外之後，編排函式都只依 `t` 決定第 2 點 Q4 的 T。進度物件不持久化，不傳給其他步驟；正常返回時 `RecordStepResult.t` 等於它。
     - **候選 T 的稽核值**：第 3 點首句所取的 session，在任何之後可能拋例外的步驟之前先指派給區域變數，前置段的 except 區塊以它填 `candidate_t`。
     - **`inputs_not_ready` 的 end 寫入失敗**：依本點 N-66 子點補寫 `error_before_run`（`candidate_t` 為該候選 T），再拋出原例外，E-3d 一則；補寫也失敗時記 WARNING，該嘗試沒有 end。兩種情形，稽核都記 `record_start_failed`。
     - **正常返回的不變式**：`RecordStepResult.t` 為 None，若且唯若 `run_id` 為 None（即 `inputs_not_ready`）；「有 T、沒有 run」只會以例外呈現。
     - 理由：重試與啟動補跑每個交易日至少遇到一次已寫入的範圍；照原字面，M-6 唯一索引的 `IntegrityError` 會使整步中止、記 `record_error`，並蓋掉 22:10 的 `write_rejected`／`timeout`，也使後面真正要重試的範圍不跑。只改範圍快照的內容，D-3 `forecast_run_end`、D-8 第 2 點與 D-11.4 都不必改字。閘門放在前置段一開始，是為了不新增 `outcome` 值、維持「每一次排程記錄一步恰好一列開始列」，並且在閘門成立之前不讀市場 DB、不觸發重抓。
     - 另一面（照實並陳）：範圍快照不再代表當下的完整排程範圍，要完整範圍時必須加上 `forecast_run.no_pending_scopes_json`；範圍全部已寫入的重試與補跑也各留一列 run（範圍快照為空）。閘門成立之前若已註冊 job，每次執行都寫一列 `error_before_run` 並發一則 E-3d；這幾日若在缺日稽核範圍內，記 `record_start_failed`（範圍見 D-8 第 2 點與後續追蹤清單 N-84）。沒有候選 T 時同樣每次發 E-3d。
```

**N86-9｜D-8 第 2 點 L1252 句末｜補定義（不變：與 V27-02 第 1 點的字面一致）｜CEO：否**
```text
錨點（保留）: 沒有任何 S 的 run 時（含只有記錄一步嘗試），寫 `scope_key='*'`。
接在句末: （N-86）有 S 的 run，而聯集中沒有某個 claim 所屬 `scope_kind` 的任何範圍時（例如 S 的每一個 run 讀到的庫存與自選都是空的），該 claim 在 S 沒有缺日列：沒有逐範圍的列可寫，而 `scope_key='*'` 依 D-3 `forecast_gaps` 的寫入驗證只用於沒有任何 S 的 run。這不是帳目矛盾，不拋 `GapAuditRunInconsistencyError`。
```

**N86-10｜D-14 L2354 句末｜不變（指向）｜CEO：否**
```text
錨點（保留）: recorder 不比對雜湊，也不讀決策檔。
接在句末: （N-86）在記錄一步中的位置與失敗出口見 D-7 第 7 點 N-86 子點。
```

**N86-11｜FL-74 (b)（L2517）｜句中接字｜補定義（不變）｜CEO：否**
```text
old: 逐範圍的 try 只出現在 `recorder.py` 記錄一步的單一函式內；
new: 逐範圍的 try 只出現在 `recorder.py` 記錄一步的單一函式內（N-86：範圍迴圈所在的那個函式，見 D-7 第 7 點 N-86 子點「函式結構」）；
```

**N86-12｜FL-76 首段末句（L2527）｜取代｜不變｜CEO：否**
```text
old: 各格的 run 都只含尚未寫入的範圍（重試遇到已寫入範圍的處理不在本格範圍）。
new: 各格的範圍快照依 D-3 `forecast_scope_snapshot` N-86 子點只含尚未寫入的範圍；重試遇到已寫入範圍的各格見 FL-77（N-86）。
```

**N86-13｜FL-76 (j) 後半格（L2537）｜取代｜收緊（測試）｜CEO：否**
```text
old: 單獨一次嘗試、`inputs_not_ready` 的 end 寫入拋例外 → 例外往外拋，E-3d 一則；稽核 → `record_start_failed`。
new: 單獨一次嘗試、`inputs_not_ready` 的 end 寫入拋例外 →（N-86）前置段補寫 `outcome = error_before_run` 的 end（`candidate_t` ＝ S，`error_class` 為注入的類別），例外往外拋，E-3d 一則（`exception_class` 為注入的類別）；稽核 → `record_start_failed`，`attempt_id` 為該次嘗試。補寫也拋例外 → 沒有 end，WARNING 一行，只含兩個類別名稱；稽核同樣 → `record_start_failed`。
```

**N86-14｜FL-76 (o) 句末（L2542；dev-lead 提的接縫）｜收緊（測試）｜CEO：否**
```text
錨點（保留）: (o) 寫入驗證：D-3 `forecast_gaps` N-64 子點與 `forecast_record_attempt` 所列每一項各一格違反 → 拒絕。
接在句末: （N-86）`forecast_gaps` 的欄位不接受呼叫端傳入，所以各格以兩種接縫建構：(o1) 寫入驗證的重算放在純函式內，直接以違規輸入呼叫；(o2) 整合測試以 monkeypatch 替換稽核函式中、第一次判定到寫入之間唯一經過的函式（名稱暫定），注入違規值 → 整個稽核交易不寫入、記 WARNING。重算的路徑不經過被替換的函式（AST）。`forecast_record_attempt_end` 的欄位由記錄一步傳給 store，直接以違規值呼叫 store 的寫入函式。
```

**N86-15｜FL-76 (p) 句末（L2543；AST 辨識條件）｜收緊（測試）｜CEO：否**
```text
錨點（保留）: 記錄一步前置段的 `except Exception` 與範圍迴圈的 `except Exception` 不在同一個函式內；FL-74 (b) 照舊成立。
接在句末: （N-86）辨識條件（AST）：前置段函式是 `recorder.py` 中唯一呼叫 `error_before_run` end 寫入函式的函式；範圍迴圈函式是唯一呼叫中止用 run_end 寫入函式的函式；兩個 end 寫入函式各只有一個呼叫點。前置段函式恰好一個 `except Exception`，區塊內只呼叫 `error_before_run` 的 end 寫入函式，並以不帶參數的 `raise` 結束；該 end 寫入函式只有一個 `except Exception`，區塊只記 WARNING、不 `raise`、不呼叫 `str(exc)`／`repr(exc)`。入口函式沒有 `except Exception`，開始列的寫入呼叫不在任何 try 之內，前置段函式呼叫與範圍迴圈函式呼叫之間只有依回傳值返回的分支；範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try。兩張表的讀寫以呼叫點白名單判定（只在 `recorder.py` 記錄一步、`audit.py` 與稽核工具），重放執行函式尚未存在時同樣以白名單判定，不另以 skip 或 xfail 處理。
```

**N86-16｜在 FL-76 (r) 行（L2545）之後插入 FL-76 (s) 與新的 FL-77｜收緊（測試）｜CEO：否**
```text
錨點（保留）:   - (r) 非決定 run 的帳目矛盾：同 (a)，但以直接 SQL 插入（繞過 store 的寫入驗證）把 22:10 的 end 造成 `ok` → 結果同 (k)。
插入:
  - (s)（N-86）聯集中沒有 symbol 範圍：S 只有 22:10 的 run，讀到的庫存與自選都是空的，範圍快照只有大盤與族群範圍，全部寫入 → symbol 的 claim 在 S 沒有任何缺日列（逐範圍與 `scope_key = '*'` 都沒有），不拋 `GapAuditRunInconsistencyError`，`forecast_gap_audit` 照常寫入一列。
- **FL-77**（N-86；D-3 `forecast_scope_snapshot` N-86 子點；D-7 第 2 點 Q4 與第 3 點的 N-86 句；D-7 第 7 點 N-86 子點；D-14；ADR-0029 E-3d）：fixture 同 FL-76；A、C 是 symbol 範圍（分別為 holding、watchlist），B 是族群範圍，各有 h＝3、h＝5 兩個 claim；`late_cutoff_at` 之前的各次執行都寫 `late=0`。
  - (a) 全部已寫入：22:10 寫入 A、B、C（`ok`）；23:10 → 寫入 run 與 `run_written` 的 end，範圍快照為空，`no_pending_scopes_json` 恰為 A、B、C；run_end 為 `ok`、`scopes_done = scopes_missed = 0`、`refused_scopes_json = []`；`RecordStepResult` 的 `t` ＝ S、`run_id` 為 23:10 的 run、`run_outcome = ok`、`failed` 為假；E-3d 0 則；沒有任何例外；稽核 → S 沒有缺日列。
  - (b) 部分已寫入、重試仍拒寫：22:10 寫入 A、C，B 拋 `LabeledThresholdSnapshotIncompleteError`；23:10 的範圍快照只有 B，`no_pending_scopes_json` 恰為 A、C；B 再被拒寫 → `partial`、`scopes_done = 0`、`scopes_missed = 1`；稽核 → B 各一列 `reason = write_rejected`，`run_id` 為 23:10 的 run，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = write_rejected`）；A、C 沒有缺日列；沒有任何 `record_error`。
  - (c) 逾時之後重試完成：22:10 寫入 A 後期限已到；23:10 的範圍快照恰為 B、C，全部寫入 → `ok`、`scopes_done = 2`；S 沒有缺日列。
  - (d) 週末啟動補跑與 plan 的比對：週六啟動，候選 T ＝ 週五 S，S 的範圍都已寫入 → 同 (a)；該次 plan 作業的 step_start（`targets_json` 含 A、C）依 D-3 `plan_coverage_log`「衍生計數」的不一致標的數為 0；只以範圍快照比對時會得到 2（反例斷言）。
  - (e) `late=1` 算已寫入：S 的 `late_cutoff_at` 之後，啟動補跑寫入 C（`late=1`）；再一次啟動補跑 → C 在 `no_pending_scopes_json`，不在範圍快照；C 的每個 claim 仍只有一筆原始紀錄。
  - (f) 以（範圍, claim）為單位：(f1) 22:10 之後、23:10 之前，登記 A 所屬 `scope_kind` 的新前瞻 claim Y → 23:10 的範圍快照含 A，A 的交易只寫入 Y 的紀錄，A 原有兩個 claim 的紀錄沒有第二筆，`scopes_done` 計入 A；Y 在 S 的缺日義務不在本格（後續追蹤清單 N-84）。(f2) 兩次執行之間規則只升 PATCH（同一 `claim_id`）→ A 不在範圍快照，不寫入第二筆。
  - (g) 分割的寫入驗證：(g1) 以純函式直接檢查三種違規各一格（範圍快照的項沒有待寫 claim、`no_pending_scopes_json` 的項有待寫 claim、兩者相交）→ 判為違規；(g2) monkeypatch 分割判定函式，使其回傳錯誤的分割 → A-25 交易整個 rollback，沒有 run，也沒有 `run_written` 的 end；嘗試的 end 為 `error_before_run`；E-3d 一則。
  - (h) 仍撞到唯一索引：A-25 commit 之後、A 的交易之前，以直接 SQL 插入 A 的一筆排程紀錄 → A 的交易拋 `sqlite3.IntegrityError`，整步中止：`outcome = error`、`error_class = IntegrityError`；E-3d 一則。AST：`recorder.py`、`store.py` 沒有指名 `IntegrityError` 的 except。
  - (i) 執行期閘門：VS-6 的 `verified_on` 為 None（G-4 不成立）→ 開始列照寫；假 `MarketPanelReader` 與假 `app.services.index` 都沒有被呼叫（spy）；end 為 `error_before_run`、`candidate_t` 為 null、`error_class = WriteGateClosedError`；沒有 `forecast_run`；E-3d 一則（`exception_class = WriteGateClosedError`）。G-3 不成立、dirdef 缺 `f2_variant` 各一格，結果相同。與 FL-38 的單元測試共用 fixture。
  - (j) 沒有候選 T：市場 DB 沒有任何 ok bars run → end 為 `error_before_run`、`candidate_t` 為 null、`error_class = NoCandidateSessionError`；E-3d 一則；沒有 `outcome = inputs_not_ready` 的 end。
  - (k) T 的交回：(k1) (ii) 強制重抓之後拋例外 → end 的 `candidate_t` ＝ S，進度物件的 `t` 為 None，驗證快照與 plan 都沒有被呼叫（spy），沒有 `plan_coverage_log` 列；(k2) 四項成立後、A-25 交易 commit 時拋例外 → 進度物件的 `t` ＝ S，驗證快照與 plan 依 D-7 第 2 點其他前置條件呼叫；(k3) FL-74、FL-76 與本條各格正常返回時，`RecordStepResult.t` 為 None 若且唯若 `run_id` 為 None。
  - (l) AST：`no_pending_scopes_json` 只有 `validation.py`（D-3 `plan_coverage_log` 的不一致標的數）與稽核工具讀取，`audit.py`、`views.py`、API route 與匯出不讀；進度物件只由編排函式建立、只由記錄一步設定 `t`；`forecast_record_attempt_end.outcome` 的值域恰為三值。
```

**N86-17｜待決事項 devops-sre 句末（L3306）｜不變（揭露）｜CEO：否**
```text
錨點（保留）: **devops-sre**：常駐方案；把 mark-restored 寫進整檔還原程序。
接在句末: （N-86，知悉）D-14 的 G-3、G-4 成立之前若已註冊 job `forecast_record`，每次執行都寫一列 `error_before_run` 並發一則 E-3d；是否在閘門成立之前註冊這個 job，由 devops-sre 決定。
```

**待決事項 CEO 不新增項目**：各項都沒有放寬面，表數不變（只新增欄位，沒有新增表）。

**N86-18｜修訂紀錄 N-64、N-66 批（L5328）句末**
```text
錨點（保留）: dev-lead 查證（後續追蹤清單 N-86）回覆 tech-architect 之前不實作。
接在句末: 〔已決（N-86）：見修訂紀錄「N-86 記錄一步路徑批」。本項原文不改〕
```

**N86-19｜修訂紀錄新段，接在檔尾 L5363 之後（先加一行 `---`）**
```text
---

**N-86 記錄一步路徑批（後續追蹤清單 N-86；D-1、D-3、D-7 第 2、3、7 點、D-8 第 2 點、D-14、FL-74、FL-76、FL-77、待決事項；方向：逐項標示，見各項）**
- 來源與套用範圍：
  - dev-lead 查證：`work/reviews/2026-10-24-N86記錄一步路徑查證-dev-lead.md`；tech-architect 2026-10-24 裁定 Q-A～Q-H 與本批落字稿（轉存路徑由 coordinator 補）。
  - 風控逐字確認：（路徑待補）。風控改字之處以風控為準。
  - CEO：否（各項都沒有放寬面）；devops-sre 知悉（N86-17）。
  - 事先宣告不改字；本批不依附任何事先宣告版次，可以單獨 commit。
- 逐項（被取代的原文：判準同 v0.25 同步批段）：
  - N86-1 D-1 `errors.py`：方向：補定義（不變：補登 D-8 已使用的 `GapAuditRunInconsistencyError`；新增兩個型別）。CEO：否。句中接字，無被取代原文。
  - N86-2 D-3 `forecast_scope_snapshot` N-86 子點與新增欄位 `forecast_run.no_pending_scopes_json`：方向：補定義（收緊：新增持久化與寫入驗證；範圍快照的語意改為本 run 要寫的範圍，S 的範圍快照聯集不變）。CEO：否。插入，無被取代原文。
  - N86-3 D-3 `forecast_record_attempt_end` 的 `inputs_not_ready` 一項：方向：補定義（不變：`reason` 不變，end 列由「沒有」改為 `error_before_run`）。CEO：否。被取代的原文——
    > 寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗。
  - N86-4 D-3 `error_before_run` 的 `candidate_t`：方向：補定義（不變）。CEO：否。句中接字，無被取代原文。
  - N86-5 D-3 `plan_coverage_log`「衍生計數」的不一致標的數：方向：不變（比對對象仍是同一 run 讀到的完整排程範圍；避免 N86-2 之後重試時的假性不一致）。CEO：否。被取代的原文——
    > 與同一 run 的 `forecast_scope_snapshot`（`reason ∈ {holding, watchlist}`）不一致的標的數，在 §4.2 另列。
  - N86-6 D-7 第 2 點 Q4 句末：方向：補定義（收緊：「決定 T」要四項都成立）。CEO：否。句末接字，無被取代原文。
  - N86-7 D-7 第 3 點候選 T 句末：方向：補定義（收緊：沒有候選 T 時 fail-closed）。CEO：否。句末接字，無被取代原文。
  - N86-8 D-7 第 7 點 N-86 子點：方向：補定義（收緊：函式結構與閘門位置固定；重試不再因已寫入的範圍整步中止，與 D-8 第 2 點 N-24「22:10 記錄失敗、23:10 重試成功時，S 沒有缺日列」的原意一致）。CEO：否。插入，無被取代原文。
  - N86-9 D-8 第 2 點「有範圍快照時」一項句末：方向：補定義（不變：與事先宣告 V27-02 第 1 點的字面一致）。CEO：否。句末接字，無被取代原文。
  - N86-10 D-14「recorder 執行期強制」句末：方向：不變（指向）。CEO：否。句末接字，無被取代原文。
  - N86-11 FL-74 (b)：方向：補定義（不變：澄清讀法）。CEO：否。句中接字，無被取代原文。
  - N86-12 FL-76 首段末句：方向：不變。CEO：否。被取代的原文——
    > 各格的 run 都只含尚未寫入的範圍（重試遇到已寫入範圍的處理不在本格範圍）。
  - N86-13 FL-76 (j) 後半格：方向：收緊（測試）。CEO：否。被取代的原文——
    > 單獨一次嘗試、`inputs_not_ready` 的 end 寫入拋例外 → 例外往外拋，E-3d 一則；稽核 → `record_start_failed`。
  - N86-14、N86-15 FL-76 (o)、(p) 句末：方向：收緊（測試）。CEO：否。句末接字，無被取代原文。
  - N86-16 FL-76 (s) 與 FL-77：方向：收緊（測試）。CEO：否。插入，無被取代原文。
  - N86-17 待決事項 devops-sre 句末：方向：不變（揭露）。CEO：否。句末接字，無被取代原文。
  - N86-18 N-64、N-66 缺日原因批「落檔後的閘門」句末〔已決（N-86）〕：原文不改，無被取代原文。
  - N86-19 本段。
- 照實並陳：
  - 相對「重試照字面整步中止」的讀法，本批使重試能寫入先前拒寫或逾時的範圍，缺日列可能較少；這是 D-7 第 1 點 23:10 重試與 D-8 第 2 點 N-24 理由的原意，不是放寬〔推論，請風控確認方向〕。列的集合（S 的範圍快照聯集）、n、W 與作廢率的定義都不變。
  - 範圍快照不再代表當下的完整排程範圍；完整範圍要加上 `forecast_run.no_pending_scopes_json`。範圍全部已寫入的重試與補跑各留一列 run（範圍快照為空）。
  - 閘門成立之前若已註冊 job，或市場 DB 沒有任何 ok bars run，每次執行都發一則 E-3d。
  - 新登記 claim 的缺日義務（N-84）不在本批；本批只讓重試時新 claim 能寫入紀錄。
  - `plan_coverage_log` step_start 的 `run_id` 為 null 時如何比對，原文沒有定義，本批也沒有定義（另列後續追蹤，coordinator 分配編號）。
- 待決事項與同批規則：
  - 本批內部不拆開；N86-2、N86-5、N86-8 不得單獨先落檔。修訂紀錄（本段與 N86-18）最後落檔。
  - 落檔後的閘門：`audit.py` 的多 run `reason` 判定、`record_start_failed`、記錄一步的開始列、end 列、範圍快照的分割與執行期閘門，依本批與 N-64、N-66 批的字面實作；本批落檔前不實作。
```

### 落檔後預期值（ADR-0027 單檔，Grep `-o` 計次數）

**新增或增加的字串**（落檔前為本次實測，淨增含自帶提及）：

| 字串 | 落檔前 | 淨增 | 落檔後 |
|---|---|---|---|
| `N-86` | 1（L5328） | +36（N86-1:2, -2:2, -3:2, -4:1, -5:2, -6:2, -7:1, -8:2, -9:1, -10:2, -11:2, -12:2, -13:1, -14:1, -15:1, -16:5, -17:1, -18:1, -19:5） | 37 |
| `no_pending_scopes_json` | 0 | +10（-2:1, -5:1, -8:1, -16:5, -19:2） | 10 |
| `FL-77` | 0 | +4（-12:1, -16:1, -19:2） | 4 |
| `NoCandidateSessionError` | 0 | +3 | 3 |
| `WriteGateClosedError` | 0 | +4（-1:1, -8:1, -16:2） | 4 |
| `RecordProgress` | 0 | +1 | 1 |
| `GapAuditRunInconsistencyError` | 2 | +4（-1, -9, -16(s), -19） | 6 |
| `IntegrityError` | 0 | +6（-2:2, -8:1, -16:3） | 6 |
| `ForecastFailClosedError` | 11 | 0 | 11 |

**被取代的原文**：
- N86-1、N86-4、N86-11 的 old 字串，落檔後為 0。
- N86-3 的 old 全句為 0。它的片段「寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗。」落檔前 1，落檔後 1（只剩修訂紀錄的引文）。
- N86-5、N86-12、N86-13 的 old 字串，落檔後各 1（都在修訂紀錄的引文）。

**插入錨點**：N86-2、-6、-7、-8、-9、-10、-14、-15、-16、-17、-18 的錨點，落檔後仍各 1 處。

### 三、給 quant 的同步與送審判斷
- **事先宣告不需要改字**。
  - 唯一跟「範圍快照」字面有關的是 L858「把當時的名單存成快照」。依 N86-2，第一次執行仍然存完整名單，S 的快照聯集也不變，所以不必改。
  - 風控若認為要補註，請 quant 在 v0.29 之後的版次加〔註〕，方向「不變」，避開 L1431 與 L1106。v0.29 照原計畫進行。
  - L837 在事先宣告裡沒有對應字面（Grep「同一 run」「不一致的標的」都是 0），L300 的名稱核對也不受影響。
- **V27-02 三點都沒有被觸及**：
  - 第 1 點：S 的快照聯集不變，理由在 N86-2；Q-H 是這一點的直接結果。
  - 第 2 點：判定仍然只依持久化的紀錄。
  - 第 3 點：被蓋過的原因仍然留在 `basis_json`。本批還消除了「重試誤中止把原因蓋成 `record_error`」的情形。
- **風控**：建議送逐字確認，不必 CEO 明確同意。要確認的點：
  - (i) N86-5 揭露的意思不變；
  - (ii) 缺日列可能變少這一點，方向判為「補定義」、不是放寬；
  - (iii) N86-9 判為不變。

### 四、對實作的約束（給 dev-lead，逐條可查）
1. 範圍快照只列至少有一個待寫（範圍, `claim_id`）的範圍。範圍內只寫待寫的 claim。`late=1` 算已寫入。判定在 A-25 交易內，查詢以 `claim_id` 比對，不用 M-6 鍵。
2. A-25 的寫入函式只接受排程範圍，在交易內自行分割；寫入驗證用另一個純函式重算（FL-77 (g)）。
3. `forecast_run.no_pending_scopes_json` 必填，只有 `validation.py` 的 L837 計數與稽核工具可以讀，`audit.py` 不讀（AST）。
4. `recorder.py`、`store.py` 都不得有指名 `IntegrityError` 的 except，範圍內也不得「先查後跳過」（FL-77 (h)）。
5. `forecast_record_attempt_end.outcome` 維持三值，`reason` 維持九值。
6. 函式結構照 D-7 第 7 點 N-86 子點：
   - 入口函式沒有 `except Exception`，開始列的寫入不在任何 try 之內；
   - 前置段函式恰好一個 `except Exception`，A-25 commit 之後只回傳；
   - 範圍迴圈函式的第一個陳述式就是 try；
   - 兩個 end 寫入函式各只有一個呼叫點。
7. 執行期閘門在前置段一開始、讀市場 DB 之前。不成立時拋 `WriteGateClosedError`，沒有其他出口。
8. 市場 DB 沒有任何 ok bars run 時拋 `NoCandidateSessionError`，不得記 `inputs_not_ready`。
9. T 只經 `RecordProgress.t` 交回，在四項都成立的當下設定。編排函式不讀例外屬性，也不讀 attempt 表。
10. 判定候選 T 時，先把 `candidate_t` 指派給區域變數，再做可能拋例外的步驟。
11. `inputs_not_ready` 的 end 寫入在前置段的 try 內，失敗時補寫 `error_before_run`。
12. 正常返回時：`RecordStepResult.t is None` 若且唯若 `run_id is None`。
13. 缺日稽核遇到 Q-H 的情形時不寫列，也不拋例外（FL-76 (s)）。
14. FL-76 (o)、(p) 與 FL-77 全部要有測試；(p) 用呼叫點白名單判定，不用 skip 或 xfail。
15. 本批落檔之前，`audit.py` 的多 run 判定、`record_start_failed`、範圍分割和閘門都不實作。

- **其他部門**：本次未參與。product-manager、quant-researcher、risk-compliance-officer、qa-reviewer、qa-e2e、devops-sre、tech-writer、frontend-engineer 等都沒有動到。這是純評估、沒有 diff，所以不需要 qa-reviewer 審查；落檔後的 diff 照例送 qa-reviewer（含 Codex 第二意見）。

## 驗證
- 所有 old 字串與錨點，都已在 HEAD 版 ADR-0027 用 Grep `-o` 實測：恰好 1 處，行號如上。
- 「落檔前」各數字是本次實測；「落檔後」是依落字稿逐項算出來的，tech-writer 落檔後用同樣的 Grep `-o` 重算比對即可。
- 我也確認了以下幾點：
  - `scheduler.py:647,672,686` 確實用 `next_run_time` 做啟動補跑；
  - 事先宣告沒有 L837 的對應字面；
  - `GapAuditRunInconsistencyError` 原本不在 D-1 `errors.py` 列內（只出現在 L1244、L2538），所以由 N86-1 補登。
- 沒有跑任何程式或測試，沒有讀 `.env` 或 `*.db`，也沒有寫檔。
- CEO 不需要親自驗證任何事項（各項都是 CEO：否）。

## 下一步
1. coordinator 把 N86-1～N86-19 送 risk-compliance-officer 逐字確認，重點是第三節 (i)～(iii)。確認之後交 tech-writer 依上面的順序落檔（修訂紀錄最後），單獨一個 commit，再送 qa-reviewer（含 Codex）。
2. coordinator 在後續追蹤清單新增一項：`plan_coverage_log` step_start 的 `run_id` 為 null 時的比對規則（本批不定義）。
3. 落檔之後，dev-lead 依第四節的約束實作記錄一步與 `audit.py` 的多 run 判定；在那之前繼續不實作。
