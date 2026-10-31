# FD-9 介面契約（tech-architect 2026-10-29；dev-lead 與 frontend-engineer 並行依據）

規格本體見 ADR-0002「FD-9 增補」（Decision 1～6、C-61～C-70）與 `work/flight-deals-FD-9-PRD.md`。本檔只放兩邊要對齊的介面。

## Domain（`domain/models.py`、`domain/validation.py`、`domain/trip_labels.py`、`domain/messages.py`）
```python
@dataclass(frozen=True)
class ComparisonTarget:            # satisfies SearchConditions
    origin: str
    destination: str
    max_stops: int | None
    cabin: Cabin = "economy"
    adults: int = 1
    children: int = 0
    airlines: tuple[str, ...] = ()
    dep_hour_from: int | None = None
    dep_hour_to: int | None = None

@dataclass(frozen=True)
class ComparisonSpec:
    origin: str
    destinations: tuple[str, ...]   # input order, unique, 2..8
    trip_type: TripType
    depart_date: date
    return_date: date | None        # None iff one_way
    max_stops: int | None
    cabin: Cabin = "economy"
    currency: str = "TWD"
    adults: int = 1                 # fixed (FD-9)
    children: int = 0               # fixed (FD-9)
    @property
    def pair(self) -> DatePair: ...
    def target(self, destination: str) -> ComparisonTarget: ...
    def condition_key(self) -> str: ...
    # "cmp1|TPE|BKK,NRT,OSA|round_trip|2026-12-10|2026-12-15|-|1|0|economy|TWD"

MIN_DESTINATIONS = 2; MAX_DESTINATIONS = 8   # validation.py
@dataclass(frozen=True)
class ComparisonOutcome: spec: ComparisonSpec | None; errors: dict[str, str]
def validate_comparison(raw: Mapping[str, object], today: date) -> ComparisonOutcome
# error keys: origin, destinations, trip_type, date_input, depart_date, return_date, trip_days, max_stops, cabin

def stay_range_label(min_days: int, max_days: int) -> str      # trip_labels.py: "4 天" / "3–5 天"
def flight_duration_label(minutes: int | None) -> str | None   # trip_labels.py: "3 小時 25 分"
```
`messages.py` 新增：`COMPARISON_STATUS_LABELS`、`COMPARISON_ROW_LABELS`（keys：ok, pending, no_data, no_embedded_results, blocked, error, currency_mismatch, global_hourly_limit, breaker_open, interrupted）、`COMPARISON_REFERENCE_NOTE`、`COMPARISON_ORDER_NOTE`、`COMPARISON_BUSY`、`COMPARISON_BLOCKED_BY_EXPLORATION`、`COMPARISON_SCHEDULER_OFF`、`COMPARISON_NOT_FOUND`、`COMPARISON_RESTARTED`、`COMPARISON_DEFERRED_NOTE`、`COMPARISON_PREFILL_OK`（「已由比價帶入條件，請確認後送出」）、`COMPARISON_PREFILL_MISSING`、`DETAIL_ALL_DEPARTED`；函式 `comparison_quota_message(hourly_left, needed, reserve)`（含「本小時額度不足以開始比價，請稍後再試」）、`comparison_unfinished_note(done, total, reason)`、`comparison_reused_note(hours)`、`comparison_busy_message(path)`、`comparison_static_texts()`。文字定稿須經 risk-compliance-officer。

