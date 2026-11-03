# FD-12 介面契約（tech-architect 2026-11-01；總經理代為落檔）

> 本契約名稱、型別、key 合併後凍結；要改回 tech-architect。
> 契約撰寫時依據 PRD v0.1。之後風控兩輪裁定與 PRD v0.2 已修改多項文案與條件，**以下「總經理裁定補記」優先於本文**。

## 0. 總經理裁定補記（以此為準）

1. **文案一律以 PRD v0.2 文案對照表（45 列，風控已核可）為準**，4.2 的 field 只定名稱、不定文字。重點：
   - `booking_button`＝「到 Google Flights 查看並訂票」；`booking_button_short`＝「查看並訂票」；全站不得單獨出現「訂票」按鈕或欄名（R1）。
   - `booking_hint`＝#44「開啟 Google Flights 該日期組合的結果頁（非直接訂位），請依航班號碼選擇。」；`↗` 配 sr-only「（另開新分頁）」。
   - `best_card_title`＝「已查到最低價」；列表卡片價格標「已查到最低價」；表格欄名「查到價格」；表格逐列可拿掉「查到」前綴，但**每個價格旁都要有可見的查到時間**（R4）。`price_prefix` 依此處理。
   - `WEB_BOOKING_FALLBACK_NOTE`＝「連結只帶航線與日期；人數、艙等、篩選請在 Google 重選」（含「篩選」，R3），每個備援連結旁可見。
   - `return_leg_explain`＝#43「只列去程航班；回程需在 Google Flights 選擇，價格可能因回程不同而改變。」有來回價格的頁面一次可見、不收合；探索日曆上方也要有（R10）。
   - `delta_explain` 可見短句＝「較前一輪＝與上一輪最低價的差額，可能是不同日期。」其餘收進說明（R6）；漲跌徽章對稱、無動畫。
   - `unembedded_form_hint`＝「依實測，此組合常無法自動查價，可能需人工查價。」；健康頁 #35＝「過去 24 小時有 X%（a/b）查詢 Google 未提供結果（可能是非同步載入或封鎖），需人工查價。」（R9）
   - 比價 #30「只依總價由低到高排列，未比較飛行時間與轉機。」、#31「沒有價格的目的地未參與排序，不代表沒有機票或價格較高。」（R11）
   - 探索日曆 #23「每格為該出發日單次查到的最低價；低／中／高只與本次已查到的價格相比。」（多人前加「金額為 A 大 C 小總價」）；詳情價格分布 #15「只含已取樣日期。顏色：綠＝較便宜三分之一、紅＝較貴三分之一。」；`SAMPLED_ONLY_NOTE` 原文不改、緊鄰主卡。
   - 監看層級「已過期」改「已結束」（#40）屬本批範圍。
   - #39「其他日期組合（依價格）」、#41 列表空狀態、#42「近 N 輪未更新」、#45 `/watch` 頁尾句皆依 PRD v0.2。
   - C-105 列的增補字串（`day_offset_sr`、`sr_text`、`local_time_explain`、`source_page_note`、`pax_summary`、`watch_settings_summary`、`date_range_weekday_text`、`web_price_caption`）由 dev-lead 依 PRD 精神起草並列在任務單，risk-gate 時一併逐字比對。
2. **C-40 修訂風控已同意**（條件 (a)～(e) 見任務單），可實作規則切換，仍以獨立 commit 提交。(a) 有價格的頁面與卡片，價格旁摘要列可見「1 位成人・艙等」（列表每卡、詳情主卡、探索與比價頁首）；(b) 多人時每個價格逐一帶人數總價；(e) 多人預算同樣註明。
3. **Telegram（R14、C1）**：價格通知與 `/watch` 來回時在時刻前加「去程」，單程不加；通知行內標「（當地時間，直飛）」；**缺哪一欄就省略該段，不印「—」或 None**（覆蓋第 7 節「未知顯示—」）；新欄全 NULL 時逐字退回原寫法。`/watch` 頁尾改用新常數（#45），`/list`、`/scan` 共用的 `COMMAND_TIME_NOTE` 不動。
4. **列表卡片（R5 與按鈕條件）**：
   - 顯示最低價的查到時間；超過門檻顯示「可能已過期」；有價格且連續 N 輪未內嵌時顯示「近 N 輪未更新」。保留 `no_embedded_streak` 資料，改出 `stale_rounds_label: str | None`；4.3「移除 no_embedded_streak」改為「移除網頁長句，保留輪數供短標籤」。
   - `manual_check`（「需人工查價」）只在 snapshot 無價格時為真。
   - 「查看並訂票」按鈕：href 必須來自卡片顯示的那筆最低價觀測（測試斷言價格、航班、href 同源）；無價格卡片不放，改放「到 Google Flights 人工查價」（第一組日期）；最低價出發日皆已過不放按鈕；退回備援連結時按鈕旁可見備援提示；按鈕不得特殊高亮。
   - 列表頁 #44 提示可見一次；有來回價格時 #43 再一次。
