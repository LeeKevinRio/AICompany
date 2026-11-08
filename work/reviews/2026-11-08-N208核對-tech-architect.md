# N-208 手動換標的說明核對

- 審查者：tech-architect
- 日期：2026-11-08
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **第 1 部分（唯讀計數）：修改後再交付。** 安全性沒有問題：正本不會被寫入，也不會印出任何代號。但有 4 處必須先改，否則 CEO 看不出指令是成功還是失敗。最嚴重的一處：dev-up 預設路徑下，停機檢查一定會誤報。這幾處改動都很機械，dev-lead 改完、在 sandbox 重跑、更新 SHA 後就可以交，不需要等 qa-reviewer。
- **第 2 部分（手動換標的）：暫不交付。** 四處「[待 TA 核對]」的推論都成立（各附補充）。「只允許補位」的設計方向在 ADR-0035 之下也成立。但寫入指令有三個邏輯缺口：
  - 沒有擋「這個代號在 DB 裡已經有歷史紀錄」的情況。CEO 過去手寫 SQL 的歷史不明，這會直接打破 ADR-0035 的不變式。
  - dry run 實際上會寫 schema。
  - 有些前置條件只靠 CEO 用眼睛判讀，指令本身沒有檢查。

  另外，這份寫入指令會寫入正式帳冊 DB，**必須先送 qa-reviewer 審查（含 Codex 第二意見）**。而且只有第 1 部分的結果顯示確實有空位（(a2) < `n_targets`），第 2 部分才有用處。
- **風控：** 文件裡沒有選股或投資建議。只有 §2.4 改寫了風控已定稿的通知句，還漏掉了「本補充在 N-197a 上線前有效」這個有效期限。改成逐字引用就不必送風控；如果保留改寫，那一句要送風控。

## 各部門回報

- **tech-architect（本人）：** 讀了 N-208、N-203、ADR-0035，以及我上一輪的 N-207 架構評估（`work/reviews/2026-11-08-N207架構評估-tech-architect.md`）。對照查證的 code：`store.py:68-171、279-283、826-868、916-947、1115-1131、1239-1246、1531-1652`，`service.py:1809-1912、2149-2159、2288-2327`，`engine.py:186-215、738-750`，`sqlite_util.py`，`dev-up.bat:150、166、274`，主機部署手冊 `:79-152`，風控通知 `:171`。我沒有執行任何指令（我的工具只能讀檔），所以 SHA 值與 sandbox 輸出都沒有重算。以下依我的輸出契約分節。

### 評估摘要

- 採用：第 1 部分照現行設計（`mode=ro`、`query_only`、對複本執行、只印數字），加上 4 處必要修改。
- 採用：第 2 部分「停機狀態下只補位」的方向。
- 否決：第 2 部分現行版本直接交付。要先補 W-1 到 W-8 八項必要修改，並通過 qa-reviewer 審查。
- 否決：把第 2 部分做成進版控的 script（理由見方案比較）。
- 不新立 ADR。

### 第 1 部分判定

**安全性逐項：**

| 項目 | 判定 | 依據 |
|---|---|---|
| `mode=ro` 加 `query_only` | 成立。不可能寫入主檔 | sandbox 前後雜湊相同 |
| 對複本執行 | 成立。正本只被 `Copy-Item` 與 `Get-FileHash` 讀取 | |
| 檔案不存在就拒絕、不新建 | 成立。走 stdlib，不經過 `PlaybookStore`；`store.py:826-830` 的自動建檔不會被觸發 | |
| 只印數字 | 成立。沒有任何一行會印出 symbol | |
| exit 碼 | **不成立**。文件要 CEO 回報 exit 碼，卻沒有任何一行把 exit 碼顯示出來；而且 exit 2 和 uv、python 自己的錯誤碼撞號 | 見 P1-2 |

