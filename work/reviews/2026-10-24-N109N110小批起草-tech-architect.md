# N-109、N-110 小批起草

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-109、N-110 小批已起草，共 7 項加 1 段修訂紀錄：N109-1、N109-2、N110-1～N110-5、修訂紀錄。我沒有寫檔，也沒有跑指令。
- **N-109 的定案**：`scope_reason` 維持單一值，取值採固定優先序。scheduled 列從本列 `run_id` 的範圍快照讀取，依 `("market", "sector", "holding", "watchlist")` 取排在最前的值，所以同時在庫存與自選時一律是 `holding`。on-demand 列一律是 `queried`。值由 store 自己決定，呼叫端不能傳入；另外加了寫入驗證和用途限制（讀它的地方用 AST 列舉）。
- **對 D-11.4 與 LM 原因片段**：沒有影響。依據是全檔 `scope_reason` 只出現 2 處（L330 欄位宣告、L5471 引文）；`not_in_schedule` 看的是範圍快照有沒有這檔（L1703）；LM-88、LM-89 看的是 `plan_record.in_holdings_or_watchlist_at_plan`（L1715）。
- **事先宣告**：不改字。事先宣告 §6.1 本欄的值域是 `market`／`sector`／`holding`／`watchlist`／`queried`，並寫「引用 `forecast_scope_snapshot`」（事先宣告草案 L1657），本規則留在這個範圍內。事先宣告裡個股是庫存與自選合併計算（L874、L877），沒有分開兩者的統計。
- **風控**：N109-1、N109-2 需要送逐字確認，這是風控 2026-10-24 自己提的要求。N-110 各項不需要。
- **CEO**：每一項都是「否」。
- **另外兩點**：
  - N-110 的 medium 我多改了一處：`error_class` 也移進寫入函式。except 區塊裡的 `type(exc).__name__` 本身就是函式呼叫，同樣違反 FL-74 (b)。
  - qa 那項 low（N108-2 是否允許 `ast.AnnAssign`）其實會擋 CI，我改成允許。CI 跑 `mypy app tests` strict〔事實：`/home/user/AICompany/.github/workflows/stock-desk.yml:36-37`〕，沒有型別註記的空 list 或 dict 會被判錯。

## 各部門回報
- **tech-architect**：依 HEAD 4e815bb 的 ADR-0027 字面起草。下文 L 都是 HEAD 行號；每個 old 與錨點都已用 Grep `-o` 實測，恰好 1 處。

### 一、N-109 方案比較
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **固定優先序、單一值（採用）** | 欄位形狀和值域不變，在事先宣告 §6.1 之內；完整的 `reason` 集合可以用 (`run_id`, `scope_kind`, `scope_key`) 對回範圍快照取得（N-108 已讓主鍵含 `reason`），資訊沒有遺失 | 單看本欄看不出這檔也在自選 | 有人誤把 `holding` 當成「只在庫存」。用途限制禁止任何讀取者，可擋住 |
| 改為集合欄位 | 本欄自己就完整 | 改變事先宣告 §6.1 的欄位形狀，要改事先宣告；和範圍快照成為兩份資料來源 | 兩處不一致 |
| 新增合併值（例如 `holding_and_watchlist`） | 一眼看得出來 | 擴充值域，要改事先宣告 | 組合數變多 |
| 每個 `reason` 各寫一筆 | 不必選 | 違反 M-6 唯一索引，也違反 N-108 句「一個範圍不因有兩個 `reason` 而計兩次」 | 灌水 n（否決） |

`holding` 排在 `watchlist` 前面，只是沿用 D-3 L281 與事先宣告 §6.1 的列舉順序，不是新的判斷。

### 二、落字稿

**通則**
- 本批只有 N110-1 與 N110-2 是取代，其餘是插入或句末接字。各錨點互相獨立：N110-4 改 (n) 行的中段，N109-2 的錨點是 (n) 行的句尾。
- N109-1 至 N110-5 可以依任意順序落檔，修訂紀錄一定最後落。
- N109-1 與 N109-2 必須同一個 commit；N110-1 與 N110-2 必須同一個 commit。