5. **詳情頁設定區連結**維持「到 Google Flights 人工查價」，「帶入第一組日期」可見（R2）。
6. **免責 `DISCLAIMER`**：每個顯示價格的頁面恰好 1 次、不收合、內文字級、緊鄰第一個價格區塊且同首屏（依 PRD v0.2 FR-10）；C-101 的 base.html block 覆寫做法沿用。主卡不得有推薦式強調標記。
7. **來源 #13**：全頁皆 Google Flights 即時價才可在頁面層級說明一次；任一列來源不同（含 fixture）該列顯示來源。
8. **視覺規範 v2 已與 PRD v0.2 對齊**（R12、R13 已處理）；仍有衝突時以 PRD v0.2 為準。網頁缺值顯示「—」。
9. risk-gate 第一次比對（2026-11-03）已修改提示句與新增 #46，最終文字以 PRD 對照表為準（本節第 1 點的 #44 舊句作廢）。
10. 架構師對 PM 的待回覆：FR-1 以推導欄位滿足、轉機點未知時不帶括號，總經理代為確認接受。

---

## 評估摘要

- 採用離散欄位：三張表各加 4 欄 `flight_numbers`、`arrive_time`、`arrive_day_offset`、`route_airports`；migration 0009 純 `ALTER TABLE ADD COLUMN`，不重建、無 FK-off 標記；舊列 NULL 不回填。
- 否決：單一 JSON 欄、segment 子表、`duration_minutes` 改用 info[9]（維持各段飛行分鐘相加；含轉機總時長另案）。
- FD-8 快照路徑完全不動：`_snapshot_keep_select`、`_SNAPSHOT_COLUMNS`、兩個 scope 常數、`SNAPSHOT_OBSERVATIONS_SQL`、`ix_obs_snapshot` diff 為空。列表最低價那班的資料隨外層 `SELECT o.*` 依 rowid 取回；顯示的那班與該格最低價同一列。
- 同價取捨只在「同一次查詢多筆 quote」層新增（最早出發優先）；跨日期組合排序鍵不改。
- 共用顯示：新增 `domain/flight_summary.py` 產出 `FlightSummary`，網頁與 Telegram 都由它組字。
- FD-9 快照退役，錄 `fd12_*` 新基準（獨立 commit）。
- tfs 連結不限定航空公司。抵達日差以各機場當地日期相減，允許 −1，範圍外視為未知。

## 1. 資料模型

### 1.1 `PriceQuote` 新欄位（`domain/models.py`，接在 `depart_time` 之後，全部預設 None）

| 欄位 | 型別 | 例 | 來源 | 驗證（任一不過該欄 None） |
|---|---|---|---|---|
| `flight_numbers` | `str \| None` | `"BR184"`、`"CZ3088,CZ3575"` | 每段 `seg[22][0]`＋`seg[22][1]`，依段序逗號連接 | 代碼 ASCII `[A-Z0-9]{2}`；號碼必須是 `str` 且 ASCII `[0-9]{1,4}`（int 無效）；段數 1～6（`MAX_DETAIL_SEGMENTS = 6`）；全有或全無 |
| `arrive_time` | `str \| None` | `"12:00"` | 最後一段 `seg[10]`，正規化同 `depart_time_text` | HH:MM 合法且 `arrive_day_offset` 可算出，否則兩欄同 None |
| `arrive_day_offset` | `int \| None` | `0`、`1`、`-1` | `date(*last[21]) − date(*first[20])` | 兩日期皆 3 個 int 且真實日期；`first[20]` 必須等於 quote 的 `depart_date`；結果 −1～3；不符與 `arrive_time` 同 None |
| `route_airports` | `str \| None` | `"TPE,NRT"`、`"TPE,SZX,SHA"` | `seg[0][3]` ＋ 每段 `seg[i][6]` | 代碼 ASCII `[A-Z]{3}`；`seg[i][6] == seg[i+1][3]`（換機場視為未知）；代碼數＝段數＋1 |

既有欄位語意不變：`carrier` 取 info[1]；`stops`＝段數−1；`duration_minutes`＝各段 seg[11] 相加；`depart_time`＝seg[0][8]。時刻與日期皆當地值，不做時區換算；抵達日＝`depart_date + arrive_day_offset`。

新增 domain 函式（同檔）：

```python
def quote_rank_key(q: PriceQuote) -> tuple[int, int, str, int, str]
# (amount_minor, 0 if depart_time else 1, depart_time or "", stops if stops is not None else 99, flight_numbers or "~")
```

### 1.2 解析與推導分工