**寫入與洩漏路徑：**
- 唯一的寫入：SQLite 以唯讀模式開 WAL 檔時，可能在 `$PROBE` 資料夾建出 `-shm`／`-wal`。這只發生在複本上，可以接受。
- 洩漏：Python traceback 和 `Get-FileHash` 表格會帶出含使用者名稱的路徑，但不含持股資料。文件已寫明雜湊表不必貼回，維持即可。

**PowerShell 上最可能出錯的地方（依可能性排序），以及 CEO 怎麼看出來：**

1. **停機檢查誤報（一定會發生）。** dev-up 用 `cmd /k "... && uv run python -m app.scheduler"` 啟動（`dev-up.bat:166`）。按 Ctrl+C 後 `cmd.exe` 視窗還在，它的 CommandLine 仍含 `app.scheduler`，所以 `Get-CimInstance` 會印出一列。CEO 依文件「必須沒有輸出」，會卡住，或者學會忽略這項檢查。修法見 P1-1。
2. **看不到 exit 碼。** 修法見 P1-2：加結果哨兵行，並印出 `$LASTEXITCODE`。
3. **`$REPO` 沒有把佔位字串換掉，或 `$DB_DIR` 填錯。** 三檔都會顯示 `not present`，接著計數出現 `ERROR: db copy not found`。有訊號，但出現得太晚。修法見 P1-4。
4. **here-string 貼上失敗。** 結尾 `'@` 前面有空白時，PowerShell 會一直停在 `>>` 等待輸入。要在文件裡加一句：「一直出現 `>>` 時按 Ctrl+C 重貼」。如果貼上時縮排被改動，會出現 IndentationError，有了哨兵行就能看出來。也請註明不要用 PowerShell ISE。
5. **`$OutputEncoding` 被 profile 改成帶 BOM 的 UTF-8。** stdin 開頭可能出現 U+FEFF，造成 SyntaxError。文件已有改寫成檔案再執行的備援做法，加上哨兵行就能辨識。
6. **路徑轉 `file:` URI。** `Path.resolve().as_uri()` 在 Windows 會產生 `file:///C:/...`，空白、`#`、非 ASCII 字元都會被百分比編碼，SQLite 能正確解碼。風險低。只有 `$HOME` 在 UNC 或網路磁碟時，會出現 `invalid uri authority` 例外（exit 1）。這有訊號；文件要註明 `$WORK` 必須放在本機磁碟。
7. **中文輸出亂碼。** Python 寫到主控台時走 WriteConsoleW，風險低；而且後面接的 ASCII 說明仍然看得懂。可以選擇把那兩段 `\u` 中文拿掉，只留 `NOT_SET`。

**第 1 部分必要修改（確切改法）：**

- **P1-1：停機檢查改用程式名稱白名單**（與 `dev-up.bat:274` 的做法一致）：
  ```powershell
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^(python|pythonw|uv|uvicorn)\.exe$' -and ($_.CommandLine -like '*app.scheduler*' -or $_.CommandLine -like '*app.main:app*') } |
    Select-Object ProcessId, Name
  ```
  另外補一句：用 NSSM 或工作排程器常駐的，按 Ctrl+C 不夠，要先停用監督程式的自動重啟；做不到就停下來回報。

- **P1-2：結果哨兵行，加上顯示 exit 碼。**
  - 腳本開頭加：
    ```python
    def done(code):
        print('N208_COUNT_RESULT=%d' % code); sys.exit(code)
    ```
  - 兩處 `sys.exit(2)` 改成 `done(20)`；結尾的 `c.close()` 之後加 `done(0)`。
  - 每一行 PowerShell 呼叫（含備援的檔案版）後面加 `; "exit=$LASTEXITCODE"`。
  - 文件寫明：「最後兩行必須是 `N208_COUNT_RESULT=n` 和 `exit=n`，而且兩個數字相同。沒有 `N208_COUNT_RESULT=` 這一行，代表腳本沒有跑完：可能是貼上錯誤、uv 或 python 出問題、或 Python 例外。請把整段輸出貼回，不要自行修改後重試。」
  - exit 碼表補上：1 是 Python 例外；沒有哨兵行就是沒有跑完。

