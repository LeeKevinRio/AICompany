# 真實資料管線驗收一鍵檔設計提案

- 審查者：devops-sre
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

設計提案，沒寫程式、沒 commit、沒讀 `.env`、沒碰任何 `data/*.db`、沒在真實資料上跑任何東西。以下 harness 與 ADR 的細節，都來自 worktree head `9f45cb2` 與 ADR-0030 原文。

**可行，但 coordinator 的五步要改三處。**

1. **「SQLite backup API 複製主 DB」改成沿用 r2 的做法：不開啟原檔，只做位元組複製。**
   - 複製 `stock-desk.db`、`-wal`、`-shm` 三個檔，前後逐檔比雜湊。
   - 理由：backup API 必須開一條連線到主 DB。WAL 模式下，最後一條可寫連線關閉時會 checkpoint，那就是寫入主 DB。
   - 用 `mode=ro` 可避開，但仍比「只讀位元組」弱。D-7 沒有指定複製方式，CG-3 才指定 backup API，而 CG-3 是登記檔的備份，不是這一步。
2. **「唯讀取 ^TWII」的做法**：由一鍵檔外層包裝，以純 `sqlite3`、`mode=ro`、只 `SELECT`，讀**複本**的 `price_bars_cache`，轉成 `PriceBar` 清單後以參數注入 `run_acceptance`。
   - harness 本體不碰 `price_bars_cache`，它的 AST 測試維持全綠。
   - 包裝檔也不 import `app.data.cache` 或 `app.services`。`PriceBarCache._connect` 會 `CREATE TABLE IF NOT EXISTS` 與設 WAL，等於會在複本上寫入。
3. **「刪除完整輸出」改成「完整輸出根本不寫檔」，只刪暫存帳。**
   - `result.output` 只在記憶體算 `output_sha256`。
   - 暫存帳是檔案，無法避免，因為 `ForecastStore` 要檔案路徑。它在 `finally` 刪除，並在下次啟動時掃除殘留。
   - 補充五第 5 點提到「只寫進暫存檔的完整輸出」，這是允許寫，不是要求寫。不寫更符合 CEO #149，需 TA 確認（T-6）。

另有一個**未在你列出的問題**：`uv.lock` 沒有 `eol=lf`，而 `runtime_json.lockfile_sha256` 是對原始位元組取雜湊。CRLF 風險實際落在這個檔，不在 `code_digest`（見各部門回報第 5 點）。

---

## 各部門回報

### 方案總覽（devops-sre）

新增兩個檔：
- `apps/stock-desk/pipeline-acceptance.bat`：薄啟動器，仿 `r2-probe.bat`，`.gitattributes` 已有 `*.bat eol=crlf`。
- `apps/stock-desk/backend/scripts/pipeline_acceptance_real.py`：外層包裝。

指令：`uv run --no-sync python -I -X utf8 scripts\pipeline_acceptance_real.py`，工作目錄為 backend。bat 先 `set "UV_ENV_FILE="`，避免 `.env` 被載進程序環境。

流程：
1. 顯示說明，CEO 關掉 backend、scheduler、frontend 三個視窗後按 Enter。
2. 前置檢查，任一不成立就 STOP：
   - 環境變數 `STOCK_DESK_DB_PATH` 沒設。
   - `apps/stock-desk/.env` 沒有這個鍵（r2 的「只找鍵名」做法）。
   - 預設位置有主 DB。
   - port 8000 沒有監聽。
   - 工作目錄不在 git 工作樹內。
   - git 工作樹乾淨：`app/`、`tests/`、`scripts/`、`uv.lock`。
   - `HEAD` 可由 `origin/product/stock-desk` 到達。
   - CRLF 檢查。
   - `import tests.forecast_pipeline_harness` 成功。失敗就 STOP 並提示先跑 `dev-up.bat`，不印例外內容。