- `sources/google_payload.py`（仍只用 stdlib）：`_record` 在每個 `flights[i]` dict 加 7 個 key：`code`、`number`、`from`、`to`、`arrive_time`、`depart_date`、`arrive_date`（正規化後 `str | None`；日期 ISO，非真實日期 None）。`ParseStats`、`classify_itinerary`、`itinerary_key` diff 為空。
- `sources/_records.py`：`quotes_from_records` 從 `flights[*]` 推導 1.1 的 4 欄並驗證；缺 key 當 None；推導失敗**不得**拋 `RecordFormatError`，不得改變價格、stops、carrier、depart_time、duration 或查價狀態。

### 1.3 傳遞鏈

- `storage/repository.py`：`ObservationRecord`、`ExplorationCellRecord`、`ComparisonCellRecord`、`CellUpdate` 末尾加 4 欄預設 None；`_observation`、`_cell`、`_comparison_cell` 讀取；`insert_observation`、`record_exploration_cell`、`record_comparison_cell` 寫入。
- `services/exploration.py::cell_update`：有價格分支帶 4 欄；無價格維持 None（比價共用）。
- `domain/rules.py::Candidate` 末尾加 `stops`、`depart_time`、`duration_minutes`、`flight_numbers`、`arrive_time`、`arrive_day_offset`、`route_airports`（預設 None）；`services/scan.py` 從 cheapest quote 填入。
- `domain/messages.py::CommandPriceRow` 末尾加 `depart_time`、`duration_minutes`、`flight_numbers`、`arrive_time`、`arrive_day_offset`、`route_airports`；`services/commands.py::top_prices` 從 obs 填入。
- dedupe key（`price_item_key`、`price_message_key`）diff 為空；`notification_item` 不加欄。

## 2. Migration 0009 與快照、效能

### 2.1 `storage/migrations/0009_flight_details.sql`

- 首行不加 FK-off 標記；只有 12 條 `ALTER TABLE <t> ADD COLUMN`，`<t>` 依序 `price_observation`、`exploration_cell`、`comparison_cell`，每表欄位順序：
  - `flight_numbers TEXT CHECK (flight_numbers IS NULL OR (length(flight_numbers) BETWEEN 3 AND 41 AND flight_numbers NOT GLOB '*[^A-Z0-9,]*' AND flight_numbers NOT GLOB ',*' AND flight_numbers NOT GLOB '*,' AND flight_numbers NOT GLOB '*,,*'))`
  - `arrive_time TEXT CHECK (...)`：逐字照抄 0003 `depart_time` CHECK，只換欄名。
  - `arrive_day_offset INTEGER CHECK ((arrive_day_offset IS NULL) = (arrive_time IS NULL) AND (arrive_day_offset IS NULL OR (typeof(arrive_day_offset) = 'integer' AND arrive_day_offset BETWEEN -1 AND 3)))`
  - `route_airports TEXT CHECK (route_airports IS NULL OR (length(route_airports) BETWEEN 7 AND 27 AND length(route_airports) % 4 = 3 AND route_airports NOT GLOB '*[^A-Z,]*' AND substr(route_airports, 4, 1) = ','))`
- 若 SQLite 拒絕跨欄 CHECK：只留範圍檢查，配對規則改 Python 驗證並補測試；回報 architect、記任務單，不得刪其他 CHECK。
- 不建索引，不 CREATE、DROP、RENAME 表；`pre-v9` 備份由 `db.py` 既有機制產生，`db.py` diff 為空；cell 新欄只在 ok 時有值，由 Python 保證並測試。

### 2.2 快照路徑

- diff 必須為空：`repository.py` 的 `_snapshot_keep_select`、`_SNAPSHOT_COLUMNS`、`_SNAPSHOT_SCOPE_WATCH`、`_SNAPSHOT_SCOPE_RETENTION`、`SNAPSHOT_OBSERVATIONS_SQL`、`LIST_WATCHES_SQL`；`0006_snapshot_index.sql`、`services/price_snapshot.py`、`services/retention.py`；`tests/test_snapshot_read.py` 與 C-57、C-58 既有測試（含 EXPLAIN 斷言）不修改且全綠。
- 列表 `snapshot.cheapest` 即 `ObservationRecord`，直接帶 4 欄，不新增 SQL；C-55「20 監看＝1＋20 次 SQL」照舊。
- 詳情主卡差額用 `Snapshot.build(current_obs, ...)` 在 Python 算。

### 2.3 效能門檻

暖機 1 次後取 10 次中位數，原始輸出記任務單；steady180 複本遷移到 v9。
- `list_page` steady180 ≤ **240 ms**（184.8 × 1.3），用真實 `GoogleFlightsLinkBuilder`。
- 單一監看 `snapshot_observations_for_watch` <10 ms；一輪掃描寫入（12 組）≤146 ms；FD-6 基準庫 `list_page` <100 ms；詳情頁與 migration 耗時只記錄。
- 超標回報 tech-architect，不得自行快取連結、改 snapshot SQL、加索引。

