# ADR-0019：stock-desk 日線 coverage 判定與「取得時間」單一基準（部分取代 ADR-0009 D-3／D-5）

- 狀態：proposed（待 CEO 核可；D-5 已由風控裁示 (b)）
- 日期：2026-10-04
- 決策者：tech-architect（草案）、CEO（核可）；D-5 字面由 risk-compliance-officer 裁示
- 適用範圍：僅 product/stock-desk 產品線
- 取代：ADR-0009 D-3 的 layer 0 條件（「(a) fetch log 存在且 `covered_start ≤ start`，再依 `judge()`」與 CHECKED_RECENTLY 的
  `covered_end` 附帶條件），以及 D-3／D-5 中 `last_fetched_at` 作為 `judge()` 的 `last_checked_at` 與 staleness 基準的角色。
  ADR-0009 其餘條文（D-1、D-2、D-4、D-6、D-7、D-8、「不相鄰則取代」規則、R-8、混源明示）維持有效。
  ADR-0010 D-1 的 cache-only 讀取改用本 ADR D-1 的判定式；ADR-0010 R-1／R-2（只回 CACHED_STALE／UNAVAILABLE、不寫 log）不變。
- 編號說明：落檔時 `docs/adr/` 目錄查無 0019，repo 內（`*.md`／`*.py`／`*.yml`）亦無 ADR-0019 引用；0013 為員工線佔用（見 ADR-0017 編號說明），不得挪用。
- 來源與版本：本檔為 tech-architect 2026-10-04 handback（ADR-0019 草案）的落檔，B 類轉錄，僅做格式調整，技術內容未增補、結論未改動。
  - 「Context」「Options」「Decision」「Consequences」逐字取自該 handback「決策（ADR 草案）」區塊內的 markdown（含上方檔頭 metadata 的「狀態」「日期」「決策者」「適用範圍」「取代」五項）。
  - 「對實作的約束」K-1～K-14、「測試要求」T-1～T-14（含末段「既有測試若斷言…」一句）逐字取自該 handback。
  - 「附錄 A：方案比較」兩張表、「附錄 B：架構師評估摘要」逐字取自該 handback（附錄 A 僅將原標題降階以符合本檔層級）。
  - 檔內所有 `檔案:行號`（例：`service.py` L414–L426）、函式名、欄位名、數字（例：TW 540 天約 18 次 HTTP、`max_gap_days=830`、540 根）均為草案作者與其引用的 L-10c 路徑分析所述；tech-writer 落檔時**未重新對 code 驗證**。行號會隨 commit 漂移，引用時以原文定位。
  - 落檔時的快照：分支 `product/stock-desk`，HEAD `588ded64be25d505e1d8d6df8bfcd0b6c33dc3f6`（tech-writer 於落檔時讀取 `.git/refs/heads/product/stock-desk`）。此為快照，之後 HEAD 可能前進。
  - 此為 proposed 狀態；依 ADR-0001，生效前的內容可修訂，生效後不得原地改寫決策。

---

## 關聯

- 依據：`work/research/L-10c-取得時間基準不一致-路徑分析-2026-10-04.md`（dev-lead，含 scratchpad 實測重現）。
- 源於：L-10／L-10c，見 `work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md`。
- 對 ADR-0009 的處理：ADR-0009 只在檔頭「修訂」清單加一行指標（見 K-14），不改決策內文；該指標行標明「ADR-0019 accepted 後生效」。
- 對 ADR-0010 的影響：D-1 的 cache-only 讀取改用本 ADR D-1 判定式（見檔頭「取代」）；本落檔未修改 ADR-0010。
- 風控立場（`work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md` 末段，2026-10-04）：D-1（空洞）與 D-2（P4）為 required 等級，不接受以揭露代替修正（列管 L-10h）；
  L-10g（`LeverageChapterView.tsx` 以「日線取得時間」顯示列層 `as_of`）為新增列管，本 ADR 改 accepted 前必須結案（見 K-13）。