**N109-1｜D-3 `forecast_record`（L330 之後插入新行）｜補定義（收緊）｜CEO：否｜送風控**
```text
錨點（保留，整行）:   - 識別：`forecast_id`（ULID）、`run_id`、`claim_id`、`scope_kind`、`scope_key`、`scope_reason`、`horizon`、`data_as_of`；
在該行之後插入新行:
    - （N-109；後續追蹤清單 N-109；tech-architect 2026-10-24）**`scope_reason` 的取值**：由 `store.py` 寫入 `forecast_record` 的函式在該列的寫入交易內自行決定，不接受呼叫端傳入。`trigger = scheduled` 的列：讀本列 `run_id` 的 `forecast_scope_snapshot` 中同一 (`scope_kind`, `scope_key`) 的各列，依常數 `SCOPE_REASON_ORDER = ("market", "sector", "holding", "watchlist")`（`store.py`，名稱暫定；與 `forecast_scope_snapshot.reason` 列舉的前四值同序）取排在最前的 `reason`；同一標的同時在庫存與自選時（D-3 `forecast_scope_snapshot` 的 N-108 句），一律為 `holding`。`trigger = on_demand` 的列一律為 `queried`（事先宣告 §6.1 `scope_reason`；V2-04「臨時查詢另標」）。本欄是單一值，不改為集合，也不新增合併值；一筆紀錄完整的 `reason` 集合，以 (`run_id`, `scope_kind`, `scope_key`) 對回 `forecast_scope_snapshot` 取得，不另存第二份。**寫入驗證**（任一項不成立就拒絕寫入）：`trigger = scheduled` ⇒ 本列 `run_id` 的範圍快照至少有一列同一 (`scope_kind`, `scope_key`)，各列的 `reason` 都在 `SCOPE_REASON_ORDER` 內，而且 `scope_reason` 等於依上述規則重算的值；`trigger = on_demand` ⇒ `scope_reason = 'queried'`。**用途限制**：本欄不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W、D-11.4 的 `unavailable_reason` 與片段選擇（`not_in_schedule` 依範圍快照是否含該檔；LM-88、LM-89 依 `plan_record.in_holdings_or_watchlist_at_plan`）或任何判定。除了 `store.py` 的寫入、寫入驗證與 `content_hash` 的計算之外，`views`、`display.py`、`validation.py`、`audit.py`、API route 與匯出都不讀本欄（AST）；任何統計、揭露、畫面或 API 欄位要讀本欄，須先修訂本點並送風控。
```
這樣寫為什麼成立：
- scheduled 列必定能在範圍快照中找到自己的範圍。依 N-86 子點（L286），範圍迴圈只寫範圍快照內的範圍，而範圍快照在 A-25 交易就已 commit。
- scheduled 列不會是 `queried`。排程範圍的來源只有大盤、族群、庫存、自選四種（L284）。

**N109-2｜FL-77 在 (n) 行之後插入 (o)｜收緊（測試）｜CEO：否｜隨 N109-1 送風控**
```text
錨點（保留）: A 的兩項 `market` 不同 → 違規。
在該行之後插入新行:
  - (o)（N-109；D-3 `forecast_record` 的 N-109 子點）`scope_reason`：(n) 的 fixture，22:10 寫入的 A 兩筆紀錄（h＝3、h＝5）都是 `holding`，B 的都是 `sector`，C 的都是 `watchlist`；改為 A 只在自選 → A 的都是 `watchlist`。on-demand 寫入的列都是 `queried`。寫入函式沒有 `scope_reason` 參數（簽章）。寫入驗證的重算放在 `store.py` 的純函式內，直接以違規輸入呼叫，下列各一格都判為違規：scheduled 列的值與重算不同（A 記為 `watchlist`）；本列 `run_id` 的範圍快照沒有該範圍；範圍快照的 `reason` 為 `queried`；on-demand 列不是 `queried`。AST：D-3 同子點用途限制所列的模組不讀本欄。
```