## 3. 同價多班取捨

- 層級 A（新）：`services/source_query.py` 兩處 `min(...)`（幣別相符與不符備援）改 `key=quote_rank_key`。順序：價低 → 有出發時刻 → 出發早 → 轉機少 → 航班號碼字典序小；全同取 payload 順序第一筆。
- 層級 B（不改）：`cheapest_pairs`、`snapshot_min` 用 (amount, depart, return or depart)；探索前 5 (amount, depart)；`comparison_order` (amount, position)。
- 保證：航班 4 欄與 `amount_minor` 同列、同一 `PriceQuote`。測試斷言任一頁顯示的 `flight` 由同一列記錄產生。

## 4. View model 介面與檔案歸屬

### 4.1 `domain/flight_summary.py`（新檔；只 import stdlib 與 domain）

```python
class FlightFacts(Protocol):          # read-only properties
    carrier: str | None; stops: int | None; depart_time: str | None; duration_minutes: int | None
    flight_numbers: str | None; arrive_time: str | None; arrive_day_offset: int | None; route_airports: str | None

@dataclass(frozen=True)
class FlightSummary:
    leg_label: str | None        # "去程" for round_trip, None for one_way
    is_outbound_only: bool       # leg_label is not None
    airline: str                 # carrier split on "、", de-duplicated in order; else names from domain.airlines by code; else "—"
    flight_numbers: str          # "BR 184" / "BR 198 → JL 99" / "—"
    depart_time: str             # "07:55" / "—"
    arrive_time: str             # "12:00" / "—"
    day_offset: str | None       # "+1" / "−1" (U+2212) / None when 0 or unknown
    day_offset_sr: str | None    # screen-reader suffix, e.g. "，隔天抵達"
    times: str                   # "07:55 → 12:00" / "23:55 → 03:30+1" / "07:55 → —"
    times_compact: str           # "07:55→12:00" (Telegram /watch)
    depart_airport: str | None
    arrive_airport: str | None
    stops: str                   # "直飛" / "轉機 1 次（HKG）" / "轉機 2 次（HKG、NRT）" / "轉機 1 次" / "—"
    stops_short: str | None      # "直飛" / "轉機 1 次" / None
    duration: str | None         # flight_duration_label(duration_minutes)
    detailed: bool               # any of the four FD-12 fields is not None
    sr_text: str                 # "去程，長榮航空 BR 184，07:55 出發，12:00 抵達，直飛"

def flight_summary(facts: FlightFacts, *, trip_type: TripType) -> FlightSummary
def format_flight_numbers(canonical: str | None) -> str | None
def day_offset_label(offset: int | None) -> str | None
def layover_codes(route_airports: str | None) -> tuple[str, ...] | None
```

規則：網頁與 Telegram 只能透過此模組組航班字串，`src/` 其他地方不得拼 `" → "` 形式航班號碼；舊資料 airline 用 carrier、depart_time 用既有值、其餘「—」、`detailed=False`；輸出不含 `None`；轉機機場只顯示代碼。Telegram 缺欄省略規則見第 0 節第 3 點（由 Telegram 組字函式處理，不改 `FlightSummary` 欄位語意）。

### 4.2 共用頁面字串：`base_context()` 新增 key `ui`

`domain/messages.py` 定義 `UiTexts` frozen dataclass 與唯一實例 `WEB_TEXTS`；樣板只用 `ui.<field>`，不寫死。field（文字以第 0 節與 PRD v0.2 為準）：
`help_summary`、`tech_details_summary`、`manual_check`、`manual_check_explain`、`delta_explain`、`booking_button`、`booking_button_short`、`booking_hint`、`manual_link`、`best_card_title`、`price_prefix`、`return_leg_explain`、`local_time_explain`、`not_scanned`、`detail_no_price`／`detail_no_price_explain`、`distribution_legend`、`limit_reached_note`、`global_limit_note`、`query_failed`、`old_revision_note`、`kind_cached`／`data_time_unknown`／`stale_badge`、`unembedded_form_hint`；另依第 0 節新增 `price_column`（查到價格）、`other_pairs_title`（#39）、`watch_ended`（#40）、`stale_rounds`（#42 句型）、`settings_manual_link`（R2）。

