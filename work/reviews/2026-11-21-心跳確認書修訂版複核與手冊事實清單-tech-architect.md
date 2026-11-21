# D-10 確認書修訂版複核、主機部署手冊第 0.2／0.3 節的事實清單

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：D-10 確認書修訂版複核、主機部署手冊第 0.2／0.3 節的事實清單

兩件分開寫，每件都用四段式。全程唯讀（Read／Glob／Grep），沒有寫檔，沒有讀 `.env`，沒有碰 `backend/data/`。`.env.example` 的讀取被權限擋下，所以它的內容我沒有查證。

---

# 第一件：D-10 心跳責任確認書修訂版複核

## 本次結論

1. **M1～M8 全部到位。** 程式事實我逐項抽查過，都成立。
2. **修訂版可以視為補充十三第 7 點 (b) 的書面確認，但要再補一個 commit。**（tech-architect 建議）
   - 檔頭第 5 行還寫「修訂版待 tech-architect 複核後才 commit」，但檔案已經 commit 了。依確認書第 5 節與我上一份「下一步 1」，順序應該是先複核、後 commit。
   - 補正 commit 必改 R1～R3，建議一併改 R4～R8（見下）。改完的這個 commit 才算數，而且要早於接線 PR 的合併 commit（第 7 點 (c)）。
   - 是誰、什麼時候 commit 的，我沒有權限查 `git log`，沒有查證。
3. **devops-sre 自行補的兩處：**
   - (a) 方向正確但不完整。見 R3。
   - (b) 轉送本身正確，但歸類的名稱不對。見 R2。
4. **`misfire_grace_time`：接線 PR 內不改，另案處理。**（tech-architect 裁示）
   - 這不是接線前要處理的缺口。
   - 原因 G 標「推論，未查證」是恰當的。
   - 補充十的「啟動補跑」**沒有涵蓋喚醒後的情形**。
5. 全文沒有對 CEO 說的字面，和補充十三、RC-360、361、364、378 都沒有牴觸。只有兩處措辭建議修改（R5、R6）。

## 各部門回報（tech-architect）

### 1. M1～M8 逐項

| 項目 | 結果 | 位置與說明 |
|---|---|---|
| M1 | 到位 | 第 108～121 行是 (i)～(iii) 的表，並改為「多半也會」；(ii) 寫明表現為漏記；(三)(a)-4 第 4 步與 (六) 第 5 項都已擴大。對照程式屬實：`dev-up.bat` 94～101 行；`forecast-status.bat` 11 行；`forecast_status.py` 224～227 行；`scheduler.py` 699～700 行。接線版 `dev-up.bat` 的 92～101、150、166 行也和 product 版相同（只抽查這幾行，沒有全檔比對）。 |
| M2 | 到位 | C1／C2、D 的三種來路、E 拆成兩半（67、71 行）、G（69 行）都在；(四) 已註明「有開著」排除不了 D、G、C2（222 行）。另有一處不完整，見 R4。 |
| M3 | 到位 | 84～89 行。`recorder.py` 的 `end_run` 寫在 except 區塊裡；`get_index_resolver()` 在 `scheduler.py` 788 行，位於 try 之外。兩點都屬實。 |
| M4 | 到位 | 140～143、196、276 行。另有小建議，見 R7。 |
| M5 | 到位 | 223 行，「連續」的定義與兩種例外都照寫。 |
| M6 | 到位 | 278 行。 |
| M7 | 到位，但有一句要更正（R1） | (五) 第 2～4 點的內容正確。 |
| M8 | 到位 | 104～106、188～189 行。 |

### 2. devops-sre 自行補的兩處

**(a) 「中斷後沒有後續執行」加了 C2 與 G：正確，但不完整。**
- 依補充十三第 2 點 (f)，這個代號的意思是「P 到 R 之間沒有任何一次新的執行開始」。所以漏記表中，凡是能持續整段期間的原因都可能成立，不只 C2 與 G：
  - C1 若連續多晚發生（例如資料來源連續幾天失敗），一樣不會留新列；
  - 之後某一次執行卡在 `begin_run` 之前（E 的前一半），一樣會被 `max_instances=1` 擋住後續。
