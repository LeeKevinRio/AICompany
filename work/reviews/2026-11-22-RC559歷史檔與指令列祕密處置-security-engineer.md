# RC-559 第 2～4 點：CEO 文件的祕密處置常設要求、phase8 常駐環境變數評估、spike 腳本輸出只讀確認

- 作者：security-engineer
- 日期：2026-11-22
- 對象：coordinator、風控（risk-compliance-officer）、tech-architect（第 2 點條文草稿的後續承接）。
- **本報告任何文字都不是 CEO 可見文字，也不是擬給 CEO 的字面。** 沒有聯絡 CEO。
- 工作方式：只用 Read／Grep／Glob 與非變更性的 `git log`、`sha256sum`、`grep`、`sed -n`。沒有讀任何 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，沒有執行 `.bat`，沒有改任何既有檔案。本檔是唯一新增檔，未 commit；刪除本檔即還原。
- 範圍：RC-559 的第 2、3、4 點；第 1 點（處置建議）依指示這次不做，只在文末列出屆時需要的事實。
- 行號以目前 checkout（`product/stock-desk`，HEAD `f2937c0`）為準。

---

## 一、本次結論

1. **第 2 點**：條文草稿在第二節。建議放在新增的 skill `.claude/skills/ceo-facing-secret-handling/SKILL.md`，章程 §4 只加一句指向它的條文，兩處都走 `chore/agent-*`。理由與替代方案見第二節 2.1。
2. **第 3 點**：phase8 第 155 行沒有指定設定方式。若設成常駐的使用者環境變數，〔一般知識，未在 CEO 機器上查證〕值會以明文存在 Windows 登錄檔 HKCU 底下，且之後該使用者啟動的每個程序都會繼承。〔repo 事實〕`local-run` skill 寫明系統環境變數優先於 `.env`，所以它還會悄悄蓋過 `.env` 的同名設定。細節與事實／推論分界見 2.3。
3. **第 4 點**：以程式碼確認，`fundamentals_spike.py` 的輸出路徑上，金鑰、token、`SEC_USER_AGENT` 整串、任何 email 都會被遮成 `***`，程式不寫任何檔案、沒有 log 檔。確認的是程式碼的寫法；**我沒有執行過它，也沒有跑測試**，所以「實際輸出是否零洩漏」未查證。有 4 個邊界情形，見 2.4。
4. 另一項值得 RC 知道的事實：我讀的腳本檔 sha256 與 spike 文件第 130 行的預期值相同，最後修改它的 commit 與第 124 行的預期值相同（2.4 〔事實〕6）。也就是這份檢查對象就是文件要 CEO 執行的那一版。

---

## 二、各部門回報（security-engineer）

### 2.1 第 2 點：日後寫給 CEO 的文件的常設要求（條文草稿）

#### 放哪裡、為什麼（建議，由 tech-architect 裁示）

| 項目 | 建議 | 理由 |
|---|---|---|
| 全文 | 新增 `.claude/skills/ceo-facing-secret-handling/SKILL.md` | 章程 CLAUDE.md 開頭寫「只放每次都要遵守的最高原則」，長流程放 `.claude/skills/`。這條是流程性要求（誰要確認、確認什麼），而且寫給 CEO 文件的人不限一個角色（creative-lead、tech-writer、devops-sre、data-engineer 都寫過），skill 才讓各角色引用同一份。 |
| 章程指向 | CLAUDE.md §4 加一條「寫給 CEO 的文件適用 `ceo-facing-secret-handling`」，並在 §5 的 skill 清單加上名稱 | 章程 §4 是祕密處置的現有落點，加一句才不會有人沒看到 skill。這是章程修改，依章程需 CEO 核可（RC-559 第 2 點也寫「需要 CEO 核可的部分照章程辦」）。 |
| 角色檔 | `.claude/agents/security-engineer.md` 的職責加「出具 CEO 文件的存放位置書面確認」一行；`docs/org-chart.md` 要同步 | `scripts/validate_agents.py` 強制 org-chart 與 agents 同步。我 grep 該腳本沒有任何 skill 清單檢查，所以新增 skill 不會讓 CI 變紅；章程 §5 的清單靠人工維護（〔推論〕容易漏，tech-architect 提 PR 時請一併核對）。 |
| 替代方案（我不建議） | 只放 `docs/handoff-protocol.md` | 該檔是任務單與交接格式，沒有「給 CEO」的章節（我 grep「給 CEO」「coordinator」零命中）；放進去會變成交接流程的一個旁支，找不到。 |

