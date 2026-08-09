# Stock Desk 數據市場面核實報告

- **日期**:2026-08-09
- **承辦**:market-researcher
- **委託人**:CEO
- **調查問題**:stock-desk 的價格數據與公開市場對不對得起來?資料來源本身可信嗎?已知資料缺口在市場面是否致命?

---

## 1. 調查方法與範圍

1. 讀取 `work/stock-desk-產品說明.md`、`work/stock-desk-已知限制與後續.md`。
2. 盤點 `apps/stock-desk/backend` 的資料層:adapter(`app/data/providers/`)、資料表(SQLite)、fixture(`tests/fixtures/`)。
3. 原計畫抽 3–5 檔台股 × 2–3 個交易日的收盤價/成交量,對 TWSE / Yahoo 股市比對;實際執行狀況見第 3 節。
4. 網路查證一律經公司 proxy 的 WebFetch / WebSearch;引用附 URL 與擷取日期(皆為 2026-08-09)。

---

## 2. 資料層盤點結果(實地確認)

### 2.1 本機資料庫:**無任何真實市場資料**

| DB | 內容 |
| --- | --- |
| `backend/data/stock-desk.db` | `price_bars_cache` **0 筆**、positions 0 筆(空庫,只有 3 筆 app_settings) |
| `backend/data/ceo-test.db` | `price_bars_cache` 1,560 筆,**全部 `source='demo_synthetic'`**(2330 / 0050 / 00631L 各 520 筆,2024-07-31 ~ 2026-07-28);positions 3 筆,note 皆帶 `[demo_synthetic]` 前綴 |

結論:**本機兩顆 DB 中沒有任何一筆真實行情**,全部是離線示範模式的合成資料。合成資料的標記機制(`source` 欄位、note 前綴)運作正常,這點值得肯定。

### 2.2 測試 fixture:全部為手工構造的合成範例

`tests/fixtures/README.md` 自述明確:**全部 fixture 皆為合成,不是實錄的真實回應**,原因是開發環境 egress policy 擋掉 TWSE / TPEx / FinMind / 台銀四個端點(proxy 對 CONNECT 回 403,有留存驗證紀錄)。Phase 7 新增的 Alpha Vantage / yfinance fixture 同樣未經實測。

### 2.3 Adapter 實作現況(與文件的落差)

| Adapter | 端點 | 查證狀態(程式檔頭自述) |
| --- | --- | --- |
| `twse.py` | `www.twse.com.tw/exchangeReport/STOCK_DAY` | 依專案知識構造,**未對照真實回應驗證** |
| `tpex.py` | `www.tpex.org.tw/.../st43_result.php`(legacy) | 同上;且為**舊版端點**,存廢風險見 4.2 |
| `finmind.py` | `api.finmindtrade.com/api/v4/data` | 同上 |
| `fx.py`(台銀 USD/TWD) | `rate.bot.com.tw` CSV | 同上;且「當日匯率」是買賣價**中點模型值**,非官方收盤匯率(自我揭露) |
| `alpha_vantage.py` | `www.alphavantage.co` | 同上(Phase 7 新增) |
| `yfinance.py` | `query1.finance.yahoo.com/v8/finance/chart`(**無官方文件的未公開端點**) | 同上,查證基礎最弱 |

**文件落差(需開單修正)**:`work/stock-desk-已知限制與後續.md`(2026-07-26)第 1、2 項仍寫「US 市場無 adapter、無指數來源」,但 Phase 7 已實作 `alpha_vantage.py`、`yfinance.py`、`us_symbols.py` 並接線進 `app/api/deps.py`(AV 主 + yfinance 備援 + 指數路徑)。限制文件已過時,建議 tech-writer 更新。

---

## 3. 抽樣比對:無法按原計畫執行,理由與替代做法

### 3.1 為何無法逐筆比對

- 產品 DB 內**只有合成資料**(見 2.1),不存在「產品輸出的真實數據」可供與市場比對——拿合成資料去對 TWSE 逐筆比對沒有意義(它本來就不是行情)。
- 仍嘗試建立市場基準:本環境 WebFetch 對 `www.twse.com.tw`、`query1.finance.yahoo.com`、`tw.stock.yahoo.com`、`www.cnyes.com`、`pchome.megatime.com.tw` 皆回 `EGRESS_BLOCKED`(2026-08-09 實測,與 fixture README 記載的 egress 政策一致)。**無法取得任何權威來源的逐日收盤價原始數據**。
- WebSearch 可用,但回傳的是搜尋摘要而非權威頁面原文;依人設紅線「絕不腦補數字」,**拒絕引用二手摘要中的個別報價數字充當比對基準**。

