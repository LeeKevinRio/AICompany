# Stock Desk Phase 8 — 資料源 Spike 盤點（S-1～S-3）

**撰寫者**：data-engineer
**撰寫日期**：2026-08-02
**依據**：`work/stock-desk-phase8-需求.md` S-1～S-3 節、`.claude/skills/data-source-integration/SKILL.md`、CEO 裁示優先序（台股為主、美股少量；S-2 > S-1 > S-3）

---

## 0. 交付說明與誠實性聲明（先讀這段）

1. **本環境無外網**：對外 HTTPS 一律被 proxy 擋下（403/000），本文件內所有候選端點、欄位、額度數字**均未在沙盒內實測過**，全部憑 data-engineer 撰寫當下（2026-08）的既有知識手工列出。不確定的地方一律寫「不確定」，不編造端點細節或欄位名稱去湊完整性。
2. 本文件因此分兩層：
   - **紙上盤點**（本文件）：端點/取得方式、資料欄位、更新頻率、額度、授權疑慮、整合難度的最佳猜測，附信心等級（高/中/低）。
   - **可執行驗證腳本**：`scripts/spike_phase8_sources.py`，設計給 CEO 在本機（有網路）執行，對每個來源發最小查證請求。**每個來源表格最後一欄「實測結果（待 CEO 回填）」目前是空的**，請貼上腳本印出的「HTTP 狀態 / 欄位樣本 / 結論」三項。
3. 本文件的結論在 CEO 回填實測結果前，一律視為**假設**而非定案；tech-architect 依 `data-source-integration` skill 第 1 步「多來源擇一時寫成比較表放 `docs/adr/`」仍需在實測後另立 ADR 拍板主來源與備援，本文件只是 ADR 的輸入材料。
4. 查證用標的（與腳本一致）：台股上市 = 2330（台積電）、台股上櫃 = 6488、美股 = AAPL。

---

## 1. S-2 台股籌碼面（CEO 裁示最優先）

範圍：三大法人買賣超、融資融券餘額、借券。

### 1.1 候選源總表

