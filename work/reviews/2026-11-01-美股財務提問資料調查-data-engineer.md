# CEO 提問（產品現況、財報／FCF／回購／財測資料可得性、台美差異）資料調查

- 審查者：data-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論（給 CEO 的白話版）

**這次是純調查。我沒有改任何程式碼，也沒有 commit。**

**重要前提：我的沙盒對外網路被擋。** 我試著連 SEC EDGAR、TWSE OpenAPI、MOPS，三個都回 `CONNECT tunnel failed, 403`。所以第二部分所有外部來源的描述，都是依專業知識寫的，沒有任何一項實測過。第二部分每項都標了可信度，「需查證」的項目請當成待驗證，不要當事實。

### Q1：財測呢？目前有嗎？
- **我們的產品內：沒有。** 產品裡完全沒有財報、現金流、自由現金流（FCF）、庫藏股／回購、財測／guidance 的資料或畫面。我全專案搜過這些關鍵字，零命中（`eps` 唯一命中是 `dirdef/definition.py:8` 的數學 epsilon，不是每股盈餘）。
- **容易混淆的名稱：** 程式裡有個叫 `forecast` 的目錄，它是本系統自己對「未來 3／5 日方向」的預測紀錄帳，**不是公司財測**。而且它的寫入閘門是關的，沒接任何 API 路由（`app/forecast/__init__.py:1-5`）。
- **市場上：**
  - 美股公司有給 guidance，但沒有規定要給，通常寫在財報新聞稿和電話會議。免費的結構化來源基本上沒有，分析師共識預估通常要付費。
  - 台股現在沒有強制財測（大致確定，需查證廢止年份）。公司可自願公布，法說會的展望多是簡報或口頭，沒有結構化資料。
- **更正你的認知：** 你說的「自由現金流拿來回購」，FCF 和回購兩者都可以從財報算出來，但不是公司直接給的一個欄位。美股用免費官方資料算得出來。台股的資料源比較不確定，見下面。

### Q2：這些功能台股有嗎？還是只有美股？
- **台股和美股都有。** 財報（含現金流量表）是法定要公布的，兩邊都有。差別在取得難易：
  - 美股：SEC EDGAR 有免費、官方、結構化的 API，品質最好。
  - 台股：官方有但偏網頁／檔案型，結構化程度和覆蓋範圍我不能確定，免費 API 友善度較差。FinMind（我們已經在用它做價格備援）可能有現金流量表 dataset，需查證。
- **財測：** 美股沒有免費結構化來源。台股已非強制，也沒有結構化來源。兩邊都缺。
- 詳細對照見第二部分第 4 題的表。

### Q3：我們有做美股功能嗎？可以另做一個美股頁籤嗎？
- **有，但只做了一半，而且沒有實測過。**
  - 持倉、日線 K 線、技術指標、建議卡、槓桿 ETF 專章都支援 `US`。
  - 但美股資料鏈（Alpha Vantage 主、yfinance 備援）「尚未以真實 API key 對外部服務實際發送過請求」，這是產品設定頁自己寫的揭露（`DataSourcesSection.tsx:65`）。
  - 美股沒有代號搜尋（代號目錄只收台股上市櫃），沒有美股專屬頁面，沒有基本面。
- **可以另做美股頁籤，技術上可行。** 現有導覽列只有 5 個頁籤（`NavBar.tsx:283-289`），多一個不難。
- **有兩個前置條件：**
  - 基本面在 2026-10-26 的產品審視中被列為「凍結」（`work/reviews/2026-10-26-產品審視-product-manager.md:168`），要做需要你解凍。
  - 基本面資料需要新的資料結構，現有介面是為價格設計的，放不進去（`work/research/2026-10-15-外部prompt需求對照盤點.md:280`），要先由 tech-architect 出 ADR。
- **資料面最小方案：** SEC EDGAR 免費（財報、現金流、回購金額）加上現有價格鏈，成本 $0。排版交美術部門，等 PM 出規格、資料欄位確定後再接。

---

## 各部門回報

### 一、產品現況（讀碼）