- 在這個代號下，C2 有一層特別的含意：那筆沒有 end 列的執行 R 當時已經通過目標核對、也通過了 `begin_run`，所以 C2 一定是 R **之後**才出現的。可能是環境或 `.env` 被改過、而且重新啟動過；也可能是主 DB 被移動、替換，或 schema 不見了（`target_unresolved`、`target_not_default`、`SchemaIncompleteError`）。後者屬於 F-8 的疑慮。
- D 不適用：R 本身就是接線版程式留下的。F 已包含在 A 裡。

**(b) (六) 第 7 項把 M5 的例外列入轉送：轉送正確，名稱不對。**
- M5 的兩種例外，適用在 CEO 回答「不確定」，或者根本沒有問的時候，也就是**沒有任何依據顯示當時開著**。歸在「開著卻沒有記錄的缺陷調查」底下，等於預設了機器開著。

### 3. 修改清單（R1～R3 必改，R4～R8 建議；都可以放進同一個補正 commit）

- **R1**（必改，(五) 第 4 點）：「coordinator 已請風控在接線 PR 合併之前預先定稿一則請求」這句，我在追蹤清單（讀到第 692 行）只找到我的建議，找不到 coordinator 已經送出的紀錄。改為「tech-architect 建議預先定稿；是否已送、是否已定稿，以追蹤清單為準」。在責任確認書裡，不能把沒有查證的事寫成已發生。
- **R2**（必改，(六) 第 7 項）：改成兩款：
  - 「有開著」的缺陷調查；
  - 「原因未明、依 (四) 須轉送」：連續兩次原因未明、「漏記（尚未開始記錄）」、同一次已達 5 個以上平日。
- **R3**（必改，「中斷後沒有後續執行」那一段）：
  - 原因補上「持續多晚的 C1」與「之後卡在 `begin_run` 之前的執行」；
  - 加一句：「C2 在此代號下表示 R 之後環境或主 DB 有變動；疑似主 DB 被移動、替換或 schema 不見時，依 (六) 第 4 項當天轉 tech-architect。」
  - 同一份貼回若另依第 2 點 (b) 列出日期，L2 照漏記的條件判斷。「中斷後沒有後續執行」本身不問，不排除同一份貼回的漏記可以問。
- **R4**（D 的來路與 B 的界線）：依 `dev-up.bat`：
  - 在 123 行 `ensure_scheduler_free` 之前結束的情形，都會讓舊 scheduler 留著，屬於 D：缺工具（51～53 行）、不是 git repo（61～65 行）、切換分支回答 N 或切換失敗（79～88 行）、port 8000／3000 的提示回答 N 或遇到 PID 4（119～122、251～261 行）。
  - 在它之後才失敗的情形，舊 scheduler 已經停掉、新的沒有啟動，屬於 **B、不是 D**：`uv sync`（130 行）、`npm install`（139 行）失敗，或 backend 健康檢查逾時（159 行）。
  - (五) 第 2 點的「D 的三種來路」照此修正。
- **R5**（第 253 行）：「請 CEO 不要自己重新啟動任何程式」放在引號裡，容易被當成定稿字面。實際字面是「不要自己重抓資料、修改設定或重新啟動任何程式」。改成不加引號的描述。
- **R6**（(三)(c) 第 4、5 步）：
  - 「只有改變 CEO 開關機習慣才能根本改善停機」只適用 A。G 另有技術上的槓桿（見第 4 節），但那是 ADR-0030 補充九第 7 點 (d) 決定的事項，不屬於 devops-sre 部門可以自己處理的範圍。
  - 第 5 步的發現一律依 (六) 第 8 項轉 tech-architect，只陳述事實，不提建議。
