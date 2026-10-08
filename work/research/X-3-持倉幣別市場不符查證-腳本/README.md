# X-3a 持倉幣別與市場不符查證：CEO 本機執行說明

對應任務單 `work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md` 的 **X-3a**（規格：檔尾 tech-architect 評估第六節、第八節 KX-1～KX-5）：
在 CEO 本機真實資料庫上查證，持倉表裡是否存在「**幣別與市場不符**」的舊資料列（例如美股記成 TWD、台股記成 USD）。
本腳本同時取代 ADR-0017 要求、但一直沒執行的「合併前本機唯讀盤點 SQL」，結果也用來結掉 PR-0 的「legacy 雙幣別列管可達」。

腳本：`work/research/X-3-持倉幣別市場不符查證-腳本/check_currency_market_mismatch.py`（純讀取、只用 Python 標準庫、不連網）。

## 為什麼要查

持倉的估值會依「市場」決定價格來源與匯率，依「幣別」讀平均成本。兩者不一致時，App 不會報錯，而是**算錯**：

- **美股記成 TWD（A 型，`US_stored_as_TWD`）**：這檔市值被低估約 31 倍，加碼建議股數可能高估約 31 倍；
  決策卡上卻附著一句 USDTWD 匯率來源說明，讓人以為已經換算過。
- **台股記成 USD（B 型，`TW_stored_as_USD`）**：這檔市值被放大約 31 倍，**其他所有標的**的比率因此被低估、加碼股數被高估。

兩種情況畫面上都沒有正確提示。寫入時的檢查是 2026-10-03 前後（commit b7d67e1）才加上的，之前寫入的列、
用外部工具改過的列、或從更早備份還原的列都可能不一致。agent 不得讀 DB，所以「本機到底有沒有」只能由 CEO 執行本腳本確認。

## 執行步驟（Windows）

1. 開 PowerShell 或命令提示字元，切到後端目錄：

   ```
   cd <你的 repo 路徑>\apps\stock-desk\backend
   ```

2. 執行腳本，由腳本自己把摘要寫成 UTF-8 檔 `X-3_out.json`。
   `--db` 請指到 App 平常在用的**主資料庫**（預設是後端目錄下的 `data\stock-desk.db`；若你有改過 `STOCK_DESK_DB_PATH` 就用你改的路徑）：

   ```
   .venv\Scripts\python ..\..\..\work\research\X-3-持倉幣別市場不符查證-腳本\check_currency_market_mismatch.py --db data\stock-desk.db --out X-3_out.json
   ```

   - `--db` 沒有預設值，不給會報錯，這是刻意的，避免誤指到別的檔案。
   - 請用 `--out`，不要用 `>` 導向（Windows 的 `>` 可能把中文轉成 cp950 或 UTF-16）。
   - `--out` 不可以跟 `--db` 是同一個檔，也不可以是它旁邊的 `-wal`／`-shm`／`-journal` 附屬檔，腳本會拒絕執行。
   - `--out` 指到的檔若已存在，會**直接覆寫**、不會詢問；要保留上一次的結果請先改名或換一個 `--out` 檔名。
   - 不需要、也不要打開任何 `.env`。

3. 螢幕（stderr）會印 `X-3 verdict: ...`、一行計數摘要，**最後一行是判定句**（`X-3 判定：low（僅代表執行當下）——…` 或 `X-3 判定：high——…`）；完整內容在 `X-3_out.json`。

結束碼：

| 結束碼 | 意義 |
|---|---|
| 0 | 查無：每一列持倉的幣別都與市場一致（`escalation: low`） |
| 1 | 查有：至少一列不符或無法讀取（`escalation: high`），詳見 `X-3_out.json` |
| 2 | 錯誤：檔案不存在、不是 SQLite 資料庫、沒有 `positions` 表（多半是指到市場或研究資料庫）、`positions` 缺 `id`／`symbol`／`market`／`currency` 任一欄、`--out` 與 `--db`（或其 `-wal`／`-shm`／`-journal`）相同、`--out` 寫不出去，或沒給 `--db`。訊息在 stderr，不會丟出 traceback |

沒有 `positions` 表時，腳本仍會先寫出 `X-3_out.json`（`verdict: positions_table_absent`，其餘欄位為 `null`），再以結束碼 2 結束，請改指主資料庫後重跑。

### 關於「純讀取」

- 資料庫以 SQLite `mode=ro` 開啟並設定 `PRAGMA query_only`，腳本只有 `SELECT`（與讀欄位清單的 `PRAGMA table_info`），
  沒有任何寫入、建表、修改資料的程式碼；檔案不存在時直接報錯，不會建立新檔。也不讀 `.env`、不連網。
