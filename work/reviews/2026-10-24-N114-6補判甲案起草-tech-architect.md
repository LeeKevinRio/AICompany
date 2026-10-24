# N-114 第二批修訂與 N114-6 補判（甲案）起草

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

1. **甲案（補判）可行。CEO 決策包可以用風控檔 C 第 2 項的白話句送出。** 這也是我自己傾向的方案。原因：在 M 的做法下，若一個 ≤ M 的日子當初稽核時不在觀察日集合，之後就永遠不會被判定，這是 M 這條捷徑本身的缺陷。改用持久化的「本次首判日集合」後，「首判」的定義變成「成為觀察日、截止已過、而且不在任何集合中」，自然涵蓋守衛期間漏判、之後才補寫的日子。
   - 為什麼可行（下列各點都已核對 ADR 原文）：
     - 第一批落檔後，store 的寫入交易一律 `BEGIN IMMEDIATE`。我規定稽核在寫入交易內讀既有集合，所以兩次稽核不會同時首判同一日。
     - 每一日至多出現在一列集合中，該日的缺日列只由那一次稽核交易寫入。所以以 `gap_audit_id` 重算時，改用「`audit_id` ≤ g 的集合聯集」界定已判定日，結果仍逐位相同（R5）。
     - 補判日數 (vi) 只讀 `forecast_gap_audit`，同樣可以重算。
     - D-7 第 2 點的理由句（風控寫 L965，現行檔在 L972）在甲案下成立，「只會少寫」實際上只是延後，我補了註（R6）。
   - 甲案有三個代價，都已寫進「照實並陳」：
     - (a) `gap_judged_through` 以前的缺日統計之後仍可能因補判而增加，使用者面文案不能寫成「此日以前已全部定案」；
     - (b) 記錄一步嘗試的歸屬窗依判定當時的觀察日集合計算，所以補判日的窗可能和鄰日首判時用的窗重疊，同一次嘗試可能同時列在兩日；
     - (c) 新欄必須和表同時建立。只增不改之下，晚建的欄位無法回填。
2. **風控 B 段的 old→new 我照單採用。** 有一處技術補充，標為「TA 增補」送風控重審：首判之後才寫入的 S 的 run，不會經過 N-64、N-66 子點第 3 項的帳目矛盾檢查。理由是稽核已不讀 S，所以這種 run 的帳目矛盾不會讓稽核 rollback。依 D-3 `forecast_run_end` 的寫入驗證，這種矛盾只可能來自繞過 store 的寫入〔推論〕。我把這句接在「另一面」的末尾，FL-76 (t8) 第二格也把這個行為釘住了。要不要把它列入修訂紀錄的放寬面 (c)，請風控決定。
3. **N114-6（甲案）已涵蓋 R1～R7；新增 N114-7 回應第 (4) 點；第 (5) 點加了 FL-76 (t8)。**
   - 欄名定為 `first_judged_sessions_json`。
   - quant 五點的 (1)(2) 改由風控 B 段處理；(3) 照甲案處理，不採 G-a 原稿的排除分母。
4. **前提有變：第一批已經在工作樹內。** `N-113` 有 9 處，第一批修訂紀錄段結束於 L5586，行號整體位移約 7 行。下面每個 old 都是依現行工作樹重新以 Grep `-o` 實測。第二批不得早於第一批落檔，因為風控的 N114-4 修訂紀錄引用了 N115-3。

## 二、各部門回報

### tech-architect

#### A. 方案比較（從未判定日）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **甲案：存集合並補判（採用）** | 「已判定」只有一個定義；漏判日之後會判；沒有永久排除；以集合重算仍逐位相同 | 改寫 N114-1、N114-4 四個子點與 (t6)；前綴性質不再成立 | 補判以補判當時讀到的紀錄判定；`gap_judged_through` 以前的統計會增加 |
| 乙案（G-a 原稿）：存集合、排除分母、只揭露日數 | 保留「≤ M 不再寫入」的不變式，改字少 | 永久排除，而且和還原相關，缺日率系統性偏低 | 風控已否決（C 第 3 項） |
| 不存集合（第二批原稿） | 不必改字 | 從未判定日會以「沒有缺日」計入分母，與 N-24 C-22 衝突，事後也辨識不出 | 否決 |

#### B. 落字稿

**套用規則**
- 先套原第二批的 N114-1～N114-5，再依 T-01～T-25 順序套用。
- 修訂紀錄（T-17～T-25）最後落檔。
- 標「草稿」的 old，在原第二批草稿 `/home/user/AICompany/work/reviews/2026-10-24-N113N114N115澄清起草-tech-architect.md` 中各 1 處，在現行 ADR 中為 0，所以套完 N114-1～N114-5 後各恰 1 處。
- 標「現行」的 old，在現行 ADR 工作樹中各 1 處。
- 同一行有兩處修改的配對（T-02/T-03、T-06/T-07、T-08/T-09）互不重疊。