- **R7**（(四) 第 5 點的例外 (2)）：註明「5 個以上平日」以 coordinator 比對紀錄的判定為準，devops-sre 不自己相加（RC-364 (b)(c)）。
- **R8**（「沒有 end 列」的可能原因）：
  - 補一項：CEO 執行報告的當下，剛好有一次執行正在進行。補充十三第 2 點 (d) 已承認這種情形；它會讓「沒有 end 列=」增加，記成「中斷的執行」。
  - 「睡眠」列為原因要標「推論」：睡眠只會讓程序暫停，本身不一定會讓那一次沒有 end 列。

### 4. APScheduler、misfire 與原因 G（裁示）

**事實**
- `forecast_record` 註冊在 `scheduler.py` 928～936 行，沒有設 `misfire_grace_time`；`data_refresh` 有設 15 分鐘（191、863 行）。
- **這是 ADR 明文決定的**：補充九第 7 點 (d)（`work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md` 181 行）寫「不另設 `misfire_grace_time`，沿用 APScheduler 的預設值。錯過的時點由 23:10 重試與啟動補跑涵蓋」；補充十的裁示 205 行重申。
- 啟動補跑只在 `build_scheduler` 執行時算一次（926 行，`started` 取自 879 行），所以**喚醒不是啟動，不會觸發補跑**。補充十第 3 點的時段規定只管程序啟動，沒有涵蓋喚醒。
- 結果：程序一直開著、主機睡眠跨過 22:10 與 23:10 兩個時點時，那一晚沒有任何執行；下一次是下一個平日的 22:10，漏掉的 session 進入 F-2 分子。所以補充九第 7 點 (d) 的理由（「由 23:10 重試與啟動補跑涵蓋」）在這種情形下不成立。只跨過 22:10 一個時點時，23:10 仍會執行。

**G 標「推論，未查證」是否恰當：恰當。**
- 1 秒的預設值是讀原始碼確認的（沒有執行）；睡眠時的實際行為沒有實測。
- 另一個沒有查證的因素：Windows 的計時等待在睡眠期間可能不計時，scheduler 醒來的時間可能比牆上時鐘晚。不論是哪一種，結論都是那一次被當成 misfire、不執行。

**不在接線 PR 改，另案處理。理由：**
1. 這是 ADR 已定稿的條文。在接線 PR 改，等於違反補充九第 7 點 (d)；要改，須先有 ADR-0030 的補充並經風控。
2. 寬限期的長度屬於寫入時點的決定。寬限一長，錯過的 23:10 可能在隔天平日 13:30～22:10 之間被執行，可能以 22:10 之前取得的值寫下 `late = 0` 紀錄，正好牴觸補充十第 3 點要保證的事（每一筆 `late = 0` 都出自 t0 不早於 T 日 22:10 的執行；依第 5 點改為 18:10）。所以上限要另外推算，不能只是「比照 `data_refresh`」。
3. 屬 fail-closed：只會少記，不會記錯；而且心跳可以偵測。
4. `scheduler.py` 不在 `code_digest` 涵蓋範圍，之後再改也不會觸發 D-5 第 6 點的重算。延後的代價只有睡眠那幾晚沒記到，不影響帳本的完整性。
5. 接線 PR 已經到第五輪複審，再加範圍會讓審查重開。

**另案的處理方式**
- 由 tech-architect 列管，以 ADR-0030 的補充處理。內容：揭露這個限制；決定是否設有上限的寬限（上限要守住補充十第 3 點）；說明中途改動時驗證報告要怎麼揭露。
- 依補充十三第 4 點 (g)，這件事不得由心跳升級觸發，要獨立決定。
- 可以併入第 6 點的重審設計一起處理。目前不需要 CEO 決定，也不需要讓 CEO 知道。

### 5. 有沒有對 CEO 說的字面、有沒有牴觸
- 全文沒有對 CEO 說的字面。L2 與重啟請求都寫明「經 coordinator、用風控定稿的字面」。
- (三)(c) 照 RC-378 的先後；(七) 禁止寫入整數差，符合 RC-364 (b)；(四) 的「沒有開著」不轉送、「有開著」通知 tech-architect，符合 RC-361 (d)。
- 唯一的措辭問題是 R5、R6，屬內部用語，不構成牴觸。

