# ADR-0015：stock-desk 匯率跨請求快取（FX cross-request cache）

- 狀態：accepted（CEO 2026-10-03 核可；核可設計不等於可出貨，仍受 C-24 出貨閘門約束）
- 日期：2026-10-03
- 決策者：tech-architect（草案）；CEO 2026-10-03 核可
- 適用範圍：僅 product/stock-desk 產品線
- 與既有 ADR 的關係（不取代任何一則 ADR 全文）：
  - 結清 ADR-0010 S-1（FX 完整快取層）。
  - 回答 ADR-0011「需要 CEO 或使用者決定」第 3 題（FX 快取層），並使其 Consequences
    「FX 目前仍然沒有本地快取層」一段（0011:100）失效；降級鏈由「主 → 備援 → 不可用」
    擴為「快取命中 → 主 → 備援 → 快取舊值 → 不可用」。ADR-0011 其餘決策與紅線全數維持。
  - 滿足 ADR-0014 D-9 前置條件／I-25／W11；ADR-0014 W16 的解鎖條件以本 ADR C-19 為準。
  - 需回頭修訂 ADR-0014 I-4 與防線 2 的字面（見 C-17；已於 2026-10-03 在 ADR-0014 加修訂註記）。
  - 沿用 ADR-0009 的冷卻語意（D-8、R-4、R-6），但**不**沿用 `judge()`（理由見 Context 4）。
- 來源與版本：本檔為 tech-architect 2026-10-03 草案（ADR-0015「匯率跨請求快取」）的落檔，僅做格式調整，技術內容未增補。本檔含落檔補述與 2026-10-03 依 tech-architect 回覆的修訂（修訂處：D-3、D-8、D-10、Options F2 與延後項 L-1、Consequences 與已知限制、C-7、C-8、C-17、C-19、C-21、新增 C-22～C-25、W 清單分類與 W-8、工作拆分、待釐清改為已釐清、附錄末段）；上一句「僅做格式調整」僅指初次落檔。2026-10-03 另依 CEO 裁定（任務單轉述）將狀態改為 accepted、「需要 CEO 決定」改為「CEO 裁定（2026-10-03）」，並更新「已釐清」第 5 點與工作拆分一處引用；技術決策內容未變。
  - 檔內 `檔案:行號` 為草案作者所引，行號以草案作者 2026-10-03 讀到的工作目錄為準，落檔時未重新對 code 驗證；行號會隨 commit 漂移，引用時以原文定位。2026-10-03 修訂內容中的 `檔案:行號` 亦為 tech-architect 回覆所引，tech-writer 未重新對 code 驗證。
  - 草案對 ADR-0014 的引用一律以現行檔名 `0014-stock-desk-盤中報價資料邊界顯示範圍與節流.md` 為準。
  - 本 ADR 內的「附錄」為草案第 2 節的評估摘要，原樣轉錄。

---

## Context（背景）

1. 現況每次請求都向來源查匯率。`PositionValuator._lookup_fx`（valuation.py:386-409）
   與 `resolve_fx_quote`（services/fx.py:84）每次都呼叫 `_default_fx_provider()` 的
   `FxRateLadder`（deps.py:140-160）。ADR-0010 D-2 只做到「同一輪內去重」（valuation.py:238-247）。
   台銀 adapter 逐日查詢（fx.py:182-185），區間為 target 往前 7 天
   （`FX_BACKTRACK_DAYS`，valuation.py:56），所以每個非 TWD 部位的 fx_now 加 fx_open
   最多 16 次 HTTP。挑戰頁短路（ADR-0011 D-2）之後，實務上是台銀 1 次加 yfinance 1 次，
   但台銀若回非 200，仍會逐日打滿（fx.py:235-242）。
2. ADR-0014 要讓前端每 60 秒輪詢 `/api/portfolio/summary`（P-10）。沒有跨請求快取時，
   每輪都會重跑匯率梯子。ADR-0014 因此規定匯率快取落地前 `refresh_after_s` 恆為 null（D-9、I-25）。
3. 程序拓撲：API 是單一 uvicorn worker（compose.yaml:20）；scheduler 是另一個 container／程序
   （compose.yaml:29-44），它的警示 tick 也查匯率（scheduler.py:176-177、alerts/snapshot.py:84）。
   兩者共用同一個 SQLite 檔（compose.yaml:17,41；WAL，cache.py:153-175）。
4. 匯率的時間性與日線不同：
   - 本產品以「日」粒度使用匯率：`FxInfo.as_of` 只有日期，fx_now 取 target 當日或之前最新一筆。
   - 「今天」那筆在盤中會變。yfinance 當日 K 棒是進行中的值；台銀牌告在營業時間內會調整，
     而 `flcsv/0/<今天>` 對當日回傳的是哪一版**未查證**。
   - 過去日期的匯率已結算、不會再變。
   - 匯率沒有「交易所交易日」，ADR-0009 的 `judge()` 依 `Market` 判定交易日（freshness.py:126-164），套用不上。
5. yfinance 的日期取自 UTC timestamp（yfinance.py:385），台銀的日期是台北日曆日；
   估值器的「今天」是 UTC 日期（valuation.py:226,255）。
6. 狀態欄位既有契約：
   - `DataStatus` 的 fresh／backup 指「即時取得」（interface.py:29-30）。
   - `is_within_ttl` 只對 `CACHED_STALE` 有意義（interface.py:94-97；FxInfo valuation.py:161-167 宣告與之同一契約）。
   - 風控條件 (1)：備援匯率的「備援源」徽章必現（0011:118）。前端在
     `cached_stale && is_within_ttl===true` 時不顯示徽章（FxStatusBadge.tsx:43-47）。

---

## Options（選項比較）

七個題目各一張表，**粗體**為採用方案。採用：A2、B3、C3、D3、E2、F1、G1。

**A. 儲存位置**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| A1 程序內記憶體 | 最簡單，零 IO | API 與 scheduler 各算各的；重啟就清空；沒辦法在重啟後退回舊值 | 冷啟動後第一次輪詢仍然要跑整條梯子 |
| **A2 SQLite（採用）** | 兩個程序共享；撐過重啟；已結算的匯率永久重用；能做「舊值退回」這一層 | 每次查詢多 1～3 次 SQLite 讀；兩個程序可能同時寫 | 低：沿用 `cache.py:153-175` 的 WAL＋`busy_timeout` 慣例 |
| A3 SQLite 外加記憶體一級快取 | 讀取更快 | 兩層要維持一致；60 秒輪詢下 SQLite 讀取成本可以忽略 | 白白增加複雜度，否決（YAGNI） |

**B. key 的粒度**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| B1 只按 `(pair, rate_date)` 存 | 跨查詢重用率最高 | 必須回答「某一天沒有列，是休市還是抓失敗」：推論週末違反 ADR-0010 S-2；台銀非 200 被吞成「沒有」（`fx.py:235-242`） | 高：會把缺洞固化 |
| B2 只按查詢區間存答案 | 與存取模式一一對應，不需要推論 | 換日後找不到前一天的答案，無法做跨區間的舊值退回 | 中 |
| **B3 查詢區間紀錄＋逐日匯率列（採用）** | 命中判斷完全依照查詢紀錄（不推論）；退回舊值可以跨區間取「區間內最新一筆」 | 兩張表 | 低 |

**C. 命中時的狀態標示**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| C1 沿用原本的 `FRESH`/`BACKUP` | 前端零改動 | 違反 `DataStatus` 定義（`interface.py:29-30`：fresh／backup 指的是「即時取得」）；違反 `is_within_ttl` 只對 `CACHED_STALE` 有意義的契約（`interface.py:94-97`、`valuation.py:161-167`） | 拿快取冒充即時值，違反 ADR-0003 約束 7 |
| C2 只標 `CACHED_STALE`，不另加欄位 | 與價格路徑一致 | 命中的 yfinance 匯率會失去「備援源」徽章：`FxStatusBadge.tsx:43-47` 在 `is_within_ttl===true` 時不顯示任何徽章 | 違反風控條件 (1)「`status=BACKUP` 徽章必現」（`0011:118`） |
| **C3 標 `CACHED_STALE` 加 `is_within_ttl` 加 `origin_status`（採用）** | 一份契約；備援的揭露不會消失；不新增 `DataStatus` 值（ADR-0005／ADR-0014 I-1） | 多一個欄位，前端徽章規則要改 | 低，需風控看兩個徽章並存時的呈現 |