- **P1-3：日期改用 UTC，與 backend 一致。** backend 一律用 `datetime.now(UTC).date()`（`service.py:1827、2149、2320`），CEO 本機在台北時間 00:00–08:00 之間，本地日期會比 UTC 多一天。
  - 把 `from datetime import date` 換成 `from datetime import datetime, timezone`。
  - `today = datetime.now(timezone.utc).date().isoformat()`。
  - 標籤改為 `'(d) rule_params_in_force_on (UTC date, same basis as backend):'`。

- **P1-4：第 3 步的防呆與雜湊比對。**
  - 文件寫明：「沒有看到 `copied: stock-desk.db` 就停下，回到 §2.2 確認」。
  - 檔名不是 `stock-desk.db` 的（`.env` 或 `$env:` 指向別的檔名），停下來回報。
  - 兩張雜湊表改成下面這個不印路徑的比對函式（第 2 部分也會用到）：
    ```powershell
    function Test-N208Same($A, $B) {
      foreach ($f in "stock-desk.db","stock-desk.db-wal","stock-desk.db-shm") {
        $x = Join-Path $A $f; $y = Join-Path $B $f
        $r = if ((Test-Path $x) -ne (Test-Path $y)) { 'PRESENCE_DIFFERS' } elseif (-not (Test-Path $x)) { 'absent_both' } elseif ((Get-FileHash $x).Hash -eq (Get-FileHash $y).Hash) { 'SAME' } else { 'DIFFERENT' }
        "{0}: {1}" -f $f, $r
      }
    }
    Test-N208Same $DB_DIR $BK   # every line must be SAME or absent_both
    ```

- **P1-5（建議，可在同一次修訂一起做）：偵測孤兒指令列。** CEO 手寫 SQL 的歷史不明；如果曾經 DELETE 過批次列，這一項會抓到。
  ```python
  if 'playbook_directives' in names:
      orph = c.execute('SELECT COUNT(*) FROM playbook_directives d WHERE d.batch_no IS NOT NULL AND NOT EXISTS (SELECT 1 FROM playbook_batches b WHERE b.symbol = d.symbol AND b.batch_no = d.batch_no)').fetchone()[0]
  else:
      orph = 0
  print('(f) batch_directive_rows_without_batch_row:', orph)
  ```
  - 必須限定 `batch_no IS NOT NULL`，因為 REBALANCE 列的 symbol 是 `"—"`（`service.py:1891`）。
  - §1.5 對照表加一列：「(f) > 0：先不要做第 2 部分，回報 TA」。

### 第 2 部分判定

**四處「[待 TA 核對]」：**

1. **§2.4 先 REBALANCE、後新增：成立。**
   - `rebalance` 只累計 `open` 且 `remaining_shares > 0` 的批次與現金（`service.py:1836-1853、1870-1871`）。新加的 `planned` 批次不影響 TOTAL_DEPLOY；新標的沒有日線，也不會讓 REBALANCE 回 `insufficient_data`，因為 `missing` 只收持有中的批次。
   - 每批金額讀的是評估當下的 TOTAL_DEPLOY（`engine.py:204-205`）。所以「REBALANCE → 停機 → 新增 → 啟動」能保證新標的第一次評估時，用的就是新一季的值。
   - 這和 N-207 評估裡「先提交、再 REBALANCE」不衝突：N-207 是線上流程，靠戳記閘擋住提交到 REBALANCE 之間的窗口；N-208 用停機消除了這個窗口。
   - 補充：理由不只關係到新標的，所有標的都會在新一季用新的 TOTAL_DEPLOY。