其他新常數與函式（`domain/messages.py` 或 `trip_labels.py`，全部納入 `all_static_texts()`）：
- `WEB_BOOKING_FALLBACK_NOTE`（網頁專用；原 `BOOKING_FALLBACK_NOTE` 不改，留 Telegram）。
- `web_price_note(adults, children) -> str | None`：總人數 1 回 None，否則 `total_price_short`。
- `web_price_caption(trip_type, adults, children) -> str | None`：來回 1 人「來回總價」；來回多人「來回・2 大 1 小總價」；單程 1 人 None；單程多人「2 大 1 小總價」。
- `pax_summary(adults, children, cabin)`：「1 位成人・經濟艙」。
- `top_explain(stale_hours)`、`source_page_note(sources)`、`exploration_calendar_note(adults, children)`、`health_no_embedded_note(pct, count, total)`、`date_range_weekday_text(depart, ret)`（「12/10（週四）–12/15（週二）」）、`watch_settings_summary(...)`（「TPE → NRT・來回・{dates_text}・預算 {budget}」）。
- 改值的既有常數：`EXPLORATION_REFERENCE_NOTE`、`EXPLORATION_PREFILL_OK` 與預填提示、探索與比價進度句、`EXPLORATION_CELL_LABELS["no_embedded_results"]`、`COMPARISON_ROW_LABELS["no_embedded_results"]`、`COMPARISON_REFERENCE_NOTE`、`COMPARISON_ORDER_NOTE`、`COMPARISON_NO_PRICE_NOTE`、比價表 caption。
- 退役：`NO_EMBEDDED_LABEL`（views.py）、`no_embedded_streak_label` 的網頁長句用途（輪數改出短標籤）。

### 4.3 各頁 view model 新增或變更的 key（原則加法）

**列表 `watches[i]`**：`flight: FlightSummary | None`；`booking_url`、`booking_note`（規則見第 0 節第 4 點）；`price_caption`、`pax_note`（web 規則）、`pax_summary`；`cheapest_fetched_label`（查到時間）、`stale: bool`、`stale_rounds_label: str | None`；`dates_weekday_label`；`filters_label`（只在 `has_filters`）；`manual_check: bool`（只在無價格）；`ended: bool`（「已結束」）。移除：`no_embedded_note`、頂層長句 `no_embedded_streak_label`。

**詳情**：`top[*]`、`recent_prices[*]` 加 `flight: FlightSummary`、`kind_badge: str | None`；`old_prices[*].flight` 一律 None；`best`＝`top[0]`＝`Snapshot.build(current_obs).cheapest` 那列；`best_delta`；`watch.price_caption`、`watch.pax_note`、`watch.pax_summary`、`watch.settings_summary`；`source_note`、`manual_check`；`last_run.note`、`last_run.pairs[*].note`、`runs[*].note` 中文標籤。移除：`last_run.error`、`last_run.pairs[*].error`、`last_run.pairs[*].reason`、`runs[*].error`、`last_run.no_embedded_note`。

**探索結果**：日曆格與 `top5[*]` 加 `flight: FlightSummary | None`、`manual_check: bool`（no_data 且 no_embedded）；`exploration.price_caption`、`pax_note`；頁面層級 `reference_note`、`disclaimer`（只放 `DISCLAIMER`，拆開既有串接）、`calendar_note`；recent 的 `cheapest_label` 用 web 規則。

**比價結果**：`rows[*]` 加 `flight`、`manual_check`；`pax_note` 與 recent `cheapest_label` 用 web 規則（比價固定 1 人）；`comparison.price_caption`。

**設定與健康**：`health_rows[*].last_error` 保留原文，只能出現在「技術細節」`<details>` 內；`no_embedded_summary.note`＝#35 組好字串。

### 4.4 診斷不外露（FR-12，`services/views.py`）

- `pair_note(entry) -> str | None`：依序取 `SKIP_REASON_LABELS`、no_embedded（`ui.manual_check`）、`parse_notes`，以「；」連接；有錯誤但無對照時回「查詢失敗」；絕不回 adapter 原文。
- `run_note(run) -> str | None`：由 `query_results` 結構化 status 與 reason 推導，取不重複 `QUERY_STATUS_LABELS`、`SKIP_REASON_LABELS`；有 `error_summary` 但無標籤回「查詢失敗」；不解析 `error_summary` 字串。
- `known_error_label(text, known)`：探索與比價 `error_summary` 屬系統常數集合（`*_SCHEDULER_OFF`、中斷摘要）原樣顯示，否則「查詢失敗」。

### 4.5 檔案歸屬（不重疊）

| 角色 | 檔案 |
|---|---|
| dev-lead | `sources/google_payload.py`、`sources/_records.py`、`domain/models.py`、`domain/flight_summary.py`（新）、`domain/rules.py`、`domain/messages.py`、`domain/trip_labels.py`、`storage/repository.py`、`storage/migrations/0009_flight_details.sql`、`services/source_query.py`、`services/scan.py`、`services/exploration.py`、`services/views.py`、`services/exploration_views.py`、`services/comparison_views.py`、`services/commands.py`；`web/server.py`（預期 0 diff）；`tests/conftest.py`（ScriptedSource opt-in `flight: dict \| None = None`）；`tests/test_fd12_*.py`（parse、migration、flight_summary、views、telegram）；所有既有測試檔修改（含 `tests/test_domain.py::wording_surfaces` 加入 `flight_summary.py`）；快照重錄 |
| frontend-engineer | `web/templates/*.html`、`web/static/app.css`、`web/static/app.js`（非必要不動）、`tests/test_fd12_pages.py`（渲染後 HTML 結構斷言） |