- 資料庫若是 WAL 模式，App 關閉時 SQLite 會把附屬檔收掉；這時唯讀連線可能在 DB 旁邊建立 `-wal`（0 位元組）與 `-shm`（SQLite 的共用索引檔，約 32 KB），
  腳本結束後可能留著。兩者都不含持倉資料、不改動主檔，App 下次啟動會照常接手，不需要手動刪除。
  App 正在執行也沒關係，不需要先關閉：腳本讀得到 App 已存檔、但還在 `-wal` 裡的資料。
  若想更保險，可先複製一份 DB（連同 `-wal`、`-shm`）再對複本執行。（以上兩種情境都有測試釘住：主檔 sha256 前後不變。）
- **只讀 `positions` 表的 `id`、`symbol`、`market`、`currency` 四欄**；不讀持股數量、平均成本、備註、產業、建倉日或時間戳。
  輸出只有這四欄與計數，**不含數量、成本、備註、檔案完整路徑或任何金鑰**（只記檔名）。`id` 是為了讓你在持倉頁找到那一列修正。

### 三個資料庫環境變數各對應哪個檔

| 環境變數 | 預設檔案（相對後端目錄） | 本腳本是否使用 |
|---|---|---|
| `STOCK_DESK_DB_PATH` | `data\stock-desk.db`（主資料庫） | **是**：`positions` 表就在這個檔（`app/positions/store.py`），與 F-3 腳本指的是同一個檔 |
| `STOCK_DESK_MARKET_DB_PATH` | `data\stock-desk-market.db`（市場資料庫） | 否；指到它會因沒有 `positions` 表而回結束碼 2 |
| `STOCK_DESK_RESEARCH_DB_PATH` | `data\stock-desk-research.db`（研究資料庫） | 否；本腳本不需要也不該指到這個檔 |

## 查的是什麼

規則抄自 `apps/stock-desk/backend/app/positions/models.py` 的 `MARKET_CURRENCY`：**台股（`TW`）須為 `TWD`，美股（`US`）須為 `USD`**。
腳本的測試會直接解析該檔比對，App 若改了規則，測試會先失敗（防漂移）。

比對方式與 App 相同：**精確字串比對，不去頭尾空白、不轉大小寫**。每一列只會落在下列其中一類：

| 分類 | 意義 |
|---|---|
| `matched` | 市場與幣別一致 |
| `mismatch` | 市場是 `TW`／`US`、幣別是 `TWD`／`USD`，但兩者不符——**這就是 X-3**。再分方向：`US_stored_as_TWD`（美股記成 TWD，A 型）、`TW_stored_as_USD`（台股記成 USD，B 型） |
| `unreadable` | 市場或幣別根本不是 App 認得的值，例如 `'tw'`（小寫）、`' USD'`（前面有空白）、`'HKD'`、空值（NULL）。App 讀這種列會直接失敗（持倉 API 可能已經 500），屬於另一種故障，**分開計數**，原始值照實列出 |

## 輸出怎麼讀

`X-3_out.json` 欄位：

| 欄位 | 內容 |
|---|---|
| `check` | 固定字串 `X-3 position currency does not match market` |
| `generated_at` | 執行時間（UTC） |
| `db_file_name` | 指到的資料庫**檔名**（不含路徑） |
| `verdict` | `none_found`（查無）／`found`（查有）／`positions_table_absent`（指錯資料庫） |
| `escalation` | `low`／`high`；指錯資料庫時為 `null` |
| `counts.total_rows` | 持倉總列數 |
| `counts.matched_rows` | 一致的列數 |
| `counts.mismatch_rows` | 幣別與市場不符的列數 |
| `counts.mismatch_by_direction` | `US_stored_as_TWD`、`TW_stored_as_USD` 各幾列 |
| `counts.unreadable_rows` | 市場或幣別無法讀取的列數 |
| `mismatch[]` | 每一筆不符列：`id`、`symbol`、`market`、`currency`、`direction`、`symbol_has_mixed_currencies` |
| `unreadable[]` | 每一筆無法讀取列：`id`、`symbol`、`market_raw`、`currency_raw`（原始值，以 Python `repr` 表示，例如 `'tw'`、`' USD'`、`None`） |

- `symbol_has_mixed_currencies: true`：同一個代號＋市場底下**另有一列是另一種幣別**（例如 AAPL／US 同時有 USD 與 TWD 兩列），
  也就是 PR-0 任務單講的「同標的雙幣別」情形。只把 `TWD`／`USD` 算作幣別，`unreadable` 列的怪值不算。
- `counts` 各類加總等於 `total_rows`。