| # | 源 | 端點/取得方式 | 更新頻率與時點 | 額度/Rate limit | 授權疑慮 | 整合難度 | 信心等級 |
| - | - | - | - | - | - | - | - |
| 2-1 | TWSE OpenAPI｜三大法人買賣超日報 | `GET https://openapi.twse.com.tw/v1/fund/T86`（推測；`T86` 為 TWSE 傳統盤後資料集代號，OpenAPI 化路徑為猜測，很可能回傳全市場當日清單，需自行以股票代號篩選） | 盤後（推測 T+0 晚間或 T+1 上午更新，確切時點不確定） | 官方 OpenAPI，未見公開文件寫明速率限制；不確定是否需要 API key（傳統上不需要） | 低：官方公開資料，非再散布疑慮小 | 中：與現有 `TwseAdapter`（`app/data/providers/twse.py`）同源、可沿用 `RateLimitedClient`；但回傳形狀（全市場列表 vs 單股查詢）與既有日線 adapter（單股月查詢）不同，parser 需另寫 | 中 |
| 2-2 | TWSE OpenAPI｜融資融券餘額 | `GET https://openapi.twse.com.tw/v1/margin/MI_MARGN`（推測；`MI_MARGN` 為傳統資料集代號） | 盤後 | 同上，未查證 | 低 | 中，同上 | 中 |
| 2-3 | TWSE OpenAPI｜借券（有價證券借貸交易） | 猜測路徑 `GET https://openapi.twse.com.tw/v1/exchangeReport/TWT96U`；**確切資料集代號不確定**，`TWT96U` 為憑印象猜測，很可能是錯的 | 不確定 | 不確定 | 低（若確有公開資料集） | 低～中（若端點存在，parser 與其他 TWSE 資料集同構） | 低 |
| 2-4 | TPEx OpenAPI｜三大法人買賣金額統計表（上櫃對應） | 猜測路徑 `GET https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading`；TPEx OpenAPI 命名規則與 TWSE 不同，路徑高度不確定 | 盤後 | 不確定 | 低 | 中：需與既有 `TpexAdapter`（`app/data/providers/tpex.py`）並列維護，上市/上櫃兩套端點命名習慣不同，parser 無法共用 | 低 |
| 2-5 | TPEx OpenAPI｜融資融券餘額（上櫃對應） | 猜測路徑 `GET https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_trading` | 盤後 | 不確定 | 低 | 同上 | 低 |
| 2-6 | FinMind｜`TaiwanStockInstitutionalInvestorsBuySell` | `GET https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id=<symbol>&start_date=&end_date=&token=` | 盤後（依 FinMind 慣例） | 免費層有 request/hour 限制（確切數字不確定，且是否需登入 token 才能存取此 dataset 不確定） | 低～中：FinMind 條款需人工核對是否允許本產品用途 | 低：與既有 `FinMindAdapter`（`app/data/providers/finmind.py`）同一 base URL 與 token 讀取機制（`FINMIND_API_TOKEN` 環境變數），只需擴充 `dataset` 參數與新的 response 型別 | 中 |
| 2-7 | FinMind｜`TaiwanStockMarginPurchaseShortSale` | 同上，dataset 名稱替換 | 同上 | 同上 | 同上 | 同上 | 中 |
| 2-8 | FinMind｜借券（dataset 名稱不確定） | 同上機制，但**確切 dataset 名稱不確定**（可能是 `TaiwanStockSecuritiesLending` 或其他命名），需人工查 FinMind 官方文件核對 | 不確定 | 不確定 | 不確定 | 同上（若 dataset 存在） | 低 |
| 2-9 | 美股｜無直接對應公開日頻籌碼資料 | 不適用；13F 為季度、延遲 45 天，語意與台股「日頻籌碼」完全不同 | — | — | — | — | 高（結論本身高信心，非端點細節） |

### 1.2 初步結論（未經實測，暫定）

- 台股籌碼面在**端點層級**看起來可行：TWSE/TPEx 官方 OpenAPI 是無需 key、無付費疑慮的公開資料，符合 CEO「台股為主」的優先序，且風險低於美股基本面（無額度衝突）。這與 PRD「優先序建議」第 6 點的判斷方向一致。
- 但**具體資料集代號（尤其借券、TPEx 對應端點）信心偏低**，2-3、2-4、2-5 三項很可能需要 CEO 執行 spike 腳本後失敗（404），屆時需人工到官方 Swagger 目錄（`openapi.twse.com.tw`、`www.tpex.org.tw/openapi`）核對正確路徑，而不是本文件現在就假裝已確認。
- FinMind 作為籌碼面的第二來源（備援或涵蓋 TWSE OpenAPI 沒有的欄位）值得一併驗證，其登入/token 門檻是否會限制免費使用是必答題（比照既有日線 adapter 的 `FINMIND_API_TOKEN` 環境變數機制）。
- **美股籌碼面**：維持 PRD 預設立場——「不適用：美股市場無同類公開日頻籌碼資料」，不強找代理指標。

### 1.3 實測結果（待 CEO 本機執行腳本後回填）

| # | 源 | 實測日期 | HTTP 狀態 | 欄位樣本 | 結論 |
| - | - | - | - | - | - |
| 2-1 | TWSE OpenAPI｜三大法人買賣超日報 | | | | |
| 2-2 | TWSE OpenAPI｜融資融券餘額 | | | | |
| 2-3 | TWSE OpenAPI｜借券 | | | | |
| 2-4 | TPEx OpenAPI｜三大法人（上櫃） | | | | |
| 2-5 | TPEx OpenAPI｜融資融券（上櫃） | | | | |
| 2-6 | FinMind｜三大法人買賣超 | | | | |
| 2-7 | FinMind｜融資融券 | | | | |
| 2-8 | FinMind｜借券 | | | | |

