"""N-177 / N-190 offline probe: detection gate and backtrack list, facts only.

Run from ``apps/stock-desk/backend`` against a *copy* of the DB, with the service stopped::

    uv run --no-sync python -I -X utf8 scripts/n177_n190_backtrack_probe.py \
        --db-path <copy of stock-desk.db> --out-dir <existing folder>

Spec: ``work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`` section 6.
Two jobs, one tool:

* N-177 detection (deployment gate): an executed S2 line used to mark its schedule and
  nothing else, so the shares stayed in the book. Categories N177-A .. N177-F.
* CEO #106 backtrack list for N-190: days on which a stop-loss line may not have been
  evaluated, days M1 did not evaluate, accumulated R deferrals, skipped batches.
  Categories N190-A .. N190-D.

Output is facts only: ids, dates, shares, prices and the trial figures of N177-A. It states
no conclusion and no advice. The one fixed label that is not a bare fact is the one n172
already used for rows the tool refuses to put a number on.

Read-only by construction (S1-S11, each covered by a test):

* the DB is opened with SQLite's ``mode=ro`` URI plus ``PRAGMA query_only=ON``; it is never
  created; only SELECT / WITH statements, all module constants, bound parameters only;
* the DB file is hashed (SHA-256) before and after; a difference is exit code 3;
* the production DB path (``<backend>/data/stock-desk.db`` or the file named by the
  environment variable, read for comparison only) is refused with exit code 4;
* the only files written by this tool are ``report.md`` and ``report.json`` in ``--out-dir``,
  opened in exclusive mode so an existing file is refused (a WAL-mode copy may make SQLite
  leave its own ``-shm`` / ``-wal`` files beside the copy; the DB hash covers the main file
  only);
* standard library only: no ``app`` import, no network, no secrets file.

Private data (RC-6): the report holds holdings and cash. Keep it on the machine that made
it; never commit it, and do not paste its contents anywhere. ``--out-dir`` inside a git work
tree is refused (RC-5). Free text read from the DB (rule summaries and the like) is never
copied into the report; only short tokens are (RC-3).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1"
SCHEMA_VERSION = 1
DB_PATH_ENV_VAR = "STOCK_DESK_DB_PATH"
PRODUCTION_DB_NAME = "stock-desk.db"
REPORT_MD_NAME = "report.md"
REPORT_JSON_NAME = "report.json"

EXIT_OK = 0
EXIT_UNREADABLE = 2
EXIT_HASH_CHANGED = 3
EXIT_REFUSED = 4

#: The one fixed label kept from the n172 probe.
MANUAL_LABEL = "需人工判讀"
TRIAL_LABEL = "可試算"

#: Risk-control wording (RC-4), verbatim from the review file; a test compares them.
GATE_LINE_TEMPLATE = "N-177 部署閘門：受影響標的 {n} 檔。依風控 A-1 條件 1，這個數字大於 0 時，N-177a 部署前由 CEO 逐檔在 (A)、(B) 之間選擇；本報告不預設任何一個選項。"  # noqa: E501
TRIAL_NOTE = "試算回補現金 = 第一張 S2 的成交判定價 × 試算分配股數合計。這個數字假設你已依第一張 S2 在券商賣出且成交（L9），按 N-177a 的分配規則算出，不一定等於你實際成交的金額；實際成交的股數與價格，只有你的券商對帳單能確認。"  # noqa: E501
TRIAL_LEGEND = "可試算：本檔沒有觸發本報告列出的任何一條誤判防護，所以列出試算；這不表示試算結果與你的券商紀錄一致。"  # noqa: E501

# ------------------------------------------------- constant copies (aligned by S11 tests)

#: ``wording.INDEX_GAP_DEFER_NOTE.split("{status}")[0]``.
INDEX_GAP_MARKER = "M1 今日未評估（加權指數資料 "
INDEX_SYMBOL = "^TWII"
INDEX_MARKET = "TW"
#: ``engine.DEMO_SOURCE`` (bars with this source are synthetic).
DEMO_SOURCE = "demo_synthetic"

#: N-177a ``S2_FILL_ENTRY`` (status, action, rule_id) and the batch_no IS NULL part.
S2_ENTRY_STATUS = "executed"
S2_ENTRY_ACTION = "sell"
S2_ENTRY_RULE_ID = "S2"
#: N-177a ``S2_ELIGIBLE_BATCH_SQL`` (same predicate as ``engine._symbol_average_cost``).
S2_ELIGIBLE_BATCH_SQL = "b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL"
#: N-177a ``FILL_MOVES_TABLE``.
FILL_MOVES_TABLE = "playbook_fill_moves"

#: ``RuleParams`` defaults (``system_default_params``), as strings.
DEFAULT_S1_RATIO = "0.90"
DEFAULT_S1_DEFENSE_RATIO = "0.93"
DEFAULT_S2_RATIO = "0.85"

# ------------------------------------------------------------------ SQL (SELECT only)

TABLE_EXISTS_SQL = "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?"

#: Spec 6.5 shared SQL 1: eligible batches now (= S2_ELIGIBLE_BATCH_SQL).
ELIGIBLE_BATCHES_SQL = """
SELECT symbol, batch_no, entry_date, cost, remaining_shares FROM playbook_batches AS b
WHERE b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL
ORDER BY symbol, batch_no
"""

#: Spec 6.5 shared SQL 2, table present: executed S2 rows without an audit row.
S2_UNAUDITED_SQL = """
SELECT d.id, d.symbol, d.shares, d.data_date, d.execution_date, d.created_at,
       d.settled_at, d.settled_open_price
FROM playbook_directives AS d
WHERE d.status = 'executed' AND d.action = 'sell' AND d.rule_id = 'S2'
  AND d.batch_no IS NULL AND d.settled = 1
  AND NOT EXISTS (SELECT 1 FROM playbook_fill_moves AS m WHERE m.directive_id = d.id)
ORDER BY d.symbol, d.execution_date, d.id
"""

#: Same without the NOT EXISTS clause, used when the audit table does not exist.
S2_UNAUDITED_NO_TABLE_SQL = """
SELECT d.id, d.symbol, d.shares, d.data_date, d.execution_date, d.created_at,
       d.settled_at, d.settled_open_price
FROM playbook_directives AS d
WHERE d.status = 'executed' AND d.action = 'sell' AND d.rule_id = 'S2'
  AND d.batch_no IS NULL AND d.settled = 1
ORDER BY d.symbol, d.execution_date, d.id
"""

#: N177-B: every S2 sell line (any state), for the counts and the date range.
S2_ROWS_SQL = """
SELECT id, symbol, status, settled, execution_date
FROM playbook_directives
WHERE rule_id = 'S2' AND action = 'sell' AND batch_no IS NULL
ORDER BY symbol, execution_date, id
"""

#: G-a, verbatim from the spec (parameters: symbol, first S2 id, first S2 execution date).
G_A_SQL = """
SELECT id, rule_id, action, batch_no, shares, execution_date FROM playbook_directives
WHERE symbol = ? AND settled = 1 AND status = 'executed' AND action IN ('buy','sell')
  AND id <> ? AND execution_date >= ?
  AND NOT (rule_id = 'S2' AND action = 'sell' AND batch_no IS NULL)
ORDER BY id
"""

#: G-c / N177-F, verbatim from the spec (parameter: symbol).
G_C_SQL = """
SELECT id, rule_id, batch_no, shares, execution_date FROM playbook_directives
WHERE symbol = ? AND settled = 0 AND status = 'pending' AND action = 'sell'
  AND batch_no IS NOT NULL AND rule_id <> 'S2'
ORDER BY id
"""

#: G-g: symbols that already have any audit row.
AUDIT_SYMBOLS_SQL = "SELECT DISTINCT symbol FROM playbook_fill_moves ORDER BY symbol"

#: Audit rows that name a batch, with the S2 line's execution date (N190-A hold replay).
FILL_MOVES_SQL = """
SELECT m.id, m.symbol, m.batch_no, m.shares_moved, d.execution_date, m.created_at
FROM playbook_fill_moves AS m
LEFT JOIN playbook_directives AS d ON d.id = m.directive_id
WHERE m.batch_no IS NOT NULL
ORDER BY m.id
"""

STATE_KEYS_SQL = """
SELECT key, value FROM playbook_state
WHERE key IN ('total_deploy_set_at', 'fast_market_measured_on', 'defense_active',
              'defense_since')