- 狀態為 proposed 的理由：
  1. 待 CEO 核可。
  2. D-5 已由 risk-compliance-officer 於 2026-10-04 裁示 (b)（見 D-5）；僅待 CEO 核可。

---

## Context（背景）

L-10c 路徑分析（`work/research/L-10c-取得時間基準不一致-路徑分析-2026-10-04.md`，dev-lead，scratchpad 實測重現）指出兩個問題：

1. **P4（高估新鮮度）**：回測或事件研究抓的歷史區間與既有 coverage 重疊或相鄰時，`record_fetch` 把 coverage 擴成聯集，並把 `last_fetched_at`
   設成本次時間，但最新日線並沒有重抓。之後個股頁徽章以 `last_fetched_at` 為基準，顯示「5 分鐘前取得」，實際上最新日線是 185 分鐘前取得的。
   同一個值也被拿來當 `judge()` 的冷卻基準與 S3-1 早公布證據的冷卻閘門，所以一次歷史抓取會讓序列「看起來剛確認過最新」。
2. **coverage 空洞**：不相交的歷史區間會依 D-3 取代 coverage，但舊區間的 bar 列仍留在快取裡。D-3 的 layer 0 條件只檢查 `covered_start`，
   裁決為 HAS_LATEST_SESSION 時不檢查 `covered_end`。實測：先跑 2020-01-02～2022-12-30 回測，再請求 2022-06-01～2026-09-30，
   結果 `provider_called=False`、回 540 根、`max_gap_days=830`，被當成「本機快取、已含最近交易日」回覆，指標跨過空洞計算。
   cache-only 讀取（ADR-0010）與全梯子失敗的降級路徑用同樣的 `covered_start ≤ start` 條件決定 `is_within_ttl` 與分鐘數，有相同缺陷。

兩個問題的共同根源：fetch log 用單一區間加單一時間戳，同時承擔「哪些日期抓過」「最新那段何時確認過」「最後一次完整成功是什麼時候」三種語意。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| A 照字面不推進 `last_fetched_at` | 改一處 | 打壞 R-8 的 `attempted > last_success` 比對 | 成功後被誤判為「最近一次未成功」並擋住抓取一個冷卻窗；否決 |
| **A′ 拆出 `tail_fetched_at`（本案）** | 精確；R-8／D-8 不動；只加欄 | 多一欄；歷史區間請求的分鐘數可能偏舊（保守） | 用錯欄；以約束與 grep 防 |
| B coverage 改區段集合 | 根治 P4 與區間來回取代的成本 | 重建表、合併邏輯、D-7 與三個消費者全改 | 改動面大；暫緩列管 |
| C 由 bar 列 `fetched_at` 推導 | 不改 schema | 部分抓取也寫列，會把部分回答當確認 | 過度宣稱；否決（僅作遷移回填上限） |
| **H1 統一 coverage 判定式（本案）** | 在單一區間不變式下精確；既有空洞狀態讀取時即修正 | P1 之後判定較保守 | 低 |
| H2 不相交時拒絕取代 | — | 近期請求永遠拿不到 coverage | 否決 |
| H3 以列連續性偵測缺口 | 直接 | 啟發式；停牌會誤判 | 否決 |

完整版方案比較（P4 修法、空洞 bug 修法兩張表，含 H2′）見「附錄 A：方案比較」。

## Decision（決策）

