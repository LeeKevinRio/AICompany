# F-3 快取非正值收盤價查證：CEO 本機執行說明

對應任務單 `work/dispatch/2026-10-06-任務單-單一標的收盤價不合法不中斷整輪警示檢查.md` 的後續 **F-3**：
在 CEO 本機真實快取上查證，日線快取中是否實際存在收盤價不可用（≤ 0、NULL、`NaN`／`Infinity`）的列。
查證結果決定這張修正單**是否擋部署**。

2026-10-07 起同時滿足 F-1 任務單（`work/dispatch/2026-10-07-任務單-F-1-組合估值對不可用收盤價的防護.md`）的風控 required：
「F-3 腳本須涵蓋本機 cache，**最新 bar／較舊 bar／持有／監看分開計數**」。

腳本：`work/research/F-3-快取非正值收盤價查證-腳本/check_nonpositive_close.py`（純讀取、只用 Python 標準庫、不連網）。

## 為什麼要查

修正前，只要**任何一檔**標的在快取裡的**最新一根**日線收盤價 ≤ 0，警示檢查就會在組風險上限時出錯，
排程端整輪只記一行錯誤，**所有使用者、所有標的、所有規則都不評估**，下一輪再崩；手動檢查 `/api/alerts/evaluate` 則回 500。
同一筆壞收盤價也會進組合估值（F-1：`/limits` 可能 500、總曝險與產業佔比可能靜默錯誤通過），
而會被讀到的是**持有或監看標的的最新一根**，所以本腳本把壞列再分成「最新 bar／較舊 bar」與「持有／監看／其他」分開計數。
agent 不得讀 DB，所以「快取裡到底有沒有這種列」只能由 CEO 在本機執行本腳本確認。

## 執行步驟（Windows）

1. 開 PowerShell 或命令提示字元，切到後端目錄：

   ```
   cd <你的 repo 路徑>\apps\stock-desk\backend
   ```

2. 執行腳本，由腳本自己把摘要寫成 UTF-8 檔 `F-3_out.json`。
   `--db` 請指到 App 平常在用的**主資料庫**（預設是後端目錄下的 `data\stock-desk.db`；若你有改過 `STOCK_DESK_DB_PATH` 就用你改的路徑）：

   ```
   .venv\Scripts\python ..\..\..\work\research\F-3-快取非正值收盤價查證-腳本\check_nonpositive_close.py --db data\stock-desk.db --out F-3_out.json
   ```

   - `--db` 沒有預設值，不給會報錯，這是刻意的，避免誤指到別的檔案。
   - 請用 `--out`，不要用 `>` 導向（Windows 的 `>` 可能把中文轉成 cp950 或 UTF-16）。
   - 不需要、也不要打開任何 `.env`。

3. 螢幕（stderr）會印一行 `F-3 verdict: ...` 與各表一行摘要；完整內容在 `F-3_out.json`。

選用：市場資料庫（`data\stock-desk-market.db`，表 `market_daily_bars`）**不在警示路徑上**，可以另外對它跑一次當參考，
但它不影響本次是否擋部署的判斷；只指向市場資料庫時腳本會回結束碼 2 並提示改指主資料庫。

結束碼：

| 結束碼 | 意義 |
|---|---|
| 0 | 查無：主資料庫的 `price_bars_cache` 沒有收盤價 ≤ 0、NULL 或 `NaN`／`Infinity` 的列 |
| 1 | 查有：至少一列，詳見 `F-3_out.json` |
| 2 | 錯誤：檔案不存在、不是 stock-desk 的資料庫、指到的不是主資料庫，或主資料庫裡缺 `positions`／`alert_rules` 表或必要欄位（無法分辨持有／監看；訊息在 stderr，不會丟出 traceback） |

結束碼 0／1 只說「有沒有壞列」；**是否擋部署看 `escalation`**（見下方「結果怎麼用」）。

### 關於「純讀取」