不溯及既往的建議（RC 的判斷，我只提供意見）：條文適用於**新寫與日後修改的**文件；既有文件已走 RC-523～RC-554 的標註與更正路徑，不因本條重開。

#### 條文草稿（可直接放進 skill；中文為內容，程式碼與指令為英文）

```markdown
---
name: ceo-facing-secret-handling
description: 任何要寫給 CEO、且會讓 CEO 輸入、貼上、設定或回傳祕密或個人資料的文件，或任何描述「某個值存在哪裡、不存在哪裡」的文字，寫之前與送風控審之前必用。
---

# ceo-facing-secret-handling

## 適用範圍
- 讀者是 CEO，或內容會被轉述給 CEO 的文件、指令、畫面文案、回覆句。
- 「祕密」：API key、token、密碼、webhook 網址。
- 「個人資料」：email、姓名、持股或持倉代號、帳號、任何可指向 CEO 本人或其投資部位的值。

## 一、值不得出現在指令列
1. 不得要求 CEO 把祕密或個人資料的**值**打在任何指令列上。包括但不限於
   `$env:NAME = "<value>"`、`export NAME=<value>`、`setx NAME <value>`、
   `--token <value>`、`--api-key <value>`、`curl -H "Authorization: ..."`、
   以及任何把值寫在 URL 查詢字串裡的指令。
   理由：互動式 shell 可能把整行指令存進歷史紀錄檔，且依各 shell 的版本與設定而定，不可假設會被排除。
2. 需要 CEO 提供值時，只能用下列方式之一，並在文件裡明寫選了哪一種：
   a. 寫進 `.env`（已被 `.gitignore`），由程式從環境變數讀取；文件只講檔案位置與變數**名稱**。
   b. 靜默輸入：指令列只含變數名稱，值由提示後鍵入且不回顯
      （例：bash 的 `read -rs NAME`；PowerShell 的對應寫法必須先經 security-engineer 確認該寫法不會把值留進歷史紀錄）。
   c. 圖形介面設定，且文件要同時寫明該值會以什麼形式、存在哪裡（見第二節）。
3. 能不要 CEO 提供就不要：優先改設計，讓腳本、程式從既有的 `.env` 讀取；
   個人資料（email、持股代號）能用佔位值或預設值完成的，就不要求真值。
4. 範本裡的假值必須明顯是假的（`<your-token-here>` 一類），不得是看起來像真值的字串。
5. 不得要求 CEO 把含值的畫面、指令列、環境變數清單貼回。回傳內容必須是已確認不含祕密與個人資料的輸出。

## 二、「存在哪裡、不存在哪裡」類說法需要書面確認
1. 下列說法一律要 security-engineer 的書面確認，才可送 risk-compliance-officer 審；沒有確認不得送審：
   - 任何斷言某個值**不會**被寫進檔案、log、歷史紀錄、剪貼簿、備份、雲端同步、git；
   - 任何斷言某個值**只存在**於記憶體、某個視窗、某個程序、某個檔案；
   - 任何斷言輸出「已遮蔽」「不含金鑰」「不含 email」；
   - 任何斷言「關視窗就消失」「不會被 commit」「不會被上傳」。
2. 確認必須是獨立書面，包含：
   - 被確認的**原句**（逐字）與所在文件、行號、文件版本（commit SHA）；
   - 判定：成立 / 部分成立 / 不成立 / 未能確認；
   - 依據，並分開標示「事實（讀到的原始碼或實測）」「推論」「未查證」，附檔案與行號或指令；
   - 適用條件：作業系統、shell 與其版本、相關工具版本、預設或被改過的設定；
   - 確認所依的程式或文件版本；該版本一變，確認即失效，要重新出具。
3. 確認只涵蓋被問到的那一句。文件裡其他句子、其他版本，不得引用它當擔保。
4. security-engineer 無法確認時，該句不得寫成肯定句；改為只陳述已查證的部分，或整句拿掉。
5. 確認書不是 CEO 可見文字；CEO 可見的字面仍由風控定稿。

## 三、事後發現文件有誤時
- 已送出或已入庫的文件，若發現第一節或第二節的內容與事實不符，當天通知 security-engineer 與風控，
  不得自行改寫 CEO 已看過的字面；更正字面由風控定稿。
- 不得叫 CEO 自行去找、打開、修改或刪除任何歷史紀錄或設定檔來補救。
```

