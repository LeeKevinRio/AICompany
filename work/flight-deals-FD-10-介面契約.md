# FD-10 介面契約（tech-architect 2026-10-31；dev-lead 與 frontend-engineer 並行依據）

依據：ADR-0002 FD-10 增補（Decision 1～10、C-71～C-82）與 `work/flight-deals-FD-10-PRD.md`。本檔只放兩邊要對齊的介面；名稱、型別、key 一經合併即凍結，要改請回 tech-architect。

## 1. 星期編碼（全系統唯一約定）
- 星期整數 `0..6`，0＝週一…6＝週日，等於 Python `date.weekday()`、DB bitmask 的 bit 位置、`month_weeks` 的欄位索引。
- 全選＝`(0,1,2,3,4,5,6)`＝mask `127`。DB、domain、JSON 都沒有「未設定」：缺 key 一律正規化為全選（修改監看時為「沿用既有值」）。
- 欄位名稱統一 `depart_weekdays`（DB 欄位、domain 欄位、JSON key、表單 checkbox name）。

## 2. Domain

### 2.1 `domain/weekdays.py`（新檔，只用 stdlib）
```python
ALL_WEEKDAYS: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
ALL_WEEKDAYS_MASK: int = 127
def normalize_weekdays(values: Iterable[int]) -> tuple[int, ...]   # sorted, unique; ValueError if any not in 0..6 or empty
def weekdays_to_mask(weekdays: Iterable[int]) -> int               # sum(1 << d)
def weekdays_from_mask(mask: int) -> tuple[int, ...]               # ValueError unless 1 <= mask <= 127
def is_all_weekdays(weekdays: Iterable[int]) -> bool
```

### 2.2 `domain/models.py`
```python
@dataclass(frozen=True)
class WatchSpec:
    ...  # existing fields unchanged, then:
    depart_weekdays: tuple[int, ...] = ALL_WEEKDAYS
    # search_shape(): append tuple(sorted(set(self.depart_weekdays))) as the LAST element

@dataclass(frozen=True)
class ExplorationSpec:
    ...  # existing fields unchanged; year/month now mean the START month, then:
    end_year: int | None = None      # None (with end_month None) = single month
    end_month: int | None = None
    depart_weekdays: tuple[int, ...] = ALL_WEEKDAYS
    # properties
    month_text -> str                # unchanged: start "YYYY-MM"
    end -> tuple[int, int]           # (end_year, end_month) or (year, month)
    month_to_text -> str | None      # None when single month
    months -> list[tuple[int, int]]  # inclusive start..end
    def condition_key(self) -> str   # v2, see 2.6
```
`FlightSearch`、`search_for`、`cache_key()`、`ComparisonSpec`、`ComparisonTarget` 不變。

### 2.3 `domain/dates.py`
```python
def expand_pairs(spec: WatchSpec, today: date) -> list[DatePair]          # signature unchanged; fixed or all-weekdays = FD-9 code path
def first_pair(spec: WatchSpec, today: date) -> DatePair | None           # weekday-aware, <= 7 candidate days
def is_expired(spec: WatchSpec, today: date) -> bool                      # unchanged body (uses first_pair)
def weekday_filter_leaves_nothing(spec: WatchSpec, today: date) -> bool   # filtered first_pair None but all-weekdays first_pair not None
def sample_pairs(...)                                                     # unchanged
def range_months(spec: ExplorationSpec) -> list[tuple[int, int]]
def range_pairs(spec: ExplorationSpec, today: date) -> list[DatePair]     # no truncation
def month_pairs(spec: ExplorationSpec, today: date) -> list[DatePair]     # legacy: range_pairs(...)[:MAX_MONTH_CELLS]; services must not call
def month_weekday_counts(year: int, month: int, today: date) -> tuple[int, int, int, int, int, int, int]
def month_weeks(year: int, month: int) -> list[list[date | None]]         # unchanged
MAX_MONTH_CELLS = 31                                                      # unchanged
```

### 2.4 `domain/validation.py`
- 新常數 `EXPLORATION_MAX_SPAN_MONTHS = 3`。
- `validate_watch_input(raw, today, existing=None)` 簽章不變：解析 `depart_weekdays`（只在 `date_mode == "flexible"`）；固定日期一律輸出 `ALL_WEEKDAYS`。
- `validate_exploration(raw, today)` 簽章不變：解析 `month_to` 與 `depart_weekdays`；單月時 `end_year`／`end_month` 為 None。
- 不 import `domain.dates`。錯誤文案從 `domain.messages` import。

