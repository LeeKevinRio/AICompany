# 對沖 PRD 三題回覆（data-engineer）

- 日期：2026-11-19｜作者：data-engineer｜依據：`work/prd/2026-11-16-對沖三段規劃.md` 第 145～149 行；風控條件 RC-168～RC-178（`work/reviews/2026-11-16-對沖規劃PRDv0.3重審與C1選B書面確認-風控.md`）
- 本次沒有改任何程式與 PRD；沒有讀 `.env` 值；沒有碰 `apps/stock-desk/backend/data/*.db`（不讀、不開、不 stat、不算雜湊）。
- 標記：【已證實】= 讀到程式碼行號或實際取得回應；【推論】= 由程式碼或名稱推得，未實測；【未查證】= 查不到或連不上，數字不填。
- 查證日期一律為 2026-11-19。

---

## 1. 本次結論

### 1.1 會影響 CEO 這次驗收與正式登記的發現（放最前面）

**發現 A：PRD 第 147 行的前提與程式不符。`^TWII` 開盤值為 null 時，canonical 不會「拒收整份快照」，而是這根 bar 在更上游就被靜默丟掉，canonical 根本看不到。**【已證實】

- `canonical_price(None)` 確實會丟 `CanonicalFormError`（`app/forecast/canonical.py:88-102`，測試 `tests/test_forecast_canonical.py:125-130`）。但 null 到不了那裡：
  - `^TWII` 唯一來源是 yfinance adapter。cache 路徑的逐列解析 `_parse_chart_row`，只要 open/high/low/close/volume 任一為 None，整列回傳 None 跳過（`app/data/providers/yfinance.py:301-307`），沒有 log、沒有計數，連**有效的收盤價也一起丟掉**。
  - 快取表 `price_bars_cache` 的 open 欄是 `TEXT NOT NULL`（`app/data/cache.py:43`），寫入時用 `str(bar.open)`（`cache.py:200`）；`PriceBar.open` 型別是 `Decimal`（`app/data/interface.py:61`）。所以 DB 裡不會有 null 的開盤值。
- 結果：被丟的 session 在快照裡直接缺席。`snapshot_view` 只檢查嚴格遞增、不檢查連續（`app/outlook/inputs.py:174-176、270-290`），`app/outlook` 內 grep 不到對交易日曆的連續性檢查，`missing` 的代碼只有 E-BARS-SHORT、E-PRICE-UNUSABLE 等（`app/outlook/engine.py:370-420`），沒有「缺一天」的代碼。所以缺一天時，均線與報酬的 lag 會悄悄跨過缺口，**不報錯、不標 missing、不記 dropped_rows**（`DropReason` 只有 `"not_final"`，`inputs.py:62`）。
- 風險性質因此是「靜默失真」，不是「拒收」。比 PRD 設想的更不容易被發現。

**發現 B：開盤值為 0 會一路通過所有現有防線。**【已證實】

- adapter 的 `_to_price(0)` 得 `Decimal("0")`，不檢查（`yfinance.py:283-284、313`）；cache 存 `"0"`；`canonical_price` 對 0 回 `"0"`（`canonical.py:105-106`，測試 `test_forecast_canonical.py:115` 只涵蓋 `-0.00`）。
- 唯一會抓「開盤 0」的是 `quality._check_ohlc_consistency`（`low > open` 會標 `OHLC_INVALID`，`app/data/quality.py:167-189`），但 `check_price_bars` 在 `app/` 內沒有任何呼叫者（grep 結果只有 quality.py 自己與 tests）。`price_guard.usable_price` 也只判收盤價（`app/data/price_guard.py` 檔頭）。
- 預測核心只讀收盤價（`inputs.py:262-267`、`engine.py` 內 grep 無 `.open`），所以**開盤 0 不會影響目前的記錄本身**，只會被原樣寫進快照與 content hash。它會在第二段（T+1 開盤進場）才造成問題：TA 與 PRD 只定義「缺日」為 `open_unusable`，沒有定義「有值但為 0 或不合理」。

**發現 C：開盤值為 NaN/Infinity 才會真的讓整次記錄失敗。**【已證實（程式路徑）／發生機率屬推論】

- yfinance 回應以 `parse_float=Decimal` 解析（`yfinance.py:667`），JSON 的 `NaN` 字面值會變成非有限 `Decimal`，adapter 當成正常 bar（註解寫明，`yfinance.py:350-352`）。進快照時 `canonical_price` 丟 `CanonicalFormError`（`canonical.py:103-104`），經 `store._series_row`（`app/forecast/store.py:322-323`）上拋；`record_forecasts` 以 `except Exception` 收下，該次 run 記為 `outcome="error"`、`error_class="CanonicalFormError"`（`recorder.py:306-322`），不寫任何紀錄，直到該 bar 滑出快照視窗。這是 fail-closed 且可見的，但 Yahoo 是否真的會回 NaN 未實測。

