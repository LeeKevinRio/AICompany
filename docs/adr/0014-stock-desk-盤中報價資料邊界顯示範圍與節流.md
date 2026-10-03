# ADR-0014：stock-desk 盤中報價（TWSE MIS）的資料邊界、顯示範圍與節流

- 狀態：proposed
- 日期：2026-10-03
- 決策者：tech-architect（草案）、CEO（待核可；2026-10-02 已裁定「加盤中價」與「主來源採 MIS」；2026-10-03 另裁定三點，見「CEO 裁定（2026-10-03）」一節）
- 適用範圍：僅 product/stock-desk 產品線
- 修訂：新增。**不取代任何 ADR。** 2026-10-03 依 ADR-0015（proposed）C-17 加註兩處修訂註記（I-4、防線 2），並調整 D-9 前置條件、W11 列、「前置條件（明列）」段對 ADR-0015 的引用字樣；僅調整引用與註記，決策內容未變。
  - 落實 ADR-0003:32「日後需要即時報價另案評估」這一條另案。
  - 擴充 ADR-0010 R-1：`cache_only` 一律不取盤中報價。
- 編號說明：0013 已由員工線（`chore/agent-readonly-hook`）的唯讀 hook ADR 佔用，該 ADR 之後會 merge 進產品線，故本 ADR 使用 0014（來源：任務單，2026-10-03）。
- 來源與版本：本檔為 tech-architect 2026-10-03 草案的落檔，僅做格式調整，另含落檔時補明一處（D-3 的 13:25～13:30）；「CEO 裁定」一節來自 CEO 2026-10-03 裁定（由任務單轉述）。檔內 `檔案:行號` 為草案作者所引，落檔時未重新對 code 驗證，行號會隨 commit 漂移，引用時以原文定位。

---

## Context（背景）

**1. 現況：所有現價都來自日線。**
- 現價取自日線收盤：`valuation.py:304-328` 的 `_resolve_price` 取 `max(bar.date).close`。
- 台股梯子是 TWSE → TPEx → FinMind（`api/deps.py:95-101`）。

**2. 日線的新鮮度規則與快取。**
- 新鮮度以交易日判定（ADR-0009 D-1）。台股 `publish_cutoff` 15:00、冷卻 1 小時（`freshness.py:109-110`）。所以盤中時段 `judge()` 一律判定「快取已含最近交易日」，不會向來源抓資料。
- 整本帳另有 `cache_only` 估值器（ADR-0010 D-1，`deps.py:171-185`），供 `/api/advice` 使用。

**3. 誰在用 `build_summary`。** 同一份 `build_summary`（`portfolio/summary.py:107-151`）被以下五個路徑呼叫：
- 共用 live 估值器 `get_valuator()`：`/api/portfolio/summary`（`api/portfolio.py:98-100`）、`/api/portfolio/limits`（`:103-167`）、警示（`alerts/snapshot.py:83`、`scheduler.py:176`）、設定頁淨值檢核（`api/settings.py:337-359`）。
- `cache_only` 估值器：`/api/advice`（`api/advice.py:59,165`）。

**4. MIS 介面的已知與未知。**
- `mis.twse.com.tw/stock/api/getStockInfo.jsp` 是非公開文件介面，CEO 已接受這個風險。
- 雲端環境連不到，欄位、延遲、限流、cookie、收盤對帳都還沒有實證。驗證工具是 `scripts/verify_intraday_quotes.py`，CEO 2026-10-05 實測。
- 已知欄位語意（來自該腳本）：
  - `z`＝最後成交價，`"-"` 代表無成交（`:313-316`）。
  - 必要欄位清單（`:129-142`）不含漲跌停 `u`／`w`，所以這兩個欄位是否存在仍未知。
  - MIS 用 `tse_`／`otc_` 前綴區分上市／上櫃（`:240-241`）。腳本遇到未知代號時預設猜「上市」（`:268-272`），production 不得沿用這個猜法。

**5. 上市／上櫃判定可用的現有線索。**
- 證券目錄只有 `market="TW"`，沒有上市／上櫃欄位（`directory/models.py:33-60`）。只能從 `source` 間接判斷：`twse_openapi`（`directory/providers.py:190`）或 `tpex_openapi`（`:278`）。
- 目錄要手動跑 CLI 同步（`deps.py:198-207`）。
- 日線快取的每根 bar 自帶 `source`：`twse`／`tpex`／`finmind`（`twse.py:77`、`tpex.py:200`、`finmind.py:87`）。

**6. 使用者可見字面目前全建立在「非即時」上。**
- `NON_REALTIME_NOTICE`（`adviceWording.ts:308-311`）寫的是「本產品…非即時報價系統」，是**產品層級**的宣稱。
- 首頁價格 tooltip 寫死「（日線收盤，非即時）」（`DataStatusBadge.tsx:16-18`）。
- 總資產卡的「資料時間」其實是**回應產生時間**（`SummaryCards.tsx:59-61`、`summary.py:109`）。
- D4 措辭檔 R3 禁止「即時」等正向時效字眼（`work/stock-desk-D4-資料來源措辭.md:266-267`）。

**7. 前端與 HTTP 層現況。**
- 前端沒有任何 `refetchInterval`，QueryClient 用預設值（`providers.tsx:8`、`queries.ts:62-69`）。
- `RateLimitedClient._throttle` 會持鎖 `sleep`（`http.py:204-213`），而且 HTTP 層刻意不做斷路器（`http.py:64-67`）。

---

## Options（選項比較）

**A. 資料模型**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A1 獨立 `QuoteProvider`＋`Quote` 型別（採用）** | 型別上就與 `PriceBar` 分開；前例是 ADR-0012 §7 的 `MarketSnapshotProvider`（`interface.py:348-370`） | 多一套模型 | 低 |
| A2 把盤中價寫成當日「暫定日線」進 `price_bars_cache` | 前端零改動 | 會讓 `judge()` 誤判今天已有收盤、讓 fetch log 記下假的覆蓋區間，訊號／回測也會吃到半根 K 棒 | **否決** |
| A3 在 `MarketDataProvider` 加 `get_latest()` | 少一個抽象 | 把「一檔、一段日期區間」和「當下、多檔」兩種形狀混成一種，ADR-0012 §7 已否決同類作法 | 否決 |

**B. 接點**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| B1 在 `_resolve_price` 逐檔問 QuoteService（data-engineer 原案） | 改動集中 | 每檔一次查詢，估值器還得知道時鐘與盤中時段 | 批次被拆散 |
| **B2 `value_book()` 開頭整批預取，盤中時段判定只放在 QuoteService（採用）** | 一本帳最多 ceil(N/批次上限) 次請求；估值器不讀時鐘 | 要新增一個方法 | 低 |
| B3 另開報價端點，前端疊加重算 | 後端改動小 | 估值邏輯會分叉到前端，總計與明細可能對不上 | 否決 |