---

## 2. S-1 基本面（台股優先、美股次之）

範圍：EPS、本益比、殖利率、淨值比、月營收（台股）；美股對應可得欄位。

### 2.1 候選源總表

| # | 源 | 端點/取得方式 | 更新頻率與時點 | 額度/Rate limit | 授權疑慮 | 整合難度 | 信心等級 |
| - | - | - | - | - | - | - | - |
| 1-1 | TWSE OpenAPI｜個股日本益比、殖利率及股價淨值比 | `GET https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL`（`BWIBBU` 為 TWSE 傳統資料集代號，OpenAPI 版常見 `_ALL` 後綴代表全市場當日清單） | 每日（盤後） | 同 S-2 官方 OpenAPI，未見明文速率限制 | 低 | 中：與 S-2 的 TWSE OpenAPI 端點可共用同一套 client/rate-limit 基礎設施，但 parser 需另寫（欄位為本益比/殖利率/淨值比，非日線 OHLCV） | 中 |
| 1-2 | 公開資訊觀測站（MOPS）｜上市公司月營收彙總表 | 猜測路徑 `https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_<民國年>_<月>.html`（legacy HTML 表格，非 JSON API，且疑似 big5 編碼） | 每月（法定申報截止日後，約次月 10 日前） | 不確定；非 JSON API 故無「rate limit」概念，但仍應節流避免頻繁掃描 | 低（官方公開資料）但**格式非機器友善**，需額外寫 HTML/編碼解析層，增加脆弱度 | 高：非 JSON、疑似 big5、需額外 HTML parser 與編碼處理，與現有 adapter 的 JSON-first 慣例落差最大 | 中（端點路徑）／低（是否真為此格式） |
| 1-3 | 公開資訊觀測站（MOPS）｜財報 EPS | 是否有可程式化端點**未確認**，MOPS 財報查詢傳統上是網頁表單／XBRL 下載，非簡單 REST API | 季（財報申報後） | 不確定 | 低 | 高（若僅有網頁/XBRL 下載，需額外解析層或改走 FinMind 財報 dataset 代替） | 低 |
| 1-4 | FinMind｜`TaiwanStockFinancialStatements` | `GET https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=<symbol>&...` | 季 | 同 S-2 FinMind 說明 | 低～中 | 低（沿用既有 FinMind adapter 機制） | 中 |
| 1-5 | FinMind｜`TaiwanStockMonthRevenue` | 同上機制 | 月 | 同上 | 同上 | 低 | 中 |
| 1-6 | Alpha Vantage｜`OVERVIEW`（含 GICS Sector） | `GET https://www.alphavantage.co/query?function=OVERVIEW&symbol=<symbol>&apikey=<key>` | 不確定更新頻率（推測隨財報季更新，非日更） | **與 Phase 7 日線查詢共用同一個 25 req/day 免費額度**——這是 S-1 必答題（PRD 風險與依賴第 2 點） | 低：官方 key、條款明確（同既有 `AlphaVantageAdapter` 結論） | 低：與既有 `app/data/providers/alpha_vantage.py` 同一套額度帳本（`QuotaLedger`）、環境變數（`ALPHA_VANTAGE_API_KEY`）機制可直接沿用，但需額外設計「基本面查詢是否計入同一額度池」的分配策略（ADR-0005 額度分配可能需擴充） | 高（端點存在）／未知（額度分配策略） |
| 1-7 | Alpha Vantage｜`EARNINGS` | 同上機制 | 季 | 同上共用額度疑慮 | 同上 | 同上 | 高 |
| 1-8 | yfinance fundamentals（非官方） | 猜測端點 `GET https://query1.finance.yahoo.com/v10/finance/quoteSummary/<symbol>?modules=defaultKeyStatistics,financialData,summaryDetail,earnings`（`yfinance` 套件內部呼叫的未公開端點之一，與既有 `app/data/providers/yfinance.py` 用的 `v8/finance/chart` 是同一家但不同端點，**未驗證過**） | 不確定 | 無官方額度概念，但無 SLA、隨時可能被封鎖或改版 | 高：非官方、無授權條款保障，與既有 yfinance 日線備援同級風險 | 低～中：可沿用既有 `_REQUEST_HEADERS`（`User-Agent: Mozilla/5.0`）慣例，但需另寫 parser | 低 |

