# PSReadLine 歷史檔查證（RC-530）— devops-sre

- 日期：2026-11-22
- 對象：coordinator、風控（risk-compliance-officer）。**不對 CEO 提；本報告任何字面都不是 CEO 可見文字。**
- 查證範圍：PSReadLine 原始碼（master `a2d143f`，另取 tag v1.2、v2.0.0、v2.0.0-rc1、v2.1.0、v2.2.0-beta1/beta5、v2.2.2、v2.2.5、v2.2.6、v2.3.0-beta0、v2.3.3、v2.3.6、v2.4.5）、repo 文件。只讀，沒有 build、沒有執行。
- 疑似實值檢查：11 份文件掃過 `eyJ…`、32 字元以上英數串、email 樣式。**沒有發現疑似實值**：命中者是 git SHA／雜湊（N152 第 102、163 行；N172 第 150、156、247 行；spike 第 124、130、308 行）、資料集名稱（Phase1 第 586、649 行）、佔位 email（spike 第 67、68 行，`your@…`）。短字串假值我刻意遮掉，沒有逐一人工確認。
- 工作樹：branch `product/stock-desk`，HEAD `7e54571`。

## 一、本次結論

1. **預設會寫檔，且是每按一次 Enter 就寫**（原始碼實查）。`HistorySaveStyle` 預設 `SaveIncrementally`，Windows 預設路徑為 `%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\<hostName>_history.txt`；新版 AddToHistoryHandler 只用關鍵字加 AST 判斷是否排除，排除的才不寫檔。
2. **三行判定（以 master 邏輯）**：
   - `$env:STOCK_DESK_DB_PATH = "C:\x\stock-desk.db"` → `MemoryAndFile`（寫檔）。
   - `$env:SEC_USER_AGENT = "name someone@example.com"` → `MemoryAndFile`（寫檔）。email 與 `SEC_USER_AGENT` 都不在關鍵字內。
   - `$env:FINMIND_TOKEN = "abc"` → `MemoryOnly`（不寫檔）。上一輪「右側被判 Safe 所以寫檔」的推論，與原始碼相反：`IsRightSideOfAnAssignmentSafe` 回傳 true 才代表「放過」，右側是字串常數時回傳 false，於是判為敏感。
3. **spike 文件的 `$env:ALPHA_VANTAGE_API_KEY = …` 在 PSReadLine 2.1.0 以後的預設下會寫進歷史檔**（原始碼實查＋推論）。關鍵字是 `apikey`（連續），變數名 `API_KEY` 有底線，不命中；2.0.0 的關鍵字是 `key`，會命中。也就是同一行指令，在 Windows PowerShell 5.1 內建版與新版上結果相反。
4. **哪個版本在 CEO 機器上跑，原始碼無法回答**。Windows PowerShell 5.1 內建 PSReadLine 的版本，repo README 與原始碼都沒寫（標「未查證」；我的印象是 2.0.0，但那是記憶，不是查證）。CEO 用哪種 shell、哪個版本、是否照做過，都未查證。
5. 風控 RC-530 的核心推論「`SEC_USER_AGENT`（含 email）可能留在歷史檔」：**原始碼層面成立**（第 2 點）。「金鑰可能留在歷史檔」：**部分成立**，取決於版本與變數名（第 3 點）；`FINMIND_API_TOKEN` 在所有查到的版本都會被排除。
6. 此外有一項與風控推論無關、但影響「不會寫進任何檔案」字面的內部矛盾：同一份 spike 文件第 81 行已寫「您在視窗裡打的指令列會留在畫面與 PowerShell 歷史裡」，第 82 行又寫「不會寫進任何檔案」。

## 二、各部門回報

### 要回答 1：預設 HistorySaveStyle 與 HistorySavePath