**C. 用哪個估值器**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| C1 直接接進 `_default_valuator` | 改一處就好 | 盤中價會漏進 limits、警示、排程、設定頁 | **否決** |
| **C2 新增第三個估值器，只接給 `/api/portfolio/summary`（採用）** | 影響範圍可窮舉 | 首頁會同時有盤中與收盤兩種基準 | 用標示處理，見 D-7 |

**D. 混合基準**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **D1 逐檔取用；取不到的退回收盤，並揭露（採用；CEO 2026-10-03 裁定可接受，見「CEO 裁定」第 2 點）** | 冷門股「今日尚無成交」時，收盤價本來就是正確的估值依據 | 總計會混合不同時點 | 用 `price_basis` 揭露 |
| D2 整本帳「全有或全無」 | 總計時點一致 | 一檔冷門股就讓整本帳的盤中價失效；美股本來就只有收盤，等於永遠混合 | 否決 |

**E. 上市／上櫃判定**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| E1 只看目錄 | 簡單 | 目錄沒同步就整體失效 | 中 |
| **E2 目錄 → 日線快取的 bar 來源 → 雙通道探測（需實測通過才啟用）（採用）** | 不必假設目錄已同步；探測和正常查詢同一次 HTTP | 雙通道探測依賴 MIS 對不存在的通道是否容錯 | 待實測（P-16） |
| E3 預設猜上市 | 零成本 | 上櫃股會查無資料或對錯市場別 | 否決 |

**F. 更新頻率**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| F1 前端直連 MIS | 無後端負載 | 會遇到 CORS；沒有節流；每個分頁各自打 | 否決 |
| F2 前端固定間隔輪詢 | 簡單 | 前端得硬編盤中時段 | 時段判定分叉 |
| **F3 後端回傳建議間隔，前端只輪詢 summary；後端用快取、single-flight、節流、斷路器統一節流（採用）** | 不論開幾個分頁，上游請求數都有上限 | 前置條件：匯率要有跨請求快取 | 見 D-9 |
| F4 SSE／WebSocket 推送 | 延遲最低 | 複雜度高；單機單人使用不值得 | 延後 |

**G. 備援**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **G1 無備援，MIS 失敗就退回收盤（實測前的預設）** | 不會有冒充的盤中價 | MIS 掛掉時沒有盤中價 | 低 |
| G2 yfinance 備援 | 免費 | 延遲未知；和美股備援、指數、匯率共用同一個 `RateLimitedClient`（`deps.py:58-67`） | 待實測（P-15） |
| G3 FinMind 即時資料 | 官方 API | 權限與方案未知（腳本 check E） | 待實測，預設不採 |

---

## Decision（決策）

**D-1 介面放在 `app/data/interface.py`。**

```python
Board = Literal["tse", "otc"]
class QuoteKey(BaseModel): symbol: str; board: Board
class Quote(BaseModel):            # frozen; every datetime tz-aware
    symbol: str; board: Board; currency: Literal["TWD"]
    price: Decimal                 # parsed from MIS `z` only
    prev_close: Decimal | None     # `y`; check input only, never a price fallback
    limit_up: Decimal | None; limit_down: Decimal | None   # `u`/`w` if present (待實測)
    trade_date: date               # exchange-local (Asia/Taipei)
    quote_time: datetime           # from `tlong`
    server_time: datetime | None   # MIS `queryTime`
    as_of: datetime                # when we retrieved it
    source: str                    # "twse_mis"
class QuoteRejection(BaseModel): symbol: str; board: Board | None; code: QuoteRejectCode; detail: str
class QuoteBatch(BaseModel):
    quotes: tuple[Quote, ...]; rejections: tuple[QuoteRejection, ...]
    status: Literal["ok", "partial", "failed", "blocked"]; as_of: datetime; source: str; reason: str | None
class QuoteProvider(ABC):
    source_id: ClassVar[str]
    def get_quotes(self, keys: Sequence[QuoteKey]) -> QuoteBatch: ...  # never raises for expected failures
```

- `Quote` **沒有**委買價、委賣價、開盤、最高、最低這類欄位可以被誤當成價格取用。
- provider 只做**結構性檢查**：rtcode、代號與市場別是否和請求一致、`z` 是否為 `"-"`、價格是否 ≤0、是否重複。
- 跟時間有關的判斷交給服務層；前例是 `interface.py:190-198`，品質判定在事後指派，不由 provider 自己決定。

**D-2 模組配置。**
- `app/data/providers/twse_mis.py`：adapter。
- `app/data/quote_quality.py`：純函式品質檢查，時鐘與門檻都用注入。
- `app/services/quotes.py`：`IntradayQuoteService`，負責盤中時段判定、上市／上櫃判定、記憶體快取、single-flight、節流、斷路器。
- 依賴方向：`app/data/**` 不 import `app.directory`；上市／上櫃判定放在 services 層；目錄 `source` 對應到 `tse`／`otc` 的函式由 `app/directory` 提供。

**D-3 盤中時段由服務層判定，時鐘一律用 Asia/Taipei。**
- 預設時段：平日 09:00 ≤ t < 13:25（P-6）。
- 假日、颱風假靠證據判斷，不靠假日表（呼應 ADR-0009 Options E 的精神）：報價的 `trade_date` 不是今天，就拒絕為 `not_today`。如果同一批**所有**回傳列都是 `not_today`，`session_state="no_session_today"`，記住 5 分鐘（待實測）。這種情況不算「盤中價取得失敗」，不顯示失敗原因句。
- 13:25～13:30（收盤集合競價）：P-6 預設下已不屬盤中時段，與下一項相同，退回前一交易日收盤；P-6 實測通過改為 13:30 後，這段空窗即消失。（主會話落檔時補明，依 P-6 預設與 CEO 裁定 3 的保守方向，非 CEO 原裁定文字，待 CEO 確認。）
- 盤中時段結束（預設 13:25，P-6）到今日日線入庫之間（受 `publish_cutoff` 15:00 與冷卻影響）：
  - 預設退回前一交易日收盤，並揭露原因（對應揭露點 10）。**〔CEO 裁定 3（2026-10-03）：13:30 收盤後到 15:00 正式收盤公布前，先顯示前一交易日收盤；P-7 預設「關閉」維持不變。見「CEO 裁定」。〕**
  - P-7 實測通過後，才延伸用 MIS 的最後成交價，以專屬標示呈現。
  - 不論哪一種，**都不得把 MIS 的價格寫進日線**。

