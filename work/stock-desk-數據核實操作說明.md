# Stock Desk 數據核實 -- CEO 本機一鍵操作說明

- **背景**：`work/research/2026-08-09-stock-desk數據核實.md` 判定「資料源從未真實
  驗證」為上線前致命缺口；本雲端開發環境的 egress policy 擋掉所有財經網域，
  無法直接驗證，須由 CEO 在有網路的本機執行。
- **工具**：`apps/stock-desk/scripts/verify_market_data.py`（data-engineer 產出）。

## 三步驟開始

1. **（可選）準備憑證** -- 缺的來源工具會如實回報 FAIL，不會讓整個工具中斷：

   ```bash
   export FINMIND_API_TOKEN=...          # FinMind 備援來源
   export ALPHA_VANTAGE_API_KEY=...      # Alpha Vantage 美股主來源
   export ALPHA_VANTAGE_DAILY_LIMIT=25   # 依 Alpha Vantage 當下方案填寫
   ```

2. **執行**（用專案既有的 `uv` 虛擬環境，沿用 `app.*` 的匯入路徑）：

   ```bash
   cd apps/stock-desk/backend
   uv sync                                        # 第一次執行前先裝依賴
   uv run python ../scripts/verify_market_data.py
   ```

3. **看結果**：終端會印出摘要表格；完整報告寫到
   `work/research/驗證結果-<今天日期>.md`（會覆蓋掉本次雲端環境跑出的草稿）。

## 這支工具在查什麼

對應 `work/research/2026-08-09-stock-desk數據核實.md` 第 4.5 節 checklist：

| checklist 項目 | 工具怎麼做 |
| --- | --- |
| 1. 六個 adapter 各打一次真實請求 | 直接呼叫既有 `app.data.providers.*`，PASS/FAIL/UNREACHABLE 三態回報 |
| 2. TPEx legacy 端點存活確認 | 主測 legacy 端點，另外對 TPEx OpenAPI 根網域做連線探測供比對 |
| 3. 抽樣逐筆比對，零容差 | 主來源（TWSE/TPEx）vs FinMind 同日同檔比對，收盤價/成交量須完全相等 |
| 4. 成交量單位（股 vs 張）一致 | 比對成交量時若數量級差 1000 倍會特別標註「疑似單位不一致」 |
| 6. FinMind 與 TWSE 交叉比對 | 同上第 3 項的比對表 |
| 8. 槓桿 ETF 註冊表查證（可自動化部分） | 結構性檢查（倍數/費用率是否落在合理範圍）+ `verified` 統計；**不含**抓取發行人 PDF |
| 9. 真實 DB 與 demo DB 物理隔離確認 | 讀 `price_bars_cache`/`positions` 算 `demo_synthetic` 佔比，純本機讀取，不需網路 |

第 5、7、10 項需人工判斷或文案審查，**不在本工具範圍**（報告第 5 節會列出）。

## 常用參數

```bash
uv run python ../scripts/verify_market_data.py \
  --tw-symbols 2330,0050,00631L,5483,2317 \   # 抽樣標的，逗號分隔；預設 2330,0050,00631L
  --start 2026-08-01 --end 2026-08-09 \       # ISO 日期，預設近 10 個日曆天
  --db-path ./data/stock-desk.db \            # 可重複，追加要掃描的 SQLite 檔
  --output /tmp/verify.md                      # 指定輸出檔路徑
```

`--help` 看全部參數。

## 判讀結果

- 六個 adapter 全部 **PASS** 且比對表無 **FAIL** → checklist 第 1/3/4/6 項通過，
  資料源真實性驗證通過，可回報 coordinator。
- 任何 **UNREACHABLE** → 這台機器連不到對方網域（防火牆、DNS、逾時），先排查
  網路本身，不是 adapter 程式的問題。
- 任何 **FAIL** → 連得到但沒拿到可用資料（缺憑證、額度用罄、代號查無資料、
  schema 不符），細節在 `detail` 欄位；若是 schema 不符，需 data-engineer 依真實
  回應更新 adapter 與 `tests/fixtures/*`（`tests/fixtures/README.md` 已有補實錄
  流程）。
- 第 1.1 節（TWSE/TPEx OpenAPI 根網域探測）：只代表「連得到」，不代表已驗證
  資料集路徑；若 legacy 端點 UNREACHABLE 但 OpenAPI 根網域可連線，是改接
  OpenAPI 的訊號（checklist 第 2 項）。

## 離線測試（給 data-engineer / qa-reviewer 驗證程式碼正確性，不需網路）

```bash
cd apps/stock-desk/backend
uv run pytest tests/test_verify_market_data.py -v
```

用既有的 `tests/fixtures/*` 合成 fixture 驗證分類邏輯、比對邏輯、demo_synthetic
統計、槓桿註冊表檢查，全程走 `httpx.MockTransport`，一律不打外網。