## 驗證
- 讀過：確認書修訂版全文；修訂交件全文；我方上一份審查第一件全文；補充十三組版檔全文；RC-360、RC-361、RC-364 全文；追蹤清單 674～692 行；補充九裁示 130～189 行；補充十組版 50～114 行。
- 程式：接線版 `scheduler.py` 189～229、600～955 行；`claims.py` 280～419 行；product 版 `dev-up.bat` 全文；接線版 `dev-up.bat` 的部分行（Grep）；`forecast-status.bat` 全文；`forecast_status.py`（Grep STOP 與環境變數條件）。
- 沒有查證：
  - 修訂版是誰、什麼時候 commit 的（沒有 `git log` 權限）；
  - coordinator 是否已經請風控預先定稿重啟請求（追蹤清單沒有紀錄）；
  - APScheduler 與 Windows 在睡眠時的實際行為；
  - 接線版與 product 版 `dev-up.bat` 全檔是否相同。

## 下一步
1. devops-sre 依 R1～R3（必改）與 R4～R8（建議）出一個補正 commit。檔頭修訂紀錄改為「2026-11-21 經 tech-architect 複核（出處：本報告存檔），R1～R8 已補」。這個 commit 要早於接線 PR 的合併 commit。範圍只限本報告列出的項目，我不必再審一輪，由 coordinator 逐項核對 diff 即可。
2. coordinator：追蹤清單補兩列：「重啟請求預先定稿」是否已經送風控（R1 的事實）；「`forecast_record` 的 misfire 與睡眠，tech-architect 另案以 ADR-0030 補充處理，不是接線前置」。
3. tech-architect：起草 misfire 另案的補充（優先序中，不在接線前）。
4. 這一件沒有需要 CEO 決定的事。

---

# 第二件：手冊第 0.2、0.3 節改寫所需的事實清單

（行號以接線版工作樹 `agent-a352324c9d164984b` 為準；三個路徑解析函式在 product 版的行號相同。手冊行號是 product 現行版；在 `chore/dev-up-missing-tool-wording` 分支上，第 0.1 節已經改寫，0.2／0.3 節大約往後移 2 行。）

## 本次結論