**D-4 估值器。**
- 建構參數 `PositionValuator(..., intraday: IntradayQuoteLookup | None = None)`。
- 和 `price_mode="cache_only"` 一起傳 → `ValueError`。
- 新增 `value_book(positions) -> BookValuation(valuations, intraday: IntradayContext | None)`：開頭整批呼叫一次 `lookup`，結果傳給 `_resolve_price`。
- `value_all` 保持原本的簽名，改為回傳 `value_book(...).valuations`。
- 不得用「估值器實例上的狀態」傳遞盤中上下文，因為估值器是跨執行緒共用的單例。
- 報價被接受時，該部位**不跑**日線梯子。被拒絕或不在盤中時段，走原本的日線路徑，結果與未啟用盤中功能時相同，只多一個原因欄位。

**D-5 `PriceInfo` 擴充，三個欄位都有預設值。**
- `price_kind: Literal["daily_close", "intraday_quote"] = "daily_close"`
- `quote_time: datetime | None = None`
- `intraday_fallback: QuoteRejectCode | None = None`：在盤中時段卻退回收盤時，填上原因碼。
- `as_of` 維持「交易日」字串。
- `data_status`：MIS 為 `FRESH`；之後若採 yfinance 備援則為 `BACKUP`。`is_within_ttl` 為 `None`。
- **不新增 `DataStatus` 值**（ADR-0005，`interface.py:94-97`）。

**D-6 接線。**
- 新增 `deps._default_intraday_valuator()`，只給 `api/portfolio.py:portfolio_summary` 使用。
- `_default_valuator` 與 `_default_cached_valuator` 不變。
- `PortfolioSummary` 新增兩個區塊：
  - `price_basis`：盤中幾檔、收盤幾檔、最早／最晚成交時間、收盤日期範圍。**〔CEO 裁定 2：總覽需揭露「含 N 檔盤中、M 檔收盤」，見「CEO 裁定」。〕**
  - `intraday`：`session_state`、`source_status`、`refresh_after_s`、`reason`。
- `Totals` 欄位與 `status` 語意不變（`summary.py:27-44`）。

**D-7 畫面影響範圍（回答第 2 題）：**

| 畫面元素 | 依據 | 價格基準 |
| --- | --- | --- |
| 持倉明細的現價／市值／損益（`PositionsTable.tsx:29,46,64`） | `/api/portfolio/summary` | **盤中（可用時）**，逐檔標示 |
| 總資產、未實現損益、標的貢獻、匯率貢獻（`SummaryCards.tsx`） | 同一份 summary | **跟隨持倉**（可能混合基準），以 `price_basis` 標示 |
| 風險儀表（`RiskGauge.tsx`，`/api/portfolio/limits`） | 分母來自 `build_summary`，分子是 `load_bars` 的收盤與 ATR（`portfolio.py:125-153`） | **收盤**。同一條上限若混用盤中分母與收盤分子會失去一致性，判定也會在盤中翻來翻去 |
| 族群動能卡 | ADR-0012 全市場日線（PIT），C-7 | **收盤**，沿用既有截至句 |
| 警示狀態列／推播 | `get_valuator`＋`load_bars` | **收盤** |
| 個股頁一句話結論「收盤 X」（`oneLinerWording.ts:22-33`）、關鍵價位（`KeyLevelsPanel.tsx:38,174`）、DecisionCard「距最新收盤」（`decisionCardWording.ts:31`）、技術指標 | `/api/bars`、`/api/signals` | **收盤**；本階段個股頁不顯示任何盤中數字 |
| 建議卡 `/api/advice` | `cache_only` 整書＋本標的 `load_bars` | **收盤** |
| 操作指令頁「現價」（`PositionSnapshotTable.tsx:41`） | 基準日收盤，已有說明句 | **收盤** |
| 設定頁淨值檢核、回測、事件研究、Kelly | 日線 | **收盤** |

避免使用者看到兩個對不上的數字而困惑，作法如下：
- (a) **時間基準不變式**：每個價格數字，以及由價格算出的金額，在同一個視覺單元內一定附上基準標籤：「盤中 HH:MM:SS 成交」或「MM/DD 收盤」。`intraday_quote` 不得出現「收盤」字樣；`daily_close` 不得出現成交時間。
- (b) 首頁總資產卡：把「資料時間：{回應時間}」改為顯示估值基準。
- (c) 風險儀表與族群動能卡的**主視圖**（不是 `<details>` 裡）各放一句基準句，說明「本卡以 {date} 收盤計算，與上方盤中估值不同」。**〔CEO 裁定 1（2026-10-03）：仍用收盤價的區塊，卡片上直接寫一句依據，例如「本卡以 10/02 收盤計算」。見「CEO 裁定」。〕** 後半句「與上方盤中估值不同」只在總覽實際含盤中價（`price_basis` 盤中檔數 > 0）時顯示；休市日、13:25 後或全數退回收盤時只寫「以 {date} 收盤計算」。實際字面仍走風控逐字核可（I-26）。
- (d) 標籤一律由後端的 `price_kind` 驅動，前端不得自己用時間推斷。
- (e) 個股頁本階段不顯示盤中數字。日後若要加，只能是不參與任何計算的獨立參考列，並修訂本 ADR。

**D-8 上市／上櫃判定（回答第 3 題）：** 判定順序如下，結果在程序記憶體裡快取一個交易日。
- ① 目錄：由 `app/directory` 提供 `board_of(entry)`，把 `twse_openapi` 對應為 `tse`、`tpex_openapi` 對應為 `otc`，並附測試。
- ② 日線快取中該序列最後一根 bar 的 `source`：`twse` 對應 `tse`、`tpex` 對應 `otc`；`finmind` 視為未知；`demo_synthetic` 一律**不報價**。
- ③ ① 與 ② 都沒有結果或互相矛盾（例如轉上市）時：如果 P-16 實測通過，就在**同一次 HTTP** 裡同時送 `tse_X.tw|otc_X.tw`，只採用回傳列 `ex` 與 `c` 都和請求一致的那一列；兩列都有就拒絕為 `board_ambiguous`。P-16 沒通過，就是 `board_unknown`，退回收盤。

目錄沒同步時自然落到 ② 和 ③，**不視為錯誤，也不預設猜上市**。