| 項目 | 結果 | 依據 | 類別 |
|---|---|---|---|
| 預設 `HistorySaveStyle` | `SaveIncrementally` | `Cmdlets.cs` 第 152 行（常數）、第 215 行（建構子指派）；列舉定義第 54～59 行 | 原始碼實查 |
| 何時寫檔 | `SaveIncrementally` 下，每筆新增歷史後立刻 `IncrementalHistoryWrite()` | `History.cs` 第 236～239 行 | 原始碼實查 |
| 寫檔時跳過敏感項 | `if (item._sensitive) { continue; }` | `History.cs` 第 374 行；`_sensitive` 由 `addToHistoryOption == MemoryOnly` 設定，第 228 行 | 原始碼實查 |
| Windows 預設 `HistorySavePath` | `%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\<hostName>_history.txt` | `Cmdlets.cs` 第 225～232 行（`SpecialFolder.ApplicationData` + `Microsoft\Windows\PowerShell\PSReadLine` + `hostName + "_history.txt"`） | 原始碼實查 |
| 非 Windows 路徑 | `$XDG_DATA_HOME/powershell/PSReadLine/…`，否則 `~/.local/share/powershell/PSReadLine/…`，無 HOME 則 `/dev/null` | 第 237～268 行 | 原始碼實查 |
| `hostName` 實際字串（慣例是 `ConsoleHost`，檔名 `ConsoleHost_history.txt`） | 由呼叫端傳入（`ReadLine.cs` 第 748 行：`hostName ?? DefaultName`），本 repo 內沒有實際傳值的證據 | | 未查證 |
| 預設 `AddToHistoryHandler` | `DefaultAddToHistoryHandler = s => GetDefaultAddToHistoryOption(s)` | `Cmdlets.cs` 第 193、204 行 | 原始碼實查 |
| 使用者有沒有改過 `Set-PSReadLineOption`／profile | 無法由原始碼得知 | | 未查證 |

### 要回答 2：預設 AddToHistoryHandler 的判斷邏輯（master `a2d143f`，`History.cs`）

流程：
1. 第 116～118 行：`s_sensitivePattern` = `password|asplaintext|token|apikey|secret`，不分大小寫。
2. 第 685～689 行：整行沒有任何命中 → 直接 `MemoryAndFile`（寫檔），不做 AST。
3. 第 691～709 行：有命中才進 AST；解析有錯誤 → `MemoryOnly`。
4. 第 711～794 行：對每個命中位置找最內層 AST（第 719～723 行），依型別分流：
   - `VariableExpressionAst`（第 724～736 行）：`isSensitive = IsOnLeftSideOfAnAssignment(...) && !IsRightSideOfAnAssignmentSafe(rhs)`。位於賦值左側，且右側不是「Safe」→ 敏感。
   - `StringConstantExpressionAst`（第 737～757 行）、`CommandParameterAst`（第 758～788 行）、其他（第 789～791 行）另有規則。
5. 第 796 行：`isSensitive ? MemoryOnly : MemoryAndFile`。
6. `IsRightSideOfAnAssignmentSafe`（第 565～580 行）：右側是 `PipelineAst`（指令呼叫、管線）→ true；右側是 `CommandExpressionAst` 且其 Expression 是 `MemberExpressionAst` 或 `InvokeMemberExpressionAst`（屬性、方法呼叫）→ true；**其餘一律 false**。純字串常數的右側是 `CommandExpressionAst` 包字串，不是成員存取，所以 false。
7. 第 724～730 行的原始碼註解自己就舉了例子：`$token = Get-Secret` 放過（寫檔），`$token = 'token-text'` 不放過。
8. 測試佐證：`test/HistoryTest.cs` 第 185 行 `"$token = 'abcd'", // Assign expr-value to sensitive variable. Not saved to file.`；第 209～222 行另有 `$a.Password = 'abcd'` 等「Not saved to file」；預期寫檔清單（第 226～250 行）不含這些項目。

逐行判定：