1. 手冊現行的 0.2／0.3 節照做的話，**每一晚的預測記錄都會被拒絕**。原因有兩個：在 PowerShell 視窗或 `.env` 設了 `STOCK_DESK_DB_PATH`；三顆 DB 被指到 `C:\stock-desk\data\`，和 `dev-up.bat` 實際用的 `apps\stock-desk\backend\data\` 是不同的檔案。
2. 會讓預測記錄、正式登記、狀態報告拒絕或 STOP 的，**只有 `STOCK_DESK_DB_PATH` 一個變數**。只要這個名稱存在就算有設，不看值，空值也算。另外兩個路徑變數和拒絕條件無關。
3. （tech-architect 判斷）手冊第 1 節以後的 PowerShell 流程，照現有字面和「以 `dev-up.bat` 啟動並記錄預測」**不相容**。**手冊開頭必須標明適用範圍**：CEO 的啟動方式是 `dev-up.bat`；兩種啟動方式不得混用；保留下來的手動步驟必須和記錄相容。字面歸風控。
4. 時點：0.2／0.3 節的改寫不能晚於 `dev-up` 改字分支的合併。那次合併會結束 RC-387 的過渡期，之後 coordinator 就可以引用這份手冊。所以要比照 RC-386，以獨立 commit 放進同一個 PR，而且要早於接線 PR 的合併。

## 各部門回報（tech-architect）

### 1. `.env` 的位置與讀取方式

- **位置**：`apps\stock-desk\.env`，和 `dev-up.bat` 放在同一層。`dev-up.bat` 第 94 行是 `ENV_FILE=%DEVUP_SRC_DIR%.env`，`DEVUP_SRC_DIR` 是 `dev-up.bat` 所在的資料夾（第 11 行）。**不是 `backend\.env`。**
- **`dev-up.bat` 怎麼帶給 backend 與 scheduler**：
  - 檔案存在時設 `UV_ENV_FILE`（95～96 行），只印出路徑（98 行）。
  - backend（150 行）與 scheduler（166 行）都以 `uv run` 在新的 `cmd /k` 視窗啟動，會繼承這個變數，由 uv 把檔案內容放進這兩個程序的環境（依第 92 行的註解；鎖定版本 uv 的實際行為我沒有查證）。
  - 前端（167 行）不是經 uv 啟動，拿不到 `.env`。
  - 第 27 行註解寫「Windows 已設的變數優先於檔案」，這是 uv 的行為，沒有查證。
- **程式本身不讀 `.env`**：`app/` 裡 Grep `dotenv`、`load_dotenv` 都是零筆。唯一讀這個檔的是登記檢查，而且只找變數名稱（見第 3 點）。
- **沒有 `.env` 時**：清空 `UV_ENV_FILE`（101 行，同時也蓋掉 Windows 層的同名變數），印出「沒有 .env，照常啟動，FinMind 與推播不開」（103～104 行），整套照常啟動。
- **其他一鍵檔都刻意不帶 `.env`**：`forecast-status.bat`、`cg2-preflight.bat`、`cg2-register.bat`、`pipeline-acceptance.bat` 第 11 行都清空 `UV_ENV_FILE`。
- **手冊第 1 節的 PowerShell 流程（不經 `dev-up.bat`）**：
  - 第 3 步（115～118 行）在 `apps\stock-desk\backend` 執行，讀的是 **`backend\.env`**，用片段把內容設成「目前這個 PowerShell 程序」的環境變數；API 與 scheduler 的視窗要各自跑一次。
  - 這個流程沒有設 `UV_ENV_FILE`，所以 **`apps\stock-desk\.env` 不會被讀到**。我依 uv 的一般行為推論 `uv run` 不會自動讀 `.env`，鎖定版本沒有查證。
  - 結論：兩種流程讀的是兩個不同的檔案。

### 2. 三顆 DB 的預設位置

| DB | 預設值 | 出處 |
|---|---|---|
| 主 DB | `./data/stock-desk.db` | `app/data/cache.py` 28、99～102 行 |
| 市場 DB | `./data/stock-desk-market.db` | `app/data/market_panel.py` 95、239～242 行 |
| 研究 DB | `./data/stock-desk-research.db` | `app/research/sector_biased/store.py` 46、124～127 行 |

- 三者都是相對路徑，**取決於程序開檔時的工作目錄**。我沒有查到任何會改工作目錄的程式，但沒有逐檔查證。
- **`dev-up.bat` 路徑下**：backend 與 scheduler 都先 `cd /d "%BACKEND_DIR%"`（150、166 行），`BACKEND_DIR` 是 `apps\stock-desk\backend`（30 行）。所以三顆都落在 **`apps\stock-desk\backend\data\`**。研究 DB 只有在跑研究程式時才會開，API 永遠不開。
- **另外三處的主 DB 位置固定，由程式所在位置導出，不看工作目錄、也不看變數**：
  - scheduler 的目標核對要求主 DB 等於 `<backend>/data/stock-desk.db`（`scheduler.py` 666、686～688 行）；
  - 狀態報告固定讀 `<backend>/data/stock-desk.db`（`forecast_status.py` 7、161 行）；
  - bootstrap 也一樣（`claims.py` 407～410 行）。
  - 所以 scheduler 若不是從 `backend` 目錄啟動，預設的相對路徑會解析到別處，記錄會被拒絕（`target_unresolved` 或 `target_not_default`）。
- 手冊 0.3 節的 `C:\stock-desk\data\*.db`，和 `dev-up.bat` 用的是**不同的檔案**。

### 3. 設了路徑變數的後果

**`STOCK_DESK_DB_PATH`**
- **一般功能**：所有主 DB 的 store 都改用它指定的檔案（`resolve_db_path`）。API 與 scheduler 若一個有設、一個沒有，就各用各的檔案。
- **設成空值**：`Path("")` 等於 `.`，也就是目前目錄。用一個資料夾當 SQLite 檔開不起來，所以推論一般功能會失敗，沒有實際執行驗證。
- **預測記錄**（補充九第 3 點，`scheduler.py` 691～709、783～786 行）：
  - (a) 程序環境裡**有這個名稱就拒絕**，不看值：空值、甚至指向預設檔本身都一樣（699～700 行，`env_db_path`）。
  - (b) 主 DB 解析失敗（`target_unresolved`）、不等於 `<backend>/data/stock-desk.db`（`target_not_default`）、不是一般檔案（`target_not_regular`），都拒絕（701～708 行）。
  - **只看這一個變數**，另外兩個不在任何條件裡。被拒絕時記一行固定的 WARNING（668～683 行），不留 `forecast_run`。
- **正式登記**：
  - bootstrap（`claims.py` 403～406 行）與 preflight／register（`cg2_register.py` 861～866 行）都會拒絕兩種情形：環境裡有這個名稱（空值也算）；`apps\stock-desk\.env` 有一行符合 `^\s*STOCK_DESK_DB_PATH\s*=`（`claims.py` 291、385～390 行，只找名稱，空值也算）。
  - 注意：這兩支工具的 `.bat` 都清空 `UV_ENV_FILE`，所以環境檢查只看得到 Windows 層，或啟動那個視窗裡已經設好的變數；`.env` 則是直接把檔案當文字讀。
  - 沒有查證的缺口：
    - 以 `#` 開頭的註解行不算；
    - 寫成 `export STOCK_DESK_DB_PATH=`、或大小寫不同的寫法，這個比對抓不到，而 uv 會不會照樣載入，沒有查證；Windows 的環境變數名稱不分大小寫，所以 scheduler 那邊仍可能拒絕；
    - **`backend\.env`（手冊用的那個檔）不在檢查範圍內。**