**D-9 節流與更新頻率（回答第 4 題）：**
- `IntradayQuoteService` 是程序單例，包含：
  - 依代號分別快取，TTL 為 P-1。
  - single-flight：併發請求合併成一次上游呼叫。
  - 全程序共用的最小請求間隔 P-2。這裡**不用 sleep 等待**（和 `http.py:204-213` 不同）：間隔內一律回傳已快取的報價（帶它原本的 `as_of`），超過 P-1 的兩倍就退回收盤。
  - 每批最多 P-9 個通道。
  - 斷路器：遇到封鎖類失敗（非 200、3xx、非 JSON、`rtcode≠"0000"`、`msgArray` 為空，比照腳本 `:1008-1034`），在 P-8 冷卻期內零請求。MIS client 不跟隨重導向（比照腳本 `:626-627`）。
  - 斷路器是刻意的例外，和 `http.py:64-67` 的「請求範圍、不做斷路」不同，理由寫在模組 docstring。
- 前端：
  - 只有 `["portfolio-summary"]` 輪詢，間隔取回應的 `intraday.refresh_after_s`（`null` 就不輪詢），且設 `refetchIntervalInBackground: false`，分頁隱藏時停止。
  - 前端寫死 15 秒下限作為防呆。
  - limits 與族群動能**不輪詢**。
- **前置條件**：匯率有跨請求快取（ADR-0010 S-1 或等效作法；2026-10-03 起由 ADR-0015（proposed）承接，解鎖條件以 ADR-0015 C-19 為準）之前，`refresh_after_s` 一律回 `null`，也就是只靠既有的切回視窗時重新整理。
- 排程程序不得持有或呼叫 `IntradayQuoteService`，所以只有 API 程序會打 MIS。部署前提是單一 uvicorn worker（`compose.yaml:20` 目前就是）；改成多 worker 必須回頭修訂本 ADR。

**D-10 品質檢查。** 拒絕碼如下，每一種都必須浮上檯面：寫 log、寫進回應的 `intraday_fallback`。
- 批次層級：`batch_blocked`、`batch_failed`、`rtcode_not_ok`、`server_time_missing`（實測前一律採 fail-closed）、`clock_skew`（|as_of − server_time| > P-4）、`feed_lagging`（哨兵通道最後成交距今 > P-3，哨兵見 P-13）。
- 逐檔：`symbol_missing`、`code_mismatch`、`board_mismatch`、`duplicate_row`、`no_trade`（`z="-"` 或空值）、`price_non_positive`、`not_today`、`future_quote_time`（`quote_time` > `server_time` + P-5）、`outside_price_limits`（有 `u`／`w` 時檢查）、`implausible_move`（沒有 `u`／`w` 時用 P-12 的寬鬆帶）、`trial_match`（如果實測找到試撮旗標）。
- 判定與狀態：`board_unknown`、`board_ambiguous`、`demo_series`、`source_cooldown`、`throttled_no_cache`。
- 「最後成交距今」**不是**拒絕理由，只是揭露項目，超過 P-11 才顯示提示。
- 絕不以昨收、開盤或委買委賣價冒充成交價。被拒絕的就退回日線收盤，不內插、不取平均。
- 逐檔退回收盤（例如尚未成交的 `no_trade`、美股）即 D1 的混合基準，CEO 2026-10-03 裁定可接受（見「CEO 裁定」第 2 點）。

**D-11 盤中價只用於持倉估值顯示。**
- 訊號、回測、事件研究、建議引擎、Kelly、族群動能、警示、操作指令、設定頁淨值檢核，一律用日線。
- 以 import graph 測試加上「被呼叫就 raise 的假 QuoteService」守住邊界。

**D-12 美股延後。** US 持倉一律 `daily_close`，不觸發任何報價請求。

**待實測參數**：全部集中在單一模組的常數裡，不得用環境變數設定。CEO 2026-10-05 報告回填後，由 data-engineer 更新常數並回頭修訂本表。**全部 P-1～P-16 皆為「待 10/05 實測」的預設值，不是已驗證的數值。**

| 編號 | 參數 | 實測前預設 | 判準（對照腳本檢查項） |
| --- | --- | --- | --- |
| P-1 | 報價快取 TTL | 30 秒 | ≥ B3 活躍標的「相異 `tlong`」的中位間隔；且 ≥ P-2 |
| P-2 | 全程序 MIS 最小請求間隔 | 10 秒 | B4 以 2 秒間隔跑完沒被擋 → 維持 10 秒（5 倍餘裕）；B4 被擋 → ≥ 30 秒並由 CEO 重新裁定；任何情況都不低於 5 秒 |
| P-3 | 來源停滯門檻（哨兵通道最後成交距今） | 120 秒 | B3 最活躍標的中位數 ≤ 30 秒 → 90 秒；30～120 秒 → 180 秒並揭露；> 120 秒 → CEO 重新裁定 MIS 是否適用（對照腳本 `MIS_DELAY_OK_S`／`SLOW_S`，`:144-148`） |
| P-4 | 時鐘偏差容忍 | 60 秒 | 看 B2 有沒有 `queryTime`；沒有 → 維持 fail-closed，交 data-engineer 另提方案 |
| P-5 | 未來時間容忍 | 5 秒 | 看 B3 的 `tlong` 與 `queryTime` 實際差值分布 |
| P-6 | 盤中時段結束點 | 13:25 | 從 13:20 起跑一次 mid，輪詢涵蓋 13:25～13:31：`z` 只在真實成交時變動、沒有試撮值 → 改為 13:30 |
| P-7 | 收盤後延伸窗 | 關閉（CEO 2026-10-03 裁定維持關閉，見「CEO 裁定」第 3 點） | 上市部分：B5 連續兩個交易日全數一致；上櫃部分：另行對帳 TPEx 日線，腳本目前不做（`:953-955`）。兩者都通過才開啟 |
| P-8 | 斷路器冷卻 | 10 分鐘 | B4 被擋 → 30 分鐘（對照腳本 `:1088` 的建議） |
| P-9 | 每批通道上限 | 10 | 目前只驗證過 10 檔（腳本 `MAX_SYMBOLS`，`:123`）；更大批次要另外實測 |
| P-10 | 前端輪詢建議間隔 | 60 秒（匯率快取落地前回 `null`） | max(P-1, 30 秒)；下限 15 秒 |
| P-11 | 「最後成交較久」提示門檻 | 30 分鐘 | 純顯示用，不影響是否接受報價 |
| P-12 | 沒有漲跌停欄位時的寬鬆帶 | ±50% 對比 `y` | 看 B2 原始 JSON 有沒有 `u`／`w`；有 → 改用 `u`／`w`，寬鬆帶只保留給沒有漲跌幅的情況 |
| P-13 | 哨兵通道 | `tse_2330.tw` | 如果實測確認大盤指數通道可用，改用指數 |
| P-14 | cookie | 依 B1 結果 | 需要 cookie → session 只存在記憶體，暖機請求也計入 P-2 |
| P-15 | yfinance 備援 | 不接 | 兩次 mid 的 C 延遲中位數 ≤ 2 分鐘、且 D 為 all_close → 可提案接成 BACKUP，但要有獨立節流預算並揭露延遲 |
| P-16 | 雙通道探測 | 關閉 | 額外跑一次 `--symbols tse:5483,otc:2330`：錯誤通道只是從 `msgArray` 缺席、`rtcode` 仍為 `"0000"` → 開啟 |

