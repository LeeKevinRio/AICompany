# ADR-0012 補充一 (b)(iii) 範圍、backend README 與 seed.py 訊息、預測紀錄大盤來源

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **第一件**
  - 【裁示】(iii) 的「改寫」不包含只改 `echo` 字面、不改控制流程的變更。甲、丙兩支都不會觸發設計 (a)，可以照原順序在接線 PR 之前合併。
  - 【裁示】這個讀法記在追蹤清單，算 tech-architect 的解釋，不另寫補充二。日後 ADR-0012 有下一則補充時，再一併收進去。
- **第二件**
  - 【裁示】`backend/README.md` 走一支只改文件的獨立 PR，由 devops-sre 起草，接線 PR 合併前完成。
  - 【裁示】`seed.py` 那句訊息要改，但時間排在正式登記之後。理由是它在 `app/` 樹內：不在 `code_digest` 的涵蓋範圍，不會觸發 D-5 第 6 點；但會讓登記一鍵檔釘住的 `app/` tree id 失效。
  - 【建議】「偵測到正式主 DB 就拒絕」值得做，另立任務，低優先，不擋接線。
  - 【事實】示範資料寫進主 DB 對預測紀錄帳沒有影響：它不寫 `^TWII`，也不寫任何 recorder 會讀的表。
- **第三件**
  - 【事實】`forecast_record` 強制重抓大盤的整條來源鏈只有 yfinance，沒有任何一步用到 FinMind 或 token。
  - 【事實】token 補不補、FinMind 額度用掉多少，都不會改變 `forecast_record` 讀到的資料，也不會改變 `runtime_json`、`code_digest`。

## 各部門回報（tech-architect）

### 第一件：補充一第 2 點 (b)(iii) 的範圍

**【裁示】可寫進追蹤清單的讀法**

> ADR-0012 補充一第 2 點 (b)(iii)「改寫 `dev-up.bat`」，指新增、刪除或重排指令行，或改動控制流程（`if`／`errorlevel`／`goto`／`call`／`start`／`set`／`REM` 以外的任何指令與其參數）的變更。只改 `echo` 輸出字面、不改控制流程與步驟順序的變更，不觸發 (iii)。（tech-architect 解釋，2026-11-21）

**【裁示】qa 判定「只改字面」的檢查方式（逐條可查）**

1. `git diff` 的每一個變更行，把 `echo` 之後的輸出字面拿掉後，新舊兩行要完全相同。像 `if errorlevel 1 (echo …) else (echo …)` 這種同一行內有控制結構的，括號和 `if`／`else` 也必須不變。
2. 新字面裡不得出現沒有跳脫的 cmd 特殊字元：`( ) & | < > ^ %`，以及在 delayed expansion 下的 `!`。
   - 【事實，依 cmd 的一般行為，未實機驗證】在括號區塊內，沒有跳脫的 `)` 會提早結束區塊，`&`、`|` 會串接或導向成另一個指令。
   - 所以「只改字」在 batch 裡可能實質改到控制流程。這一條沒過，就視為改寫，觸發 (iii)。
3. 沒有新增或刪除任何一行。

**【推論】為什麼不採「包含」**

- (iii) 的目的，是有人本來就在改啟動步驟時，順手把 attestation 步驟一起排進去、一起審。純字面變更不碰步驟，沒有可以搭的審查。
- 如果採「包含」，設計 (a) 要在甲、丙之前交件。但第 3 點 (d) 的時間上限還沒有實測，(i) 的監控方式也還沒裁示。結果會把風控 RC-446 的字面修正，以及接線時程，一起卡在一個還沒成形的設計後面。我不要求這樣做。

**【裁示】怎麼記錄**

- 理由一：這個讀法只是界定 (iii) 的文義範圍，沒有改任何決策、期限或約束。
- 理由二：補充一是 accepted ADR 的 append，不能改字。
- 所以記在追蹤清單（列為「tech-architect 解釋」，附本報告的出處），再加一列「下一則 ADR-0012 補充收錄此解釋」就夠了。單獨為這件事 append 補充二，成本不划算。
- 如果有人對這個讀法有異議，再改成補充二。

**qa 的兩個備註**