- **D-1（coverage 判定式，取代 ADR-0009 D-3 的 layer 0 條件）**
  在 `app/data/freshness.py` 新增純函式
  `coverage_reaches(*, covered_start: date, covered_end: date, tail_fetched_at: datetime | None, start: date, expected: date) -> bool`。
  只在 `covered_start ≤ start`、`covered_end ≥ expected`、`tail_fetched_at` 非空三者都成立時回 True。
  `expected` 一律是 `expected_session(policy, requested_end=end, now=now)`。
  在 coverage 是「單一連續且完整取得的區間」這個不變式下，判定式成立就代表 `[start, expected]` 全部向來源完整問過；
  `(expected, end]` 依 D-1 的公布假設不會有已公布交易日。
  `judge()` 的三個消費者都必須先過這個判定式：
  - layer 0（`_try_session_fresh_cache`）：判定式不成立時，走原本 `covered_start > start` 的分支（R-8：冷卻期內且最後一次提問晚於最後一次完整成功，
    就以 `cached.fetched_at` 為基準回快取並附原因；否則走梯子）。原本 CHECKED_RECENTLY 的 `covered_end < expected` 檢查被這條吸收。
  - cache-only 讀取（`get_cached_bars`，ADR-0010 D-1）與全梯子失敗的降級（`_fall_back_to_cache`）：判定式不成立時，`checked_at = cached.fetched_at`、
    `is_within_ttl=False`，不呼叫 `judge()`。
  不以 bar 列的連續性作為判定依據。

- **D-2（fetch log 的兩個時間戳，取代 ADR-0009 D-3／D-5 中 `last_fetched_at` 的角色）**
  `price_bars_fetch_log` 新增 `tail_fetched_at TEXT`（可為 NULL）。兩欄語意：
  - `last_fetched_at`：最後一次**任何範圍**的完整成功（語意與 ADR-0009 相同）。**只**用於 R-8／D-8 的
    「最後一次提問是否晚於最後一次完整成功」比對。
  - `tail_fetched_at`：`covered_end` 這一端最近一次被**完整**向來源問過的時間。用於 `judge()` 的 `last_checked_at`、
    S3-1 早公布證據的冷卻閘門、`_cached_result` 的 `checked_at`（即 `staleness_minutes` 與回傳 `as_of`）。
  `record_fetch(start, end, fetched_at)` 在同一個 `BEGIN IMMEDIATE` 交易內：`last_fetched_at` 一律設為 `fetched_at`；
  `tail_fetched_at` 只在以下情況設為 `fetched_at`：無舊列、新區間與舊區間不相交（取代）、或 `end ≥ 舊 covered_end`。
  其他情況（新區間完全落在舊區間內，或只往前延伸）保留舊值。
  「不相鄰則取代」規則維持 ADR-0009 原樣。

- **D-3（遷移）** 啟動時若缺 `tail_fetched_at` 欄：在 `BEGIN IMMEDIATE` 內重新檢查 `PRAGMA table_info`，然後 `ALTER TABLE ... ADD COLUMN`，
  並只在加欄當下回填一次。每列取 `min(last_fetched_at, 該序列在 [covered_start, covered_end] 內最新 trade_date 那一列的 fetched_at)`，
  以 tz-aware datetime 在 Python 端比較。找不到列或解析失敗時留 NULL；NULL 依 D-1 視為判定式不成立。
  不刪任何 bar 列或 coverage，不連網，不做一次性重建；既有的空洞狀態由 D-1 在讀取時修正。

- **D-4（live 回應的取得時間）** `MarketDataService` 在 live rung 回傳的 `ProviderResult.as_of` 改為本次寫入 `put`／`record_fetch` 的同一個
  `fetched_at`（服務端時鐘），不再沿用 provider 呼叫開始時蓋的章。這樣同一次取得，在 live 回應與之後的快取回應中呈現同一個時間（修 L-10c P5）。
  `PriceBar.as_of` 維持「寫入該列那次抓取的 provider 時間」，屬於列層級出處，不是序列的取得時間。

