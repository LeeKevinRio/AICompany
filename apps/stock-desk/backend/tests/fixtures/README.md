# Fixtures — 來源與狀態

**全部 fixture 皆為合成範例（synthetic），不是實錄的真實回應。**

## 為什麼沒有實錄

Phase 2 開發時嘗試直接打各資料源的公開端點錄製真實回應，四個都被本環境的
egress policy 擋下（proxy 對 CONNECT 回 403）：

| 端點 | 結果 |
| --- | --- |
| `https://www.twse.com.tw/exchangeReport/STOCK_DAY` | `curl: (56) CONNECT tunnel failed, response 403` |
| `https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php` | `curl: (56) CONNECT tunnel failed, response 403` |
| `https://api.finmindtrade.com/api/v4/data` | `curl: (56) CONNECT tunnel failed, response 403` |
| `https://rate.bot.com.tw/xrt/flcsv/0/...` | `curl: (56) CONNECT tunnel failed, response 403` |

驗證：`curl -sS "$HTTPS_PROXY/__agentproxy/status"` 顯示
`recentRelayFailures` 記到 `openapi.twse.com.tw:443` 的
`connect_rejected`（`gateway answered 403 to CONNECT`）。因此以下每個檔案
都是**依公開文件描述的 schema 手工構造**，僅供契約測試（驗證 adapter 解析
邏輯、欄位對應、ROC 日期換算、千分位/佔位符處理）使用，**絕不可當成真實市場
資料展示給使用者**。

Phase 7（stock-desk ADR-0005/ADR-0003）新增美股主/備援來源與指數來源，
同一套 egress policy 阻擋同樣適用（本環境對外部網域一律無法連線），未另外
重新嘗試 `www.alphavantage.co` 與 `query1.finance.yahoo.com`，因此
`alpha_vantage_daily_aapl.json`、`yfinance_chart_*.json` 一律視為**同等未查證**，
比照既有檔案處理。`yfinance` 走的還是一個**沒有官方文件**的端點（真正的
`yfinance` PyPI 套件內部也是打這支未公開 API），比 TWSE／FinMind 等有官方文件
但連線被擋的情況又更弱一層查證基礎——這點在 `app/data/providers/yfinance.py`
的檔頭與下表中都有標註。

## 各檔案