### 2.2 初步結論（未經實測，暫定）

- 台股本益比/殖利率/淨值比（1-1）路徑最乾淨：官方 OpenAPI、免 key，整合難度中等，建議優先驗證與接入。
- 台股月營收/財報 EPS（1-2、1-3）是本次信心最低的一塊——MOPS 官方管道疑似不是機器友善的 JSON API，很可能需要退而求其次改走 FinMind（1-4、1-5）。**這正是 spike 要回答的問題，本文件不預先假裝 MOPS 有 JSON 端點**。
- 美股基本面（1-6、1-7）的**核心矛盾**是 PRD 已點名的額度共用問題：若接入 Alpha Vantage `OVERVIEW`/`EARNINGS`，會直接侵蝕 Phase 7 日線查詢的 25 req/day 額度。在 CEO 尚未回答「實際持倉台股/美股結構」（PRD 開放問題 3）前，本文件**不建議**貿然接入，傾向維持 PRD 優先序（台股籌碼優先於美股基本面）。
- `OVERVIEW` 的 GICS Sector 欄位若確認可用，可一次查證兩用（供下一階段美股產業欄位使用，PRD 已點名）。
- yfinance fundamentals（1-8）風險與既有 yfinance 日線備援同級（非官方、無 SLA），只建議作為美股基本面的最後備援，不作主來源。

### 2.3 實測結果（待 CEO 本機執行腳本後回填）

| # | 源 | 實測日期 | HTTP 狀態 | 欄位樣本 | 結論 |
| - | - | - | - | - | - |
| 1-1 | TWSE OpenAPI｜本益比/殖利率/淨值比 | | | | |
| 1-2 | MOPS｜月營收彙總表 | | | | |
| 1-4 | FinMind｜財報 | | | | |
| 1-5 | FinMind｜月營收 | | | | |
| 1-6 | Alpha Vantage｜OVERVIEW | | | （若未設 `ALPHA_VANTAGE_API_KEY` 則為 SKIPPED，請 CEO 視情況另外設定 key 測試） | |
| 1-7 | Alpha Vantage｜EARNINGS | | | 同上 | |
| 1-8 | yfinance｜quoteSummary | | | | |

---

## 3. S-3 消息面（最後盤點，PRD 預設傾向本期不做）

範圍：個股新聞/公告。

### 3.1 候選源總表

| # | 源 | 端點/取得方式 | 更新頻率 | 額度/Rate limit | 授權疑慮 | 整合難度 | 信心等級 |
| - | - | - | - | - | - | - | - |
| 3-1 | MOPS｜重大訊息公告 | 傳統上是網頁表單查詢（POST，疑似 big5 編碼），本次猜測 `POST https://mops.twse.com.tw/mops/web/ajax_t05st02`；**無官方 JSON API 文件**，欄位/表單參數皆為猜測 | 即時（公司申報後） | 不確定；非典型 REST，無法評估 rate limit | 低（官方公告，但語意是「公司公告」非「新聞」，需誠實區分，PRD 已載明） | 高：POST 表單 + 疑似 big5 編碼 + 無官方 schema，是本次盤點中整合難度最高的一項 | 低 |
| 3-2 | FinMind｜`TaiwanStockNews`（是否存在待驗證） | 同 FinMind 機制，**dataset 是否真的存在完全不確定** | 不確定 | 不確定 | 不確定 | 若存在則低（沿用既有機制），若不存在則不適用 | 低 |
| 3-3 | Alpha Vantage｜`NEWS_SENTIMENT` | `GET https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=<symbol>&apikey=<key>` | 準即時（依 AV 更新頻率） | **同樣共用 25 req/day 額度**；且其 sentiment 分數是第三方模型輸出，PRD 明文要求風控官單獨核准才能呈現 | 中：條款明確但 sentiment 分數的呈現本身是風控審查標的，非純資料源問題 | 低（端點機制與 1-6/1-7 相同），但**呈現層**需風控官另行核准，不是單純技術整合難度 | 高（端點存在）／需風控介入（能否呈現） |
| 3-4 | 美股｜其他免費新聞源 | 未特別調查（PRD 消息面本身即為最低優先，且 PRD 預設傾向本期不做） | — | — | — | — | 不適用 |

