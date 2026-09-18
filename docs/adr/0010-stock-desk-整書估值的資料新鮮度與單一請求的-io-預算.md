# ADR-0010：stock-desk 整書估值的資料新鮮度與單一請求的 IO 預算

- 狀態：proposed（待 CEO 核可）
- 日期：2026-09-18
- 決策者：tech-architect（裁決）、CEO（待核可）
- 適用範圍：僅 product/stock-desk 產品線
- 修訂：（無，本次為新增）

## Context（背景）

`/api/advice/{symbol}` 為了畫出風險上限卡，會先對整本持倉跑 `build_summary`：
`app/api/advice.py:get_advice` → `app/portfolio/summary.py:build_summary` →
`app/portfolio/valuation.py:_resolve_price`，對每一筆持倉序列跑完整的資料梯子；
再加上每個非 TWD 部位最多 16 次匯率 HTTP（`app/data/providers/fx.py` 逐日曆日查詢、
`valuation.py` 7 天回看）。整段流程全部序列執行、沒有跨請求快取。

逾時預算：連線 2 秒、讀取 8 秒、重試 1 次（`app/data/http.py`）。台股三層梯子最壞情況約
60 秒／檔，12 檔持倉序列跑下來最壞約 12 分鐘。CEO 於 2026-09-17 實測 12 檔持倉時，
建議 API 數分鐘未回應。

同一份 `build_summary` 也被 `/api/positions`、`/api/portfolio/summary`、
`/api/portfolio/limits`、警示快照呼叫，並非只有 `/api/advice` 一處。

**關鍵觀察**：本標的價格與整書聚合值對精度的需求差一個數量級——整書估值落後一個交易日，
對「是否超過風險上限」這個判斷的影響落在四捨五入等級；但「使用者等三分鐘沒畫面」是
確定會發生的傷害。本案不新造新鮮度定義，沿用 ADR-0009 的 `judge()`。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 / 處置 |
| --- | --- | --- | --- |
| (a) 程序內短 TTL memo | 實作簡單 | 首次請求（冷啟動、TTL 到期後第一次）仍是慢的那一次 | 保留為第二步（見 D-5），不單獨採用 |
| **(b) 整書估值 cache-only、只對本標的即時（本案主決策）** | `/api/advice` 整書網路呼叫可降為 0 | 整書估值最舊可能落後一個交易日；需常駐揭露 | 主決策，見 D-1 |
| (c) 有界 thread pool 平行化 | 理論上可縮短序列總時間 | `RateLimitedClient._throttle` 持鎖 `sleep`，同一 provider 全序列化，平行化拿不到效果；SQLite 三張表寫入會競爭；Alpha Vantage 額度預扣分岔會破壞可重現性 | **否決／延後**（D-7）。重啟前置條件：節流機制改為並行度上限＋非持鎖等待、補上競態測試、另立 ADR |
| (d) 總逾時保護 | 有明確的時間上限 | 逾時判斷本身不解決「為何要等」的根因 | 降格為 backstop，只用在仍走 live 的整書路徑（見 D-6，未落地）；逾時部位以 `not_evaluable` 呈現、不計入 totals；不得宣稱背景工作已取消 |
| (e) 排程預熱 | 讓 cache-only 讀取有東西可讀 | interval trigger 若只設 interval，首次執行在一個 interval 之後，等同冷啟動 24 小時內快取是空的 | 升格為方案 (b) 的必要伴隨項，見 D-4 |
| (f)（發現，非選項）ADR-0009 冷卻缺口 | — | `_try_session_fresh_cache` 在 `cached is None` 時直接跳出，attempt-log 冷卻讀不到；結果是「從未成功抓過該序列」且「來源正在失敗」的序列，每次請求都跑完整梯子——最需要冷卻保護的情況反而沒有冷卻 | 併入本案處理，見 D-3（並回頭修訂 ADR-0009 為 D-8） |

## Decision（決策）