- 資料庫以 SQLite `mode=ro` 開啟並設定 `PRAGMA query_only`，腳本只有 `SELECT`，沒有任何寫入、建表、修改資料的程式碼；
  檔案不存在時直接報錯，不會建立新檔。也不讀 `.env`、不連網。
- 資料庫若是 WAL 模式，SQLite 在唯讀連線時可能在 DB 旁邊建立空的 `-wal`／`-shm` 附屬檔。這不是改動資料；App 本來就會產生同名檔案。
  App 正在執行也沒關係，不需要先關閉。若想更保險，可先複製一份 DB（連同 `-wal`、`-shm`）再對複本執行。
- 輸出只有代號、市場、日期與筆數；**不含價格、持股數量、成本、檔案完整路徑或任何金鑰**（只記檔名）。
  持倉與警示規則表只讀 `symbol`、`market`、`enabled` 三欄，不讀數量、成本、規則參數或備註。

## 查的是什麼

表與欄位依 `apps/stock-desk/backend/app/data/cache.py` 的建表語句（`price_bars_cache`：`symbol`、`market`、`trade_date`、`close TEXT NOT NULL`…），不是猜的。
`close` 以文字存放，腳本逐列以十進位解析後分類：

| 分類 | 意義 | 是否計入判定 |
|---|---|---|
| `nonpositive` | 可解析且 ≤ 0（含 `0`、`-1.5`、`-0`、`0E-8`） | **是**（造成整輪中斷的就是這種） |
| `null` | SQL NULL（建表禁止，保險起見仍計） | **是** |
| `nonfinite` | `NaN`／`Infinity`（含 `-Infinity`、`sNaN`） | **是**（2026-10-07 更正，見下方說明） |
| `unparseable` | 其他無法解析的文字 | 否，只列出：App 讀快取時會跳過這種列，到不了警示路徑 |

判定口徑與 App 的「可用收盤價」一致（`app.alerts.engine.usable_price`：有值、有限、> 0 才可用）。

**更正（2026-10-07，qa-reviewer 指出）**：舊版說「`NaN`／`Infinity` 列 App 讀快取時會丟掉」不成立。
`app/data/cache.py` 讀快取時只在 `Decimal(...)` 丟例外（或日期等欄位無效）時跳過該列，而 `Decimal("NaN")`、`Decimal("Infinity")`
不會丟例外，所以這種列會進入警示與估值路徑（`app/alerts/snapshot.py` 也把「零、負、非有限」併為同一類不可用收盤價）。
現在 `nonfinite` 計入判定、`bad_rows` 與 `bad_rows_total`；舊欄位 `other_unusable_rows.nonfinite` 為向後相容保留，數字與 `bad_rows.nonfinite` 相同。

計入判定的壞列再依兩個維度分開計數：

| 維度 | 分類 | 定義 |
|---|---|---|
| bar 位置 | `latest_bar_bad` | 這列就是該標的（`symbol`＋`market`）在快取裡、**App 讀得進來的列之中日期最新的一根**（快照與估值會讀到的那根）。收盤價屬 `unparseable` 或日期不是有效 ISO 日期的列，App 讀快取時會跳過，所以不拿來當「最新」——否則一筆被跳過的新列會把它前面那根壞列錯算成較舊 |
| | `older_bar_bad` | 同一標的較舊日期的壞列（最新一根正常或另計） |
| 持有／監看 | `held` | `positions` 表裡有任何一筆該標的的持倉 |
| | `watched` | `alert_rules` 表裡有該標的、且 `enabled = 1` 的規則（任何類型；停用規則不算） |
| | `held_and_watched` | 同時持有又監看（交集；這些標的**也**分別算在 `held` 與 `watched` 裡） |
| | `other` | 既沒持有也沒監看 |

- 本 App 沒有獨立的 watchlist 表，「監看」只以啟用中的警示規則認定。
- 比對持有／監看時，兩邊的代號與市場都先去頭尾空白並轉大寫再比對；大小寫不同只會多比中、不會漏掉。

### 三個資料庫環境變數各對應哪個檔

