# P2 一次性指令文件：批次標註送審資料（RC-473）

- 產出者：coordinator（唯讀 `sed`／`grep`／`git ls-files` 擷取，未改任何對象檔）
- 日期：2026-11-21
- 註記：本檔初版以位元組截斷擷取 grep 輸出，造成一處多位元組字元被切斷（非有效 UTF-8）；已移除被切斷的殘位元組，被截斷的行以原檔為準（風控 RC-529 觀察）。
- 用途：依風控 RC-473「套用前要送我：五份文件各自的第 1～10 行、讀者行或對象行的原文，以及 `STOCK_DESK_DB_PATH` 的 Grep 結果」。

## work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md
- tracked: yes；行數 161
```
     1	# N-152 檢測指令：舊 DB 裡是否殘留「未收盤 K 棒」（給 CEO 本機執行）
     2	
     3	- 日期：2026-10-26
     4	- 對應：後續追蹤清單 N-152；風控裁定 `work/reviews/2026-10-26-信任缺陷結案確認-風控.md` 第 3 點 (c)
     5	- 腳本：`apps/stock-desk/backend/scripts/unfinished_bar_probe.py`（分支 `feat/stock-desk-unfinished-bar-probe`）
     6	- 性質：**唯讀**離線檢測。本雲端環境沒有真實的價格 DB，**必須在存有 `stock-desk.db` 的機器上跑**。不涉祕密、不需付費、不讀 `.env`。
     7	- 網路：腳本本身不連網。但第一次在新 worktree 用 `uv run --frozen` 時，uv 會建立 `.venv` 並同步依賴，需要網路或 uv 快取（見第三節）。
     8	
     9	## 一、這支腳本唯讀，不會改資料
    10	
```
- 讀者／對象行：
1:# N-152 檢測指令：舊 DB 裡是否殘留「未收盤 K 棒」（給 CEO 本機執行）
- STOCK_DESK_DB_PATH：
68:$env:STOCK_DESK_DB_PATH = "C:\stock-desk\data\stock-desk.db"
151:export STOCK_DESK_DB_PATH="$REPO/apps/stock-desk/backend/data/stock-desk.db"   # 依您的實際位置

## work/research/N172-重複指令偵測-執行指令-2026-10-31.md
- tracked: yes；行數 247
```
     1	# N-172 偵測指令：帳冊裡有沒有「同一個決策寫了好幾列」（給 CEO 本機執行）
     2	
     3	- 日期：2026-10-31
     4	- 對應：後續追蹤清單 N-172；CEO #84（2026-10-31）授權先跑唯讀偵測
     5	- 依據：
     6	  - `work/reviews/2026-10-31-N172修法與資料修復評估-tech-architect.md` 第「二、既有資料修復」節（類別 D-A～D-F、誤判防護、偵測 SQL）
     7	  - `work/reviews/2026-10-31-N172評估追加N174N176-tech-architect.md` 第三節第 1 點（D-G）
     8	  - `work/reviews/2026-10-31-4xx重複列N171N174評估-tech-architect.md` Q2-bis（EMERGENCY 重複列）
     9	  - 格式與安全步驟比照 `work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md`
    10	- 腳本：`apps/stock-desk/backend/scripts/n172_duplicate_probe.py`（分支 `feat/stock-desk-n172-probe`）
```
- 讀者／對象行：
1:# N-172 偵測指令：帳冊裡有沒有「同一個決策寫了好幾列」（給 CEO 本機執行）
- STOCK_DESK_DB_PATH：

## work/research/財務資料源spike-執行指令-2026-11-01.md
- tracked: yes；行數 309
```
     1	# 財務資料源 spike 執行指令：免費來源能不能支撐「財務」頁籤（給 CEO 本機執行）
     2	
     3	- 日期：2026-11-01
     4	- 對應：CEO #92（財務資料源 spike）；CEO #90、#91 已裁示做「財務」頁籤（資訊展示、台美切換、美股先上）；ADR-0038 草案第五節 D-9 的待確認項 P-1～P-9、P-12（P-10 台股、P-11 下次財報日不在本次範圍）
     5	- 依據：`work/reviews/2026-11-01-美股財務提問資料調查-data-engineer.md`（下一步第 1 點）、`work/reviews/2026-11-01-ADR0038基本面資料型別-tech-architect.md`（第五節 P 項）。該調查是在沒有外網的沙盒寫的，所有外部來源的描述都沒實測過，這份 spike 就是補實測。
     6	- 腳本：`apps/stock-desk/backend/scripts/fundamentals_spike.py`（分支 `feat/stock-desk-fundamentals-spike`，版本 2）
     7	- 性質：**會連外網的唯讀探測**。沙盒對外回 403，所以必須在**有網路的 Windows 機器**跑。**不碰帳冊 DB、不寫任何檔案、不讀 `.env`**，所以**不需要停服務，也不需要備份 DB**。
     8	- 目標：跑一次，把輸出貼回來。
     9	
    10	## 一、這支腳本做什麼、不做什麼
```
- 讀者／對象行：
1:# 財務資料源 spike 執行指令：免費來源能不能支撐「財務」頁籤（給 CEO 本機執行）
- STOCK_DESK_DB_PATH：

## work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md
- tracked: yes；行數 3041
```
     1	# Phase 1 資料源探測指令（T1-07～T1-10，CEO 本機代跑）
     2	
     3	- 日期：2026-10-16
     4	- 作者：data-engineer
     5	- 對應：`work/stock-desk-新定位-PRD-2026-10-16.md` §6.2 B 組 T1-07～T1-10；ADR-0025 D-9（Phase 1 四列）；PRD #15（資料源查證需連網環境）
     6	- 依據：`.claude/skills/data-source-integration/SKILL.md` 第 1 步「調查與比較」與紅線「不憑記憶寫死費率、額度或 API 規格」
     7	- 性質：**探測指令包，本文件的指令全部尚未執行**。撰寫環境不能連外網，下列端點、資料集名稱、欄位全部是「候選」，查證日期欄待 CEO 跑完後由 data-engineer 填入。
     8	
     9	---
    10	
```
- 讀者／對象行：
874:| 項目 | 指令能給的 | 仍需人工的 | 判讀者 |
2509:| 項目 | 指令能給的 | 仍需人工的 | 判讀者 |
- STOCK_DESK_DB_PATH：
1107:- 路徑由你自己填：市場 DB 預設為後端目錄下 `./data/stock-desk-market.db`（環境變數 `STOCK_DESK_MARKET_DB_PATH` 可覆蓋）；快取 DB 為 `STOCK_DESK_DB_PATH` 指向的
1970:    print("positions not readable in this DB copy (%s); use the copy of the main STOCK_DESK_DB_PATH file" % e)

## work/stock-desk-數據核實操作說明.md
- tracked: yes；行數 79
```
     1	# Stock Desk 數據核實 -- CEO 本機一鍵操作說明
     2	
     3	- **背景**：`work/research/2026-08-09-stock-desk數據核實.md` 判定「資料源從未真實
     4	  驗證」為上線前致命缺口；本雲端開發環境的 egress policy 擋掉所有財經網域，
     5	  無法直接驗證，須由 CEO 在有網路的本機執行。
     6	- **工具**：`apps/stock-desk/scripts/verify_market_data.py`（data-engineer 產出）。
     7	
     8	## 三步驟開始
     9	
    10	1. **（可選）準備憑證** -- 缺的來源工具會如實回報 FAIL，不會讓整個工具中斷：
```
- 讀者／對象行：
- STOCK_DESK_DB_PATH：