**T-01｜N114-1 末句｜取代｜草稿 L286**
```text
old: ，也就是晚於本交易開始時讀到的 M；
new: ，也就是本交易寫入之 `forecast_gap_audit` 列的 `first_judged_sessions_json` 所列的日子（D-3 `forecast_gap_audit` 寫入驗證 N-114 項）；
```

**T-02｜N114-4「已判定日」整點｜取代｜草稿 L306**
```text
old: **已判定日**：M ＝ 稽核交易開始時讀到的既有 `forecast_gap_audit` 各列 `judged_through` 的最大值；沒有列，或各列都是 null 時，M 不存在。觀察日 S ≤ M 時，S 已判定。本次稽核已判定的觀察日（D-3 `forecast_gap_audit` 寫入驗證所稱範圍內 ≤ `judged_through` 的觀察日）中晚於 M 者，稱為本次首判日；M 不存在時，本次已判定的觀察日都是本次首判日。M 取歷來最大值、不取最新一列，所以 `judged_through` 依 D-3 `forecast_gap_audit` 寫入驗證末項回退時，已判定日不會被重判。
new: **已判定日**：觀察日 S 已判定，若且唯若既有某一列 `forecast_gap_audit` 的 `first_judged_sessions_json` 含 S（D-3 `forecast_gap_audit`）；只依這一欄判定，不以 `judged_through`、M 或缺日列是否存在推定。本次稽核判定上界內的觀察日（D-3 `forecast_gap_audit` 寫入驗證所稱範圍內 ≤ `judged_through` 的觀察日）中，尚未判定者稱為本次首判日；沒有任何既有列時，這些觀察日都是本次首判日。本次首判日記入本次寫入之列的 `first_judged_sessions_json`，自此已判定，之後不再判定。所以 `judged_through` 依 D-3 `forecast_gap_audit` 寫入驗證末項回退時，已判定日不會被重判；不晚於既有 `judged_through`、而尚未判定的觀察日，在下一次成功的稽核中首判（本子點「另一面」的補判）。M ＝ 稽核交易開始時讀到的既有各列 `judged_through` 的最大值（沒有列，或各列都是 null 時，M 不存在），只作效率用途：實作可以先取晚於 M 的觀察日，但必須另取 ≤ M 而不在任何既有列 `first_judged_sessions_json` 中的觀察日，兩者合起來才是本次首判日；M 不是「已判定」的定義。
```

**T-03｜N114-4「只對本次首判日寫入」｜取代｜草稿 L307**
- 不在風控列的三點之內，但不改的話會和 T-02 矛盾。
```text
old: S ≤ M 時，本次稽核不判定 S，也不寫入任何 `session = S` 的 `forecast_gaps` 列；
new: S 已判定時（本子點「已判定日」），本次稽核不判定 S，也不寫入任何 `session = S` 的 `forecast_gaps` 列；
```

**T-04｜N114-4「重跑不改變結果」｜取代｜草稿 L309**
```text
old: 帳目矛盾（同子點第 3 項）使整次稽核 rollback 時，M 不前進，
new: 帳目矛盾（同子點第 3 項）使整次稽核 rollback 時，不留下 `forecast_gap_audit` 列，也就沒有任何日子成為已判定，
```

**T-05｜N114-4「驗證快照的重算」整點｜取代｜草稿 L311（R5）**
```text
old: **驗證快照的重算**：`session` ≤ 某列 `forecast_gap_audit` 的 `judged_through` 的缺日列，都在該列或更早的稽核中寫入，之後不再增加；所以 D-3 `forecast_gap_audit`「讀取」中以 `gap_audit_id` 重算驗證快照時逐位相同，不另存水位〔推論，依本子點與已判定日的前綴性質〕。
new: **驗證快照的重算**：每一個觀察日至多出現在一列 `forecast_gap_audit` 的 `first_judged_sessions_json`，它的缺日列都由寫入該列的稽核交易寫入，之後不再增加（本子點「只對本次首判日寫入」；D-3 `forecast_gaps` 寫入驗證 N-114 句）。所以以 `gap_audit_id` ＝ g 重算驗證快照時，已判定日取 `audit_id` ≤ g 各列 `first_judged_sessions_json` 的聯集，缺日列只取 `session` 在這個聯集中的列（D-3 `forecast_gap_audit`「讀取」`validation.py` 一項），結果逐位相同；g 之後才首判的日子（含補判）與它們的缺日列都不在這個聯集內。補判使「`session` ≤ 某列 `judged_through` 的缺日列不再增加」的前綴性質不成立，所以不以 `judged_through` 界定〔推論，依本子點與 D-3 `forecast_gaps`、`forecast_gap_audit` 的寫入驗證〕。
```

