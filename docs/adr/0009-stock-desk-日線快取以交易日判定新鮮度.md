# ADR-0009：stock-desk 日線快取以「交易日」判定新鮮度，不以時鐘 TTL

- 狀態：proposed
- 日期：2026-09-13（tech-architect 第一輪 NEEDS_CHANGES 後修訂）
- 決策者：tech-architect（草案與審查）、CEO（2026-09-13 授權「你決定」，待核可）
- 適用範圍：僅 product/stock-desk 產品線
- 修訂：
  - **取代 ADR-0003** 決策摘要「24h TTL」與對實作的約束第 4 條（每標的記 `last_fetch_at`、只重抓過期者）。
    ADR-0003 約束 7（快取命中須明示新鮮度、不得以舊值冒充最新）**維持有效**，由本 ADR D-5 的裁決分岔承擔。
  - **取代 ADR-0005** 決策四第 1～4 點與約束 D-1（TTL 24h、TW 不開 layer 0、`cached_stale` 核可字面）；
    第 3 點改寫為「不得為了節省額度而延長指數路徑的 `recheck_cooldown`」。其餘 ADR-0005 維持。

## Context（背景）

台股資料鏈 `cache_first=False`（ADR-0005 D-1）：每一次請求都先打 TWSE，且 `TwseAdapter`
每個日曆月一次 HTTP 呼叫，兩年區間就是 24 次；回測頁按一次「執行回測」、再按一次
「顯示五項觀察條件事件研究」，就是兩輪 TWSE 請求，快取只在來源掛掉時才用得到。
美股走 24 小時 TTL：週日重抓週五就有的資料；週一 09:00 又把週五抓的當「新鮮」。

CEO 問「一天更新一次？還是真正有更新才更新？標準在哪？」。日線的本質是**每個交易日收盤後
才多一根**，所以正確的問題不是「快取幾小時了」，而是**「市場是否已完成並公布一個快取沒有的交易日」**。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| A 台股也用 24h TTL | 改一個旗標 | 週一早上仍當週五資料「新鮮」；週末重抓 | 錯的問題，只是換個市場 |
| B 固定每日排程重抓、請求一律吃快取 | 零請求時延 | 排程沒跑（機器關機）就永遠舊資料；新加的標的沒人抓 | 靜默陳舊 |
| **C 交易日判定＋冷卻（本案）** | 只在真有新交易日才打來源；週末／盤中零請求；排程可有可無 | 要假設收盤公布時間；不含假日表 | 假日或公布延遲時每個冷卻窗多一輪請求 |
| D 向來源問「最後更新時間」再決定 | 最精準 | 即使來源提供，查詢本身仍是一次請求，省不到額度；且無法離線 | 不採 |
| E 以既有觀察式日曆（`market_trading_days`）佐證假日 | 零新資料結構；同市場任一序列在 expected 日有 bar 即證明開盤，可消掉大部分假日誤判 | 只能單向作為「確定缺一天」的證據，沒證據時仍退回冷卻規則；單一標的使用者的日曆等於自己 | 本期不做：先讓 C 上線觀察真實成本，E 為下一步（已列管） |
| F 只補抓缺的月份（provider 粒度） | 一輪重抓從 N 個月降到 1 個月 | 要改 TWSE／TPEx adapter 的請求切分 | 與 C 可併行，本期不做（已列管） |

## Decision（決策）

- **D-1（判定標準）** 新增 `app/data/freshness.py`。對每個市場定義 `SessionFreshnessPolicy`
  （交易所時區、收盤公布時間 `publish_cutoff`、`recheck_cooldown`）。
  `latest_completed_session(now)` ＝ 交易所當地時間已過 `publish_cutoff` 則為今天，否則為前一天，
  再退到最近的平日。`judge()` 三種裁決：
  - `HAS_LATEST_SESSION`：快取最後一根 ≥ min(最近已公布交易日, 請求 end 退到平日) → **直接用快取，不打來源**。
  - `CHECKED_RECENTLY`：快取少一個交易日，但 `recheck_cooldown` 內已問過來源而沒有更新（假日、尚未公布）
    → 用快取，`is_within_ttl=False` 誠實揭露。
  - `REFETCH`：快取少一個交易日且冷卻已過 → 打來源。
  `judge()` 只接受 timezone-aware 時間；`last_checked_at` 在未來（時鐘被撥回）視為未知 → REFETCH，不讓冷卻永不到期。
  `requested_end` 是呼叫端時鐘的日期（容器實務上 UTC），安全前提是各市場 `publish_cutoff` 晚於呼叫端與交易所的時差（15:00 台北距 UTC 換日七小時），把 cutoff 調早於此會讓「今天」永遠等不到。