草稿的設計說明（給 TA，不放進 skill）：
- 第一節 2(b) 刻意把 PowerShell 的靜默輸入寫法列為「需先確認」，因為我沒有查證 `Read-Host` 的輸入是否經過 PSReadLine 歷史（〔推論〕它不是指令列所以不會，但未查證）。TA 若要把具體寫法直接寫進條文，請先讓我在可執行的環境確認。
- 第二節 2 的「適用條件」欄是從這次事件學到的：同一行指令，在 PSReadLine 2.0.0 與 2.1.0 以後結果相反（devops-sre 報告第 16 行、第 89～94 行），所以任何「不會被存」的說法都要綁版本。
- 第二節 4 與 RC-557 的禁說一致：「token 不會被存」這類部分擔保，沒有版本與實跑，不得出現。

### 2.2 第 2 點的後續（給 TA 的小清單）

- 章程 §4 的修改要 CEO 核可；skill 新增與 security-engineer 角色檔修改走 `chore/agent-*` 分支。
- 改完後跑 `python scripts/validate_agents.py`（章程 §5 規定）。我沒有改任何檔，所以沒有跑。
- 〔未查證〕現有 skill 清單（章程 §5）與 `.claude/skills/` 實際目錄是否一致：目錄裡有 `local-run`，章程 §5 清單沒有列它。這是我順帶看到的，不影響本件。

### 2.3 第 3 點：phase8 第 155 行「自行在本機環境變數設定 `ALPHA_VANTAGE_API_KEY`」

**原文**（`work/stock-desk-phase8-spike-盤點.md` 第 155 行）：CEO 需自行在本機環境變數設定 `ALPHA_VANTAGE_API_KEY`（免費申請）；未設定則腳本會直接跳過。文件沒有說用哪一種方式設定。這份文件已有 RC-551 的標註（P8-1）要 CEO 不要設定，但標註只影響 CEO 做不做，不影響「若做了，值在哪裡」。

**〔repo 事實〕**
1. 該腳本 `scripts/spike_phase8_sources.py` 用 `os.environ.get("ALPHA_VANTAGE_API_KEY")` 讀值（第 426、526 行），把值放進請求參數 `apikey`（第 446、458、541 行）。
2. 該腳本我 grep `mask|redact|遮` 零命中；它沒有遮蔽機制，也就是它的輸出若回顯金鑰，不會被遮。〔未查證〕它的輸出實際上會不會回顯金鑰：錯誤字串用 `exc!r`（第 144～175 行），我沒有查 httpx 的例外字串在各情形下是否帶出 URL 與查詢字串，Alpha Vantage 的回應本文會不會原樣回顯 key 也未查證。
3. `local-run` skill 第 46～47 行：「已在系統環境變數設過的同名變數優先於 `.env`」；後端與 scheduler 啟動時只印「已設定／未設定」，不印值（同檔第 46～48 行）。
4. `.gitignore` 第 2～4 行：`.env`、`.env.*` 被忽略，`.env.example` 例外；`*.key`、`.codex/` 也被忽略（我只讀 `.gitignore`，沒有開任何 `.env*`）。