**D. 新鮮度規則**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| D1 全部用單一時鐘 TTL | 簡單 | 歷史建倉匯率會被白白重抓 | 浪費上游請求 |
| D2 沿用 ADR-0009 `judge()` | 一致 | 匯率沒有交易所交易日，`policy_for(Market)` 套不上 | 會誤判 |
| **D3 已結算／暫定兩類＋備援重驗（採用）** | 歷史值零重抓；當日值有上限 TTL；台銀恢復後可以升回官方 | 多三個參數 | 參數未經實測，集中成常數 |

**E. 失敗時**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| E1 直接回不可用 | 最保守 | 一次失敗就讓所有美股部位變成 `insufficient_data`；60 秒輪詢時每輪都重跑梯子 | 擴大上游壓力 |
| **E2 回舊值並揭露，加失敗冷卻（採用）** | 與價格降級鏈一致；壓力有上限 | 需要新揭露句 | 風控審 |

**F. `cache_only`**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **F1 讀快取，沒有或過期才查（採用）** | 不需要新的 token 或字面；`/api/advice` 匯率成本降到每 30 分鐘最多一輪梯子 | 建議卡仍可能發出匯率 HTTP | 已明列為後果 |
| F2 完全不查來源 | 建議卡整本帳零網路 | 要新 token（`fx_*_not_queried`）、排程預熱、風控重審 `book.py:165-168` | 延後；重啟條件見本 ADR 延後項 L-1 |

**G. 擺放位置**

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **G1 decorator 實作 `FxRateProvider`，包住梯子（採用）** | 呼叫端零改動；梯子維持「純即時鏈」 | 多一個類別 | 低 |
| G2 寫進 `FxRateLadder` | 少一層 | 混淆「來源降級」與「快取策略」；梯子的測試全部要重寫 | 否決 |
| G3 寫進估值器 | 改動集中 | `resolve_fx_quote`（建議、警示、limits 都用）拿不到好處；同一份邏輯會出現兩份 | 否決 |

---

## Decision（決策）

**D-1 位置與介面**
- 新增 `app/data/fx_cache.py`：`FxRateCacheStore`，只管 SQLite 讀寫。
- 新增 `app/data/fx_service.py`：`CachedFxRateProvider(FxRateProvider)`，以 decorator 形式包住任一
  `FxRateProvider`；只在 `deps._default_fx_provider()` 內包一次，包住既有的 `FxRateLadder`。
- `FxRateProvider.get_daily_rates(pair, start, end)` 的簽名不變；`FxRateLadder`、`BankOfTaiwanFxAdapter`、
  `YFinanceFxAdapter` 的降級邏輯不變（唯一例外是 D-7 的 `complete` 旗標）。

**D-2 儲存（同 `STOCK_DESK_DB_PATH`，WAL、`busy_timeout` 沿用 cache.py 慣例）**
- `fx_rate_cache`：(pair, rate_date, source, rate TEXT, origin_status TEXT ∈ {fresh, backup}, fetched_at TEXT)，
  PK (pair, rate_date, source)。每次梯子回「可用」時，把回傳的每一筆寫入（upsert）。
- `fx_lookup_log`：(pair, window_start, window_end, last_success_at, success_source, success_origin_status,
  success_complete, last_attempt_at, last_failure_reason)，PK (pair, window_start, window_end)。
  成功或失敗都更新 `last_attempt_at`。
- 金額一律存 Decimal 字串；時間一律存 tz-aware UTC ISO8601。
- 任何欄位都不存 HTML 或回應 body（ADR-0011 紅線）。

**D-3 新鮮度（區間 [start, end]，以查詢紀錄判定，不推論休市）**
- `settle_at(end)` 的正式定義（2026-10-03 依 tech-architect 回覆取代原草案「(d + 1 日) 00:00 UTC + `FX_SETTLE_MARGIN`，台北日期與 UTC 日期都以較晚者為準」一句）：

  ```
  settle_at(end) = max(
      datetime.combine(end + 1 day, 00:00, tz=Asia/Taipei),   # end of Taipei calendar day `end`
      datetime.combine(end + 1 day, 00:00, tz=UTC),           # end of UTC calendar day `end`
  ) + FX_SETTLE_MARGIN
  ```

  - `end` 指查詢區間的迄日，不是單筆 `rate_date`。
  - 原意：快取模組不得認得來源名稱（見「紅線」），但兩個來源的「日期」屬不同日曆：yfinance 取自 UTC 時間戳（yfinance.py:385），台銀是台北日曆日（Context 5）。所以 `settle_at` 與來源無關，對兩種解讀取較晚者。
  - 實際值：Asia/Taipei 是固定 +08:00，所以 max 恆等於 UTC 那一項，即 `(end+1) 00:00 UTC + 2h` = `(end+1) 02:00 UTC`（台北 10:00）。實作可以寫成這個封閉式，但 docstring 要寫出 max 的來由，並以 C-7 的測試釘住數值。
- 「已結算」：`success_complete` 為真，且 `settle_at(end) <= last_success_at <= now`。
  - 下界含等號（`last_success_at` 正好等於 `settle_at(end)` 即為已結算）。
  - `last_success_at > now`（時鐘被撥回）時，一律不算已結算。
  - 下列 (b)、(c) 的「未滿」TTL 一律用嚴格小於：`now - last_success_at < TTL`。
- 「命中」條件：查詢紀錄存在，且區間內有 `source = success_source` 的列，且符合以下任一：
  - (a) 已結算，且 `success_origin_status = fresh`：永久有效。
  - (b) 已結算，且 `success_origin_status = backup`，且距 `last_success_at` 未滿 `FX_BACKUP_REVALIDATE`。
  - (c) 未結算，且距 `last_success_at` 未滿 `FX_PROVISIONAL_TTL`。
- `last_success_at` 或 `last_attempt_at` 在未來（時鐘被撥回）時，視為過期或不在冷卻期（比照 ADR-0009 R-6、freshness.py:74-81）。
- 參數（常數，不讀環境變數，全部「未經實測、待觀測回填」）：

| 參數 | 預設值 |
| --- | --- |
| `FX_PROVISIONAL_TTL` | 30 分 |
| `FX_SETTLE_MARGIN` | 2 小時 |
| `FX_BACKUP_REVALIDATE` | 24 小時 |
| `FX_FAILURE_COOLDOWN` | 10 分 |
| `FX_SINGLE_FLIGHT_MAX_WAIT` | 60 秒 |

**D-4 回傳契約（`FxRateResult` 新增三個有預設值的欄位，向後相容）**
- `is_within_ttl: bool | None = None`、`origin_status: DataStatus | None = None`、`complete: bool = True`。

| 情境 | status | is_within_ttl | origin_status | rates | reason |
| --- | --- | --- | --- | --- | --- |
| 即時（本次打了梯子且可用） | 梯子原樣（FRESH／BACKUP） | None | None | 梯子原樣 | 梯子原樣 |
| 命中 | CACHED_STALE | True | 記錄的 fresh／backup | 區間內該來源的列 | origin=fresh 時為 None；origin=backup 時為新字面 W-1，**不得**重播梯子含「本次」的句子 |
| 已結算的 backup 重驗失敗 | 同命中 | 同命中 | 同命中 | 同命中 | 同命中（已結算的值不因重驗失敗被標成「較舊」） |
| 舊值退回 | CACHED_STALE | False | 該列的 origin | 見下 | 新字面 W-2（含取得時間） |
| 無快取，失敗或冷卻中 | UNAVAILABLE | None | None | 空 | 本次有打梯子：梯子原因；冷卻中：新字面 W-3 |

