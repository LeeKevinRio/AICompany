# ADR-0011：stock-desk 匯率來源梯子與台銀挑戰頁降級

- 狀態：proposed
- 日期：2026-09-19
- 決策者：data-engineer（草案）；待 CEO 核可
- 適用範圍：僅 `product/stock-desk` 產品線（本 ADR 不存在於 main）
- 相依：
  - ADR-0003（美股主來源 Alpha Vantage、備援 yfinance、四層降級鏈、`as_of`/`source` 約定）
  - ADR-0005（指數來源 yfinance、非官方來源一律 `status=backup` 不得標 `fresh` 的揭露紀律，本 ADR 的匯率備援直接沿用此紀律）
  - skill `data-source-integration`（adapter／契約測試／離線 fixture／降級策略／紅線）
- 與既有 ADR 的關係：**不取代任何 ADR**。本則補上匯率（FX）這個垂直的降級鏈；`app/data/providers/fx.py` 檔頭既有的「即期買賣中點模型值、非官方收盤匯率、端點未查證」聲明維持有效，本 ADR 只處理「主來源現在整天回不了 CSV」這個新事實。

---

## Context（背景）

CEO 本機於 2026-09-19 執行 `scripts/verify_market_data.py`，發現台灣銀行匯率 CSV 端點（`https://rate.bot.com.tw/xrt/flcsv/0/<date>`）**對每一天的請求都回傳 HTTP 200，但內容是一頁 HTML「Challenge Validation」防爬驗證頁**（`<title>Challenge Validation</title>`、設定 `cp_clge_done` 的腳本、一個 `sec-cpt-if` iframe），不是 CSV。

既有的 `BankOfTaiwanFxAdapter._parse_csv` 只認得「找不到『即期』欄位」這一種失敗模式，對 HTML 內容一樣會落到「找不到欄位 → 回 None」的分支，於是：

1. 該日的匯率被判定為「當日無資料」而非「來源故障」，兩者在使用者視角意義完全不同（前者是台銀真的沒公告，後者是抓取本身壞了）。
2. 舊版 log 會把整頁 HTML 印出來（`logger.warning(...header=%r...)` 印出的是 CSV 解析後的 header 陣列，對 HTML 輸入會印出整段被 `csv.reader`誤切的內容），每天一大段，污染 log。
3. 一次查詢（`FX_BACKTRACK_DAYS=7` 天回溯 + 目標日）在同一次呼叫中對外發出多達 11 次請求，全部注定失敗——多打的 10 次除了拖慢回應、多佔一次節流間隔，沒有任何價值。
4. 最終結果：`FxRateResult.rates == []`、`status=UNAVAILABLE`，導致 `PositionValuator._resolve_fx` 對所有非 TWD 持倉回 `missing=["fx_now"/"fx_open"]`，美股持倉的市值與匯率貢獻全部變成 `insufficient_data`。

同一台機器上 `yfinance`（`query1.finance.yahoo.com/v8/finance/chart/^TWII`）驗證為 PASS，代表 Yahoo Finance 這個端點目前仍可連線——雖然它本身也是 ADR-0003/ADR-0005 已經標註「未查證、非官方」的來源，但作為「有總比沒有好」的備援仍優於讓匯率整條鏈斷在原地。

三項限制決定了本 ADR 的形狀：

- **台銀端點何時恢復未知**：這是對方主動部署的防爬機制，不是暫時性網路問題，重試/退避對此無效——短路比重試更誠實。
- **yfinance 已有前例被核可為非官方備援**（ADR-0005 對指數路徑的紀律），本 ADR 只是把同一套紀律套用到 FX 這個新垂直，不是新創先例。
- **FX 目前沒有本地快取層**（`app/data/cache.py` 的 `PriceBarCache` 只服務 `PriceBar`，`FxRate` 沒有對應表），因此本 ADR 的降級鏈只有「主 → 備援 → 不可用」三層，沒有 ADR-0005/ADR-0009 那種 cache-first / cached_stale 層——這是本 ADR 明確承認、暫不解決的缺口（見「尚缺的事實」）。