**T-06｜N114-4「另一面」｜取代｜草稿 L313**
- old：風控檔 B 第一項的 old（逐字）。
- new：風控檔 B 第一項的 new 逐字照抄，句末（「……揭露。」之後）再接 TA 增補：
```text
首判之後才寫入的 S 的 run，也不經本點 N-64、N-66 子點第 3 項的帳目矛盾檢查：這種 run 的帳目矛盾不使稽核 rollback（D-3 `forecast_run_end` 的寫入驗證使這種矛盾只可能來自繞過 store 的寫入〔推論〕）。
```

**T-07｜N114-4 殘餘句改為補判｜取代｜草稿 L313**
```text
old: 殘餘：D-7 第 2 點「還原疑似時的共同守衛」成立期間沒有登記的平日，若之後才補寫成為 ≤ M 的觀察日，不會被判定，也沒有缺日列〔推論〕。
new: 補判：D-7 第 2 點「還原疑似時的共同守衛」成立期間不在觀察日集合、也沒有登記為未觀察平日的平日，若之後才補寫成為 ≤ M 的觀察日，不算已判定（本子點「已判定日」），在它成為觀察日之後第一次成功的稽核中首判，依該稽核交易讀到的紀錄判定，首判之後同樣終局〔推論〕。補判之前，它不以「沒有缺日列」計入任何以缺日界定的分母；補判的日數另列（D-3 `forecast_gap_audit`「讀取」`validation.py` 一項；事先宣告 §6.3「缺日」「不補造」一點〔v0.30 註〕(vi)）。補判日的缺日列在 `gap_judged_through` 越過它之後才出現，所以補判之前寫入的驗證快照不含它，`gap_judged_through` 以前的缺日統計之後仍可以增加〔推論〕。
```

**T-08｜FL-76 (t6)｜取代｜草稿 L320**
- 甲案下，`session` ≤ M 的列可能是合法的補判列，所以要改寫。
```text
old: (t6) `verify_gap_rows` 以 `session` ≤ M 的列直接呼叫 → 判為違規
new: (t6) `verify_gap_rows` 以 `session` 不在本交易 `first_judged_sessions_json` 內的列（例如已在既有列的該欄內）直接呼叫 → 判為違規
```

**T-09｜FL-76 (t7) 句末接 (t8)～(t11)｜接字｜草稿 L320**
- 錨點（保留）：`(t7) 以 (t1) 第一次稽核寫入的 `audit_id` 寫入的驗證快照，在 (t1) 第二次稽核之後依 `gap_audit_id` 重算 → 逐位相同。`
- 接在其後：
```text
 (t8)（事先宣告 LG-48 (c) 的對應格）首判之後才出現的範圍：(t1) 第二次稽核之後（C 已有 `late=1` 紀錄），在市場 DB 中最新一個有 ok bars run 的 session 仍是 S 的期間，把 symbol 範圍 D、E 加入自選（fixture 的 symbol claim 都在 S 的第一個 run 之前登記），再一次啟動補跑以 S 為候選 T → 範圍快照恰為 D、E（C 依 FL-77 (e) 列入 `no_pending_scopes_json`）；寫入 D（`late=1`）之後期限已到，E 沒有寫入，end 為 `timeout`；再稽核 → S 沒有新列，C 的列仍是 `timeout`，D、E 在 S 都沒有缺日列，`gaps_written = 0`。同一 fixture，該次補跑的 end 改以直接 SQL 寫成 `ok`（繞過 store 的寫入驗證，比照 (k)）→ 再稽核不拋 `GapAuditRunInconsistencyError`，S 沒有新列，`forecast_gap_audit` 照常寫入一列（D-8 第 2 點 N-114 子點「另一面」）。(t9)（N-114；D-3 `forecast_gaps` 用途限制的 N-114 句）AST：計算事先宣告 V30-02 (i)～(v) 的函式在 `validation.py` 恰一個定義；它與它呼叫的 `store.py` 讀取函式不讀 `forecast_run.no_pending_scopes_json`、`forecast_run_end`、`forecast_record_attempt`、`forecast_record_attempt_end`，對 `forecast_record` 的 SQL 明列欄位、不含 `scope_reason`；`validation.py` 不 import `app.forecast.audit`；n、W、作廢率、F-3 與 D-12 的判定函式不呼叫它與補判日數的函式；`db_restored` 標記的區間在 `store.py` 恰一個讀取函式，缺日稽核與它都只經這個函式。行為：(t8) 之後計算 → (iii)、(iv) 每個 symbol claim 各 1；同一份紀錄連續計算兩次，結果相同。(t10)（N-114；D-3 `forecast_gap_audit.first_judged_sessions_json`）本次首判日集合：(t3) 的第一次稽核（之前沒有任何 `forecast_gap_audit` 列）→ 本欄恰為範圍內 ≤ `judged_through` 的全部觀察日；第二次 → `[]`；之後新增觀察日 S′，過了 S′ 的 `late_cutoff_at` 再稽核 → 恰為 `[S′]`；各列的本欄兩兩不相交。寫入驗證的重算純函式直接以違規輸入呼叫，各一格判為違規：少一個本次首判日；含既有列本欄已有的日子；含晚於 `judged_through` 的日子；未依日期升冪；重複；本交易寫入一列 `session` 不在本欄的缺日列。AST：該重算純函式不呼叫決定本次首判日的函式；SQL trace：稽核在 `BEGIN IMMEDIATE` 之後才讀既有各列的本欄。建表後 `PRAGMA table_info(forecast_gap_audit)` 中本欄的 `notnull` 為 1、`dflt_value` 為 None（SQL NULL）。(t11)（N-114；D-8 第 2 點 N-114 子點「已判定日」與「另一面」的補判；D-7 第 2 點守衛的缺日稽核一項 N-114 句；D-3 `forecast_gap_audit`「讀取」`validation.py` 一項 N-114 句）補判：平日 S1 < S2 < S3；第一次稽核時假市場 DB 只有 S1、S3，並以 monkeypatch 使 `market_run_regression()` 回報守衛成立 → 判定 S1、S3，本欄為 `[S1, S3]`，`forecast_ledger_events` 沒有新的 `unobserved_weekday` 列；之後守衛解除、假市場 DB 補上 S2（沒有 S2 的 run 與記錄一步嘗試），再稽核 → 本欄恰為 `[S2]`，S2 每個 claim 一列 `scope_key = '*'`、`reason = scheduler_down`；以第一次稽核的 `audit_id` 計 → 以缺日界定的分母只含 S1、S3，補判日數 0；以第二次計 → 分母含 S1、S2、S3，補判日數每個 claim 各 1；第二次稽核之後依第一次的 `gap_audit_id` 重算 → 逐位相同。第三次稽核 → 本欄為 `[]`，S2 沒有新列。反例斷言：以「S ≤ M 即已判定」判定時，第二次稽核不寫 S2 的列。
```