| 檔案 | 來源 schema | 狀態 |
| --- | --- | --- |
| `twse_stock_day_2330_202401.json` | TWSE `exchangeReport/STOCK_DAY`（個股日成交資訊，`response=json`） | 合成，依文件手工構造；含一列 `--` 無成交佔位符用於測試跳過邏輯 |
| `tpex_daily_trading_5483_202401.json` | TPEx `web/stock/aftertrading/daily_trading_info/st43_result.php`（個股日成交資訊，`o=json`） | 合成，依文件手工構造 |
| `finmind_taiwan_stock_price_2330.json` | FinMind API v4 `dataset=TaiwanStockPrice` | 合成，依文件手工構造 |
| `bot_fx_usd_twd_20240102.csv` | 台灣銀行牌告匯率歷史 CSV 匯出（`xrt/flcsv/0/<date>`） | 合成，依常見公開格式手工構造；欄位順序（現金/即期/遠期各買入賣出成對出現）**未經即時回應驗證**，`app/data/providers/fx.py` 因此改用「找標籤字串」而非寫死欄位索引來降低風險，找不到時明確回 `unavailable` 而非讀錯欄 |
| `alpha_vantage_daily_aapl.json` | Alpha Vantage `TIME_SERIES_DAILY`（`function=TIME_SERIES_DAILY&outputsize=compact`，2026-08-16 由 `full` 改回 `compact`——CEO 本機實測 `full` 已是免費方案的付費限制，見 `app/data/providers/alpha_vantage.py` 檔頭 VERIFICATION STATUS 段） | 合成，依公開文件手工構造（ADR-0005/ADR-0003 範圍）；含一列全為 `"N/A"` 的不可解析日期，用於測試 adapter 的跳過（不臆測）邏輯；**欄位格式本身仍未經即時回應驗證**（key 有效性與 `outputsize` 限制已實測，但 `compact` 回應的實際欄位 schema 尚未經一次真實回應核對，待 CEO 重跑 `scripts/verify_market_data.py`） |
| `yfinance_chart_tqqq.json` | Yahoo Finance 未公開 `v8/finance/chart/<symbol>` 端點（`app/data/providers/yfinance.py` 個股/ETF 備援路徑） | 合成，依常見公開格式手工構造；含一列全欄位為 `null` 的日期，模擬非交易日/資料缺漏的跳過邏輯；**此端點本身無官方文件，格式僅為廣泛引用的慣例，完全未經即時回應驗證** |
| `yfinance_chart_ndx.json` | 同上端點，指數路徑（`^NDX`，ADR-0005 決策一） | 合成，依常見公開格式手工構造；指數 `volume` 以 `0` 表示（非缺漏）；**完全未經即時回應驗證** |
| `yfinance_chart_twii.json` | 同上端點，指數路徑（`^TWII`，ADR-0005 決策一） | 合成，依常見公開格式手工構造；**完全未經即時回應驗證** |
| `twse_openapi_stock_day_all.json` | TWSE OpenAPI `v1/exchangeReport/STOCK_DAY_ALL`（`app/directory/providers.py` 證券目錄同步用，只取 `Code`/`Name` 欄位） | 合成，依端點命名推斷手工構造；含一列 `Code` 為空字串，用於測試跳過邏輯；**stock-desk-代號目錄 phase，欄位名稱完全未經即時回應驗證，見 `app/directory/providers.py` 檔頭** |
| `tpex_openapi_mainboard_daily_close_quotes.json` | TPEx OpenAPI `openapi/v1/tpex_mainboard_daily_close_quotes`（`app/directory/providers.py` 證券目錄同步用，只取 `代號`/`名稱` 欄位） | 合成，依端點命名推斷手工構造；含一列 `名稱` 為空字串，用於測試跳過邏輯；**stock-desk-代號目錄 phase，中文欄位鍵完全未經即時回應驗證，見 `app/directory/providers.py` 檔頭** |
| `twse_openapi_twt48u_all.json` | TWSE OpenAPI `v1/exchangeReport/TWT48U_ALL`（上市股票除權除息預告表，`app/dividends/providers.py` 除權息還原用） | **端點路徑與欄位結構已由 CEO 2026-08-12 實測確認**（`TWT49U` 已確認不存在、`t187ap45_L` 已評估排除，見 `app/dividends/providers.py` 檔頭）；`Name` 欄位值為合成佔位，僅欄位「結構」對齊實測樣本。合成內容含：一列純現金除息（無 `StockDividendRatio`）、一列全數值欄位皆為空字串（僅 `Exdividend="息"` 這個真實樣本會出現的型態）、一列 `Exdividend="權息"` 且 `StockDividendRatio` 有值（測「記錄存在但不計算」分支）、一列 `Exdividend` 為未知值（測防禦分支，計入 skip）、一列缺 `Code`（測跳過邏輯）、一列 `Exdividend="權"` 但 `StockDividendRatio` 空白（測「旗標與欄位不一致」異常，計入 skip）、一列 `CashDividend` 含千分位逗號 |
| `twse_openapi_t187ap03_l.json` | TWSE OpenAPI `v1/opendata/t187ap03_L`（上市公司基本資料，`app/directory/providers.py` 的 `TwseSectorProfileAdapter` 只取 `公司代號`／`公司名稱`／`產業別` 欄，供 `--verify-sectors` 產業清單覆核用） | **端點路徑與 `公司代號`／`公司名稱`／`產業別` 欄位名稱已由 CEO 2026-08-12 實測確認（1095 筆公司列）**；`產業別` 值改為兩碼代碼（如 `"24"`），貼合實測結果——舊版 fixture 用中文名稱是查證前的錯誤假設。含缺 `公司代號`、缺 `產業別` 各一列測跳過邏輯，一列代碼 `91`（存託憑證）測「官方有、本地清單沒有」分支，一列代碼 `99`（`app/directory/twse_sector_codes.py` 未收錄）測 `app/directory/sector_audit.py` 的 UNKNOWN_CODE 分支 |

## 若之後要補實錄

等 egress policy 開放這些網域後：

1. 用 `httpx`/`curl` 打一次真實請求，把回應存成 `*.real.json` / `*.real.csv`
   （檔名加 `.real` 後綴以區分）。
2. 對照本檔案更新每個 adapter 檔頭的「NOT re-verified」註記與此表格。
3. 若真實 schema 與本檔合成範例不同，優先修正 adapter 解析邏輯與此處合成
   fixture，讓兩者一致，並在 PR 說明中列出差異。

## 憑證聲明

本目錄內任何檔案都不含真實 API token 或憑證。`finmind_taiwan_stock_price_2330.json`
的取得完全不需要 token 存在於 fixture 中——`FinMindAdapter` 的 token 只在執行時
從 `FINMIND_API_TOKEN` 環境變數讀取，測試以 monkeypatch 設定假值。