- 舊值退回的選列規則：取區間內所有來源的列中日期最大者；同日以 origin=fresh 優先，再以 `fetched_at` 較新者優先。
- `as_of` 是匯率資料實際取得的時間；`staleness_minutes` 由此計算。
- 〔2026-10-08 加註（RK-5 N-3／R5-10／RK5-R5）：**提議（待 CEO 核可），尚未生效**；上列 D-4 條文在 CEO 核可前仍以原文為準〕提議在本節補一條：「快取命中」與「舊值退回」兩列，`FxRateResult.source` 應為**該列原本的 source id**，並以測試釘住。
  - 缺口：本節原文只寫了 `status`、`is_within_ttl`、`origin_status`、`rates`、`reason`，沒有寫明這兩種情境下 `source` 的值（tech-architect 新發現 N-3）。
  - 理由（風控引述）：source id 失真會讓 RK2-R2 的 72 字銜接句與 W-RK5-1 出現假的「混用」陳述，或讓 `GENERIC_SOURCE_NOTE` 歸錯來源。
  - 風控預先否決紀錄（轉述大意，非逐字）：W11-5 若缺 N-3（本節未寫明 source 值），不論 CEO 是否核可 C-24 的 RK-5 前置條件，風控預先否決出貨。本加註自身在 CEO 核可前不是已生效的條文；風控的否決立場以其裁定檔為準。
  - 來源與版本：tech-architect 2026-10-08 RK-4／RK-5 評估 N-3、R5-10（`work/reviews/2026-10-08-tech-architect-RK-4-RK-5-缺漏型揭露與fx_open來源評估.md`）；風控 2026-10-08 裁定 RK5-R5、「本次結論」RK-5 段與「否決理由」（`work/reviews/2026-10-08-RK-4-RK-5-風控裁定附條件APPROVE與X-10核對.md`）。tech-writer 未讀快取層 code（`app/data/fx_*.py` 依 RK-2 評估當時不存在）。

**D-5 失敗冷卻**
- `last_attempt_at > last_success_at`（或從未成功）且在 `FX_FAILURE_COOLDOWN` 內時，不打梯子，直接走舊值退回或回不可用。
- 比照 ADR-0009 D-8：沒有快取列時冷卻同樣生效。

**D-6 single-flight（程序內）**
- 以 (pair, start, end) 為單位，每個 key 一把鎖。
- 跟隨者等待 leader 完成後重讀 SQLite，不自己打梯子；等待超過 `FX_SINGLE_FLIGHT_MAX_WAIT` 時走舊值退回或回不可用，同樣不打梯子。
- leader 不論成功、失敗或例外都必須釋放鎖。
- 不提供跨程序保證：API 與 scheduler 在同一個 TTL 窗內最多各打一次，接受此代價。

**D-7 不完整的答案不得固化（比照 ADR-0009 R-4）**
- `BankOfTaiwanFxAdapter` 在區間內任一天回非 200 時（不含挑戰頁，挑戰頁已整體回不可用）設 `complete=False`。
- `FxRateLadder` 原樣傳遞此旗標。
- 快取把 `complete=False` 的答案一律視為「暫定」，永遠不升為「已結算」。

**D-8 估值與呼叫端**
- `PositionValuator._lookup_fx` 把 `FxRateResult.is_within_ttl` 與 `origin_status` 傳進 `FxInfo`。
- `FxInfo` 新增 `origin_status`（預設 None）。
- ADR-0010 D-2 的同輪 memo 保留：同一回應內同一 key 只讀一次，避免同一輪的讀取跨過 TTL 邊界而前後不一致。
- `cache_only` 估值器共用同一個包了快取的 provider（F1：讀快取，沒有或過期才查來源）。
  ADR-0010 R-1／R-2 只約束價格路徑（`get_cached_bars`、`PriceBarCache`）；cache_only 估值器的匯率路徑經 `CachedFxRateProvider`，可能發出 HTTP 並寫入 `fx_rate_cache`、`fx_lookup_log`，這是本 ADR F1 的明示例外。ADR-0010 已於 2026-10-03 在 R-1、R-2 加對應修訂註記；本例外的測試見 C-25。
- `FxQuote`（advice／alerts）本 ADR 不擴欄位：ADR-0011 列管項維持。但 `FX_APPLIED_NOTE` 會出現
  「資料狀態 cached_stale」字面（book.py:197-200），列為風控審查點 W-6。
- 〔2026-10-08 加註（RK-2）〕本節「共用同一個包了快取的 provider」不等於估值與風險卡（snapshot 報價）兩條路徑讀到同一個匯率，見附錄「與 ADR-0011 梯子的邊界」列下的同日加註。經查本節沒有出現「包在同一處才能維持兩條路徑讀到同一個匯率」這句，該句僅見於附錄該列；tech-architect 的加註草案把它歸在 D-8，此處以實際位置為準並在此留指引。（來源：`work/reviews/2026-10-08-tech-architect-RK-2-估值器與snapshot匯率來源一致性評估.md`「決策」段加註草案；風控重審 RK2-R9。）
- 〔2026-10-08 加註（RK-5 R5-10）：**提議（待 CEO 核可），尚未生效**；上列 D-8 條文在 CEO 核可前仍以原文為準〕提議：本節「`_lookup_fx` 把 `is_within_ttl` 與 `origin_status` 傳進 `FxInfo`」的傳遞，同樣適用 RK-5 新增的 `Valuation.fx_open`。
  - 背景：RK-5 採方案 (a)，`Valuation` 新增與 `fx` 並列的 `fx_open: FxInfo | None`，`FxInfo` 本身零 diff；fx_open 也由同一個 `_lookup_fx` 產生，所以 D-8 的 `origin_status`／`is_within_ttl` 會自動帶上；對應的 C-15 測試只需加一列 fx_open。RK-5 **不併入**本節的實作工作（併入會被 W-1～W-8 與 C-24 卡住），而是在 W11-5 之前獨立落地（PR-RK5a），資料形狀與本節對齊。
  - 狀態：`fx_open` 尚未落地（PR-RK5a 未合併，屬 tech-architect 評估的計畫）。
  - 來源與版本：tech-architect 2026-10-08 RK-5 評估「決策」、R5-1、R5-10、「與 ADR-0015 D-8 的關係與時機」；風控 2026-10-08 RK5-R9 要求 tech-writer 依 R5-10 加註。

**D-9 前端**
- `PositionFx` 型別加上 `origin_status`。
- 「備援源」徽章：`data_status === "backup" || origin_status === "backup"` 時顯示。
- 「資料較舊」徽章：維持 `cached_stale && is_within_ttl !== true` 時顯示。
- 兩者可以並存，呈現方式交風控審（W-5）。

**D-10 觀測**
- 每次 `get_daily_rates` 的結果不是單純命中時，寫一行 INFO log（英文）；觸發點是「結果不是單純命中」，不是「呼叫梯子」（跟隨者依 D-6 不呼叫梯子，但同樣要留一行）。
  - 涵蓋的結果：leader 打梯子、跟隨者等待結束（重讀或逾時）、冷卻短路、舊值退回；每種情況恰好一行。
  - 欄位：`pair`、`start`、`end`、`outcome`（∈ `ladder_ok`／`ladder_fail`／`follower_reread`／`follower_timeout`／`cooldown`／`stale_fallback`）、`status`、`origin_status`、`source`、`duration_ms`、`follower`（bool）。
  - 單純命中不寫 INFO，避免 60 秒輪詢洗版。
  - 不得記錄回應 body。

---

## 明確不該做的事（紅線）