- **狀態報告一鍵檔**：環境裡有這個名稱（空值也算）就 STOP（`forecast_status.py` 11～13、224～227 行），不讀 `.env`。所以變數只寫在 `apps\stock-desk\.env` 時，報告照常印出，記錄卻每晚被拒絕。
- **Windows 上的空值**：`cmd` 的 `set X=`、PowerShell 的 `$env:X=""`、`SetEnvironmentVariable(…, "")`，一般的效果是刪掉變數，不是設成空值（未實機驗證）。所以實務上「空值」比較可能經由 uv 讀 `.env` 而出現；uv 會不會把空值放進環境，沒有查證。

**`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH`**
- 和預測記錄、登記、狀態報告的任何拒絕條件都無關（Grep：只出現在各自的模組與 scripts 裡）。
- 一般功能：改變市場 DB（族群動能，手冊 4.1 說「完全無法重建」）與研究 DB 的位置。兩種啟動方式的設定若不一致，市場 DB 會分成兩份。
- 空值：市場 DB 變成 `.`，推論會開檔失敗；研究 DB 的空值會回到預設值（126～127 行）。

### 4. 手冊 0.2 節的變數表：和拒絕條件有沒有關

| 變數 | 和預測記錄／登記的拒絕條件有沒有關 |
|---|---|
| `STOCK_DESK_DB_PATH` | **有關**，而且是唯一有關的變數（scheduler、bootstrap、preflight／register、狀態報告 STOP） |
| `STOCK_DESK_MARKET_DB_PATH` | 無關 |
| `STOCK_DESK_RESEARCH_DB_PATH` | 無關 |
| `ALERT_DISCORD_WEBHOOK_URL`、`ALERT_TELEGRAM_*` | 無關 |
| `SCHEDULER_DATA_INTERVAL_MINUTES`、`SCHEDULER_ALERT_INTERVAL_MINUTES` | 無關（只影響 `data_refresh`、`alert_evaluation`；`forecast_record` 的時刻是固定常數，`scheduler.py` 222～224 行） |
| `FINMIND_API_TOKEN` | 不是拒絕條件。它會不會影響當晚強制重抓指數成不成功（也就是 C1 的機率），我沒有查證 `^TWII` 的取數來源有沒有 FinMind |