**T-10（N114-7）｜D-3 `forecast_gaps` 用途限制（現行 L791）｜句末接字**
- 錨點（保留）：`只有 `audit.py`、`validation.py` 的缺日揭露（事先宣告 §6.3「缺日」）與稽核工具可以讀；`views`、API route、匯出與 `app.ops_alert.*` 不讀（AST）。`
- 接在其後：
```text
（N-114）`validation.py` 的缺日揭露另依事先宣告 §6.3「缺日」「不補造」一點〔v0.30 註〕（V30-02）計算首次判定之後才寫入之紀錄的 (i)～(v)：只由 `validation.py` 的單一函式計算（名稱由 dev-lead 定；AST 列舉定義與呼叫點），在一個明確開啟的 read transaction 內，經 `store.py` 只讀下列欄位：`forecast_run` 的 `run_id`、`trigger`、`data_as_of`；`forecast_scope_snapshot` 的 `run_id`、`scope_kind`、`scope_key`；`forecast_record` 的 `claim_id`、`scope_kind`、`scope_key`、`data_as_of`、`trigger`、`late`、`supersedes_id`（以明列欄位的 SQL 讀取，不讀 `scope_reason`，D-3 `forecast_record` N-109 子點）；`forecast_claim_registry` 的 `claim_id`、`kind`、`scope_kind`；`db_restored` 標記的區間（與 D-8 第 2 點 N-64、N-66 子點第 1 項共用 `store.py` 的同一個讀取函式）；本表；D-3 `forecast_gap_audit` 的 `audit_id`、`judged_through`、`first_judged_sessions_json`（只計已判定的觀察日，D-8 第 2 點 N-114 子點「已判定日」）。S 的 run 取 `trigger = scheduled`、`data_as_of = S`；排程紀錄另加 `supersedes_id IS NULL`。範圍以 (`scope_kind`, `scope_key`) 計，同一範圍在快照中有多個 `reason` 時只計一次（D-3 `forecast_scope_snapshot` N-108 句）。不讀 `forecast_run.no_pending_scopes_json`、`forecast_run_end`、`forecast_record_attempt`、`forecast_record_attempt_end`、log、告警與 job 層事件；不 import `app.forecast.audit`，不呼叫缺日稽核的判定與寫入驗證函式（AST）。(i)～(v) 是讀取當下的值：首判之後才寫入的紀錄可以在任何時點增加，所以不在 D-3 `forecast_gap_audit`「讀取」以 `gap_audit_id` 重算逐位相同的保證內，揭露時附讀取時刻（store 時鐘）；同點 (vi) 的補判日數只讀 `forecast_gap_audit`，在這個保證內（同表「讀取」`validation.py` 一項）。兩者都不屬於 `E_CHANGING_EVENTS`，不是 n、W、作廢率、F-3、徽章或任何判定的輸入（AST）。
```