## 結果只代表執行當下

本腳本的結果是**執行當下的快照**。之後只要發生下列任一情形，就要**重跑一次**（任務單 X3-F4）：

- 從 b7d67e1（約 2026-10-03）部署**之前**的舊備份還原資料庫；
- 從其他機器複製資料庫檔過來；
- 用 App 以外的外部工具（DB 瀏覽器、SQL 指令等）改過資料庫。

`escalation: low` 只代表**執行那一刻**沒有不符列，**不代表日後不會再發生**；App 現行的寫入檢查擋得住正式寫入路徑，但擋不住上面三種來源。

## 結果怎麼用

升級規則（依風控 C-5）：

| 情況 | `escalation` | 意思 |
|---|---|---|
| 不符 0 列且無法讀取 0 列 | `low` | X-3 列管為「舊資料在本機不可達」，PR-0 的「legacy 雙幣別列管可達」一併結案；讀取端標示（X-3c）改為縱深防護，由 CEO 排序 |
| 不符 ≥ 1 列 | `high` | 依下方步驟修正後重跑；若下次部署前沒歸零，X-3c 列入部署前置候選，交 CEO 裁決 |
| 無法讀取 ≥ 1 列 | `high` | 另案處理（持倉 API 可能已經 500） |

### 查到時（`escalation: high`）

1. **先不要改任何資料**，把 `X-3_out.json` 的**全文**貼回給 coordinator（不含任何金鑰、持股數量或成本），
   並用一句話補充指向哪個 DB（說「App 平常用的主資料庫」即可，不必貼完整路徑）。
2. 等 coordinator 確認後，修正走任務單第十節「CEO 知悉」第 3 點：
   - 在持倉頁找到該列（以 JSON 裡的代號、市場核對）按「**更多**」，在「**編輯部位「代號」**」視窗（ADR-0017 稱為「進階修改彈窗」）
     把幣別改成與市場一致（台股 TWD、美股 USD），**同時把平均成本改成該幣別的數字**。
   - 若真正錯的是**市場**而不是幣別，改市場會讓以（代號, 市場）對應的凱利輸入與警示規則失聯，**請先問 coordinator**。
   - **不要直接改資料庫**。
   - 改完**重跑本腳本，直到不符與無法讀取都是 0**。
3. `unreadable` 列另案處理，同樣先貼回 coordinator，不要自己改。
4. 結果確認前，把出問題標的的決策卡與 `/limits` 數字視為不可信。

## 開發者：如何跑本腳本的測試

測試檔 `test_check_currency_market_mismatch.py` 只在 `tmp_path` 自建 SQLite，不碰任何真實 DB。
它會以文字方式解析 `apps/stock-desk/backend/app/positions/models.py`（`ast`，不 import App）比對規則常數與 `Market`／`Currency` 允許值。
在本目錄下直接用後端 venv 執行（不用 `uv run`，避免觸發 venv 同步；`-I` 隔離環境、`-B` 不寫 `__pycache__`、`-p no:cacheprovider` 不寫 `.pytest_cache`）：

```
cd work/research/X-3-持倉幣別市場不符查證-腳本
../../../apps/stock-desk/backend/.venv/bin/python -I -B -m pytest -p no:cacheprovider -q .
../../../apps/stock-desk/backend/.venv/bin/ruff check --no-cache --config ../../../apps/stock-desk/backend/pyproject.toml .
../../../apps/stock-desk/backend/.venv/bin/ruff format --no-cache --check --config ../../../apps/stock-desk/backend/pyproject.toml .
../../../apps/stock-desk/backend/.venv/bin/mypy --strict --config-file ../../../apps/stock-desk/backend/pyproject.toml check_currency_market_mismatch.py test_check_currency_market_mismatch.py
```

（Windows 把 `.venv/bin/python` 換成 `.venv\Scripts\python`。mypy 會在目前目錄寫 `.mypy_cache`，可加 `--cache-dir` 指到暫存目錄。）

## 本腳本看不到什麼

- 只看資料庫裡**已經存在**的持倉列；不呼叫 `/api/positions`、`/api/advice`、`/limits` 等 API 實際驗證畫面上的數字。
- 只判斷市場與幣別是否一致；**不判斷平均成本本身是不是用對的幣別填的**（腳本刻意不讀成本）。
  幣別欄正確、但成本數字其實是另一種幣別的情形，本腳本查不到。
- 不判斷代號本身是否屬於該市場（例如美股代號記成 `TW` 且幣別 `TWD`，對本腳本是 `matched`）。
- 只查主資料庫的 `positions` 表；備份檔若日後要還原，請先對備份檔也跑一次。