協作：既有測試檔只由 dev-lead 改；frontend 需要改既有斷言時，把「檔名::測試名、舊期望、新期望、理由」交 dev-lead 列任務單 AC-F4。`test_fd12_pages.py` 依賴 dev-lead 先合入 conftest opt-in 與 4.1～4.3 的 key。

### 4.6 樣板約束（frontend）

- 只用 `flight.*` 與 `ui.*` 顯示航班與新文案，不在樣板拼航班號碼、時刻或標點。
- 未知欄位 view model 已給「—」，照樣顯示。
- 不得出現任何回程航班號碼或回程時刻。
- 不用 inline `style=`、不新增外部資源、`app.js` 不得出現 `innerHTML`；既有 `data-action`、`data-watch-id`、`data-unembedded-hint` 掛鉤保留。

## 5. C-40 修訂條文（風控已同意，條件見任務單）

> **C-40（FD-12 修訂）**：`pax_label`、`pax_full_label`、`cabin_label`、`total_price_note`、`total_price_short`、`web_price_note`、`web_price_caption` 在 domain、無 I/O。
> 推播、每日與手動摘要、`/list`、`/watch`、`/scan` 回覆、通知紀錄頁：價格旁一律帶 `total_price_note`（含「（1 人總價）」），規則與既有斷言不變。
> 網頁列表、詳情、探索（含近期列表）、比價（含近期列表）：總人數 >1 時每個價格旁帶 `web_price_note`；總人數＝1 時價格旁不帶註記，改在頁首或主卡摘要列（列表每張卡）以 `pax_summary` 可見顯示「1 位成人・艙等」，不可收合。
> 網頁是否帶註記只由 `web_price_note` 判斷；`views.py` 不得寫死「經濟艙」或 `adults: 1`；新字串納入 `all_static_texts()` 並通過 BANNED_PHRASES。
> 測試：1 人摘要列斷言、多人逐價格斷言兩組。

以獨立 commit 切換規則，AC-F4 列出改到的既有斷言。

## 6. FD-9 快照裁定

退役 `fd9_*`，錄 `fd12_*` 新基準。
1. `git mv tests/test_fd10_snapshots.py tests/test_fd12_snapshots.py`；錄製開關 `FD12_RECORD_SNAPSHOTS=1`；`git rm` 三份 `tests/snapshots/fd9_*.html`。
2. `build_fixture`、`render` 逐字不變（舊資料降級畫面）；新增第 4 份 `fd12_exploration_flights.html`（opt-in 航班：直飛、+1、一次轉機）。
3. 移除 `without_top_scope_note` 剝除步驟；`explore.html` 比對範圍維持表單外加預估文字。
4. 錄製輪寫完檔後 `pytest.fail("recorded; rerun without FD12_RECORD_SNAPSHOTS")`。
5. 寫檔前防呆：`DISCLAIMER` 恰 1 次且不在 `<details>`；不含 `None`、「未在頁面內嵌」、「查票」、`no result section`；外部 href 只有 Google Flights、`target="_blank"`、`rel` 含 `noopener noreferrer`。
6. 錄製條件：其他驗收全過、樣板定稿；獨立 commit `test: 重錄 FD-12 探索頁 HTML 基準快照`（只含 test 與 snapshot 檔）；review 附新舊 diff 與實機截圖。

## 7. Telegram 兩處改動

1. **`price_alert_message`**：簽章不變；原「`   航空公司：…`」行改由 `flight_alert_line(cand: FlightFacts, trip_type: str) -> str` 產生，仍 1 行。detailed 時「`   航班：{airline} {flight_numbers}｜{去程 }{depart} → {arrive}{day_offset}（當地時間，{stops_short}）`」，缺欄省略該段（第 0 節第 3 點）；非 detailed 逐字輸出原「`   航空公司：{carrier or '未提供'}`」。
2. **`command_watch_message`**：每組原 `{row.carrier or '航空公司未提供'}` 改由 `flight_command_text(row, trip_type) -> str`；detailed 時「`{airline} {flight_numbers} {去程 }{times_compact}`」，缺欄省略；非 detailed 逐字照舊。頁尾改 #45 新常數（只用於 `/watch`）。其餘欄位、「查票連結：」標籤、`fit_reply`、`COMMAND_REPLY_MAX_CHARS` 不變。測試：3 組最長情境（6 段航班號碼、最長航空名、備援提示）全部顯示、各帶總價註記、含 `DISCLAIMER`、≤3800 字。
- `/list`、摘要、`/scan`、`/status`、ops 告警組字函式 diff 為空；`BOOKING_FALLBACK_NOTE`、`DISCLAIMER`、`SAMPLED_ONLY_NOTE` 文字不改。