**T-11（N114-6，R1）｜D-3 `forecast_gap_audit` 欄位（現行 L799）｜整行之後插入一行，縮排 4 格**
- 錨點（保留）：`- `gaps_written INTEGER NOT NULL`：本次寫入的 `forecast_gaps` 列數；`
- 在該行之後插入：
```text
    - （N-114）`first_judged_sessions_json NOT NULL`：本次首判日（D-8 第 2 點 N-114 子點「已判定日」），以 ISO 日期字串組成、依日期升冪、不重複的 JSON 陣列（`separators=(",", ":")`，UTF-8）；沒有時為 `[]`。一日是否已判定只依本欄。不設 DEFAULT：漏填時拒絕寫入，不得靜默成為 `[]`。本欄屬於 `forecast` component 的初版 DDL，與本表同時建立，沒有既有列，不需要遷移（比照 D-3 `forecast_run.no_pending_scopes_json` 的 N-108 句）；若晚於本表第一個上線 schema 版本才落地，既有列不得回填，遷移方式依 ADR-0026 D-6.5 另案送風控；
```

**T-12（N114-6，R1）｜同表寫入驗證（現行 L808）｜句末接字**
- 錨點（保留）：`晚於它的每一日都有 `late_cutoff_at > audit_now`（`late_cutoff_at` 以 D-7.4 的同一個函式、取 T ＝ S 計算）；`
- 接在其後：
```text
（N-114）本項與 `judged_count` 所稱「已判定」，指本次稽核判定上界內的日子；一日是否已判定（D-8 第 2 點 N-24、N-114 子點）只依 `first_judged_sessions_json`；
```

**T-13（N114-6，R2）｜同表寫入驗證（現行 L810）｜句末接字**
- 錨點（保留）：`` `gaps_written` ＝ 本交易寫入的 `forecast_gaps` 列數，而且每一列的 `session` ≤ `judged_through`； ``
- 接在其後：
```text
（N-114）`first_judged_sessions_json` 恰為範圍內 ≤ `judged_through`、而且不在既有任何一列本欄中的全部觀察日（`judged_through` 為 null 時為 `[]`），以與決定本次首判日不同的純函式、依本交易讀到的既有各列重算比對；既有各列在本稽核的寫入交易（`BEGIN IMMEDIATE`）之內讀取；本交易寫入的每一列 `forecast_gaps`，`session` 都在本欄內；
```

**T-14（N114-6，R3、R4、R5）｜同表「讀取」`validation.py` 一項（現行 L817）｜句末接字**
- 錨點（保留）：`缺日率（失效條件 F-3）與任何以缺日界定的分母，只計 ≤ 所用列 `judged_through` 的觀察日（D-8 第 2 點 N-24「比率不因尚未判定而偏低」）。`
- 接在其後：
```text
（N-114）其中「已判定的觀察日」只取 `audit_id` ≤ 所用列的各列 `first_judged_sessions_json` 的聯集中、≤ 所用列 `judged_through` 的日子（A-77 第 7 項排除的日子照舊在查詢時排除），缺日列也只取 `session` 在這個聯集中的列；不在聯集中的日子（尚未首判，或在所用列之後才補判），不得以「沒有缺日列」計入任何以缺日界定的分子或分母（D-8 第 2 點 N-114 子點「已判定日」）。補判日數（事先宣告 §6.3「缺日」「不補造」一點〔v0.30 註〕(vi)）：上述聯集中，記入它的那一列的 `audit_id`，大於 `judged_through` ≥ 該日的最早一列（`audit_id` ≤ 所用列）的 `audit_id` 的日子數，依 claim 列出，0 也照列（新登記 claim 的缺日義務起日依後續追蹤清單 N-84）；只讀本表的 `audit_id`、`judged_through` 與 `first_judged_sessions_json`。兩者都只依 `audit_id` ≤ 所用列的列，所以以 `gap_audit_id` 重算時仍逐位相同（D-8 第 2 點 N-114 子點「驗證快照的重算」）。
```

**T-15（N114-6，R6）｜D-7 第 2 點守衛的缺日稽核一項（現行 L972）｜句末接字**
- 確認：甲案下這句理由成立。若沒有甲案，「第一次稽核會補上」對缺日列並不成立。
- 錨點（保留）：`所以還原處理完之後的第一次稽核會補上。`
- 接在其後：
```text
（N-114）缺日列同理：守衛期間不在觀察日集合、因而沒有判定的日子，補寫成為觀察日之後，在第一次成功的稽核中首判（D-8 第 2 點 N-114 子點「已判定日」的補判），所以「缺日列只會少寫」只是延後；補判之前，這些日子不算已判定，不以「沒有缺日列」計入分母。守衛之前已判定、守衛期間移出觀察日集合的日子不重判，既有列照舊。
```

**T-16（N114-6，R1）｜D-8 第 2 點 N-24「比率不因尚未判定而偏低」（現行 L1255）｜句末接字**
- 原文寫「已經過一次成功稽核的日子」，若不接註，會和 R1「只依集合判定」衝突。
- 錨點（保留）：`所以本點只延後反映，不降低比率。`
- 接在其後：
```text
（N-114）「已經過一次成功稽核的日子」指已記入某一列 `forecast_gap_audit.first_judged_sessions_json` 的日子（本點 N-114 子點「已判定日」）；判定上界已過、而沒有記入任何一列的日子（例如守衛期間不在觀察日集合、之後才補寫的平日），在補判之前仍屬尚未判定。
```