#### 1.1 支援哪些市場
- **只有 TW 和 US 兩個。** 型別是 `Market = Literal["TW", "US"]`，三處定義：
  - `app/data/interface.py:23`
  - `app/positions/models.py:33`
  - `shared/market-currency.json` 的映射：TW→TWD、US→USD（`app/positions/models.py:67`）
- **`market_resolver`：**
  - 組裝在 `app/api/deps.py:92-145`（`_default_resolver`）。
  - TW 梯子：TWSE 主，TPEx、FinMind 備援，再接快取（`deps.py:125-134`）。
  - US 梯子：Alpha Vantage 主，yfinance 備援（`deps.py:135-144`）。
  - 無 adapter 的市場回 `insufficient_data`，不是 500（`app/services/market.py:5-13`）。
- **`index_resolver`：**
  - 組裝在 `deps.py:149-189`。
  - 只走 yfinance 的指數端點，只收 `^NDX`、`^GSPC`、`^TWII` 三個（`app/data/providers/yfinance.py:150-151`）。Alpha Vantage 不碰指數，避免吃掉額度。
  - 基準指數：TW 用 `^TWII`，US 用 `^GSPC`（`app/services/index.py:309-312`）。
- **`/api/bars/{symbol}`：** `market` 參數預設 `"TW"`（`app/api/bars.py:86`）。
- **`app/leverage/index_mapping.py`：**
  - 只做「槓桿 ETF 對應標的指數」。共 17 列：12 列有對應（NDX、GSPC、TWII），5 列標示取不到（台灣50、美債20+年、半導體）。
  - 全部 `verified=False`、`MAPPING_VERIFIED_ON=None`（`index_mapping.py:44-50`）。這與基本面無關。
- **前端：**
  - 市場選單有 TW／US，美股選項固定帶「（資料來源未經真實環境驗證）」（`app/lib/format.ts:73-78`）。
  - 個股頁讀 `?market=`，預設 TW（`position/[symbol]/page.tsx:91-92`）。
  - 導覽列沒有任何美股專屬頁籤。
  - 代號目錄只同步 TWSE／TPEx（`app/directory/providers.py`），所以美股代號搜尋不存在，只能手動輸入並選市場。
  - 族群動能、籌碼相關功能是台股限定（持倉表單的產業欄位只對 TW 啟用，`ManualAddForm.tsx:293,304-310`）。

#### 1.2 有沒有基本面資料
**完全沒有。** 專案內關鍵字搜尋（財報、現金流、FCF、EPS、營收、回購、庫藏、財測、guidance、fundamental）在 `apps/stock-desk` 下，除了無關命中（`buildFooterGuidance` 是頁尾揭露文案函式）之外，沒有基本面資料或邏輯。既有文件也一致：
- `work/research/2026-10-15-外部prompt需求對照盤點.md:277`：「後端依賴與 provider 都沒有基本面來源」。
- `work/stock-desk-新定位-需求總綱與分期-2026-10-15.md:25,312-324`：NP-D5 基本面「未實作」。
- 資料源盤點 spike S-1（`work/stock-desk-phase8-需求.md:98-100`）從未執行，結果表全空（`總綱:546`，0-10）。

四個目錄各自在做什麼：

| 目錄 | 實際用途 | 與公司財測的關係 |
|---|---|---|
| `app/dividends` | 台股 TWSE「除權除息預告表」（`TWT48U_ALL`）事件，用來把歷史價格做除權息還原，只供回測（`dividends/__init__.py`、`providers.py:337-340`） | 無關。它是「公司已宣告的配股配息日程」，不是財報或財測。只有 TW adapter，美股回測沒有除息還原（我讀到的只有 `TwseDividendAdapter`） |
| `app/forecast` | 預測紀錄帳（ADR-0027）：記錄「本系統自己對 3／5 日方向的判斷」以便事後驗證。寫入閘門關閉，沒接 `app.main`／`app.scheduler`，無 API、無儲存（`forecast/__init__.py:1-5`） | **完全不是公司財測。** 這是系統對價格方向的預測，不是公司對營收或獲利的預估 |
| `app/outlook` | 上述 forecast 的計算零件：波動度 sigma、族群等權籃子序列、缺漏項結構。純函式，未接線（`outlook/__init__.py:1-11`） | 同上，無關 |
| `app/research` | 內部研究專用的「含已知偏誤」族群動能分析，隔離在獨立資料庫檔，API 與排程碰不到（`research/__init__.py`、`research/sector_biased/__init__.py`） | 無關 |

