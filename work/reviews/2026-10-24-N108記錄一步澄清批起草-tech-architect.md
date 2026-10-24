# N-108 記錄一步落檔審查澄清批起草

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-108 小批修訂已起草，共 N108-1～N108-9，qa 第五節的 5 項加上風控 2 項 suggested 全部涵蓋。我沒有寫檔、沒有跑指令。
- **約束 6 的定案**：不另加傳入的狀態物件。改為「try 之前只可有純區域變數的初始化」，FL-76 (p) 的 AST 條件同步改成可機械判定的寫法。
- **CEO**：每一項都是「否」。
- **風控**：不需要逐字確認。這批不改任何揭露、統計或缺日列的定義；FL-77 (c)、(f2) 直接照風控 suggested 的字句。
- **事先宣告**：不改字，這批可以單獨 commit。

## 各部門回報
- **tech-architect**：依 HEAD `636054c` 的 ADR-0027 字面，以及 qa 審查檔第五節、風控確認檔第 77 行的 suggested，裁定與起草如下。下文的 L 都是 HEAD 行號；每個 old 與錨點都已用 Grep `-o` 實測，恰好 1 處。

### 一、約束 6 怎麼定案

| 方案 | 優點 | 缺點 |
|---|---|---|
| 計數器改由傳入的可變狀態物件承載 | 「第一個陳述式是 try」的字面可以不改 | 入口函式要在「前置段呼叫與範圍迴圈呼叫之間只有返回分支」的規則外，多建一個物件；`RecordProgress` 已明定只有欄位 `t`；記錄一步的內部狀態會外露 |
| 初始化放進 try 內，except 再補預設值 | 字面不改 | except 區塊要判斷變數是否已綁定，違反 FL-74 (b)「區塊內只呼叫中止用 run_end 寫入函式」 |
| **try 之前只可有純區域變數的初始化（採用）** | AST 可以精確判定；不會拋例外，所以原本要守的「A-25 commit 之後、try 之前沒有會拋例外的程式」照樣成立 | 字面放寬一點；`MemoryError` 屬程序層級失敗，不在考量範圍〔推論〕 |

### 二、落字稿

**通則**
- N108-1～N108-8 可以依任意順序落檔；N108-9（修訂紀錄）一定最後落，因為它會引用被取代的原文，先落的話錨點就不再唯一。
- N108-1 與 N108-2 必須在同一個 commit。
- 方向與 CEO 層級逐項寫在 N108-9 裡。

**N108-1｜D-7 第 7 點 N-86 子點「函式結構」（L1065）｜取代｜補定義（不變）｜CEO：否**
```text
old: 範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try；
new: 範圍迴圈函式在包住範圍迴圈的 try 之前（docstring 除外），只能有計數與拒寫清單的初始化，每一句都是『單一區域名稱 ＝ 常數（含 None）或空的 list、dict、tuple 字面值』的指派，不得有函式呼叫、屬性存取、下標或其他陳述式；try 的 except 區塊以這些區域變數與傳入的範圍快照，填中止用 run_end 的 `scopes_done`、`scopes_missed` 與 `refused_scopes_json`（本點 N-52 子點；N-108）；
```

**N108-2｜FL-76 (p)（L2566）｜取代｜不變（測試，隨 N108-1）｜CEO：否**
```text
old: 範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try。
new: 範圍迴圈函式中包住範圍迴圈的 try 之前（docstring 除外），只有目標為單一 `ast.Name`、值為 `ast.Constant` 或空的 `ast.List`／`ast.Dict`／`ast.Tuple` 的 `ast.Assign`（N-108；D-7 第 7 點 N-86 子點「函式結構」）；行為面由 FL-74 (e)、(f) 涵蓋。
```

**N108-3｜FL-76 (o1)、(o2)（L2565）｜取代｜收緊（測試：接縫具名，呼叫點恰一個）｜CEO：否**
```text
old: (o1) 寫入驗證的重算放在純函式內，直接以違規輸入呼叫；(o2) 整合測試以 monkeypatch 替換稽核函式中、第一次判定到寫入之間唯一經過的函式（名稱暫定），注入違規值 → 整個稽核交易不寫入、記 WARNING。重算的路徑不經過被替換的函式（AST）。
new: (o1) 寫入驗證的重算放在 `audit.py` 的純函式 `verify_gap_rows`（名稱暫定）內，直接以違規輸入呼叫；(o2) 注入點是 `audit.py` 的模組層級函式 `build_gap_rows`（名稱暫定）：缺日稽核函式把第一次判定的結果交給它，取得要寫入的 `forecast_gaps` 列，每次稽核恰呼叫一次（AST：呼叫點恰一個）。整合測試以 monkeypatch 替換 `app.forecast.audit.build_gap_rows`，注入違規值 → 整個稽核交易不寫入、記 WARNING。`verify_gap_rows` 的重算路徑不呼叫 `build_gap_rows`（AST）。兩個名稱改動時同步改本格（N-108）。
```