#### C. 修訂紀錄差異（全部以草稿為準，各 1 處）

**T-17｜標題（L327）**
```text
old: **缺日稽核冪等批（後續追蹤清單 N-114；D-3 `forecast_gaps`、D-8 第 2 點、FL-76；
new: **缺日稽核冪等批（後續追蹤清單 N-114；D-3 `forecast_gaps`、`forecast_gap_audit`、D-7 第 2 點、D-8 第 2 點、FL-76；
```

**T-18｜「風控」行（L332）**
- old：`  - 風控：逐字確認（確認檔名與結論由 coordinator 在確認後取代本行）。CEO：依風控對 N114-4 方向的判定；判為須 CEO 明示同意時，同意之前本批與事先宣告同步版本都不落檔。`
- new：風控檔 B 末項的定稿逐字照抄，前面加兩格縮排的 `- `。

**T-19｜N114-1（L334）**
```text
old: 收緊：每一列的 `session` 必須是本次首判日）。被取代的原文——
new: 收緊：每一列的 `session` 必須是本次首判日）。CEO：否（隨本批）。被取代的原文——
```

**T-20｜N114-2（L336）**
```text
old: 方向：補定義（兩面，同 N114-4）。句末接字，無被取代原文。
new: 方向：補定義（兩面，同 N114-4）。CEO：明確同意（同 N114-4）。句末接字，無被取代原文。
```

**T-21｜N114-3（L337）**
- 照風控 B 的 old→new 逐字套用。

**T-22｜N114-4（L339）**
- 照風控 B 的 old→new 逐字套用，涵蓋 quant 的 (1)(2)。
- 技術上沒有錯誤。「N115-3」在第一批落檔後已是 ADR 修訂紀錄中的項目標籤，可以引用。

**T-23｜N114-5（L340）**
```text
old:   - N114-5 FL-76 (t)：方向：收緊（測試）。插入，無被取代原文。
new:
  - N114-5 FL-76 (t)（(t1)～(t8)；(t9) 見 N114-7，(t10)、(t11) 見 N114-6）：方向：收緊（測試）。CEO：否（隨本批）。插入，無被取代原文。
  - N114-6 從未判定日的補判（D-3 `forecast_gap_audit` 新欄 `first_judged_sessions_json`、寫入驗證與「讀取」`validation.py` 一項，D-3 `forecast_gaps` 寫入驗證 N-114 句末，D-7 第 2 點守衛的缺日稽核一項，D-8 第 2 點 N-24 子點「比率不因尚未判定而偏低」句末與 N-114 子點「已判定日」「只對本次首判日寫入」「重跑不改變結果」「驗證快照的重算」「另一面」，FL-76 (t6)、(t10)、(t11)；落實風控 2026-10-24 C 第 3 項甲案 R1～R7）：方向：補定義（收緊：「已判定」只依持久化的本次首判日集合；守衛期間沒有判定、之後才成為觀察日的平日改為補判，補判之前不以沒有缺日列計入以缺日界定的分母，補判日數另列。另一面：補判日的缺日列晚出現，補判之前寫入的驗證快照不含它，`gap_judged_through` 以前的缺日統計之後仍可以增加〔推論〕）。表數不變，`forecast_gap_audit` 加 1 欄。CEO：明確同意（與 N114-4 同一份決策包；白話句已含補判）。對本批 N114-1、N114-4、N114-5 字面的改寫與它們同一個 commit 落檔，不另列被取代原文；其餘為插入與句末接字，無被取代原文。
  - N114-7 D-3 `forecast_gaps` 用途限制的 N-114 句（`validation.py` 計算事先宣告 V30-02 (i)～(v) 的讀取範圍）與 FL-76 (t9)：方向：補定義（收緊：讀取限於明列的表與欄位，不讀 `scope_reason`，不 import `audit.py`；不變：不影響任何計數與判定；(i)～(v) 是讀取當下的值，不在以 `gap_audit_id` 重算逐位相同的保證內）。CEO：否（隨本批）。句末接字，無被取代原文。
```