**N110-1｜D-7 第 7 點 N-86 子點「函式結構」（L1065）｜取代｜補定義（不變）｜CEO：否**
```text
old: 每一句都是『單一區域名稱 ＝ 常數（含 None）或空的 list、dict、tuple 字面值』的指派，不得有函式呼叫、屬性存取、下標或其他陳述式；try 的 except 區塊以這些區域變數與傳入的範圍快照，填中止用 run_end 的 `scopes_done`、`scopes_missed` 與 `refused_scopes_json`（本點 N-52 子點；N-108）；
new: 每一句都是『單一區域名稱 ＝ 常數（含 None）或空的 list、dict、tuple 字面值』的指派，可以帶型別註記（註記不受本句限制；區域變數的註記在執行時不求值），不得有函式呼叫、屬性存取、下標或其他陳述式；try 的 except 區塊不做任何運算，只以這些區域變數、函式的參數（含傳入的範圍快照）與 except 綁定的例外名稱為引數，呼叫中止用 run_end 的寫入函式；`scopes_missed`（範圍快照的相異 (`scope_kind`, `scope_key`) 數減 `scopes_done`）、`refused_scopes_json` 的排序與序列化，以及 `error_class`（D-3 `forecast_run_end.error_class` 的規則），都由該寫入函式在內部計算（本點 N-52 子點；FL-74 (b)；N-108、N-110）；
```

**N110-2｜FL-76 (p)（L2566）｜取代｜不變（測試，隨 N110-1）＋收緊｜CEO：否**
```text
old: 只有目標為單一 `ast.Name`、值為 `ast.Constant` 或空的 `ast.List`／`ast.Dict`／`ast.Tuple` 的 `ast.Assign`（N-108；D-7 第 7 點 N-86 子點「函式結構」）；行為面由 FL-74 (e)、(f) 涵蓋。
new: 只有目標為單一 `ast.Name`、值為 `ast.Constant` 或空的 `ast.List`／`ast.Dict`／`ast.Tuple` 的 `ast.Assign`，或目標為單一 `ast.Name`、`simple = 1`、`value` 不是 None、值的條件同上的 `ast.AnnAssign`（`annotation` 不檢查）（N-108、N-110；D-7 第 7 點 N-86 子點「函式結構」）；包住範圍迴圈的 `except Exception` 區塊內，中止用 run_end 寫入函式的那一個呼叫，每個位置引數與關鍵字引數的值都是 `ast.Name`（N-110）；行為面由 FL-74 (e)、(f) 涵蓋。
```

**N110-3｜FL-76 (o2)（L2565）｜句中取代｜收緊（測試：spy 計次）｜CEO：否**
```text
old: 每次稽核恰呼叫一次（AST：呼叫點恰一個）。
new: 每次稽核恰呼叫一次（AST：呼叫點恰一個；行為：以委派給原函式的 spy 替換 `app.forecast.audit.build_gap_rows`，FL-74 (e) 的稽核（三個範圍、六個 claim 都記缺日列）與 FL-76 (s) 的稽核（沒有缺日列）各一格，一次稽核的呼叫次數都恰為 1；N-110）。
```

**N110-4｜FL-77 (n)（L2584）｜句中取代｜不變（措辭）｜CEO：否**
```text
old: (g1) 另加兩格：
new: (g1) 另加兩格（連同 (g1) 原有五格，共七格）：
```