- 不新增 `DataStatus` 值；命中不得標 FRESH 或 BACKUP。
- 不得以 1.0、內插、交叉匯率或區間外的列回答。
- 不得把梯子當次含「本次」的 reason 原樣用在快取命中或舊值退回上。
- 不得用環境變數開關快取或調整參數。
- 快取模組不得 import 任何具體 adapter，也不得寫死來源名稱；只認 `DataStatus`。
- `scripts/verify_market_data.py` 必須維持直接探測 adapter，不得經過快取。

---

## Consequences（後果）

**好處：**
- 在 60 秒輪詢下，每個幣別對的匯率 HTTP 從「每輪最多 16 次」降為「每 30 分鐘最多一輪梯子」
  （台銀被擋的現況約 2 次）。已結算的建倉匯率重啟後也不再重抓。
- API 與 scheduler 共享快取；scheduler 的警示 tick 也受惠。
- 來源全部失敗時可以退回舊值，不再讓所有美股部位整片變成 `insufficient_data`。
- 解鎖 ADR-0014 W16（前端輪詢）。

**代價（照實計）：**
- 當日 fx_now 最多落後 `FX_PROVISIONAL_TTL`（30 分）；畫面只顯示「MM/DD 匯率」，不顯示取得時間。
- 備援來源的已結算值在台銀恢復後，最多 24 小時才會升回官方值。
- 每次估值多 1～3 次 SQLite 讀；網路成本有冷卻時，API 路徑仍可能有 SQLite 寫入。
- `/api/advice` 的整本帳仍可能發出匯率 HTTP（F1），沒有做到「整本帳零網路」。
- 跨程序沒有 single-flight。
- 新增 3 句使用者可見字面（W-1～W-3）、1 條前端徽章呈現規則（W-5），並觸發 4 處既有字面重審（W-4、W-6、W-7、W-8）；任一重審結論為改字時，改後字面同樣適用 C-21。
- 接受 F1 的連帶後果：ADR-0010 風控逐字鎖定的 cache_only 兩組字面（`UNVALUED_POSITIONS_NOTE_CACHE_ONLY`、`CACHE_ONLY_BOOK_NOTE_*`）寫「本次未向來源查詢／更新」，對匯率路徑可能不再屬實，須重審（W-8）。
- 前端 FX 徽章新增 `origin_status` 分支；`test_fx_info_freshness.py:224-230` 的 key 集合斷言需要更新（屬預期內的契約變更）。

**已知限制：**
- 不建假日表、不推論休市；某區間持續沒有新匯率時，每個 TTL 窗仍然會重查一次。
- 台銀當日 CSV 的版本語意、yfinance FX 日線 timestamp 的對齊方式未查證；
  若 yfinance 日期錯位一天，「已結算」會把錯誤固化。對策是 settle margin 取保守值，並列為實測項。
- D-3 的 `settle_at` 對台銀等於多留 10 小時餘裕，對 yfinance 只有 2 小時。若「尚缺的事實」第 2 點查證後發現 yfinance 標為日期 d 的 K 棒在 `(d+1) 00:00 UTC` 之後才收定，就必須拿實測證據調大 `FX_SETTLE_MARGIN`；C-7 驗不到這件事。

---

## CEO 裁定（2026-10-03）

來源：CEO 2026-10-03 裁定（由任務單轉述）。草案原列三點「需要 CEO 決定」，CEO 對「核可匯率快取設計（ADR-0015）、接受當天匯率最多落後 30 分鐘、接受建議卡在快取過期時仍會連網」的回覆為「可以」，三點皆核可：

1. **核可本 ADR。** 這同時等於裁定 ADR-0011 第 3 題（「要幫 FX 補快取層」）。
2. **接受 F1**：建議卡的整本帳仍可能查匯率（快取過期時仍會連網）。若日後要求零網路，改走 F2，代價是新 token、排程預熱與風控重審（見延後項 L-1）。
3. **接受 `FX_PROVISIONAL_TTL` = 30 分的落後**（當天匯率最多落後 30 分鐘）。

**核可設計不等於可出貨。** 本 ADR 的 C-24 出貨閘門、W-1～W-8 風控審查（含 W-1～W-3 逐字核可、W-4～W-8 書面結論）與 C-19 的解鎖條件仍是實作前置條件，未滿足前 `_default_fx_provider()` 不得包快取、`refresh_after_s` 不得回非 null。本次裁定未對 W-1～W-8 做任何核可。

---

## 尚缺的事實（實作前或觀測期補齊，記錄查證日期）

1. 台銀 `flcsv/0/<今天>` 對當日回傳的是盤中最新一版，還是固定版本。
2. yfinance `TWD=X` 日線 timestamp 落在哪個 UTC 時刻（yfinance.py:385 以 UTC 取日期）。
3. 既存問題，與本 ADR 無關但會被放大：yfinance 揭露句寫「每日收盤價」（fx_notes.py:37-42），
   但盤中取到的是進行中的 K 棒，這句的事實性需要風控重審。

---

## 延後項

**L-1：F2（`cache_only` 完全不查來源）**

目前採 F1。F2 延後；刻意不訂數值門檻，因為目前沒有實測依據。

- **觸發條件（任一成立）**：
  - (a) CEO 要求 `/api/advice` 整書零網路；
  - (b) 使用者或 qa 回報 `/api/advice` 延遲，且 C-23 的 log 證實延遲來自 cache_only 路徑上的梯子呼叫。
- **前置條件（全部滿足才可上線）**：
  - scheduler 預熱 FX 區間，且預熱先於 F2 上線（比照 ADR-0010 D-4／R-13）；
  - 新增 missing token；
  - 風控重審 `book.py:165-168`；
  - 另立 ADR 或修訂本 ADR。

---

## 對實作的約束（逐條可檢查）

- **C-1**：diff 中 `FxRateProvider.get_daily_rates` 的簽名沒有變；`FxRateLadder`、`BankOfTaiwanFxAdapter`、`YFinanceFxAdapter` 除了 `complete` 旗標以外，沒有任何邏輯改動。
- **C-2**：`CachedFxRateProvider` 只在 `deps._default_fx_provider()` 被建構一次。`_default_valuator`、`_default_cached_valuator`、`get_fx_provider()` 拿到的是同一個實例（測試以 identity 斷言）。
- **C-3**：`app/data/fx_cache.py` 與 `app/data/fx_service.py` 不 import `app.portfolio`、`app.services`、`app.api`、`app.advice`，也不 import `fx_yfinance` 或 `BankOfTaiwanFxAdapter`。原始碼中不出現 `"bank_of_taiwan"`、`"yfinance_fx"` 字面（import graph 測試加 grep）。
- **C-4**：`DataStatus` 仍只有 4 個值；命中一律是 `CACHED_STALE`，`is_within_ttl=True`，`origin_status` 屬於 {FRESH, BACKUP}（有測試）。
- **C-5**：在暫定 TTL 內連續查詢，梯子呼叫次數 = 0；過了 TTL = 1（假時鐘加計數梯子）。
- **C-6**：origin=fresh 的已結算區間，時鐘推進 365 天，梯子呼叫次數 = 0。origin=backup 的已結算區間，滿 24 小時後 = 1；重驗失敗時仍回 `is_within_ttl=True`（有測試）。
- **C-7**：`settle_at` 邊界測試至少涵蓋下表。固定 `end = 2026-10-02`，所以 `settle_at = 2026-10-03T02:00:00Z`；每組都用假時鐘加會計數的梯子。

  | 測試 | 輸入 | 期望 |
  | --- | --- | --- |
  | 純函式 | `settle_at(2026-10-02)`；`settle_at(2026-12-31)` | `2026-10-03T02:00Z`；`2027-01-01T02:00Z` |
  | 1a 差 1 秒 | `complete=True`、`origin=fresh`、`last_success_at=2026-10-03T01:59:59Z`；clock=`2026-10-03T02:30:00Z` | 判為未結算（暫定且已過 TTL），梯子呼叫 = 1 |
  | 1b 正好到期 | 同 1a，但 `last_success_at=2026-10-03T02:00:00Z`；clock=`2027-10-03T02:00:00Z`（+365 天） | 判為已結算，梯子呼叫 = 0；回傳 `CACHED_STALE`、`is_within_ttl=True`、`origin_status=FRESH` |
  | 2a 台北 08:00／UTC 換日（防止誤用台北午夜） | `complete=True`、`origin=fresh`、`last_success_at=2026-10-02T18:30:00Z`（台北 10/03 02:30）；clock=`2026-10-03T00:00:00Z`（台北 08:00） | 判為未結算，梯子呼叫 = 1。若誤用「台北午夜 +2h」（10/02 18:00Z），這筆會被錯判為已結算 |
  | 2b 同一個換日點下的 key 切換（估值器層） | clock 從 `2026-10-02T23:59:59Z`（台北 10/03 07:59:59）走到 `2026-10-03T00:00:00Z`（台北 08:00） | fx_now 查詢區間由 `[09-25, 10-02]` 換成 `[09-26, 10-03]`；新 key 未命中，梯子呼叫 +1。換日點是 UTC，不是台北（`valuation.py:255`） |
  | 3 `complete=False` 永不結算 | `complete=False`、`origin=fresh`、`last_success_at=2026-10-05T00:00:00Z`（遠晚於 `settle_at`） | clock 為 `last_success_at + 29:59` 時梯子呼叫 = 0；`+30:00` 時 = 1；`+365 天` 時仍是 1，絕不會因為已結算而變成 0。只有在 `settle_at` 之後取得 `complete=True` 的答案，才升為已結算 |