**發現 D：CEO 即將跑的真實資料管線驗收，不會因開盤值為 0 而停，回貼內容也看不出來。**【已證實（只描述程式行為）】細節見 1.3 第 5 點。

### 1.2 三題一句話結論

| 題 | 結論 | 證據等級 |
|---|---|---|
| 1 | 無法證實 CEO 資料庫裡 `^TWII` 開盤值有無 null 或 0（不能看）。程式面：null 會被整列靜默丟棄（缺口、非拒收）、0 會被原樣收下；核心計算不讀開盤值，所以對「現在的記錄」影響小，對第二段與資料完整性有缺口。以官方 TWSE 加權指數日線交叉看，近 34 個月 685 個交易日的開盤值無 null、無 0。 | 程式面已證實；真實資料面未實測 |
| 2 | repo 內的手續費與證交稅是**未查證預設值**（`verified_on=None`）。現行法定費率因官方網站在本環境連不上，**未查證**，數字不填。反向 ETF 的標的指數名稱已從 TWSE 官方 ETF 清單取得（兩種指數）；指數編製方法與期貨轉倉成本未查證。RC-170 歷史值來源找到：TWSE 價格指數（1999-01 起可得）與報酬指數（2003-01 起可得）。 | 部分已證實、部分未查證 |
| 3 | 上櫃（TPEx）有公開、免金鑰的 OpenAPI，含融券借券餘額、可借券賣出股數、標借費率範圍、當沖券差借券費率；上市（TWSE）有每日融券餘額、可借券賣出股數、停券預告，但上市的借券費率沒有找到可用端點。repo 現有 adapter 完全不涵蓋融券與借券。 | 端點與欄位已證實；費率部分未查證 |

### 1.3 第 1 題完整回答

#### 1) 程式面：`^TWII` 日線的路徑與缺值處理【已證實】

來源與路徑：

1. 抓取：`YFinanceAdapter.get_index_daily_bars`（`app/data/providers/yfinance.py:464-512`）。`^TWII` 登記在 `INDEX_SYMBOL_METADATA`（`yfinance.py:149-153`），是唯一的指數來源，狀態一律 `BACKUP`。
2. 服務層：`load_market_benchmark`（`app/services/index.py:359-412`）經 `IndexSeriesService` 取 bar；市場基準 `MARKET_BENCHMARK["TW"]` 為 `^TWII`（`index.py:309-312`）。
3. 落地表：`price_bars_cache`（`app/data/cache.py:38-54`；欄位 symbol、market、trade_date、open…，open 為 `TEXT NOT NULL`）；寫入以 upsert，最新抓取覆蓋舊列（`cache.py:185-225`）。
4. 進核心：`app/outlook/inputs.py::capture_market_snapshot`（`inputs.py:228-246`）→ recorder `_fetch`（`recorder.py:600-612`）→ `store.write_run_records`（`recorder.py:380-398`）→ `canonical_bars`（`store.py:322-323`）。

來源缺值時各路徑的行為：

| 情境 | cache 路徑（recorder／驗收實際用的） | raw 路徑（重放快照用，`yfinance.py:539-622`） |
|---|---|---|
| open 為 null（其餘有值） | 整列略過，無 log 無計數（`yfinance.py:301-307`） | 列入 `null_gap_rows`，不當 bar，但有被回報（`yfinance.py:371-382`） |
| 任一欄 null（含 volume） | 同上，整列含有效收盤一起丟 | 同上，`null_fields` 逐欄列出 |
| open 陣列整個缺或長度不符 | `quote_data.get("open") or []`（`yfinance.py:265`）→ 取值 IndexError 被吞（`yfinance.py:709-713`，僅 debug log）→ 全部列被略過 → 回 `unavailable`（`yfinance.py:500-504`） | 長度不符 → 整次 fail-closed（`yfinance.py:358-359`） |
| open 為 0 | 收下，存 `"0"` | 收下 |
| open 為 NaN/Infinity | 收下為非有限 Decimal | 收下（註解說明留給重放閘門判斷，`yfinance.py:350-352`） |

另外：raw 路徑（含 null_gap 回報）目前在 `app/` 內沒有任何呼叫者——docstring 指名的呼叫者 `app/forecast/replay_checks.py` 在目前的樹裡不存在（`ls app/forecast` 無此檔，`grep fetch_replay_index_snapshot` 無 app 內呼叫者）；`record_forecasts` 在 `app/` 內也沒有呼叫者（尚未接線）。所以「null 有被回報」只在 adapter 的單元測試裡成立，正式記錄路徑用的是會靜默丟列的 cache 路徑。

#### 2) 核心面【已證實】