**N108-4｜D-3 `no_pending_scopes_json` 的既有列（L287 句末）｜句末接字｜補定義（收緊：不設 DEFAULT、禁止回填）｜CEO：否**
```text
錨點（保留）: 範圍快照與本欄的聯集，就是本 run 讀到的完整排程範圍。
接在句末: （N-108）本欄屬於 `forecast` component 的初版 DDL（ADR-0026 D-6；D-2 第 5 點），與 `forecast_run` 同時建立；`app/forecast/` 尚不存在〔事實：dev-lead 2026-10-24 N-86 查證〕，沒有任何 `forecast` schema 版本上線，所以沒有既有列，不需要遷移。不設 DEFAULT：漏填時拒絕寫入，不得靜默成為 `[]`。若本欄晚於 `forecast_run` 的第一個上線 schema 版本才落地，既有列不得以 DEFAULT 或 UPDATE 回填 `'[]'`（D-2 第 2 點只增不改；回填會把沒有分割過的 run 呈現成「沒有其餘範圍」），遷移方式依 ADR-0026 D-6.5 另案送風控，核可之前本欄與 D-3 `plan_coverage_log` 的不一致標的數不得上線。
```
- 為什麼不給 DEFAULT `'[]'`：給了 DEFAULT，分割程式漏填時會被靜默接受，這正好是 FL-77 (g) 要抓的錯誤。
- 這段寫法與 D-2「只增不改」、第 5 點「欄位保留型遷移」一致：條文明文禁止回填，遷移另案處理。

**N108-5｜D-3 分割與完整性檢查的粒度（L288 句末）｜句末接字｜補定義（收緊：`market` 不一致時拒絕；其餘是把既有意思明寫出來）｜CEO：否**
```text
錨點（保留）: 兩者的聯集恰等於傳入的排程範圍（逐項比對 (`scope_kind`, `scope_key`, `market`, `reason`)，不多不少）。
接在句末: （N-108）**粒度與去重**：排程範圍是四欄 (`scope_kind`, `scope_key`, `market`, `reason`) 的集合，依四欄去重；同一標的同時在庫存與自選時是兩項（`reason` 分別為 `holding`、`watchlist`），不合併。同一 (`scope_kind`, `scope_key`) 的各項 `market` 必須相同，否則拒絕寫入。待寫與分割都以 (`scope_kind`, `scope_key`) 為單位，同一範圍的各項一律落在同一邊：範圍快照每一項各一列 `forecast_scope_snapshot`（主鍵因此含 `reason`，例如 (`run_id`, `scope_kind`, `scope_key`, `reason`)），本欄每一項各一個元素。不相交以 (`scope_kind`, `scope_key`) 比對，所以同一範圍拆在兩邊時判為違規；聯集以四欄比對。`scopes_done`、`scopes_missed` 與 D-3 `forecast_run_end` 的寫入驗證照舊以相異 (`scope_kind`, `scope_key`) 計，一個範圍不因有兩個 `reason` 而計兩次。
```

**N108-6｜FL-77 (c)（L2573）｜句中接字｜收緊（測試；風控 suggested）｜CEO：否**
```text
old: 23:10 的範圍快照恰為 B、C，全部寫入 → `ok`、`scopes_done = 2`；S 沒有缺日列。
new: 23:10 的範圍快照恰為 B、C，`no_pending_scopes_json` 恰為 A，全部寫入 → `ok`、`scopes_done = 2`；S 沒有缺日列。
```

**N108-7｜FL-77 (f1) 句末與 (f2)（L2576）｜取代｜收緊（測試；(f2) 依風控 suggested）｜CEO：否**
```text
old: Y 在 S 的缺日義務不在本格（後續追蹤清單 N-84）。(f2) 兩次執行之間規則只升 PATCH（同一 `claim_id`）→ A 不在範圍快照，不寫入第二筆。
new: Y 在 S 的缺日義務不在本格（後續追蹤清單 N-84）。本格只測寫入端：在已有 `forecast_run` 的觀察日登記新的前瞻 claim，依 N-64、N-66 批在 N-84 定案之前不得進行，生產環境在那之前不會發生（N-108）。(f2) 22:10 寫入 A、B、C；兩次執行之間規則只升 PATCH（同一 `claim_id`）→ 同 (a)：23:10 的範圍快照為空，`no_pending_scopes_json` 恰為 A、B、C，沒有任何範圍寫入第二筆。
```