2. **§2.6 ⑨ 之前整檔還原不違反 ADR-0035：成立，但有前提。**
   - 不變式講的是 DB 狀態：任何 (symbol, batch_no) 一生最多只有一列 executed 的 R1 buy。③ 的備份滿足這條不變式。如果 ③ 之後唯一的寫入就是 ⑦ 那一次 INSERT 交易，那麼整檔還原就是這次寫入的精確反操作。
   - 前提有三個，必須寫進文件：
     - (i) 從 ② 到還原，服務一直沒有啟動；
     - (ii) 沒有其他寫入者，例如 N-172／N-177 工具或 DB 瀏覽器；
     - (iii) 三個檔一起還原。
   - 這三個前提要用 W-6 的雜湊比對與停機檢查**證明**，不能只寫成要求。
   - 「⑨ 之後不得整檔還原」也成立，而且理由比不變式更重：帳冊的現金 KV 沒有歷史（ADR-0035 R-1 的否決理由）。⑨ 之後可能已經有指令列被 CEO 拿去券商實際下單，整檔還原會讓帳冊和真實帳戶分歧，而且沒有痕跡。
   - 建議把 §2.6 的註記換成這句：「⑨ 之前、且 W-6 的檢查全部通過時，整檔還原等於 ⑦ 從未執行，不違反 ADR-0035 不變式（tech-architect 2026-11-08 核對）。」

3. **§2.7 以 (a2) 判斷總投入：成立。** 另外補一個單調性論證，可以寫進文件：
   - `closed` 與 `skipped` 都是終態。批次不會回到 `planned`（`store.py:1563-1564`）；`skipped` 只能由 `planned` 轉入（`store.py:1285-1286`）。EMERGENCY_EXIT 不會把 `planned` 改成 `skipped`。
   - 所以服務重新啟動後，(a2) 只會減少、不會增加。離線時檢查「新增後 (a2) == `n_targets`」，就是之後所有時點的上界：這次新增永遠不會造成超額投入。

4. **§2.7 改 `n_targets` 對已部分買進標的的影響：成立。**
   - 末批的股數是 `max(1, floor(新的每檔配置 / close) − already)`（`engine.py:208-215`），其中 `already` 用的是非 `planned` 批次的 `shares`。
   - `n_targets` 調高時，末批可能只買 1 股，因為公式下限是 1，即使該檔已經超出配置也一樣；調低時末批會變大。
   - 已經落檔的 R1 列股數固定，下一次評估才會生效。
   - 再補一句：改 `batches_per_target` 更糟，因為既有批次列的數量不會跟著變，「哪一批是末批」的判定也會錯位。同樣不在本說明的範圍。

**「只允許補位」在 ADR-0035 與結算約束之下：方向成立，但要補三個條件才完整。**
- 已成立的部分：
  - 只新增全新的 (symbol, batch_no)，不 UPDATE、不 DELETE，所以不構成「重置」。
  - `ensure_batches` 的所有 INSERT 在同一個交易裡（`store.py:861`），寫到一半失敗會整筆回滾。
  - G1、K1、claim、`settle()` 都沒有改動。
- **缺口一（最重要）：沒有擋歷史紀錄。**
  - G1 只在「批次列存在而且不是 `planned`」時擋下 buy（`BATCH_LEFT_PLANNED_SQL`，`store.py:279-282`）。
  - 如果 CEO 過去曾手動 DELETE 某檔的批次列，這檔的舊指令列會變成孤兒。現行設計下，孤兒的 buy 結算時只標記排程（`store.py:1616-1618`）。
  - 一旦用同一個代號重新建出 `planned` 批次：還沒結算的孤兒 buy 會被 G1 放行，並在 `settle()` 動到現金與股數；已經結算的孤兒 executed R1，會和新批次將來的 R1 構成同一個 (symbol, batch_no) 的兩列 executed。兩種情況都直接違反不變式。N-207 評估在 Q-T3 也指出過同一個機制：「舊的永久 pending R1 會被 G1 放行」。
  - 現行的 exit 4 只檢查 `playbook_batches`，擋不到這種情況。修法見 W-2。