## Repository（`storage/repository.py`）
```python
@dataclass(frozen=True)
class ComparisonRecord:
    id: int; spec: ComparisonSpec; condition_key: str; status: str
    total: int; done: int; queries_used: int
    created_at: datetime; started_at: datetime | None; finished_at: datetime | None
    error_summary: str | None
    min_amount_minor: int | None = None      # list query only
    min_destination: str | None = None       # list query only; tie -> lowest position

@dataclass(frozen=True)
class ComparisonCellRecord:
    comparison_id: int; position: int; destination: str; status: str; reason: str | None
    source: str | None; price_kind: str | None; from_cache: bool; attempts: int
    amount_minor: int | None; currency: str | None; carrier: str | None; stops: int | None
    duration_minutes: int | None; depart_time: str | None
    as_of: datetime | None; fetched_at: datetime | None; error: str | None

def insert_comparison(self, spec: ComparisonSpec, now: datetime) -> int          # parent + N pending cells, one txn
def get_comparison(self, comparison_id: int) -> ComparisonRecord | None
def active_comparison(self) -> ComparisonRecord | None
def reusable_comparison(self, condition_key: str, since: datetime) -> ComparisonRecord | None  # status='done'
def list_comparisons_since(self, since: datetime) -> list[ComparisonRecord]       # one SQL, newest first
def comparison_cells(self, comparison_id: int) -> list[ComparisonCellRecord]       # ORDER BY position
def start_comparison(self, comparison_id: int, now: datetime) -> bool
def record_comparison_cell(self, comparison_id: int, position: int, update: CellUpdate) -> None
def finish_comparison(self, comparison_id: int, *, status: str, finished_at: datetime,
                      skip_reason: str, error_summary: str | None) -> int         # returns cells skipped here
def interrupt_active_comparisons(self, now: datetime, summary: str) -> list[int]
def delete_comparisons_created_before(self, cutoff: datetime) -> int               # not queued/running
def comparison_cell_counts_since(self, since: datetime) -> list[tuple[str, int, int]]
# modified: queries_used_since(since) adds comparison.queries_used (COALESCE(started_at, created_at) >= since)
```

## Service（`services/comparison.py`）
```python
ComparisonCreateStatus = Literal["created", "reused", "joined", "invalid", "quota", "busy", "scheduler_off"]
@dataclass(frozen=True)
class ComparisonCreateResult:
    status: ComparisonCreateStatus; comparison_id: int | None = None
    errors: dict[str, str] = field(default_factory=dict)
    hourly_left: int | None = None; needed: int | None = None
    message: str | None = None; progress_url: str | None = None
@dataclass
class ComparisonHooks: schedule: Callable[[int], None]; scheduler_running: Callable[[], bool]

class ComparisonService:
    def __init__(self, repo, sources, health, notifications, settings, *, scan_lock: threading.Lock,
                 create_lock: threading.Lock, reuse_hours: int, retention_days: int,
                 clock: Clock, redactor: Redactor) -> None
    hooks: ComparisonHooks
    def quota(self) -> QuotaView              # QuotaView from services.exploration; max_cells = 8
    def create(self, raw: Mapping[str, object]) -> ComparisonCreateResult
    def status(self, comparison_id: int) -> dict[str, object] | None   # {comparison_id, status, total, done}
    def run(self, comparison_id: int) -> str
    def recover_interrupted(self) -> list[int]
    def purge_expired(self) -> int
    def get(self, comparison_id: int) -> ComparisonRecord | None
```
`ExplorationService.__init__` 新增 `create_lock: threading.Lock | None = None`（keyword，預設自建）。`app.py` 只建一把 lock 傳給兩者。`Services` 新增 `comparison`、`comparison_views`。scheduler 新增 `COMPARE_PREFIX="compare:"`、`COMPARE_PURGE_JOB_ID="comparison-purge"`（併入 `NON_SCAN_JOB_IDS`）、`schedule_comparison(id)`、`_compare(id)`；`start()` 依序呼叫 `exploration.recover_interrupted()`、`comparison.recover_interrupted()`。

## View service（`services/comparison_views.py`）
```python
def comparison_order(cells: Sequence[ComparisonCellRecord], currency: str) -> list[ComparisonCellRecord]
class ComparisonViewService:
    def __init__(self, repo, settings, comparisons: ComparisonService, *, clock, link_builder=None)
    def compare_page(self) -> dict[str, Any]
    def comparison_page(self, comparison_id: int, *, reused: bool = False) -> dict[str, Any] | None
    def watch_prefill(self, base: dict[str, Any], comparison_id: str | None,
                      destination: str | None) -> tuple[dict[str, Any], str, str | None]
def active_comparison_view(repo) -> dict[str, int] | None   # {"id","done","total"}
```