- `canonical.py`：
  - `canonical_price`（88-110）：`None`、float、bool、非十進位字串、NaN、Infinity 一律丟 `CanonicalFormError`；`0` 與 `-0` 輸出 `"0"`，接受。
  - `canonical_bar`（152-166）：鍵必須恰為 `BAR_KEYS`（含 `open`），缺鍵或多鍵丟錯；`volume` 須為非負 int（137-140，所以 volume=0 合法，指數常見）。
  - `canonical_bars`（169-177）：至少一根、`session_date` 嚴格遞增，否則丟錯。
- PRD 所稱「第 88～102 行」實為 `canonical_price`，行為如上，但如發現 A 所述，null 到不了這裡。
- `app/forecast/inputs.py` 不存在；PRD 提到的快照輸入模組實為 `app/outlook/inputs.py`（ADR-0030 D-1 命名 `inputs.py` 位在 outlook 套件）。該檔對開盤值**沒有任何檢查**，`SnapshotBar.open` 只是 `Decimal`（`inputs.py:84`），僅 `_close_value` 驗收盤型別與 sNaN（`inputs.py:262-267`）。
- recorder：
  - 快照被拒（canonical 丟錯）→ 整次 run 為 `outcome="error"`，`error_class` 為例外類別名（`recorder.py:306-322`）；沒有專屬 missing code，也沒有部分寫入（單一交易，`recorder.py:379-398`）。
  - 缺 bar 或收盤不可用 → 記錄內 `missing`：`E-BARS-SHORT`、`E-PRICE-UNUSABLE`（`engine.py:370-420`），標籤降為 insufficient。這兩個碼只針對**收盤價**，不看開盤。
  - 開盤值為 0 或缺 → recorder 完全不知道。

#### 3) 既有測試與離線 fixture【已證實】

- fixture `tests/fixtures/yfinance_chart_twii.json`：4 列，開盤值為 17910.3、17925.1、17880.55、17902.2，全為正數、無 null；volume 全為 0（指數以 0 表示非缺漏）。fixture 全部是**合成**範例，不是實錄回應（`tests/fixtures/README.md`，該檔明記因 egress policy 無法錄製）。所以沒有任何真實 `^TWII` 開盤值證據在 repo 內。
- null 案例：
  - cache 路徑：`test_parses_fixture_and_skips_null_gap_row`（`tests/test_providers_yfinance.py:38-60`）用 TQQQ fixture（`yfinance_chart_tqqq.json:15`，open 陣列含 null），驗證整列被跳過；**不是 `^TWII`**。
  - raw 路徑：`tests/test_replay_index_snapshot.py:694-731` 有 `^TWII` 的 null_gap 案例（含 `("open","close","volume")` 同缺，715 行）。
- 開盤為 0 的案例：**沒有找到**（針對 open=0 的 grep 無結果）。canonical 測試只涵蓋 `-0.00`（`test_forecast_canonical.py:115`）與拒收 None/NaN/Infinity/float（125-130）。
- 驗收腳本測試 `tests/test_pipeline_acceptance_real_bars.py:212-236`：open 為 `"not-a-number"` 會 `AcceptanceStop("unparseable_row")`；沒有 open=0 或 NaN 案例。
- 契約測試：沒有針對真實 Yahoo 回應的契約測試（無實錄）；`yfinance` adapter 的所有測試都用合成 fixture 或 `httpx.MockTransport`。

#### 4) 直接抓資料【未實測 Yahoo；用官方 TWSE 做了替代交叉核對】

- Yahoo（程式實際使用的來源）：`https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII` 回 `CONNECT tunnel failed, response 403`，**網路不通，未實測**。沒有改任何環境設定。
- 替代：本環境可連 `www.twse.com.tw` 的 `rwd` API。我向 TWSE 官方「發行量加權股價指數歷史資料」（`/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date=YYYYMM01`，欄位：日期、開盤指數、最高指數、最低指數、收盤指數）逐月抓取 36 個月，間隔 1.2 秒；其中 2024-02、2024-09 因 TWSE 回「安全性考量」307 頁（疑似限流）而缺，其餘 34 個月、共 685 個交易日取得（2023-12 至 2026-11）。
  - 結果：開盤欄**沒有空值、非數字或小於等於 0**；前 590 列（29 個月）另檢查了「最低 ≤ 開盤 ≤ 最高」，全部成立；後補的 95 列（5 個月）只檢查了數值為正。
  - 解讀限制：這是官方指數的資料，**不是 Yahoo `^TWII` 的資料**。它只能說明「大盤指數本身在這段期間每天都有正常的開盤指數」，不能證明 Yahoo 回傳的開盤欄沒有 null 或 0。Yahoo 該欄的實況仍【未查證】。
  - 另一個可用的事實：同一端點歷史可回溯到 1999-01（見第 2 題），可作為日後 `^TWII` 開盤值的官方對照源（不需金鑰）。

#### 5) CEO 的真實資料管線驗收遇到開盤值 null 或 0 時的行為【已證實，只描述程式】

腳本：`apps/stock-desk/backend/scripts/pipeline_acceptance_real.py`。它**只讀 DB 複本的 `price_bars_cache`**，不連網（檔頭 25-27 行）。