| 環境變數 | 預設檔案（相對後端目錄） | 本腳本用到的表 |
|---|---|---|
| `STOCK_DESK_DB_PATH` | `data\stock-desk.db`（主資料庫） | `price_bars_cache`（警示與估值讀的日線快取）、`positions`（持有）、`alert_rules`（監看）——**三張表都在這個檔**，所以只要一個 `--db` |
| `STOCK_DESK_MARKET_DB_PATH` | `data\stock-desk-market.db`（市場資料庫） | `market_daily_bars`（只供參考，不在警示路徑；這個檔沒有持倉與規則表，持有／監看會顯示為 `null`） |
| `STOCK_DESK_RESEARCH_DB_PATH` | `data\stock-desk-research.db`（研究資料庫） | 不用；本腳本不需要也不該指到這個檔 |

持倉（`app/positions/store.py`）與警示規則（`app/alerts/store.py`）都跟日線快取共用 `STOCK_DESK_DB_PATH`，
所以腳本**不需要**也**沒有** `--positions-db`／`--alerts-db` 選項。

## 輸出怎麼讀

`F-3_out.json` 主要欄位：

- `verdict`：`none_found`（查無）／`found`（查有）／`alert_path_table_absent`（指錯資料庫）。
- `escalation`：`deploy_prerequisite`（升級部署前置）／`next_release`（不擋部署）；指錯資料庫時為 `null`。
- `held_or_watched_symbols_whose_latest_bar_is_bad`：持有或監看標的中，快取最新一根是壞列的檔數；`escalation` 就是看這個數字。
- `membership`：主資料庫裡持有幾檔（`held_symbols`）、有啟用規則的標的幾檔（`watched_symbols`）。兩個都是 0 時請確認 `--db` 有指到 App 平常用的主資料庫。
- `tables.price_bars_cache`：
  - `bad_rows`：`nonpositive`、`null`、`nonfinite` 各幾列；`bad_rows_total` 是三者合計。
  - `affected_symbols`：涉及幾檔標的；`date_range`：這些列最早與最晚的日期。
  - `symbols_whose_latest_cached_bar_is_bad`：有幾檔的**快取最新一根**就是壞列。這是最直接會造成中斷的情形
    （線上會經 resolver 補抓較新的日線，所以快取最新一根壞了不保證線上一定讀到它，但機率很高）。
  - `latest_bar_bad`／`older_bar_bad`（新增）：兩類各自的 `symbols`（檔數）與 `rows`（列數），
    再各分 `held`、`watched`、`held_and_watched`、`other`，每格同樣是 `{symbols, rows}`。
    `latest_bar_bad` 每檔最多一列，所以檔數等於列數；同一檔若最新一根與較舊列都壞，兩類都會各算一次。
  - `membership_known`：是否讀得到持倉與規則表（主資料庫一定是 `true`；為 `false` 時上面的分組為 `null`）。
  - `affected`：逐檔明細（代號、市場、壞列數、起訖日期、最新一根是否為壞列），每筆另加：
    `latest_is_bad`（與既有的 `latest_cached_bar_is_bad` 同值）、`older_bad_rows`（較舊壞列數）、
    `held`（是否持有）、`watched`（是否有啟用規則）。
  - 既有欄位名稱都保留不變（向後相容）。
  - `other_unusable_rows`：`nonfinite`、`unparseable` 筆數（欄位名沿用舊版）。其中 **`nonfinite` 現在也計入判定**（與 `bad_rows.nonfinite` 同數）；
    只有 `unparseable` 不影響判定，供資料品質後續（F-2）參考。
- `tables.market_daily_bars`：只在你指到市場資料庫時才有內容；`on_alert_path: false`。

## 結果怎麼用

升級判定句（腳本在螢幕最後一行也會印出同義的判定）：

> **持有或監看標的的最新 bar 壞列 ≥ 1 → 升級部署前置，交 CEO 裁決；只有較舊列或只有 other → 不擋部署、排下一 release。**

