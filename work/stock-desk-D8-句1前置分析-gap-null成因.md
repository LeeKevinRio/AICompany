# D8 句 1 前置分析:產線上「as-of 有日期但 trading_days_behind 為 null」的成因與頻率

- 出具者:dev-lead|分支 lane-s2-landing(基於 product/stock-desk a0f7f1a)|2026-08-19
- 對應:`work/reviews/2026-08-19-三句補充揭露-風控批審.md` 句 1 **required 7**
  (dev-lead 書面說明產線「有日期但 gap null」成因與頻率;若屬常態,正解修上游,本句改列管)。
- 性質:純分析,無任何程式碼變更。

## 結論(一句話)

**例外(補句合理)。** 在 CEO 的實際使用情境(TW 持倉、本機後端、cache 內已有 ^TWII
與個股 bars)下,句 1 所在的畫面(操作摘要面板)**結構上不可能**出現
「as-of 顯示日期、但 `trading_days_behind` 為 null」的組合——不是低機率,是資料流上
封死的狀態。因此不存在「修上游」的問題,句 1 作為防禦性揭露(涵蓋測試環境、
時鐘偏移等殘餘邊角)是正確做法,不需改列管。

## 分析依據

### 1. null 的三個成因(`app/services/market.py:104-143`)

`trading_days_behind_market()` 回 `None` 只有三條路:

1. `source is None` ——呼叫端沒帶 `calendar_source`(無日曆來源);
2. `last_bar_date is None` ——沒有任何 bar;
3. `market_trading_days(market, last_bar_date, today)` 回空集合——窗內未觀察到任何交易日。

### 2. 誰帶 calendar_source(`app/api/` 全數清點)

| 呼叫端 | 帶 calendar_source? |
|---|---|
| `app/api/advice.py:97`(GET /api/advice/{symbol}) | **有**(`CalendarDep` = `get_price_bar_cache`) |
| `app/api/bars.py:90`、`signals.py:93`、`leverage.py:97`、`backtest.py:331`、`portfolio.py:129` | 無 |
| `app/playbook/service.py:201`、`app/scheduler.py:110`、`app/alerts/snapshot.py:65` | 無 |

不帶的端點其 `data.trading_days_behind` **永遠是 null**——但這是 C4 的刻意設計
(`market.py:157-161`:不發布資料過舊判斷的端點不付日曆查詢的成本),而且
**前端產線程式碼中唯一讀取 `trading_days_behind` 的地方是
`frontend/app/lib/operationSummary.ts`**(句 1 所在的操作摘要面板),它只吃
`GET /api/advice/{symbol}` 的回應——正好就是唯一帶 calendar_source 的端點。
其他端點的 null 不會流到任何會下「資料過舊/不過舊」判斷的畫面上。

### 3. 為何在句 1 的畫面上三個成因都封死

以 CEO 實際情境逐條檢查(advice 端點):

- **成因 1 封死**:`CalendarDep` 由 FastAPI 依賴注入,每一個 request 都帶,
  且注入的就是全 process 共用的同一顆 `PriceBarCache`(`deps.py:44-52` 的
  `_default_cache`,lru_cache 單例)。
- **成因 2 封死**:卡片(as-of 句所在)只在 `latest` bar 存在時才產生
  (`advice.py:127-143`:無 bar 直接回 `insufficient_data`、`advice=None`,
  此時前端不渲染 as-of 句)。有卡片 ⇒ 有 bars ⇒ `meta()` 的 `last_bar_date` 必非 null。
  (此不變量已由 `tests/test_api_advice.py` 的 R-D5②-2 測試雙向釘死。)
- **成因 3 封死**:資料階梯保證「被端出的 bars 必在同一顆 cache 裡」——
  live 取得的 bars 在回傳前先 `self._cache.put(...)`(`app/data/service.py:116`),
  cache_first layer 0 與 fall-back 兩路本來就是從 cache 讀的。
  日曆查詢窗 `[last_bar_date, today]` 是 SQLite `BETWEEN`(含端點,
  `cache.py:270-279`),窗內至少含 `last_bar_date` 當天那根 bar 自己
  ⇒ 集合非空 ⇒ 回傳值 ≥ 0,絕不是 null。TW 與 US 兩市場的產線 service
  都是同一顆 cache(`deps.py:86-98`),CEO 本機依 `local-run` skill 固定用
  同一份資料庫,cache 內已有 ^TWII 與個股 bars 只會讓集合更大。

### 4. 殘餘的例外情境(句 1 實際守住的東西)

- **測試/開發 harness**:`tests/conftest.py:62-66` 明文寫著 fake price service
  不寫 cache、日曆一無所見、欄位為 null——這是目前唯一穩定重現 null 的環境。
- **系統日期偏移**:`today=date.today()`(server 本地日)若落後 bar 日期,
  `BETWEEN` 窗會倒置成空集合。但 bars 本身就被請求窗 `[start, today]` 過濾,
  bar 日期不會晚於 today,實務上此路也近乎封死;CEO 本機為台北時間,更無此問題。
- **未來新增的呼叫面**:若哪天有別的畫面開始讀其他端點的
  `trading_days_behind`,那些端點目前一律回 null——届時的正解才是「上游補帶」:
  在該端點的 `load_bars(...)` 加一行 `calendar_source=get_price_bar_cache()` 依賴
  (與 advice.py 同款,成本只是一次已建索引的 SQLite DISTINCT 查詢,
  `idx_price_bars_cache_market_date`)。此為預留修法,今日無需動作。

## 頻率量化

在 CEO 實際使用情境下,句 1 畫面上「有日期但 gap null」的發生頻率:**0**
(結構上不可達,非統計估計)。全系統範圍內 null 常見(八個不帶日曆的呼叫端),
但均不落在任何做資料年齡判斷的 UI 上,與句 1 無涉。

## 給風控的答覆(required 7)

成因與頻率如上:**例外,補句合理**。句 1 依原裁決落地條件 1-8 修字面即可,
無需改列管、無需修上游;上游預留修法已記錄於本文第 4 節,供未來新增呼叫面時取用。