**〔一般知識，不是這個 repo 的事實，也沒有在 CEO 的機器上查證〕**
1. Windows 的「使用者環境變數」持久保存在目前使用者的登錄檔 `HKEY_CURRENT_USER\Environment`，型別是字串，**沒有加密**。
2. 該使用者之後新啟動的程序，預設都會繼承這些變數。已經在跑的程序不會即時看到。
3. 以該使用者身分執行的任何程式，都可以讀到它。「系統環境變數」（`HKLM`）是另一個位置，需要系統管理員權限才能寫；這裡只討論使用者環境變數。
4. 登錄檔的 HKCU 內容存在使用者設定檔的 `NTUSER.DAT`。〔未查證〕它會不會被備份軟體、系統映像、網域漫遊設定檔帶走，取決於 CEO 機器的備份與網域設定，我完全沒有這些資訊。

**〔推論，依上面事實與一般知識〕**
- 若 CEO 用「系統內容 → 環境變數」的圖形視窗設定：值不會進任何 shell 的歷史紀錄；但它會**一直留著**，直到有人手動刪除。沒有到期、沒有提醒。
- 若 CEO 用 `setx NAME value` 或 PowerShell 的 `[Environment]::SetEnvironmentVariable(..., "User")` 設定：那是一行含值的指令列，會碰到 PSReadLine 歷史檔的問題。PSReadLine 對 `ALPHA_VANTAGE_API_KEY` 在 2.1.0 以後不會排除（devops-sre 報告第 16 行、第 62 行）；`setx` 的情形我沒有逐字查證判定結果，但關鍵字比對是對整行文字，名稱同樣不含 `apikey`，〔推論〕結果同。
- 若 CEO 用 `$env:ALPHA_VANTAGE_API_KEY = "..."`：只對該視窗生效（不常駐），但同樣是含值的指令列。
- 常駐之後的額外影響：
  - 之後 `dev-up.bat` 開的 backend、scheduler 視窗會繼承它，並且依 `local-run` 第 46 行的優先順序，**蓋過 `.env` 裡的同名值**。〔推論〕若 CEO 之後在 `.env` 換了新 key，但常駐的舊值還在，產品會繼續用舊值，且啟動訊息只會顯示「已設定」，看不出是哪一個來源。
  - 其他以該使用者執行的程式（含非本公司的）可以讀到它；螢幕上若出現環境變數清單，會含明文。
  - 用同一把 key 的另一個工具或視窗，額度（Alpha Vantage 免費額度，phase8 第 73 行寫與日線共用 25 req/day）會被一起消耗。這是額度問題，不是保密問題，順帶記錄。
- 「金鑰在哪裡、以什麼形式」的答案，依設定方式分三種：
  1. 圖形視窗設定：登錄檔，明文；
  2. 指令設定：登錄檔，明文，**加上**含值指令列在歷史檔（版本與設定相依）；
  3. 只在視窗內 `$env:` 設定：程序記憶體，明文，加上歷史檔那一項。
- 要清除「常駐」只能由設定它的方式的反向操作做（刪除該使用者環境變數）；清掉之後，已經啟動的程序仍帶著舊值直到重啟。〔一般知識〕

**〔未查證〕**
- CEO 有沒有設過；用哪一種方式；機器是否個人專用；有沒有備份、同步或漫遊設定檔涵蓋 HKCU；是否有其他人以同一個 Windows 使用者登入。
- 這把 Alpha Vantage key 是否與 `.env` 裡的同一把。
- Alpha Vantage 帳號端是否可以重新產生 key、舊 key 何時失效（我沒有外部查證，也不應該對外部服務查）。

**我的評估（只評估，不聯絡 CEO）**：phase8 第 155 行讓「設定方式」完全開放，這正是 2.1 的條文要擋的情形。對這份文件本身，RC-551 的 P8-1 已經叫 CEO 不要設；若日後真的需要這個 key 來源測試，走 2.1 第一節 2(a)，由 `.env` 載入，不要走常駐環境變數。

### 2.4 第 4 點：`fundamentals_spike.py` 輸出檔與 log 是否寫進 email 或金鑰

**腳本路徑**：`/home/user/AICompany/apps/stock-desk/backend/scripts/fundamentals_spike.py`（2242 行），由 `work/research/財務資料源spike-執行指令-2026-11-01.md` 第 8 行指出。