| # | 指令列 | 關鍵字命中 | 判定 | 依據 | 類別 |
|---|---|---|---|---|---|
| a | `$env:STOCK_DESK_DB_PATH = "C:\x\stock-desk.db"` | 無（`STOCK_DESK_DB_PATH`、路徑都不含五個字） | `MemoryAndFile` | 第 685～689 行 | 原始碼實查＋推論（未實跑） |
| b | `$env:SEC_USER_AGENT = "name someone@example.com"` | 無（`SEC_` 不等於 `secret`；email 不在關鍵字內） | `MemoryAndFile` | 第 685～689 行 | 同上 |
| c | `$env:FINMIND_TOKEN = "abc"` | 命中 `TOKEN`（變數名內） | `MemoryOnly` | 命中位置最內層 AST 為變數節點（`$env:FINMIND_TOKEN` 是 `VariableExpressionAst`）→ 第 724～736 行；位於賦值左側；右側是字串的 `CommandExpressionAst`，第 565～580 行回傳 false；`isSensitive = true && !false = true` → 第 796 行 `MemoryOnly` | 原始碼實查＋推論；**未實跑**，沒有直接測 `$env:` 前綴的測試案例 |

c 的兩個未確認點：（一）雙引號字串可能被解析為 `ExpandableStringExpressionAst`，我推論與單引號同樣落在「非 Safe」，但沒有用 parser 實跑；（二）`$env:` 變數的 AST 節點型別，我依 PowerShell 語法判斷為 `VariableExpressionAst`，測試檔第 222 行有 `$env:PGPASS = gcloud auth print-access-token` 但該行沒有關鍵字命中，不能當直接佐證。

其他在 spike 文件會出現的指令列（同一邏輯，供要回答 4 使用）：
- `$env:FINMIND_API_TOKEN = …` 含 `TOKEN` → `MemoryOnly`。
- `$env:ALPHA_VANTAGE_API_KEY = …`：`API_KEY` 不含 `apikey`；整行無其他關鍵字 → `MemoryAndFile`（寫檔）。
- `$env:SPIKE_US_HOLDINGS = …`、`$env:UV_ENV_FILE`、`$PROBE_DB = …` → 無命中 → `MemoryAndFile`。

### 要回答 3：過濾從哪個版本開始

| 版本 | `s_sensitivePattern` | 判斷方式 | 依據 |
|---|---|---|---|
| v1.2 | 無此變數 | 無 `MemoryOnly` 機制 | `git show v1.2:PSReadLine/History.cs` 搜不到 |
| v2.0.0-beta1 | 搜不到 | 同上 | 搜尋結果為空 |
| v2.0.0-rc1、v2.0.0 | `password\|asplaintext\|token\|key\|secret` | 只有關鍵字：命中即 `MemoryOnly`（v2.0.0 `History.cs` 第 436～440 行） | tag 原始碼 |
| v2.1.0 | `…\|apikey\|…`（`key` 收斂為 `apikey`） | 仍只有關鍵字（v2.1.0 第 468～472 行） | tag 原始碼 |
| v2.2.0-beta1 | 同 v2.1.0 | 尚無 AST | tag 原始碼 |
| v2.2.0-beta5～v2.2.6 | 同上 | 加入 `Parser.ParseInput` AST 判斷；v2.2.6 對字串節點是 `!IsSecretMgmtCommand`，**尚無 `IsRightSideOfAnAssignmentSafe`** | tag 原始碼 |
| v2.3.0-beta0 | 同上 | 仍無 `IsRightSideOfAnAssignmentSafe` | tag 原始碼 |
| v2.3.3 以後（v2.3.6、v2.4.5、master） | 同上 | 有 `IsRightSideOfAnAssignmentSafe`；v2.3.6 另有 `IsCloudTokenOrSecretAccess` | tag 原始碼 |