- 知悉：檔頭那一行多了反引號與「（D 節）」；第 1 點 (d) 後面有一行只含 5 個空白，是草稿原樣。
- 沒有意見，兩者都不影響文義，也都符合 S-A1-1（diff 只有新增行）。不要為了這兩處另外改檔，否則會破壞 append-only。

### 第二件：`backend/README.md` 與 `seed.py`（RC-460）

**【事實】依據**

- `scheduler.py`（接線版）
  - 699～700：程序環境裡只要有 `STOCK_DESK_DB_PATH`（空值也算），`forecast_record` 就跳過；跳過時記的 WARNING 字句在 669～670。
  - 701～708：除此之外，目標必須等於 `<backend>/data/stock-desk.db`（686～688），而且是一般檔案。
- `claims.py`
  - 398～403：登記與 bootstrap 也拒絕環境變數或 `<backend>/../.env` 設定 `STOCK_DESK_DB_PATH`；拒絕字句在 305。
- `dev-up.bat`（product）
  - 165：環境變數照原樣繼承。
- `compose.yaml`
  - 19、43：顯式設定 `STOCK_DESK_DB_PATH`。【推論】接線合併後，compose 形態下 `forecast_record` 每次都會跳過。這和 C-52 採主機 checkout 部署一致。
- `seed.py` 寫入範圍
  - 寫入哪些表：`price_bars_cache`（經 `PriceBarCache.put`，第 438 行）、持倉表（`PositionStore.create`，第 447 行）、警示規則表（`AlertStore.create_rule`，第 458 行）。
  - 寫入哪些標的：只有 `2330`、`0050`、`00631L`，市場 TW（第 318～322 行）。
- `seed.py` 的 `--db-path`
  - 第 559 行：有指定時直接用該路徑，不讀環境變數；沒指定時用 `resolve_db_path()`，也就是環境變數，或相對於 cwd 的 `./data/stock-desk.db`（`cache.py` 第 28、99～102 行）。
  - 第 560～562 行：在衝突檢查之前就先建立三個 store。【推論】目標檔或表可能在檢查之前就被建立，未驗證。

**1. `backend/README.md` 各行應寫成的事實**

- 第 54 行（環境變數表）
  - 執行預測紀錄的主機上，不得設定這個變數，空值也不行，也不得寫進 `.env`。設了，排程的 `forecast_record` 每次都跳過、只記一行 WARNING；登記與 bootstrap 也會拒絕。
  - 預測紀錄只寫 `<backend>/data/stock-desk.db`。
  - Docker Compose 會顯式設定這個變數，所以 compose 不是會記錄預測的部署形態。
  - 這個變數只適用於不執行預測紀錄的機器，例如 CI、展示機。
- 第 109 行
  - 不加 `--db-path` 時，示範資料會寫進預設主 DB（相對於 cwd 的 `./data/stock-desk.db`），和預測紀錄帳同一個檔。
  - 在執行預測紀錄的主機上不得這樣跑。
- 第 113 行
  - 用 `--db-path` 隔離示範資料是正確做法，不需要、也不應該設環境變數。
  - 路徑相對於 cwd。
  - 要讓 API 讀示範 DB，只能在不執行預測紀錄的機器上，對那一個 API 程序設變數。
- 第 142 行
  - 衝突時建議的出路只寫 `--db-path`。拿掉「／`STOCK_DESK_DB_PATH`」，或改成上述只限非預測紀錄機器的限定說法。
- 【建議】第 99 節順手加一條事實：示範持倉與警示規則寫進主 DB 時，會進入真實帳本的估值、`data_refresh` 的持有標的清單，以及警示評估。標記只是用來辨識，不會把它們排除。

**由誰改、哪個 PR、時點**

- 【裁示】由 devops-sre 起草（環境變數與部署事實是他的職責），dev-lead 核對程式事實。
- 開一支只改 `apps/stock-desk/backend/README.md` 的獨立 docs PR，不放進 README PR，以符合風控要求。
- 經 qa-reviewer（含 Codex）審查，diff 送風控知悉。
- 時點：接線 PR 合併前完成；而且在任何 CEO 文件連到 `backend/README.md` 之前一定要完成。
- 【事實】`README.md` 不在 `app/` 樹內，不影響登記一鍵檔的 tree id 常數。