**〔事實：我讀到的〕**
1. **版本相符。** `git log -1 --format=%H -- fundamentals_spike.py` 回 `b4d18bc662d7c7687e59d4800e012d11d068265a`，與 spike 文件第 124 行預期值相同。`sha256sum` 該檔得 `01556a87…ad3fd`（前 8 字元與後 5 字元；完整值與文件第 130 行相同）。檔案在工作樹無未提交改動（`git status --short` 無輸出）。〔注意〕文件的 `script_sha256_lf` 是把 CRLF 換成 LF 後的雜湊；這個 Linux checkout 本來就是 LF，所以兩者相同。
2. **輸出管道只有一個，且全部先過遮蔽。**
   - `main()` 第 2196 行用三個環境變數（`SECRET_ENV_VARS`，第 94 行：`SEC_USER_AGENT`、`FINMIND_API_TOKEN`、`ALPHA_VANTAGE_API_KEY`）的值建立 `Redactor`。
   - 第 2197 行 `sink` 是 `print(text, flush=True)`；第 2199～2200 行 `say()` 先 `redact(text)` 再給 `sink`。我 grep 全檔的 `print(` 只在第 2197 行出現一次；`sys.std…` 只在第 2238 行（做 `reconfigure`）；沒有 `logging`、`traceback` 模組。
   - 其他所有輸出（`ctx.say`、`ctx.record`、`print_summary`）都走 `say`：`Context.record` 在第 480 行附近呼叫 `self.say`，`print_summary` 第 2176～2178 行用 `ctx.say`。
3. **遮蔽規則**（`Redactor`，第 257～286 行）：
   - 第 268～279 行：三個祕密值本身、`urllib.parse.quote` 與 `quote_plus` 的編碼版，長的先換；第 281～283 行逐一 `replace(secret, "***")`（`MASK`，第 88 行）。
   - 第 262～266 行：三個 regex，遮掉 `bearer`／`basic` 之後的值、`token=`／`apikey=`／`api_key=`／`key=` 之後的值、`"token"|"apikey"|"api_key"|"authorization"` 後接 `:` 或 `=` 的值。
   - 第 267、286 行：任何符合 email 樣式的字串一律換成 `***`（不限使用者設的那一個）。
   - 這與 spike 文件第 16 行、第 81 行「金鑰、token、User-Agent、email 在輸出中一律遮成 `***`」的說法一致：**程式碼確認該說法成立，範圍限於 `Redactor` 看得到的那三個值與上述 regex／email 樣式**。
4. **金鑰進入請求的地方，各自的顯示處理：**
   - Alpha Vantage：第 1556 行 `shown` 把 `apikey=` 直接寫成 `***`，第 1557 行才是真正帶值的 `url`；第 1558 行 `fetch_json(..., shown_url=shown)` 只印 `shown`（`fetch_json` 第 512～516 行：`ctx.say(f"GET {shown_url or url}")`）。
   - FinMind：token 放在 `Authorization: Bearer` 標頭（第 1492 行），不進 URL；標頭不印出。
   - SEC：`SEC_USER_AGENT` 放在請求標頭（第 1181 行），不印出；第 1175 行的訊息只說「未設定或缺 email」，沒有回顯值。
   - 狀態列：第 2216～2218 行只印 `set (value hidden)` 或 `NOT set`；第 2219～2223 行對 `SPIKE_US_HOLDINGS` 只印 `set` 或 `NOT set`。
   - 回應端：`keep_headers`（第 347～354 行）只保留 validator、大小、限流類標頭，註解與實作都排除 cookie 與 auth；跨主機轉址時第 458 行移除 `Authorization`。
