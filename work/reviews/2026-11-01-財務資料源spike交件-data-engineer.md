# 財務資料源 spike 腳本與 CEO 執行指令交件

- 審查者：data-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

財務資料源 spike 腳本、測試與 CEO 本機執行指令都寫好了，已 push 到 `origin feat/stock-desk-fundamentals-spike`（沒有 merge product）。後端 CI 全綠。腳本沒有連過真實網路，只用假 HTTP 回應驗證；真實結果要等 CEO 在有網路的機器跑完貼回。工作樹已移除。

**有一件事與任務前提不符：Alpha Vantage 並非「從未實測」。**
- `work/stock-desk-已知限制與後續.md` 記錄 2026-08-16 三輪驗證時，CEO 本機已實測通過（AAPL 7 筆 fresh）。
- `alpha_vantage.py` 檔頭也寫 VERIFIED。
- 所以 調查報告 與 `DataSourcesSection.tsx:65` 的「尚未以真實 API key 發送過請求」可能已過時，建議 PM 或前端確認。
- 腳本仍照任務打 1 次，在 CEO 文件裡註明這是隔兩個半月後的再確認。

**我順手查到的 FinMind 事實：**
- 我從沙盒讀到 FinMind 官方 GitHub 用戶端的 `schema/data.py`（該網域沙盒可達）。
- 裡面有 `TaiwanStockCashFlowsStatement`、`TaiwanStockBalanceSheet`、`TaiwanStockFinancialStatements`、`TaiwanStockDividend` 等。
- 沒有庫藏股或買回相關的 dataset 名稱。
- 還有 `USStockPrice`、`USStockInfo`，可能是美股價格的另一個備援，可留給 tech-architect 評估。
- 這只是用戶端程式碼的名單，不是官方完整清單，不能當定論。
- 腳本執行時會再讀一次這個檔。

## 各部門回報（data-engineer）

**Commit 清單**（分支 `feat/stock-desk-fundamentals-spike`，從 `origin/product/stock-desk`@9c2d705 長出）
1. `b1efdb9` feat: 新增財務資料源 spike 腳本與測試（CEO #92）
2. `382861b` chore: .env.example 新增 SEC_USER_AGENT（財務 spike 用，僅假值）
3. `bdc5dd7` docs: 新增財務資料源 spike 的 CEO 本機執行指令（CEO #92）

三個 commit 都帶指定的兩行 trailer。

**檔案**（均為相對路徑）
- 腳本：`apps/stock-desk/backend/scripts/fundamentals_spike.py`
- 測試：`apps/stock-desk/backend/tests/test_fundamentals_spike.py`
- 環境變數範本：`apps/stock-desk/.env.example`，只新增 `SEC_USER_AGENT=`（空值加格式說明註解）
- CEO 文件：`work/research/財務資料源spike-執行指令-2026-11-01.md`

**預計請求數**（程式內硬上限 20，超過會停）：正常 16，最壞 17。

| 來源 | 請求數 | 內容 |
| --- | --- | --- |
| SEC | 4（最壞 5） | ticker 對照檔 1；AAPL、AMZN、INTC 各 1 次 companyfacts；第一個路徑失敗才多打備用路徑 |
| TWSE | 4 | swagger 1，最多 3 個樣本資料集 |
| TPEx | 3 | swagger 1，最多 2 個樣本資料集 |
| FinMind | 4 | GitHub 的 dataset 名稱表 1、額度查詢 1、現金流量表（上市 2330、上櫃 6488）2 |
| Alpha Vantage | 1 | AAPL 日線 compact |

SEC 兩個網域合計間隔至少 0.25 秒；其他網站至少 1 秒。不重試，碰到 403 或 429 就如實記錄。

**腳本涵蓋的驗證項目**
- SEC：
  - 確認 ticker 對照檔路徑。
  - 三家公司的營運現金流、資本支出、回購、股利、股票薪酬（SBC）、流通股數標籤，每項都列主標籤與備用標籤。
  - 印單位、期間（`fp`、`fy`、`form`）、`filed` 格式檢查、期間長度分布、重複期間數。
  - 其中期間長度用來確認 10-Q 現金流是不是年初累計。
- TWSE／TPEx：
  - 列出 t187ap 系列資料集。
  - 分「資料集層級」與「欄位層級」兩種比對現金流量表與庫藏股。
  - 後者用來區分「獨立資料集」和「只是資產負債表的期末庫藏股欄位」。
  - 再抽樣印欄位與前兩筆。
- FinMind：dataset 名稱、現金流量表欄位與項目（`type`）、額度。
- Alpha Vantage：1 次日線，印筆數、最新日期、距今天數。