---

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A. BoT 主 + yfinance 備援（本 ADR 採用）** | 不需要新憑證；沿用 ADR-0005 已核可的「非官方來源必須揭露、不得標 fresh」紀律；`_default_yfinance()` 單例已存在，備援可直接共用同一個 `RateLimitedClient` | yfinance 匯率是 Yahoo 的市場報價，不是台銀官方中價，兩者口徑可能有落差；yfinance 端點本身也未經即時回應驗證（ADR-0005 既有揭露） | 若 yfinance 也被封鎖，FX 整條鏈回到 `unavailable`（可接受，fail-safe，不生造假匯率） |
| **B. 央行（中央銀行）公告匯率或其他政府端點** | 官方性質更接近台銀 | 本環境無網路可查證是否有結構化、免費、可程式化存取的每日 CSV/JSON 端點；貿然接線等於憑記憶寫死規格，違反 data-engineer 紅線 | 高：規格若錯，會靜默讀錯欄位 |
| **C. 商用 ExchangeRate API（如 exchangerate-api.com、Fixer 等）** | 通常有明確文件與 SLA | 需要付費或申請 API key，屬於「資料源要付費或額度不足」的情境，依章程應先停下交 CEO／tech-architect 裁決成本，不得自行決定 | 若不申請 key，等同方案 D |
| **D. 匯率整個下線，不做備援** | 零額外程式碼與風險 | 所有非 TWD 持倉的市值、P&L、FX 貢獻永久回 `insufficient_data`，是產品目前最需要的美股估值功能直接失能 | 產品缺口不收斂，且無法區分「資料源问题」與「這個功能本來就沒做」 |

### 決策

**採方案 A。** 理由：不需要新憑證、不需要 CEO 對付費方案的裁決即可先止血，且完全複用 ADR-0005 已經核可的「非官方來源＝備援、揭露、不升級為 fresh」設計模式，實作與審查成本最低。方案 B／C 留在「需要 CEO 或使用者決定」一節，作為未來若要「匯率更接近官方」時的升級路徑。

---

## Decision（決策）

1. **`BankOfTaiwanFxAdapter` 新增挑戰頁偵測**：以回應 `Content-Type` 是否為 `text/html`／`application/xhtml`，或 body 開頭（忽略前導空白、不分大小寫）是否為 `<!doctype html` 或 `<html` 判斷——不比對特定防爬廠商的文字（`cp_clge_done`、`sec-cpt-if`），因為挑戰頁供應商換了實作細節時，字串比對會靜默失效，回應「形狀」（HTML vs CSV）比字面內容更穩定。

2. **同一次 `get_daily_rates` 呼叫內，第一次偵測到挑戰頁即短路，不再對範圍內其餘日期發出請求**，並整體回 `status=UNAVAILABLE`、`rates=[]`（即使呼叫初期已有真實成功的日期也一併捨棄——這是刻意的簡化：呼叫端不應該猜測「部分真實、部分被擋」的混合結果是否可信，而本 ADR 的觸發情境本來就是「每一天都被擋」，這個取捨在實務上幾乎不會犧牲任何真實資料）。

3. **`FxRateResult` 新增 optional `reason: str | None = None` 欄位**（預設 `None`，向後相容，不影響既有呼叫端）。挑戰頁情境下填入固定文案：「台灣銀行匯率來源目前回應為 HTML 挑戰頁（防爬機制），非 CSV 資料，本次判定為不可用。」

4. **Log 只印一行 warning**（英文，內部技術訊息，符合既有 `logger.warning("Bank of Taiwan FX request failed for %s: %s", ...)` 的先例）：`"Bank of Taiwan FX returned an HTML challenge page for {date}; treating as unavailable"`——**絕不**把回應 body（整頁 HTML）印進 log。

5. **新增 `YFinanceFxAdapter`**（`app/data/providers/fx_yfinance.py`）：重用 `YFinanceAdapter` 既有的 chart 端點 HTTP + JSON 解析（新增一個公開方法 `fetch_chart_closes`，不重寫解析邏輯），把 6 碼幣別代碼（如 `USDTWD`）轉成 Yahoo 的 FX 代號慣例：
   - USD 為基準貨幣時用 Yahoo 的簡寫慣例 `"<報價貨幣>=X"`（`USDTWD` → `TWD=X`）——這是本程式碼庫目前唯一會用到的形狀（`app/portfolio/valuation.py` 一律組出 `f"{position.currency}TWD"`，而目前範圍內非 TWD 幣別只有 USD）。
   - 其他基準貨幣退回一般化的 `"<基準><報價>=X"` 形式，僅為前向相容保留，**未經即時回應驗證**。
   - 取每日 `close` 當該日匯率；`source_id="yfinance_fx"`；`status` **恆為 `DataStatus.BACKUP`**，即使取得成功也不得標 `FRESH`——比照 ADR-0005 對 yfinance 指數路徑的紀律（決策一第 3 點／I-3），這不是台銀官方中價，不得被誤認為系統記錄來源。