- **D-5（L-10c 對齊基準，資料介面層表態；字面由風控裁示）**
  序列層級的「取得時間」只有一個定義：服務回傳的 `ProviderResult.as_of`（快取路徑即 `checked_at`）。
  `PriceBar.as_of` 與訊號層各 `as_of` 欄（`signals/frame.py::provenance` 等）是機器可讀的列出處，**不得**以「取得」字樣顯示給使用者。
  **風控裁示（2026-10-04）：選 (b) 拿掉建議卡時間（比照 V-3A），不新增欄位。** (a)（對齊：`DataMeta` 新增 `fetched_at`、卡片改讀 `data.fetched_at`）已否決，理由見
  `work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md` 末段「L-10c／ADR-0019 D-5 與 L-10b-2 裁示」。
  (b) 的核可字面（`AdviceCardView.tsx`，風控紀錄逐字）：
  `規則版本 {advice.rules_version}｜觀察區間：{advice.observation_window.start ?? "—"} ~ {advice.observation_window.end ?? "—"}（{advice.observation_window.bars ?? "—"} 根日線）`。
  卡片任何位置不得再渲染 `advice.as_of`。

## Consequences（後果）

- 好處：空洞序列不再被說成「本機快取、已含最近交易日」，指標不再跨空洞計算；歷史區間抓取不再讓徽章與冷卻看起來剛確認過最新；
  R-8 不會把成功誤報成未成功；live 回應與之後快取回應的取得時間一致。
- 代價：
  - fetch log 多一欄，三個消費者要分清楚用哪一欄。
  - 完全落在舊區間內的歷史請求，分鐘數顯示的是尾端的確認時間，可能比該段實際抓取時間舊（低估新鮮度，屬保守方向）。
  - 不相交區間仍會互相取代：歷史回測與每日個股頁／排程之間來回時，回到近期請求會整段重抓（TW 540 天約 18 次 HTTP），
    沿用 ADR-0009 已列管的代價。**觸發改區段集合（方案 B）的條件**：觀測到 TWSE 限流、AV 額度因此用盡，或使用者回報回測後個股頁明顯變慢。
  - 部分抓取（P1）把最新列寫到 `covered_end` 之後時，該序列會從「current=True、分鐘數偏舊」改為「冷卻期內 current=False，附『最近一次向來源取得資料未成功』，
    分鐘數取最舊列」，冷卻期過後重抓。這是保守方向（只增加抓取、只降低宣稱）；與 L-10c P3 的「回落最舊 `fetched_at`」同屬既有 R-2 取捨。
  - 遷移回填的殘餘誤差：P4 與部分抓取都發生過的序列，回填值可能仍比真實尾端時間新，到下一次尾端抓取時自癒。
- 已知限制：降級路徑（R-8、全梯子失敗）仍回傳快取中現有的列，可能含內部缺口，但一律 `is_within_ttl=False` 並附原因；本 ADR 不新增缺口揭露。
- 約束：見「對實作的約束」K-1～K-14。

---

## 對實作的約束

### K-x（逐條可檢查）

- **K-1** 判定式只存在一份，即 `freshness.py::coverage_reaches`。`service.py` 中除了 `_incremental_start`（D-7 自己的條件）以外，不得再出現 `covered_start <=`、`covered_start >` 或 `covered_end <` 的行內比較（可 grep 驗證）。
- **K-2** 三個 `judge()` 消費者（`_try_session_fresh_cache`、`get_cached_bars`、`_fall_back_to_cache`）都必須先呼叫 `coverage_reaches`，判定式不成立時不得呼叫 `judge()`，也不得用任何 fetch log 時間當 `checked_at`。
- **K-3** 欄位用途固定：
  - `tail_fetched_at` 只出現在：`judge(last_checked_at=...)`、S3-1 的 `is_within_cooldown` 閘門、`_cached_result(checked_at=...)`。
  - `last_fetched_at` 只出現在 R-8/D-8 的 `attempted > last_success` 比對。
  - 兩者不得互換或混用。