- **D-1（cache-only 估值路徑）** 新增 `MarketDataService.get_cached_bars()`：cache-only 讀取，
  套用同一個 `judge()`，裁決結果只回 `CACHED_STALE` 或 `UNAVAILABLE`，不寫 fetch log／attempt log，
  也不 `put`。`PositionValuator` 新增顯式建構參數 `price_mode="live"|"cache_only"`，
  **不得**用環境變數切換價格模式。`/api/advice` 改用 cache-only 估值器
  （`app/api/deps.py:get_cached_valuator`）計算整書；本標的（卡片標題那一檔）仍由端點自己的
  `load_bars` 即時抓取。`/api/portfolio/summary` 維持 live（見 R-8）。
- **D-2（單次請求內收斂匯率查詢）** 同一次 `build_summary` 內，相同 `(pair, date)` 的匯率查詢
  收斂為一次（`PositionValuator.value_all` 的 per-pass memo）。完整的 FX 快取層是另一件事，
  列管 data-engineer 另立 ADR（見 S-1）；在該案落地前，本案只能宣稱「台股持倉部分的延遲已修復」，
  不得宣稱整書延遲問題全部解決。
- **D-3（回頭補上 ADR-0009 冷卻缺口，即 ADR-0009 D-8）** attempt-log 冷卻的判斷移到
  `cached is None` 之前：若在冷卻期內、且最後一次向來源提問晚於最後一次完整成功，
  即使快取完全沒有列，也直接回 `UNAVAILABLE` 並附上原因（`COOLDOWN_NO_CACHE_REASON`），
  不再因為「沒有列可读」而略過冷卻判斷、每次都重跑整條梯子。
- **D-4（排程預熱）** `scheduler.data_refresh` 加上 `next_run_time=now`，服務啟動即立即預熱一次，
  不等第一個 interval 過去。**D-1 不得在 D-4 之前上線**（否則冷啟動期間 cache-only 會讀到空快取）。
- **D-5（程序內 memo，第二步，未落地）** `build_summary` 加程序內 memo：鍵包含持倉表版本
  （`PositionStore.version()`），TTL 60 秒，single-flight（同一鍵的併發請求只算一次），
  `as_of` 為實際建立時間、不得覆寫。
- **D-6（總逾時 backstop，未落地）** 只用在仍走 live 的整書估值路徑（非 cache-only 路徑）；
  逾時的部位以 `not_evaluable` 呈現，不計入 totals。
- **D-7** 否決方案 (c)（有界 thread pool 平行化），理由與重啟前置條件見 Options 表。

### 對實作的約束（R-1～R-14）

- **R-1** cache-only 路徑只能回 `CACHED_STALE` 或 `UNAVAILABLE`（測試要求：零 HTTP 呼叫）。
- **R-2** cache-only 路徑不得呼叫 `record_fetch`／`record_attempt`／`put`。
- **R-3** `is_within_ttl` 一律由同一個 `judge()` 產生；沒有 coverage 資訊一律回 `False`。
- **R-4** `mixed_sources_reason` 照既有規則套用，不因 cache-only 而省略。
- **R-5** 沒有快取列時回 `insufficient_data`；`missing` 需以 `price_not_queried` 與 `price`
  區分「本次未向來源查詢」與「查了但沒有資料」兩種狀態。
- **R-6** `/api/advice` 的執行順序固定：先跑本標的的 live `load_bars`，再跑 cache-only 的
  `build_summary`。
- **R-7** `book_fully_valued` 不得因為效能考量而放寬判定標準。
- **R-8** `price_mode` 必須是顯式參數；`/api/portfolio/summary` 維持 live 模式。
- **R-9** D-5 落地時，memo 鍵須包含持倉版本，`as_of` 不得被覆寫。
- **R-10** D-5 落地時，須有 single-flight 機制。
- **R-11** D-6 落地時，逾時部位不計入 totals。
- **R-12** 不得為了減少請求而延長 `PRICE_LOOKBACK_DAYS = 10`。
- **R-13** D-4（排程預熱）必須先於 D-1（cache-only 上線）落地。
- **R-14** 持倉含非 TWD 部位時，D-2（匯率查詢收斂）必須與 D-1 同批落地，不得分批。