6. **新增 `FxRateLadder`**（`app/data/providers/fx.py`）：`primary`（`BankOfTaiwanFxAdapter`）先試，成功（`status != UNAVAILABLE` 且至少一筆匯率）原樣回傳；`primary` 失敗則試 `backup`（`YFinanceFxAdapter`），成功時**重新標記為 `BACKUP`**（即使備援自己回的已經是 `BACKUP` 也不升級/降級狀態字面本身，只是統一由梯子的邏輯決定要不要沿用），並在 `reason` 附上「主來源為什麼被跳過」；兩者皆敗則回 `UNAVAILABLE`，`reason` 合併兩層原因（分句銜接方式比照 `app/data/service.py` 的 `_combine_reasons`）。任一層拋出非預期例外（bug，不是「查無資料」的正常降級）會被捕捉並記錄，視同該層宣告失敗，不讓一個介面卡死整條鏈。

7. **`app/api/deps.py` 的 `_default_fx_provider()` 改回傳 `FxRateLadder`**，其 `backup` 建立在 `_default_yfinance()` 這個既有單例上——與美股個股備援、指數路徑共用同一個 `RateLimitedClient`，同一份節流預算，不對 Yahoo 開第二條連線。

8. **`scripts/verify_market_data.py`**：
   - `probe_fx`（台銀）現在把 `FxRateResult.reason` 傳進 `classify_result`，挑戰頁情境下報表顯示的 `detail` 是「台灣銀行匯率來源目前回應為 HTML 挑戰頁（防爬機制），非 CSV 資料，本次判定為不可用。」，而不是整頁 HTML 或籠統的「無可用資料」。
   - 新增 `probe_yfinance_fx`，對 `TWD=X` 單獨探測一次，獨立於梯子邏輯之外，讓報表能分別看到「台銀本身狀態」與「備援本身狀態」，而不是只看到梯子的合成結果。
   - 報表既有的「六個 adapter」用詞全面改為「七個 adapter」。

---

## 明確不該做的事（紅線，違反即否決）

- 不得把 yfinance 匯率標為 `FRESH`，或在任何使用者可見文案暗示這是台銀官方牌告。
- 不得用字面比對特定防爬廠商的 HTML 內容做挑戰頁偵測（供應商更換實作即失效）；只能用回應「形狀」（Content-Type／HTML 標籤）判斷。
- 不得把整頁 HTML 寫入 log 或任何持久化紀錄。
- 不得在偵測到挑戰頁後繼續對範圍內其餘日期發出請求。
- 不得用 1.0 或任何預設值代入匯率（ADR-0005 F-2 的紅線在此依然適用；本 ADR 沒有變更這一條，只是多一層備援，備援失敗時仍然是誠實的 `UNAVAILABLE`）。

---

## Consequences（後果）

### 好處

- 台銀端點被防爬擋住時，非 TWD 持倉的估值不再整體失能——yfinance 備援能撐住基本可用性。
- 一次查詢從最多 11 次注定失敗的 HTTP 請求降到 1 次即短路，減少對台銀端點的無謂請求（即使它現在擋著我們，繼續狂打也不禮貌，且違反 rate-limit 精神）。
- Log 不再被整頁 HTML 洗版。
- `FxRateLadder` 的形狀與既有 `MarketDataService` 一致，日後接手的人不需要學一套新心智模型。

### 代價（照實列）

- **yfinance 匯率是 Yahoo 的市場報價，不是台灣銀行的官方即期中價**，兩者口徑（例如報價時間點、買賣價處理方式）可能有落差，備援生效期間的匯率精度會比平常略低。這個落差對使用者的揭露句由 **risk-compliance-officer 另審**，本 ADR 不代為決定文案（`app/services/fx.py` 的 `SOURCE_NOTES["yfinance_fx"]` 先給出一句工程side的事實陳述，最終使用者可見文案仍需風控過）。
- **一次呼叫中途遇到挑戰頁會捨棄該次呼叫中已成功抓到的日期**，即使那幾天其實是真資料。這是本 ADR 為了避免「部分真、部分假、呼叫端要自己判斷可信度」的複雜度而接受的簡化，代價是理論上會比逐日獨立重試多流失一點點資料（實務上因為觸發情境是「每天都被擋」，這個代價幾乎不會發生）。
- **FX 目前仍然沒有本地快取層**：本 ADR 只加了「線上主 → 線上備援」，沒有比照 ADR-0005/ADR-0009 加上 cache-first／cached_stale。若兩個線上來源都掛掉，即使前一天才成功抓過匯率，這次查詢也還是 `UNAVAILABLE`，不會像價格那樣退回快取。
- **`YFinanceFxAdapter` 與美股個股備援、指數路徑共用同一個 `RateLimitedClient`**：三個角色的節流預算現在互相排擠（原本只有兩個角色）。目前流量規模下影響可忽略，但若未來 FX 查詢頻率大增，需要重新評估節流間隔是否足夠。

---

## 需要 CEO 或使用者決定（本 ADR 不代決）