### 2.5 `domain/trip_labels.py`／`domain/messages.py`
```python
# trip_labels.py
def depart_weekdays_label(weekdays: Iterable[int]) -> str | None   # None when all; "週五、週六出發"; names from timeutil.WEEKDAY_LABELS

# messages.py (new)
WEEKDAYS_REQUIRED = "請至少選一個出發星期"
WEEKDAYS_INVALID = "出發星期格式不正確，請從選項勾選"
WEEKDAYS_NO_MATCH_WINDOW = "所選日期區間內沒有符合出發星期的日子"
WEEKDAYS_NO_MATCH_MONTHS = "所選月份內沒有符合出發星期的日子"
EXPLORATION_TOO_MANY_CELLS = "請縮小月份範圍或減少星期"
MONTH_TO_BEFORE = "結束月份不可早於起始月份"
MONTH_SPAN_TOO_LONG = "月份範圍最多連續 3 個月"            # built from EXPLORATION_MAX_SPAN_MONTHS
EXPLORATION_CELL_LABELS["weekday_filtered"] = "未查（星期篩選）"
EXPLORATION_STALE_FALLBACK = "這是較早前查到的價格，可能已變動。"   # moved verbatim from exploration.html
EXPLORATION_RANGE_WATCH_BUTTON = "以所選月份建立彈性窗監看"       # multi-month only; single month keeps the existing button text
COMMAND_COMPARISON_DEFERRED = "比價進行中，掃描順延"
COMMAND_SCAN_COMPARISON_DEFERRED = "比價進行中，掃描順延，將於比價結束後執行。"
MAINTENANCE_TABLE_LABELS += {"comparison": "比價", "comparison_cell": "比價明細"}
def month_range_label(year: int, month: int, end_year: int, end_month: int) -> str  # equal -> month_label; else "A～B"
def exploration_quota_message(hourly_left, needed, reserve, *, months: int = 1) -> str  # months > 1 replaces "整月" with "所選月份"
WEEKDAY_OPTION_LABELS: tuple[str, ...]  # ("週一", ..., "週日") built from timeutil.WEEKDAY_LABELS

@dataclass(frozen=True)
class DigestRow: ...; weekdays_label: str | None = None          # appended after the cabin part when not None
@dataclass(frozen=True)
class CommandExplorationStatus: ...; end_year: int | None = None; end_month: int | None = None
@dataclass(frozen=True)
class CommandComparisonStatus: done: int; total: int
@dataclass(frozen=True)
class CommandStatus: ...; comparison: CommandComparisonStatus | None = None
```
- `/status`：`comparison` 不為 None 時，在「探索：…」行之後加 `f"比價：{COMMAND_COMPARISON_DEFERRED}（已查 {done}／共 {total}）"`。
- 探索頁暫定文案（送風控定稿）：h1「探索出發日價格」；說明句「對所選月份（最多連續 3 個月）內符合出發星期的每個出發日各查一次，最多 31 次查詢；完成後以價格日曆與最低價前 5 個日期呈現。」
- 字串最終版以 risk-compliance-officer 審查結果為準。改字面不改 key。

### 2.6 `condition_key` v2 格式
`v2|{origin}|{destination}|{trip_type}|{YYYY-MM start}|{YYYY-MM end}|{weekday mask}|{trip_days or -}|{max_stops or -}|{adults}|{children}|{cabin}|{airlines sorted or -}|{dep_hour_from or -}|{dep_hour_to or -}|{currency}`
例：`v2|TPE|KIX|round_trip|2026-12|2027-02|48|4|-|1|0|economy|-|-|-|TWD`（48＝週五＋週六）。單月時結束月寫與起始月相同的值。

## 3. Storage

### 3.1 Migration `0008_depart_weekdays_and_exploration_range.sql`
內容依 ADR FD-10 Decision 1。新欄位：`watch.depart_weekdays INTEGER NOT NULL DEFAULT 127`；`exploration.month_to TEXT NULL`（NULL＝單月；等於 `month` 時不得寫入）；`exploration.depart_weekdays INTEGER NOT NULL DEFAULT 127`。