"""

BLACKLIST_SQL = """
SELECT symbol, triggered_on, until, rule_id FROM playbook_blacklist ORDER BY symbol
"""

#: N177-D, verbatim from the spec.
MISSING_BATCH_SQL = """
SELECT d.id, d.symbol, d.batch_no, d.rule_id, d.action, d.shares, d.execution_date,
       d.settled_open_price FROM playbook_directives AS d
WHERE d.status = 'executed' AND d.settled = 1 AND d.action IN ('buy','sell')
  AND NOT (d.rule_id = 'S2' AND d.action = 'sell' AND d.batch_no IS NULL)
  AND (d.batch_no IS NULL OR NOT EXISTS (SELECT 1 FROM playbook_batches AS b
       WHERE b.symbol = d.symbol AND b.batch_no = d.batch_no))
ORDER BY d.id
"""

#: N177-E.
PENDING_S2_SQL = """
SELECT id, symbol, shares, data_date, execution_date, created_at FROM playbook_directives
WHERE rule_id = 'S2' AND action = 'sell' AND settled = 0 AND status = 'pending'
ORDER BY symbol, execution_date, id
"""

BATCHES_SQL = """
SELECT symbol, batch_no, status, entry_date, cost, shares, remaining_shares, defer_count
FROM playbook_batches ORDER BY symbol, batch_no
"""

MIN_ENTRY_DATE_SQL = "SELECT MIN(entry_date) FROM playbook_batches"

#: Executed per-batch sells, replayed in order (N190-A hold definition).
SELL_ROWS_SQL = """
SELECT id, symbol, batch_no, shares, execution_date FROM playbook_directives
WHERE status = 'executed' AND settled = 1 AND action = 'sell' AND batch_no IS NOT NULL
ORDER BY execution_date, id
"""

PARAMS_SQL = "SELECT version, effective_date, payload FROM playbook_rule_params"

#: N190-A: spec query, plus the ORDER BY the report needs for stable output.
DAY_DIRECTIVES_SQL = """
SELECT symbol, batch_no, rule_id, action, data_date, MIN(created_at)
FROM playbook_directives WHERE data_date BETWEEN ? AND ?
GROUP BY symbol, batch_no, rule_id, action, data_date
ORDER BY data_date, symbol, batch_no, rule_id, action
"""

#: First time the system wrote an evaluation line for each data date (not EMERGENCY or
#: REBALANCE), the clock the cache facts are compared against.
FIRST_WRITE_SQL = """
SELECT data_date, MIN(created_at) FROM playbook_directives
WHERE rule_id NOT IN ('EMERGENCY', 'REBALANCE')
GROUP BY data_date
"""

#: TW bars in a date range, every symbol (index included), demo rows too (counted apart).
BARS_SQL = """
SELECT symbol, trade_date, close, source, fetched_at FROM price_bars_cache
WHERE market = ? AND trade_date BETWEEN ? AND ?
"""

INDEX_BARS_SQL = """
SELECT trade_date, fetched_at, source FROM price_bars_cache
WHERE symbol = ? AND market = ? AND source <> ? ORDER BY trade_date
"""

#: Fallback calendar when the cache holds no index bar: every real TW bar date.
TW_BAR_DATES_SQL = """
SELECT DISTINCT trade_date FROM price_bars_cache
WHERE market = ? AND source <> ? ORDER BY trade_date
"""

#: N190-B, verbatim from the spec (parameter: INDEX_GAP_MARKER).
M1_ROWS_SQL = """
SELECT id, symbol, batch_no, rule_id, action, data_date, execution_date, created_at, rule_summary
FROM playbook_directives
WHERE (rule_id = 'M1' AND action = 'defer')
   OR (rule_id = 'R3' AND action = 'skip' AND instr(rule_summary, ?) > 0)
ORDER BY data_date, id
"""

#: N190-C / N190-D: every deferral and skip line that names a batch.
DEFER_ROWS_SQL = """
SELECT id, symbol, batch_no, rule_id, action, execution_date, rule_summary
FROM playbook_directives
WHERE batch_no IS NOT NULL
  AND (action = 'defer' OR (action = 'skip' AND rule_id = 'R3'))
ORDER BY symbol, batch_no, id
"""

# ------------------------------------------------------------------ limitations

LIMITATIONS: dict[str, str] = {
    "L1": (
        "N-190 修正前沒有逐次評估紀錄，warnings 也不落檔。「評估了但沒有規則命中」與"
        "「沒有評估」無法區分；只有「已越過門檻、但當日沒有列」能強烈推定未評估"
        "（或當天沒開 /today）。"
    ),
    "L2": "P 系列（停利、移動停利）與 R1 進場不重算，所以不列。",
    "L3": "當日防守狀態無法回溯，S1 只能分成「一般門檻」與「僅防守門檻」兩種。",
    "L4": (
        "指數狀態只記在 M1 順延列上，也就是排程日、正常模式、該檔有 planned 批次的日子。"
        "其他日子 M1 是否評估無法回溯。"
    ),
    "L5": (
        "price_bars_cache 每根 bar 只留最新一版，fetched_at 會被覆寫，"
        "所以「評估時快取已有」只能單向證明。"
    ),
    "L6": (
        "持有區間是以已成交賣單重放推算的；N-166 之前的重複列會造成扭曲，請搭配 n172 探針一起看。"
    ),
    "L7": "黑名單相差的交易日數是用快取 bar 日期近似計算。",
    "L8": (
        "複本只反映複製當下的狀態，部署閘門以 R2 停機時的那次執行為準。"
        "WAL 模式的複本可能被 SQLite 在同資料夾建立 -shm、-wal 檔；DB 雜湊只涵蓋主檔。"
    ),
    "L9": ("試算回補假設使用者已照第一張 S2 在券商賣出（R10）。是否屬實只有券商對帳單能確認。"),
    "L10": "demo 來源的 bar 不計入，只計數。",
    "L11": (
        "時區：created_at、settled_at、fetched_at 是 UTC ISO；data_date 是台北交易日。"
        "只比較時間先後，不換算日界。"
    ),
}

CAT_S1 = "低於 S1 一般門檻"
CAT_S1_DEFENSE = "僅低於 S1 防守門檻"
CAT_S2 = "低於 S2 門檻"
NOTE_DEFENSE = "當日防守狀態無法回溯"
CACHE_HAD_BAR = "是"
CACHE_UNDETERMINED = "無法判定"
CACHE_NO_BAR = "快取無此 bar"

TRADING_DAY_BASIS_INDEX = "^TWII 快取 bar 日期"
TRADING_DAY_BASIS_UNION = "TW 標的 bar 日期聯集（快取無指數）"

REPORT_TABLES = (
    "playbook_directives",
    "playbook_batches",
    "playbook_state",
    "playbook_rule_params",
    "playbook_blacklist",
    "price_bars_cache",
    FILL_MOVES_TABLE,
)


# ------------------------------------------------------------------ small helpers


def fingerprint_of(data: bytes) -> str:
    """SHA-256 of ``data`` with line endings normalised to LF (git autocrlf safe)."""
    return hashlib.sha256(b"\n".join(data.splitlines()) + b"\n").hexdigest()


def script_fingerprint() -> str:
    """:func:`fingerprint_of` this very file."""
    return fingerprint_of(Path(__file__).read_bytes())


def sha256_file(path: Path) -> str:
    """SHA-256 of the file as stored (no normalisation)."""
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _decimal(text: object) -> Decimal | None:
    """A finite Decimal, or ``None`` when the value is absent or unusable."""
    if text is None:
        return None
    try:
        value = Decimal(str(text))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _ratio4(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def _instant(text: object) -> datetime | None:
    """An aware UTC datetime; a naive value is read as UTC (L11); junk is ``None``."""
    if text is None:
        return None
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    if moment.tzinfo is not None:
        return moment
    return datetime.combine(moment.date(), moment.time(), tzinfo=UTC)


def _opt_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(TABLE_EXISTS_SQL, (name,)).fetchone() is not None


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open ``path`` read-only (S1); refuses a missing file instead of creating one."""
    if not path.is_file():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
    except BaseException:
        conn.close()
        raise
    return conn


# ------------------------------------------------------------------ facts as read


@dataclass(frozen=True)
class S2Line:
    id: int
    symbol: str
    shares: int
    data_date: str
    execution_date: str
    created_at: str
    settled_at: str | None
    settled_open_price: str | None


@dataclass(frozen=True)
class EligibleBatch:
    symbol: str
    batch_no: int
    entry_date: str | None
    cost: str
    remaining_shares: int