- 開盤值為 null：DB 裡不會存在（NOT NULL，且 adapter 先丟列）。所以驗收讀到的序列，缺的 session 就是「不在表裡」。腳本只檢查來源是 yfinance、不含 demo、「在 run_date 之前的 session 數」夠不夠（`check_depth`，255-258）；不檢查連續性。深度夠就不會停；不夠則停在 `cache_short`，回貼為 `STOP: the cache copy holds too few TWII sessions before today.`（142 行）。
- 開盤值為 0：`_bar` 轉 `Decimal("0")` 成功（165-181）；`bars_sha256` → `content_sha256` → `canonical_price("0")` 成功（271）；harness 只用收盤價。**不會停**，回貼只會看到 `bars_sha256=...`（雜湊，看不出內容）與 `acceptance_result=PASS`（白名單 388～395 行）。也就是說，回貼的任何一行都不會反映出開盤為 0。
- 開盤值是空字串或不可解析（理論上 DB 不會有）：`Decimal(...)` 丟 `InvalidOperation` → `AcceptanceStop("unparseable_row")`，回貼為 `STOP: a TWII row of the cache copy cannot be read.`（139 行；測試 `test_pipeline_acceptance_real_bars.py:212-236`）。
- 開盤值為 NaN/Infinity（若 Yahoo 曾回 NaN 並被存進快取）：`_bar` 不會擋（`Decimal("NaN")` 合法）；到 `bars_sha256`（271 行，於 843 行呼叫）時 `canonical_price` 丟 `CanonicalFormError`，不是 `AcceptanceStop`，被 `main` 的 `except BaseException` 接住，螢幕只顯示 `ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.`（342、959-961 行），不產生 paste-back 檔、結束碼 1。

#### 6) 結論：風險、防線、缺口

風險有多大：

| 情境 | 對目前記錄本身 | 對第二段紙上對沖 | 發生機率 |
|---|---|---|---|
| open 為 null | 整列靜默消失，lag 悄悄跨缺口，無任何標記（品質風險） | 缺 T+1 bar → 可歸為 `open_unusable`，前提是宣告以「應有交易日 vs 有無 bar」判定，而不是只看欄位 | 未實測（推論：歷史已定案的 bar 少見，但無證據） |
| open 為 0 | 無影響（核心不讀 open）；原樣寫進快照與雜湊 | 若宣告只列「缺日」，0 會被當成真實開盤價算出荒謬報酬 | 未實測（推論：Yahoo 指數資料偶有 0 值屬常見現象，但本次無法證實） |
| open 為 NaN/Inf | 該次 run 失敗（fail-closed、可見） | 同上 | 推論：很低 |

目前的防線：(1) adapter 不補值、不內插（`yfinance.py:106-108` 註）；(2) canonical 拒收非有限、float、缺鍵、未遞增；(3) 快照寫入單一交易，失敗整個 rollback；(4) raw 路徑有 null_gap 回報與 fail-closed（但尚無呼叫者）；(5) 驗收腳本對來源與深度有停止條件。

缺口：(G1) cache 路徑丟列無計數、無 dropped_rows、無 missing 代碼；(G2) 沒有連續性檢查，缺一天不會被發現；(G3) 沒有任何一層對「開盤 ≤ 0」或「開盤不在 [最低, 最高]」做判斷（`check_price_bars` 沒接線）；(G4) 驗收回貼不呈現 open 的品質；(G5) 沒有真實 `^TWII` 開盤值的證據進 repo（fixture 全合成）；(G6) volume 為 null 也會連帶丟整列，與開盤無關但機制相同。

修補建議（只是建議，沒動手；標明時點）：