**實測補充請求（請轉 CEO，在 10/05 同一天加跑）：**
1. 跑一次錯誤市場別探測（P-16）。
2. 13:20 起跑一次 mid，涵蓋收盤集合競價時段（P-6）。
3. 至少涵蓋一檔冷門股，觀察 `z="-"`。
4. 若可行，隔一個交易日再跑一次 post（P-7）。

---

## CEO 裁定（2026-10-03）

以下三點為 CEO 於 2026-10-03 對本 ADR 草案中「需 CEO 裁定」事項所作的裁定（來源：CEO 裁定，由任務單轉述）。本節記錄裁定內容，並與正文相關段落交叉引用；本 ADR 整體狀態仍為 proposed。

1. **兩種價格基準直接寫在卡片上。** 風險儀表、族群卡等仍用收盤價的區塊，卡片上直接寫一句依據，例如「本卡以 10/02 收盤計算」。
   - 交叉引用：D-7 (c)、D-7 畫面影響範圍表、I-23。
   - 待確認：裁定文字中「等」是否包含建議卡與警示（揭露點 15），本 ADR 暫只涵蓋風險儀表與族群動能卡，未擴大範圍。
2. **逐檔混合基準可接受。** 尚未成交的個股、美股等拿不到盤中價的，用前一交易日收盤；其他用盤中價；總覽需揭露「含 N 檔盤中、M 檔收盤」。
   - 交叉引用：Options D1、D-6 `price_basis`、D-10 末項、D-12、「需風控審查的揭露點」第 3 點。
3. **13:30 收盤後到 15:00 正式收盤公布前，先顯示前一交易日收盤。** 等實測（P-7）確認 MIS 最後成交與官方收盤一致後再改；即 P-7 預設「關閉」維持不變。
   - 交叉引用：D-3、參數表 P-7、「需風控審查的揭露點」第 10 點。

---

## 需風控審查的揭露點（回答第 5 題；只列要審的點，文案交 creative-lead 起草）

1. **盤中價旁的標籤**：要含成交時間與來源性質（交易所基本市況報導、非公開文件介面）；不得用「即時／最新／現在／real-time」等正向時效字眼（D4 R3）。
2. **盤中時段退回收盤的原因句**：每個使用者會遇到的拒絕碼各一句，至少涵蓋：今日尚無成交、來源暫停取用（冷卻中）、報價未通過檢查、無法判定上市／上櫃、示範持倉不取盤中價。
3. **混合基準揭露**：總資產、未實現損益同時含盤中價、台股收盤、美股收盤。（CEO 裁定 2：總覽需揭露「含 N 檔盤中、M 檔收盤」。）
4. **首頁兩種基準並存**：總資產卡（盤中）對上風險儀表與族群動能卡（收盤）的主視圖基準句。（CEO 裁定 1。）
5. **總資產卡「資料時間」改名或改義**：目前顯示的是回應產生時間（`SummaryCards.tsx:59-61`）。
6. **`NON_REALTIME_NOTICE` 改字**（`adviceWording.ts:308-311`）：第一句是產品層級的「非即時報價系統」，盤中上線後與事實不符，需要收斂到「本頁評估」的範圍。必須與盤中上線同一批出貨。
7. **`priceDateTooltip`**「（日線收盤，非即時）」依 `price_kind` 分成兩種字面（`DataStatusBadge.tsx:16-18`）；風險儀表 summary 的「其中 N 檔非即時」（`RiskGauge.tsx:205`）在混合頁面上是否會誤讀。
8. **設定頁資料來源表**：新增盤中來源列與非公開文件介面揭露，呈現規格比照 D4（常駐、≥ `text-sm`、≥ `neutral-400`）。
9. **最後成交時間較久的提示**（P-11）。
10. **收盤後延伸窗的標示**（只在 P-7 開啟時需要）：「今日最後成交、正式收盤資料尚未入庫」。另外，盤中時段結束（預設 13:25，P-6；含 13:25～13:30 集合競價）到日線入庫之間退回前一日收盤的揭露（P-7 關閉時需要）。（CEO 裁定 3：P-7 維持關閉，故後者為目前需要的揭露。）
11. **yfinance 備援的延遲揭露**（只在 P-15 開啟時需要）。
12. **自動更新的揭露**：要說明「約每 N 秒、分頁隱藏時暫停」，不得暗示即時。
13. **禁用詞清單**：是否把「即時報價」「即時價」等正向用法加進 `FRONTEND_FORBIDDEN_TERMS` 與 `shared/forbidden-terms.json`。
14. **「最近一筆成交價」不等於「可成交價格」**的聲明是否必要（未實現損益的性質）。
15. **警示與建議卡**是否需要明示「以收盤評估」，以免使用者以為它們會跟著首頁盤中價變動。

---

## 測試策略與 look-ahead／污染防線（回答第 6 題）

**防線（逐層）：**
1. **型別隔離**：`Quote` 不是 `PriceBar`，而且不存在任何 `Quote` → `PriceBar` 的轉換函式。
2. **儲存隔離**：一輪含盤中報價的估值，前後的 SQLite 每張表列數都不變。比照 `tests/test_market_panel_boundary.py:31` 的 C-7 寫法。
   - **〔2026-10-03 依 ADR-0015 C-17 修訂：「報價不寫入任何表」的不變式維持；「每張表列數不變」僅排除 `fx_rate_cache`、`fx_lookup_log` 兩張表（以表名明列，不得以 `fx_%` 之類的萬用字元排除），`price_bars_cache` 仍在範圍內；或該測試改用不經快取的假匯率 provider，此時不排除任何表。〕**