@dataclass(frozen=True)
class BatchRow:
    symbol: str
    batch_no: int
    status: str
    entry_date: str | None
    cost: str | None
    shares: int
    remaining_shares: int
    defer_count: int


@dataclass(frozen=True)
class DeferRow:
    id: int
    symbol: str
    batch_no: int
    rule_id: str
    action: str
    execution_date: str
    rule_summary: str


@dataclass(frozen=True)
class M1Row:
    id: int
    symbol: str
    batch_no: int | None
    rule_id: str
    action: str
    data_date: str
    execution_date: str
    created_at: str
    rule_summary: str


@dataclass(frozen=True)
class Bar:
    close: str
    source: str
    fetched_at: str


@dataclass(frozen=True)
class ParamsRow:
    version: int
    effective_date: str
    payload: str


@dataclass
class Snapshot:
    """Everything the SELECTs returned; the classification works on this alone."""

    since: date | None
    until: date
    tables: dict[str, bool]
    eligible: dict[str, list[EligibleBatch]]
    s2_unaudited: list[S2Line]
    s2_rows: list[tuple[int, str, str, int, str]]
    audit_symbols: set[str]
    g_a_rows: dict[str, list[tuple[Any, ...]]]
    g_c_rows: dict[str, list[tuple[Any, ...]]]
    state: dict[str, str]
    blacklist: list[tuple[str, str, str, str]]
    calendar: list[str]
    calendar_basis: str | None
    missing_batch_rows: list[tuple[Any, ...]]
    pending_s2: list[tuple[Any, ...]]
    batches: list[BatchRow]
    sells: list[tuple[int, str, int, int, str]]
    fill_moves: list[tuple[int, str, int, int, str | None, str]]
    params_rows: list[ParamsRow]
    day_directives: list[tuple[str, int | None, str, str, str, str]]
    first_write: dict[str, str]
    bars: dict[str, dict[str, Bar]]
    demo_bars: dict[str, int]
    index_bars: dict[str, Bar]
    m1_rows: list[M1Row]
    defer_rows: list[DeferRow]


def first_s2_per_symbol(
    unaudited: Sequence[S2Line], eligible: Mapping[str, Sequence[EligibleBatch]]
) -> dict[str, tuple[S2Line, list[int]]]:
    """N177-A: per symbol the first qualifying S2 line and every qualifying id.

    An S2 line qualifies when its symbol now holds an eligible batch with
    ``entry_date IS NULL OR entry_date < execution_date`` (the L predicate).
    """
    found: dict[str, tuple[S2Line, list[int]]] = {}
    for line in sorted(unaudited, key=lambda s: (s.symbol, s.execution_date, s.id)):
        batches = eligible.get(line.symbol, ())
        if not any(b.entry_date is None or b.entry_date < line.execution_date for b in batches):
            continue
        if line.symbol in found:
            found[line.symbol][1].append(line.id)
        else:
            found[line.symbol] = (line, [line.id])
    return found


def _s2_line(row: Sequence[Any]) -> S2Line:
    return S2Line(
        id=int(row[0]),
        symbol=str(row[1]),
        shares=int(row[2]),
        data_date=str(row[3]),
        execution_date=str(row[4]),
        created_at=str(row[5]),
        settled_at=_opt_str(row[6]),
        settled_open_price=_opt_str(row[7]),
    )


def load(conn: sqlite3.Connection, *, since: date | None, until: date) -> Snapshot:
    """Read every fact the report needs; only SELECT statements are issued."""
    tables = {name: _table_exists(conn, name) for name in REPORT_TABLES}
    for required in ("playbook_directives", "playbook_batches"):
        if not tables[required]:
            raise sqlite3.OperationalError(f"no such table: {required}")
    has_audit = tables[FILL_MOVES_TABLE]
    has_bars = tables["price_bars_cache"]

    eligible: dict[str, list[EligibleBatch]] = {}
    for r in conn.execute(ELIGIBLE_BATCHES_SQL):
        eligible.setdefault(str(r[0]), []).append(
            EligibleBatch(str(r[0]), int(r[1]), _opt_str(r[2]), str(r[3]), int(r[4]))
        )
    s2_unaudited = [
        _s2_line(r)
        for r in conn.execute(S2_UNAUDITED_SQL if has_audit else S2_UNAUDITED_NO_TABLE_SQL)
    ]
    s2_rows = [
        (int(r[0]), str(r[1]), str(r[2]), int(r[3]), str(r[4])) for r in conn.execute(S2_ROWS_SQL)
    ]
    audit_symbols = {str(r[0]) for r in conn.execute(AUDIT_SYMBOLS_SQL)} if has_audit else set()

    affected = first_s2_per_symbol(s2_unaudited, eligible)
    g_a_rows: dict[str, list[tuple[Any, ...]]] = {}
    g_c_rows: dict[str, list[tuple[Any, ...]]] = {}
    for symbol, (first, _ids) in affected.items():
        g_a_rows[symbol] = [
            tuple(r) for r in conn.execute(G_A_SQL, (symbol, first.id, first.execution_date))
        ]
        g_c_rows[symbol] = [tuple(r) for r in conn.execute(G_C_SQL, (symbol,))]

    state = (
        {str(k): str(v) for k, v in conn.execute(STATE_KEYS_SQL)}
        if tables["playbook_state"]
        else {}
    )
    blacklist = (
        [(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in conn.execute(BLACKLIST_SQL)]
        if tables["playbook_blacklist"]
        else []
    )

    index_bars: dict[str, Bar] = {}
    calendar: list[str] = []
    calendar_basis: str | None = None
    if has_bars:
        for r in conn.execute(INDEX_BARS_SQL, (INDEX_SYMBOL, INDEX_MARKET, DEMO_SOURCE)):
            index_bars[str(r[0])] = Bar("", str(r[2]), str(r[1]))
        if index_bars:
            calendar = sorted(index_bars)
            calendar_basis = TRADING_DAY_BASIS_INDEX
        else:
            calendar = [
                str(r[0]) for r in conn.execute(TW_BAR_DATES_SQL, (INDEX_MARKET, DEMO_SOURCE))
            ]
            calendar_basis = TRADING_DAY_BASIS_UNION if calendar else None

    missing = [tuple(r) for r in conn.execute(MISSING_BATCH_SQL)]
    pending_s2 = [tuple(r) for r in conn.execute(PENDING_S2_SQL)]
    batches = [
        BatchRow(
            symbol=str(r[0]),
            batch_no=int(r[1]),
            status=str(r[2]),
            entry_date=_opt_str(r[3]),
            cost=_opt_str(r[4]),
            shares=int(r[5]),
            remaining_shares=int(r[6]),
            defer_count=int(r[7]),
        )
        for r in conn.execute(BATCHES_SQL)
    ]
    sells = [
        (int(r[0]), str(r[1]), int(r[2]), int(r[3]), str(r[4])) for r in conn.execute(SELL_ROWS_SQL)
    ]
    fill_moves = (
        [
            (int(r[0]), str(r[1]), int(r[2]), int(r[3]), _opt_str(r[4]), str(r[5]))
            for r in conn.execute(FILL_MOVES_SQL)
        ]
        if has_audit
        else []
    )
    params_rows = (
        [ParamsRow(int(r[0]), str(r[1]), str(r[2])) for r in conn.execute(PARAMS_SQL)]
        if tables["playbook_rule_params"]
        else []
    )

    resolved_since = since
    if resolved_since is None:
        earliest = conn.execute(MIN_ENTRY_DATE_SQL).fetchone()
        if earliest is not None and earliest[0] is not None:
            try:
                resolved_since = date.fromisoformat(str(earliest[0]))
            except ValueError:
                resolved_since = None
    day_directives: list[tuple[str, int | None, str, str, str, str]] = []
    bars: dict[str, dict[str, Bar]] = {}
    demo_bars: dict[str, int] = {}
    if resolved_since is not None and resolved_since <= until:
        low, high = resolved_since.isoformat(), until.isoformat()
        day_directives = [
            (str(r[0]), _opt_int(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5]))
            for r in conn.execute(DAY_DIRECTIVES_SQL, (low, high))
        ]
        if has_bars:
            for r in conn.execute(BARS_SQL, (INDEX_MARKET, low, high)):
                symbol = str(r[0])
                if symbol.startswith("^"):
                    continue
                if str(r[3]) == DEMO_SOURCE:
                    demo_bars[symbol] = demo_bars.get(symbol, 0) + 1
                    continue
                bars.setdefault(symbol, {})[str(r[1])] = Bar(str(r[2]), str(r[3]), str(r[4]))
    first_write = {str(r[0]): str(r[1]) for r in conn.execute(FIRST_WRITE_SQL)}
    m1_rows = [
        M1Row(
            id=int(r[0]),
            symbol=str(r[1]),
            batch_no=_opt_int(r[2]),
            rule_id=str(r[3]),
            action=str(r[4]),
            data_date=str(r[5]),
            execution_date=str(r[6]),
            created_at=str(r[7]),
            rule_summary=str(r[8]),
        )
        for r in conn.execute(M1_ROWS_SQL, (INDEX_GAP_MARKER,))
    ]
    defer_rows = [
        DeferRow(int(r[0]), str(r[1]), int(r[2]), str(r[3]), str(r[4]), str(r[5]), str(r[6]))
        for r in conn.execute(DEFER_ROWS_SQL)
    ]
    return Snapshot(
        since=resolved_since,
        until=until,
        tables=tables,
        eligible=eligible,
        s2_unaudited=s2_unaudited,
        s2_rows=s2_rows,
        audit_symbols=audit_symbols,
        g_a_rows=g_a_rows,
        g_c_rows=g_c_rows,
        state=state,
        blacklist=blacklist,
        calendar=calendar,
        calendar_basis=calendar_basis,
        missing_batch_rows=missing,
        pending_s2=pending_s2,
        batches=batches,
        sells=sells,
        fill_moves=fill_moves,
        params_rows=params_rows,
        day_directives=day_directives,
        first_write=first_write,
        bars=bars,
        demo_bars=demo_bars,
        index_bars=index_bars,
        m1_rows=m1_rows,
        defer_rows=defer_rows,
    )