5. **不寫檔、沒有 log 檔。**
   - 檔頭說明第 10 行：「Touches no database and writes no file; every line goes to stdout」。
   - 我 grep `open(`、`write`、`Path(`：唯一的檔案存取是 `script_digest()` 第 2145～2148 行 `Path(__file__).read_bytes()`（讀自己算雜湊）。
   - 測試檔有對應的原始碼斷言：`test_source_writes_no_files`（第 1794 行）、`test_source_only_reads_its_own_file_and_nothing_else_from_disk`（第 1835 行）、`test_source_holds_no_credentials_or_contact_details`（第 1861 行）、`test_redactor_*`（第 473、481、494、499 行）、`test_alpha_vantage_vendor_messages_are_reported_and_key_echo_is_masked`（第 1017 行）。**我只 grep 了測試名稱與行號，沒有讀測試內容，也沒有執行測試**，所以「測試逐項驗證過」我沒有親自確認。
6. 腳本只 `urllib`、只讀環境變數（第 2195 行 `os.environ`），不讀 `.env`；符合 spike 文件第 9、48 行的說法（我只確認 `.env` 沒有出現在程式碼的讀取路徑，`grep` 無命中）。

**〔事實：邊界情形，程式碼寫法造成的，不等於已發生〕**
1. **持股代號不遮。** `SPIKE_US_HOLDINGS` 不在 `SECRET_ENV_VARS`，第 1214～1226 行與第 2076～2093 行會把代號印出來。spike 文件第 46、80 行已經明說，這是設計。它屬個人資料，不是祕密值，RC-557 的更正字面也把持股代號列入個人資料。
2. **長度小於 4 的值不遮。** 第 273～274 行：`len(secret) < 4` 直接略過。極短的假 token 或測試值不會被整串替換（但 regex 與 email 規則仍然會處理 `token=` 這類格式）。實際金鑰通常遠長於此，〔推論〕不構成實際缺口。
3. **整串 User-Agent 才被精確替換。** `SEC_USER_AGENT` 是「姓名 email」；email 部分由 email regex 遮，**姓名部分單獨出現時不會被遮**。我 grep 沒有看到任何地方把 User-Agent 單獨或其片段印出，所以〔推論〕目前不會發生，但這是靠「程式不印」而不是靠遮蔽守住的。
4. **未預期例外不經遮蔽。** 每個段落的例外被第 2226～2231 行接住並走 `ctx.record`（會遮）。但 `main()` 在建立 `ctx` 之後、進入段落迴圈之前（第 2210～2223 行）與迴圈之後（第 2233 行）的例外，會成為 Python 的 traceback，直接寫到 stderr，不經 `Redactor`。〔推論〕traceback 預設只含程式行與例外訊息，不含變數值，所以洩漏的可能性低；但我沒有實測。
5. **腳本之外的位置不在這份確認範圍。** CEO 在 PowerShell 視窗打的指令列、視窗捲動緩衝區、被選取複製的內容，都不是腳本輸出，不受 `Redactor` 管。這正是 spike 文件第 81 行自己寫的「您在視窗裡打的指令列會留在畫面與 PowerShell 歷史裡」，與 RC-557／RC-558 處理的是同一件事。

**〔未查證〕**
- 腳本實際跑一次的輸出是否零洩漏：我沒有執行（沙盒對外 403、也沒有金鑰，也不應執行）。
- 測試的實際通過狀況與其斷言內容。
- Windows 上 `print` 在 cp950 主控台的編碼行為（腳本第 2238～2242 行用 `errors="replace"`）對遮蔽結果有無影響：〔推論〕遮蔽發生在字串層、早於編碼，不受影響，未實測。
- 供應端（SEC、FinMind、Alpha Vantage）會不會在回應本文回顯使用者提供的值：Alpha Vantage 的 `Note`／`Information` 訊息，spike 文件第 226 行與測試第 1017 行的說法是「金鑰回顯會被遮成 `***`」，程式規則（第 262～266 行與整串替換）涵蓋這種情形，但真實回應長什麼樣我沒有證據。

**結論**：spike 文件第 81 行「腳本的輸出本身不會顯示前三個值（會遮成 `***`）」這個說法，在**程式碼層**成立，且程式不寫任何輸出檔與 log。這句話的後半「持股代號例外」也成立。我不把它寫成「輸出沒有洩漏」，因為沒有實跑。

---

## 三、驗證