3. **import graph**：沿用 `tests/import_graph.py` 的 `reachable_app_modules`。signals、backtest、advice、kelly、sectors、research、alerts、playbook、leverage、dividends、scheduler 都不可達報價模組。
4. **接線隔離**：只有 summary 端點用盤中估值器。limits、advice、alerts、settings PUT、`scheduler.evaluate_alerts_tick`、`data_refresh`，搭配「被呼叫就 raise」的假 QuoteService 都要跑通。
5. `cache_only` 加上盤中參數，建構時就 `ValueError`。
6. **時間正確性**：凍結時鐘測下列邊界：
   - 盤中時段：08:59:59／09:00:00／13:24:59／13:25:00／13:30。
   - 台北 08:00（等於 UTC 換日）。
   - 週末，以及假日（MIS 回傳前一日資料）。
   - `tlong` 在未來；naive datetime 被 validator 拒絕。
7. **不冒充**：`z="-"` 但 `y`／`b`／`a`／`o` 都有值時 → 不產生 `Quote`，拒絕碼 `no_trade`。
8. **向下相容**：不傳 `intraday` 時，`test_valuation.py`、`test_valuation_golden.py`、`test_valuation_cache_only.py` 不改任何斷言即可通過。

**單元測試：**
- 每個拒絕碼一張表格驅動測試。
- 盤中時段判定。
- 上市／上櫃判定：目錄已同步／未同步／衝突／只有 finmind／demo。
- 服務層：TTL、多執行緒 single-flight、不阻塞的節流、斷路器、分批、部分成功。
- 估值器：報價接受、退回收盤、US 不受影響、混合基準。
- `price_basis` 的彙總。

**契約測試：**
- 用 10/05 的 `.real.json` 去敏後當 fixture，並記錄查證日期（data-source-integration SKILL 第 22、24 行）。
- 在那之前只能用檔名明標 `synthetic` 的合成 fixture，而且不得當作契約依據。

**API 測試：**
- summary 在盤中／非盤中時段的 `intraday` 區塊。
- `refresh_after_s` 在匯率快取落地前恆為 `null`。

**前端測試（vitest）：**
- 標籤依 `price_kind` 分岔。
- 字面逐字釘住（風控核可後）。
- `refetchInterval` 函式：`null` 時不輪詢，下限 15 秒。
- 只有 summary 輪詢。
- 正向「即時」用法的禁語掃描。

**qa-e2e：**
- 交易日盤中與盤後各做一次實機驗收。
- 雲端環境連不到 MIS，所以依 e2e-fallback 走「執行與判斷分離」：由 CEO 本機代跑、qa-e2e 判定（ADR-0007）。

---

## 工作拆分與先後順序（回答第 7 題）

**實測前可以先做：**

| 編號 | 工作 | 負責 | 前置 |
| --- | --- | --- | --- |
| W1 | `interface.py` 的 Quote 模型與 `QuoteProvider`（D-1） | data-engineer | ADR 草案 |
| W2 | `quote_quality.py` 純函式、全部拒絕碼、門檻常數（P 表預設值並註明「待實測」） | data-engineer | W1 |
| W3 | 盤中時段判定模組（台北時鐘） | data-engineer | 無 |
| W4 | `app/directory` 的 `board_of()`，以及服務層的判定流程（D-8 的 ① ②；③ 先寫好但預設關閉） | data-engineer | W1 |
| W5 | `IntradayQuoteService`：快取、single-flight、節流、斷路器，用假 provider 測 | data-engineer | W1–W4 |
| W6 | 估值器 `value_book`、`PriceInfo` 三個新欄位、`cache_only` 防護、跳過日線梯子 | dev-lead | W1、W5 的介面 |
| W7 | summary 的 `price_basis` 與 `intraday` 區塊；新增 `deps._default_intraday_valuator`（**先不接到端點**） | dev-lead | W6 |
| W8 | 邊界與污染測試（防線 2～5） | dev-lead | W6、W7 |
| W9 | 前端型別、標籤分岔、輪詢函式（先用占位字面，並以守門測試禁止占位字面出貨） | frontend-engineer | W7 的 schema |
| W10 | 揭露文案起草，接著風控審查 | creative-lead → risk-compliance-officer | 本 ADR |
| W11 | 匯率跨請求快取（ADR-0010 S-1），另立 ADR（已立：ADR-0015，proposed） | data-engineer → tech-architect | 無；這是輪詢的前置條件 |

**必須等實測：**

| 編號 | 工作 | 負責 | 前置 |
| --- | --- | --- | --- |
| W12 | MIS adapter 解析，接上真實 fixture 與契約測試（cookie、`u`／`w`、`ex` 值、`tlong` 單位、試撮旗標） | data-engineer | 10/05 報告 |
| W13 | 依判準回填 P-1～P-16，並回修本 ADR 的參數表 | data-engineer → tech-architect | W12 |
| W14 | yfinance 備援的去留（P-15） | tech-architect → CEO | 報告 C、D 兩項 |
| W15 | **接線 commit（獨立、最後做）**：`portfolio_summary` 改依賴盤中估值器，同批出貨 NON_REALTIME 改字與全部核可字面 | dev-lead＋frontend-engineer | W8、W10 核可、W12、W13 |
| W16 | 開啟前端輪詢（`refresh_after_s` 非 null） | dev-lead | W11、W15 |
| W17 | qa-reviewer（含 Codex）審查，加上 qa-e2e 實機驗收 | qa | W15 |
| W18 | 確認單一 worker 部署；建 MIS 請求計數的 log 與觀測 | devops-sre | W15 前 |

---

## Consequences（後果）

**好處：**
- 首頁持倉與總計在盤中可以反映最近一筆成交價。
- 訊號、回測、建議、Kelly、警示、族群動能的資料完全不受影響。
- ADR-0009 的新鮮度判定與快取不用動。
- 不論開幾個分頁，上游請求都受程序層級的節流與斷路器約束。

**代價（照實計）：**
- 首頁同時存在兩種價格基準：總資產對上風險儀表。只能靠標示化解，無法消除。（CEO 裁定 1：標示直接寫在卡片上。）
- 總計是混合時點：台股盤中價、冷門股前一日收盤、美股收盤混在一起。（CEO 裁定 2：逐檔混合基準可接受，總覽揭露「含 N 檔盤中、M 檔收盤」。）
- 盤中時段結束（預設 13:25，P-6）到今日日線入庫之間，首頁會從「今日盤中價」退回「前一日收盤」（P-7 開啟前）。（CEO 裁定 3：維持此行為，P-7 預設關閉不變。）
- 首頁主視圖要多兩到三句基準句。這可能和 CEO 2026-09-19 §4.1 把揭露收進 `<details>` 的方向衝突，需要 CEO 裁定。（草案原文；CEO 裁定 1 要求基準句直接寫在卡片上。）
- 斷路器是 HTTP 層慣例之外的刻意例外，要獨立維護。
- 自動輪詢要等匯率快取落地，在那之前盤中價只在載入頁面或切回視窗時更新。
- MIS 是非公開文件介面，隨時可能改格式或封鎖。屆時整個功能退回收盤，產品其餘部分不受影響（fail-closed）。