3. 複製：把三檔複製到 `%USERPROFILE%\stock-desk-pipeline-acceptance\<時間戳>\copy\stock-desk.db`，逐檔比雜湊（r2 的 `compare_copy`）。複本沿用 `stock-desk.db` 這個檔名，這是縱深防禦：萬一被誤當成 ledger 傳給 harness，`refuse_production` 會因檔名直接拒絕。
4. 取數：`read_twii_bars(copy)` 讀複本的 `^TWII`、market `TW`，轉成 `PriceBar` 放進記憶體，立刻刪除複本。含持股與現金的完整複本只存在數秒。
5. 守門反例測試（不開任何檔）：對 `<backend>/data/stock-desk.db` 呼叫 `refuse_production` 必須拋 `HarnessRefused`；對 `<work>/p0/pipeline-acceptance.db` 必須放行。成立才輸出 `refusal_guard=ok`。
6. P-0、P-1 各自在獨立子資料夾跑一次 `run_acceptance`，參數如下：
   - `backend_dir` 為真實 backend。
   - `env` 只傳 `{STOCK_DESK_DB_PATH}` 子集。
   - `cwd` 為真實 cwd。
   - `wall_clock` 用預設實際時鐘。
   - `definition` 用 `tests.dirdef_helpers.dirdef_v1_0()`（見 T-5）。
   - 每次跑完立刻 `render_summary`，在 `finally` 刪掉該子資料夾。
7. 回貼內容經白名單過濾後寫 `paste-back.txt`（`utf-8-sig`，Notepad 才不會亂碼），自動開 Notepad。主控台只印同樣的白名單行，且一律 ASCII 轉義，同 r2。
8. 全程 `logging.disable(CRITICAL)`。所有例外只印固定句 `ERROR: unexpected failure`，不印例外文字與 traceback，因為 traceback 可能夾帶值或路徑。

### 第 1 題：bars 由誰、怎麼取

- **來源**：外層包裝讀複本，以參數注入。`price_bars_cache` 欄位為 `trade_date, open, high, low, close, volume, currency, source, as_of, fetched_at`。包裝只取前八欄，丟棄資料庫裡真實的 `as_of` 與 `fetched_at`。
- **注入值**：`as_of` 一律設為該 session 當日 20:00 Asia/Taipei，與 `synthetic_series` 的 `stamp_hour=20` 完全同一規則。harness 的 loader 已經只回傳 `as_of <= store 時鐘` 的 bar，`SyntheticAnswer.reason = synthetic_timestamps` 也是現成的。
- **讀取範圍**：整條 `^TWII` 序列，不設起點，以滿足 D-5 的「至少涵蓋 T 前 500 個日曆日」。
- **fail-closed STOP**（固定句，不回貼任何值）：
  - 沒有 `^TWII` 列。
  - 任何列無法解析。
  - 任何列的 `source` 以 `demo` 開頭（demo seeder 的週間網格不是真實序列）。
  - 深度不足 N_SNAPSHOT + 21（= 336 根）。這只輸出布林 `cache_depth=sufficient|short`，不輸出根數。
- **D-7 對真實資料一次的建議寫法**（寫成補充六，由 TA 定稿）：「真實資料的一次，取數由 harness 外層從主 DB 的位元組複本讀 `price_bars_cache` 的 `^TWII` 列，只 SELECT；`as_of`、`fetched_at` 由注入值取代，標 `synthetic_timestamps`；主 DB 從不被開啟，harness 本體維持不讀快取、不 import `app.services`。」

需 TA 裁示的具體問題：T-1、T-2、T-5，見下方清單。

### 第 2 題：複本位置、守門、輸出與刪除、Windows 注意事項