- **C-8**：梯子失敗且有快取列時（D-4「已結算 backup 重驗失敗」列除外，該列維持 `is_within_ttl=True`），回 `CACHED_STALE`、`is_within_ttl=False`、reason 不是空字串，選列規則符合 D-4。沒有快取列時回 `UNAVAILABLE`，rates 為空（有測試）。
- **C-9**：冷卻期內梯子呼叫次數 = 0，過期後 = 1；快取完全沒有列時冷卻同樣生效；最後一次成功晚於最後一次嘗試時不進入冷卻（有測試）。
- **C-10**：時間戳在未來時，`last_success_at` 視為過期、`last_attempt_at` 視為不在冷卻（有測試）。
- **C-11**：K 個執行緒同時查同一個 key，梯子只被呼叫 1 次，且所有執行緒拿到同一份答案；不同 key 互不阻塞；leader 例外後鎖被釋放、下一次能再查；跟隨者逾時時不打梯子（threading 測試）。
- **C-12**：用同一個 db 檔建第二個實例（模擬重啟或 scheduler），讀得到第一個實例寫入的資料（有測試）。
- **C-13**：回傳的 rates 一律落在 [start, end] 內且 `date ≤ end`；沒有任何預設匯率、內插或交叉匯率（grep 加測試）。
- **C-14**：快取命中與舊值退回的 reason 不得等於梯子原句；用含「本次」的梯子 reason 做 fixture 測試。SQLite 兩張表中沒有任何以 `<` 開頭的字串欄位。
- **C-15**：`FxInfo.is_within_ttl` 與 `origin_status` 原樣傳遞。不傳快取時，`test_valuation*.py` 三個檔案的既有斷言不改就能通過；`test_fx_info_freshness.py` 只有 key 集合那條斷言因新增 `origin_status` 而改。
- **C-16**：ADR-0010 D-2 的同輪 memo 保留；一輪 `value_all` 內同一個 key 的 SQLite 讀取 ≤ 1 次。
- **C-17**：ADR-0014 I-4／防線 2 的「每張表列數不變」不變式，僅排除 `fx_rate_cache`、`fx_lookup_log` 兩張表（以表名明列，不得以 `fx_%` 之類的萬用字元排除），`price_bars_cache` 必須在不變式內；或該測試改用不經快取的假匯率 provider，此時不排除任何表。（修訂註記已於 2026-10-03 依此字面落在 ADR-0014 的 I-4 與「防線 2」。）
  - 理由：`price_bars_cache` 正是 ADR-0014 污染防線要守的表（ADR-0014 D-3「不得把 MIS 的價格寫進日線」、I-5），排除它會讓「`Quote` 被寫成 bar」偵測不到。
  - 日線快取會被寫入是既有行為（退回日線梯子時 `MarketDataService.get_daily_bars` 會寫快取，`app/data/service.py:182`），與本 ADR 無關。ADR-0014 測試應在布置上預先放入「新鮮」的日線快取，或改用不寫入的假日線服務。
- **C-18**：參數集中成單一模組的常數，各自註明「ADR-0015，未實測」；不讀 `os.environ`（grep）。
- **C-19（ADR-0014 W16 的解鎖條件）**：以下全部成立後，dev-lead 才可以讓 `refresh_after_s` 回非 null：
  - C-1～C-16、C-22、C-23、C-25 全部有測試且綠燈；
  - qa-reviewer（含 Codex）沒有 BLOCKING；
  - C-24 已滿足且已出貨；
  - 有一條「10 次連續 `build_summary`、TTL 內」的測試：梯子呼叫數 = 首輪的不同 key 數，第 2～10 輪為 0。
- **C-20**：`scripts/verify_market_data.py` 不 import `fx_service` 或 `fx_cache`（grep）。
- **C-21**：使用者可見的新字面要有風控逐字核可紀錄，並以守門測試釘住；核可前只能用占位字面，且要有守門測試禁止占位字面出貨（比照 ADR-0014 W9）。W-4～W-8 若結論為改字，改後字面同樣適用本條。
- **C-22（D-9 前端徽章，vitest；擴充 `app/lib/__tests__/fxStatusBadge.test.ts`）**：
  - `PositionFx` 型別新增 `origin_status: "fresh" | "backup" | null`；後端恆會送出這個 key。
  - 表格驅動測試必須覆蓋下表：

    | data_status | is_within_ttl | origin_status | 備援源徽章 | 資料較舊徽章 |
    | --- | --- | --- | --- | --- |
    | backup | null | null | 有 | 無 |
    | cached_stale | true | backup | **有**（現行 `FxStatusBadge.tsx:47` 會回 null，這是要修的退化） | 無 |
    | cached_stale | false | backup | 有 | 有 |
    | cached_stale | true | fresh | 無 | 無 |
    | cached_stale | false（或 null） | fresh | 無 | 有 |
    | fresh | null | null | 無 | 無 |
    | unavailable | null | null | 維持「資料不足」不變 | — |

  - 「備援源」徽章維持 amber 樣式，title 為 `source_note`；「資料較舊」徽章 title 為 `reason`。兩個徽章與台銀句同位置、同樣式，不得收進 tooltip（`0011:118` 條件 (1)）。
  - 判斷只讀 `data_status`、`is_within_ttl`、`origin_status`。前端原始碼不得出現 `"yfinance_fx"`、`"bank_of_taiwan"` 字面（grep），也不得用 `source` 推論。
  - `origin_status` 為 null 或 fresh 時，既有測試不改斷言就要通過（`fxStatusBadge.test.ts:58-60` 等）。唯一允許修改的是字彙 regex（`fxStatusBadge.test.ts:120-125`），改成容許兩個徽章並存，且須依 W-5 核可的呈現方式修改。W-5 核可前不得出貨並存呈現（比照 C-21）。
  - `valuation.py:162-166` 與 `FxStatusBadge.tsx:44-46` 兩段「FX 資料層沒有快取」的程式註解，接線後會變成不實，須同批改寫。
  - 〔2026-10-08 加註（RK-5 N-1／N-2／R5-10／RK5-R3／RK5-R4）：**提議（待 CEO 核可），尚未生效**；上列 C-22 條文在 CEO 核可前仍以原文為準〕提議把 C-22 的範圍擴及首頁（總覽）「備援匯率」徽章的判斷 helper（RK-5 PR-RK5c 要把 `page.tsx:62-64` 的判斷抽成純函式）：
    - helper 須加上 `origin_status === "backup"` 的分支（N-2），並**與 W11-5 放在同一個 PR**；表格驅動測試比照上表：總覽 helper 也要有「`cached_stale`／`is_within_ttl: true`／`origin_status: backup` → 有徽章」這一列（與 `FxStatusBadge` 相同）。
    - 缺口（N-2，危險方向）：原判斷只比對 `data_status === "backup"`，接線後快取命中（`cached_stale` 加 origin backup）時徽章會**消失**，備援揭露會在使用者面前消失。C-22 原文只涵蓋 `FxStatusBadge`，沒有涵蓋這個總覽徽章。
    - PR-RK5c 的徽章規則（RK5-R3，風控已核可語意變更，字面不變）：任一 **ok** 持倉的 `fx` 或 `fx_open` 是 backup，或（W11-5 時）`origin_status === "backup"`；語意從「任一部位」改成「任一已估值部位」。
    - 風控預先否決紀錄（轉述大意，非逐字）：W11-5 若缺 N-2（快取命中徽章消失），不論 CEO 是否核可 C-24 的 RK-5 前置條件，風控預先否決出貨。本加註自身在 CEO 核可前不是已生效的條文。
    - 來源與版本：tech-architect 2026-10-08 RK-4／RK-5 評估 N-1、N-2、R5-9、R5-10；風控 2026-10-08 裁定 RK5-R3、RK5-R4、「否決理由」。tech-writer 2026-10-08 親讀 `apps/stock-desk/frontend/app/page.tsx:62-64`：現況判斷為 `summary.data.positions.some((position) => position.valuation.fx?.data_status === "backup")`，只看 `fx.data_status`，不看 `origin_status`，也不看 `fx_open`（該欄位尚不存在）。