## 需風控核可的揭露點

以下字面為 2026-09-18 實際出貨常數（逐字，與程式一致；creative-lead 草案與理由見
`work/stock-desk-ADR-0010-揭露句-文案.md`），風控狀態逐條標示：

1. 整書以本機快取估值的常駐揭露句，`context_notes` **首條**（`app/api/advice.py`；風控第一輪 VETO、複審 VETO 後三修，**風控核可 2026-09-18（三審），逐字鎖定**）：
   - `CACHE_ONLY_BOOK_NOTE`：「本卡風險上限所用的整體持倉估值取自本機快取，本次未向來源更新；已估值持倉的價格分別截至
     {earliest}～{latest}，上限判定可能建立在較舊的價格上。總覽頁的整體持倉估值是否向來源查詢，同樣視快取涵蓋範圍而定，
     不代表其數字比本卡估值更新。」（日期只取估值成功的持倉）
   - `CACHE_ONLY_BOOK_NOTE_SINGLE_DAY`（同日）：「…已估值持倉的價格皆截至 {date}，上限判定可能建立在較舊的價格上。」＋同一出口句。
   - `CACHE_ONLY_BOOK_NOTE_EMPTY`（有持倉但無一筆估值成功）：「本卡風險上限所用的整體持倉估值本次未向來源更新，且本機目前沒有任何一筆持倉完成估值；
     以總資產為分母的相關比率，本次均無法計算。」＋同一出口句。空帳本（零持倉）不掛。
   - `insufficient_data` 分支不掛（無卡無上限）。
2. 未估值部位的快取先行變體（`app/advice/book.py` `UNVALUED_POSITIONS_NOTE_CACHE_ONLY`，依原因分列計數，**風控核可 2026-09-18（三審），逐字鎖定**）：
   「組合中有 {count} 筆部位無法估值（本次未向來源查詢，本機尚無可用的價格或匯率），未計入總資產；比率會因此偏高。」
   原句字面保留，用於「向來源查了沒資料」的部位。
3. 全站聲明句限定本標的（`frontend/app/lib/adviceWording.ts` `NON_REALTIME_NOTICE` 第三句，creative-lead 版本 (i)，**風控複審核可**）：
   「以下本標的評估以系統手上最新一份資料計算，反映的是打開頁面當下、系統能取得的本標的資料，不代表市場當下狀況。」
4. 無快取列且本次未查詢的原因句（`CACHE_ONLY_MISS_REASON`，**風控核可**）：「本機尚無此標的的日線資料；本次未向來源查詢。」
   併 `Valuation.missing` token `price_not_queried`；前端 `valuationWording.ts` 對照（**風控核可**）：price→「查無價格資料」、
   price_not_queried→「本次未查價格」、fx_now→「查無即期匯率」、fx_open→「查無建倉匯率」。
5. D-3 冷卻情境的原因句（`COOLDOWN_NO_CACHE_REASON`，時間戳與非承諾式等待句，**風控核可 2026-09-18（三審），逐字鎖定**）：
   「本機尚無此標的的日線資料，最近一次向來源取得已於約 {minutes} 分鐘前未成功，冷卻期內暫不重試。冷卻期為 {cooldown_hours} 小時，
   冷卻期內系統不會自動重試；冷卻期結束後的下一次查詢才會重新向來源取得。」（`cooldown_hours` 以整數小時顯示，
   `tests/test_freshness.py` 釘住兩市場冷卻皆為整小時）
6. 裁決題：cache-only 模式下 `totals.status` 可為 `complete`（**風控同意**：`complete` 只講涵蓋率，`Totals.status` 契約已註明；
   新鮮度由第 1 點常駐句承擔，第 1 點已於三審核可，前提滿足）。D-5 隨第 1 點結清，條件：三態共用 `_book_freshness_notes`
   單一判定路徑，任一態被移除、改為靜默或改字面即回復未結清並重送風控。