### 3.2 抽樣紀錄(合成資料側,供日後有網環境比對)

自 `ceo-test.db` 抽出的合成收盤價(單位 TWD;僅為留檔,**非行情**):

| 標的 | 2026-07-24 | 2026-07-27 | 2026-07-28 |
| --- | --- | --- | --- |
| 2330 | 934.70(量 34,273) | 920.17(量 25,433) | 918.66(量 34,891) |
| 0050 | 208.27(量 19,667) | 208.41(量 17,173) | 210.06(量 20,822) |
| 00631L | 195.83(量 13,459) | 196.08(量 12,567) | 199.19(量 13,803) |

旁證(**未證實**,僅供方向參考):2026-08-09 WebSearch 摘要顯示台積電 2026 年 8 月初收盤價在 2,000 元以上量級(來源摘要,未能開啟原頁驗證),與合成資料的 900 元量級明顯不同——這符合預期(合成資料不追蹤真實行情),同時也說明**若有人誤把 demo DB 當真實資料用,偏差會非常巨大**。成交量欄位同樣明顯偏小(2330 真實日成交量通常以千張計,合成值僅數萬股量級;此判斷基於一般市場常識,未逐筆查證,標註未證實)。

### 3.3 逐筆比對結論

**0 筆可核實、0 筆一致、0 筆偏差**——不是資料正確,而是「無真實資料可核」。這與限制文件 2026-07-28 的撤銷紀錄一致:**台股資料源至今未經任何真實環境驗證**。此狀態本身就是目前最大的數據風險。

---

## 4. 替代路線:資料來源本身的可信度核實

### 4.1 TWSE(主來源,上市)