**安全與唯讀**
- 只用標準函式庫，只做 GET。
- 不 import `app`，不碰 DB，不寫檔，輸出只到 stdout。唯一的檔案讀取是讀自己（算腳本雜湊）。
- 金鑰、token、User-Agent、email 一律遮成 `***`，涵蓋 URL 編碼形式與 `token=`、`apikey=`、`Bearer` 字樣。
- 沒設環境變數時，SEC 與 Alpha Vantage 整段略過、不發請求。FinMind 沒 token 時以匿名額度跑。
- 沒讀 `.env`，也沒碰 `data/*.db`。
- 憑證與 email 沒進任何檔案：範例一律是 `your@email.com` 這類假值，並有測試掃描原始碼不得含 email 或金鑰字面值。

**撰寫中抓到並修掉的遮蔽 bug**
- 測試發現 `Authorization: Bearer X` 會遮到 "Bearer" 而漏掉 X。
- 另有 `token=` 的 `=` 被吃掉。
- 已修，並有測試釘住。

**CEO 文件重點**
- 格式比照 N172 文件，但不停服務、不備份 DB。
- 提醒新開 PowerShell，並確認 `UV_ENV_FILE` 為空。
- `SEC_USER_AGENT` 格式範例「姓名 email」，並提醒不要貼回含 email 的那一行。
- 用 `git worktree` 取出，執行 `uv run --frozen python scripts\fundamentals_spike.py`，直接從主控台複製，不要用 `>`。
- 版本核對預期值：
  - 腳本最後修改的 commit 是 `b1efdb95c6539f4e4322f18861163146d9ec5016`。
  - 輸出的 `script_sha256_lf` 是 `8206caaf520ae52a9b1ca1870cbb08a79edbfc98a83fa5094a279209aa9fbe0e`。
- 附逐項白話對照表，包含 10-Q 現金流是累計值、Q4 要用全年減前三季的提醒，以及 bash 版附錄。
- `git check-ignore` 驗證：不帶 `-v` 時 exit=1，代表不被忽略（`work/.gitignore` 的 `!research/**` 放行）。`git add -n` 也成功。

## 驗證

- 後端 CI 在工作樹以 `Popen(start_new_session=True)` 啟動的 runner 跑（runner 有 `__main__` guard）：
  - ruff check：`All checks passed!`
  - ruff format：`465 files already formatted`
  - mypy strict：`Success: no issues found in 457 source files`（`app tests`）
  - pytest：`Required test coverage of 90% reached. Total coverage: 97.45%`，`8933 passed, 2 xfailed, 34 warnings in 832.16s (0:13:52)`
- 新測試 54 項，單獨跑 54 passed。以 `--cov=scripts` 另量，腳本本身覆蓋約 99%。CI 的覆蓋率只算 `app`。
- 測試涵蓋：
  - 遮蔽。
  - 限速與請求上限。
  - SEC、OpenAPI、FinMind 解析。
  - 全部來源斷線、429、403、非 JSON、Alpha Vantage 三種廠商訊息。
  - 單一區段拋例外不影響其他區段。
  - 原始碼斷言：無 `sqlite3`、不 import `app`、只 import 標準函式庫、無寫檔呼叫、唯一的檔案讀取是讀自己（算雜湊）、只有 GET。
  - `__main__` guard 與 `Popen(start_new_session=True)` 啟動 `--help` 測試。
- 完整假回應跑一遍的輸出我看過，版面與判定標籤都正常。
- 限制：以上全是假回應。真實的 SEC、TWSE、TPEx、FinMind 欄位長相與標籤，要等 CEO 輸出才知道。
- 我的沙盒只有 Python 3.11；`uv` 實際用 3.13 venv 跑，專案要求 `>=3.12`，CI 用 3.12。我沒用 3.12 實跑，風險低但需如實說明。
- 支線：沙盒本地的 `.venv` 與工作樹已隨工作樹移除，本地 `git status` 乾淨。

## 下一步

1. **CEO** 在有網路的 Windows 機器照 `work/research/財務資料源spike-執行指令-2026-11-01.md` 跑一次，把 `Fundamentals data source spike` 到 `== Summary ==` 的輸出貼回。我們這邊預期 16 次請求，若看到 `[ERROR]`，請補一句網路環境（VPN、公司網路）。
2. 輸出回來後，由 data-engineer 整理成「標籤與資料集對照表」，內容含 SEC 備用標籤清單、10-Q 累計值還原規則、重複期間的去重規則。
3. 再交 **tech-architect** 出基本面資料介面 ADR（現有介面是為價格設計的，放不進去）與台股來源選型。
4. 風險提示：台股現金流量表與庫藏股買回，目前最可能缺的是官方 OpenAPI 的獨立資料集。若 TWSE、TPEx 與 FinMind 都沒有庫藏股買回的結構化資料，台股的「回購」可能要降級成「期末庫藏股金額」或標示「無資料」。這要等實測結果才能定論，不要先對 CEO 承諾。
5. 另請 PM 或前端確認 `DataSourcesSection.tsx:65` 那句「美股資料鏈尚未實測」是否需要更新（見上方 Alpha Vantage 說明）。這屬展示文案，若是建議性文案需走 risk-compliance-officer。
6. 送 **qa-reviewer** 審查（含 Codex 第二意見）後才可視為 done。