## API
| 路由 | 需 header | 回應 |
|---|---|---|
| `POST /api/comparisons` | 是（缺少回 403） | 202 `{"ok":true,"id":int,"reused":false}`；200 reused `{"ok":true,"id":int,"reused":true}`；200 joined `{"ok":true,"id":int,"reused":false}`；409 `{"ok":false,"code":"quota"\|"busy"\|"scheduler_off","message":str,"id"?:int,"progress_url"?:str,"hourly_left"?:int,"needed"?:int}`（busy 時 `progress_url` 為 `/comparisons/<id>` 或 `/explorations/<id>`）；422 `{"ok":false,"errors":{key:msg}}` |
| `GET /api/comparisons/{id}/status` | 否 | 200 `{"comparison_id","status","total","done"}`、no-store；404 `{"ok":false,"errors":{"_":COMPARISON_NOT_FOUND}}`、no-store |
| `GET /explore/compare` | — | `compare.html` |
| `GET /comparisons/{id}?reused=1` | — | `comparison.html`；404 → `not_found.html` |
| `GET /watches/new?from_comparison=<id>&destination=<CODE>` | — | 只有 `from_exploration` 為 None 時才處理；沿用 `prefill_note`／`prefill_sampled_note`（後者 None），`watch_form.html` 不改 |

POST body：`{"origin":"TPE","destinations":["NRT","OSA","SEL"],"trip_type":"round_trip"|"one_way","date_input":"fixed"|"stay","depart_date":"YYYY-MM-DD","return_date":"YYYY-MM-DD"|null,"trip_days":int|null,"max_stops":""|"0"|"1"|"2","cabin":"economy"|...}`。其他欄位一律忽略。

## 樣板變數
- `compare.html`：`values{origin, origin_label, destinations:[{code,label}], trip_type, date_input, depart_date, return_date, trip_days(5), max_stops, cabin}`、`cabin_options`、`quota{hourly_left, reserve, available, min_destinations:2, max_destinations:8}`、`recent[{id, url, origin_label, destination_count, dates_label, trip_type_label, conditions_label, status, status_label, created_at_label, finished_at_label, cheapest_label, cheapest_destination_label}]`、`active`（`{kind:"comparison"|"exploration", id, done, total, url}` 或 None）、`today`、`max_date`、`disclaimer`。
- `comparison.html`：`comparison{id, origin_label, trip_type, trip_type_label, depart_date, return_date, dates_label, max_stops_label, cabin_label, pax_label("1 位成人"), pax_note("（1 人總價）"), status, status_label, done, total, queries_used, created_at_label, finished_at_label, error_summary, stale, stale_note, reused_note, deferred_note}`、`rows[{position, destination, destination_label, status, label, priced, amount_label, rank_note, carrier, stops_label, duration_label, depart_time, fetched_at_label, booking_url, booking_note, watch_url}]`、`order_note`、`disclaimer`。
- `explore.html` 新增 `active_comparison` 與入口卡片（連 `/explore/compare`）；`settings.html` 新增 `active_comparison` 一行；`base.html` nav 判斷 tuple 加 `"compare.html","comparison.html"`。
- `watch_detail.html`：`top_empty_note`（str 或 None）、`watch.stay_label`（取代原 `min–max`）。

## `app.js` 需要的 DOM 與 data 屬性
- 表單 `#compare-form[data-url="/api/comparisons"]`；出發地沿用 `data-combo="origin"`。
- 目的地挑選器：`div[data-combo="destination_pick"][data-combo-multi="destinations"]`；`initCombobox` 的 `select()` 改為 dispatch `CustomEvent("combo-select",{detail:{code,display}})`，既有單選行為不變。
- 已加入清單：`ul#compare-destinations[data-max="8"]`，每項 `li[data-code]` 內含移除按鈕 `button[data-remove-destination]`，一律用 createElement／textContent 建立。前端只擋完全相同的代碼和第 9 個；城市與機場的重疊交給後端判定。錯誤槽 `[data-error-for="destinations"]`。
- 日期：radio `name="date_input"`（fixed/stay），用 `data-show-when` 切換顯示；compare 的同步函式要能讀 `date_input`。
- 預覽 `#compare-estimate[data-available][data-hourly-left][data-reserve]`，文字「預計查詢 N 次／本小時可用 X 次（已保留 R 次給排程）」，N＝chip 數。
- 送出成功 → `/comparisons/<id>`，`reused===true` 時加 `?reused=1`；409 → 以 `_` 顯示 message，有 `progress_url` 時另外 createElement 一個 `<a>`；422 → `showErrors(errors)`。
- 進度：`#comparison-progress[data-total][data-done][data-status-url]`，加上 `#progress-text`、`#progress-bar`、`#progress-note`。建議抽成 `pollProgress(root, statusUrl)`，探索也改用它，但行為和 C-46 測試必須不變。