**2. `seed.py` 的訊息**

- 【事實】`app/demo/seed.py` 不在 `code_digest` 的涵蓋範圍內。`canonical.py` 第 77～78 行只列了 `forecast`、`outlook`、`dirdef` 這三個 package，以及 `data/session_calendar.py`。所以改它不會改變 `code_digest`，也不會觸發 D-5 第 6 點的重算。`runtime_json` 也不受影響（`recorder.py` 第 182～191 行只有 Python、平台資訊與鎖檔雜湊）。
- 【事實】但它在 `app/` 樹內。登記一鍵檔用 `git rev-parse HEAD:apps/stock-desk/backend/app` 比對一個釘死的常數（`work/reviews/2026-11-17-CG2登記PR第三段一鍵檔交件-devops-sre.md` 第 108、328～330 行）。任何 `app/` 變動都會讓它 STOP `app_changed`。
- 【裁示】要改，排在正式登記之後合併。正式登記前不改，也不併入接線 PR。
- 【裁示】新字面應有的事實（字面由 creative 或 dev-lead 起草，送風控）：
  - 建議的出路只有 `--db-path <獨立檔>`；
  - 不建議設環境變數；
  - 不得引導去清除主 DB 的資料，現行第 2 點「請自行清除後再重跑」在主 DB 情境下應一併檢討；
  - 不新增要使用者回答的提示。
- 同一個 PR 內，模組 docstring 第 47 行和 `--help` 第 555 行裡關於 `STOCK_DESK_DB_PATH` 的說法，要和新字面一致。這兩處是英文註解或工程字面，不送風控逐字審，但 qa 要核對有沒有矛盾。
- **行為改動（拒絕寫入主 DB）**
  - 【建議】值得做，另立任務，低優先。
  - 理由：示範持倉寫進真實帳本，會汙染估值、風險上限與警示，這比預測紀錄帳的風險更直接。
  - 約束如下（逐條可查）：
    - (a) 判斷依據是「解析後的目標路徑等於 `<backend>/data/stock-desk.db`」，用 `Path.resolve`，`<backend>` 由模組位置推得。不以「有沒有帳本表」判斷，因為那樣 `app.demo` 就得知道 `app.forecast` 的 schema，形成耦合（K-2 的精神）。
    - (b) 檢查要放在建立任何 store 之前，不開啟、不建立任何檔案。
    - (c) 不提供用環境變數放行的方式。如果要保留放行旗標，旗標名稱與字面送風控。
    - (d) `--reset` 一併套用同樣的規則。
    - (e) 不 import `app.forecast`。
    - (f) 合併時點同樣在正式登記之後。

**3. 示範資料寫進主 DB 對預測紀錄帳的影響**

- 【事實】沒有影響。
  - recorder 對市場資料只呼叫 `load_benchmark(resolver, market=MARKET, …)`（`recorder.py` 第 670 行），而 TW 的基準只有 `^TWII`（`services/index.py` 第 329 行）。
  - `session_calendar.py` 只 import `freshness` 與 `interface`（第 24～28 行），不讀快取。
  - seed 寫的是 `2330`、`0050`、`00631L`，沒有 `^TWII`；也不寫任何帳本表。
- 【推論】主 DB 裡有示範資料時：
  - 只有在示範標的和真實日線同日期時，seed 才會拒絕；
  - 示範日線用的是平日序列（`trading_days`），可能讓把快取當交易日曆用的路徑（`deps.py` 第 367～374 行，C4）看到假的交易日。
  - 這不是 `forecast_record` 的路徑，不屬於本件，列為未查證的旁支風險。

### 第三件：預測紀錄的大盤來源

- 【事實】來源鏈（接線版）
  - `scheduler.py` 788：`get_index_resolver()`
  - → `deps.py` 377～379：`_default_index_resolver()`（148～189）
  - → `MarketDataService(primary=IndexProviderBridge(_default_yfinance()), …)`，沒有 `backups`（178～187）
  - → `IndexSeriesService`
  - → `services/index.py` 538：`refresh_daily_bars_live`
  - → `data/service.py` 579：只遍歷 `(self._primary, *self._backups)`，也就是只有 yfinance
  - → 543：用 `get_cached_bars` 讀回快取。
  - `FinMindAdapter` 只出現在 TW 個股階梯（`deps.py` 第 127 行），不在指數路徑上。
  - `yfinance.py` 裡 Grep `finmind|token|environ|getenv` 零命中。