- 缺口二：b2（batch_no 連號）和 `other_status` 只靠 CEO 判讀第 1 部分的輸出，寫入指令本身沒有檢查。修法見 W-3。
- 缺口三：日期基準與 backend 不一致。修法見 W-4。
- 備註（不阻擋）：「新增後必須剛好等於 `n_targets`」比「不超過 `n_targets`」嚴格。補得比空位少，結果是少投入，屬於安全方向。是否允許只補一部分，屬於產品取捨，交 CEO 決定；預設維持 `==`。

**C5 的處理：對這份寫入指令的路徑來說足夠，但文件要再補兩點。**
- 寫入指令只對沒有任何批次列的代號呼叫 `ensure_batches`（exit 4），批數取自參數，既有標的的批數也必須等於參數（exit 5），所以 C5 在這條路徑上不會發生。
- 要補的兩點：
  - (1) C5 不限於「已經全部 closed」的標的。任何既有標的，只要用較大的批數呼叫，都會多長出批次；有 open 批次的標的，末批的判定還會跟著錯位。§2.6 的說明要改成通則；§2.8「現行標的也不會因為再加一次而多出批次」要改成「**以相同批數**再加一次」。
  - (2) §2.10 加第 3 條：「禁止在本指令以外自行呼叫 `PlaybookStore(...).ensure_batches(...)`（包括 `python -c`）」。N-203 推論 CEO 當初很可能就是用這個方法寫入的。
- 對 N-207 的影響：我在 N-207 評估中已經否決以 `ensure_batches` 作為正式路徑，C5 是這個否決的又一條佐證，不必另外立約束。

**「停機、備份、整檔還原」與帳冊不變式的關係：**
- 這個流程是 ADR-0035 R-3「離線修復工具」模式的簡化版：停服務、先備份、先 dry run、再 apply。
- 但它少了 R-3 的 compare-and-set，也就是無法證明 ⑦ 寫入時的正本，就是 ⑥ 預演時的那份狀態。W-6 用「⑦ 之前正本三檔與 ③ 備份逐檔雜湊相同」補上這一點：雜湊相同，同時證明了三件事：服務在 ③ 之後沒有寫過、沒有其他寫入者、而且 probe 的預演結果適用於正本。
- 補上之後，還原的前提就從「要求」變成「可以驗證」。

**是否先送 qa-reviewer：是，必須送。**
- 理由：
  - 這段程式會寫入正式帳冊 DB；
  - 章程規定「通過審查才算完成」；
  - ADR-0035 R-3 的離線工具也走過審查；
  - 風控在 N-177 C8 的 required 要求「綁定 qa 審查的版本」。
- 審查範圍：修訂後以 SHA-256 釘住的腳本全文、PowerShell 包裝步驟，以及下方約束 N208-C1 到 C10，並附 Codex 第二意見。
- 依 ADR-0007「執行與判斷分離」：sandbox 重跑由 qa-automation 獨立執行，qa-reviewer 只負責判斷。
- 第 1 部分是對複本的唯讀操作，經我核對後可以先交，不必等這輪審查。

**第 2 部分必要修改（確切改法）：**