### 3.2 結論（依 CEO 交辦，只需盤點並下結論，不強求可行）

**初步結論：消息面延續 PRD 的保守預設立場——「無合規、可持續、品質可接受的免費源」，建議本期不做。**

理由：
1. 台股唯一乾淨的官方源（MOPS 重大訊息）在端點層級就是本次盤點中整合難度最高的一項——無官方 JSON API、疑似需要 POST 表單與 big5 編碼解析，這類「網頁抓取」性質的接入方式本身就比其他來源脆弱，且與 `data-source-integration` skill「不用假資料或內插值冒充真實資料」的紅線無關但與「查證當下文件」原則相悖（沒有文件可查證）。
2. FinMind 是否真的有新聞 dataset 完全不確定，屬本次盤點信心最低的一項。
3. 美股 Alpha Vantage `NEWS_SENTIMENT` 技術上可行，但（a）進一步侵蝕已經吃緊的 25 req/day 共用額度；（b）其 sentiment 分數依 PRD 明文需風控官單獨核准，即使技術上抓得到，呈現與否仍卡在風控審查而非資料源本身。
4. 消息面對台股主軸（CEO 裁示台股為主）幾乎沒有乾淨的免費選項，對美股（次要市場）雖有 Alpha Vantage 路徑但要犧牲共用額度且需額外風控審查。

**此結論待 CEO 執行 spike 腳本、實測結果回填後確認或推翻**——若 MOPS 重大訊息端點實測結果比預期好（例如存在乾淨的 JSON API 是本文件未查到的），或 FinMind 新聞 dataset 確實存在且免費額度充足，本結論應被推翻，改為可行路徑並回到 FR-C5 的「可行路徑」分支。若結論維持不可行，依 PRD AC-C5.2，此即合格的交付結果（不是失敗）：決策中樞頁消息面區塊顯示「本產品目前不提供消息面資料」＋原因。

### 3.3 實測結果（待 CEO 本機執行腳本後回填）

| # | 源 | 實測日期 | HTTP 狀態 | 欄位樣本 | 結論 |
| - | - | - | - | - | - |
| 3-1 | MOPS｜重大訊息公告 | | | | |
| 3-2 | FinMind｜新聞 | | | | |
| 3-3 | Alpha Vantage｜NEWS_SENTIMENT | | | （若未設 key 則為 SKIPPED） | |

---

## 4. 與現有 adapter 架構整合的共通觀察

參考 `apps/stock-desk/backend/app/data/providers/`（`twse.py`、`tpex.py`、`finmind.py`、`alpha_vantage.py`、`yfinance.py`）既有慣例：