- **C-23（D-10 觀測 log，pytest `caplog`）**：
  - `outcome` 的六種值（`ladder_ok`、`ladder_fail`、`follower_reread`、`follower_timeout`、`cooldown`、`stale_fallback`）各寫 1 筆 INFO record（英文），且 D-10 列的必要欄位齊全。
  - 跟隨者那筆是 `follower=True`，同時梯子呼叫數不變。
  - 命中路徑沒有 INFO record。
  - 所有 record 都不含 `<`，也不含回應 body（ADR-0011 紅線，`0011:81`）。
- **C-24（快取接線出貨閘門）**：
  - W11-5（deps 接線）必須與 D-9 前端徽章變更在同一個 PR。
  - 合併前須同時滿足：C-22 綠燈；W-1～W-3 已有風控逐字核可；W-4～W-8 都有風控書面結論（結論可以是「維持現字面」）。
  - 尚未滿足時，`_default_fx_provider()` 不得包快取。
  - 理由：快取一接線，即使還沒開輪詢，`CACHED_STALE` 與 W-4～W-8 的既有字面就會在第一次載入畫面時上線。
  - 〔2026-10-08 加註（RK-2）：**提議（待 CEO 核可），尚未生效**；上列 C-24 條文在 CEO 核可前仍以原文為準〕提議在合併前須同時滿足的條件之外，增加一條前置條件：「PR-RK2 已合併，含 RK2-R1 篩選條件、RK2-R2 銜接句已經風控逐字核可、RK2-R3 測試全綠」。
    - 來源與版本：tech-architect 2026-10-08 RK-2 評估提出「RK-2 的 (d) 已合併」；風控 2026-10-08 重審附議並要求寫成上列完整寫法（RK2-R9、重審檔「逐條意見」第 4 項）。RK2-R1、RK2-R2、RK2-R3 的內容見 RK-2 任務單「風控重審裁定」段。
    - 風控等級裁定（引述）：「ADR-0015 W11-5 若在 PR-RK2 合併前接線，等級為 high，風控保留書面否決紀錄」。理由為情境 6 會讓 4b 型（附台銀方法論句、數字卻是 yfinance）整天持續。
    - 這會改動 accepted ADR 的出貨閘門，須由 CEO 核可並負最終責任。核可後由 tech-writer 把本段改為正式條文並註明核可日期；未核可前，請勿以本段作為已生效的閘門，也不得以此為由放行或阻擋 W11-5。
    - 依據檔案：`work/reviews/2026-10-08-RK-2-風控重審X3-F8-來源集合揭露附條件APPROVE.md`、`work/reviews/2026-10-08-tech-architect-RK-2-估值器與snapshot匯率來源一致性評估.md`、`work/dispatch/2026-10-08-任務單-RK-2-警示與決策卡匯率來源揭露與實際換算來源不一致.md`。
  - 〔2026-10-08 加註（RK-5 RK5-R6；附議 tech-architect 建議）：**提議（待 CEO 核可），尚未生效**；上列 C-24 條文與上方 RK-2 加註在 CEO 核可前仍以原文為準〕提議在合併前須同時滿足的條件之外，再增加 RK-5 前置條件，完整寫法如下：
    - PR-RK5a 已合併。
    - PR-RK5b 已合併，**W-RK5-1 已經風控逐字核可**、守門測試綠。
    - PR-RK5c 已合併：ok 篩選、`fx` 與 `fx_open` 兩個分支都在，vitest 綠，qa-e2e 通過。
    - 再加上 RK5-R4（C-22 加註：總覽徽章 helper 的 `origin_status === "backup"` 分支與 W11-5 同一個 PR）、RK5-R5（D-4 加註：快取命中與舊值退回時 `source` 為該列原本的 source id，並以測試釘住）。
    - **CEO 不核可時**：W11-5 出貨須附 CEO 書面知悉「**匯率貢獻可能長期混源，畫面無說明**」，風控等級 medium，風控保留紀錄；**RK5-R4、RK5-R5 仍然不能免**（風控預先否決紀錄：缺 N-2 或 N-3 的 W11-5，不論 CEO 是否核可本前置條件，風控都否決出貨）。
    - 風控等級裁定（引述，RK5-R7）：現況 low；W11-5 先於 PR-RK5b 合併 → medium；在該狀態下台銀曾回應過 → high。背景（tech-architect 評估「決策」與風控 X-12 方向）：ADR-0015 接線後，台銀 fresh 的已結算值永久有效，買入日匯率與目前匯率的混源會長期存在，而畫面（總覽揭露只列目前匯率來源、「備援匯率」徽章不看買入日匯率）沒有任何說明。
    - 這會改動 accepted ADR 的出貨閘門，須由 CEO 核可並負最終責任。核可後由 tech-writer 把本段改為正式條文並註明核可日期；未核可前，請勿以本段作為已生效的閘門，也不得以此為由放行或阻擋 W11-5。
    - 來源與版本：tech-architect 2026-10-08 RK-5 評估「是否需要 ADR 或加註」與「與 ADR-0015 D-8 的關係與時機」；風控 2026-10-08 裁定 RK5-R6、RK5-R7（`work/reviews/2026-10-08-RK-4-RK-5-風控裁定附條件APPROVE與X-10核對.md`）；RK-5 任務單「風控裁定」段（`work/dispatch/2026-10-08-任務單-RK-5-fx_open來源未記錄與總覽匯率貢獻混源.md`）。
- **C-25（cache_only 的寫入與 HTTP 計數，ADR-0010 R-1／R-2 的例外邊界）**：cache_only 估值器跑一輪：
  - 價格這一側，`put`、`record_fetch`、`record_attempt` 呼叫數都 = 0（ADR-0010 R-2 在價格路徑上仍成立）；
  - 快取 miss 時，有寫入的表只有 `fx_rate_cache`、`fx_lookup_log`；
  - 快取命中時，HTTP 呼叫數 = 0。

**需要風控審查的點**（文案交 creative-lead 起草）：

