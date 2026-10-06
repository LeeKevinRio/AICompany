# F-3 快取非正值收盤價查證：CEO 本機執行說明

對應任務單 `work/dispatch/2026-10-06-任務單-單一標的收盤價不合法不中斷整輪警示檢查.md` 的後續 **F-3**：
在 CEO 本機真實快取上查證，日線快取中是否實際存在收盤價 ≤ 0（或 NULL）的列。
查證結果決定這張修正單**是否擋部署**。

腳本：`work/research/F-3-快取非正值收盤價查證-腳本/check_nonpositive_close.py`（純讀取、只用 Python 標準庫、不連網）。

## 為什麼要查

修正前，只要**任何一檔**標的在快取裡的**最新一根**日線收盤價 ≤ 0，警示檢查就會在組風險上限時出錯，
排程端整輪只記一行錯誤，**所有使用者、所有標的、所有規則都不評估**，下一輪再崩；手動檢查 `/api/alerts/evaluate` 則回 500。
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
| 0 | 查無：主資料庫的 `price_bars_cache` 沒有收盤價 ≤ 0 或 NULL 的列 |
| 1 | 查有：至少一列，詳見 `F-3_out.json` |
| 2 | 錯誤：檔案不存在、不是 stock-desk 的資料庫、或指到的不是主資料庫（訊息在 stderr） |

### 關於「純讀取」

- 資料庫以 SQLite `mode=ro` 開啟並設定 `PRAGMA query_only`，腳本只有 `SELECT`，沒有任何寫入、建表、修改資料的程式碼；
  檔案不存在時直接報錯，不會建立新檔。也不讀 `.env`、不連網。
- 資料庫若是 WAL 模式，SQLite 在唯讀連線時可能在 DB 旁邊建立空的 `-wal`／`-shm` 附屬檔。這不是改動資料；App 本來就會產生同名檔案。
  App 正在執行也沒關係，不需要先關閉。若想更保險，可先複製一份 DB（連同 `-wal`、`-shm`）再對複本執行。
- 輸出只有代號、市場、日期與筆數；**不含價格、持股數量、成本、檔案完整路徑或任何金鑰**（只記檔名）。

## 查的是什麼

表與欄位依 `apps/stock-desk/backend/app/data/cache.py` 的建表語句（`price_bars_cache`：`symbol`、`market`、`trade_date`、`close TEXT NOT NULL`…），不是猜的。
`close` 以文字存放，腳本逐列以十進位解析後分類：

| 分類 | 意義 | 是否計入判定 |
|---|---|---|
| `nonpositive` | 可解析且 ≤ 0（含 `0`、`-1.5`、`-0`、`0E-8`） | **是**（造成整輪中斷的就是這種） |
| `null` | SQL NULL（建表禁止，保險起見仍計） | **是** |
| `nonfinite` | `NaN`／`Infinity` | 否，只列出：App 讀快取時本來就會丟掉這種列，到不了警示路徑 |
| `unparseable` | 其他無法解析的文字 | 否，同上 |

## 輸出怎麼讀

`F-3_out.json` 主要欄位：

- `verdict`：`none_found`（查無）／`found`（查有）／`alert_path_table_absent`（指錯資料庫）。
- `tables.price_bars_cache`：
  - `bad_rows`：`nonpositive` 與 `null` 各幾列；`bad_rows_total` 是兩者合計。
  - `affected_symbols`：涉及幾檔標的；`date_range`：這些列最早與最晚的日期。
  - `symbols_whose_latest_cached_bar_is_bad`：有幾檔的**快取最新一根**就是壞列。這是最直接會造成中斷的情形
    （線上會經 resolver 補抓較新的日線，所以快取最新一根壞了不保證線上一定讀到它，但機率很高）。
  - `affected`：逐檔明細（代號、市場、壞列數、起訖日期、最新一根是否為壞列）。
  - `other_unusable_rows`：`nonfinite`、`unparseable` 筆數，供資料品質後續（F-2）參考，不影響判定。
- `tables.market_daily_bars`：只在你指到市場資料庫時才有內容；`on_alert_path: false`。

## 結果怎麼用

- **查無（`verdict: none_found`，結束碼 0）**：這張修正單照獨立任務排進下一個 release，**不擋部署**。
- **查有（`verdict: found`，結束碼 1）**：代表警示排程很可能每輪都在中斷（尤其 `symbols_whose_latest_cached_bar_is_bad` > 0 時），
  **升級為部署前置**，交 CEO 裁決。即使只有較早日期的壞列（最新一根正常），也請一併回報：
  它們不會造成中斷，但會污染報酬與回撤等計算，屬於 F-2（資料品質政策，須另開 ADR）的範圍。
- **錯誤（結束碼 2）**：多半是 `--db` 指錯檔，請確認指到主資料庫後重跑。

## 把結果貼回給 coordinator

1. 把 `F-3_out.json` 的**全文**貼回對話（不含任何金鑰或持股數量、成本）。
2. 用一句話補充執行時指向哪個 DB（說「App 平常用的主資料庫」即可，不必貼完整路徑）。
3. 若查有，請先**不要**手動修改或刪除任何資料列；是否修、怎麼修由 coordinator、data-engineer 與風控處理
   （任務單已否決在 `PriceBar` 層靜默丟列的做法，見方案 C）。

## 本腳本看不到什麼

- 只看快取裡**已經存在**的列；線上資料來源當下會回什麼，不在本腳本範圍（不連網）。
- 只判斷收盤價；開高低價與成交量的異常不在本次範圍。
- 不查 `/api/advice`、`/api/portfolio` 是否受影響（同一缺陷另開 F-1）。