**讀過：**
- RC-557～RC-559 所在的風控判定全文（`work/reviews/2026-11-22-補普查標註定稿R0-2另案揭露句方向與PSReadLine更正RC548至RC560-風控.md`）。
- devops-sre 的 PSReadLine 查證全文（`work/reviews/2026-11-22-PSReadLine歷史檔查證RC530-devops-sre.md`）。
- `work/research/財務資料源spike-執行指令-2026-11-01.md` 全文。
- `work/stock-desk-phase8-spike-盤點.md` 第 69～96、152～157 行。
- `apps/stock-desk/backend/scripts/fundamentals_spike.py` 第 80～140、250～500、1530～1575、2170～2242 行，其他處用 `grep -n` 查關鍵字（`print(`、`open(`、`write`、`environ`、`ENV_*`、`User-Agent`、`Authorization`、`logging`、`traceback`）。
- `scripts/spike_phase8_sources.py` 第 40～100 行與 `grep` 命中處。
- `.claude/skills/local-run/SKILL.md`、`.claude/skills/README.md`；`.claude/agents/security-engineer.md` 開頭；`docs/handoff-protocol.md` 的標題與 `grep`；`.gitignore` 的 `.env`、`*.key`、`.codex/` 行（用 `grep -n`，不是讀 `.env*`）。

**執行的指令（可重現）：**
- `git log -1 --format=%H -- apps/stock-desk/backend/scripts/fundamentals_spike.py`
- `sha256sum apps/stock-desk/backend/scripts/fundamentals_spike.py`
- `git status --short apps/stock-desk/backend/scripts/fundamentals_spike.py`
- `grep -n -E "mask|redact|\*\*\*|environ|getenv|open\(|write|print\(|logging|logger|SEC_USER_AGENT|API_KEY|API_TOKEN|HOLDINGS"` 作用在上述腳本；同一類 `grep` 作用在 phase8 腳本與測試檔名稱。
- 沒有安裝或執行任何工具，沒有版本需要記錄；`git` 為系統內建。

**沒有做、也不得宣稱的：**
- 沒有執行 `fundamentals_spike.py` 或任何測試；沒有連網；沒有在 Windows、PowerShell、Git Bash 上實測任何東西。
- 沒有讀測試內容；沒有讀 `.env*`；沒有碰 `apps/stock-desk/backend/data/`；沒有執行 `.bat`；沒有看 `.claude/worktrees/`。
- 掃描疑似祕密值：這次沒有做新的全 repo 掃描。報告中引用的文件與程式，我沒有看到任何疑似實值的長字串（只看到佔位字樣如 `<您的 FinMind token>`）；短字串假值我沒有逐一人工確認。

**未查證清單（彙整）：**
1. Windows 使用者環境變數的儲存位置、加密與備份行為（一般知識，未對照 Microsoft 文件，因環境無法解析該網域；devops-sre 也有同樣限制）。
2. CEO 是否設過 `ALPHA_VANTAGE_API_KEY`、用什麼方式、機器與備份情形。
3. phase8 腳本錯誤字串是否回顯金鑰；供應端是否回顯使用者值。
4. `fundamentals_spike.py` 的實際輸出、測試通過狀況。
5. `Read-Host` 與 `setx` 在 PSReadLine 下的判定。
6. 章程 §5 的 skill 清單與 `.claude/skills/` 目錄不一致處（`local-run`）。

---

## 四、下一步

**風控／coordinator：**
- 第 2 點條文草稿交 tech-architect 走 `chore/agent-*`；章程 §4 與 §5 的修改需 CEO 核可，我不聯絡 CEO。
- 第 3 點：RC-551 的 P8-1 標註已涵蓋「不要設定」。若風控認為要補一句「若曾設過常駐環境變數」的處置，那屬 RC-557 收到「有」或「不確定」之後的第 1 點範圍，字面由風控定稿；我不擬。
- 第 4 點：spike 文件第 81 行說法在程式碼層成立。若要把這個結論寫成文件裡的敘述，屬 RC-558 之外的新修改，需另走 RC-525。建議的書面確認範圍就是 2.4 的邊界情形 1～5，不要寫成「沒有洩漏」。