「財測」兩種意思的差別：
- **公司財測／guidance：** 公司管理層對自己未來營收或獲利的預估，是基本面資訊，我們沒有。
- **系統 forecast：** 本系統對股價未來方向的推估，是技術面衍生物，不是任何公司給的。

#### 1.3 外部資料源 adapter 現況
環境變數只列名稱，沒讀值。

| Adapter | 提供 | 市場 | 限流（程式內） | 金鑰環境變數 |
|---|---|---|---|---|
| TWSE `STOCK_DAY`（`providers/twse.py`） | 上市個股日線，一次一個月 | TW | 最小間隔 0.5s + 指數退避 | 無 |
| TPEx（`providers/tpex.py`） | 上櫃個股日線 | TW | 0.5s | 無 |
| FinMind（`providers/finmind.py:71`） | `TaiwanStockPrice` 日線（備援） | TW | 0.3s | `FINMIND_API_TOKEN` |
| TWSE OpenAPI 快照（`twse_snapshot.py`、`dividends`、`directory`） | 全市場日線、公司基本資料／產業別、除權息預告、代號目錄 | TW | 0.5s | 無 |
| Alpha Vantage（`providers/alpha_vantage.py:147`） | 美股日線（主），僅個股，不碰指數 | US | 本地額度帳本，約 25 req/day 預算（`data/freshness.py:138`），自行節流預設 12s | `ALPHA_VANTAGE_API_KEY`，另有 `ALPHA_VANTAGE_DAILY_LIMIT`、`ALPHA_VANTAGE_SAFETY_MARGIN`、`ALPHA_VANTAGE_MIN_INTERVAL_SECONDS`、`QUOTA_RESET_TZ` |
| yfinance（`providers/yfinance.py`） | 非官方 chart 端點：美股備援、三個指數、USD/TWD 匯率備援 | US、指數 | 1.0s | 無 |
| 台灣銀行匯率（`providers/fx.py`） | USD/TWD 日匯率 CSV（現被反爬挑戰頁擋，退到 yfinance，ADR-0011） | FX | 0.5s | 無 |

其他環境變數（非資料源）：`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH`、`ALERT_DISCORD_WEBHOOK_URL`、`ALERT_TELEGRAM_BOT_TOKEN`、`ALERT_TELEGRAM_CHAT_ID`、`SCHEDULER_DATA_INTERVAL_MINUTES`、`SCHEDULER_ALERT_INTERVAL_MINUTES`。

共通機制是 `app/data/http.py` 的 `RateLimitedClient`：最小間隔、最多 3 次重試、退避 1／2／4 秒。價格資料已有 `as_of` 與 `source`。

**驗證狀態：**
- TW 的 TWSE 與 FinMind 在 2026-08-16 經 CEO 本機實測，兩源 21/21 日線筆數相符。TPEx 端點可達，但是否真能解析出 bar，原註記仍欠一次確認（`tpex.py:7-21`）。
- 美股鏈（Alpha Vantage、yfinance）全未實測，ticker 轉換對照表也全是未驗證（`providers/us_symbols.py` 文件字串）。

### 二、資料可得性

以下全部依專業知識，沙盒無法實測。這是市調的「待驗證假設清單」，不是已驗事實。

#### 2.1 自由現金流（FCF）
- **定義（確定）：** FCF = 營業活動現金流量（OCF）− 資本支出（CapEx）。要注意：
  - FCF 不是會計準則下的法定科目。各公司自己公布的「FCF」口徑不一（有的另扣租賃）。我們自己算的應標「OCF 減 CapEx 的標準化算法」，不要冒充公司公布值。
  - 金融業（銀行、保險）的現金流結構不同，FCF 對它們沒有意義（確定）。
  - 兩邊的現金流量表都是年初至今累計（YTD）。要得單季值需自行相減，Q4 = 全年 − 前三季（大致確定）。