### 3.2 `storage/repository.py`
- `_spec_values(spec)` 新增 `"depart_weekdays": weekdays_to_mask(spec.depart_weekdays)`；`_watch(row)` 讀 `weekdays_from_mask(row["depart_weekdays"])`。所有讀 watch 的 SQL 仍用 `w.*`／`*`。
- `insert_exploration(spec, pairs, now)` 簽章不變，另寫 `month_to = spec.month_to_text`（單月 None）、`depart_weekdays = mask`。
- `_exploration(row)`：`month_to` 不為 NULL 時填 `end_year`／`end_month`；星期由 mask 轉回 tuple；v1 列不特別處理。
- `table_counts()` 回傳順序：`watch, scan_run, price_observation, notification, exploration, comparison, comparison_cell`，仍是單一 UNION ALL SQL。
- 不新增 repository 方法；比價進行中用既有 `active_comparison()`。

## 4. Services
- `WatchService.create(raw)`／`update(id, raw)`：驗證通過後，若 `weekday_filter_leaves_nothing(spec, today)` 回 `{"depart_weekdays": WEEKDAYS_NO_MATCH_WINDOW}` 422，不寫入。
- `ExplorationService.create(raw)`：`pairs = range_pairs(spec, today)`（刪除截斷）。依序：0 格且全選 → `{"month": EXPLORATION_NO_DATES}`；0 格且有篩選 → `{"depart_weekdays": WEEKDAYS_NO_MATCH_MONTHS}`；`len(pairs) > max_cells` → `{"month_to": EXPLORATION_TOO_MANY_CELLS}`；之後才是重用、busy、額度（額度訊息帶 `months=len(spec.months)`）。
- `views.dates_text(spec)`：彈性窗且 `depart_weekdays_label` 不為 None 時接上 `"，" + label`。
- `ViewService.form_options(values)` 新增 `weekday_options: [{"value": 0, "label": "週一"}, …]`。新增、編輯、預填表單的 `values` 一律帶 `depart_weekdays: list[int]`。
- `DigestService.compose`：`DigestRow.weekdays_label = depart_weekdays_label(spec.depart_weekdays)`（固定日期 None）。
- `CommandService.status_text`：填 `CommandStatus.comparison`；探索狀態帶 `end_year`／`end_month`。`_scan`：既有 `COMMAND_SCAN_DEFERRED` 之後，若 `active_comparison()` 不為 None 再加 `COMMAND_SCAN_COMPARISON_DEFERRED`。
- `ExplorationViewService`：`explore_page()` 的 `values` 新增 `month_to`（等於 `month`）、`depart_weekdays`（全選）；新增 `weekday_options`、`max_months=3`、`over_limit_text=EXPLORATION_TOO_MANY_CELLS`、`quota.weekday_counts: dict[str, list[int]]`（key 為每個 `month_options` 的 value）。`_recent_row`：`month` 改 `month_range_label`，`conditions_label` 含星期。`exploration_page()`：`exploration.month_label` 改範圍；新增 `exploration.weekdays_label`、`exploration.stale_fallback`、`exploration.month_watch_label`（單月用既有字串）；頂層新增 `calendar_months`，保留 `weeks`；`exploration_conditions(spec)` 接上星期。`watch_prefill`：單格不變；`mode=month` 依 ADR Decision 6。`_cell_view`：cell 為 None 時依序 weekday_filtered → past → out_of_range。
- `ViewService.settings_page` 維護區自動多兩列（labels 來自 messages）。`services/retention.py` diff 為空。

## 5. HTTP API（JSON）
| 端點 | 新欄位 | 型別與預設 | 422 key |
|---|---|---|---|
| `POST /api/watches` | `depart_weekdays` | `int[]`（0..6）；缺 key＝全選；固定日期時忽略 | `depart_weekdays`（REQUIRED／INVALID／NO_MATCH_WINDOW） |
| `PUT /api/watches/{id}` | `depart_weekdays` | 同上；缺 key＝沿用既有值 | 同上 |
| `POST /api/explorations` | `month`（既有，語意改起始月）、`month_to`、`depart_weekdays` | `month_to: "YYYY-MM"`，缺或空＝單月；`depart_weekdays: int[]`，缺＝全選 | `month`（既有）、`month_to`（格式／範圍／BEFORE／SPAN／TOO_MANY_CELLS）、`depart_weekdays`（REQUIRED／INVALID／NO_MATCH_MONTHS） |
| `POST /api/comparisons` | 無 | 收到 `depart_weekdays` 時忽略 | 無 |
- 422 body 沿用 `{"errors": {key: message}}`。409／202／200 不變。
- 既有唯讀 JSON 若回傳監看條件，新增 `depart_weekdays: int[]`。各 status 端點白名單**不得新增**。