- **W-1：所有閘門都在唯讀連線上完成；只有 `--apply` 而且全部通過時，才建立 `PlaybookStore`。**
  - 原因：現行版在任何 STOP 之前就先執行 `PlaybookStore(db)`。`_init_schema` 會做 `PRAGMA journal_mode=WAL`、`CREATE TABLE IF NOT EXISTS`、`ALTER TABLE ADD COLUMN`（`store.py:840-854`、`sqlite_util.py:116-123`）。所以 dry run 的「nothing written」不正確，而且 ⑦ 在拒絕的路徑上也已經改過正本的 schema。
  - 改法：
    - 清單檔的解析移到開啟唯讀連線之前。
    - 加上 `from app.playbook.models import RuleParams` 和 `from app.playbook.store import PlaybookStore, system_default_params`。只 import 不會寫檔；只有建立實例才會寫。
    - 唯讀連線上照抄 store 的 SQL：
      ```python
      rows = sorted(ro.execute('SELECT symbol, batch_no, status FROM playbook_batches').fetchall())
      r = ro.execute('SELECT payload FROM playbook_rule_params WHERE effective_date <= ? ORDER BY effective_date DESC, version DESC LIMIT 1', (today.isoformat(),)).fetchone() if 'playbook_rule_params' in tables else None
      params = system_default_params(today) if r is None else RuleParams.model_validate(json.loads(str(r[0])))
      pending = ro.execute('SELECT COUNT(*) FROM playbook_rule_params WHERE effective_date > ?', (today.isoformat(),)).fetchone()[0] if 'playbook_rule_params' in tables else 0
      ```
    - `--apply` 階段：
      ```python
      snap = (params.n_targets, params.batches_per_target, pending, rows)
      store = PlaybookStore(db)
      p2 = store.active_params(today)
      again = (p2.n_targets, p2.batches_per_target, len(store.pending_rule_changes(today)), sorted((b.symbol, b.batch_no, b.status) for b in store.list_batches()))
      if again != snap:
          print('STOP: db changed between check and write'); done(8)
      ```
    - dry run 的訊息改成 `DRY RUN: read-only; nothing written.`

- **W-2：擋下有歷史紀錄的代號**（放在 exit 4 的檢查之後；新的 exit 碼或沿用 4 都可以）：
  ```python
  q = ','.join('?' * len(targets)); hist = 0
  for t, col in (('playbook_directives','symbol'), ('playbook_schedule','symbol'), ('playbook_blacklist','symbol'), ('playbook_symbols','symbol'), ('playbook_evaluation_marks','subject')):
      if t in tables:
          hist += ro.execute('SELECT COUNT(*) FROM %s WHERE %s IN (%s)' % (t, col, q), targets).fetchone()[0]
  if hist:
      print('STOP: %d history row(s) reference listed code(s); report to TA' % hist); done(4)
  ```

- **W-3：在指令內檢查批次的形狀**（取代現行 exit 5 的條件）：
  ```python
  nos = {}
  for s, n, _ in rows: nos.setdefault(s, set()).add(n)
  bad_shape = any(v != set(range(1, bpt + 1)) for v in nos.values())
  bad_status = any(st not in ('planned', 'open', 'closed', 'skipped') for _, _, st in rows)
  if bad_shape or bad_status:
      print('STOP: existing batches are not 1..%d with known statuses; report before changing' % bpt); done(5)
  ```

- **W-4：日期改用 UTC。**
  - `from datetime import datetime, timezone`；`today = datetime.now(timezone.utc).date()`。
  - 用 UTC 時，「待生效版本」的集合只會比用本地日期時更大，所以這個改法同時更保守，也和 backend 一致。

- **W-5：哨兵行，加上更強的寫入後核對。**
  - 同 P1-2，加 `done()`，哨兵行為 `N208_ADD_RESULT=n`；每一行呼叫後面加 `; "exit=$LASTEXITCODE"`。
  - 寫入後的核對改成全表比對，順便證明既有列完全沒動：
    ```python
    after = sorted((b.symbol, b.batch_no, b.status) for b in store.list_batches())
    expect = sorted(rows + [(t, n, 'planned') for t in targets for n in range(1, bpt + 1)])
    good = after == expect
    print('APPLIED: rows added:', len(after) - len(rows), '/ check:', 'OK' if good else 'MISMATCH')
    done(0 if good else 7)
    ```

- **W-6：⑦ 拆成三步。**
  - ⑦-0：再跑一次 P1-1 的停機檢查。
  - ⑦-1：`Test-N208Same $DB_DIR $BK`，每一行都必須是 `SAME` 或 `absent_both`，否則停下來回報。
  - ⑦-2：W-1 修好之後，dry run 已經真正唯讀，所以先對正本跑一次 dry run，數字必須和 ⑥ 的 dry run 相同。
  - ⑦-3：最後才 `--apply`。
  - 還原段同樣改造：還原前跑停機檢查；還原後跑 `Test-N208Same $DB_DIR $BK`，每一行都必須是 `SAME` 或 `absent_both`。