- **權威性:最高**。臺灣證券交易所為官方市場資料的第一手來源;個股日成交資訊亦同步上架政府資料開放平臺(https://data.gov.tw/dataset/11549 ,擷取 2026-08-09)。
- 官方另有 OpenAPI(https://openapi.twse.com.tw/ ,擷取 2026-08-09),可作為 `exchangeReport/STOCK_DAY` 之外的交叉查核與備援端點。
- 更新頻率:盤後日更(官方盤後資訊頁 https://www.twse.com.tw/zh/trading/historical/stock-day.html ,擷取 2026-08-09;確切每日發布時刻**未查得**,上線前應實測)。
- 已知缺陷:收盤價**未還原除權息**(產品文件已自我揭露);STOCK_DAY 以月為單位查詢,長區間需多次請求。

### 4.2 TPEx(主來源,上櫃)——**高風險項**

- adapter 用的 `st43_result.php` 是**改版前的 legacy 端點**;TPEx 已推出官方 OpenAPI(https://www.tpex.org.tw/openapi/ ,擷取 2026-08-09),上櫃收盤行情亦上架政府開放平臺(https://data.gov.tw/dataset/11371 ,擷取 2026-08-09)。
- 舊端點目前是否仍存活**未查得**(本環境無法連線實測);社群文章多已改教 OpenAPI 路徑。**上線前第一件事就是實測 st43_result.php,若已失效需改接 TPEx OpenAPI**。

### 4.3 FinMind(備援)

- 第三方開源彙整,台股價格資料源自證交所,每日更新(GitHub 專案自述 https://github.com/FinMind/FinMind ,擷取 2026-08-09)。
- 免費額度 600 次/小時,註冊驗證後 1500 次/小時(FinMind 官方文件 https://finmind.github.io/v3/quickstart/ 與社群實測 https://finlab.finance/blog/python-get-taiwan-stock-data ,擷取 2026-08-09)。
- 已知缺陷:非官方、額度撞牆為社群常見痛點(有使用者掃 2000 檔在 400 多檔即爆額度的公開分享);作備援定位恰當,不宜當唯一來源。

### 4.4 台銀 FX / Alpha Vantage / yfinance

- 台銀匯率:官方來源但 adapter 取**買賣中點模型值**而非收盤價,且 CSV 欄位格式未驗證(程式自我揭露)。可信度:來源官方、處理方式屬模型近似,上線前須加常駐揭露。
- Alpha Vantage:官方 API 有文件,免費額度低(ADR 記載 25 req/day;**未另行查證現行額度**,標註未查得)。
- yfinance:走 Yahoo **無官方文件的未公開端點**,隨時可能變更或封鎖,只可當備援,不可承諾可用性。

### 4.5 上線前數據核實 checklist(交 data-engineer / qa-e2e)

1. [ ] 在有網環境對 6 個 adapter 各打一次真實請求,錄下 `*.real.json/csv`,對照 fixture 修正 schema 差異(fixture README 已有此流程)。
2. [ ] **TPEx legacy 端點存活確認**;失效即改接 TPEx OpenAPI(需改 adapter)。
3. [ ] 抽 3–5 檔(建議 2330、0050、00631L、一檔上櫃如 5483、一檔低流動性股)× 3 個交易日,將產品入庫的收盤價/成交量與 TWSE/TPEx 官網或政府開放平臺 CSV 逐筆比對,容差 0(收盤價應完全一致)。
4. [ ] 確認成交量單位(股 vs 張)在 adapter 解析與前端顯示一致——TWSE 原始欄位是「成交股數」。
5. [ ] 除權息日跨日抽測:選一檔近期除息股,確認產品顯示的是未還原價並有對應揭露。
6. [ ] FinMind 與 TWSE 同日同檔交叉比對,確認備援資料一致再啟用降級鏈。
7. [ ] 台銀 FX:與台銀官網牌告歷史頁比對中點計算;揭露文案上線。
8. [ ] 槓桿 ETF 註冊表 17 筆的倍數/費用率逐筆查證(發行人公開說明書),`verified` 翻真。
9. [ ] 真實 DB 與 demo DB 物理隔離確認(`STOCK_DESK_DB_PATH`),避免合成資料混入。
10. [ ] 驗證紀錄附可觀測證據(來源徽章截圖、後端 log),遵守 2026-07-28 撤銷事件的教訓。

---

## 5. 已知資料缺口的市場面致命性評估

| 缺口(限制文件編號) | 市場面影響 | 致命性 |
| --- | --- | --- |
| 資料源從未經真實環境驗證(2026-07-28 撤銷紀錄) | 產品所有數字的可信度為「未知」而非「已驗證」 | **致命(上線前)**——但可用第 4.5 節 checklist 一次解除 |
| TPEx legacy 端點存廢未知 | 上櫃股可能整條路線失效,僅剩 FinMind 單點 | **高**,驗證成本低,應列 P0 |
| 收盤價無除權息還原 | 台股高配息文化下,回測與長期報酬**系統性低估**;競品(看盤軟體)普遍提供還原權值線 | **重要不致命**(已揭露);但商業化前必須解,否則回測結論會被市場檢驗打臉 |
| 槓桿 ETF metadata 未驗證(verified 恆 false) | 00631L 等熱門標的的費用/倍數若錯,拆解數字誤導使用者 | 中——台灣槓桿 ETF 散戶持有度高,查證清單短(17 筆),應速解 |
| 產業欄位缺失、Kelly 無來源、總曝險依賴自報淨值 | 風控完整性缺口,單人自用可接受;三態 not_evaluable 的誠實呈現是正確做法 | 低(自用)/中(商業化) |
| 指數日線依賴 yfinance 未公開端點 | 槓桿 ETF 情境推估的可用性不穩定 | 低——功能性 nice-to-have |

---

## 6. 結論與建議下一步

1. **核實結論:目前產品沒有任何經過驗證的真實市場數據**;本機資料 100% 為標記清楚的合成資料,標記機制本身健全。
2. 六個 adapter 的可信度排序:TWSE(官方)> 台銀/TPEx(官方但端點待驗)> FinMind(第三方開源)> Alpha Vantage(官方 API 低額度)> yfinance(未公開端點)。
3. **開單 data-engineer**:執行 4.5 checklist(P0:TPEx 端點存活、6 adapter 實錄、抽樣逐筆比對)。
4. **開單 tech-writer**:更新限制文件第 1、2 項(US/指數 adapter 已於 Phase 7 實作)。
5. 除權息還原列入商業化前必辦;槓桿 ETF 註冊表 17 筆速查速翻 verified。

*本報告為內部數據核實,非投資建議;所有網路引用擷取日期均為 2026-08-09。*