7. 風控三審 suggested／列管：`_OVERVIEW_CLAUSE` 可補「與新鮮度」；`UNVALUED_POSITIONS_NOTE_CACHE_ONLY` 的「或匯率」歸因在
   FX 快取層落地後重審；冷卻句「約 0 分鐘前」與 US 四位數分鐘；`GROSS_EXPOSURE_SELF_REPORTED_NOTE` 在未完全估值成常態後改述
   （creative-lead）；`NON_REALTIME_NOTICE` 只在個股頁渲染的守門測試。

## Consequences（後果）

- 好處：
  - `/api/advice` 的整書估值網路呼叫可降為 0，剩下 12 次 SQLite 讀取（依 CEO 實測的 12 檔持倉估算）。
  - D-3 讓「來源持續失敗」的情境從「每次請求都付 180 秒」變成「每個冷卻窗只付一次」。
- 代價（照實計）：
  - 整書估值資料最舊可能落後一個交易日（TW 冷卻 1 小時／US 冷卻 24 小時，沿用 ADR-0009 D-2 參數），
    且此落後狀態會常駐揭露在畫面上。
  - 完全沒有快取列的持倉會落入 `insufficient_data`，`totals.status` 呈現 `partial`，
    該持倉的曝險呈現 `not_evaluable`；D-4（排程預熱）是目前唯一用來壓低此類情況發生面積的手段。
  - `/api/portfolio/summary`（總覽頁）本階段維持 live，不受本案改善，仍會慢。
  - D-5（程序內 memo）一旦落地，是程序內（in-process）的快取，API 服務與 scheduler 各自持有一份，
    不互相共享。
  - D-3 的冷卻機制也會擋掉冷卻期內使用者主動重試的請求（等到冷卻窗過才會再打來源）。
- 已知限制：
  - D-5、D-6 尚未落地，僅為決策記錄，實作前不得宣稱已生效。
  - FX 完整快取層（S-1）未落地前，非 TWD 持倉的匯率查詢仍是每次請求對來源查詢（只是同批內去重）。
- 約束：D-5、D-6 落地前，`/api/advice` 的效能改善範圍僅限於 D-1～D-4 所涵蓋者；擴大 cache-only
  適用範圍或調整 D-2 的收斂邏輯須回頭修訂本 ADR 或另立新 ADR。

## Suggestion／列管

- **S-1** FX 完整快取層：列管 data-engineer，另立 ADR。
- **S-2** 不得為了節省請求數，在 FX 回看邏輯中跳過週末（與 ADR-0009 Options E 被否決的理由同構——
  以「應該休市」的推論取代實際查證）。
- **S-3** 收斂 `LatestPriceService`（重複實作，待後續整理）。
- **S-4** `/api/portfolio/limits` 對同批標的目前有兩次 fan-out，待收斂。
- **S-5** 冷卻期內，前端顯示距下次可重試嘗試的時間，改善使用者體感。

風險：

- 資料變舊而使用者未察覺——目前僅靠三層文字揭露（`CACHE_ONLY_BOOK_NOTE`／
  `CACHE_ONLY_MISS_REASON`／`COOLDOWN_NO_CACHE_REASON`）把關，未經風控核可前不得視為已控管。
- 冷啟動空窗：服務重啟到排程預熱完成之間，cache-only 讀取可能落空。
- CEO 2026-09-17 的 12 檔持倉實測中，幣別組成未知；「整書序列梯子過慢」（發現 1）與
  「FX 序列查詢過多」（發現 2）何者為主因，屬條件式判斷，需視實際幣別組成而定，本 ADR
  不對此下定論。
- 退市／長期停牌標的每個冷卻窗仍會被重抓一次，此為 ADR-0009 已知限制，本案未新增也未解決。

## 已落地狀態（2026-09-18）

- 已落地、待審查：D-1、D-2、D-3、D-4。
- 未落地：D-5、D-6。