| # | 建議 | 時點 |
|---|---|---|
| R1 | 第二段事先宣告把 `open_unusable` 定義為「T+1 應有交易日但無 bar，或 open 非有限、≤ 0、不落在該列 [low, high]」，以 `session_calendar` 判定應有的交易日，而不是只看欄位是否缺。量化門檻（若要用）由 quant 決定。 | 登記前可做（不動 `app/`，是宣告內容） |
| R2 | 登記前先做一次性、唯讀的資料體檢：對 DB 複本（由 CEO 或 coordinator 決定是否執行）數 `^TWII` 的 open ≤ 0 或非數字的列數，以及與 TWSE 官方交易日清單比對缺日數；結果只回報「幾列、哪些日期」，不回貼數值。我不能自己做（鐵則不碰 db）。 | 登記前可做（不改 `app/`；若寫成腳本，不得改動已被 pin 的 `pipeline_acceptance_real.py`，且新增檔案要先 commit 並已推到 origin，才不會讓驗收的 `git_dirty`／`head_unpublished` 檢查停下來，建議放在 CEO 這次驗收之後） |
| R3 | 登記後，建立一份官方對照：用 TWSE `MI_5MINS_HIST` 每月核對 `^TWII` 的開盤欄（日期、開盤是否一致或差異多大），作為紙上對沖的對照資料源與 `open_unusable` 判定的外部佐證。檔案放 `scripts/` 或 `work/research/`，不進 `app/`。 | 登記前或後皆可（不動 `app/`） |
| R4 | adapter 的 cache 路徑丟列時要有計數與原因，並傳到 recorder 寫進 `dropped_rows`（`DropReason` 增加如 `null_field`）。這會改 `inputs.py` 與 adapter。 | 接線之後（動 `app/outlook` 與 `app/data`，會改 code_digest 與快照語意，需 TA 出 ADR） |
| R5 | recorder 增加快照連續性檢查（對 session_calendar），缺口記成 missing（新代碼如 `E-BARS-GAP`）。 | 接線之後（動 `app/outlook`，同上） |
| R6 | 在 `inputs.py` 或 canonical 之前接上 `check_price_bars`／對 open 做 ≤ 0 與 [low, high] 檢查，異常標記而非補值。若要加進快照欄位會改 `BAR_KEYS` 與 hash，須 ADR。 | 接線之後 |
| R7 | 驗收腳本回貼增加一行「open 異常列數」。腳本被 pin（`script_sha256_lf`），改了就要重新核准。 | 不建議在這次驗收前做；之後視需要 |

---

## 2. 各部門回報（第 2 題、第 3 題完整回答）

### 2.1 第 2 題：手續費、證交稅、反向 ETF、RC-170 歷史值來源

#### (a) repo 內既有的成本設定【已證實】

| 項目 | 現值 | 位置 | 來源註記 | 查證日期 |
|---|---|---|---|---|
| 台股券商手續費 | 0.001425（買賣皆收） | `app/backtest/costs.py:47` | 檔頭自述為「model's training knowledge」，環境無外網未能對主管機關查證（`costs.py:5-16`）；未區分「法定上限」或「實收折讓後」 | 無（`verified_on=None`，`costs.py:55`） |
| 證交稅（一般股） | 0.003（賣出才收） | `costs.py:48` | 同上 | 無 |
| 證交稅（ETF 類） | 0.001 | `costs.py:49`；ETF 類型集合 `_ETF_LIKE` 含 `etf`、`leveraged_etf`、`futures_etf`（`costs.py:39-40`） | 同上 | 無 |
| 美股券商費、規費 | 0.0、0.0000278 | `costs.py:50-51` | 同上；與本題無關 | 無 |
| 滑價 | 0.0 bps | `costs.py:52` | 預設，非查證值 | 無 |
| 反向 ETF 經理費（年） | 例：0.0113（元大台灣50反1）、0.0120（富邦臺灣加權反1） | `app/leverage/detect.py:101-122` | 註冊表值，來源與日期 repo 內未見註記（`index_mapping.py` 檔頭說明對應表整體 `verified=False`） | 無 |

文件側：多份 work 文件引用同一組數字並自標「未查證」（例：`work/research/2026-10-13-外部交易提示詞-回測與相關性方法論對照.md:79`、`work/stock-desk-族群動能-方法論.md:320`）。2026-10-16 我寫過 CEO 本機代跑的探測指令（`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md:741`），其中已提醒「`0.001425` 是法定上限還是一般實收要寫清楚口徑」；該指令包當時未執行，repo 內沒有看到回填結果。

與本題的差距：

1. 全部是未查證值，沒有查證日期。
2. 缺「反向 ETF 專屬」項目：反向 ETF 是否適用 ETF 稅率、管理費實值、期貨型標的的轉倉成本、保管費等，repo 內沒有設定。
3. 缺「口徑」：手續費是法定上限或實收折讓，第二段需事先宣告用哪一種。
4. 第二段要的 0、1 倍、2 倍敏感度，repo 內沒有對應的設定結構（`CostModel` 只有單一檔位）。

#### (b) 現行費率查證【未查證】

- 證交稅與手續費的現行規定，官方來源（全國法規資料庫、財政部、金管會、證交所、券商公會）在本環境都連不上：`law.moj.gov.tw`、`www.mof.gov.tw`、`www.fsc.gov.tw`、`www.csa.org.tw`、`www.sfb.gov.tw` 皆連線被代理拒絕（000／403）；`www.twse.com.tw` 的靜態說明頁回 307 安全頁，只有 `rwd` 資料 API 與 `www.tpex.org.tw` 可連。兩個可連網站的資料 API 沒有手續費與稅率欄位。
- 因此「ETF 手續費」「證交稅（含反向 ETF 是否同為 ETF 稅率）」現行費率，**數字不填**。待辦：在可連外網的環境（CEO 本機）對以下類型的頁面查證並記錄條文、公告日、查證日：證券交易稅條例（稅率條文）、財政部相關公告（含有無調降或延長的暫行稅率，例如是否有當日沖銷減徵規定）、證交所營業細則或證券商管理規則（手續費上限）、各券商公告（實收與電子下單折讓，口徑不同）、各投信公開說明書（經理費、保管費）。這份清單是方向，不是已查到的內容，不含任何數字。