### 5. 必須讓 CEO 知道的事實，以及不該寫進給 CEO 段落的內部細節

**必須讓 CEO 知道的事實**（只是內容，不是字面；字面歸風控）
1. 設定檔放在 `apps\stock-desk\.env`，就是 `dev-up.bat` 所在的那個資料夾，不是 `backend` 資料夾。這個檔可以沒有；沒有的話 stock-desk 照常啟動，只是 FinMind 和推播不開。
2. 用 `dev-up.bat` 啟動時，這個檔會自動套用到 backend 與 scheduler，不需要自己設環境變數，也不需要跑任何 PowerShell 片段。
3. **不要在任何地方設定 `STOCK_DESK_DB_PATH`**：Windows 的環境變數、`.env`、PowerShell 視窗都不要。只要它存在，不論設成什麼值，預測紀錄每晚都會停止記錄。
4. （tech-architect 建議）另外兩個路徑變數也不需要設。資料檔放在 `apps\stock-desk\backend\data\`，不要移動或改名。
5. 如果已經照舊手冊設過這些變數，或資料放在別的資料夾，**不要自己刪變數或搬檔案**，先告訴 coordinator。拿掉變數可能讓程式改用另一顆資料庫，這是資料位置的決定（確認書 (五) 第 3 點），要經 tech-architect 與風控，必要時由 CEO 決定。
6. 手冊裡手動啟動的步驟，不是 CEO 平常的啟動方式（見第 6 點）。

**不該出現在給 CEO 段落的內部細節**
- 四種 refusal 的名稱、WARNING 的英文字面、行號、`code_digest`、補充與 RC 的編號；
- (i)～(iii) 的表、「報告正常但記錄被拒」的機制（要不要告訴 CEO，由風控判定；我建議不寫，以預防為主）；
- `UV_ENV_FILE` 的機制、uv 對空值與 `export` 的處理、「Windows 已設的變數優先」（未查證）、Windows 變數名稱不分大小寫；
- `Path("")` 的行為、登記成功可以當作接線前的時點證據、F-2、F-8、心跳比對；
- misfire 與睡眠；
- 任何暗示要改變開關機習慣的內容（RC-360）。

### 6. 手冊第 1 節以後的 PowerShell 流程，和 `dev-up.bat` 加預測記錄相容嗎

**照現有字面：不相容。**
- 第 1 節第 3 步加上 0.2、0.3 節：會把 `STOCK_DESK_DB_PATH` 設進 scheduler 的程序環境，每晚拒絕記錄（`scheduler.py` 699 行）。
- 0.3 節的路徑和 `dev-up.bat` 的 `backend\data\` 是不同的檔案，兩種啟動方式會看到不同的資料庫；狀態報告與記錄的目標核對只認 `backend\data\stock-desk.db`。
- 手冊用 `backend\.env`，`dev-up.bat` 用 `apps\stock-desk\.env`，而登記檢查只看後者。
- 第 5、6 步手動啟動 API（127.0.0.1:8000）與 scheduler：若和 `dev-up.bat` 啟動的同時存在，會搶 port；`dev-up.bat` 會把任何命令列含 `app.scheduler` 的 python 程序當成舊 scheduler，提示後以 `taskkill /F /T` 結束（`dev-up.bat` 277～302 行）。這正是「沒有 end 列」的來源之一。兩個 scheduler 同時跑時，對帳本的影響沒有查證。
- 第 3 節「每次更新」的 `git pull` 與重啟，和 `dev-up.bat` 自己做的事重複。
- 第 4 節備份指令寫死 `C:\stock-desk\data\`，在 `dev-up.bat` 路徑下指錯檔案。還原主 DB 屬於 F-8，依補充九第 2 點，還原後的 bootstrap 要先修訂 ADR；這一節不能讓 CEO 自己還原。
- 第 5 節的監控依賴 `logs\scheduler.log`，但 `dev-up.bat` 不會產生檔案 log。

**相容的部分**
- 從 `backend` 目錄啟動、程序環境裡沒有 `STOCK_DESK_DB_PATH` 時，手動啟動的 scheduler 也能正常記錄。
- 把 log 導向檔案不影響寫入。

**架構判斷：手冊開頭必須標明適用範圍。**（tech-architect 建議；字面歸風控）
- 預測記錄期間，CEO 的啟動方式是 `dev-up.bat`。
- 手冊裡手動啟動、更新、log 監控的流程，不得和 `dev-up.bat` 混用。
- 保留的任何手動步驟，都必須做到：不設 `STOCK_DESK_DB_PATH`、從 `backend` 目錄啟動、資料在 `backend\data\`。
- 第 4 節的備份路徑與還原，要一起修正或加註。這超出 0.2／0.3 的範圍，建議列為同一個 PR 的後續項。

## 驗證
- 讀過：手冊全文；product 版 `dev-up.bat` 全文；`forecast-status.bat`；接線版的 `cache.py` 1～115 行、`market_panel.py` 88～99 與 236～247 行、研究 `store.py` 40～134 行、`claims.py` 280～419 行、`scheduler.py` 相關各段。
- Grep：三個路徑變數在 `app/` 與 `scripts/` 的全部出處；`app/` 內的 `dotenv`；各 `.bat` 的 `UV_ENV_FILE`；`compose.yaml` 第 19、43 行顯式設了 `STOCK_DESK_DB_PATH`（所以 compose 部署不會記錄，和補充九第 3 點一致）。
- 沒有查證：
  - `.env.example` 的內容（權限擋下）。`dev-up.bat` 第 104 行叫 CEO「把 .env.example 複製成 .env」，**它若含有 `STOCK_DESK_DB_PATH` 那一行，照做就會讓記錄被拒絕**。請 devops-sre 確認；
  - uv 對 `UV_ENV_FILE` 的空值、`export` 前綴、優先順序的處理；
  - Windows 上空值與變數名稱大小寫的實際行為；
  - `FINMIND_API_TOKEN` 在指數取數中的角色；
  - 兩個 scheduler 同時跑時對帳本的影響。

## 下一步
1. devops-sre：確認 `apps/stock-desk/.env.example` 有沒有 `STOCK_DESK_DB_PATH` 這一行（只回答有或無）。有的話，在接線前移除，並送 qa-reviewer。
2. creative-lead：依第 5 點起草 0.2／0.3 節，加上開頭的適用範圍；風控定稿。以獨立 commit 放進 `chore/dev-up-missing-tool-wording`（比照 RC-386）。分支 head 改變後，qa-reviewer 與風控要重新單項確認，`dev-up` 分支合併前的各項核對也要以新的 head 重做。
3. coordinator：追蹤清單把「手冊 0.2／0.3 節改寫」標為接線 PR 合併前置，而且不晚於 `dev-up` 分支合併；第 4 節備份路徑列為後續項。
4. 這一件沒有需要 CEO 決定的事。

---

相關路徑：
- `/home/user/AICompany/work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`
- `/home/user/AICompany/work/reviews/2026-11-21-心跳責任確認書修訂交件M1至M8-devops-sre.md`
- `/home/user/AICompany/work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md`（補充九第 7 點 (d)，181 行）
- `/home/user/AICompany/work/reviews/2026-11-20-補充十定稿-待寫入-coordinator組版.md`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/claims.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/data/cache.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/data/market_panel.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/research/sector_biased/store.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/scripts/cg2_register.py`
- `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/forecast-status.bat`
- `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/backend/scripts/forecast_status.py`
- `/home/user/AICompany/apps/stock-desk/dev-up.bat`
- `/home/user/AICompany/apps/stock-desk/compose.yaml`
- `/home/user/AICompany/apps/stock-desk/docs/族群動能-主機部署手冊.md`