- **美股來源（大致確定）：** SEC EDGAR XBRL API（`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`，另有 `companyconcept`、`frames`）。
  - 免費、無需金鑰；要求請求帶可聯絡的 User-Agent，公平使用上限約 10 req/s（需查證現行數字）。
  - 常用標籤：OCF 為 `NetCashProvidedByUsedInOperatingActivities`；CapEx 常見 `PaymentsToAcquirePropertyPlantAndEquipment`，但公司間標籤不一致（需查證／需做對照與缺漏回報，不可補值）。
  - 代號要先對應到 CIK（SEC 提供 ticker→CIK 對照檔，需查證確切路徑）。
- **台股來源：**
  - 官方為公開資訊觀測站 MOPS 的綜合損益表、資產負債表、現金流量表。網頁查詢確定存在；有無穩定的程式化端點需查證。
  - TWSE OpenAPI 有上市公司財報類資料集（`t187ap` 系列，例如 `t187ap03_L` 公司基本資料已被本專案實際使用；損益、資產負債集我認為存在，但**現金流量表是否在 OpenAPI 內：需查證**）。TPEx 對應上櫃集：需查證。
  - FinMind 應有現金流量表 dataset（名稱我記得是 `TaiwanStockCashFlowsStatement`，需查證）；免費層限額約數百次／小時（需查證現行數字）。
- **更新頻率與時間落差：**
  - 美股（確定）：10-K 於會計年度結束後，大型加速申報者 60 天、加速申報者 75 天、一般 90 天；10-Q 於季末後，大型加速申報與加速申報者 40 天、一般 45 天。EDGAR 資料在申報後很快更新（延遲量級需查證）。
  - 台股（大致確定）：慣例截止日為年報次年 3/31、Q1 5/15、Q2 8/14、Q3 11/14。證交法第 36 條曾修訂，法定天數細節需查證。
  - 以今天 2026-11-01 為例：台股 Q3 財報尚未全部公布，截止日約 11/14，美股 Q3 10-Q 已陸續公布中。
  - 月營收為台股特有：次月 10 日前公布（大致確定），是台股相對美股較及時的指標。

#### 2.2 股票回購（庫藏股）
- **美股：**
  - 現金流量表的「回購普通股支出」（XBRL 常見 `PaymentsForRepurchaseOfCommonStock`）可從 EDGAR 取得，大致確定。
  - 10-Q／10-K 內有「發行人購回股權證券」表（Reg S-K Item 703，按月列數量與均價），在文件內，非獨立結構化資料，需另行解析（需查證結構化程度）。
  - 董事會授權額度公告在 8-K 或新聞稿，是非結構化文字。
  - SEC 曾於 2023 年通過每日回購揭露新規，後被法院撤銷，不應假設有每日資料（大致確定，需查證現況）。
- **台股：**
  - 庫藏股依證交法第 28-2 條，董事會決議後須公告申報，這些公告出現在 MOPS 重大訊息及庫藏股相關查詢頁。上限規範（已發行股份 10% 等）我記得，但細節需查證。
  - 結構化程度與免費 API：需查證（TWSE OpenAPI 或 FinMind 是否有庫藏股 dataset 未知）。
  - 現金流量表籌資活動的「庫藏股票買回」金額，可與美股用同樣方式從現金流量表取得。
- **注意：**
  - 回購是「公司買回」，而 CEO 說的「FCF 拿來回購」是一種看法。真正的衡量是 FCF 與回購金額（或股東報酬率）的並排比較，兩者都可從現金流量表算出。
  - 公告 ≠ 已執行。授權額度和實際買回要分開顯示。

#### 2.3 財測／guidance
- **產品內：沒有。** 見本次結論 Q1。
- **台股市場：**
  - 公開發行公司強制公開財務預測，在 2005 年前後已改為自願（大致確定，需查證年份與例外情形）。
  - 現在的情況：多數公司不給正式財測；若自願公布，會在公開資訊觀測站揭露。
  - 法說會：MOPS 有法說會場次的結構化列表（日期、時間、地點，大致確定），簡報是 PDF，展望為口頭，沒有結構化資料。
  - 分析師共識預估：要付費（鉅亨、CMoney、XQ、Bloomberg、FactSet、LSEG 等）。爬公開網站有使用條款風險，我們不建議。