**T-24｜照實並陳（L344）**
```text
old:   - 首判時點的依賴與還原守衛的殘餘，見 D-8 第 2 點新子點「另一面」。
new:
  - 首判時點的依賴與補判，見 D-8 第 2 點新子點「另一面」與「已判定日」。
  - N114-6 不採「從未判定日不計入分母、只揭露日數」（G-a 原稿）：還原期間正是容易出缺日的日子，永久排除會使缺日率系統性偏低（風控 2026-10-24 C 第 3 項）。補判的代價：補判日以補判當時讀到的紀錄判定；`gap_judged_through` 以前的日子之後仍可能補判，所以 D-8 第 2 點 N-24 子點「統計只到 `gap_judged_through`」的使用者面文案，不得寫成此日以前已全部定案（文案另經 creative-lead 起草、風控審查）〔推論〕；記錄一步嘗試的歸屬窗依判定當時的觀察日集合計，補判日的歸屬窗可以與鄰日首判時所用的窗重疊，同一次嘗試因此可能同時列在兩日〔推論，依 D-8 第 2 點 N-64、N-66 子點「S 的記錄一步嘗試」(b)〕。`first_judged_sessions_json` 必須與本表同時建立：只增不改之下，晚建的欄位無法回填早期稽核的本次首判日。
```

**T-25｜待決（L347）｜句末接字**
- 錨點（保留）：`  - 本批內部不拆開；與事先宣告同步版本同一個 commit。修訂紀錄（本段）最後落檔。`
- 接在其後：`本批（含 N114-6、N114-7）不得早於第一批落檔（N114-4 的修訂紀錄引用 N115-3）。`
- 第二批修訂紀錄段接在現行 L5586（第一批段「落檔後的閘門」那一行）之後，前面先加一行 `---` 與一個空行。

#### D. 第 (4) 點：與各表用途限制的相容性

結論：相容，條件是照 T-10 限定讀取範圍。逐表說明：

| 讀取對象 | 用途限制 | 相容方式 |
|---|---|---|
| `forecast_record`（排程紀錄的 `late`） | N-109 白名單外的模組不讀 `scope_reason`；N117-4 不得用 `SELECT *`，也不得出現含 `scope_reason` 的字串常數 | SQL 明列欄位，FL-76 (t9) 用 AST 檢查 |
| `forecast_run` | `no_pending_scopes_json` 只供 `validation.py` 的不一致標的數讀（FL-77 (l)） | 只讀 `run_id`、`trigger`、`data_as_of`；(iii)、(iv) 的範圍只取 `forecast_scope_snapshot` |
| `forecast_run_end` 的 `refused_scopes_json`、`error_class`；`forecast_record_attempt(_end)` | 只有 `audit.py` 可以讀 | (i)～(vi) 都不需要，明文禁讀 |
| `db_restored` 標記 | 無特別限制 | 規定與稽核共用 `store.py` 的同一個區間函式，以免兩邊判法分岐 |
| `forecast_gaps` 的 `basis_json` 等欄 | `validation.py` 的缺日揭露可以讀 | 已涵蓋 |

另有兩點：
- **N-110 的稽核接縫**：規定不 import `app.forecast.audit`，也不呼叫 `build_gap_rows`、`verify_gap_rows`。如果揭露端借用稽核的判定函式去算「字面讀法」，等於在稽核以外重判一次。
- **可重算性**：(i)～(v) 依「現在」的紀錄計算，首判之後才寫入的紀錄隨時可能增加，所以不能納入 `gap_audit_id` 逐位相同的保證，揭露時要附讀取時刻。(vi) 只讀 `forecast_gap_audit`，可以重算。
- 風控 D 段建議在 (iii) 加的縱深條件「沒有 `late=0`」也相容，因為 `late` 已在可讀欄位內。

#### E. 對實作的約束（dev-lead，B6 逐條可檢查）

1. 稽核在 `BEGIN IMMEDIATE` 之後才讀既有各列的 `first_judged_sessions_json`。本次首判日 ＝ 範圍內 ≤ `judged_through` 的觀察日，扣掉集合聯集中已有的日子。M 只能用來縮小查詢範圍，不能作為「已判定」的判準。
2. 寫入驗證以另一個純函式重算集合，不得呼叫決定函式。新欄 NOT NULL，不設 DEFAULT。
3. `validation.py` 的分母、分子與補判日數，一律以 `audit_id` ≤ 所用列的集合聯集界定。(i)～(v) 依 T-10 只讀明列的欄位，不 import `audit.py`。
4. FL-76 (t6) 依新字面改寫；(t8)～(t11) 全部要過。

### quant-researcher（需同步）

- E-06、E-07 的依據改為「TA N-114 起草第二批 N114-1～N114-7」。
- V30-02 (vi) 照 T-14 的導出式寫（集合中的日子，記入它的那一列 `audit_id` 大於最早一列 `judged_through` ≥ 該日的 `audit_id`，依 claim 列出，0 也照列）。
- (i)～(v) 要補一句「讀取當下的值，揭露時附讀取時刻」。
- LG-48 (c) 引用 FL-76 (t8)，R7 的對應格引用 FL-76 (t11)。
- 殘餘句全部改寫成補判。

### risk-compliance-officer（重審）

- 確認 T-06 的 TA 增補（首判之後的 run 不經帳目矛盾檢查），並決定是否把它列入修訂紀錄放寬面 (c)。
- 確認 T-03、T-04、T-08、T-12、T-15、T-16 這幾處：它們不在要求清單內，但要讓 R1 在全文一致，所以必須跟著改。
- 確認 T-24 的使用者面文案限制。