**N110-5｜FL-77 (l) 句末（L2582）｜句末接字｜收緊（測試）｜CEO：否**
```text
錨點（保留）: `forecast_record_attempt_end.outcome` 的值域恰為三值。
接在句末: （N-110）`no_pending_scopes_json` 不設 DEFAULT（D-3 `forecast_run.no_pending_scopes_json` 的 N-108 句）：建表後 `PRAGMA table_info(forecast_run)` 中本欄的 `notnull` 為 1、`dflt_value` 為 None（SQL NULL）；以直接 SQL 插入一列不含本欄、其餘欄位皆為有效值的 `forecast_run` → `sqlite3.IntegrityError`，沒有列寫入。
```

**修訂紀錄｜接在檔尾 L5474（N-108 段「落檔後的閘門」那一行）之後，前面先加一行 `---`**
```text
---

**N-109、N-110 小批（後續追蹤清單 N-109、N-110；D-3 `forecast_record`、D-7 第 7 點、FL-76、FL-77；方向：逐項標示，見各項）**
- 來源與套用範圍：
  - N-109：`work/reviews/2026-10-24-N108記錄一步澄清批起草-tech-architect.md`「下一步」第 2 點；風控 2026-10-24 的要求見後續追蹤清單同項（日後任何統計、揭露或畫面讀本欄之前須先定案送風控；`forecast_record` 只增不改，實作時取值會永久凍結）。
  - N-110：`work/reviews/2026-10-24-ADR0027-N108批落檔審查-qa-reviewer.md`「問題清單」（medium 一項、low 四項）。
  - tech-architect 2026-10-24 起草：`work/reviews/2026-10-24-N109N110小批起草-tech-architect.md`。
  - CEO：否。風控：N109-1、N109-2 依上述要求送逐字確認，確認之後才落檔；N110-1～N110-5 不需要（不改任何揭露、統計或缺日列的定義）。
  - 事先宣告不改字：N109-1 只在事先宣告 §6.1 本欄的值域與「引用 `forecast_scope_snapshot`」之內定取值規則。本批可以單獨 commit。
- 逐項（被取代的原文：判準同 v0.25 同步批段）：
  - N109-1 D-3 `forecast_record` 的取值規則：方向：補定義（收緊：新增寫入驗證與用途限制）。CEO：否。插入，無被取代原文。
  - N109-2 FL-77 (o)：方向：收緊（測試）。CEO：否。插入，無被取代原文。
  - N110-1 D-7 第 7 點 N-86 子點「函式結構」：方向：補定義（不變：except 區塊的運算移入中止用 run_end 的寫入函式，FL-74 (b)「區塊內只呼叫中止用的 run_end 寫入函式」因此可照字面成立；try 之前的初始化可帶型別註記，「A-25 commit 之後、try 之前沒有會拋例外的程式」的原意不變）。CEO：否。被取代的原文——
    > 每一句都是『單一區域名稱 ＝ 常數（含 None）或空的 list、dict、tuple 字面值』的指派，不得有函式呼叫、屬性存取、下標或其他陳述式；try 的 except 區塊以這些區域變數與傳入的範圍快照，填中止用 run_end 的 `scopes_done`、`scopes_missed` 與 `refused_scopes_json`（本點 N-52 子點；N-108）；
  - N110-2 FL-76 (p) 的對應 AST 條件：方向：不變（測試，隨 N110-1）＋收緊（except 區塊內的呼叫引數只能是名稱）。CEO：否。被取代的原文——
    > 只有目標為單一 `ast.Name`、值為 `ast.Constant` 或空的 `ast.List`／`ast.Dict`／`ast.Tuple` 的 `ast.Assign`（N-108；D-7 第 7 點 N-86 子點「函式結構」）；行為面由 FL-74 (e)、(f) 涵蓋。
  - N110-3 FL-76 (o2) 的呼叫次數：方向：收緊（測試：spy 計次）。CEO：否。被取代的原文——
    > 每次稽核恰呼叫一次（AST：呼叫點恰一個）。
  - N110-4 FL-77 (n) 的 (g1) 格數：方向：不變（措辭）。CEO：否。被取代的原文——
    > (g1) 另加兩格：
  - N110-5 FL-77 (l) 句末：方向：收緊（測試：本欄不設 DEFAULT）。CEO：否。句末接字，無被取代原文。
  - 本段。
- 照實並陳：
  - N109-1 採「固定優先序、單一值」。不採集合欄位或合併值，因為兩者都會改變事先宣告 §6.1 本欄的形狀或值域；不採每個 `reason` 各寫一筆，因為同一範圍會計兩次，抵觸 M-6 的唯一索引與 D-3 `forecast_scope_snapshot` 的 N-108 句「一個範圍不因有兩個 `reason` 而計兩次」。代價：單看本欄看不出同一檔也在自選，完整集合只能對回範圍快照取得。`holding` 排在 `watchlist` 之前，只是沿用 D-3 與事先宣告 §6.1 的列舉順序，不代表任何統計上的區分；事先宣告的個股驗證狀態是庫存與自選合併的紀錄（§1.3，PA-4），沒有依兩者分開的統計。
  - N110-1 允許型別註記，是因為 CI 以 mypy strict 檢查 `app`〔事實：`.github/workflows/stock-desk.yml:36-37`〕，沒有註記的空 list 或 dict 會被判錯；區域變數的註記在執行時不求值〔推論，依 PEP 526〕，所以不會在 try 之前拋例外。
  - N110-3 的兩格不涵蓋 FL-76 (k)、(r)（帳目矛盾時拋例外）；這兩種情形的呼叫次數，本批不規定。
- 待決事項與同批規則：
  - N109-1 與 N109-2 必須同一個 commit；N110-1 與 N110-2 必須同一個 commit。修訂紀錄（本段）最後落檔。
  - 落檔後的閘門：dev-lead 的範圍迴圈函式、中止用 run_end 寫入函式與 `forecast_record` 的寫入路徑，依本批的字面實作；本批落檔前，這三處不實作。
```
coordinator 轉存本回報時，請用修訂紀錄裡寫的檔名 `work/reviews/2026-10-24-N109N110小批起草-tech-architect.md`，這樣修訂紀錄裡就沒有占位字。風控確認時若給了自己的確認檔名與字句，照 N-108 的 R-2 前例取代「風控：……」那一行。