**dev-lead／devops-sre（建議，非必要）：**
- 〔suggested〕在有 Windows 的環境實測：(a) `Read-Host` 輸入不進 PSReadLine 歷史；(b) `setx` 與 `[Environment]::SetEnvironmentVariable` 的判定；(c) 跑 `fundamentals_spike.py` 的測試。需要 RC 或 coordinator 指示，我沒有自行做。

**屆時（第 1 點啟動：RC-557 收到「有」或「不確定」）我會需要的事實：**
1. CEO 的回答原文，以及是哪一類（PowerShell、Git Bash，或兩者都有；不得叫 CEO 去查檔案）。
2. 團隊記錄上「CEO 可能照做過」的文件清單與時間：`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`、`work/research/財務資料源spike-執行指令-2026-11-01.md`（第 68、71、72、76 行）、`work/stock-desk-數據核實操作說明.md`（第 17～19 行）、N152、N118 等（devops-sre 報告第 102～122 行），以及 2026-08-16 的行情探測文件的指令列。要確認哪些文件 CEO 真的收到過、哪天，以及那一版的指令列內容。
3. 每個值各是什麼類型：FinMind token、Alpha Vantage key、`SEC_USER_AGENT`（含 email）、`SPIKE_US_HOLDINGS`（持股代號）；哪些真的被 CEO 打在指令列上（要回答才知道，不得由我們推）。
4. Windows PowerShell 與 PSReadLine 的版本，是否自訂過 `Set-PSReadLineOption`（含 `HistorySaveStyle`、`AddToHistoryHandler`）；Git Bash 的 `HISTFILE`、`HISTCONTROL` 預設——這些要由有權限看 CEO 機器的人取得，我們沒有，需要風控決定怎麼合規地取得（RC-530 不得叫 CEO 查歷史檔）。
5. `%APPDATA%` 與 `~/.bash_history` 是否被備份、同步或漫遊設定檔涵蓋（devops-sre 報告未查證清單第 7 點）；機器是個人專用還是多人共用。
6. FinMind 與 Alpha Vantage 帳號端的 key 重新產生流程、舊 key 何時失效、是否與 `.env` 為同一把、換 key 後 `.env` 與 `dev-up.bat` 要怎麼對應（我不對外部服務查，要由 CEO 或風控授權的人確認）。
7. 清除歷史檔的副作用：同一個檔案裡其他指令一併消失；PSReadLine 與 bash 清除方式各別；這些我可以依原始碼寫，但要在 CEO 的版本確認之後才定稿。
8. email 與持股代號作為個人資料：是否已進過 `work/` 或對話紀錄（先 `git grep` 疑似樣式，但不貼值）；若有，屬 git 歷史外洩評估，依角色規範立即 critical 並升級 CEO，這要由風控與 coordinator 轉。
9. 這次事件裡「值是否曾進 git」的初步掃描：devops-sre 報告第 6 行已做 11 份文件的掃描，未發現疑似實值；若第 1 點啟動，我會另做 git 歷史範圍的樣式掃描，工具與版本屆時記錄。

**回滾**：本次只新增本檔；刪除 `/home/user/AICompany/work/reviews/2026-11-22-RC559歷史檔與指令列祕密處置-security-engineer.md` 即還原。

**Verdict**
NEEDS_CHANGES（針對文件層：2.1 條文尚未入規；2.3、2.4 為評估與確認，不阻擋本次工作）
BLOCKING_ISSUES=false

相關路徑：
- /home/user/AICompany/work/reviews/2026-11-22-RC559歷史檔與指令列祕密處置-security-engineer.md
- /home/user/AICompany/apps/stock-desk/backend/scripts/fundamentals_spike.py
- /home/user/AICompany/scripts/spike_phase8_sources.py
- /home/user/AICompany/work/research/財務資料源spike-執行指令-2026-11-01.md
- /home/user/AICompany/work/stock-desk-phase8-spike-盤點.md
- /home/user/AICompany/.claude/skills/local-run/SKILL.md