- **K-4** `record_fetch` 的 `tail_fetched_at` 推進規則照 D-2，並且在既有的 `BEGIN IMMEDIATE` 交易內完成讀取與寫入。
- **K-5** 不相交區間維持取代。本輪不得引入多列 coverage，也不得拒絕取代。
- **K-6** `FetchCoverage` 新增 `tail_fetched_at: datetime | None`。NULL 或解析失敗時，判定式一律不成立，不得以 `last_fetched_at` 代填。
- **K-7** 遷移照 D-3：加欄前先 `PRAGMA table_info` 檢查，在 `BEGIN IMMEDIATE` 內重新檢查；只在加欄當下回填一次；不刪列、不連網；第二次啟動不得再動既有的值。
- **K-8** `get_cached_bars` 仍然不寫兩張 log、不 `put`（ADR-0010 R-2）。
- **K-9** 判定 coverage 時不得使用 `market_trading_days` 或任何列連續性的啟發式；測試裡可以用它當 oracle。
- **K-10** `_incremental_start`（D-7）的三個條件不變。
- **K-11** live rung 回傳的 `ProviderResult.as_of` 必須等於同一次 `put`／`record_fetch` 用的 `fetched_at`（D-4）。實作前 dev-lead 要先 grep 服務端 `as_of` 的所有消費者（含指數與基準路徑），列在 PR 裡。
- **K-12** 本 ADR 不改徽章八句字面（`dataMetaStatusBadge.test.ts` 不得修改）。D-5 的畫面字面以風控 2026-10-04 核可版為準（見 D-5），不得另行變動。
- **K-13** 前端任何檔案不得以「取得」字樣顯示 `PriceBar.as_of` 或訊號層各 `as_of` 欄；`AdviceCardView.tsx` 不得讀 `advice.as_of`；`LeverageChapterView.tsx` 現行兩行（L-10g）為已知殘餘，替代字面落地前暫留，本 ADR 改 accepted 前必須結案；以 grep 守門測試釘住。
- **K-14** ADR-0009 只在檔頭加指標行，不改 D-x 內文。

---

## 測試要求

全部用假 provider、假 clock，不連網，不碰 `backend/data/*.db`。

### 空洞 bug

- **T-1（必含，dev-lead 重現情境）**
  - 前置：快取先有 2024-04～2026-09-30 的列，以及對應的 coverage。
  - 操作：`record_fetch` 寫入 2020-01-02～2022-12-30（不相交，取代 coverage），然後在 2026-10-01 08:00 UTC（台北週四 16:00）請求 2022-06-01～2026-09-30。
  - 斷言：provider 被呼叫，請求起點是 2022-06-01；結果不是 CACHED_STALE + `is_within_ttl=True`；回傳序列以週間格點計 `max_gap_days ≤ 3`；事後 coverage 為 2020-01-02～2026-09-30。
  - 這個測試必須先在 HEAD 上失敗，PR 要附上失敗輸出作為證據。
- **T-2** 同 T-1 的前置，改走 `get_cached_bars`。斷言：`is_within_ttl=False`；`as_of` 不等於歷史抓取時間；兩張 log 與列數都不變。
- **T-3** 同 T-1 的前置，所有 provider 都失敗、走 `_fall_back_to_cache`。斷言：`is_within_ttl=False`；`staleness_minutes` 以列的最舊 `fetched_at` 計算。

### P4

- **T-4（必含，dev-lead S2）**
  - 前置：coverage 為 [A, 最新]，T0 時尾端取得。
  - 操作：T0+180 分做一次重疊的歷史抓取，T0+185 分請求個股頁區間。
  - 斷言：`staleness_minutes == 185`；`as_of == T0`；`last_fetched_at == T0+180`；`tail_fetched_at == T0`。
- **T-5** 延續 T-4，下一次請求的裁決是 REFETCH 時，provider 必須被呼叫，回應不得帶 `RECENT_ATTEMPT_FAILED_REASON`（對應方案 A 的陷阱）。
- **T-6** `record_fetch` 單元測試逐一覆蓋推進規則，每一種情況同時斷言兩欄：
  - 無舊列：推進。
  - 重疊且 `end ≥ old_end`：推進。
  - 在舊區間之後相鄰：推進。
  - 被舊區間包含：保留舊值。
  - 在舊區間之前相鄰：保留舊值。
  - 不相交在前、不相交在後：都取代並推進。
  - `end == old_end`：推進。