- **D-2（參數）** TW：`Asia/Taipei`、`publish_cutoff` 15:00、冷卻 1 小時。US：`America/New_York`、18:00、冷卻 24 小時
  （美股冷卻 24h 是為了 Alpha Vantage 25 req/day，最壞情況＝舊 TTL）。
  **兩個公布時間皆未查證**（本環境無外網，依 data-source-integration 慣例揭露）；設得偏晚。
  偏晚的代價（風控 R3）：若 TWSE 實際更早公布，最多 30 分鐘（US 約 2 小時）內快取被判「已含最近交易日」
  而其實新的一根已存在——因此 D-5 的徽章不再宣稱「已含最近交易日」，只陳述資料截至日期。
- **D-3（覆蓋範圍與紀錄）** 快取新增兩張小表：
  - `price_bars_fetch_log`（每 symbol/market 一列：**單一連續**已完整取得區間 `covered_start`～`covered_end`、
    最後一次完整取得時間 `last_fetched_at`）。只在 provider 回報 `complete=True`（TWSE／TPEx 沒有任何月份被略過）
    時寫入；新區間與既有區間重疊或相鄰才合併，不相鄰則取代——不得用 MIN/MAX 把中間沒抓過的空檔說成已覆蓋。
    記的是**請求**區間而非回傳 bars 的範圍：上市晚於請求起點的標的，不會每次請求都重抓。
  - `price_bars_attempt_log`（每 symbol/market 一列：最後一次向來源提問的時間，成功失敗皆記）。
  layer 0 條件：快取有列，且 (a) fetch log 存在且 `covered_start ≤ start`，再依 `judge()`；或 (b) 無 (a) 但
  attempt log 在冷卻期內**且該次提問晚於最後一次完整成功**（即失敗或部分回答）→ 用快取並揭露 `is_within_ttl=False`
  並附「最近一次向來源取得資料未成功，暫以本機快取回覆。」（風控核可字面；**目前僅存在於 service 回傳與日誌，尚未上畫面**——
  `load_bars` 成功分支未帶 `reason`、前端亦無元件渲染成功載入的 `DataMeta.reason`，使用者看到的是徽章的「可能未含最近交易日」；接通列管）
  （來源正在失敗時不每次重跑整條梯子）；
  拉寬區間緊接在一次成功抓取之後不算此例，照樣打來源。`CHECKED_RECENTLY` 另要求 `covered_end` 已到達本次預期交易日，
  否則視為區間缺口而非假日 → 打來源。否則走梯子。
  `delete_by_source`（示範資料 reset）同步刪除受影響序列的兩張 log。
- **D-4（所有市場開啟）** TW 服務 `cache_first=True`，取代 ADR-0005 D-1。`cache_first=False` 仍存在
  （純降級鏈），但沒有市場使用。指數路徑依呼叫端指名的 market 取 policy（`^TWII` 走台北時鐘）。
- **D-5（欄位與文案）** `is_within_ttl` 欄位名保留，語意改為「快取已含最近已公布交易日」，且**適用於每一條回傳
  `cached_stale` 的路徑**（layer 0 與來源全掛的降級路徑同一套 `judge()`；`CacheReadResult` 不再持有時鐘 TTL 欄位，
  `PriceBarCache` 移除 `ttl_seconds`）。`staleness_minutes` 與 `as_of` 為**該批資料最後一次實際取得**的時間
  （完整取得時取 fetch log，其餘取快取列的 `fetched_at`），不是失敗嘗試的時間；完整取得時也不是區間內最舊一列。
  保留欄位名的理由不是「API 相容」（消費者只有本 repo 前端），而是**不值得為改名動十個前端檔**；
  `app/api/common.py` 與 `types.ts` 的 schema 說明寫明新語意。
  前端徽章改為陳述可驗證事實（風控 2026-09-13 第二輪核可方案 A 八句，字面釘在 `dataMetaStatusBadge.test.ts`）：
  `true` → 「本機快取，資料截至 {last_bar_date}（N 分鐘前取得）」；`false`／`null` → 「快取資料，資料截至 {last_bar_date}
  （N 分鐘前取得，可能未含最近交易日）」；缺欄位時逐段截短，不捏造。回測頁兩個區塊的「來源：」列同時顯示「資料截至」，
  讓同頁兩個徽章狀態不同（一個 fresh 無徽章、一個 cached）時，使用者以截止日而非徽章有無判斷資料是否相同。
- **D-6（排程）** `scheduler.data_refresh` 不改：它走同一條 `load_bars`，自然只在有新交易日時才打來源。
  改為「收盤公布後 cron 預熱」與 `SCHEDULER_DATA_INTERVAL_MINUTES` 與冷卻的交互，列管 devops-sre。

## Consequences（後果）