**N108-8｜在 FL-77 (m) 行之後插入 (n)｜收緊（測試）｜CEO：否**
```text
錨點（保留）: B 寫入，`outcome = ok`、`scopes_done = 1`、`scopes_missed = 0`；稽核 → S 沒有缺日列，不拋 `GapAuditRunInconsistencyError`。
在該行之後插入新行:
  - (n)（N-108）同一標的同時在庫存與自選：fixture 另把 A 加入自選，排程範圍有 A 的兩項（`holding`、`watchlist`）→ 22:10 的 `forecast_scope_snapshot` 有 A 兩列，`scopes_done` 只計 A 一次（`scopes_done = 3`）；23:10 A、B、C 都已寫入 → `no_pending_scopes_json` 恰為 A 的兩項、B、C，範圍快照為空。(g1) 另加兩格：A 的兩項拆在範圍快照與 `no_pending_scopes_json` 兩邊 → 違規；A 的兩項 `market` 不同 → 違規。
```

**N108-9｜修訂紀錄新段，接在檔尾 L5443（N-86 批「落檔後的閘門」那一行）之後，前面先加一行 `---`**
```text
---

**N-108 記錄一步落檔審查澄清批（後續追蹤清單 N-108；D-3、D-7 第 7 點、FL-76、FL-77；方向：逐項標示，見各項）**
- 來源與套用範圍：
  - qa-reviewer：`work/reviews/2026-10-24-ADR0027-N86批落檔審查-qa-reviewer.md`「五、工程角度」（約束 6 為 medium，其餘為 low）；風控 suggested：`work/reviews/2026-10-24-N86記錄一步路徑批逐字確認-風控.md` 對 FL-77 (c)、(f2) 的建議。
  - tech-architect 2026-10-24 起草：`work/reviews/2026-10-24-N108記錄一步澄清批起草-tech-architect.md`。
  - CEO：否。風控：不需逐字確認（不改任何揭露、統計或缺日列的定義；(c)、(f2) 照風控 suggested 字句）。
  - 事先宣告不改字；本批可以單獨 commit。
- 逐項（被取代的原文：判準同 v0.25 同步批段）：
  - N108-1 D-7 第 7 點 N-86 子點「函式結構」：方向：補定義（不變：放寬 AST 字面，以消除與 N-52 子點中止用 run_end 照實計數的衝突；try 之前只可有不會拋例外的純初始化，「A-25 commit 之後、try 之前沒有會拋例外的程式」的原意不變）。CEO：否。被取代的原文——
    > 範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try；
  - N108-2 FL-76 (p) 的對應 AST 條件：方向：不變（測試，隨 N108-1）。CEO：否。被取代的原文——
    > 範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try。
  - N108-3 FL-76 (o1)、(o2) 的接縫：方向：收緊（測試：接縫具名、呼叫點恰一個）。CEO：否。被取代的原文——
    > (o1) 寫入驗證的重算放在純函式內，直接以違規輸入呼叫；(o2) 整合測試以 monkeypatch 替換稽核函式中、第一次判定到寫入之間唯一經過的函式（名稱暫定），注入違規值 → 整個稽核交易不寫入、記 WARNING。重算的路徑不經過被替換的函式（AST）。
  - N108-4 D-3 `forecast_run.no_pending_scopes_json` 的既有列：方向：補定義（收緊：不設 DEFAULT、禁止回填）。CEO：否。句末接字，無被取代原文。
  - N108-5 D-3 分割與完整性檢查的粒度：方向：補定義（收緊：`market` 不一致時拒絕寫入；其餘為不變的明寫）。CEO：否。句末接字，無被取代原文。
  - N108-6 FL-77 (c)：方向：收緊（測試；風控 suggested）。CEO：否。句中接字，無被取代原文。
  - N108-7 FL-77 (f1) 句末與 (f2)：方向：收緊（測試；(f2) 依風控 suggested）。CEO：否。被取代的原文——
    > (f2) 兩次執行之間規則只升 PATCH（同一 `claim_id`）→ A 不在範圍快照，不寫入第二筆。
  - N108-8 FL-77 (n)：方向：收緊（測試）。CEO：否。插入，無被取代原文。
  - N108-9 本段。
- 照實並陳：
  - N108-1 不採「計數器由傳入的可變狀態物件承載」：那會讓入口函式或編排函式多持有記錄一步的內部狀態，而 D-7 第 7 點 N-86 子點的進度物件明定只有欄位 `t`。純區域變數的初始化不會拋例外〔推論；`MemoryError` 屬程序層級失敗，不在此列〕。
  - N108-5：同一 (`scope_kind`, `scope_key`) 的 `market` 不一致是上游資料錯誤；拒絕寫入後依 D-7 第 7 點 N-66 子點記 `error_before_run`，S 的缺日列記 `record_start_failed`，直到上游修正。
  - 同一範圍有兩個 `reason` 時，`forecast_record.scope_reason` 取哪一個，原文沒有規則（D-3 只有欄位宣告一處），本批不定義。
- 待決事項與同批規則：
  - 本批內部不拆開；N108-1 與 N108-2 必須同一個 commit。修訂紀錄（本段）最後落檔。
  - 落檔後的閘門：dev-lead 的記錄一步與 `audit.py` 實作，依 N-64、N-66 批、N-86 批與本批的字面；本批落檔前，範圍迴圈函式與缺日稽核的寫入路徑不實作。
```
coordinator 轉存本回報時，請用 N108-9 裡寫的檔名 `work/reviews/2026-10-24-N108記錄一步澄清批起草-tech-architect.md`，這樣修訂紀錄裡沒有任何占位字。