**已知限制：**
- 沒有假日表；休市只能事後從報價日期判斷。
- 節流是每個程序各自計算。
- 個股頁本階段沒有盤中價。

**約束：**
- 擴大盤中價的使用範圍（警示、個股頁、建議），或接任何備援來源，都要修訂本 ADR 或另立新 ADR。
- 任何 P 參數變更都要附實測依據，並回填本表。

**前置條件（明列）：**
- **示範持倉排除盤中價。** 示範持倉用真實代號但成本取自合成序列（`demo/seed.py:107-114,158-169`），接上 MIS 會變成「真實現價減去合成成本」的捏造損益，所以一律走 `daily_close`、拒絕碼 `demo_series`（D-8 ②、D-10、I-20；評估摘要阻擋項 2）。
- **前端自動輪詢必須等匯率跨請求快取（W11，即 ADR-0010 S-1 或等效作法；已由 ADR-0015（proposed）承接，W16 解鎖條件以 ADR-0015 C-19 為準）落地。** 在那之前後端 `refresh_after_s` 恆為 `null`（D-9 前置條件、I-25、W16）。原因：每輪輪詢都會讓每個非 TWD 部位重打匯率來源，最多 16 次 HTTP（評估摘要阻擋項 3）。
- **P-1～P-16 皆為「待 10/05 實測」的預設值。** 實測回填前，這些數值不得當作已驗證的事實引用；回填後由 data-engineer 更新常數並回修參數表（W13、I-28）。

---

## 對實作的約束（逐條可檢查）

- **I-1** `MarketDataProvider`、`ProviderResult`、`DataStatus` 的定義在 diff 中沒有改動；`DataStatus` 仍只有四個值。
- **I-2** `Quote` 模型沒有 bid／ask／open／high／low 欄位；`Quote.price` 唯一的指派來源是 MIS 的 `z`（code review 加上 parser 測試）。
- **I-3** `Quote` 的 `as_of`／`quote_time`／`server_time` 都有 tz-aware validator；`trade_date` 以 Asia/Taipei 計算（有測試）。
- **I-4** 報價模組不 import `app.data.cache`、`app.data.market_panel`，也不 import 任何 store；含盤中報價的 `build_summary` 前後，SQLite 每張表列數不變（有測試）。
  - **〔2026-10-03 依 ADR-0015 C-17 修訂：「報價不寫入任何表」的不變式維持；「每張表列數不變」僅排除 `fx_rate_cache`、`fx_lookup_log` 兩張表（以表名明列，不得以 `fx_%` 之類的萬用字元排除），`price_bars_cache` 仍在範圍內；或該測試改用不經快取的假匯率 provider，此時不排除任何表。〕**
- **I-5** 程式碼中沒有任何從 `Quote` 建構 `PriceBar` 或 `BarSnapshotRow` 的地方（grep 加 review）。
- **I-6** import graph 測試：signals、backtest、advice、kelly、sectors、research、alerts、playbook、leverage、dividends、scheduler 都不可達 `app.services.quotes` 與 `app.data.providers.twse_mis`。
- **I-7** `get_intraday_valuator`（dependency，內部呼叫 factory `deps._default_intraday_valuator()`）只在 `api/portfolio.py` 的 `portfolio_summary` 被引用；`_default_valuator` 與 `_default_cached_valuator` 的建構參數不含 `intraday`（grep 加測試）。
- **I-8** `PositionValuator(price_mode="cache_only", intraday=<任何非 None>)` 會丟出 `ValueError`（有測試）。
- **I-9** 盤中時段搭配「被呼叫就 raise」的假報價服務：`/api/portfolio/limits`、`/api/advice/{symbol}`、`/api/alerts/*`、`PUT /api/settings`、`evaluate_alerts_tick`、`data_refresh` 全部通過（有測試）。
- **I-10** 估值器與前端都不判斷盤中時段：`valuation.py` 沒有出現時段常數；前端輪詢邏輯沒有 09:00／13:25／13:30 常數，只讀 `intraday.refresh_after_s`。
- **I-11** N 檔台股持倉的一次 `build_summary`，上游請求數不超過 ceil(N/P-9)，且同一代號不重複（計數用假 provider 測）。
- **I-12** 任兩次 MIS HTTP 的間隔 ≥ P-2；在間隔內的請求不 sleep，直接回快取或退回收盤（假時鐘測試）。
- **I-13** K 個併發請求要同一批代號 → 上游只呼叫 1 次（threading 測試）。
- **I-14** 遇到封鎖類失敗後，P-8 冷卻期內上游零呼叫；MIS client 設 `follow_redirects=False`（有測試）。
- **I-15** D-10 的每個拒絕碼都至少有一個單元測試；被拒絕時 `PriceInfo.intraday_fallback` 非 null，並寫一行 log。
- **I-16** 報價被拒絕或不在盤中時段時，`PriceInfo` 的 `value`／`as_of`／`source`／`data_status`／`is_within_ttl`／`reason` 與「沒傳 `intraday`」時完全相同。
- **I-17** `PriceInfo` 的三個新欄位都有預設值；三個既有估值測試檔不改任何斷言即可通過。
- **I-18** 報價被接受時，該部位不呼叫 `get_daily_bars`／`get_cached_bars`（假服務計數）。
- **I-19** US 持倉永遠是 `price_kind="daily_close"`，而且不觸發報價請求（有測試）。
- **I-20** 示範持倉（備註帶 `DEMO_NOTE_PREFIX`，或快取最後一根 `source="demo_synthetic"`）永遠是 `daily_close`，拒絕碼 `demo_series`（有測試）。
- **I-21** 上市／上櫃判定不會預設成 `tse`；回傳列的 `c` 或 `ex` 與請求不一致時拒絕；`app/data/**` 不 import `app.directory`（import graph 測試）。
- **I-22** `Totals` 的欄位與 `status` 判定沒有改動；`price_basis` 與 `intraday` 放在 `PortfolioSummary` 上。
- **I-23** 前端：`price_kind==="intraday_quote"` 的價格儲存格不出現「收盤」，並且顯示成交時間；`daily_close` 不出現成交時間；總資產卡不再把回應時間標成「資料時間」；風險儀表與族群動能卡的主視圖有基準句（vitest 測試）。（對應 CEO 裁定 1。）
- **I-24** 只有 `["portfolio-summary"]` 設了 `refetchInterval`；設定 `refetchIntervalInBackground: false`；間隔下限 15 秒（vitest 測試）。
- **I-25** 匯率跨請求快取落地前，後端的 `refresh_after_s` 恆為 `null`（有測試）。
- **I-26** 新增的使用者可見字面不含「即時」的正向用法；每一句都要有風控逐字核可紀錄，並以守門測試逐字釘住。
- **I-27** `NON_REALTIME_NOTICE` 改字與 W15 接線在同一個 PR。
- **I-28** P-1～P-16 集中在單一模組常數中，每個常數註明「ADR-0014 P-x，待實測／查證日期」；不讀環境變數。
- **I-29** W15 接線 commit 之前，已有以真實 `.real.json` 去敏 fixture 為基礎的 MIS 契約測試合入。
- **I-30** 若 ADR-0010 D-5 的 memo 落地：盤中估值路徑不在 memo 範圍內，或 memo 的 TTL ≤ P-1 且鍵含報價批次的 `as_of`。
- **I-31** 每次 MIS 請求寫一行 log（時間、通道數、HTTP 狀態、耗時、拒絕碼計數）；cookie 值不進 log、fixture 或任何檔案。
- **I-32** 部署維持單一 uvicorn worker；改成多 worker 前要先修訂本 ADR（devops-sre 確認）。