### 三、落檔後預期值（ADR-0027 單檔，Grep `-o` 計次數；落檔前為本次實測）
| 字串 | 落檔前 | 淨增 | 落檔後 |
|---|---|---|---|
| `N-109` | 0 | +6（N109-1:2、N109-2:2、修訂紀錄:2） | 6 |
| `N-110` | 0 | +7（N110-1:1、-2:2、-3:1、-5:1、修訂紀錄:2） | 7 |
| `scope_reason` | 2 | +6（N109-1:4、N109-2:2） | 8 |
| `SCOPE_REASON_ORDER` | 0 | +2 | 2 |
| `` `queried` ``（含反引號） | 0 | +4（N109-1:1、N109-2:3） | 4 |
| `AnnAssign` | 0 | +1 | 1 |
| `ast\.Assign` | 1 | +1（修訂紀錄引文） | 2 |
| `build_gap_rows` | 3 | +1 | 4 |
| `dflt_value` | 0 | +1 | 1 |
| `PRAGMA` | 0 | +1 | 1 |
| `DEFAULT` | 3 | +2（N110-5:1、修訂紀錄:1） | 5 |
| `共七格` | 0 | +1 | 1 |
| `臨時查詢另標` | 0 | +1 | 1 |

- **被取代的原文**：N110-1、N110-2、N110-3 的 old，以及 `(g1) 另加兩格：`，落檔後各 1 處，都在修訂紀錄的引文裡。
- **插入錨點**：L330 整行、`A 的兩項 \`market\` 不同 → 違規。`、`` `forecast_record_attempt_end.outcome` 的值域恰為三值。 ``、`本批落檔前，範圍迴圈函式與缺日稽核的寫入路徑不實作。`，落檔後仍各 1 處。

