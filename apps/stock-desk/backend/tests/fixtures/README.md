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

## 各檔案

| 檔案 | 來源 schema | 狀態 |
| --- | --- | --- |
| `twse_stock_day_2330_202401.json` | TWSE `exchangeReport/STOCK_DAY`（個股日成交資訊，`response=json`） | 合成，依文件手工構造；含一列 `--` 無成交佔位符用於測試跳過邏輯 |
| `tpex_daily_trading_5483_202401.json` | TPEx `web/stock/aftertrading/daily_trading_info/st43_result.php`（個股日成交資訊，`o=json`） | 合成，依文件手工構造 |
| `finmind_taiwan_stock_price_2330.json` | FinMind API v4 `dataset=TaiwanStockPrice` | 合成，依文件手工構造 |
| `bot_fx_usd_twd_20240102.csv` | 台灣銀行牌告匯率歷史 CSV 匯出（`xrt/flcsv/0/<date>`） | 合成，依常見公開格式手工構造；欄位順序（現金/即期/遠期各買入賣出成對出現）**未經即時回應驗證**，`app/data/providers/fx.py` 因此改用「找標籤字串」而非寫死欄位索引來降低風險，找不到時明確回 `unavailable` 而非讀錯欄 |

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