結論（原始碼實查，粒度只到 tag，沒查 commit 日期）：
- 「關鍵字過濾」從 2.0.0 系列（beta1 之後、rc1 以前）出現；
- 關鍵字從 `key` 縮為 `apikey` 發生在 v2.0.0 到 v2.1.0 之間；
- AST 判斷出現在 v2.2.0-beta1 到 beta5 之間；
- 「右側是指令或成員存取才放過」的規則出現在 v2.3.0-beta0 到 v2.3.3 之間。
- 我沒有抓到 changelog 檔，也沒有 git log（depth 1），所以引進的確切 commit 與日期未查證。

**Windows PowerShell 5.1 內建的 PSReadLine 版本**：repo README（v2.0.0 第 45、69 行、master 第 44 行）只提到 5.1 的 PowerShellGet 較舊、5.1 不必另裝某段內容，**沒有寫內建 PSReadLine 版本**。標「未查證」。若內建確為 2.0.0，則 CEO 用 5.1 時的判定要用 2.0.0 的規則（見下表）。PowerShell 7 內建版本同樣未查證。

三種版本規則下的結果對照（要回答 2 的延伸）：

| 指令列 | 2.0.0（關鍵字含 `key`，無 AST） | 2.1.0～2.2.x（`apikey`） | 2.3.3 以後／master |
|---|---|---|---|
| `$env:STOCK_DESK_DB_PATH = "…"` | 寫檔 | 寫檔 | 寫檔 |
| `$env:SEC_USER_AGENT = "…@…"` | 寫檔 | 寫檔 | 寫檔 |
| `$env:FINMIND_API_TOKEN = "…"` | 不寫（`token`） | 不寫（`token`） | 不寫 |
| `$env:ALPHA_VANTAGE_API_KEY = "…"` | 不寫（`key`） | **寫檔**（`API_KEY` 不含 `apikey`） | **寫檔** |

2.1.0～2.2.x 的 `$env:FINMIND_API_TOKEN = "…"` 結果依原始碼邏輯推為「不寫」（v2.2.6 對字串節點的規則我只讀了關鍵行，AST 分流沒有逐行比對），標「推論」。

### 要回答 4：repo 內叫讀者輸入敏感指令列的文件

行號以 HEAD `7e54571` 為準。值全部不抄。「新版預設」欄以 master 邏輯判斷；「2.0.0」欄另列只在結果不同時。