- **W-7：文字修正。**
  - §2.4 第二點改成逐字引用風控的通知全文（`work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md:171`，含「本補充在 N-197a 上線前有效」），並刪掉「實務上：……」那句改寫。
  - §2.6、§2.8、§2.10 依上面「C5 的處理」修正。
  - §2.6 的還原註記換成第 2 點建議的那一句。
  - exit 碼表補上 1（Python 例外）、8（檢查與寫入之間 DB 被改過）、「沒有哨兵行」。
  - 主機部署走 NSSM 或工作排程器的情況，比照 P1-1 的說明。

- **W-8：sandbox 重跑與更新 SHA。**
  - 既有的 A1 到 A14 全部重跑，並新增：
    - A15：清單裡的代號在 `playbook_directives` 有紀錄，預期 exit 4；
    - A16：batch_no 為 1、3、4，預期 exit 5；
    - A17：出現未知 status，預期 exit 5；
    - A18：dry run 與所有 STOP 路徑前後，DB 三檔的雜湊都不變；
    - C6：第 1 部分的 (f) 能數出孤兒指令列。
  - 兩段腳本都重新計算 SHA-256，交 qa-reviewer 時以新的 SHA 為準。

### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A. 把腳本內嵌在文件裡（現行做法，依 W-1 到 W-8 修改） | 不進產品 code；N-207 上線就作廢；⑥ 的 probe 預演本身就是一次 Windows 實機測試 | 沒有 CI、沒有單元測試；只能用 SHA 釘住版本 | 品質完全靠人工審查加 sandbox，所以 qa-reviewer 審查不能省 |
| B. 進版控，做成 `backend/scripts/` 下的 CLI 並附 tests | 有 CI，可以審 commit | 會變成事實上的第二個名單寫入入口，與 N-207／ADR-0043（擬立）的方向重疊，那邊已否決用 `ensure_batches` 建批次；要走完整流程；作廢時還要刪 code | 臨時工具變成長期存在 |
| C. 不交付第 2 部分，等 N-207 | 零寫入風險 | 季末如果有空位，就補不了 | 只會少投入，屬於安全方向 |

決策：預設走 C。只有第 1 部分顯示 (a2) < `n_targets`，而且 CEO 確定了季末 REBALANCE 日時，才走 A，並且必須修訂完、通過審查之後才交付。B 否決。

### 決策（ADR 草案）

不新立 ADR，理由是 N-208 是 N-207 上線前的暫行操作程序，不是新的架構決策；它的約束都可以從 ADR-0035 推導出來。決策紀錄如下，請在 N-208 文件末尾加一節「TA 核對紀錄」：

- **Context：** 排程台沒有正式的換標的入口；CEO 本機寫入標的的歷史不明（N-203）；ADR-0035 的不變式不容許重置批次、不容許 DELETE。
- **Decision：** N-207 上線前，只允許在停機狀態下，為「在所有 playbook 表都沒有任何紀錄的新代號」補位，使「還有 planned 或 open 批次的檔數」等於 `n_targets`。寫入必須通過唯讀閘門、與 ③ 備份的雜湊比對，以及寫入後的全表核對。
- **Consequences：**
  - 好處：不變式成立；不會超額投入，單調性論證保證這一點；出錯時在 ⑨ 之前可以精確還原。
  - 壞處：
    - 不能移除舊標的；
    - 曾經出現過的代號無法再加入；
    - 這類手動新增不會留下 N-207 稽核表（`playbook_roster_log`）的紀錄。N-207 設計時，必須把「有批次列、但沒有名單稽核紀錄」視為合法的歷史狀態；CEO 原本的 5 檔就屬於這種情況。
    - 每次操作都要停機。

### 對實作的約束（逐條可由 qa-reviewer 檢查）

