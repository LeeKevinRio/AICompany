# stock-desk 全公司產品審視（資料視角）

- 審查者：data-engineer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## stock-desk 資料面審視（data-engineer，唯讀）

範圍說明：我只讀程式、文件和前端，沒有改任何檔案，也沒有讀 `.env`、碰 `*.db` 或連外網，所以沒有任何真實來源回應可佐證。`.env.example` 的讀取被權限拒絕，不影響結論。我沒有跑測試，結論都來自靜讀程式碼。下面「已驗證」的說法一律指團隊文件自述的 CEO 本機驗證，不是我驗證的。

### 一、評分（1～5）

| 面向 | 分數 | 依據 |
|---|---|---|
| 合理性 | 3 | 台股主線扎實：TWSE 加 TPEx 是官方來源，FinMind 與 TWSE 在 3 檔、7 個交易日有 21/21 筆收盤價與成交量完全吻合（`twse.py:13-24`）。降級階梯完整，沒有假資料或內插值，AV 額度先預留再呼叫。但有三個缺口：(1) 台股價格沒有還原權息，除權息資料只有「預告表」且只涵蓋上市（`dividends/providers.py:90-107`）。(2) 美股個股備援 yfinance 沒被真實驗證過（`yfinance.py:59-65`）。(3) 資料品質檢查函式沒有接進正式流程（見問題 1）。 |
| 好用性 | 2 | 證券目錄與除權息要靠人在後端主機手動跑 CLI，目錄同步排程沒有（`directory/sync.py:1-12`、`scheduler.py` 無 directory job）。FinMind 備援要自備 token。美股要設兩個環境變數，否則主來源整層被跳過。新標的第一次載入要逐月抓約 19 次，上櫃股還會先白跑一輪 TWSE。 |
| 簡易清楚 | 3 | 優點：總覽每檔價格旁有「MM/DD 收盤」（`DataStatusBadge.tsx:46-52`），詳細頁主視圖有「資料截至」徽章（`page.tsx:271-275`），資料不足有明顯的框線標籤。缺點：「資料來源：twse」藏在收合的「詳細」裡（`page.tsx:404-420`）。快取的精簡標籤一律只寫「快取資料」，分不出「快取已是最新」和「快取已落後」（`DataMetaStatusBadge.tsx:123-126`）。設定頁的來源表是靜態配置，不是健康狀態，而且台股那一列和實際行為不符。 |

### 二、最重要的 5 個問題

**1. 資料品質檢查寫了但沒接進正式流程，TWSE 解析也沒有欄位防呆**
- `check_price_bars` 涵蓋重複列、未來日期、OHLC 不一致、缺交易日（`quality.py:41-63`）。我 Grep 整個 `app/`，它只有定義，沒有任何呼叫者。`service.py:28` 只引入幣別檢查。
- 部分緩衝仍在：cache 主鍵 upsert 去重（`cache.py:219`）、丟棄未收盤 K 棒（`service.py:941-957`）、非正值收盤價防護（`price_guard.py`）。但 data-source-integration skill 要求的「異常浮上檯面」沒有完全做到。
- TWSE 用固定欄位位置解析（`twse.py:168-176`），沒有 TPEx 那樣的表頭比對（`tpex.py:169-194`）。TWSE 若調整欄位順序，數字型欄位會被靜默錯位。
- 解析失敗的列只記 debug 就跳過，`complete` 仍是 True（`twse.py:159-163`、`twse.py:148`）。格式一變，就會變成「少幾天資料」而且沒人知道。
- 唯一的交叉驗證是一次性的 CEO 本機驗證，執行期沒有常駐比對。

**2. 目錄與除權息的新鮮度使用者看不到，而且靠手動**
- `is_synced` 只看「筆數大於 0」（`directory/store.py:167-169`）。UI 顯示「已同步」，卻沒有同步日期，只有「本次查詢時間（非目錄同步時間）」（`DirectorySection.tsx:67,80-82`）。每列資料其實都有 `as_of`（`api/directory.py:49-75`），只是沒露出來。
- 新上市股票、新上櫃股票搜尋不到。持倉的產業別留空會讓單一產業佔比上限變成「無法評估」（見 `work/stock-desk-D4-資料來源措辭.md` 第五節對 `limits.py:612-621` 的引述）。
- 除權息排程有了（`scheduler.py:688-701`），但來源是預告表，只列未來的除權息日，沒有歷史可回補（`dividends/providers.py:99-107`）。覆蓋範圍只能從開始跑那天往後累積，上櫃完全沒有（同檔 90-97 行）。
- `signals/` 與 `advice/` 的程式碼 Grep 沒有任何除權息處理。技術指標和回撤都吃未還原的收盤價。回測有標「未還原」，建議卡和回撤沒有同等揭露。

**3. 美股主來源在預設情境下形同虛設**
- AV 免費方案只回約 100 根日線（`alpha_vantage.py:145`、`alpha_vantage.py:335-343`）。預設觀察窗是 540 個日曆天（`signals/window.py:22`）。
- 後果：每檔美股第一次取價，AV 先預留並消耗 1 個額度（`alpha_vantage.py:265-270`），之後一定因為涵蓋不足而自己放棄，再轉給 yfinance。yfinance 是非官方端點，個股角色沒被驗證過。
- 之後每天增量只抓最後一根 K 棒所在月份起（`service.py:650-675`），AV 可能接手，序列就變成「yfinance 的頭加 AV 的尾」。系統有如實揭露拼接（`service.py:108-111`），但這是設計造成的常態，不是偶發。
- 設定頁仍把 AV 列為「主要來源」（`DataSourcesSection.tsx:44`），和上面的實況有落差。