| # | 文件 | 行號 | shell | 指令中的變數名 | 新版 PSReadLine 預設是否寫歷史檔 |
|---|---|---|---|---|---|
| 1 | `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` | 第 31～33 行 | bash（文件要求先在 PowerShell 輸入 `bash`） | `read -rs FINMIND_API_TOKEN; export FINMIND_API_TOKEN`：指令列只有變數名，值是靜默輸入，不在指令列裡 | PowerShell 歷史：指令列本身不含值；進了 bash 之後的輸入不經 PSReadLine（推論）。bash 歷史：推論同下，指令列沒有值。 |
| 1 | 同上 | 第 41、935、2126、2158～2159 行 | bash | `PROBE_DIR`、`HOLIDAY`、`THIN_ID`、`THIN_DATE`（路徑、日期、代號） | 不含祕密；bash 歷史見下 |
| 1 | 同上 | 第 188 行 | bash | `FM_TOKEN_MODE`（開關，值為模式字） | bash；無祕密值 |
| 1 | 同上 | 第 1121～1122 行 | bash | `MARKET_DB_SRC`、`CACHE_DB_SRC`（DB 路徑） | bash；路徑 |
| 2 | `work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md` | 第 74 行 | PowerShell | `$env:STOCK_DESK_DB_PATH`（DB 路徑） | **寫檔**（要回答 2 a） |
| 2 | 同上 | 第 159 行 | bash | `export STOCK_DESK_DB_PATH=` | bash 歷史（推論） |
| 3 | `work/research/N172-重複指令偵測-執行指令-2026-10-31.md` | 第 111 行、第 129 行 | PowerShell | `$PROBE_DB`（路徑）；第 129 行 `--db-path $PROBE_DB`；無祕密名稱 | 沒有關鍵字 → 寫檔，內容是路徑 |
| 4 | `work/research/財務資料源spike-執行指令-2026-11-01.md` | 第 68 行 | PowerShell | `$env:SEC_USER_AGENT`（「姓名 email」） | **寫檔**（a/b 邏輯；email 進歷史檔） |
| 4 | 同上 | 第 71 行 | PowerShell | `$env:FINMIND_API_TOKEN` | 不寫（token 關鍵字） |
| 4 | 同上 | 第 72 行 | PowerShell | `$env:ALPHA_VANTAGE_API_KEY` | 2.1.0 以後**寫檔**；2.0.0 不寫 |
| 4 | 同上 | 第 76 行 | PowerShell | `$env:SPIKE_US_HOLDINGS`（持股代號） | **寫檔** |
| 4 | 同上 | 第 296～299 行 | bash | `export SEC_USER_AGENT`、`FINMIND_API_TOKEN`、`ALPHA_VANTAGE_API_KEY`、`SPIKE_US_HOLDINGS` | bash 歷史（推論） |
| 5 | `work/stock-desk-數據核實操作說明.md` | 第 17～19 行 | bash | `export FINMIND_API_TOKEN`、`ALPHA_VANTAGE_API_KEY`、`ALPHA_VANTAGE_DAILY_LIMIT` | bash 歷史（推論） |
| 6 | `work/research/N118-除權息預告表持續列出與row_count查證-查證指令-2026-10-24.md` | 第 13 行 | bash | `export STOCK_DESK_MARKET_DB_PATH=` | bash 歷史（推論）；路徑 |
| 7 | `work/research/V-1-除權息列出前置天數-查證指令-2026-10-04.md` | 第 12 行 | bash/shell 未標明 | 只有 `--db-path ./data/stock-desk-market.db` 參數；沒有環境變數指令列 | 路徑參數，無祕密 |
| 8 | `work/research/實測指令-盤中-2026-10-05.md` | 第 22～27、58～63 行 | PowerShell | 沒有祕密、沒有 DB 路徑環境變數；只有 `git`／`uv sync` 指令 | 不涉敏感名稱；commit 訊息會進歷史檔（內容是一般文字） |
| 9 | `work/research/F-3-快取非正值收盤價查證-腳本/README.md` | 第 32 行 | PowerShell／cmd | `--db data\stock-desk.db` 參數；`STOCK_DESK_DB_PATH` 只在說明文字（第 29、100～104 行），不是叫讀者輸入的指令 | 路徑參數 |
| 10 | `work/research/L-12-公司行動查證-腳本/README.md` | 第 28 行 | PowerShell／cmd | `--db <DB 檔完整路徑>`；`STOCK_DESK_DB_PATH` 只在說明文字（第 25 行） | 路徑參數 |
| 11 | `work/research/X-3-持倉幣別市場不符查證-腳本/README.md` | 第 32 行 | PowerShell／cmd | `--db data\stock-desk.db`；`STOCK_DESK_DB_PATH` 只在說明文字（第 29、69～71 行） | 路徑參數 |