- **美股市場：**
  - guidance 放在財報新聞稿（8-K Item 2.02 的附件）和電話會議，公司自願提供，SEC 沒有結構化欄位。
  - 免費結構化來源：基本上沒有。Alpha Vantage、Finnhub、FMP 等的免費層可能有「EPS 實際 vs 預估」或財報日曆（確切欄位與免費額度需查證），但這是第三方彙整的共識預估，不是公司 guidance，也不是官方資料。
  - 分析師共識預估：通常要付費（LSEG I/B/E/S、FactSet、Bloomberg、Zacks 等）。

#### 2.4 台股 vs 美股差異對照（回答 CEO 第 2 題）

| 項目 | 台股 | 美股 | 可信度 |
|---|---|---|---|
| 現金流量表（算 FCF） | 有。MOPS 網頁；程式化端點與 OpenAPI 覆蓋需查證；FinMind 可能有 | 有。SEC EDGAR XBRL API，免費、官方、無金鑰 | 美股大致確定；台股需查證 |
| 結構化程度 | 中偏低 | 高（但 CapEx 標籤不一致） | 大致確定 |
| 申報頻率 | 季報＋年報＋月營收（次月 10 日前） | 10-Q＋10-K（無月營收） | 大致確定 |
| 申報期限 | 年報約 3/31；Q1 5/15；Q2 8/14；Q3 11/14 | 10-K 60／75／90 天；10-Q 40／45 天 | 美股確定；台股大致確定 |
| 回購資料 | 庫藏股公告在 MOPS；結構化 API 需查證 | 現金流量表有金額；10-Q 有按月明細，需解析 | 需查證 |
| 公司財測 | 非強制（已廢止強制），多數不提供 | 自願，無統一格式 | 台股大致確定，美股確定 |
| 財測結構化資料 | 無 | 無免費來源 | 大致確定 |
| 分析師共識 | 付費 | 付費 | 大致確定 |
| 我們目前產品 | 無 | 無 | 確定（讀碼） |

#### 2.5 美股頁籤的資料面最小可行方案（MVP）

建議範圍：先做「財報摘要」三項：OCF、CapEx、FCF，加上回購金額，不含 guidance。guidance 的免費結構化來源不存在，用「本頁不提供財測，原因：免費官方來源不存在」明文說明即可，不要假裝有。

| 項目 | 方案 | 成本 | 限流／風險 |
|---|---|---|---|
| 財報（OCF、CapEx、回購金額） | SEC EDGAR companyfacts（單檔含該公司全部歷史，一次請求即可） | $0 | 約 10 req/s、須帶聯絡用 User-Agent（大致確定）。此資料屬公共領域，授權風險低（需查證） |
| 價格 | 沿用現有 Alpha Vantage 主＋yfinance 備援 | $0 | AV 約 25 req/day（`freshness.py:138`），多檔不夠用；yfinance 為非官方端點，隨時可能失效，條款通常限個人用途（需查證）。**目前整條鏈未實測** |
| 財測／共識 | 不做 | — | 若要做，要評估付費源，須升級 CEO |

建議做法（資料面）：
1. 新增獨立的基本面資料型別（含 `as_of`、`source`、會計期間、申報日），不要塞進 `PriceBar`。這需要 tech-architect 出 ADR（現有介面放不進去）。
2. EDGAR companyfacts 結果按 CIK 快取，只在新申報日前後重抓，不每次點頁面都打。
3. CapEx 標籤缺漏或口徑不一時，明確標「無法取得」，不補值、不內插。
4. 金融股標「FCF 不適用」。
5. 每個數字顯示財務期間與申報日，並標示「系統依 OCF 減 CapEx 計算，非公司公布值」。