## 6. 樣板變數
- `watch_form.html`：`values.depart_weekdays`（list[int]；未定義視為全選）、`weekday_options`。結構：`<fieldset class="group" id="weekday-group" data-show-when="date_mode=flexible">`，legend「出發星期」，7 個 `<input type="checkbox" name="depart_weekdays" value="{0..6}">`，提示 `id="h-depart_weekdays"`（例如「全部勾選代表不限；只篩選去程出發日，回程不篩」），錯誤 `<span id="err-depart_weekdays" class="field-error" data-error-for="depart_weekdays">`。
- `explore.html`：既有 `<select id="f-month" name="month">` 的 label 改「起始月份」；新增 `<select id="f-month_to" name="month_to">`（label「結束月份」，選項同 `month_options`，預設 `values.month_to`）與 `data-error-for="month_to"`；星期群組同監看表單但不加 `data-show-when`，元素 id 用 `ex-` 前綴；`#explore-estimate` 新增 `data-weekday-counts='{{ quota.weekday_counts|tojson }}'`、`data-over-limit-text="{{ over_limit_text }}"`，`data-max-cells` 沿用；h1 與說明句用 §2.5 暫定文案。
- `exploration.html`：標題 `e.month_label`（範圍）；facts「條件」為 `e.conditions_label`（含星期）；stale 行 `{{ e.stale_note or e.stale_fallback }}`；日曆 `{% for m in calendar_months %}`，`calendar_months|length > 1` 時才輸出 `<h3>{{ m.label }}</h3>`，每月一個 table、caption 用 `m.label`；`cell.status == "weekday_filtered"` 走既有無價格分支顯示 `cell.label`；整段預填按鈕文字用 `e.month_watch_label`。
- `explore.html` 最近清單：`r.month`（範圍標籤）、`r.conditions_label`。
- `settings.html`：不改（`maintenance.table_counts` 自動多兩列）。

## 7. app.js
- `collectWatch`：`dateMode !== "fixed"` 分支加 `payload.depart_weekdays`（已勾選 `input[name="depart_weekdays"]` 依序 parseInt）。固定日期不送。
- `collectExplore`：加 `month_to: value("month_to")`、`depart_weekdays`。
- 預估 `estimateCells(box, form)`：讀 `JSON.parse(box.getAttribute("data-weekday-counts"))`，從 `#f-month` option 順序取起始到結束的索引區間（結束早於起始視為只有起始月），對每月加總已勾選星期；無屬性或解析失敗退回舊算法；文字格式沿用；估計值 > `data-max-cells` 時 `submit.disabled = true` 並以 `textContent` 接上 `data-over-limit-text`，否則恢復；監聯 `change`（checkbox 與兩個 select）。
- `syncWatchForm` 不改，由 `data-show-when="date_mode=flexible"` 控制星期群組顯示。
- 禁止：`getDay`、`getUTCDay`、`innerHTML`、在 JS 寫死 422 文案。

## 8. 測試側交付物
- FD-9 `expand_pairs` 對照實作（測試檔內原文副本）；全選單月時 `exploration.html`／`explore.html` 的 HTML 快照（**改檔前先錄**，存 `tests/snapshots/`）。
- 有資料的 v7 DB fixture（C-71）；C-72～C-79 矩陣；C-81 bench 腳本（輸出貼任務單）；AC-F4 修改清單範本：檔名::測試名、原期望、新期望、理由。

## 9. 總經理已裁（原「待確認」）
- `mode=month` 預填帶入星期。
- 單月沿用「2026 年 12 月」，跨月「2026 年 12 月～2027 年 2 月」。
- 探索頁 h1 與說明句採 §2.5 暫定文案，送風控定稿。