- **T-7** 冷卻期內的歷史成功抓取，不得壓掉 S3-1 早公布證據觸發的 REFETCH（延伸 `test_another_series_holding_the_next_session_means_the_close_is_out`）。
- **T-8** CHECKED_RECENTLY 的冷卻以 `tail_fetched_at` 判定；`test_a_historical_coverage_is_not_reused_for_a_request_that_runs_to_today` 必須繼續通過。

### 判定式與遷移

- **T-9** `coverage_reaches` 純函式邊界：`covered_start == start`；`covered_end == expected`；`covered_end` 早一天；請求 end 落在週末；`tail` 為 None。
- **T-10** 遷移：
  - 以舊 schema 建立 DB（無該欄）後，回填值等於 `min(...)`；序列無列時為 NULL。
  - NULL 序列 layer 0 不服務，R-8 仍正常運作。
  - 第二次初始化不改變任何值。
  - 兩個 `PriceBarCache` 指向同一個檔案先後初始化，不報 duplicate column。

### 回歸

- **T-11** `test_a_disjoint_range_replaces_the_coverage_instead_of_bridging_the_gap` 保留，並補上兩欄的斷言。
- **T-12** D-7 增量抓取在修正後仍只發 1～2 次呼叫，且 `tail_fetched_at` 有推進。
- **T-13** P1 情境（尾段某月 `complete=False`）在修正後的行為照 Consequences 所述：冷卻期內 `is_within_ttl=False` 並附原因；冷卻期過後重抓。
- **T-14（D-4）** live 回應的 `as_of`、fetch log 的 `tail_fetched_at`、之後快取回應的 `as_of` 三者相等。

既有測試若斷言「`covered_end < expected` 仍由快取服務」，代表該測試釘住的正是這個 bug。只能依 D-1 改寫，PR 要逐條說明，不得放寬。

---

## 附錄 A：方案比較（tech-architect 原文，逐字轉錄）

### P4 修法

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 照字面：新區間沒涵蓋舊 `covered_end` 時不推進 `last_fetched_at` | 改一處 | `last_fetched_at` 同時被 R-8/D-8 拿來比對 `attempted > last_success`。回測成功後 attempt 新、`last_fetched_at` 舊，下一次 REFETCH 會走進 R-8（`service.py` L414–L426） | 對使用者說「未成功」是假話；成功後一小時（US 24 小時）不抓新日線。**否決** |
| **A′ 拆欄（建議）**：新增 `tail_fetched_at`，只在本次 `end ≥ 舊 covered_end`（或無列、或不相交取代）時推進；`last_fetched_at` 每次完整成功都推進 | 精確修掉 P4，S3-1 冷卻也被 P4 重置的問題一併修掉；R-8/D-8 完全不動；只加欄，遷移便宜 | 多一欄，消費者要分清楚用哪一欄。歷史區間請求的分鐘數可能比實際舊（低估新鮮度，屬保守方向） | 有人用錯欄。以 K-3 加 grep 檢查約束 |
| B coverage 改成區段集合（每序列多列） | 根治 P4；順帶解掉 ADR-0009 已列管的「兩段不相鄰區間來回互相取代、每次整段重抓」 | PK 要變，必須重建表；要做合併/coalesce；判定式改成集合覆蓋；D-7 要挑最後一根所在的區段；跨多區段的請求還得決定取哪個時間（取 min）；diagnose、`delete_by_source` 也要改 | 改動面大，牽動三輪審查過的程式碼。**暫緩**，維持列管（見 Consequences 觸發條件） |
| C `last_fetched_at` 改記「最新交易日那段」的取得時間，由 bar 列 `fetched_at` 推導 | 不用改 schema | 部分抓取（P1）也會寫 bar 列，等於把部分回答當成確認；違反 fetch log 存在的理由（`freshness.py::judge` docstring：bar 列無法表達「問過了、沒有更新」） | 重新引入過度宣稱。**否決執行期使用**，只在遷移回填時當保守上限 |