補充：
- 這 11 份中，**會把 `SEC_USER_AGENT`（含 email）直接打進 PowerShell 指令列的只有 spike 第 68 行**；會把金鑰值打進指令列的是 spike 第 71、72 行（PowerShell）、第 297、298 行（bash）、數據核實第 17、18 行（bash）。Phase1 第 32 行是靜默輸入，指令列不含值。
- 各份文件開頭多數已有「給 CEO：請不要照做」類標註（例如 Phase1 第 3～5 行、spike 第 59 行、數據核實第 13 行；N152、N172 同型）。標註只影響 CEO 是否照做，不影響歷史檔行為。這些標註 CEO 看到前是否已照做過，未查證。
- spike 第 81 行與風控檔所引行號有出入：風控檔寫「第 78 行」，我在 HEAD 讀到的是第 82 行（「不會寫進任何檔案」），N152 風控檔寫第 68、151 行，我讀到第 74、159 行。可能是風控讀的版本與 HEAD 不同；內容文字相符，行號請風控以 HEAD 為準重對。
- bash（Git Bash／Linux／macOS）：我沒有讀 bash 原始碼，也沒有在 Git Bash 實測。依一般行為**推論**：互動式 bash 預設把指令列存進記憶體，離開 shell 時寫入 `~/.bash_history`（HISTFILE 預設值）；`HISTCONTROL`、`HISTIGNORE` 預設都不排除含 `TOKEN`、`KEY` 的指令列，**不像 PSReadLine 有任何關鍵字過濾**。Git Bash 的預設 profile 與 Ubuntu 等發行版的預設（例如 `HISTCONTROL=ignoreboth` 會略過「開頭空白」的指令列）可能不同，**未查證**。所以 bash 版的 `export FINMIND_API_TOKEN=…`、`export SEC_USER_AGENT=…`，依推論會在視窗正常結束時留在 `~/.bash_history`；視窗被強制關閉、用 `unset` 或 `history -c` 的情況，結果不同，未查證。

### 要回答 5：「不會寫進任何檔案」類句子，事實面哪裡不成立

只寫事實；文字上的修改與對 CEO 的任何字面，標「字面待風控定稿」。

spike 第 82 行原句：「這些值只存在這個視窗的程序記憶體，關視窗就消失，不會寫進任何檔案。」

1. **對象與事實不符之處**：該句說的是「這些值」，前面（第 68～76 行）的值是 `SEC_USER_AGENT`、`FINMIND_API_TOKEN`、`ALPHA_VANTAGE_API_KEY`、`SPIKE_US_HOLDINGS`。PSReadLine 預設（見要回答 1）把指令列文字（含這些值）寫進 `%APPDATA%\…\PSReadLine\*_history.txt`，且是每按 Enter 就寫（`History.cs` 第 236～239 行）。因此「不會寫進任何檔案」這個說法，對指令列文字本身不成立。依要回答 2、3：`SEC_USER_AGENT`、`SPIKE_US_HOLDINGS` 的指令列在所有查到的版本都寫檔；`ALPHA_VANTAGE_API_KEY` 在 2.1.0 以後寫檔；`FINMIND_API_TOKEN` 在所有查到的版本被排除。
2. **「程序記憶體」說法的範圍**：環境變數本身只在該程序（及其子程序）內存在，這部分原始碼無關、屬一般行為，我沒有另外查證。spike 腳本是否把這些值寫入輸出檔，不在本次範圍（第 80 行寫腳本輸出會遮成 `***`，我沒有讀腳本）。
3. **文件內部矛盾**：第 81 行已寫「您在視窗裡打的指令列會留在畫面與 PowerShell 歷史裡」，這句本身與第 82 行相反。「PowerShell 歷史」在 PSReadLine 下包含兩層：目前工作階段的記憶體歷史，以及上述檔案；第 81 行沒說清楚有沒有寫檔。
4. **bash 附錄（第 295～311 行）**：沒有同類「不會寫進任何檔案」句（我只在 PowerShell 段看到），但附錄有 `unset`（第 311 行附近），未處理 `~/.bash_history`。依要回答 4 的推論，bash 指令列也會留下。
5. **其他文件**：Phase1 第 31～33 行用 `read -rs`，該寫法是靜默輸入、值不在指令列內，與其他文件不同，不列入「不成立」。數據核實第 17～19 行沒有「不會寫進任何檔案」類句子（我只確認這份沒有該字串，其餘措辭沒逐句比對）。
6. 字面待風控定稿：是否在 spike 第 82 行或其他文件增修說明、是否對 CEO 提及，皆由風控與 coordinator 決定；本報告不擬 CEO 字面。