#### (c) 反向 ETF 與 TAIEX 的差異（只談「追蹤臺灣加權股價指數相關的反向型 ETF」這個類別，不涉個別商品）

已證實（來源：TWSE ETF 清單 `GET https://www.twse.com.tw/rwd/zh/ETF/list?response=json`，2026-11-19 取得；欄位：上市日期、證券代號、證券簡稱、發行人、標的指數）：

- 清單共 245 檔，其中標的指數名稱含「反向」或「反」者 16 檔，涵蓋多個市場（臺灣、中國、日本、美國、印度、商品、債券、匯率）。
- 與臺灣加權相關的反向型：3 檔，分屬**兩種標的指數名稱**：
  1. 「臺灣證券交易所發行量加權股價日報酬反向一倍指數」（1 檔）；
  2. 「臺指反向一倍指數」（2 檔）。
- 這兩種名稱不同，代表同一類別內的標的指數並非同一條；兩者與 TAIEX 報酬的精確關係屬指數編製規則，見下。

推論（僅由名稱與 repo 內既有分析程式推得）：

- 名稱 1 是加權股價指數的「日報酬反向一倍」，每日以前一日收盤重設曝險，所以「N 日累積報酬 ≠ −1 × TAIEX 的 N 日累積報酬」，差異隨波動與持有天數增加（路徑依賴）。這是數學結構，repo 內 `app/leverage/drag.py` 已用同一公式拆解（費用效應、重置效應、殘差）。
- 名稱 2 的「臺指」字樣顯示標的可能建立在臺指期貨而不是現貨加權指數上；若如此，會多出期貨與現貨的基差，以及轉倉（換月）成本，且不含現貨指數的股利概念。**以上由名稱推得，指數編製規則書未取得。**

未查證（編製方法與費用細節）：

- 兩條指數的編製方法、重設時點、融資成本（資金成本）扣減方式、轉倉規則、與 `^TWII` 日報酬的實際追蹤差：指數編製機構網站（臺灣指數公司 `www.taiwanindex.com.tw`）與期交所（`www.taifex.com.tw`）在本環境連不上（403／000）。
- 是否含股利、基金層級追蹤誤差、折溢價、管理費實值：未查證。
- 對 repo 的影響（事實）：`app/leverage/index_mapping.py:256-263` 把其中一檔對映到 `^TWII` 且 `return_basis="unknown"`、`verified=False`；另兩檔「臺指反向一倍指數」不在 `app/leverage` 的註冊表內（grep 無）。所以第二段 (c) 層「標的指數與 TAIEX 差異」目前 repo 內沒有可用的對映資料，需要新資料源（對映表與查證）。這與 PRD 表格「`app/leverage` 可部分沿用」的說法有落差：可沿用的是減損公式，不是資料。

#### (d) RC-170 股利調整敏感度：公開歷史值的來源、可得年限、格式

我只回答來源，不提供常數（常數由 quant 於事先宣告鎖定）。

| 項目 | 價格指數（不含股利） | 報酬指數（含股利再投入） |
|---|---|---|
| 名稱 | 發行量加權股價指數歷史資料 | 發行量加權股價報酬指數 |
| 端點 | `GET https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date=YYYYMM01` | `GET https://www.twse.com.tw/rwd/zh/TAIEX/MFI94U?response=json&date=YYYYMM01` |
| 欄位 | 日期、開盤指數、最高指數、最低指數、收盤指數 | 日期、發行量加權股價報酬指數（只有收盤值） |
| 可得起點（實測） | 1999-01（取得 88/01/05 起的資料；更早月份未探測） | 2003-01（取得 92/01/02 起的資料；2002-12 兩次探測皆回 307，無法區分「無資料」與「限流」，保守以 2003-01 為起點） |
| 最新 | 2026-11-02～2026-11-19 皆有（當日資料已含；公布時間未測） | 同左 |
| 格式 | JSON；一次一個月；`stat`、`title`、`fields`、`data` 陣列；日期為民國年「115/11/02」（早於 100 年者前方有空白，如 ` 92/01/02`）；數值為含千分位逗號的字串 | 同左 |
| 授權 | 本次請求未帶任何金鑰；條款未查證 | 同左 |
| 限制 | 連續請求會被回 307「安全性考量」頁（實測 36 個月連抓時 7 次被擋，放慢到 5～12 秒後多半恢復）；呼叫端要處理非 JSON 回應並做長間隔限速 | 同左 |