---

## 交接與升級

- **交 data-engineer**：W1–W5、W11、W12、W13。請 CEO 在 10/05 加跑「實測補充請求」的四項。
- **交 dev-lead**：W6–W8、W15、W16。
- **交 frontend-engineer**：W9。
- **交 creative-lead → risk-compliance-officer**：上方 15 個揭露審查點。
- **交 devops-sre**：W18。
- **需 CEO 裁定**（草案原列四項；2026-10-03 已裁定的標註如下）：
  - (1) 首頁主視圖增加基準句，與 2026-09-19 §4.1「揭露收進 details」可能衝突。→ 對應 CEO 裁定 1。
  - (2) 接受逐檔混合基準（D1）。→ 已裁定可接受（CEO 裁定 2）。
  - (3) P-7 開啟前，盤中時段結束（預設 13:25）到日線入庫之間首頁會退回前一日收盤。→ 已裁定先顯示前一交易日收盤，P-7 維持關閉（CEO 裁定 3）。
  - (4) 實測後 yfinance 備援的去留。→ 仍待裁定（W14）。

---

## 查證限制

（以下為草案作者 tech-architect 的聲明，原樣轉錄。）

- tech-architect 沒有 Bash 權限，所以沒有用 git 檢視 commit `26f7772`；`is_within_ttl`／`reason` 是依 `valuation.py:139-141` 的現況確認的。
- `verify_intraday_quotes.py` 讀到第 1410 行左右，報告輸出段（1410–1692）沒有細讀，不影響本裁決。
- 本文所列的 MIS 欄位行為（`u`／`w`、`ex` 值、試撮、cookie）都是**未查證**，全部歸在 P 表的「待實測」。

---

## 相關檔案（絕對路徑，草案作者所列）

- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/valuation.py
- /home/user/AICompany/apps/stock-desk/backend/app/portfolio/summary.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/interface.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/deps.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/portfolio.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/settings.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/http.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/freshness.py
- /home/user/AICompany/apps/stock-desk/backend/app/directory/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/directory/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/demo/seed.py
- /home/user/AICompany/apps/stock-desk/scripts/verify_intraday_quotes.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/adviceWording.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/components/DataStatusBadge.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/components/SummaryCards.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/components/RiskGauge.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts
- /home/user/AICompany/docs/adr/0009-stock-desk-日線快取以交易日判定新鮮度.md
- /home/user/AICompany/docs/adr/0010-stock-desk-整書估值的資料新鮮度與單一請求的-io-預算.md
- /home/user/AICompany/work/stock-desk-D4-資料來源措辭.md

---

## 附錄：tech-architect 評估摘要（草案前言，原樣轉錄）

**結論：data-engineer 的架構方向可行，採用其骨幹（獨立 `QuoteProvider`、報價不進 `price_bars_cache`、盤中價只用於持倉估值顯示、`cache_only` 不呼叫盤中來源、美股延後），但有 10 處要修正後才能放行。**其中 3 處屬阻擋級，不修會造成污染或把 MIS 打爆：

1. **（阻擋）盤中價不得接進共用的 `_default_valuator`。** 它同時供 `/api/portfolio/limits`、警示 API、排程警示 tick、設定頁淨值檢核使用（`api/portfolio.py:47,125`、`api/alerts.py:61`、`scheduler.py:176`、`api/settings.py:82,350`）。接進去，風險儀表與警示都會在盤中價上翻來翻去。必須另建第三個估值器，只接給 `/api/portfolio/summary`。
2. **（阻擋）示範持倉會被真實盤中價污染。** 示範持倉用真實代號（2330／0050／00631L），成本取自合成序列（`demo/seed.py:107-114,158-169`）。接上 MIS 後，損益會變成「真實現價減去合成成本」的捏造數字，所以示範持倉必須排除。
3. **（阻擋，影響輪詢）匯率沒有跨請求快取（ADR-0010 S-1 未落地）。** 前端每 N 秒輪詢 summary，每輪都會讓每個非 TWD 部位重打匯率來源（最多 16 次 HTTP）。前端自動輪詢必須等匯率快取落地才能上線。

其餘修正（第 4 到第 10 點）：

4. `session_state` 從 `Quote` 拿掉，改放批次／服務層。provider 不讀時鐘，前例是 `interface.py:190-198` 的 snapshot。
5. `fetched_at` 改名為 `as_of`，沿用 `interface.py:5-8` 的慣例。
6. 不在 `_resolve_price` 裡逐檔問報價，改由 `value_book` 先整批預取。
7. 「延遲超過門檻」拆成兩件事：
   - 「來源停滯」：拒絕。
   - 「該檔最後成交距今」：只揭露、不拒絕，因為冷門股本來就久久才成交。
8. 補上幾項品質檢查：代號／市場別與請求不一致、回應裡查無該檔、重複列、時鐘偏差、試撮（待實測）、示範持倉。
9. TTL 在實測前預設 30 秒，而不是 5～15 秒。另加全程序共用的節流、single-flight 與斷路器，見 P 表。
10. 報價通過檢查時，該部位不再跑日線梯子。

**否決的做法：**
- 把盤中價寫成「暫定日線」。
- 在 `MarketDataProvider` 上加 `get_latest`。
- 前端自己重算估值。
- 上市／上櫃判定不出來時預設猜「上市」。
- 用環境變數開關盤中功能。