## 三、驗證

- **實查（原始碼）**：`Cmdlets.cs` 第 54～59、152、193、204、215、225～268 行；`History.cs` 第 116～118、228、236～239、374、565～580、678～796 行；`test/HistoryTest.cs` 第 105～125、170～256 行。指令：`Read`、`grep`、`sed -n`、`git -C … fetch --depth 1 origin tag …`、`git show <tag>:<path>`。
- **tag 對照**：取得 v2.0.0、v2.1.0 以外，另取 v1.2、v2.0.0-beta1、v2.0.0-rc1、v2.2.0-beta1、v2.2.0-beta5、v2.2.2、v2.2.5、v2.2.6、v2.3.0-beta0、v2.3.3、v2.3.6、v2.4.5，抽查 `s_sensitivePattern` 與 AST 函式是否存在。
- **未實跑**：沒有 build PSReadLine、沒有用 PowerShell parser 驗三行的實際 AST 型別、沒有跑 `HistoryTest`（守則禁止）。判定 a～c 都是靜態讀碼加測試案例類比。
- **repo 文件**：只用 `grep -n -o` 與遮蔽值的 `sed` 讀；沒有讀任何 `.env*`、沒有碰 `apps/stock-desk/backend/data/`、沒有執行 `.bat`、沒有看 `.claude/worktrees/`。
- **未查證清單**：
  1. Windows PowerShell 5.1 內建 PSReadLine 版本（repo 無記載）、PowerShell 7 內建版本；
  2. CEO 實際使用的 shell 與版本，是否照做過，是否自訂過 `Set-PSReadLineOption`（含 `HistorySaveStyle`、`AddToHistoryHandler`）；
  3. `hostName` 的實際值與歷史檔實際存在與否；
  4. `$env:FINMIND_TOKEN = "abc"` 的 AST 型別（需用 parser 實跑確認）；
  5. 各版本引進過濾的日期、changelog；
  6. Git Bash 與其他 bash 的預設 `HISTCONTROL`／`HISTFILE`／寫檔時機；
  7. 歷史檔的檔案權限與是否被備份或同步（例如漫遊設定檔）；
  8. 各份文件內短佔位值是否真為佔位（已掃描無長串疑似實值）。
- **限制**：learn.microsoft.com 無法解析，沒有引用 Microsoft 文件；所有結論來自 GitHub 上的 PSReadLine 原始碼。

## 四、下一步

交給 coordinator 與風控決定，我沒有動任何 repo 檔案、沒有 commit：

1. 風控把 RC-530 的推論改為有依據的表述：成立的範圍是 `SEC_USER_AGENT`、`SPIKE_US_HOLDINGS`、`STOCK_DESK_DB_PATH`、`UV_ENV_FILE` 類路徑，以及（2.1.0 以後）`ALPHA_VANTAGE_API_KEY`；`FINMIND_API_TOKEN` 在 PowerShell 下被排除。
2. 風控決定是否、如何對 CEO 提起，並自行定稿字面。**在此之前不對 CEO 提，也不叫 CEO 去查歷史檔。**
3. 需要時我可進一步查證（需風控或 coordinator 指示）：（一）在可執行環境以 PowerShell parser 確認判定 c 的 AST 型別；（二）取得 Windows PowerShell 5.1 內建 PSReadLine 版本的可引用來源；（三）Git Bash 預設的 history 行為。
4. 若 spike 文件要修，涉及 spike 第 81～82 行與 bash 附錄，屬文件修改，不由我動手，交 coordinator 派工並經 qa-reviewer 審查。
5. 回滾方式：本次只新增這一份報告檔；刪除 `work/reviews/2026-11-22-PSReadLine歷史檔查證RC530-devops-sre.md` 即還原。scratchpad 內的 PSReadLine clone 只在 scratchpad，不在 repo 內。