說明（推論）：價格指數與報酬指數的差，就是股利對指數的累積貢獻，月別分布可用來看 6～9 月集中的程度；但「報酬指數是否為稅前、再投入的時點與假設」是指數編製規則，未查證，會影響怎麼從兩條序列推出「每日扣除的股利量」。另外個股層面的歷史除權息資料，repo 的 `app/dividends/providers.py` 只涵蓋「預告表」（TWT48U_ALL，未來除權息），沒有歷史完整檔，所以不能用現有 adapter 重建歷史。

### 2.2 第 3 題：融券券源與借券費率的資料來源（第三段用）

#### (a) 已確認的公開來源（2026-11-19 實際取得回應；未帶金鑰；不涉任何帳戶）

上市（TWSE，`www.twse.com.tw/rwd/zh/marginTrading/`）：

| 資料 | 端點 | 觀察到的欄位 | 更新頻率與規模 |
|---|---|---|---|
| 融資融券彙總（個股） | `MI_MARGN?date=YYYYMMDD&selectType=STOCK&response=json` | 融券：賣出、買進、現券償還、前日餘額、今日餘額、次一營業日限額；資券互抵；註記 | 每交易日；2026-11-18 有 1,068 列；回傳為 `tables` 結構 |
| 信用額度總量管制餘額表 | `TWT93U?date=YYYYMMDD&response=json` | 融券欄＋借券賣出欄：前日餘額、當日賣出、當日還券、當日調整、當日餘額、次一營業日可限額；備註 | 每交易日；1,315 列 |
| 當日可借券賣出股數（券源） | `TWT96U?response=json`（回「當日」，標題 115年11月19日） | 證券代號、可借券賣出股數（兩組並排；代號含 HTML 連結需清除） | 每日一份、不帶日期參數時為當日；1,249 列 |
| 停券預告表 | `BFI84U?date=YYYYMMDD&response=json` | 股票代號、名稱、停券起日（最後回補日）、停券迄日、原因 | 隨公告更新；22 列 |

上櫃（TPEx OpenAPI，`https://www.tpex.org.tw/openapi/v1/<name>`，目錄 `https://www.tpex.org.tw/openapi/swagger.json`，共 225 個資料集）：

| 資料集 | 內容 | 規模（2026-11-19） |
|---|---|---|
| `tpex_margin_sbl` | 融券借券賣出餘額；含 `SaleAvailableVolumes`（融券可用）、`AvailableVolumesForSBLShortSale`（可借券賣出股數）、各項日增減 | 935 列 |
| `tpex_mainboard_margin_balance` | 融資融券餘額；含 `ShortSaleBalance`、`ShortSaleQuota`、`ShortSaleUtilizationRate` | 923 列 |
| `tpex_margin_trading_lend` | 融資融券標借（證金標借）；含 `LendingRates`（費率區間字串，如「x.xxxx~x.xxxx」，單位與計算基礎未查證）、得標量、最高可接受費率 | 5 列（當日有標借的標的才有） |
| `tpex_intraday_fee` | 應付現股當日沖銷券差借券費率；含 `LendingVolume`、`LendingFee` | 658 列，資料日期為 2026-11-02，不是每日 |
| `tpex_margin_trading_term` | 暫停融券賣出預告表 | 18 列 |
| `tpex_margin_trading_adjust`、`tpex_margin_trading_margin_used`、`tpex_short_sell` 等 | 調整成數、使用率排行、當日融券與借券賣出成交量值 | 未逐一展開 |

共通特性：

- 格式：JSON；TPEx 為物件陣列（鍵為英文欄名，值皆為字串）；日期為民國年七碼（如 `1151119`）；TWSE 為 `fields`＋`data` 二維陣列、含千分位逗號字串。
- 授權：本次請求沒有使用任何金鑰或登入，也沒有看到金鑰欄位；使用條款、頻率上限未查證。
- 歷史：TPEx 的資料集在 swagger 中沒有日期參數，實測回傳為當日快照；TWSE 的 `MI_MARGN`、`TWT93U`、`BFI84U` 有 `date` 參數，可回補（可回溯多久未測）。要有融券券源與借券費率的長期序列，需自己每日蒐集留存。
- 限流：TWSE 對連續請求會回 307「安全性考量」頁；需長間隔限速與非 JSON 回應處理。TPEx OpenAPI 在本次約 10 次請求中沒有被擋。

#### (b) 找不到或未查證的部分

- **上市股票的借券費率**：沒有找到可用的公開端點。我試過 `TWT72U`、`TWT92U`、`TWT85U`、`TWT94U`、`BFI85U`、`TWT98U`，皆回 307 或非 JSON，這些路徑是猜的，沒有任何證據顯示存在，所以不能當成「確認沒有」，結論是**未查證**。
- 議借（借券人與出借人議定）的費率分布、借券中心的成交行情、證金公司融券費與券商融券利率：**未查證**（官方站未連上或未探測）。`tpex_margin_trading_lend` 的 `LendingRates` 與 `tpex_intraday_fee` 的 `LendingFee` 只涵蓋上櫃特定情境（標借、當沖券差），不能代表一般融券或議借成本。
- TWSE OpenAPI 主機 `openapi.twse.com.tw` 在本環境連不上；repo 的既有註記指出 CEO 本機可連（`app/dividends/providers.py` 檔頭），那裡是否有對應資料集未查證。