- **W-1**：快取命中且來源是備援時的原因句（不能用「本次」）。
- **W-2**：舊值退回時的原因句（含取得時間，以及「本次向來源更新未成功」）。
- **W-3**：冷卻期內、沒有快取時的原因句（比照 `COOLDOWN_NO_CACHE_REASON` 的寫法）。
- **W-4**：yfinance 揭露句裡「本次」與「每日收盤價」在快取與盤中情境下是否仍然屬實。
  - 〔2026-10-08 加註（RK-2）：**提議納入 RK-2 銜接句（待 CEO 核可 C-24 一併生效）**〕風控 2026-10-08 重審指出：RK-2 的銜接句（RK2-R2；兩句來源方法論句不一致時加的那一句，字面待 creative-lead 起草、風控逐字核可，尚未定稿）要併入本項的重審範圍，理由是快取接線後「本次」的語意會再變。在 CEO 核可前，本項重審範圍仍以原文為準。來源：`work/reviews/2026-10-08-RK-2-風控重審X3-F8-來源集合揭露附條件APPROVE.md`「RK2-R2」段末與「逐條意見」第 4 項。
  - 〔2026-10-08 加註（RK-4 RK4-R3／RK-5 RK5-R9）：**提議（待 CEO 核可 C-24 一併生效），尚未生效**；在 CEO 核可前，本項重審範圍仍以原文為準〕提議在上一條 RK-2 銜接句之外，再把下列三項併入本項的重審範圍：
    - **W-RK4-1**（RK-4 歸屬句：(A′) 不成立、(B) 成立時，標明來源說明只對應持倉市值與總資產的換算，價格與 ATR 沒有用這個匯率換算）。字面由 creative-lead 起草、風控逐字審，尚未定稿；風控裁定檔 RK4-R3 列為「列入 ADR-0015 W-4 的重審範圍」。
    - **W-RK5-1**（RK-5 總覽混源句：任一 ok 持倉的買入日匯率與目前匯率 source id 不同時，放在 `fx_disclosures` 最後）。字面由 creative-lead 起草、風控逐字審，尚未定稿；風控裁定檔 RK5-R9 要求加入本項的重審範圍。
    - **fx_open 揭露**（RK-5：`fx_disclosures` 納入 fx_open 來源句）。來源檔只寫「加入 fx_open 揭露」，具體重審問句待 tech-architect／風控確認。
    - 另依 RK4-R9／RK4-R10：W-RK4-1、W-RK5-1 納入 RK2-T6 失敗訊息的範圍；W-RK4-1 的組態比照 RK2-T9，推播在最壞情形下 ≤ 2000 字元。
    - 來源與版本：風控 2026-10-08 裁定 RK4-R3、RK4-R9、RK4-R10、RK5-R9（`work/reviews/2026-10-08-RK-4-RK-5-風控裁定附條件APPROVE與X-10核對.md`）；tech-architect 2026-10-08 評估 R5-10 末項「W-4 的重審範圍加入 fx_open 揭露與 W-RK5-1」與 RK-4 評估「是否需要 ADR 或加註」。- **W-5**：「備援源」與「資料較舊」兩個徽章同時出現時的呈現方式。
- **W-6**：建議卡 `FX_APPLIED_NOTE` 會顯示 raw 狀態值「cached_stale」。
- **W-7**：冷卻中缺匯率的部位被歸進「有向來源查詢」那句 `UNVALUED_POSITIONS_NOTE`（`book.py:543-546`）是否可以接受。
- **W-8**（2026-10-03 qa-reviewer 補列）：ADR-0010 風控逐字鎖定的 cache_only 兩組字面（`UNVALUED_POSITIONS_NOTE_CACHE_ONLY`、`CACHE_ONLY_BOOK_NOTE_*`，寫「本次未向來源查詢／更新」）在 F1 下對匯率是否仍屬實；ADR-0010 風控列管第 7 點已預告 FX 快取落地後須重審「或匯率」歸因。

分類（2026-10-03，tech-architect 回覆）：W-1～W-3 為新字面（出貨必要，逐字核可）；W-5 為前端徽章呈現規則；W-4、W-6、W-7、W-8 為既有字面重審（本 ADR 讓既有字面變得可能不實，結論可以是「維持現字面」）。出貨閘門見 C-24。

---

## 工作拆分與先後順序

承接 ADR-0014 W11（匯率跨請求快取，data-engineer → tech-architect）。建議由 data-engineer 依序拆成 W11-1～W11-6：

| 編號 | 工作 | 對應 |
| --- | --- | --- |
| W11-1 | `fx_cache.py` store、兩張表、WAL | D-2、C-12 |
| W11-2 | `CachedFxRateProvider`：命中、新鮮度、single-flight | D-3、D-6、C-5～C-7、C-10、C-11 |
| W11-3 | 失敗冷卻與舊值退回，先用占位字面加守門測試；含 D-10 觀測 log | D-4、D-5、D-10、C-8、C-9、C-21、C-23 |
| W11-4 | `FxRateResult` 新增欄位，以及台銀 `complete` 旗標 | D-7 |
| W11-5 | deps 接線與 identity 測試（與 D-9 前端徽章變更同一個 PR） | C-2、C-24、C-25 |
| W11-6 | 10 輪輪詢的計數測試 | C-19 |

- dev-lead 負責 `FxInfo` 的傳遞（D-8、C-15）；frontend-engineer 負責 `origin_status` 徽章規則（D-9、C-22）。
- creative-lead → risk-compliance-officer：W-1～W-8 併入 ADR-0014 W10 那一批送審；CEO 已於 2026-10-03 裁定上方「CEO 裁定（2026-10-03）」三點（原標題為「需要 CEO 決定」）。
- 實作完成後以 C-1～C-25 逐條驗收；C-19 是開啟 ADR-0014 輪詢的唯一閘門（C-19 的第一點涵蓋全部可測約束；C-17、C-18、C-20、C-21 屬文件／grep 類約束，於 C-24 與驗收時檢查，未重複列入）。

---

## 已釐清（2026-10-03）

落檔時由 tech-writer 提出的五點待釐清，tech-architect 於 2026-10-03 均已答覆。結論與對應的修訂位置如下：

1. **D-3 `settle_at` 的比較對象與算法**：比較對象是查詢區間迄日 `end`（不是單筆 `rate_date`），取台北與 UTC 兩個日曆日結束時刻的較晚者再加 `FX_SETTLE_MARGIN`，實際值為 `(end+1) 02:00 UTC`；「已結算」含等號、`last_success_at` 不得在未來。修訂位置：D-3、C-7、已知限制。
2. **使用者可見字面的數量**：統一為 3 句新字面（W-1～W-3）、1 條呈現規則（W-5）、3 處既有字面重審（W-4、W-6、W-7）；出貨閘門前移到快取接線（W11-5）。修訂位置：Consequences、C-19、C-21、新增 C-24、W 清單分類。
3. **C-17 排除日線快取表**：原寫法是錯的，會讓 ADR-0014 的污染防線失效；收斂為只排除 `fx_rate_cache`、`fx_lookup_log` 兩張表，`price_bars_cache` 必在不變式內。修訂位置：C-17、附錄末段，以及 ADR-0014 的 I-4 與「防線 2」兩處修訂註記。
4. **D-9、D-10 無對應 C 條**：新增 C-22（前端徽章表格驅動測試）與 C-23（log caplog 測試）；D-10 原文自相矛盾（跟隨者依 D-6 不呼叫梯子，卻要記錄是否為跟隨者），已改為「每次 `get_daily_rates` 結果不是單純命中時寫一行」。另新增 C-24（快取接線出貨閘門）與 C-25（cache_only 寫入與 HTTP 計數），並新增延後項 L-1 接住 F2 的重啟條件。修訂位置：D-8、D-10、Options F2、延後項 L-1、C-22～C-25、工作拆分。
5. **ADR-0011 是否加註記**：ADR-0010、ADR-0011 皆為 proposed，不需 CEO 裁定；採雙向標註，原文不改寫、狀態欄不動。已在 ADR-0011 的「與既有 ADR 的關係」、Consequences 與「需要 CEO 或使用者決定」第 3 題加註，並在 ADR-0010 的 R-1、R-2 加註。本 ADR 核可後，由 tech-writer 將 ADR-0011 註記的「擬由」改為「其第 3 題與 Consequences 一段已由 ADR-0015 處理」（落檔程序，不需另一則裁定；不使用「取代」一詞，與檔頭「不取代任何一則 ADR 全文」一致）。**〔2026-10-03：本 ADR 已獲 CEO 核可，ADR-0011 的三處註記已依此改寫，並將 ADR-0010、ADR-0014 內「ADR-0015（proposed）」字樣同步改為「accepted」。〕**