- **N208-C1**：兩段腳本裡的所有 SQL 都是 SELECT，只有 `ensure_batches` 例外。
- **N208-C2**：寫入腳本在 `--apply` 以外的任何路徑都不建立 `PlaybookStore`。
- **N208-C3**：建立 `PlaybookStore` 之後，必須重新讀取並與唯讀快照比對一致，才可以呼叫 `ensure_batches`。
- **N208-C4**：清單裡的代號只要在 `playbook_batches`、`playbook_directives`、`playbook_schedule`、`playbook_blacklist`、`playbook_symbols`、`playbook_evaluation_marks` 任何一張表有列，就整批拒絕。
- **N208-C5**：`batches_per_target` 只取自 `active_params`，日期基準為 UTC。
- **N208-C6**：既有批次的 batch_no 必須是 1 到 `bpt` 連號、status 只能是四種已知值，否則拒絕。
- **N208-C7**：「新增後還有 planned 或 open 批次的檔數」不等於 `n_targets` 就拒絕。
- **N208-C8**：所有輸出都不含代號與路徑；每一條結束路徑都印出哨兵行。
- **N208-C9**：寫入後做全表的 (symbol, batch_no, status) 比對，必須等於「原有列加上新列」。
- **N208-C10**：操作程序在 ⑦ 之前與還原之後，都要做 `Test-N208Same` 比對與停機檢查。

### 風控判定（任務第 3 題）

- 沒有選股或投資建議；代號都是 `NNNN` 這類示意；⑨ 的「本說明不保證會出單」與 §2.7 的「多投入 20%」都是事實陳述。
- 唯一需要處理的是 §2.4：文件自稱「引用的是風控既有通知原文」，實際上是改寫，還漏了有效期限。風控上一輪才剛判定一次改寫「會誤導」。依 W-7 改成逐字引用，就不必送風控；如果保留改寫，那一句要送 risk-compliance-officer。

- **其他部門**（dev-lead、qa-reviewer、qa-automation、risk-compliance-officer、product-manager、devops-sre 等）：本次未參與，這是 TA 的唯讀核對。

## 驗證

- 我的判定全部來自讀 code，附有檔案與行號。我沒有執行任何指令，所以 SHA 值和 sandbox 輸出都沒有重算；修訂後由 dev-lead 重跑 W-8 的情境，qa-automation 獨立再跑一次。
- 第 1 部分的驗收方式：CEO 輸出的最後兩行是 `N208_COUNT_RESULT=0` 和 `exit=0`；停機檢查不印任何東西；`Test-N208Same` 每一行都是 `SAME` 或 `absent_both`。
- 第 2 部分的驗收方式：qa-reviewer 審查通過（沒有 BLOCKING_ISSUES，並附 Codex 第二意見），審的是 N208-C1 到 C10，並綁定新的 SHA。

## 下一步

1. dev-lead 依 P1-1 到 P1-4 修改第 1 部分（P1-5 建議一起做），在 sandbox 重跑 C1 到 C4（含 C6），更新 SHA 後，由 coordinator 交給 CEO 執行。
2. dev-lead 依 W-1 到 W-8 修改第 2 部分，送 qa-reviewer（含 Codex）審查，sandbox 由 qa-automation 獨立重跑。在 CEO 回傳第 1 部分結果、而且顯示 (a2) < `n_targets` 之前，第 2 部分不交給 CEO。
3. 交 CEO 決定（不急）：補位要求「剛好補滿」還是「不超過即可」。另外請 coordinator 把「手動新增的標的沒有 N-207 名單稽核紀錄，N-207 要能接受這種狀態」登記為 N-207／ADR-0043 的待辦。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-08-N208手動換標的操作說明-dev-lead.md`
- `/home/user/AICompany/work/reviews/2026-11-08-N203排程台標的寫入路徑查證-dev-lead.md`
- `/home/user/AICompany/work/reviews/2026-11-08-N207架構評估-tech-architect.md`
- `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`
- `/home/user/AICompany/work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py`
- `/home/user/AICompany/apps/stock-desk/dev-up.bat`