#### (c) repo 現有 adapter 的涵蓋度【已證實】

- `app/data/providers/` 內只有 `twse.py`（個股日成交）、`tpex.py`、`twse_snapshot.py`、`finmind.py`、`yfinance.py`、`alpha_vantage.py`、`fx*.py`；`app/` 內對「融券」「借券」「margin」的 grep 無資料來源類的命中。**沒有任何融資融券或借券 adapter，現有 adapter 不涵蓋。**
- 可重用：`RateLimitedClient`（`app/data/http.py`）、`ProviderResult` 的 `as_of`／`source` 模式、離線 fixture 慣例。新增 adapter 要走 `data-source-integration` skill（快取、限流、退避、離線 fixture、降級），且與 PRD RC-173 (c) 一致：個股 claim 通過前不開，所以現在只列資料源，不建議排實作。

---

## 3. 驗證

- 本次沒有跑 repo 測試（任務為查證分析，不改程式）。所有程式面結論來自逐行閱讀與 grep，行號已附。
- 網路實測（唯讀 GET，未帶金鑰，User-Agent 為通用字串）：
  - Yahoo chart `^TWII`：`CONNECT tunnel failed, response 403`，未取得。
  - TWSE `rwd`：`MI_5MINS_HIST`、`MFI94U`、`ETF/list`、`MI_MARGN`、`TWT93U`、`TWT96U`、`BFI84U` 取得 JSON；`TWT72U` 等六個猜測路徑未取得。
  - TPEx OpenAPI：swagger 與六個資料集取得 JSON。
  - 無法連線：`law.moj.gov.tw`、`www.mof.gov.tw`、`www.fsc.gov.tw`、`www.taifex.com.tw`、`www.taiwanindex.com.tw`、`www.csa.org.tw`、`www.tdcc.com.tw`、`openapi.twse.com.tw`、`mops.twse.com.tw`、`www.sitca.org.tw`。
  - TWSE 的 `rwd` 在連續請求時多次回 307 安全頁（我後續放慢到 5～12 秒）。這次探測的請求節奏比 2026-10-16 探測指令包的「每次間隔 6 秒」更密，已觀察到被擋；日後正式的 adapter 必須照限速設計。
- 開盤值掃描只涵蓋 TWSE 官方指數的 34 個月（685 列），缺 2024-02、2024-09；方法、判準與限制見 1.3 第 4 點。
- 沒有碰 `.env`、沒有碰 `data/*.db`、沒有改 `apps/` 與 PRD。暫存檔只放在 scratchpad 與 `/tmp/claude-0`，不在 repo 內。

## 4. 下一步

1. **coordinator／PM**：發現 A（PRD 第 147 行前提不實，null 是靜默丟列而非拒收）需要在 PRD 凍結期間以「待辦」形式記錄，不改本文；並把「開盤為 0」列為與 null 並列的情境。
2. **quant**：第二段事先宣告的 `open_unusable` 請依 R1 擴充（缺 bar、非有限、≤ 0、不在 [low, high]），並指定 `session_calendar` 為「應有 bar」的判準。RC-170 常數請以 2.1(d) 的 TWSE 兩條指數為來源自行鎖定；報酬指數的編製假設（是否稅前、再投入時點）需先查證，查證責任見下。
3. **tech-architect**：R4～R6（cache 路徑丟列的計數與 `dropped_rows` 原因、連續性檢查、開盤檢查）需要 ADR，屬接線之後；請決定是否把 adapter 的 null 丟列行為視為「動核心 app/」（`app/data` 不在 `code_digest` 範圍，但仍在 `app/`）。
4. **CEO（本機）**：(a) 這次驗收可照常跑；腳本對開盤為 0 不會停，也不會在回貼中反映，這是已知缺口，不是這次驗收失敗的原因。(b) 若 CEO 同意，驗收之後可做 R2 的唯讀體檢。(c) 手續費、證交稅、反向 ETF 指數編製規則與費用、上市借券費率，需要在可連外網的環境查證（我可再出一份探測指令包，沿用 2026-10-16 那份的限速與停手設計，但目前沒有排程，未建立）。
5. **devops-sre**：第三段若要蒐集 TPEx／TWSE 融券資料的每日序列，需要排程與監控；目前無需求，不排。
6. **風控**：本報告不含任何對外文案與投資建議；反向 ETF 段落僅描述類別結構與名稱。
7. 未決的資訊缺口總表：現行手續費、證交稅（含反向 ETF 適用性）；兩條反向指數編製規則、期貨轉倉成本、經理費實值；上市借券費率；Yahoo `^TWII` 開盤欄實況；TWSE 報酬指數的編製假設。以上皆【未查證】。