實作前仍需 tech-architect 定案的細節（不影響本 ADR 核可）：C-22 的「資料較舊」title 在 `reason` 缺值時是否用 fallback；C-23 的 outcome 在「梯子失敗後退回舊值」「冷卻後退回舊值」兩種複合情境下取哪一值、以及「恰好一行」的計算方式；D-5 冷卻期內、已結算 backup 已過重驗期時 `is_within_ttl` 應回 True 或 False。

## 查證限制

（以下為草案作者 tech-architect 的聲明，原樣轉錄。）

- tech-architect 沒有 Bash，所以沒有跑測試，也沒有用 git 確認分支；行號以 2026-10-03 讀到的工作目錄為準。
- 台銀與 yfinance 的行為（「尚缺的事實」第 1、2 點）在草案作者的環境無法查證。

---

## 附錄：tech-architect 評估摘要（草案第 2 節，原樣轉錄）

| 題目 | 結論 | 主要依據 |
| --- | --- | --- |
| 放記憶體還是 SQLite | **SQLite**（同 `STOCK_DESK_DB_PATH`、WAL）＋程序內 single-flight | scheduler 是另一個程序：`compose.yaml:29-44` 是獨立 service。它的警示 tick 也會查匯率（`scheduler.py:176-177,184-193` → `alerts/snapshot.py:84`），只放記憶體就無法共享。服務會重啟（`restart: unless-stopped`），已結算的建倉匯率每次重啟重抓沒有意義。「來源全掛時退回舊值」也需要能撐過重啟。API 是單一 worker（`compose.yaml:20` 沒有 `--workers`），所以 single-flight 在程序內就能完整成立 |
| key | 查詢紀錄以「幣別對＋查詢起日＋查詢迄日」為 key；匯率值以「幣別對＋匯率日期＋來源」為 key | 兩個呼叫端都是同一種問法：「target 往前 7 天內最新一筆」（`valuation.py:386-389`、`services/fx.py:84`）。單用日期 key 必須推論週末，這違反 ADR-0010 S-2。台銀非 200 的日子也會被當成「當天沒公告」（`fx.py:235-242`），無法分辨 |
| 新鮮度 | 已結算的查詢區間永久有效。當日暫定值 TTL 30 分。備援來源的已結算值每 24 小時重驗一次，用來嘗試升回官方來源 | 匯率在本產品是「日」粒度（`FxInfo.as_of` 只有日期）。但「今天」那根資料盤中會變：yfinance 的當日 K 棒是進行中的值。台銀牌告營業時間內會調整，`flcsv/0/<今天>` 回的是哪一版**未查證**。不沿用 ADR-0009 的 `judge()`，因為它以交易所交易日判定，匯率沒有交易所交易日 |
| single-flight | 同一個查詢 key 在程序內只打一次上游；跨程序不保證 | `RateLimitedClient._throttle` 持鎖 sleep（`http.py:204-213`），yfinance client 由美股備援、指數、匯率三個角色共用（`deps.py:58-67`），重複查詢會直接吃掉別人的節流預算 |
| 失敗降級 | 回舊值並標示 `CACHED_STALE` 加 `is_within_ttl=False` 加原因。完全沒有快取時回 `UNAVAILABLE`。另設失敗冷卻 | 與價格的降級鏈一致（ADR-0009 D-3/D-8）。也回答了 ADR-0011「需 CEO 決定」第 3 題（`0011:109`）。仍然維持絕不捏造匯率（`0011:83`） |
| `cache_only` | 匯率改為「讀快取，沒有或過期才查來源」，**不是**完全不查 | 現況是 `cache_only` 只管價格，匯率一直即時查（`valuation.py:386-388` 沒有依模式分支；ADR-0010 D-2 已承認）。改成完全不查需要新的 missing token、排程預熱，還要風控重審 `UNVALUED_POSITIONS_NOTE_CACHE_ONLY`（`book.py:163-168` 已列管），代價不成比例，列為延後選項 |
| 與 ADR-0011 梯子的邊界 | decorator 包在 `_default_fx_provider()` 的梯子外，只認 `DataStatus`，不認來源名稱 | `deps.py:140-160` 的單例同時供估值與風險卡使用，包在同一處才能維持「兩條路徑讀到同一個匯率」 |

〔2026-10-08 加註（RK-2）；原文保留，上列最後一列的推論不實〕
- **不保證讀到同一個來源**：共用同一個 provider 物件（`deps.py:140-160`）只是必要條件。本附錄「key」列已寫明快取以「幣別對＋查詢起日＋查詢迄日」為 key；估值器的查詢迄日是今天，snapshot 報價的查詢迄日是最後日線日，兩者是不同 key，所以不保證讀到同一個來源。
- **接線後分歧會持續（RK-2 評估情境 6）**：今天的區間是暫定值（TTL 30 分鐘），最後日線日的區間是已結算值（本附錄「新鮮度」列：已結算區間永久有效，但備援來源的已結算值每 24 小時重驗一次）。兩種 TTL 不同，使分歧由瞬間競態變成持續數小時到一整天。評估檔的描述：台銀剛恢復時 4a 型（附 yfinance 句、數字其實是台銀）最長持續 24 小時；台銀恢復後又被擋時，報價端是永久有效的台銀已結算值、估值端每 30 分鐘落 yfinance，形成 4b 型（附台銀句、數字卻是 yfinance），整天持續。
- **目前狀態**：依評估檔 2026-10-08 的 grep，`app/` 內 `CachedFxRateProvider` 零命中、`app/data/fx_*.py` 不存在，快取尚未接線；上述為接線後的推定，未實測。
- **處置**：RK-2 採 (d) 來源集合揭露（PR-RK2，狀態見 RK-2 任務單），本 ADR 的決策內容不變；C-24 前置條件與 W-4 重審範圍的提議見 C-24、W-4 下的同日加註（均待 CEO 核可）。
- 來源與版本：`work/reviews/2026-10-08-tech-architect-RK-2-估值器與snapshot匯率來源一致性評估.md`（情境 6、「決策」段加註草案）、`work/reviews/2026-10-08-RK-2-風控重審X3-F8-來源集合揭露附條件APPROVE.md`（RK2-R9，tech-writer 2026-10-08 轉錄）。TTL、key 與 `deps.py:140-160` 的行號取自本附錄原文，tech-writer 未重新讀 code 驗證。

另有一個與 ADR-0014 互相影響的點：ADR-0014 I-4／防線 2（草案作者所引為 `0014:304,415`；該行號與現行檔不一致，請以節名 I-4、「防線 2」定位）要求「含盤中報價的 `build_summary` 前後 SQLite 每張表列數不變」。匯率快取一旦寫入 SQLite，這條字面就會被打破。草案要求在 ADR-0014 補一條修訂，把範圍收斂為「報價不落地任何表；匯率快取表不在此不變式內」，或在測試中改用假的匯率 provider。本 ADR 在 C-17 明列這一點，修訂註記已落在 ADR-0014。〔2026-10-03：原草案此處同時排除日線快取表，已依 C-17 收斂，只排除 `fx_rate_cache`、`fx_lookup_log`，`price_bars_cache` 仍在不變式內。〕