### CEO

- 甲案可行，白話句不用改。CEO 層級依風控判定：N114-2～N114-4 與 N114-6 合用同一份決策包。

## 三、驗證

- **old 與錨點**：
  - 現行 ADR 工作樹 12 個錨點，以 Grep `-o` 實測各 1 處：L789、L791、L799、L808、L810、L817、L972、L1248、L1255、L1282、L1283、L2583。前四個以外，其餘就是原第二批 N114-1～N114-5 的 old 與錨點，行號已換算。
  - 草稿 17 個 old 與錨點，以 Grep `-o` 實測各 1 處：L286、L306、L307、L309、L311、L313（兩處）、L320（兩處）、L327、L332、L334、L336、L337、L339、L340、L344、L347。
  - 新 token 在現行 ADR 都是 0：`first_judged`、`補判`、`首判`、`從未判定`、`N114-`、`(t數字)`、`N-114`、`首次判定即終局`、`本次首判日`。
- **第二批落檔後預期計數**（ADR 單檔，以 Grep `-o` 計，從原第二批的值逐項加總）：

| 字串 | 落檔前 | 原第二批 | 本版第二批 |
|---|---|---|---|
| `N-114` | 0 | 11 | **36**（本文 32、紀錄 4） |
| `首次判定即終局` | 0 | 3 | **3** |
| `本次首判日` | 0 | 6 | **17** |
| `first_judged_sessions_json` | 0 | 0 | **17** |
| `補判` | 0 | 0 | **33** |
| `N114-` | 0 | 6 | **22** |
| `(t8)` | 0 | 0 | **3** |
| `從未判定日` | 0 | 0 | **3** |

  - 落檔後應為 0 的字串：
    - `也就是晚於本交易開始時讀到的 M`
    - `觀察日 S ≤ M 時，S 已判定`
    - `S ≤ M 時，本次稽核不判定 S`
    - `M 不前進`
    - `不另存水位〔推論，依本子點與已判定日的前綴性質〕`
    - `以 `session` ≤ M 的列直接呼叫`
    - 「另一面」原句 `next_session(S) 的定案資料進入市場 DB 之前`
    - `殘餘：D-7 第 2 點「還原疑似時的共同守衛」`
    - `方向：補定義（不變：把無法實作的字面`
    - `新登記的 claim 不會對過去的觀察日補列`
    - `首判時點的依賴與還原守衛的殘餘`
    - `CEO：依風控對 N114-4 方向的判定`
  - 計數是依落字稿人工加總的，沒有跑程式。T-06、T-18、T-21、T-22 照風控原文，我已確認這幾處不含表中 token，但 T-18 含 `N114-` 2 處、`補判` 1 處、`從未判定日` 1 處，已計入。tech-writer 落檔後要以 Grep `-o` 重算比對。
- **讀過的檔**（全部只讀）：
  - quant 草案全文；風控確認檔全文；我的第二批草稿；
  - ADR L270-331（各表用途限制）、L760-824、L956-981、L1241-1290、L1572-1661、L1838-1853、L2551-2590、L5584-5587。
  - trial.md 超過讀取上限，沒有讀；只依 quant 草案的 E-09～E-14 判讀。
- **推論、未查證**：
  - 歸屬窗重疊、補判多半是 `'*'` 列，都是依 D-8 第 2 點推論。
  - 「第一批已在工作樹」是依計數判定，是否已 commit 我沒有用 git 核對。
- **沒有做的事**：沒有寫檔、沒有跑指令、沒有讀 `.env`、沒有碰 `*.db`。

## 四、下一步

1. **coordinator**：
   - 依本回報第一句「甲案可行」送 CEO 決策包，白話句照風控 C 第 2 項。
   - 把 T-01～T-25 與 quant 的重送稿一起送風控重審，提醒重審 T-06 的增補與 T-03/T-04/T-08/T-12/T-15/T-16 這幾處連帶修改。
   - 用 git 核對第一批是否已 commit。
2. **quant-researcher**：依第二節「需同步」各項改 E-06、E-07、E-09、E-11、E-12、E-14，重算計數。
3. **risk-compliance-officer**：重審。若不同意 T-06 增補，刪掉那一句與 (t8) 的第二格即可，其餘不受影響。
4. **tech-writer**：風控重審通過、CEO 明確同意之後，把第二批和 v0.30 放在同一個 commit，接在 L5586 之後落檔，再依第三節計數表核對。之後送 qa-reviewer，Codex 第二意見要另外補跑。
5. **dev-lead**：B6 依第二節 E 的四條約束實作，落檔之前不實作。

相關檔案：
- /home/user/AICompany/work/reviews/2026-10-24-N113N114N115澄清起草-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-24-N114第二批與v0.30逐字確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-24-v0.30缺日首判終局同步草案-quant.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