### 空洞 bug 修法

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **H1 統一 coverage 判定式（建議）**：`covered_start ≤ start` 且 `covered_end ≥ expected_session(...)`，三個消費者共用 | 在單一連續區間的不變式下是精確判定，不靠啟發式；資料庫裡既有的空洞狀態在讀取時自動修正 | 部分抓取（P1）之後的序列會被保守判定（見 Consequences） | 低 |
| H2 `record_fetch` 不相交時拒絕取代（一律保留舊區間） | 不會出現「coverage 是舊歷史、列卻是新的」 | 舊區間若是歷史段，近期請求就永遠拿不到 coverage，每次點都整段重抓；也不能單獨修好 layer 0 | **否決** |
| H2′ 不相交時保留 `covered_end` 較晚者 | 保住每日主路徑的增量抓取 | 回測反覆調參時每次都整段重抓（正是 ADR-0009 Context 當初的痛點）；正確性仍靠 H1 | 只是成本取捨，不修正確性。不採，維持取代 |
| H3 layer 0 檢查快取列的連續性（用 `market_trading_days` 量缺口） | 直接量出洞 | 是啟發式：停牌、未抓到的序列都會誤判；每次請求多一次全市場掃描 | 誤判會擋住服務。不採，但可當測試 oracle |

---

## 附錄 B：架構師評估摘要（tech-architect 原文，逐字轉錄）

結論：兩個問題都屬於 ADR-0009 D-3/D-5 的 fetch log 與 coverage 語意範圍。空洞 bug 不只是實作缺陷：D-3 原文的 layer 0 條件只寫了「`covered_start ≤ start`，再依 `judge()`」，只有 CHECKED_RECENTLY 要求 `covered_end`。也就是說，按 ADR 字面實作就會有這個洞，所以要改的是決策本身。

建議另開 **ADR-0019（proposed）**，部分取代 ADR-0009 D-3/D-5，不在 ADR-0009 原地修訂。理由有三：
- ADR-0009 已經 accepted，ADR-0001 L18 禁止原地改寫。ADR-0009 先前在 accepted 之後原地加了 D-7/D-8，這和 ADR-0001 字面有出入，不宜再沿用。
- 這次要改 schema，而且三個消費者都要動，其中 cache-only 那一個屬於 ADR-0010 D-1 的範圍。這需要獨立的審查與核可紀錄。
- 比照 ADR-0005 被 ADR-0009 部分取代時的作法：ADR-0009 只在檔頭「修訂」清單加一行指標，不改決策內文。

採用：
1. layer 0 和另外兩個 `judge()` 消費者改用同一個 coverage 判定式，要求 `covered_start ≤ start` 且 `covered_end ≥ expected`。
2. fetch log 新增 `tail_fetched_at` 欄（covered_end 最近一次被完整取得的時間），給 `judge()`、徽章分鐘數與 S3-1 使用。`last_fetched_at` 的語意不變，仍是「最後一次任何範圍的完整成功」，只給 R-8/D-8 比對用。
3. 不相交的區間維持「取代」。

否決三種作法：
- 照字面「不推進 `last_fetched_at`」。這會打壞 R-8：回測成功後，下一次請求會被誤判成「最近一次向來源取得資料未成功」，還會擋掉一個冷卻窗的抓取。
- 本輪就把 coverage 改成區段集合。
- 用 bar 列的 `fetched_at` 推導取得時間（只在遷移回填時當保守上限用）。

回覆主會話「回答你的六個問題」中，Decision 區未涵蓋的結論性一句（tech-architect 原文，逐字）：
- 「D-4（live 回應的 `as_of` 改用服務端 `fetched_at`）不論風控選哪一個都建議做。」（出自該 handback 問題 4「L-10c 對齊基準」。）