- **`escalation: deploy_prerequisite`**（`held_or_watched_symbols_whose_latest_bar_is_bad` ≥ 1）：
  持有或監看的標的最新一根就是壞列，警示排程很可能每輪中斷、`/limits` 可能 500，**升級為部署前置**，交 CEO 裁決。
  依風控裁定，此時 F-1 的 R-2-a 前端修正必須**同一次部署**。
- **`escalation: next_release`**：持有／監看標的的最新一根都正常——可能是查無（`verdict: none_found`，結束碼 0），
  也可能是只有較舊的壞列、或壞列只落在 `other` 標的（`verdict: found`，結束碼 1）。**不擋部署**，修正排進下一個 release
  （風控：即使查無仍排下一 release）。較舊壞列不會造成中斷，但會污染報酬與回撤等計算，屬於 F-2（資料品質政策，須另開 ADR），請一併回報。
- **錯誤（結束碼 2）**：多半是 `--db` 指錯檔，請確認指到主資料庫後重跑。

## 把結果貼回給 coordinator

1. 把 `F-3_out.json` 的**全文**貼回對話（不含任何金鑰或持股數量、成本）。
2. 用一句話補充執行時指向哪個 DB（說「App 平常用的主資料庫」即可，不必貼完整路徑）。
3. 若查有，請先**不要**手動修改或刪除任何資料列；是否修、怎麼修由 coordinator、data-engineer 與風控處理
   （任務單已否決在 `PriceBar` 層靜默丟列的做法，見方案 C）。

## 開發者：如何跑本腳本的測試

測試檔 `test_check_nonpositive_close.py` 只在 `tmp_path` 自建 SQLite，不碰任何真實 DB。
在本目錄下直接用後端 venv 執行（不用 `uv run`，避免觸發 venv 同步；`-I` 隔離環境、`-B` 不寫 `__pycache__`、`-p no:cacheprovider` 不寫 `.pytest_cache`）：

```
cd work/research/F-3-快取非正值收盤價查證-腳本
../../../apps/stock-desk/backend/.venv/bin/python -I -B -m pytest -p no:cacheprovider -q .
../../../apps/stock-desk/backend/.venv/bin/ruff check --no-cache --config ../../../apps/stock-desk/backend/pyproject.toml .
../../../apps/stock-desk/backend/.venv/bin/mypy --strict --config-file ../../../apps/stock-desk/backend/pyproject.toml check_nonpositive_close.py test_check_nonpositive_close.py
```

（Windows 把 `.venv/bin/python` 換成 `.venv\Scripts\python`。mypy 會在目前目錄寫 `.mypy_cache`，可加 `--cache-dir` 指到暫存目錄。）

## 匯率 ≤ 0（F-1b）

本機**沒有可掃的匯率快取**：ADR-0011 與 `app/data/providers/fx.py` 寫明匯率走「主來源 → 備援來源 → 不可用」的梯子，
沒有本地 FX 快取層，`app/data/` 下也沒有匯率資料表。所以本腳本**不輸出匯率這一項**，也不去猜表名。
若日後新增 FX 快取表，再依該表的建表語句補上掃描。

## 本腳本看不到什麼

- 只看快取裡**已經存在**的列；線上資料來源當下會回什麼，不在本腳本範圍（不連網）。
- 只判斷收盤價；開高低價與成交量的異常不在本次範圍。
- 「最新 bar」指**快取裡**該標的、App 讀得進來的列之中日期最新的一根；線上 resolver 可能補抓更新的日線，所以快取最新一根壞了不保證線上一定讀到它（反之亦然）。
- 判斷「App 讀得進來」只看收盤價與日期；App 讀快取時若因開高低價、`as_of`、`fetched_at` 等其他欄位無效而跳過某列，本腳本仍會把該列當成最新候選（屬 F-2 資料品質範圍）。
- 只依持倉與啟用規則判斷「持有／監看」；不呼叫 `/api/advice`、`/api/portfolio`、`/limits` 等 API 實際驗證是否出錯。