1. **要不要投入成本查證央行或商用 ExchangeRate API 作為更接近官方的匯率來源？** 選項：(a) 維持本 ADR 的 yfinance 備援，接受「非官方」的代價；(b) 由 devops-sre 在有網路環境查證中央銀行是否有結構化免費端點；(c) 申請商用 API key（涉及費用，依章程紅線需先停下交 CEO 裁決）。data-engineer 立場：先上線方案 A 止血，(b)/(c) 列為後續 ADR。
2. **`yfinance_fx` 備援生效時，前端要不要新增一句常駐揭露？** 工程面已有 `app/services/fx.py` 的 `SOURCE_NOTES["yfinance_fx"]` 文字，但最終使用者可見措辭（是否要用類似 `DataMetaStatusBadge` 的徽章樣式呈現）需要 creative-lead／risk-compliance-officer 過審，本 ADR 不代決。
3. **是否要幫 FX 也補上快取層（比照 `PriceBarCache`）？** 這會把降級鏈從三層擴充到四層（主 → 備援 → 快取 → 不可用），是否值得投入取決於台銀端點恢復正常的時間長短——若挑戰頁只是短期措施，優先順序可以降低。

---

## 風控審查（risk-compliance-officer，2026-09-19）

- `SOURCE_NOTES["yfinance_fx"]` 第一稿 **VETO**（未揭露口徑落差、未揭露幣別代號未查證）；已依風控定稿字面落地，逐字鎖定：
  「匯率取自 Yahoo Finance 的每日收盤價（非台灣銀行官方牌告），為本次台灣銀行來源不可用時的備援；其口徑與台銀即期中價不同，換算結果可能與官方牌告有落差。該端點未公開文件化，幣別代號（如 TWD=X）與欄位格式均未經本環境線上查證（verified=false）。」
- 挑戰頁 `reason` 固定文案 APPROVE。事實查核結果：`FxRateResult.reason` 目前**只到 `scripts/verify_market_data.py` 報表**，`resolve_fx_quote` 只取 `source_note`、`FxQuote` 無 `reason` 欄位；使用者可見的揭露因此只有上述定稿句（其「為本次台灣銀行來源不可用時的備援」半句承擔「不可用的是台銀、顯示的是備援」的銜接）。把 `reason` 串到 `FxQuote`／前端徽章列為列管（見下）。
- 條件：(1) 備援生效不需新 UI 元件，但 `status=BACKUP` 徽章必現，且定稿句與台銀句同位置、同樣式、同字級，不得摺進 tooltip、不得只在部分端點出現；(2) 不得把 yfinance 匯率與台銀牌告並列比較或呈現「差異很小」等安撫語，除非落差量化觀測完成；(3) 長期停留備援時需定期回報台銀恢復狀態，不得讓臨時備援成為無人複核的常態；(4) `source="none"` 不得套 `GENERIC_SOURCE_NOTE`（已改為空字串）。

### 條件 (1) 在總覽頁的落實（qa 2026-09-19 blocking → 已補）

qa 指出 `GET /api/portfolio/summary` 的估值（`PositionValuator._lookup_fx`）原本只回匯率數字，無處揭露備援。已補：
- `Valuation.fx: FxInfo | None`（`pair`／`as_of`／`source`／`data_status`／`source_note`），非 TWD 部位一律帶，TWD 部位為 `None`；
- `PortfolioSummary.fx_disclosures: list[str]`：本次實際用到的匯率來源揭露句去重；
- 前端：持倉表非 TWD 部位加匯率狀態徽章（沿用既有「備援源」字面），總覽卡「匯率貢獻」下常駐列出 `fx_disclosures`。

### 列管

- `FxRateResult.reason` → `FxQuote.reason`／`FxInfo.reason` → 前端匯率徽章旁原因句（需前端型別與風控字面審）。
- qa low：`CHALLENGE_PAGE_REASON` 字面「防爬機制」比偵測判準（HTML 形狀）更具體；風控已逐字核可該句，若要改為中性措辭須重送風控。

## 尚缺的事實（不阻擋定案，實作前必須補齊，全部需記錄查證日期）

1. 台灣銀行挑戰頁機制是永久性的防爬政策改版，還是暫時性措施——本環境無法查證，需 CEO 或 devops-sre 定期用 `scripts/verify_market_data.py` 追蹤恢復狀態。
2. Yahoo FX 代號慣例（`"<QUOTE>=X"`／`"<BASE><QUOTE>=X"`）僅依常見公開慣例手工構造，**完全未對真實回應驗證**——比照 `app/data/providers/yfinance.py` 既有的 VERIFICATION STATUS 揭露，待有網路環境時查證。
3. yfinance 匯率與台灣銀行官方即期中價的實際歷史落差幅度未量化——若要在 UI 呈現「本次匯率可能與官方牌告有落差」的具體數字（而非只是文字警語），需要一段兩者並存的觀測期。