### 四、對實作的約束（給 dev-lead，逐條可檢查）
1. 範圍迴圈函式的 except 區塊只有一個呼叫，就是中止用 run_end 寫入函式，而且每個引數都是 `ast.Name`。`scopes_missed`、`refused_scopes_json`、`error_class` 都在寫入函式內算。
2. try 之前的初始化可以寫成 `refused: list[RefusedScope] = []`，但一定要有值，不能只寫 `x: int`。
3. `scope_reason` 不設為 `forecast_record` 寫入函式的參數，由 store 在交易內讀範圍快照決定。on-demand 寫 `queried`。
4. 除了 store 的寫入、寫入驗證與 `content_hash` 計算，`app/` 不讀 `scope_reason`。
5. `no_pending_scopes_json` 的 DDL 是 `NOT NULL`，而且沒有 DEFAULT。
6. FL-76 (o2) 加 spy 計次格，FL-77 加 (l) 句末與 (o) 兩格。

- **quant**：事先宣告不改字。可以知會 N109-1，但不需要確認。
- **風控**：N109-1、N109-2 需要逐字確認，請 coordinator 轉送。
- **其他部門**（product-manager、qa-reviewer、qa-e2e、devops-sre、tech-writer、frontend-engineer 等）：本次未參與。這是純起草，沒有 diff；落檔後的 diff 照例送 qa-reviewer。

## 驗證
- **old 與錨點**：7 個 old 與錨點都已在 HEAD 用 Grep `-o` 實測，各恰好 1 處，行號是 L330、L1065、L2565、L2566、L2582、L2584（兩處）、L5474。檔尾是 L5474。
- **計數**：「落檔前」是本次實測。`scope_reason` 實測 2 處，`DEFAULT` 實測 3 處；`` `queried` ``、`AnnAssign`、`dflt_value`、`PRAGMA`、`N-109`、`N-110`、`共七格`、`臨時查詢另標` 實測都是 0。「落檔後」是依落字稿逐項加總，tech-writer 落檔後用同樣的 Grep `-o` 重算比對即可。
- **D-11.4 與 LM 片段不受影響**：依據是 L1698～L1717 的判定與片段對應，以及全檔 `scope_reason` 只有 2 處。
- **事先宣告**：比對了 `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md` 的 L1657、L757、L874、L877、L2282。所有提到 holding、watchlist、自選的地方都是合併計算。
- **沒有做的事**：
  - PEP 526「區域變數的註記不求值」是我依語言規格的推論，沒有實際執行驗證。
  - `work/` 下的檔案被 rg 預設的 ignore 排除，所以追蹤清單是直接指定路徑讀的。
  - 沒有讀 `.env` 或 `*.db`，沒有寫檔，沒有跑指令。
- CEO 不需要親自驗證任何事項。

## 下一步
1. coordinator 先把 N109-1、N109-2 的 new 字句送風控逐字確認（輕量）。確認後，依第二節交 tech-writer 落檔，單獨一個 commit，再送 qa-reviewer。Codex 第二意見仍缺席，需要另外補跑，或由 CEO 接受缺席。
   - 如果 CEO 要 dev-lead 立刻動工範圍迴圈，可以把 N-110 拆成先行批，不必等風控。這需要我改寫成兩段修訂紀錄，請另外指示。
2. coordinator 更新後續追蹤清單：N-109、N-110 標「已起草，待風控（N-109）與落檔」。
3. 建議新增追蹤項〔推論，只做了字串搜尋〕：on-demand 的 `forecast_run` 也受 `no_pending_scopes_json NOT NULL`（沒有 DEFAULT）約束，但原文沒有定義 on-demand run 這一欄的值，也沒有定義 on-demand run 是否寫 `forecast_scope_snapshot`。N109-1 的 on-demand 規則不依賴這兩件事，所以本批不處理；on-demand 實作之前要定案。
4. 落檔之後，dev-lead 依第二節第四點的約束實作。