### 三、落檔後預期值（ADR-0027 單檔，Grep `-o` 計次數；落檔前為本次實測）

| 字串 | 落檔前 | 淨增 | 落檔後 |
|---|---|---|---|
| `N-108` | 0 | +9（N108-1:1, -2:1, -3:1, -4:1, -5:1, -7:1, -8:1, -9:2） | 9 |
| `N-86` | 42 | +5（-2:1, -4:1, -9:3） | 47 |
| `no_pending_scopes_json` | 13 | +5（-6:1, -7:1, -8:2, -9:1） | 18 |
| `build_gap_rows` | 0 | +3 | 3 |
| `verify_gap_rows` | 0 | +2 | 2 |
| `FL-77` | 4 | +5（-9：標題、來源行、N108-6、N108-7、N108-8 各 1） | 9 |
| `N-84` | 10 | +1（-7） | 11 |
| `DEFAULT` | 0 | +3（-4:2, -9:1） | 3 |

**被取代的原文**：
- 樣式 `範圍迴圈函式的第一個陳述式（docstring 除外）是包住範圍迴圈的 try[；。]`：落檔前 2 處（L1065、L2566）；落檔後 2 處，都在修訂紀錄的引文。
- N108-3 的 old：落檔後 1 處，在引文。
- N108-7 的 (f2) 片段：落檔後 1 處，在引文；N108-7 的完整 old 為 0。
- N108-6 的 old：落檔後 0。

**插入錨點**：N108-4、-5、-8、-9 的錨點，落檔後仍各 1 處。

### 四、送審與同步
- **quant**：不需要同步，事先宣告不改字，也不觸及 V27-02。
- **風控**：不需要逐字確認。理由是 N108-5 的 `market` 拒寫屬於 fail-closed，而且只在上游資料錯誤時才會發生；coordinator 若想讓風控知悉，可以另外轉知。
- **CEO**：不新增待決項。

### 五、對實作的約束（給 dev-lead，補充原約束 6、14）
1. 範圍迴圈函式在 try 之前只能有 `名稱 = 常數或空的 []/{}/()` 這種指派；except 區塊用這些變數填中止用的 run_end。
2. 缺日稽核經 `build_gap_rows` 產生要寫入的列，呼叫點恰一個；`verify_gap_rows` 不呼叫它。
3. `no_pending_scopes_json` 不設 DEFAULT，也不得回填。
4. 排程範圍依四欄去重；同一範圍的各項落在同一邊；`forecast_scope_snapshot` 的主鍵含 `reason`；`market` 不一致就拒絕寫入。
5. FL-77 (c)、(f2)、(n) 依新字面建測試。

- **其他部門**（product-manager、quant-researcher、risk-compliance-officer、qa-reviewer、qa-e2e、devops-sre、tech-writer、frontend-engineer 等）：本次未參與。這是純起草、沒有 diff；落檔後的 diff 照例送 qa-reviewer。

## 驗證
- 7 個 old 與錨點都已在 HEAD 用 Grep `-o` 實測，各恰好 1 處，行號如上。
- 「落檔前」的計數是本次實測；「落檔後」是依落字稿逐項加總，tech-writer 落檔後用同樣的 Grep `-o` 重算比對即可。
- 我確認了 `scope_reason` 在 ADR 只出現一次（欄位宣告），所以 N108-9 照實寫「原文沒有規則」。
- 沒有讀 `.env` 或 `*.db`，沒有寫檔，沒有跑指令。
- CEO 不需要親自驗證任何事項。

## 下一步
1. coordinator 依第二節的順序交給 tech-writer 落檔，單獨一個 commit，之後送 qa-reviewer。Codex 第二意見目前缺席，需要另外補跑，或由 CEO 接受缺席。
2. coordinator 在後續追蹤清單新增一項：同一範圍有兩個 `reason` 時 `forecast_record.scope_reason` 的取值規則（原文沒有定義）。
3. 落檔之後，dev-lead 依 N-64、N-66 批、N-86 批與本批的字面實作記錄一步與 `audit.py`。
