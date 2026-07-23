# ADR-0003:stock-desk 美股日線資料的主來源與備援來源

- 狀態:accepted
- 日期:2026-07-23
- 決策者:tech-architect(草案)、CEO(2026-07-23 核可)
- 適用範圍:僅 `product/stock-desk` 產品線(本 ADR 不存在於 main)
- 相依:ADR-0002(`MarketDataProvider` 抽象、`as_of`/`source` 欄位約定);skill `data-source-integration`(降級鏈、紅線)

## 評估摘要(結論先行)

- **主來源採用 Alpha Vantage**(`TIME_SERIES_DAILY` / adjusted 系列):官方 API key、條款明確、schema 穩定、日線歷史完整,是法遵乾淨的「紀錄來源(source of record)」。
- **備援採用 yfinance**:定位為「額度溢位與主來源故障時的補洞來源」,非常態主路徑;非官方、無授權保障,UI 與資料列必須標示來源。
- **快取**沿用既有設計:SQLite 本機快取,24h TTL。
- **否決 Finnhub**:免費層 `/stock/candle` 回 403(官方 issue #546),拿不到美股日線歷史,等同不可用。
- **否決 Polygon.io**:2026 年已無免費層(最低 $99/月),觸及「絕不付費」紅線,須升級 CEO 才能討論。
- 降級鏈:**Alpha Vantage → yfinance → SQLite 快取(明示延遲)→ unavailable**。
- 成立的關鍵前提:**實際持倉美股標的數量長期 ≤ 25**;若長期超過,主/備援定位需重評並可能觸發付費升級 CEO。

## Options(選項比較,2026-07-23 查證)

| 來源 | 免費額度 | 日線歷史可得性 | 穩定度 | 授權風險 |
| --- | --- | --- | --- | --- |
| **Alpha Vantage** | 25 req/day | 完整(`outputsize=full` 一次取多年;15 分鐘延遲對日線無影響) | 高:官方 API、schema 穩定 | 低:官方 key、條款明確(注意非再散布用途) |
| **yfinance** | 無明訂上限(無 key) | 完整(爬 Yahoo 端點,含 adjusted) | 低~中:IP 級 429/暫時封鎖、端點隨時可能變、無 SLA | 高:非官方、無授權條款保障 |
| **Finnhub** | 60 calls/min | **不可得**:免費層 `/stock/candle` 403(官方 issue #546) | 額度高但功能缺 | 低,但功能不符需求 |
| **Polygon.io** | **無免費層**(最低 $99/月) | 完整(付費) | 高 | 低,但需付費 → 觸紅線 |

## Decision(決策)

1. **主來源 = Alpha Vantage**:唯一「官方 key + 條款明確 + schema 穩定」且有完整日線歷史的免費來源,作為預設資料路徑與紀錄來源。
2. **備援 = yfinance**,僅於:(a) AV 當日 25 req 額度用罄的溢位;(b) AV 逾時/錯誤時啟用。非官方性質決定它只能當 fallback。
3. **不採用 Finnhub 作為日線來源**:免費層無 candles 是硬傷;若日後需要即時報價(quote,免費層可用)另案評估。
4. **不採用 Polygon.io**:無免費層,違反「絕不付費」;要用須先升級 CEO 做付費決策。
5. **主/備援可反轉的觸發條件**:實際持倉標的長期 > 25 導致 AV 無法穩態每日更新時重評(可能 yfinance 為主、AV 為備援,或升級 CEO 討論付費)。

## Consequences(後果)

好處:
- 預設路徑走官方、有授權背書的來源,法遵與 schema 穩定度風險最低。
- yfinance 補上 25 req/day 天花板(冷啟動 backfill 與額度溢位),可用性不被單一額度卡死。
- 完全免費;與 ADR-0002 的抽象、降級鏈、`source` 欄位天然吻合。

代價 / 壞處:
- **25 req/day 是硬天花板**:backfill 標的數 > 25 時須跨多日或動用 yfinance;快取與排程必須精算額度。
- **備援是非官方來源**:yfinance 隨時可能失效;AV 同時受限時可用性會掉到只剩快取甚至 unavailable(接受的殘餘風險)。
- **資料一致性風險**:兩源數值、adjusted 口徑、ticker 符號(`BRK.B` vs `BRK-B`)可能不同;混用需正規化,回測序列不得跨來源無標示拼接。
- **adjusted 價格未定案**(見尚缺事實 3):若 AV 免費層僅有未調整日線,回測跨除權息/分割會失真,可能迫使回測序列偏好 yfinance 的 adjusted——尚未關閉的架構岔路。

## 對實作的約束(逐條,可被 qa-reviewer 檢查)

1. 降級鏈固定:`AlphaVantageProvider → YFinanceProvider → SQLiteCache(明示延遲)→ unavailable`;上層不得繞過抽象直呼任一來源。
2. 每筆資料帶 `source` 與 `as_of`:`source ∈ {alpha_vantage, yfinance, cache}`;回測/訊號每一列可回溯 `source`。
3. **額度預算化,禁止盲打 AV**:本地持久化「當日 AV 已用次數」計數器(跨進程可見);達 25 即停止呼叫 AV 並降級 yfinance,不得靠打到 429 才發現。AV 每分鐘節流上限於接入時查證後設 client-side throttle(不憑記憶寫死)。
4. 快取配合 24h TTL:每標的記 `last_fetch_at`,只重抓過期者;每日更新的 AV 呼叫數 ≤ 剩餘額度,溢位走 yfinance。
5. 冷啟動 backfill 與每日更新分流:多年歷史 backfill 優先走 yfinance,避免燒光 AV 每日額度;AV `outputsize=full` 僅在額度內使用。
6. 備援來源必須在 UI 明示:`source == yfinance` 時該標的資料需可見標記(如「非官方來源,僅供參考」badge),衍生訊號/回測結論承載此 provenance。
7. 快取命中亦須明示新鮮度:`source == cache` 顯示 `as_of` 與延遲時間;unavailable 給明確錯誤狀態,不得以舊值靜默冒充最新。
8. 跨來源不得靜默拼接:正規化 ticker 與數值口徑、逐列保留 `source`;品質檢查(缺漏日、重複列、未來日期、口徑不一致)任一觸發須浮上 log/UI。
9. 憑證只走環境變數:AV API key 只從 env/`.env` 讀取,不進 code、設定檔、fixture。
10. 契約測試用離線 fixture:AV 與 yfinance 各錄真實回應存 fixture,測試不打外網;fixture 格式漂移須被契約測試抓到(yfinance 尤其需要)。
11. **升級 CEO 的觸發條件(任一成立)**:(a) 持倉標的長期 > 25 且 AV 無法穩態更新;(b) yfinance 持續被封鎖且 AV 額度不足,可用性長期只剩快取/unavailable;(c) 任何需付費來源才能滿足的需求;(d) 產品轉向多人/public,觸及再散布條款——同時需 risk-compliance-officer 審查。

## 尚缺的事實(不阻擋定案,實作前必須補齊)

1. AV 免費層的每分鐘 rate limit 與 `outputsize=full` 是否仍免費:接入時由 devops-sre 查證當下文件並記錄日期。
2. 實際持倉美股標的數量(portfolio size):決定 25 req/day 是否為穩態瓶頸;向 product-manager/實際持倉資料要。
3. adjusted vs unadjusted:查證 AV 免費層是否仍提供 `TIME_SERIES_DAILY_ADJUSTED`(歷史上曾移 premium);若免費層僅有未調整價,回測序列可能改以 yfinance adjusted 為準,回頭影響主/備援定位。
4. ticker 符號正規化規則:AV 與 yfinance 的符號格式差異(`BRK.B` 等)於接入時建表。