## 8. ADR-0002 FD-12 增補（草稿，完成後落檔）

**範圍**：解析並保存最低價那班的航班號碼、抵達時刻與日差、航線機場串；網頁四頁與 Telegram 兩處顯示航班；網頁文案精簡並卡片化。不新增執行期依賴、不改 import 方向表；新增 migration 0009（純 ADD COLUMN）與 `domain/flight_summary.py`。

**修訂既有條文**：C-40 依第 5 節；FD-5 Decision 4「抵達時刻本批不存」結案；FD-5 9a 網頁說明改「需人工查價」加收合說明（Telegram 不變）；C-76、C-78 F3「與 FD-9 逐字相同」由 C-104 取代；C-83「migrations 只有 0001～0008」限 FD-11 批次。

**方案比較**：A 三表各加 4 離散欄（採用：CHECK 可約束、與最低價同列、不碰索引與快照 SQL、遷移快；缺點：不存中間段時刻與機型）；B 單一 `segments_json`（否決：只能 json_valid、各頁解讀易漂移）；C segment 子表（否決：join、cascade、破壞 C-55 SQL 次數）；D `duration_minutes` 改 info[9]（否決：新舊語意混用，另案）。

**Consequences**：好處是看得到哪班、幾點到、哪裡轉機；舊列自然降級；快照、索引、清除語意零變動；同價取捨可重現；網頁與 Telegram 共用組字。代價是 payload 位置逆向取得，Google 改版時新欄靜默降為「—」（價格不受影響）；中間段時刻與機型不存；同價選中班次可能與 v0.1.0 不同；列表每卡多 1 條 tfs；網頁與 Telegram 人數註記規則分岔；HTML 快照整批重錄。約束：顯示中間段、機型、回程班次或改 info[9] 要重評；航班欄位進 `_SNAPSHOT_COLUMNS` 或索引要回 FD-8 重評；tfs 加航空限定要回 FD-5 Decision 7 重評（本節否決）。