合規要注意（供 risk-compliance-officer 參考）：
- **資料再散布：** 若產品維持 ADR-0025 的「B1 純自用」前提，風險低。一旦對外提供，yfinance／Alpha Vantage 免費層的條款（通常限個人或非商業用途，需查證）、FinMind 條款、TWSE 的使用條款都要重新審。
- **文案審查：** 任何寫出「FCF 足以支撐回購」「公司看多」之類的字眼，都屬建議性質內容，必須經 risk-compliance-officer 審查，他有否決權（CLAUDE.md 第 0 條第 5 款）。建議第一版只呈現數字與來源，不下結論。
- **金鑰：** 本方案除既有的 `ALPHA_VANTAGE_API_KEY` 外不需新金鑰；SEC 的聯絡資訊（User-Agent）建議走環境變數，不寫進程式。
- **歸屬與出處：** 每筆資料要帶出處與取得時間；第三方彙整的預估不可當作公司 guidance 呈現。

---

## 驗證
- **讀碼：** 以上第一部分所有結論都有檔案與行號，是親自讀過的。
- **搜尋：** 在 `apps/stock-desk` 下以中英文關鍵字做全面搜尋，確認無基本面資料。
- **外部連線：** 嘗試連 SEC EDGAR（`data.sec.gov`）、TWSE OpenAPI、MOPS，三者皆回 `CONNECT tunnel failed, 403`。**第二部分無一項經實測**，只能列為待驗證假設。
- **沒做的事：**
  - 沒改任何檔案，沒 commit，`git status` 乾淨。
  - 沒讀 `.env`，沒碰 `apps/stock-desk/backend/data/*.db`。
  - 沒讀任何環境變數的值，只讀取名稱。

---

## 下一步

**需要 CEO 決定：**
1. 要不要解凍基本面（PM 2026-10-26 列為凍結）。若要，優先序建議是美股 EDGAR（官方、免費、最穩），台股隨後。
2. 頁籤是「美股專屬」還是「基本面頁籤，台美切換」。後者較省力，因為台股也有現金流量表，且符合「持倉以台股為主、美股少量」的現況（`work/stock-desk-phase8-需求.md:22`）。這是產品決策，請 product-manager 提規格。
3. 是否接受第一版「只顯示數字與來源，不做解讀、不含財測」。

**建議執行順序：**
1. **spike（需有網路的環境，CEO 或 devops-sre 執行）：** 驗證下列各項，結果回填 `work/research/`。這也補上拖了三週以上未執行的 S-1。
   - EDGAR `companyfacts` 抓 AAPL，確認 OCF、CapEx、回購三個標籤與回應格式。
   - TWSE OpenAPI 是否有現金流量表與庫藏股資料集。
   - FinMind 現金流量表與庫藏股 dataset 名稱、欄位、免費額度。
   - Alpha Vantage 真實金鑰跑一次，補上美股價格鏈從未實測的缺口。
2. **tech-architect：** 出基本面資料型別的 ADR（新 schema、快取與更新策略）。
3. **product-manager：** 出頁籤規格與驗收條件。
4. **美術部門：** 等規格確定後做排版。
5. **data-engineer（我）：** spike 結果確認後實作 adapter、fixture 與品質檢查，並交 qa-reviewer 審查。
6. **risk-compliance-officer：** 在文案落地前審查，並確認資料再散布條款。

**資料源若要付費**（例如共識預估，或免費額度不足）：停下，列方案與成本，升級 CEO。

**組織提醒：** 目前沒有專職市調，這次由我兼任，所以「需查證」項目偏多。建議 spike 完成後，把結論固化進 `docs/adr/` 或 `work/research/`，下次不用再憑記憶回答。

**相關檔案（絕對路徑）：**
- `/home/user/AICompany/apps/stock-desk/backend/app/api/deps.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/api/bars.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/leverage/index_mapping.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/`
- `/home/user/AICompany/apps/stock-desk/backend/app/forecast/__init__.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/outlook/__init__.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/research/__init__.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/dividends/__init__.py`
- `/home/user/AICompany/apps/stock-desk/frontend/app/components/NavBar.tsx`
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/format.ts`
- `/home/user/AICompany/apps/stock-desk/frontend/app/settings/DataSourcesSection.tsx`
- `/home/user/AICompany/work/stock-desk-新定位-需求總綱與分期-2026-10-15.md`
- `/home/user/AICompany/work/research/2026-10-15-外部prompt需求對照盤點.md`
- `/home/user/AICompany/work/stock-desk-phase8-需求.md`
- `/home/user/AICompany/work/reviews/2026-10-26-產品審視-product-manager.md`