- 【事實】token 的有無，不會改變 `forecast_record` 讀到的資料。
  - token 只由 `finmind.py` 第 71 行讀取（另有 `pit_snapshot.py` 第 40 行，屬族群路徑）。
  - `runtime_json` 不含任何環境變數（`recorder.py` 第 182～191 行）。
  - `code_digest` 只涵蓋原始碼。
- 【推論】日後補 token，或族群動能暖身用掉 FinMind 額度，對預測紀錄都沒有影響，因為兩者不共用來源，也不共用額度。
  - 唯一共用的是同一個 yfinance 實例的程序內節流器（`deps.py` 第 68～77 行）。但那是 API 程序或 scheduler 程序各自的節流，和 FinMind 無關。

## 驗證

- 已讀（product）：
  - `apps/stock-desk/backend/app/demo/seed.py` 全檔；
  - `apps/stock-desk/backend/README.md` 全檔；
  - `docs/adr/0012-…md` 第 1150～1266 行；
  - Grep `apps/stock-desk/dev-up.bat`、`apps/stock-desk/compose.yaml`。
- 已讀（接線版，`/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/`）：
  - `app/scheduler.py` 655～830；
  - `app/api/deps.py` 1～385；
  - `app/services/index.py` 170～550；
  - `app/data/service.py` 533～612；
  - `app/data/admission.py` 140～198；
  - Grep `app/forecast/canonical.py`、`recorder.py`、`claims.py`、`app/data/cache.py`、`session_calendar.py`、`providers/yfinance.py`。
- 已讀：
  - `work/reviews/2026-11-17-CG2登記PR第三段一鍵檔交件-devops-sre.md` 第 100～114、320～334 行；
  - `work/reviews/2026-11-20-接線PR第五輪交件-警告行改字-dev-lead.md` 第 85～100 行。
- 沒有查證：
  - 甲、丙兩支分支的實際 diff 沒讀。第一件的判定以「只改 `echo`」這個前提成立為準，由 qa 依上面的檢查方式核對。
  - 丙說的「第 191 行」在 product 版是第 187 行，行號漂移。
  - cmd 特殊字元的行為沒有在 Windows 上實機驗證。
  - `seed.py` 建立 store 時會不會在檢查前建檔、建表，沒有讀 store 的建構子。
  - `TW_SYMBOL_RULE` 會不會拒絕 `^TWII`，沒有讀樣式。
  - 有沒有測試讀 `backend/README.md` 的字面，沒有查。
  - 「正式登記前不得動 `app/`」的限制，我依登記一鍵檔的 tree id 常數理解，沒有找到 ADR 正文的條號。
  - compose 形態下 `forecast_record` 會跳過，是依程式推論，沒有實跑。
  - `backend/data/` 與 `.env*` 依指示沒有讀。

## 下一步

**送風控**

1. `backend/README.md` 修正 PR 的 diff（RC-460，知悉級）。
2. 正式登記後，`seed.py` 第 243～246 行的新字面（逐字審）。
3. 若「拒絕寫入主 DB」任務成立，它的拒絕訊息與放行旗標的字面。
4. 第一件的讀法不涉及字面，不送。

**devops-sre／dev-lead**

- devops-sre
  - 起草 `backend/README.md` 的獨立 docs PR（第二件第 1 點的事實），接線 PR 合併前完成。
  - 在追蹤清單記下第一件的解釋，以及「下一則 ADR-0012 補充收錄」這一列。這兩列也可以由 coordinator 記。
- dev-lead
  - 核對 README PR 的程式事實。
  - 正式登記後開 `seed.py` 改字 PR（含 docstring 與 `--help` 的一致性）。
  - 另立低優先任務評估「拒絕寫入主 DB」，照第二件第 2 點的約束 (a)～(f)。
- qa-reviewer
  - 甲、丙合併前，照第一件的三條檢查方式核對 diff；任一條沒過，就回報 tech-architect 重判。

**須 CEO 決定的事**：沒有。