- 好處：回測頁與事件研究按鈕在同一交易日內對 TWSE 零請求；週末／盤中零請求；美股額度消耗只降不升；
  「真正有更新才更新」有可驗證的定義；來源掛掉時最多每個冷卻窗跑一次梯子。
- 代價：使用者在兩段不相鄰區間之間來回（例如 2020 事件研究 ↔ 2024 回測）會互相取代 coverage，每次點擊都是一輪完整重抓；真的痛再改成每序列多列 coverage（列管）。
- 代價（照實計）：一輪 TW 重抓＝TWSE 每個日曆月一次 HTTP（排程 540 天回看＝一輪 18 次）。以下序列
  **每個冷卻窗都會重抓一輪**，且是穩態成本、不是一次性：(a) 交易所假日（未建假日表）當天；(b) 退市／長期停牌、
  `last_bar_date` 永遠追不上 expected 的標的；(c) `end` 落在休市日的歷史區間（`judge` 只退到平日，不退到最近實際交易日）。
  TW 冷卻 1h 表示上述情況每天最多 24 輪／檔。出路：方案 E（觀察式日曆）或對「同一 expected 已確認拿不到」記否定快取，列管。
- 已知限制：
  - 不含假日表（與 `app/data/calendar.py` 同一取捨）。
  - 同一月份內的歷史修正只會在下一個交易日重抓時帶入（TWSE 月端點整月重抓），更早月份不會重抓（與現況相同）。
  - fetch log 記請求區間：若來源對請求區間**完整**回答但中段某月本來就無資料（例如停牌），該月不會再被問（與現況一致，該月本來就沒資料）。
  - 離線示範環境（無外網）：示範資料無 fetch log，第一次請求會跑一次梯子（TW 三層快速失敗約 5 秒）後才進 attempt 冷卻；每個冷卻窗重複一次。
  - 降級原因句 `RECENT_ATTEMPT_FAILED_REASON` 尚未接到畫面（風控第三輪 required 追蹤：接通並常駐顯示，或持續如實標注未上畫面）。
  - `DirectiveLedger`（操作指令頁）的徽章沒有分鐘數與截止日可接（`Directive` 只有 `data_status`／`source`），台股快取先行後「快取資料」會成為常態畫面；列管 frontend-engineer 接 `last_bar_date`。
  - `publish_cutoff` 與 `recheck_cooldown` 其實是「來源」而非「市場」的屬性（指數走 yfinance 不吃 AV 額度，卻背 24h 冷卻）；列管改為 (market, source) 鍵。
- 約束：改 `publish_cutoff`／冷卻值須 devops-sre 查證後更新常數與本 ADR；引入假日表、方案 E／F、或向來源查最後更新時間，另立 ADR 或修訂本 ADR。

## 附錄：程式註解引用的審查發現編號對照

程式碼與測試中的「ADR-0009 R-x／S-x／R2-x／S2-x／R-10」指的是本 ADR 審查過程的發現編號（全文見
`work/reviews/2026-09-09-五條件回測-審查紀錄.md` 附四），不是本文的 D-x 決策編號。對照如下：

| 編號 | 出處 | 內容 | 落點 |
| --- | --- | --- | --- |
| R-1 | tech-architect 第一輪 | 降級路徑不得沿用時鐘 TTL 語意 | D-5；`service.py::_fall_back_to_cache` |
| R-2 | tech-architect 第一輪 | staleness 不得取區間內最舊列 | D-5；`service.py::_cached_result` |
| R-4 | tech-architect 第一輪 | 部分抓取不得固化快取洞 | D-3；`ProviderResult.complete` |
| R-5 | tech-architect 第一輪 | `delete_by_source` 連帶清 log | D-3；`cache.py::delete_by_source` |
| R-6 | tech-architect 第一輪 | 未來時間戳／naive 防護 | D-1；`freshness.py::judge` |
| R-8 | tech-architect 第一輪 | 來源失敗時冷卻仍須生效 | D-3；attempt log |
| R2-2／R2-3 | tech-architect 第二輪 | attempt 分支帶原因；`complete` 向上傳遞 | `service.py` |
| S-1 | tech-architect 第一輪 | policy 應以 (market, source) 為鍵 | 已知限制（列管） |
| S2-1～S2-4 | tech-architect 第二輪 | busy_timeout、record_fetch 競態、EXISTS、`is_within_cooldown` | `cache.py`、`freshness.py` |
| R-10 | risk-compliance-officer 第二輪 | 失敗嘗試不得講成「取得」 | D-5；`service.py` attempt 分支 |
| 方案 A | risk-compliance-officer 第一／二輪 | 徽章八句定稿 | D-5；`dataMetaStatusBadge.test.ts` |