# ------------------------------------------------------------------ N-177 classification


def allocate(shares: int, batches: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """N-177a section 4.4: ascending ``batch_no``, ``moved = min(remaining, left)``."""
    left = shares
    moved: list[tuple[int, int]] = []
    for batch_no, remaining in sorted(batches):
        if left <= 0:
            break
        take = min(remaining, left)
        if take > 0:
            moved.append((batch_no, take))
            left -= take
    return moved


def _ids_text(ids: Sequence[object]) -> str:
    return ",".join(str(i) for i in ids)


def _classify_affected(
    snap: Snapshot, symbol: str, first: S2Line, qualifying: list[int]
) -> dict[str, Any]:
    eligible = snap.eligible[symbol]
    reasons: list[dict[str, str]] = []

    other = snap.g_a_rows.get(symbol, [])
    if other:
        reasons.append(
            {"code": "G-a", "detail": f"同檔有其他已成交單 ids={_ids_text([r[0] for r in other])}"}
        )

    set_at = snap.state.get("total_deploy_set_at")
    set_moment = _instant(set_at)
    settled_moment = _instant(first.settled_at)
    if set_moment is None:
        reasons.append({"code": "G-b", "detail": "total_deploy_set_at 不存在或無法解析"})
    elif settled_moment is None:
        reasons.append({"code": "G-b", "detail": "第一張 S2 的 settled_at 無法解析，無法比較"})
    elif set_moment > settled_moment:
        reasons.append(
            {
                "code": "G-b",
                "detail": "total_deploy_set_at 晚於第一張 S2 的 settled_at",
            }
        )

    eligible_numbers = {b.batch_no for b in eligible}
    inflight = [r for r in snap.g_c_rows.get(symbol, []) if r[2] in eligible_numbers]
    # RC-2: the in-flight sells are a fact column (N177-F); only one that is due no later
    # than the first S2 makes the order of events unknowable from the report (G-c').
    early = [r for r in inflight if str(r[4]) <= first.execution_date]
    if early:
        reasons.append(
            {
                "code": "G-c'",
                "detail": (
                    "合格批次上有預定執行日不晚於第一張 S2 的在途賣單 "
                    f"ids={_ids_text([r[0] for r in early])}"
                ),
            }
        )

    # D-9: a row with an enumerated value outside the known set must not feed a trial.
    odd: list[int] = [
        int(r[0])
        for r in snap.g_a_rows.get(symbol, [])
        if str(r[1]) not in ENUM_VALUES["rule_id"] or str(r[2]) not in ENUM_VALUES["action"]
    ]
    odd += [
        int(r[0]) for r in snap.g_c_rows.get(symbol, []) if str(r[1]) not in ENUM_VALUES["rule_id"]
    ]
    odd += [
        row[0] for row in snap.s2_rows if row[1] == symbol and row[2] not in ENUM_VALUES["status"]
    ]
    if odd:
        reasons.append(
            {
                "code": "D-9",
                "detail": f"判定用到含非預期枚舉值的列 ids={_ids_text(sorted(set(odd)))}",
            }
        )

    price = _decimal(first.settled_open_price)
    if price is None:
        reasons.append({"code": "G-d", "detail": "settled_open_price 缺漏、無法解析或不是有限值"})

    null_entry = [b.batch_no for b in eligible if b.entry_date is None]
    if null_entry:
        reasons.append(
            {"code": "G-e", "detail": f"合格批次 entry_date 為 NULL，批次={_ids_text(null_entry)}"}
        )

    earlier = [
        b for b in eligible if b.entry_date is not None and b.entry_date < first.execution_date
    ]
    earlier_total = sum(b.remaining_shares for b in earlier)
    if first.shares != earlier_total:
        reasons.append(
            {
                "code": "G-f",
                "detail": (
                    f"S2 股數 {first.shares} 不等於進場日早於它的合格批次合計 {earlier_total}"
                ),
            }
        )

    if symbol in snap.audit_symbols:
        reasons.append({"code": "G-g", "detail": "該檔已有稽核列，N-177a 版本已在此 DB 運作過"})

    trial: dict[str, Any] | None = None
    if not reasons and price is not None:
        moved = allocate(first.shares, [(b.batch_no, b.remaining_shares) for b in earlier])
        total = sum(shares for _no, shares in moved)
        trial = {
            "allocation": [{"batch_no": no, "shares": shares} for no, shares in moved],
            "total_shares": total,
            "price": _money(price),
            "cash": _money(price * Decimal(total)),
        }
    later = [
        row
        for row in snap.s2_rows
        if row[1] == symbol
        and row[2] == "executed"
        and row[3] == 1
        and (row[4], row[0]) > (first.execution_date, first.id)
    ]
    pending = [
        row for row in snap.s2_rows if row[1] == symbol and row[3] == 0 and row[2] == "pending"
    ]
    verdict = (
        TRIAL_LABEL
        if trial is not None
        else MANUAL_LABEL + "：" + "；".join(f"{r['code']} {r['detail']}" for r in reasons)
    )
    return {
        "symbol": symbol,
        "first_s2": {
            "id": first.id,
            "data_date": first.data_date,
            "execution_date": first.execution_date,
            "shares": first.shares,
            "settled_open_price": first.settled_open_price,
            "settled_at": first.settled_at,
        },
        "qualifying_s2_ids": qualifying,
        "later_executed_s2": len(later),
        "pending_s2": len(pending),
        "eligible_batches": [
            {"batch_no": b.batch_no, "remaining_shares": b.remaining_shares} for b in eligible
        ],
        "eligible_total": sum(b.remaining_shares for b in eligible),
        "verdict": verdict,
        "guards": [r["code"] for r in reasons],
        "reasons": reasons,
        "trial": trial,
    }


def _s2_counts(snap: Snapshot, skip: set[str]) -> list[dict[str, Any]]:
    """N177-B for the symbols that are not in N177-A."""
    per: dict[str, dict[str, Any]] = {}
    for _id, symbol, status, settled, execution_date in snap.s2_rows:
        if symbol in skip:
            continue
        entry = per.setdefault(symbol, {"symbol": symbol, "executed": 0, "pending": 0, "dates": []})
        if status == "executed" and settled == 1:
            entry["executed"] += 1
        elif status == "pending" and settled == 0:
            entry["pending"] += 1
        else:
            continue
        entry["dates"].append(execution_date)
    rows = []
    for symbol in sorted(per):
        entry = per[symbol]
        dates = sorted(entry.pop("dates"))
        entry["earliest_execution_date"] = dates[0] if dates else None
        entry["latest_execution_date"] = dates[-1] if dates else None
        if entry["executed"] or entry["pending"]:
            rows.append(entry)
    return rows


def _day_distance(calendar: Sequence[str], start: str, end: str) -> int:
    """Signed count of calendar dates in ``(start, end]`` (negative when end < start)."""
    if end >= start:
        return sum(1 for d in calendar if start < d <= end)
    return -sum(1 for d in calendar if end < d <= start)


def classify_n177(snap: Snapshot) -> dict[str, Any]:
    firsts = first_s2_per_symbol(snap.s2_unaudited, snap.eligible)
    affected = [
        _classify_affected(snap, symbol, first, ids)
        for symbol, (first, ids) in sorted(firsts.items())
    ]
    # N177-C: every blacklist row; the day distance only where a first S2 exists.
    blacklist = []
    for symbol, triggered_on, until, rule_id in snap.blacklist:
        row: dict[str, Any] = {
            "symbol": symbol,
            "triggered_on": triggered_on,
            "until": until,
            "rule_id": rule_id,
            "first_s2_data_date": None,
            "trading_day_difference": None,
            "difference_basis": None,
        }
        if symbol in firsts:
            data_date = firsts[symbol][0].data_date
            row["first_s2_data_date"] = data_date
            if snap.calendar_basis is not None:
                row["trading_day_difference"] = _day_distance(
                    snap.calendar, data_date, triggered_on
                )
                row["difference_basis"] = snap.calendar_basis
        blacklist.append(row)

    missing = []
    for r in snap.missing_batch_rows:
        price = _decimal(r[7])
        missing.append(
            {
                "id": int(r[0]),
                "symbol": str(r[1]),
                "batch_no": _opt_int(r[2]),
                "rule_id": str(r[3]),
                "action": str(r[4]),
                "shares": int(r[5]),
                "execution_date": str(r[6]),
                "settled_open_price": _opt_str(r[7]),
                "unbooked_amount": _money(
                    price * Decimal(int(r[5])) if price is not None else None
                ),
                "note": "N2 已揭露" if str(r[3]) == "EMERGENCY" else None,
            }
        )
    pending = [
        {
            "id": int(r[0]),
            "symbol": str(r[1]),
            "shares": int(r[2]),
            "data_date": str(r[3]),
            "execution_date": str(r[4]),
            "created_at": str(r[5]),
        }
        for r in snap.pending_s2
    ]
    inflight = []
    for item in affected:
        symbol = str(item["symbol"])
        numbers = {b["batch_no"] for b in item["eligible_batches"]}
        for r in snap.g_c_rows.get(symbol, []):
            if r[2] in numbers:
                inflight.append(
                    {
                        "id": int(r[0]),
                        "symbol": symbol,
                        "rule_id": str(r[1]),
                        "batch_no": int(r[2]),
                        "shares": int(r[3]),
                        "execution_date": str(r[4]),
                    }
                )
    return {
        "affected": affected,
        "not_affected_s2": _s2_counts(snap, {str(a["symbol"]) for a in affected}),
        "blacklist": blacklist,
        "missing_batch_rows": missing,
        "pending_s2": pending,
        "inflight_on_affected": inflight,
    }


# ------------------------------------------------------------------ N-190 classification


def _cache_fact(fetched_at: str | None, first_write: str | None) -> str:
    fetched = _instant(fetched_at)
    wrote = _instant(first_write)
    if fetched is None or wrote is None:
        return CACHE_UNDETERMINED
    return CACHE_HAD_BAR if fetched <= wrote else CACHE_UNDETERMINED


def _params_on(rows: Sequence[ParamsRow], day: str) -> dict[str, Any] | None:
    """The rule-set row ``active_params`` would pick for ``day`` (None: no row at all)."""
    chosen: ParamsRow | None = None
    for row in sorted(rows, key=lambda p: (p.effective_date, p.version), reverse=True):
        if row.effective_date <= day:
            chosen = row
            break
    if chosen is None:
        return {
            "version": "default",
            "s1": Decimal(DEFAULT_S1_RATIO),
            "s1d": Decimal(DEFAULT_S1_DEFENSE_RATIO),
            "s2": Decimal(DEFAULT_S2_RATIO),
        }
    try:
        payload = json.loads(chosen.payload)
        s1 = Decimal(str(payload.get("s1_ratio", DEFAULT_S1_RATIO)))
        s1d = Decimal(str(payload.get("s1_defense_ratio", DEFAULT_S1_DEFENSE_RATIO)))
        s2 = Decimal(str(payload.get("s2_ratio", DEFAULT_S2_RATIO)))
    except (ValueError, InvalidOperation, AttributeError):
        return None
    if not (s1.is_finite() and s1d.is_finite() and s2.is_finite()):
        return None
    return {"version": str(chosen.version), "s1": s1, "s1d": s1d, "s2": s2}


def _remaining_by_day(
    batch: BatchRow, days: Sequence[str], events: Sequence[tuple[str, int, int]]
) -> dict[str, int]:
    """Replay a batch's recorded moves: ``remaining = max(0, remaining - shares)``."""
    remaining = batch.shares
    pointer = 0
    out: dict[str, int] = {}
    for day in days:
        while pointer < len(events) and events[pointer][0] <= day:
            remaining = max(0, remaining - events[pointer][2])
            pointer += 1
        out[day] = remaining
    return out


def classify_n190_stop_loss(snap: Snapshot) -> dict[str, Any]:
    events: dict[tuple[str, int], list[tuple[str, int, int]]] = {}
    for _sell_id, symbol, batch_no, shares, execution_date in snap.sells:
        events.setdefault((symbol, batch_no), []).append((execution_date, 0, shares))
    for _id, m_symbol, m_batch, moved, m_date, created_at in snap.fill_moves:
        events.setdefault((m_symbol, m_batch), []).append((m_date or created_at[:10], 1, moved))
    for key in events:
        events[key].sort(key=lambda e: (e[0], e[1]))

    rows_by_day: dict[tuple[str, str], list[tuple[int | None, str, str]]] = {}
    for d_symbol, d_batch, rule_id, action, data_date, _created in snap.day_directives:
        rows_by_day.setdefault((d_symbol, data_date), []).append((d_batch, rule_id, action))

    batches_by_symbol: dict[str, list[BatchRow]] = {}
    for batch in snap.batches:
        if batch.entry_date is not None:
            batches_by_symbol.setdefault(batch.symbol, []).append(batch)

    candidates: list[dict[str, Any]] = []
    held_summary: list[dict[str, Any]] = []
    unusable = {"close": 0, "cost": 0, "params": 0}
    since_text = snap.since.isoformat() if snap.since is not None else None
    until_text = snap.until.isoformat()
    params_cache: dict[str, dict[str, Any] | None] = {}

    for symbol in sorted(batches_by_symbol):
        symbol_bars = snap.bars.get(symbol, {})
        days = sorted(
            d for d in symbol_bars if since_text is not None and since_text <= d <= until_text
        )
        if not days:
            continue
        symbol_batches = batches_by_symbol[symbol]
        timeline = {
            b.batch_no: _remaining_by_day(b, days, events.get((symbol, b.batch_no), []))
            for b in symbol_batches
        }
        held_days = 0
        with_rows = 0
        for day in days:
            held = [
                (b, timeline[b.batch_no][day])
                for b in symbol_batches
                if b.entry_date is not None
                and b.entry_date <= day
                and timeline[b.batch_no][day] > 0
            ]
            if not held:
                continue
            held_days += 1
            day_rows = rows_by_day.get((symbol, day), [])
            if day_rows:
                with_rows += 1
            bar = symbol_bars[day]
            close = _decimal(bar.close)
            if close is None:
                unusable["close"] += 1
                continue
            if day not in params_cache:
                params_cache[day] = _params_on(snap.params_rows, day)
            params = params_cache[day]
            if params is None:
                unusable["params"] += 1
                continue
            has_s2_row = any(rule == "S2" for _no, rule, _act in day_rows)
            written = snap.first_write.get(day)
            common = {
                "symbol": symbol,
                "data_date": day,
                "close": _money(close),
                "symbol_has_rows": bool(day_rows),
                "system_wrote": written is not None,
                "cache_had_bar": _cache_fact(bar.fetched_at, written),
                "params_version": params["version"],
            }
            for batch, _remaining in held:
                cost = _decimal(batch.cost)
                if cost is None or cost <= 0:
                    unusable["cost"] += 1
                    continue
                has_s1_row = any(
                    rule == "S1" and no == batch.batch_no for no, rule, _act in day_rows
                )
                if has_s1_row or has_s2_row:
                    continue
                general = cost * params["s1"]
                defense = cost * params["s1d"]
                if close < general:
                    category, threshold, note = CAT_S1, general, None
                elif close < defense:
                    category, threshold, note = CAT_S1_DEFENSE, defense, NOTE_DEFENSE
                else:
                    continue
                candidates.append(
                    {
                        **common,
                        "batch_no": batch.batch_no,
                        "cost": _money(cost),
                        "close_over_cost": _ratio4(close / cost),
                        "threshold": _money(threshold),
                        "category": category,
                        "note": note,
                    }
                )
            costed = [(b, r) for b, r in held if (_decimal(b.cost) or Decimal(0)) > 0]
            total = sum(r for _b, r in costed)
            if total > 0 and not has_s2_row:
                weighted = sum(
                    (_decimal(b.cost) or Decimal(0)) * Decimal(r) for b, r in costed
                ) / Decimal(total)
                threshold = weighted * params["s2"]
                if close < threshold:
                    candidates.append(
                        {
                            **common,
                            "batch_no": None,
                            "cost": _money(weighted),
                            "close_over_cost": _ratio4(close / weighted),
                            "threshold": _money(threshold),
                            "category": CAT_S2,
                            "note": None,
                        }
                    )
        held_summary.append(
            {
                "symbol": symbol,
                "held_days": held_days,
                "days_with_symbol_rows": with_rows,
                "days_without_symbol_rows": held_days - with_rows,
            }
        )
    candidates.sort(
        key=lambda c: (
            c["symbol"],
            c["data_date"],
            -1 if c["batch_no"] is None else c["batch_no"],
            c["category"],
        )
    )
    return {
        "stop_loss_candidates": candidates,
        "held_summary": held_summary,
        "stats": {
            "since": since_text,
            "until": until_text,
            "demo_bars_excluded": dict(sorted(snap.demo_bars.items())),
            "unusable_close_days": unusable["close"],
            "unusable_cost_batches": unusable["cost"],
            "unusable_params_days": unusable["params"],
        },
    }


def _index_status(summary: str) -> str | None:
    position = summary.find(INDEX_GAP_MARKER)
    if position < 0:
        return None
    tail = summary[position + len(INDEX_GAP_MARKER) :]
    end = tail.find("）")
    return tail[:end] if end >= 0 else None


def classify_n190_m1(snap: Snapshot) -> dict[str, Any]:
    by_day: dict[str, list[M1Row]] = {}
    for row in snap.m1_rows:
        by_day.setdefault(row.data_date, []).append(row)
    days = []
    for day in sorted(by_day):
        rows = by_day[day]
        deferred = {(r.symbol, r.batch_no, r.execution_date) for r in rows if r.action == "defer"}
        skipped = {(r.symbol, r.batch_no, r.execution_date) for r in rows if r.action == "skip"}
        statuses = sorted({s for s in (_index_status(r.rule_summary) for r in rows) if s})
        bar = snap.index_bars.get(day)
        written = snap.first_write.get(day)
        days.append(
            {
                "data_date": day,
                "execution_dates": sorted({r.execution_date for r in rows}),
                "index_status": statuses,
                "deferred_batches": len(deferred),
                "skipped_batches": len(skipped),
                "line_ids": sorted(r.id for r in rows),
                "index_cache_had_bar": CACHE_NO_BAR
                if bar is None
                else _cache_fact(bar.fetched_at, written),
            }
        )
    state = {
        key: snap.state.get(key)
        for key in ("fast_market_measured_on", "defense_active", "defense_since")
    }
    return {"m1_unevaluated_days": days, "m1_state": state}


def classify_n190_defers(snap: Snapshot) -> dict[str, Any]:
    per: dict[tuple[str, int], list[DeferRow]] = {}
    for row in snap.defer_rows:
        per.setdefault((row.symbol, row.batch_no), []).append(row)
    batch_index = {(b.symbol, b.batch_no): b for b in snap.batches}

    def counts(rows: Sequence[DeferRow]) -> dict[str, Any]:
        m1 = [r for r in rows if r.rule_id == "M1" and r.action == "defer"]
        r2 = [r for r in rows if r.rule_id == "R2" and r.action == "defer"]
        m1_dates = {r.execution_date for r in m1}
        stale = {r.execution_date for r in m1 if _index_status(r.rule_summary) == "cached_stale"}
        r2_dates = {r.execution_date for r in r2}
        share = None
        if m1_dates or r2_dates:
            share = _ratio4(Decimal(len(m1_dates)) / Decimal(len(m1_dates) + len(r2_dates)))
        return {
            "m1_defers": len(m1_dates),
            "m1_cached_stale": len(stale),
            "r2_defers": len(r2_dates),
            "r3_skip_ids": sorted(r.id for r in rows if r.rule_id == "R3" and r.action == "skip"),
            "m1_share": share,
        }

    defer_counts = []
    keys = sorted(set(per) | {(b.symbol, b.batch_no) for b in snap.batches if b.defer_count > 0})
    for key in keys:
        batch = batch_index.get(key)
        defer_counts.append(
            {
                "symbol": key[0],
                "batch_no": key[1],
                "status": batch.status if batch else None,
                "defer_count": batch.defer_count if batch else None,
                **counts(per.get(key, [])),
            }
        )
    skipped = []
    for batch in snap.batches:
        if batch.status != "skipped":
            continue
        rows = per.get((batch.symbol, batch.batch_no), [])
        r3 = [r for r in rows if r.rule_id == "R3" and r.action == "skip"]
        if not r3:
            reason = "無 R3 跳過列"
        elif any(INDEX_GAP_MARKER in r.rule_summary for r in r3):
            reason = "指數缺漏順延累計"
        else:
            reason = "其他（R2 不追價順延或 T+1 未成交累計）"
        detail = counts(rows)
        skipped.append(
            {
                "symbol": batch.symbol,
                "batch_no": batch.batch_no,
                "r3_skip_ids": detail["r3_skip_ids"],
                "reason_category": reason,
                "m1_defers": detail["m1_defers"],
                "m1_cached_stale": detail["m1_cached_stale"],
            }
        )
    return {"defer_counts": defer_counts, "skipped_batches": skipped}


# ------------------------------------------------------------------ report assembly


def diff_against_previous(
    affected: Sequence[Mapping[str, Any]], previous: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Compare by ``(symbol, first S2 id)``: verdict, guards and trial figures."""

    def fingerprint(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "verdict": entry["verdict"],
            "guards": entry["guards"],
            "trial": entry["trial"],
        }

    def key(entry: Mapping[str, Any]) -> str:
        return f"{entry['symbol']}:{entry['first_s2']['id']}"

    now = {key(a): a for a in affected}
    before = {key(a): a for a in previous.get("n177", {}).get("affected", [])}
    rows = []
    for k in sorted(set(now) | set(before)):
        if k not in before:
            status = "前次沒有"
        elif k not in now:
            status = "本次沒有"
        elif fingerprint(now[k]) == fingerprint(before[k]):
            status = "與前次相同"
        else:
            status = "與前次不同"
        rows.append({"key": k, "result": status})
    return rows


def build_result(
    snap: Snapshot,
    *,
    db_path: str,
    hash_before: str,
    hash_after: str,
    run_at: datetime,
    previous: Mapping[str, Any] | None,
) -> dict[str, Any]:
    n177 = classify_n177(snap)
    symbols = sorted(a["symbol"] for a in n177["affected"])
    n190: dict[str, Any] = {
        **classify_n190_stop_loss(snap),
        **classify_n190_m1(snap),
        **classify_n190_defers(snap),
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "script_version": SCRIPT_VERSION,
            "script_sha256_lf": script_fingerprint(),
            "db_path": db_path,
            "db_sha256_before": hash_before,
            "db_sha256_after": hash_after,
            "run_at_utc": run_at.isoformat(),
            "since": snap.since.isoformat() if snap.since is not None else None,
            "until": snap.until.isoformat(),
            "tables": dict(sorted(snap.tables.items())),
            "trading_day_basis": snap.calendar_basis,
        },
        "gate": {
            "n177_affected_symbols": symbols,
            "n177_affected_count": len(symbols),
            "ceo_decision_required": bool(symbols),
        },
        "n177": n177,
        "n190": n190,
        "limitations": sorted(LIMITATIONS, key=lambda c: int(c[1:])),
        "diff_vs_previous": None
        if previous is None
        else diff_against_previous(n177["affected"], previous),
    }
    counter = [0]
    sanitized: dict[str, Any] = sanitize(result, None, counter)
    sanitized["meta"]["unexpected_enum_values"] = counter[0]
    return sanitized


#: RC-3: values read from the DB may only be short ASCII tokens in the report.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:+\-^' ]{0,64}")
UNEXPECTED_TOKEN = "(非預期格式)"
#: Keys whose values are fixed wording of this tool (never DB text).
_FIXED_TEXT_KEYS = frozenset(
    {
        "verdict",
        "detail",
        "category",
        "note",
        "reason_category",
        "difference_basis",
        "trading_day_basis",
        "cache_had_bar",
        "index_cache_had_bar",
        "result",
        "db_path",
    }
)


ENUM_UNEXPECTED = "（非預期值）"
#: Enumerated columns: printed as read only when the value is a known one. ``source`` is
#: not printed by any category today, so no value is known for it.
ENUM_VALUES: dict[str, frozenset[str]] = {
    "rule_id": frozenset(
        {"R1", "R2", "R3", "R4", "S1", "S2", "S3", "P1", "P2", "P3", "M1", "IRON1"}
        | {"EMERGENCY", "REBALANCE"}
    ),
    "action": frozenset({"buy", "sell", "defer", "skip", "none"}),
    "status": frozenset({"pending", "executed", "missed", "planned", "open", "closed", "skipped"}),
    "source": frozenset(),
}


def sanitize(value: Any, key: str | None = None, counter: list[int] | None = None) -> Any:
    """Pass fixed wording through; enumerated columns by known value; the rest as tokens."""
    if isinstance(value, dict):
        return {k: sanitize(v, k, counter) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, key, counter) for v in value]
    if isinstance(value, str) and key in ENUM_VALUES:
        if value in ENUM_VALUES[key]:
            return value
        if counter is not None:
            counter[0] += 1
        return ENUM_UNEXPECTED
    if isinstance(value, str) and key not in _FIXED_TEXT_KEYS:
        return value if _TOKEN_RE.fullmatch(value) else UNEXPECTED_TOKEN
    return value


def render_json(result: Mapping[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _cell(value: object) -> str:
    if value is None:
        return "-"
    text = str(value)
    return " ".join("\\|".join(text.split("|")).split())


def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    if not rows:
        return ["（無）", ""]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    lines.append("")
    return lines


def _batches_text(items: Sequence[Mapping[str, Any]]) -> str:
    return "、".join(f"{i['batch_no']}:{i['remaining_shares']}" for i in items) or "-"


def render_markdown(result: Mapping[str, Any]) -> str:
    meta = result["meta"]
    n177 = result["n177"]
    n190 = result["n190"]
    gate = result["gate"]
    out: list[str] = ["# N-177 / N-190 唯讀偵測與回溯報告", ""]
    out += [
        f"- 版本：{meta['script_version']}",
        f"- 腳本 SHA-256（LF 正規化）：{meta['script_sha256_lf']}",
        f"- db_path：{meta['db_path']}",
        f"- 執行前 DB SHA-256：{meta['db_sha256_before']}",
        f"- 執行後 DB SHA-256：{meta['db_sha256_after']}",
        f"- run_at_utc：{meta['run_at_utc']}",
        f"- since：{meta['since'] or '（無批次進場日）'}",
        f"- until：{meta['until']}",
    ]
    for name, present in meta["tables"].items():
        out.append(f"- 資料表 {name}：{'存在' if present else '不存在'}")
    out.append(f"- 交易日計數依據（黑名單相差）：{meta['trading_day_basis'] or '（快取沒有 bar）'}")
    out += [
        "- 枚舉欄位（rule_id、action、status、source）的非預期值個數："
        f"{meta['unexpected_enum_values']}",
        f"- 註：{FILL_MOVES_TABLE} 存在，表示這個 DB 已被 N-177a 版本開啟過",
        "",
    ]
    out += [
        "## 摘要",
        "",
        *_table(
            ["類別", "筆數"],
            [
                ["N177-A 受影響標的", gate["n177_affected_count"]],
                ["N177-B 其他有 S2 的標的", len(n177["not_affected_s2"])],
                ["N177-C 黑名單", len(n177["blacklist"])],
                ["N177-D 帳冊找不到所屬批次的成交列", len(n177["missing_batch_rows"])],
                ["N177-E 待結算的 S2", len(n177["pending_s2"])],
                ["N177-F 受影響批次上的在途賣單", len(n177["inflight_on_affected"])],
                ["N190-A 停損未評估的候選", len(n190["stop_loss_candidates"])],
                ["N190-B M1 未評估的日子", len(n190["m1_unevaluated_days"])],
                ["N190-C 有 R 順延紀錄的批次", len(n190["defer_counts"])],
                ["N190-D 被跳過的批次", len(n190["skipped_batches"])],
            ],
        ),
        GATE_LINE_TEMPLATE.format(n=gate["n177_affected_count"]),
        "",
        "## 判讀圖例",
        "",
        TRIAL_LEGEND,
        "",
    ]

    out += ["## N177-A 受影響標的", "", TRIAL_NOTE, ""]
    rows_a = []
    for a in n177["affected"]:
        first = a["first_s2"]
        trial = a["trial"]
        rows_a.append(
            [
                a["symbol"],
                first["id"],
                first["data_date"],
                first["execution_date"],
                first["shares"],
                first["settled_open_price"],
                first["settled_at"],
                a["later_executed_s2"],
                a["pending_s2"],
                _batches_text(a["eligible_batches"]),
                a["eligible_total"],
                a["verdict"],
                "、".join(f"{x['batch_no']}:{x['shares']}" for x in trial["allocation"])
                if trial
                else "-",
                trial["cash"] if trial else "-",
            ]
        )
    out += _table(
        [
            "標的",
            "第一張 S2 id",
            "依據資料日",
            "預定執行日",
            "股數",
            "成交判定價",
            "settled_at",
            "之後的已成交 S2 張數",
            "待結算的 S2 張數",
            "合格批次（批次:剩餘股數）",
            "合格合計",
            "判讀",
            "試算分配（批次:股數）",
            "試算回補現金",
        ],
        rows_a,
    )

    out += ["## N177-B 重發次數（未受影響的標的）", ""]
    out += _table(
        ["標的", "已成交 S2 張數", "待結算 S2 張數", "最早預定執行日", "最晚預定執行日"],
        [
            [
                r["symbol"],
                r["executed"],
                r["pending"],
                r["earliest_execution_date"],
                r["latest_execution_date"],
            ]
            for r in n177["not_affected_s2"]
        ],
    )

    out += ["## N177-C 黑名單（只列出，不改）", ""]
    out += _table(
        [
            "標的",
            "triggered_on",
            "until",
            "rule_id",
            "第一張 S2 依據資料日",
            "相差交易日數",
            "計數依據",
        ],
        [
            [
                r["symbol"],
                r["triggered_on"],
                r["until"],
                r["rule_id"],
                r["first_s2_data_date"],
                r["trading_day_difference"],
                r["difference_basis"],
            ]
            for r in n177["blacklist"]
        ],
    )

    out += ["## N177-D 帳冊找不到所屬批次的成交列", ""]
    out += _table(
        [
            "id",
            "標的",
            "批次",
            "rule_id",
            "action",
            "股數",
            "預定執行日",
            "成交判定價",
            "股數 × 價（未入帳）",
            "備註",
        ],
        [
            [
                r["id"],
                r["symbol"],
                r["batch_no"],
                r["rule_id"],
                r["action"],
                r["shares"],
                r["execution_date"],
                r["settled_open_price"],
                r["unbooked_amount"],
                r["note"],
            ]
            for r in n177["missing_batch_rows"]
        ],
    )

    out += ["## N177-E 待結算的 S2", ""]
    out += [
        "N-177a 上線後，這些列會依新邏輯結算。若幻影批次已關閉，它們會是零移動。",
        "",
    ]
    out += _table(
        ["id", "標的", "股數", "依據資料日", "預定執行日", "created_at"],
        [
            [
                r["id"],
                r["symbol"],
                r["shares"],
                r["data_date"],
                r["execution_date"],
                r["created_at"],
            ]
            for r in n177["pending_s2"]
        ],
    )

    out += ["## N177-F 受影響批次上的在途賣單", ""]
    out += _table(
        ["id", "標的", "批次", "rule_id", "股數", "預定執行日"],
        [
            [r["id"], r["symbol"], r["batch_no"], r["rule_id"], r["shares"], r["execution_date"]]
            for r in n177["inflight_on_affected"]
        ],
    )

    stats = n190["stats"]
    out += ["## N190-A 停損未評估的候選日", ""]
    out += [
        f"- 範圍：{stats['since'] or '-'} 至 {stats['until']}",
        f"- demo 來源 bar（已排除，只計數）：{stats['demo_bars_excluded'] or '無'}",
        f"- 收盤價無法解析的持有日：{stats['unusable_close_days']}",
        f"- 成本缺漏或為 0 的持有批次日：{stats['unusable_cost_batches']}",
        f"- 規則參數無法解析的持有日：{stats['unusable_params_days']}",
        "",
    ]
    out += _table(
        [
            "標的",
            "批次",
            "資料日",
            "收盤",
            "成本或均成本",
            "收盤 ÷ 成本",
            "門檻值",
            "列入類別",
            "當日本檔有無任何指令列",
            "當日系統有無評估寫入",
            "評估時快取是否已有這根 bar",
            "參數版本",
            "附註",
        ],
        [
            [
                c["symbol"],
                "整檔" if c["batch_no"] is None else c["batch_no"],
                c["data_date"],
                c["close"],
                c["cost"],
                c["close_over_cost"],
                c["threshold"],
                c["category"],
                "有" if c["symbol_has_rows"] else "無",
                "有" if c["system_wrote"] else "無",
                c["cache_had_bar"],
                c["params_version"],
                c["note"],
            ]
            for c in n190["stop_loss_candidates"]
        ],
    )
    out += ["### 持有日數摘要", ""]
    out += _table(
        ["標的", "帳冊持有交易日數", "有本檔指令列的日數", "沒有本檔指令列的日數"],
        [
            [h["symbol"], h["held_days"], h["days_with_symbol_rows"], h["days_without_symbol_rows"]]
            for h in n190["held_summary"]
        ],
    )

    out += ["## N190-B M1 未評估的日子", ""]
    state = n190["m1_state"]
    out += [
        f"- playbook_state fast_market_measured_on：{state['fast_market_measured_on'] or '（無）'}",
        f"- playbook_state defense_active：{state['defense_active'] or '（無）'}",
        f"- playbook_state defense_since：{state['defense_since'] or '（無）'}",
        "",
    ]
    out += _table(
        [
            "資料日",
            "預定執行日",
            "指數狀態",
            "順延批次數",
            "跳過批次數",
            "評估時快取是否已有 ^TWII 的 bar",
            "指令列 id",
        ],
        [
            [
                d["data_date"],
                "、".join(d["execution_dates"]),
                "、".join(d["index_status"]),
                d["deferred_batches"],
                d["skipped_batches"],
                d["index_cache_had_bar"],
                _ids_text(d["line_ids"]),
            ]
            for d in n190["m1_unevaluated_days"]
        ],
    )

    out += ["## N190-C 累計的 R 順延次數", ""]
    out += _table(
        [
            "標的",
            "批次",
            "狀態",
            "defer_count 現值",
            "M1 順延列數",
            "其中 cached_stale",
            "R2 順延列數",
            "R3 跳過列 id",
            "M1 順延佔比",
        ],
        [
            [
                r["symbol"],
                r["batch_no"],
                r["status"],
                r["defer_count"],
                r["m1_defers"],
                r["m1_cached_stale"],
                r["r2_defers"],
                _ids_text(r["r3_skip_ids"]),
                r["m1_share"],
            ]
            for r in n190["defer_counts"]
        ],
    )

    out += ["## N190-D 被跳過的批次", ""]
    out += _table(
        ["標的", "批次", "R3 跳過列 id", "原因類別", "M1 順延數", "其中 cached_stale"],
        [
            [
                r["symbol"],
                r["batch_no"],
                _ids_text(r["r3_skip_ids"]),
                r["reason_category"],
                r["m1_defers"],
                r["m1_cached_stale"],
            ]
            for r in n190["skipped_batches"]
        ],
    )

    if result["diff_vs_previous"] is not None:
        out += ["## 與前次報告的比對", ""]
        out += ["以（標的，第一張 S2 id）為鍵，不同的列不沿用前次的選擇。", ""]
        out += _table(["鍵", "結果"], [[d["key"], d["result"]] for d in result["diff_vs_previous"]])

    out += ["## 已知限制", ""]
    for code in result["limitations"]:
        out.append(f"- {code}：{LIMITATIONS[code]}")
    out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------ guards and CLI


def _same_file(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return a.resolve() == b.resolve()


def inside_git_work_tree(path: Path) -> bool:
    """RC-5: ``path`` or any folder above it holds a ``.git`` entry (folder or file)."""
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def refusal(
    db_path: Path, out_dir: Path, *, backend_dir: Path, env: Mapping[str, str]
) -> str | None:
    """S6: why the run must be refused, or ``None``. The text never echoes a value."""
    production_db = backend_dir / "data" / PRODUCTION_DB_NAME
    production_dirs = [backend_dir / "data"]
    production_dbs = [production_db]
    named = env.get(DB_PATH_ENV_VAR)
    if named:
        production_dbs.append(Path(named))
        production_dirs.append(Path(named).parent)
    if any(_same_file(db_path, p) for p in production_dbs):
        return "refused: --db-path points to the production DB; give it a copy"
    if any(_same_file(out_dir, p) for p in production_dirs):
        return "refused: --out-dir is the production data folder"
    if inside_git_work_tree(out_dir):
        return "refused: --out-dir is inside a git work tree; the report holds holdings and cash"
    return None


def _parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from error


def _ascii(text: object) -> str:
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def _read_previous(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("not a report.json of this tool (schema_version differs)")
    return data


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    now_utc: datetime | None = None,
    today: date | None = None,
    backend_dir: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="n177_n190_backtrack_probe.py",
        description="Read-only N-177 / N-190 probe: detection gate and backtrack list.",
    )
    parser.add_argument("--db-path", required=True, help="a COPY of stock-desk.db")
    parser.add_argument("--out-dir", required=True, help="existing folder for report.md/json")
    parser.add_argument("--since", type=_parse_day, default=None, help="N-190 start YYYY-MM-DD")
    parser.add_argument("--until", type=_parse_day, default=None, help="N-190 end YYYY-MM-DD")
    parser.add_argument("--previous-json", default=None, help="report.json of the earlier run")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    environment = os.environ if env is None else env
    backend = backend_dir if backend_dir is not None else Path(__file__).resolve().parents[1]
    db_path = Path(args.db_path)
    out_dir = Path(args.out_dir)

    reason = refusal(db_path, out_dir, backend_dir=backend, env=environment)
    if reason is None and not out_dir.is_dir():
        reason = "refused: --out-dir does not exist or is not a folder"
    md_path = out_dir / REPORT_MD_NAME
    json_path = out_dir / REPORT_JSON_NAME
    if reason is None and (md_path.exists() or json_path.exists()):
        reason = "refused: report.md or report.json already exists in --out-dir"
    if reason is not None:
        print(reason, file=sys.stderr)
        return EXIT_REFUSED

    previous: dict[str, Any] | None = None
    if args.previous_json is not None:
        try:
            previous = _read_previous(Path(args.previous_json))
        except (OSError, ValueError) as error:
            print(f"cannot read --previous-json: {_ascii(error)}", file=sys.stderr)
            return EXIT_UNREADABLE

    until = args.until or today or date.today()
    try:
        hash_before = sha256_file(db_path)
        with closing(open_read_only(db_path)) as conn:
            snapshot = load(conn, since=args.since, until=until)
        hash_after = sha256_file(db_path)
    except (OSError, sqlite3.Error, ValueError, TypeError) as error:
        print(f"cannot read the DB: {_ascii(error)}", file=sys.stderr)
        return EXIT_UNREADABLE
    if hash_after != hash_before:
        print(
            f"DB file changed during the run: before={hash_before} after={hash_after}",
            file=sys.stderr,
        )
        return EXIT_HASH_CHANGED

    moment = now_utc if now_utc is not None else datetime.now(UTC)
    try:
        result = build_result(
            snapshot,
            db_path=str(db_path.resolve()),
            hash_before=hash_before,
            hash_after=hash_after,
            run_at=moment,
            previous=previous,
        )
        markdown = render_markdown(result)
        json_text = render_json(result)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"cannot build the report ({type(error).__name__}): {_ascii(error)}", file=sys.stderr)
        return EXIT_UNREADABLE
    try:
        with open(md_path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown)
        with open(json_path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(json_text)
    except FileExistsError:
        print("refused: a report file appeared in --out-dir", file=sys.stderr)
        return EXIT_REFUSED
    print(f"n177_n190_backtrack_probe version={SCRIPT_VERSION}")
    print(f"gate_affected_symbols={result['gate']['n177_affected_count']}")
    print(f"report_md={_ascii(md_path.resolve())}")
    print(f"report_json={_ascii(json_path.resolve())}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