**新增約束**
- **C-94 解析與推導**：`google_payload.py` 只用 stdlib；`ParseStats`、`classify_itinerary`、`itinerary_key` diff 空；4 欄只在 `_records.quotes_from_records` 推導。BR184 fixture 斷言 `flight_numbers=="BR184"`、`arrive_time=="12:00"`、`arrive_day_offset==0`、`route_airports=="TPE,NRT"`、`depart_time=="07:55"`；SHA fixture 最低價 `route_airports=="TPE,SZX,SHA"`、`flight_numbers=="CZ3088,CZ3575"`，C-39 數字（9／7／2／463300）不變。異常案例：seg[22] None、非 list、號碼 "18A"、號碼 int 184、代碼 "br"、7 段、缺 [21]、[21]=(2026,2,30)、first[20]≠查詢日、日差 4、日差 −1、轉機換機場、抵達 [24,0]；價格等既有欄位與 ParseStats 不變，只有對應欄位 None。合成 payload：+1、一次轉機、BR＋JL、seg[22] 缺漏、抵達日缺漏。測試交叉檢查兩份 fixture 推出的抵達時刻等於 info[8]。`duration_minutes` 推導 diff 空。
- **C-95 Migration 0009**：只含 12 條 ADD COLUMN；v8 含資料 DB（三表各 ≥2 列、cell ok 與 no_data）遷移後筆數不變、舊欄相等、新欄 NULL；`pre-v9` 備份可開啟、新 DB 不產生備份；integrity ok、foreign_key_check 空、版本 9；0001～0008 diff 空。CHECK 拒絕 `'br184'`、`'BR184,'`、`',BR184'`、`'BR184,,JL99'`、`'BR 184'`、`arrive_time='7:55'`、offset 4／−2／1.5、arrive_time 與 offset 一有一無、`'TPE'`、`'TPE,NR'`、`'tpe,nrt'`；接受 `'BR184'`、`'CZ3088,CZ3575'`、offset −1、`'TPE,SZX,SHA'`。
- **C-96 快照路徑與效能**：2.2 符號與檔案 diff 空；C-55～C-58 既有測試不改全綠；`list_page` SQL 次數 1＋N；2.3 門檻逐項量測記任務單，未達標不得 done。
- **C-97 同價取捨**：`quote_rank_key` 只定義一次、`source_query.py` 兩處 min 使用；測試同價 08:10 對 07:55 選 07:55、同時刻直飛優先、有時刻優先、不同價選低價、全同取第一筆；`price_snapshot.py` diff 空；頁面 flight 與價格同源；同價改變的既有測試列 AC-F4。
- **C-98 共用顯示**：`flight_summary.py` 只 import stdlib 與 domain；`" → "` 航班號碼字串只在此模組產生（grep 測試）；逐欄單元測試（FR-2 七個 Given、舊資料、同航空兩段只列一次、有抵達無日差顯示「—」、「−1」為 U+2212）；輸出無 None；列入 `wording_surfaces`。
- **C-99 view model 與診斷**：4.3 key 與型別各有斷言、移除的 key 不存在；遞迴走訪四頁 view model 不含 adapter 原文、例外類別名、`no result section`、`Traceback`、`Error:`；設定頁原文只在 `<details>`；未對照英文錯誤顯示「查詢失敗」。
- **C-100 人數註記**：依第 5 節；網頁 1 人四頁價格旁無「1 人總價」、頁首、主卡與每張列表卡有「1 位成人」；2 大 1 小列表與詳情逐價格有「2 大 1 小總價」；Telegram 通知與摘要 1 人仍「（1 人總價）」；通知紀錄頁不變。
- **C-101 誠實揭露與收合**：列表、詳情、探索結果、比價結果、探索表單、比價表單完整 `DISCLAIMER` 整份 HTML 恰 1 次、不在 `<details>`；`base.html` 頁尾免責放可覆寫 block；詳情 `SAMPLED_ONLY_NOTE` 恰 1 次可見；FR-13 必須可見項目不在 `<details>`；其他說明用 `<details>`、無 JS 可展開；探索 `disclaimer` 只等於 `DISCLAIMER`。
- **C-102 訂票連結**：每個顯示航班的位置有連結，href 等於 tfs（或備援並附 `WEB_BOOKING_FALLBACK_NOTE`），`target="_blank"`、`rel` 含 `noopener noreferrer`；外部網域只有 Google Flights；tfs 不加航空限定、C-42 golden 不變；網頁不再出現「查票」與單獨「訂票」；Telegram「查票連結：」不變。
- **C-103 Telegram**：依第 7 節與第 0 節第 3 點；`price_alert_message` 行數不變；非 detailed 逐字相同；`/watch` 最長情境 ≤3800 字；其他組字函式既有測試不改；新字串通過 BANNED_PHRASES；實機由 CEO 或總經理手動驗收。
- **C-104 HTML 快照**：依第 6 節。
- **C-105 文案與風控閘門**：文案依 PRD v0.2 對照表（風控已核可）；增補字串列任務單；新字串都在 `messages.py`、`trip_labels.py`、`flight_summary.py` 並列入 `all_static_texts()`；樣板不寫死；risk-gate 實際渲染文案與對照表差異為 0。
- **C-106 模組邊界與既有期望值**：`test_architecture.py` ALLOWED 不變；`services/` 不新增對 `sources`、`scheduler`、`web` 的 import；`retention.py`、`price_snapshot.py`、`db.py` diff 空；不新增依賴；既有 1442 項只能修改直接斷言以下者並列 AC-F4：網頁「（1 人總價）」、「查票」、「未內嵌」與 `NO_EMBEDDED_LABEL`、逐列「Google Flights（即時價）」、移除的 view model key、快照、同價取捨改變的 carrier 與 depart_time、schema 版本 8→9；pytest 連跑 3 次、ruff、format、mypy 通過。
- **C-107 UI e2e**：1120、768、360 px 無橫向捲動（表格捲動區除外）；主卡與「到 Google Flights 查看並訂票」在 1366×768 與 390×844 首屏可點；Tab 可走過所有按鈕與 summary；新舊資料混合不錯位、無 None；來回監看無回程班次；深淺色對比腳本重算；CSP 無違規；實際點開 3 條訂票連結（單程、來回、轉機）確認結果頁可依航班號碼找到該班。

## 9. 風險、不做、拆批

風險：payload 改版新欄靜默降為「—」（C-94 契約測試緩解；健康頁「有價格無航班號碼比例」另案）；同價取捨改變（預期，列 AC-F4）；列表效能（240 ms 門檻）；去重鍵不含航班號碼，共掛班號可能被合併成一筆（可接受，實測常見再評估）。

不做：回程班次、逐航班購買網址（不得捏造航空或旅行社連結）、機型、中間段時刻、含轉機總時長、舊資料回填、tfs 加航空限定、新資料源、多人優化、Telegram 其他推播改版、狀態 JSON API 加欄位。

拆批：B1 解析、migration、取捨、傳遞鏈；B2 `flight_summary`、`UiTexts`、新常數；B3 四頁 view model 與 FR-12（dev-lead）和 B4 樣板與 CSS（frontend）並行；B5 Telegram；C-40 切換（獨立 commit）；B6 快照重錄；之後 review（qa-reviewer 加 Codex）、risk-gate、e2e。