1. **共通基礎設施可重用**：`RateLimitedClient`（`app/data/http.py`）、`FinMindAdapter` 的 token 讀取機制（`FINMIND_API_TOKEN` 環境變數）、`AlphaVantageAdapter` 的 `QuotaLedger` 額度帳本、`MarketDataProvider` 抽象介面的 `as_of`/`source` 欄位約定，S-1/S-2/S-3 若接入，都應沿用而非重造。
2. **新的抽象介面缺口**：既有 `MarketDataProvider` 是為「單股日線 OHLCV」設計的抽象（`get_daily_bars(symbol, start, end) -> ProviderResult`）；基本面/籌碼面/消息面的回傳形狀完全不同（單一快照 vs 時間序列 vs 列表），**不能直接塞進現有介面**，需要 tech-architect 定義新的抽象（例如 `FundamentalsProvider`、`ChipDataProvider`、`NewsProvider`），這是 PRD 開放問題 6(a) 明確指名 tech-architect 的事項，本盤點不越權代定。
3. **全市場清單 vs 單股查詢的形狀落差**：多個 TWSE OpenAPI 候選端點（1-1、2-1、2-2）疑似回傳「當日全市場清單」而非「單股查詢」，若屬實，代表這類 adapter 的快取策略應該是「整批快取當日全市場資料、查詢時記憶體篩選」而非既有日線 adapter「逐股按月請求」的模式——會是不同的快取與 TTL 設計，需一併記錄供 tech-architect 訂 ADR 時參考。
4. **額度分配是 S-1 美股面向的架構級決策**：Alpha Vantage 若同時服務日線、`OVERVIEW`、`EARNINGS`、`NEWS_SENTIMENT`，25 req/day 的分配策略（例如「基本面查詢設遠長於日線的 TTL，優先保留額度給日線」）是 ADR 等級的決策，不是單一 adapter 的實作細節，比照 ADR-0005 先例辦理。
5. **未查證揭露的一致慣例**：若任一來源進入 build，比照現有六個 adapter 檔頭與 `tests/fixtures/README.md` 的慣例——程式碼檔頭與 fixture README 都要載明「查證日期」與「NOT re-verified against a live response」聲明，且此聲明不因上線而移除（PRD AC-C3.5/AC-C4.5 已明文要求）。

---

## 5. 降級策略（依 skill 第 6 步，先寫方向，實作待 ADR）

三個面向若接入，一律遵守既有降級鏈慣例：**主來源失敗 → 備援來源（若有）→ 本機快取（明示延遲）→ 明確錯誤狀態**，每層使用者可見狀態沿用既有 `DataMetaStatusBadge` 機制（fresh/backup/cached_stale/unavailable）。三個面向各自的主/備援配對（例如 S-2 台股主來源用 TWSE OpenAPI、備援用 FinMind）待實測結果確認雙邊皆可用後，由 tech-architect 於 ADR 中拍板，本文件不預先代定。

---

## 6. 待確認事項與下一步

1. **CEO**：於本機（有網路）執行 `uv run --with httpx python scripts/spike_phase8_sources.py` 或 `python scripts/spike_phase8_sources.py`（需先 `pip install httpx`），將輸出的「HTTP 狀態 / 欄位樣本 / 結論」逐筆回填本文件第 1.3、2.3、3.3 節的空欄。
2. 若要一併測試需要 key 的來源（Alpha Vantage `OVERVIEW`/`EARNINGS`/`NEWS_SENTIMENT`），CEO 需自行在本機環境變數設定 `ALPHA_VANTAGE_API_KEY`（免費申請）；未設定則腳本會直接跳過並在報告中明列跳過條件，不會嘗試用假值或內建金鑰。
3. 回填後，data-engineer 依實測結果修訂本文件的「初步結論」段落為「確認結論」，並將確定可行的來源交棒給 tech-architect 撰寫 ADR（比照 ADR-0003/ADR-0005 格式），拍板主來源、備援、快取 TTL 與額度分配策略。
4. S-3 若實測結果推翻本文件「本期不做」的預設結論，需回報 product-manager 更新 PRD FR-C5 的走向；若維持「本期不做」，本文件第 3.2 節結論即可直接作為 PRD AC-C5.2 的依據，交棒 risk-compliance-officer／tech-writer 核對「本產品目前不提供消息面資料」的文案。