**4. 台股失敗原因說不清楚，設定頁對台股鏈的描述有誤**
- 三個台股 adapter 失敗時都不帶 `reason`（`twse.py:125-140`、`tpex.py:260-275`、`finmind.py:74-81`）。FinMind 沒設 token 時也只記 log，回傳沒有原因（`finmind.py:102-106`）。
- 使用者會看到泛稱的「最近一次向來源取得資料未成功」（`service.py:98`），或「（主來源、備援與快取皆無）」（`services/market.py:46`）。後者在沒設 FinMind token 時並不真實，因為 FinMind 根本沒被嘗試。
- 設定頁台股列沒有列「本地快取優先」層（`DataSourcesSection.tsx:19-20,40`），但 `deps.py:123` 的台股 `cache_first=True`。
- README 寫台股「24h 快取 TTL」且「無額度限制」（`README.md:228`）。前者已被 ADR-0009 的依交易日判斷取代。後者沒有查證依據。

**5. 首次載入慢，且上櫃股有一輪白工**
- 台股每個日曆月一次 HTTP，540 天約 19 次（`twse.py:94`），每次最小間隔 0.5 秒（`twse.py:80`），在請求內同步跑完，光節流就約 10 秒。
- 上櫃股的流程是 TWSE 先走完全部月份，每月都得到 `stat != OK` 然後空手而回（`twse.py:154-155`），再輪到 TPEx（`deps.py:119-121`）。目錄其實已經知道這檔是上市還是上櫃，但階梯沒用。
- `deps.py:222-224` 的註解自承 12 個階梯跑一輪是「minutes of blank screen」。
- 每秒 2 次對 TWSE 是否會觸發封鎖，沒有查證。社群常聽到類似說法，但我沒辦法在此環境確認，請 CEO 本機實測。
- 假日、颱風假沒有建模（`freshness.py:36-40`）。這只是每個冷卻期多一次請求，風險低。

### 三、5 個具體建議

| # | 建議 | 投入 | 效益 |
|---|---|---|---|
| 1 | TWSE 改成表頭驅動欄位對應（照 TPEx 作法）。解析失敗的列算「不完整」並附原因。把 `check_price_bars` 接到寫入快取之前，異常以 reason 與 log 浮上來，不靜默吞掉。 | 中（1～2 天） | 高：堵住欄位變更時最危險的靜默錯誤，也補上 skill 紅線 |
| 2 | 所有台股 adapter 補上具體失敗原因，區分「未嘗試（沒設 token）」與「嘗試失敗」。改正 `NO_BARS_REASON` 的「皆無」說法。更正設定頁台股列與 README 的 TTL／額度描述。文案要走風控審查。 | 小（半天加審查） | 高：消除會誤導的說法 |
| 3 | 抓月資料時，第一個月 `stat != OK` 且完全無資料就停止，不要再跑完 19 個月。上櫃股優先走 TPEx，依目錄的來源欄決定。 | 小（半天） | 高：新標的與暖機載入時間大幅縮短，也降低打 TWSE 的次數 |
| 4 | 目錄同步加入排程（例如每週一次）。API 與設定頁顯示目錄與除權息「最近成功同步日期」。順手把設定頁的靜態來源表改成每個來源的最近成功時間。 | 中（1～2 天） | 高：直接回答「這個數字哪天、從哪來、是否過期」，也去掉手動維運負擔 |
| 5 | 美股：用 CEO 本機跑一次 yfinance 個股驗證。AV 只在短窗口使用，或預設窗口超過 100 根時不預留額度。設定頁的主要來源列依實況改寫。 | 小到中 | 中：保住 AV 的 25 次額度，避免每檔第一次都白燒 |

### 四、需要 CEO 決策

1. **美股定位**：維持現況（實質上靠未驗證的 yfinance）、付費升級 AV（我不憑記憶報價，需查證當下方案價格）、或把美股標成實驗性功能。
2. **除權息與還原價**：要不要投入還原價資料來源（含上櫃與歷史）？不投入的話，要讓建議卡和回撤也像回測一樣明講「未還原」。這涉及面向使用者的建議文案，須經風控。
3. **目錄與除權息同步自動化**：是否授權排程定期呼叫 TWSE／TPEx OpenAPI。
4. **FinMind token**：是否改成必備。目前它是選用的，沒設就悄悄少一個備援，台股實際上只剩 TWSE 和 TPEx。
5. **本機代跑查證**（本沙盒無外網）：
   - TPEx 第二次驗證，確認真的能解析出 K 棒（`tpex.py:11-14` 自承尚欠）。
   - yfinance 美股個股角色。
   - TWSE 在每秒 2 次下是否被限流。

### 相關檔案（絕對路徑）
- `/home/user/AICompany/apps/stock-desk/backend/app/data/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/quality.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/tpex.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/finmind.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/alpha_vantage.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/api/deps.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/market.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/directory/sync.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/dividends/providers.py`
- `/home/user/AICompany/apps/stock-desk/frontend/app/settings/DataSourcesSection.tsx`
- `/home/user/AICompany/apps/stock-desk/frontend/app/settings/DirectorySection.tsx`
- `/home/user/AICompany/apps/stock-desk/frontend/app/components/DataMetaStatusBadge.tsx`
- `/home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/page.tsx`
- `/home/user/AICompany/apps/stock-desk/README.md`