**`refuse_production` 放行複本、擋下主 DB 的機制**：它只比對 harness 的 **ledger 路徑**。複本從頭到尾不會傳給它，所以不存在「放行複本」的問題。實際保證分三層：
1. ledger 一律在 `<work>\p0\` 或 `<work>\p1\`，檔名 `pipeline-acceptance.db`。路徑不在 `<backend>/data/`，也不叫 `stock-desk.db`，所以放行。
2. 上面第 5 步的守門反例測試，證明主 DB 路徑被擋、ledger 路徑被放行。
3. 測試用的 `sqlite3.connect` 與 `open` 監聽：e2e 測試以合成的假主 DB 驗證，原檔只被 `open(..., "rb")` 讀取（複製與雜湊），從未被 `sqlite3.connect`；所有 `connect` 的目標集合包含於 {複本, 兩個 ledger}。

**完整輸出與暫存帳**：
- 完整輸出不寫檔，只留記憶體，用來產生 `output_sha256`。
- 暫存帳在 `finally` 以 `shutil.rmtree` 刪除。
- 啟動時掃除殘留：只掃 `%USERPROFILE%\stock-desk-pipeline-acceptance\` 底下、檔名符合 `\d{8}-\d{6}` 的子資料夾內的 `copy\`、`p0\`、`p1\`。
- 結束時資料夾只剩 `paste-back.txt`，並輸出 `cleanup=ok|FAILED`。

**Windows 注意事項**：
- 工作目錄放 `Path.home()`，不放桌面或「文件」，避開 OneDrive 已知資料夾重導與同步鎖檔。
- 刪除 SQLite 檔可能遇到 `PermissionError`（WinError 32：未關閉的連線或防毒掃描）。做法：
  - 所有連線用 `closing()`。
  - 刪除前 `gc.collect()`。
  - 重試 5 次，每次間隔 0.5 秒。
  - 仍失敗就輸出 `cleanup=FAILED` 並保留資料夾，不算管線失敗。
  - 刪除也要涵蓋 `-wal`、`-shm`、`-journal`。
- 路徑只用 `pathlib`。`mode=ro` 的 URI 用 `Path.resolve().as_uri()`，同 r2。
- 主控台只印 ASCII（cmd.exe 編碼不可靠），中文只寫進 `utf-8-sig` 的檔案。
- 檔案刪除後不進資源回收筒，這是好事。
- 這支 `.bat` 與 r2 一樣沒有 Windows 實測，所以 STOP 訊息都設計成無害、不依賴任何副作用，視窗不會自動關閉。

### 第 3 題：CEO 的 scheduler 與 backend 要不要停

**要停，沿用 r2 的做法。**
- 理由：複本是三檔位元組複製。服務在寫入時複製會得到不一致的 WAL。前後雜湊比對（`SAME` / `DIFFERENT`）能抓到複製期間的變動，但抓不到「scheduler 閒置但持有 WAL」這種正常狀態，所以仍要求停。scheduler 沒有 port，只能靠 CEO 關視窗加雜湊比對。
- 檢查項目全沿用 r2：port 8000、`STOCK_DESK_DB_PATH`（環境與 `.env` 鍵名）、預設位置有主 DB。
- 若 backend 或 scheduler 以 NSSM 或工作排程器常駐，同 r2：先不要跑，告訴 coordinator。
- 複本取得並比對完成後，說明文件即可告知 CEO「可以重啟服務」，之後 harness 完全不碰主 DB，只用記憶體中的 bars 與自己的 ledger。
- 這一步不依賴也不影響接線 PR（`forecast_record` job 尚未註冊）。

### 第 4 題：回貼欄位規格

固定開頭兩行（逐字，取自 `HEADER` 常數）：D-7 第 5 點的「管線驗收：使用歷史資料……規則未經驗證。」與「本次使用佔位規則，輸出不是任何將登記規則的判斷。」

| 欄位 | 型別與值域 | 為何不含標籤或對照 |
|---|---|---|
| `pipeline_acceptance_real version=1` | 固定字面 | 常數 |
| `script_sha256_lf=` | 64 位 hex，包裝檔 LF 正規化後的雜湊 | 對原始碼取雜湊 |
| `harness_sha256_lf=` | 64 位 hex，`tests/forecast_pipeline_harness.py` 同法 | 同上 |
| `git_head=` | 40 位 hex | commit id |
| `git_clean=yes` | 固定，不乾淨就 STOP，不輸出 `no` | 常數 |
| `core_autocrlf=` | 封閉集 `false`/`unset`/`input`/`true`/`other` | 設定值，非資料 |
| `eol_check=ok` | 固定 | STOP 時改印 STOP 句 |
| `code_digest=`、`lockfile_sha256=` | 64 位 hex，取自 `recorder.LOADED` | 對原始碼與鎖檔取雜湊 |
| `definition_sha256=`、`definition_logic_sha256=` | 64 位 hex | 對定義物件取雜湊，與日後 M-4 比對 |
| `db_location=default`、`port_8000_listening=no` | 固定 | 常數 |
| `copy_check=SAME`（三檔各一行，同 r2） | 封閉集 | 位元組比對結果 |
| `refusal_guard=ok` | 固定 | 守門反例測試結果 |
| `cache_depth=sufficient` | 封閉集，不足則 STOP | 布林，不輸出根數 |
| `bars_sources=` | 逗號分隔的 `[a-z0-9_]{1,32}` | 資料源名稱，如 `yahoo`；不含價格 |
| `bars_sha256=` | 64 位 hex，注入 bars 的 canonical 序列化雜湊 | 輸入識別；^TWII 是公開指數資料 |
| 每個規則集一組（取自 `render_summary`，逐行過白名單） | 見下 | 見下 |
| `acceptance_result=PASS\|FAIL` | 兩個規則集都通過才 PASS | 由兩個 `passed` 布林導出 |
| `cleanup=ok\|FAILED` | 封閉集 | 檔案操作結果 |
| `summary_lines_dropped=` | 整數 | 被白名單丟掉的 summary 行數，正常為 0，無關內容 |
| `done_at_utc=` | ISO UTC 時間 | 時鐘 |

每個規則集的 `render_summary` 行（白名單 `fullmatch`）：
- `管線驗收 (P-0|P-1)：(通過|失敗)`
- `視窗定案 session 數：21`。這個值按建構恆為 21，因為 `acceptance_window` 不足 21 就拋 `HarnessRefused`，所以不構成 n。若 TA 嫌它像計數可刪。
- `執行次數：` 後接 `<outcome>=<n>`，outcome 屬 `RunOutcome` 封閉集。D-4 第 5 點明列的執行狀態。
- `失敗種類：(無|kind(，kind)*)`，kind 屬 `FailureKind` 的九個字面值。不含 `where`。
- `暫存帳 sha256：<64 hex>`、`輸出 sha256：<64 hex>`。

**逐項證明不含標籤或對照，分四層**：
1. **來源限制**：每個欄位只由 `RunResult.outcome`（列舉）、`Failure.kind`（`Literal`）、`passed`（布林）、雜湊、固定字面、UTC 時鐘、封閉集的環境檢查結果產生。包裝檔不讀 `result.output`、store 的列、`compared`、`matches` 與 `Failure.where`。
2. **白名單過濾**：所有輸出行必須 `fullmatch` 某個固定樣式，否則丟棄並計入 `summary_lines_dropped`。未來若有人在 `render_summary` 加了筆數，會被丟掉而非洩漏。
3. **沒有例外文字、沒有 `where`**：`where` 含 `claim_id` 與 T，不在 #149 的允許輸出清單中，預設不給（見 T-3）。`vacuous_equality` 的 `where` 只有規則集加 horizon，是否放行也在 T-3。
4. **毒藥測試**：用已知標籤的 fixture 跑，斷言回貼文字不含 `偏多`、`偏空`、`震盪`、`insufficient`、`unavailable`、`bullish`、`bearish`、`range`、`符合`、`不一致`、`B1`、`B2`、`B6`、`B8`，且不含 `result.output` 的任一行。再用兩組不同標籤分佈的序列跑，斷言回貼文字除了雜湊與 `執行次數` 的 outcome 計數外結構逐行相同。

雜湊的資訊洩漏：`輸出 sha256` 涵蓋含時間戳的完整輸出，要反推標籤必須窮舉 3 的 42 次方種組合加精確到秒的時間，實務上不可行；ADR 與 CEO 指示都明列「雜湊」可輸出。

### 第 5 題：CRLF

**先修正風險位置**：`code_digest` 已經 CRLF 正規化（`canonical.py` 的 `normalised_source`：`\r\n` 與 `\r` 換成 `\n`），所以 `app/**/*.py` 不受 autocrlf 影響。harness 用的佔位規則位元組是程式內樣板，不讀 YAML。真正會因 autocrlf 變動的，是 `runtime_info` 對 `uv.lock` **原始位元組**取的 `lockfile_sha256`。補充四要求的 YAML 雜湊對不上，是接下來登記檔（R-2）才會遇到。所以做法要寫成通用的，登記檔重用。

做法（包裝檔內 `check_pinned_eol(paths)`，不修改任何東西）：
1. 讀 `git config --get core.autocrlf` 與 `core.eol`，只當診斷輸出（`core_autocrlf=`），不當判斷依據，因為 `.gitattributes` 的 `eol=` 優先於它。
2. 判斷看效果：對釘住的檔案集合，比對**工作樹原始位元組的 sha256**與 `git cat-file blob HEAD:<path>` 的 sha256。這次釘住 `apps/stock-desk/backend/uv.lock`；登記檔再加 YAML 規則檔、定義檔與兩份文件。
3. 另跑 `git ls-files --eol -- <paths>`，任何一行 `w/crlf` 或 `w/mixed` 但 `i/lf`，也判失敗。這是第二證據，用來給出較明確的訊息。
4. 失敗輸出：`STOP: line endings differ from the repository for a pinned file (git core.autocrlf is probably true). Tell the coordinator; do not change anything yourself.` 不印檔名以外的值。
5. 補救步驟由 coordinator 提供，一鍵檔不改 git 設定：
   - 暫時：`git config core.autocrlf false`（repo-local），再對該已追蹤且乾淨的檔案 `git checkout HEAD -- <path>`。
   - 根治：本 PR 在 `.gitattributes` 加 `uv.lock text eol=lf`；補充四 M-7 的 YAML 與文件屬性在 CG-2 PR。屬性優先於 `core.autocrlf`，之後 CEO 的設定就無關了。

另一個可選的硬化（T-7）：把 `runtime_info` 的 `lockfile_sha256` 也改走 `normalised_source`，讓它與 `code_digest` 一致。屬 `app/forecast/recorder.py`，歸 dev-lead，需 TA 同意。接線前沒有正式紀錄，現在改幾乎免費，接線後會牽動補充三的 `runtime_json` 比對。

### 第 6 題：`tests/` 的執行與打包

- **打包**：`pyproject.toml` 的 `[tool.hatch.build.targets.wheel] packages = ["app"]`，所以 wheel 不含 `tests/`。`Dockerfile` 只 `COPY app ./app`，所以正式映像也沒有 `tests/`。因此正式程式路徑物理上拿不到 harness，這與 K-11「正式路徑不 import harness」一致。代價是一鍵檔只能在原始碼樹執行，這正是想要的。
- **執行**：`uv run --no-sync python -I -X utf8 scripts\pipeline_acceptance_real.py`，cwd 為 backend。`dev-up.bat` 已經 `uv sync --locked`（含 dev 群組），環境就緒。
  - `-I` 不會把 cwd 與腳本目錄放進 `sys.path`，所以 `import tests...` 不能靠它。包裝檔在檔頭用 `Path(__file__).resolve().parents[1]` 算出 backend 目錄，先確認 `app/__init__.py` 存在，再 `sys.path.insert(0, backend)`。這個位置優先於 site-packages，避免被同名的 `tests` 套件搶走。
  - `--no-sync` 不會在 CEO 機器上變更環境，也不需要網路。
  - `tests.outlook_helpers` 與 `tests.dirdef_helpers` 只 import `app` 與 `yaml`，沒有 pytest，所以不依賴 dev 群組也能跑。
- **import 副作用**：`app.forecast.recorder` 模組載入時會讀 `uv.lock` 並呼叫 `git rev-parse`。唯讀，沒有寫入。e2e 測試以監聽 `sqlite3.connect` 確認 import 階段不開任何 DB。

### 第 7 題：分工與 commit 預估

建議單一 PR，分支 `feat/nm5-pipeline-acceptance-oneclick`，從已含第五批的 `product/stock-desk` 長出。補充四 M-1 要求第五批先合併。預估 **5 個 commit**：

**devops-sre（3 個）**
1. `feat:` `pipeline-acceptance.bat` 與 `pipeline_acceptance_real.py` 的外層流程：前置檢查、三檔複製與雜湊、工作目錄與清理、白名單、`paste-back.txt`，以及這些部分的測試（毒藥、STOP 每條、清理、白名單丟棄）。
2. `ci:` eol 檢查通用函式 `check_pinned_eol` 與測試，`.gitattributes` 加 `uv.lock text eol=lf`。
3. `docs:` `work/dispatch/2026-11-xx-真實資料管線驗收操作說明-CEO.md`，仿 r2 說明：三步驟、STOP 對照表、回貼欄位意義、不得截整個視窗。

**dev-lead（2 個）**
4. `feat:` `read_twii_bars(copy_path) -> list[PriceBar]`：`sqlite3` `mode=ro` 加 SELECT，注入 `as_of`，STOP 條件（無列、列無法解析、demo 來源、深度不足），並附 AST 測試：只 import 允許的模組，沒有 `INSERT`、`UPDATE`、`DELETE`、`CREATE`、`PRAGMA`（`query_only` 除外），沒有 `app.data.cache`、`app.services`。
5. `test:` 確認 `render_summary` 的每一行都通過包裝檔的白名單（`summary_lines_dropped=0`）。若 TA 同意 T-7，加 `lockfile_sha256` 的正規化。

**流程**：設定變更經 qa-reviewer 審查（含 Codex 第二意見）後才 commit；CEO 雙擊執行，執行時機由 coordinator 通知；不涉及對外發佈。

---

## 驗證

這份是設計，沒有執行。以下是我讀過的依據，可供 qa 核對：

- ADR-0030 D-4 第 3、5 點、D-7 第 1～7 點、K-10、K-11、補充二第 1 點、補充四第 4～6 點、補充五第 3、5 點與附記，全文讀過。
- `forecast_pipeline_harness.py` 全文：
  - `refuse_production` 只比對 ledger 路徑，委派 `claims.production_path_refusal`（檔名 `stock-desk.db`、主 DB、同資料夾、`STOCK_DESK_DB_PATH`）。
  - `run_acceptance` 的 `backend_dir`、`env`、`cwd` 是 keyword-only 且無預設值。
  - `render_summary` 只列通過與失敗、失敗種類、各 outcome 次數與雜湊，符合 C5-2。
  - 補充五第 3 點 (a)～(c) 的三項防護已在 head `9f45cb2` 落地：`vacuous_failures`、`record_failures`、`MISSING_CODES`。
  - 第五批測試 `test_the_harness_reads_no_price_cache_and_opens_only_its_own_ledger` 以 AST 禁止的名稱與模組，就是你問題 1 提到的那組。
- `code_digest` 的 CRLF 正規化（`canonical.py`）、`runtime_info` 對 `uv.lock` 取原始位元組雜湊、`recorder.LOADED` 在 import 時取值，皆核對原始碼。
- `r2-probe.bat`、`r2_first_run.py`、操作說明：port 檢查、`.env` 鍵名掃描、三檔複製與比對、白名單過濾、Notepad 開檔皆為現成前例。
- 專案設定：wheel 只含 `app`，Dockerfile 只複製 `app`，`.gitattributes` 目前只有 `*.bat`、`*.sh`，`dev-up.bat` 以 `uv sync --locked` 建環境。

**未驗證**：真實快取內 `^TWII` 實際是否存在、`source` 值是什麼、深度是否 ≥ 336 根；Windows 上的 `.bat`、檔案鎖與刪除行為；`price_bars_cache` 裡 `^TWII` 的 `market` 欄位是不是 `TW`（我依 `MARKET_BENCHMARK["TW"]` 推得，未在資料上確認）。這些只能由 CEO 第一次執行時暴露，所以所有失敗路徑都設計成固定 STOP 句。

---

## 下一步

### 與 ADR 的對照表

| 項目 | coordinator 方案 | 本提案 | 與 ADR 的關係 |
|---|---|---|---|
| 複製方式 | backup API | 位元組複製三檔加雜湊比對 | D-7 未指定；backup API 屬 CG-3 登記檔，非此步。不開原檔，更保守。 |
| 取數 | 唯讀取 `^TWII` | 包裝讀複本，注入 bars | 合 D-7 第 2、6 點與 K-11；harness 本體 AST 守門不受影響。**需 TA 確認（T-1）。** |
| `fetched_at` | 未提 | 注入 20:00 Taipei，標 `synthetic_timestamps` | 合 D-7 第 6 點。具體時刻需 TA 確認（T-2）。 |
| 跑 P-0、P-1 | 有 | 各自獨立資料夾跑一次 | 合 D-7 第 4 點與補充五第 3 點。 |
| 只印 summary | 有 | `render_summary` 經白名單，不含 `where` | 合 D-4 第 3、5 點、補充五第 5 點、C5-1、C5-2、CEO #149。`where` 需 TA 確認（T-3）。 |
| 刪除完整輸出 | 刪 | 完整輸出不寫檔，只刪暫存帳 | 補充五第 5 點只說「只寫進暫存檔」，沒要求保留。更嚴，需確認（T-6）。 |
| 登記前通過 | 未提 | 回貼 `git_head`、`code_digest`、定義雜湊作證據 | 補充四第 6 點與 M-1。通過證據與 CG-2 PR 的關係需 TA 定（T-4）。 |
| 拒絕主 DB | 未提 | 守門反例測試加複本沿用 `stock-desk.db` 檔名 | 合 D-7 第 2 點、K-11。 |
| CRLF | 未提 | 比對原始位元組雜湊與 `git ls-files --eol`，只報錯不修改 | 補充四 M-7、R-2 的前置。 |
| 停服務 | 未提 | 要停，沿用 r2 | 不影響 ADR 任何條款。 |

### 需 TA 裁示的問題清單

- **T-1（取數位置）**：D-7 第 2、6 點的「取數」，是否允許由 harness 外層的 `scripts/` 包裝，從主 DB 的位元組複本讀 `price_bars_cache` 的 `^TWII` 列（只 SELECT），再以參數注入 `run_acceptance`？harness 本體不變。是否接受以此做 D-7 的「真實資料那一次」？
- **T-2（時間戳）**：注入規則是否定為「每根 bar 的 `as_of` 與 `fetched_at` 一律取該 session 當日 20:00 Asia/Taipei，丟棄快取的真實值」，與 `synthetic_series` 同規則？副作用：真實 `as_of` 早於 15:00 的 bar（正式路徑會判未定案）在 harness 中視為定案，這與 D-7 第 6 點「定案只用合成 fixture 驗證」一致。
- **T-3（失敗定位）**：回貼是否一律只有失敗種類、不含 `Failure.where`（`claim_id` 與 T）？若是，失敗後 dev-lead 以什麼路徑診斷？我的建議：用合成 fixture 重現該 kind，不看真實資料；另可放行 `vacuous_equality` 的 `where`（只有規則集加 horizon，不含 T 與標籤）。
- **T-4（通過證據的有效期）**：CG-2 登記 PR 一定會改 `app/forecast/definitions.py`（登記表）與規則檔，所以 `code_digest` 與 harness 通過時不同。「harness 通過」要如何綁定？建議：記錄通過時的 `git_head` 與 `code_digest`，CG-2 PR 必須證明 `git diff <通過時 head>..<CG-2 head> -- app/forecast app/outlook app/dirdef` 只有 M-4、M-5 的登記表與規則檔新增，其餘為空。是否同意，或另定？
- **T-5（定義物件）**：真實資料這次用 `tests.dirdef_helpers.dirdef_v1_0()`（G7 值的測試替身），不是已登記的 `dirdef-v1.0`（尚未登記）。是否接受？回貼印出 `definition_sha256` 與 `definition_logic_sha256`，以便日後和 M-4 的雜湊比對，相等才算同一定義。
- **T-6（完整輸出）**：確認完整輸出不寫檔（比補充五第 5 點的「暫存檔」更嚴），只保留 `output_sha256`；暫存帳執行完即刪。
- **T-7（lockfile 雜湊）**：是否同意 dev-lead 把 `runtime_info` 的 `lockfile_sha256` 改走 `normalised_source`，與 `code_digest` 一致？這屬 `app/forecast/recorder.py`，不改會讓 CEO 機器的 autocrlf 造成 `runtime_json` 與 CI 不同；接線前改成本最低。

### 其他待辦

- coordinator：決定是否接受「完整輸出不寫檔」與「要停服務」，再通知 CEO 執行時機。CEO 執行前由 coordinator 提供 STOP 對照表。
- dev-lead：第五批合併後，開 `feat/nm5-pipeline-acceptance-oneclick` 並完成第 4、5 個 commit；devops-sre 完成第 1～3 個 commit，送 qa-reviewer。
- devops-sre：承接補充五第 1 點 (h) 的主機停機偵測（心跳，D-10），與本一鍵檔分開，不在本 PR。

### 相關檔案

- `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- `/home/user/AICompany/apps/stock-desk/r2-probe.bat`
- `/home/user/AICompany/apps/stock-desk/backend/scripts/r2_first_run.py`
- `/home/user/AICompany/work/dispatch/2026-11-13-R2探測操作說明-CEO.md`
- `/home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/forecast_pipeline_harness.py`
- `/home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/forecast/claims.py`
- `/home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/forecast/recorder.py`
- `/home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/forecast/canonical.py`
- `/home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/pyproject.toml`
- `/home/user/AICompany/.gitattributes`
