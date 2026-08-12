"""SQLite persistence for everything the playbook has to remember between days.

Six tables in the same database file as the price cache and the position book
(``STOCK_DESK_DB_PATH``), following ``app/positions/store.py``: connections are
opened per operation and closed via ``contextlib.closing``, and every money
column is TEXT so ``Decimal`` round-trips exactly.

* ``playbook_batches`` -- one row per 標的 × 批次: entry date, per-share cost,
  shares, 波段最高收盤, the P1/P2/P3 execution marks and the deferral counter.
* ``playbook_schedule`` -- 批次／預定日／順延次數／狀態 of each queued line.
* ``playbook_rule_params`` -- versioned, dated parameter sets. 鐵律④ lives here:
  :meth:`PlaybookStore.submit_rule_change` can only write a version whose
  effective date is a later day, and :meth:`PlaybookStore.active_params` only
  ever returns one that is already effective.
* ``playbook_blacklist`` -- S2 黑名單 with its 60-trading-day expiry.
* ``playbook_symbols`` -- S1 排程暫停 and 高波動清單 membership.
* ``playbook_state`` -- the single-row portfolio flags: cash, the locked
  TOTAL_DEPLOY, S3 freeze, EMERGENCY_EXIT freeze, the M1 defense flag and the
  rule-set confirmation flag the 歸屬語 reads (風控 R2).
* ``playbook_directives`` -- every line ever produced, with its rules version,
  input provenance and T+1 outcome (風控 required R16).

The split between "decided" and "filled" is deliberate. Rule *state* (pause,
blacklist, freeze, deferral, skip) is applied the moment the rule fires, because
those are decisions about the schedule. Anything that depends on an order
actually filling -- shares, cost, cash, the P1/P2/P3 marks -- is applied only by
:meth:`PlaybookStore.settle`, so a MISSED line (CEO 裁決七) leaves the book
untouched and is re-evaluated the next day.

Settlement is replay-safe. ``playbook_directives`` carries a ``settled`` flag and
:meth:`PlaybookStore.claim_directive` flips it with a conditional ``UPDATE``
before anything reaches the book, so re-running a settlement (the ``/today``
endpoint does it on every call) cannot deduct the same shares or the same cash
twice.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

from app.data.cache import resolve_db_path
from app.playbook.calendar import TradingCalendar
from app.playbook.models import (
    BatchState,
    Directive,
    FastMarketState,
    PlaybookEvaluation,
    PortfolioState,
    RuleParams,
    RuleSetAuthorship,
    StateEffect,
    SymbolState,
)

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS playbook_batches (
        symbol TEXT NOT NULL,
        batch_no INTEGER NOT NULL,
        status TEXT NOT NULL,
        entry_date TEXT,
        cost TEXT,
        shares INTEGER NOT NULL DEFAULT 0,
        remaining_shares INTEGER NOT NULL DEFAULT 0,
        peak_close TEXT,
        p1_done INTEGER NOT NULL DEFAULT 0,
        p2_done INTEGER NOT NULL DEFAULT 0,
        p3_last_date TEXT,
        trailing_active INTEGER NOT NULL DEFAULT 0,
        defer_count INTEGER NOT NULL DEFAULT 0,
        missed_count INTEGER NOT NULL DEFAULT 0,
        scheduled_date TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (symbol, batch_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playbook_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        batch_no INTEGER,
        scheduled_date TEXT NOT NULL,
        defer_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        rule_id TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playbook_rule_params (
        version INTEGER PRIMARY KEY,
        payload TEXT NOT NULL,
        submitted_at TEXT NOT NULL,
        effective_date TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playbook_blacklist (
        symbol TEXT PRIMARY KEY,
        triggered_on TEXT NOT NULL,
        until TEXT NOT NULL,
        rule_id TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playbook_symbols (
        symbol TEXT PRIMARY KEY,
        paused INTEGER NOT NULL DEFAULT 0,
        paused_since TEXT,
        high_volatility INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playbook_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playbook_directives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        rules_version INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        batch_no INTEGER,
        action TEXT NOT NULL,
        shares INTEGER NOT NULL,
        rule_id TEXT NOT NULL,
        rule_summary TEXT NOT NULL,
        data_date TEXT NOT NULL,
        execution_date TEXT NOT NULL,
        reference_price TEXT,
        limit_low TEXT,
        limit_high TEXT,
        limit_note TEXT NOT NULL DEFAULT '',
        data_status TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        settled INTEGER NOT NULL DEFAULT 0,
        settled_at TEXT,
        settled_open_price TEXT
    )
    """,
)

#: Columns added after the first release. Every playbook table is created by
#: ``CREATE TABLE IF NOT EXISTS``, so an existing database file keeps its old
#: shape until these run; ``PRAGMA table_info`` decides, following
#: ``app/positions/store.py``.
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("playbook_batches", "missed_count", "INTEGER NOT NULL DEFAULT 0"),
    ("playbook_directives", "limit_note", "TEXT NOT NULL DEFAULT ''"),
    ("playbook_directives", "settled", "INTEGER NOT NULL DEFAULT 0"),
    ("playbook_directives", "settled_at", "TEXT"),
    ("playbook_directives", "settled_open_price", "TEXT"),
)

_BATCH_COLUMNS = (
    "symbol",
    "batch_no",
    "status",
    "entry_date",
    "cost",
    "shares",
    "remaining_shares",
    "peak_close",
    "p1_done",
    "p2_done",
    "p3_last_date",
    "trailing_active",
    "defer_count",
    "missed_count",
    "scheduled_date",
)

_BATCH_SELECT = ", ".join(_BATCH_COLUMNS)

#: ``playbook_state`` keys. Kept as constants so a typo cannot invent a flag
#: that silently reads back as "off".
STATE_CASH = "cash"
STATE_TOTAL_DEPLOY = "total_deploy"
STATE_FREEZE_UNTIL = "freeze_until"
STATE_FREEZE_REASON = "freeze_reason"
STATE_EMERGENCY_UNTIL = "emergency_until"
STATE_DEFENSE_ACTIVE = "defense_active"
STATE_DEFENSE_SINCE = "defense_since"
#: D-2: when the locked TOTAL_DEPLOY was written and what wrote it.
STATE_TOTAL_DEPLOY_SET_AT = "total_deploy_set_at"
STATE_TOTAL_DEPLOY_SOURCE = "total_deploy_source"
#: 風控 R2/R3 歸屬語: the explicit record that the user adopted a rule set as
#: their own. Only :meth:`PlaybookStore.confirm_rule_set` writes it, and nothing
#: in the engine may. Authorship is never inferred from a date.
STATE_RULE_SET_CONFIRMED_AT = "rule_set_confirmed_at"
STATE_RULE_SET_VERSION = "rule_set_confirmed_version"
#: FM-1: the fast-market verdict, persisted so a day with unusable index data
#: can carry it forward instead of re-deciding from nothing.
STATE_FAST_MARKET_ACTIVE = "fast_market_active"
STATE_FAST_MARKET_VOL = "fast_market_vol"
STATE_FAST_MARKET_MOVES = "fast_market_moves"
STATE_FAST_MARKET_REASON = "fast_market_reason"
STATE_FAST_MARKET_MEASURED_ON = "fast_market_measured_on"

#: The two actions that actually place an order, and so are the only ones with a
#: T+1 outcome to settle. 順延／跳過／無動作 lines are decisions, not orders.
ORDER_ACTIONS: tuple[str, ...] = ("buy", "sell")
_ORDER_ACTION_PLACEHOLDERS = ", ".join("?" for _ in ORDER_ACTIONS)

#: Effects that only make sense once an order filled; :meth:`settle` applies
#: them, never :meth:`apply_effects`.
FILL_DEPENDENT_EFFECTS = frozenset(
    {"batch_entered", "batch_reduced", "batch_closed", "p1_done", "p2_done", "p3_marked"}
)


class PendingDirective(NamedTuple):
    """One logged line still awaiting its T+1 outcome, with its log row id.

    The id is what :meth:`PlaybookStore.claim_directive` locks on, so a caller
    can never settle "the same line" by value and hit a different row.
    """

    directive_id: int
    directive: Directive


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _day(value: Any) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


def _day_or_none(value: Any) -> date | None:
    """``_day`` for a column that may be unreadable rather than absent.

    A stored date that cannot be parsed is a gap, not a date: it comes back as
    ``None`` so the caller states the gap (歸屬語情境 2) instead of crashing or
    substituting today.
    """
    try:
        return _day(value)
    except ValueError:
        return None


def system_default_params(on_date: date) -> RuleParams:
    """The parameter set used before the user has submitted one of their own.

    Isolated behind a name so no caller can mistake it for the user's rules:
    it is an input to the arithmetic, never evidence of authorship (風控 R2,
    覆審 store 預設 fallback 須隔離). :meth:`PlaybookStore.rule_set_authorship`
    is the only answer to "did the user write these".
    """
    return RuleParams(effective_date=on_date)


class PlaybookStore:
    """Read/write access to the playbook's persistent state."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # Callers wrap this in contextlib.closing; see app/positions/store.py.
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for statement in _SCHEMA:
                conn.execute(statement)
            for table, column, definition in _MIGRATIONS:
                existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # --- batches ---------------------------------------------------------

    def ensure_batches(self, symbols: Sequence[str], *, batches_per_target: int) -> None:
        """Create the planned batch rows of every target that has none yet."""
        moment = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            for symbol in symbols:
                for batch_no in range(1, batches_per_target + 1):
                    conn.execute(
                        "INSERT OR IGNORE INTO playbook_batches "
                        "(symbol, batch_no, status, updated_at) VALUES (?, ?, 'planned', ?)",
                        (symbol, batch_no, moment),
                    )

    def list_batches(self) -> list[BatchState]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_BATCH_SELECT} FROM playbook_batches ORDER BY symbol, batch_no"
            ).fetchall()
        return [self._row_to_batch(row) for row in rows]

    @staticmethod
    def _row_to_batch(row: tuple[Any, ...]) -> BatchState:
        (
            symbol,
            batch_no,
            status,
            entry_date,
            cost,
            shares,
            remaining,
            peak,
            p1_done,
            p2_done,
            p3_last,
            trailing,
            defer_count,
            missed_count,
            scheduled,
        ) = row
        return BatchState(
            symbol=str(symbol),
            batch_no=int(batch_no),
            status=status,
            entry_date=_day(entry_date),
            cost=_decimal(cost),
            shares=int(shares),
            remaining_shares=int(remaining),
            peak_close=_decimal(peak),
            p1_done=bool(p1_done),
            p2_done=bool(p2_done),
            p3_last_date=_day(p3_last),
            trailing_active=bool(trailing),
            defer_count=int(defer_count),
            missed_count=int(missed_count),
            scheduled_date=_day(scheduled),
        )

    def save_batch(self, batch: BatchState) -> None:
        """Write one batch row wholesale (insert or replace)."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO playbook_batches
                    (symbol, batch_no, status, entry_date, cost, shares, remaining_shares,
                     peak_close, p1_done, p2_done, p3_last_date, trailing_active,
                     defer_count, missed_count, scheduled_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.symbol,
                    batch.batch_no,
                    batch.status,
                    _iso(batch.entry_date),
                    _text(batch.cost),
                    batch.shares,
                    batch.remaining_shares,
                    _text(batch.peak_close),
                    int(batch.p1_done),
                    int(batch.p2_done),
                    _iso(batch.p3_last_date),
                    int(batch.trailing_active),
                    batch.defer_count,
                    batch.missed_count,
                    _iso(batch.scheduled_date),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_batch(self, symbol: str, batch_no: int) -> BatchState | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_BATCH_SELECT} FROM playbook_batches "
                "WHERE symbol = ? AND batch_no = ?",
                (symbol, batch_no),
            ).fetchone()
        return None if row is None else self._row_to_batch(row)

    def roll_peak_closes(self, closes: Mapping[str, Decimal]) -> None:
        """Advance 波段最高收盤 of every open batch with today's close."""
        for batch in self.list_batches():
            close = closes.get(batch.symbol)
            if batch.status != "open" or close is None:
                continue
            if batch.peak_close is None or close > batch.peak_close:
                self.save_batch(batch.model_copy(update={"peak_close": close}))

    # --- symbol / blacklist state ---------------------------------------

    def symbol_states(self, on_date: date) -> dict[str, SymbolState]:
        with closing(self._connect()) as conn:
            paused_rows = conn.execute(
                "SELECT symbol, paused, paused_since FROM playbook_symbols"
            ).fetchall()
            black_rows = conn.execute(
                "SELECT symbol, until FROM playbook_blacklist WHERE until >= ?",
                (on_date.isoformat(),),
            ).fetchall()
        states: dict[str, SymbolState] = {}
        for symbol, paused, since in paused_rows:
            states[str(symbol)] = SymbolState(
                symbol=str(symbol), paused=bool(paused), paused_since=_day(since)
            )
        for symbol, until in black_rows:
            current = states.get(str(symbol), SymbolState(symbol=str(symbol)))
            states[str(symbol)] = current.model_copy(
                update={"blacklisted": True, "blacklist_until": _day(until)}
            )
        return states

    def set_paused(self, symbol: str, *, paused: bool, on_date: date | None = None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO playbook_symbols (symbol, paused, paused_since) VALUES (?, ?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET paused = excluded.paused, "
                "paused_since = excluded.paused_since",
                (symbol, int(paused), _iso(on_date) if paused else None),
            )

    def blacklist(self, symbol: str, *, triggered_on: date, until: date, rule_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO playbook_blacklist "
                "(symbol, triggered_on, until, rule_id) VALUES (?, ?, ?, ?)",
                (symbol, triggered_on.isoformat(), until.isoformat(), rule_id),
            )

    # --- portfolio state -------------------------------------------------

    def _state_map(self) -> dict[str, str]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT key, value FROM playbook_state").fetchall()
        return {str(key): str(value) for key, value in rows}

    def _set_state(self, values: Mapping[str, str | None]) -> None:
        with closing(self._connect()) as conn, conn:
            for key, value in values.items():
                if value is None:
                    conn.execute("DELETE FROM playbook_state WHERE key = ?", (key,))
                    continue
                conn.execute(
                    "INSERT INTO playbook_state (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def portfolio_state(self) -> PortfolioState:
        """The stored portfolio flags; zero cash / zero deploy until set."""
        state = self._state_map()
        set_at = state.get(STATE_TOTAL_DEPLOY_SET_AT)
        return PortfolioState(
            cash=Decimal(state.get(STATE_CASH, "0")),
            total_deploy=Decimal(state.get(STATE_TOTAL_DEPLOY, "0")),
            total_deploy_set_at=None if set_at is None else datetime.fromisoformat(set_at),
            total_deploy_source=state.get(STATE_TOTAL_DEPLOY_SOURCE),
            freeze_until=_day(state.get(STATE_FREEZE_UNTIL)),
            freeze_reason=state.get(STATE_FREEZE_REASON),
            emergency_until=_day(state.get(STATE_EMERGENCY_UNTIL)),
            defense_active=state.get(STATE_DEFENSE_ACTIVE) == "1",
            defense_since=_day(state.get(STATE_DEFENSE_SINCE)),
        )

    def set_capital(
        self,
        *,
        cash: Decimal,
        total_deploy: Decimal,
        source: str,
        at: datetime | None = None,
    ) -> None:
        """Record the cash pool and the TOTAL_DEPLOY locked for this quarter.

        ``source`` and the timestamp are not optional (CEO 裁決 D-2): a locked
        capital number nobody can date, or trace to the run that wrote it, is not
        auditable. ``at`` defaults to now in UTC, the convention of every other
        timestamp in this file.
        """
        self._set_state(
            {
                STATE_CASH: str(cash),
                STATE_TOTAL_DEPLOY: str(total_deploy),
                STATE_TOTAL_DEPLOY_SET_AT: (at or datetime.now(UTC)).isoformat(),
                STATE_TOTAL_DEPLOY_SOURCE: source,
            }
        )

    def fast_market_state(self) -> FastMarketState | None:
        """The last persisted 快市 verdict, or ``None`` before the first one.

        風控 FM-1: read back so a day whose index data is unusable can carry the
        previous verdict forward instead of deciding 快市 from missing data.
        """
        state = self._state_map()
        if STATE_FAST_MARKET_ACTIVE not in state:
            return None
        vol = state.get(STATE_FAST_MARKET_VOL)
        return FastMarketState(
            active=state[STATE_FAST_MARKET_ACTIVE] == "1",
            annualized_vol_20d=None if vol is None else float(vol),
            large_move_days=int(state.get(STATE_FAST_MARKET_MOVES, "0")),
            reason=state.get(STATE_FAST_MARKET_REASON),
            measured_on=_day(state.get(STATE_FAST_MARKET_MEASURED_ON)),
        )

    def save_fast_market(self, state: FastMarketState, *, measured_on: date) -> None:
        """Persist a verdict that was actually measured; carried ones are skipped.

        A carried-forward verdict is not a new measurement, so writing it back
        would keep moving ``measured_on`` forward and hide how old the last real
        reading is.
        """
        if state.carried_forward:
            return
        self._set_state(
            {
                STATE_FAST_MARKET_ACTIVE: "1" if state.active else "0",
                STATE_FAST_MARKET_VOL: (
                    None
                    if state.annualized_vol_20d is None
                    else str(state.annualized_vol_20d)
                ),
                STATE_FAST_MARKET_MOVES: str(state.large_move_days),
                STATE_FAST_MARKET_REASON: state.reason,
                STATE_FAST_MARKET_MEASURED_ON: measured_on.isoformat(),
            }
        )

    def set_cash(self, cash: Decimal) -> None:
        self._set_state({STATE_CASH: str(cash)})

    def freeze(self, *, until: date, reason: str) -> None:
        self._set_state({STATE_FREEZE_UNTIL: until.isoformat(), STATE_FREEZE_REASON: reason})

    def freeze_emergency(self, *, until: date) -> None:
        self._set_state({STATE_EMERGENCY_UNTIL: until.isoformat()})

    def set_defense(self, *, active: bool, since: date | None) -> None:
        self._set_state(
            {
                STATE_DEFENSE_ACTIVE: "1" if active else "0",
                STATE_DEFENSE_SINCE: _iso(since) if active else None,
            }
        )

    # --- rule parameters (鐵律④) ----------------------------------------

    def active_params(self, on_date: date) -> RuleParams:
        """The newest version whose effective date has arrived.

        Falls back to :func:`system_default_params` when the user has never
        submitted one. The fallback is a *calculation* input only: it says
        nothing about who wrote the rules, and callers that speak to the user
        must ask :meth:`rule_set_authorship` instead of reading ownership out of
        this value (覆審: 預設 fallback 須隔離).
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload FROM playbook_rule_params WHERE effective_date <= ? "
                "ORDER BY effective_date DESC, version DESC LIMIT 1",
                (on_date.isoformat(),),
            ).fetchone()
        if row is None:
            return system_default_params(on_date)
        return RuleParams.model_validate(json.loads(str(row[0])))

    def rule_set_authorship(self, on_date: date) -> RuleSetAuthorship:
        """Who authored the rules in force on ``on_date`` (風控 R2 歸屬語).

        Two explicit records count, and only these two: the confirmation flag
        written by :meth:`confirm_rule_set`, and a parameter version the user
        submitted (a 修改紀錄 is an authorship record too). Neither is a date
        inference -- :meth:`active_params` returning a default is not evidence of
        anything, which is exactly why that fallback is isolated.

        An authored rule set whose 生效日 cannot be read comes back with
        ``rule_set_date=None`` (歸屬語情境 2) rather than with a guessed date.
        """
        state = self._state_map()
        confirmed_version = state.get(STATE_RULE_SET_VERSION)
        confirmed = STATE_RULE_SET_CONFIRMED_AT in state
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT version, effective_date FROM playbook_rule_params "
                "WHERE effective_date <= ? ORDER BY effective_date DESC, version DESC LIMIT 1",
                (on_date.isoformat(),),
            ).fetchone()
            total = conn.execute("SELECT COUNT(*) FROM playbook_rule_params").fetchone()
        submitted = total is not None and int(total[0]) > 0
        if not confirmed and not submitted:
            return RuleSetAuthorship(user_authored=False)
        version = int(row[0]) if row is not None else None
        if version is None and confirmed_version is not None:
            version = int(confirmed_version)
        return RuleSetAuthorship(
            user_authored=True,
            version=version,
            rule_set_date=None if row is None else _day_or_none(row[1]),
        )

    def confirm_rule_set(
        self, params: RuleParams, *, confirmed_at: datetime | None = None
    ) -> None:
        """Record that the user adopted ``params`` as their own rule set.

        This is the one write that makes the playbook produce directives at all
        (歸屬語情境 1): before it, the module holds a system default and says so.
        It is a user action by definition, so no engine path calls it.
        """
        moment = (confirmed_at or datetime.now(UTC)).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO playbook_rule_params "
                "(version, payload, submitted_at, effective_date, status) VALUES (?, ?, ?, ?, ?)",
                (
                    params.version,
                    params.model_dump_json(),
                    moment,
                    params.effective_date.isoformat(),
                    "confirmed",
                ),
            )
        self._set_state(
            {
                STATE_RULE_SET_CONFIRMED_AT: moment,
                STATE_RULE_SET_VERSION: str(params.version),
            }
        )

    def next_version(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT MAX(version) FROM playbook_rule_params").fetchone()
        current = row[0] if row is not None else None
        return 1 if current is None else int(current) + 1

    def submit_rule_change(self, params: RuleParams) -> None:
        """Record a parameter version as pending until its effective date.

        The effective date is decided by the caller
        (:func:`app.playbook.service.request_rule_change`), which is the only
        place allowed to compute it, and is always a later trading day.
        """
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO playbook_rule_params "
                "(version, payload, submitted_at, effective_date, status) VALUES (?, ?, ?, ?, ?)",
                (
                    params.version,
                    params.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                    params.effective_date.isoformat(),
                    "pending",
                ),
            )

    def pending_rule_changes(self, on_date: date) -> list[RuleParams]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM playbook_rule_params WHERE effective_date > ? "
                "ORDER BY version ASC",
                (on_date.isoformat(),),
            ).fetchall()
        return [RuleParams.model_validate(json.loads(str(row[0]))) for row in rows]

    # --- effects, schedule and the directive log -------------------------

    def apply_effects(
        self, effects: Iterable[StateEffect], *, data_date: date, calendar: TradingCalendar
    ) -> None:
        """Persist every schedule-state effect; fills are left to :meth:`settle`."""
        for effect in effects:
            if effect.kind in FILL_DEPENDENT_EFFECTS:
                continue
            if effect.kind == "pause_symbol" and effect.symbol is not None:
                self.set_paused(effect.symbol, paused=True, on_date=data_date)
            elif effect.kind == "resume_symbol" and effect.symbol is not None:
                self.set_paused(effect.symbol, paused=False)
            elif effect.kind == "blacklist" and effect.symbol is not None:
                days = effect.value or 0
                self.blacklist(
                    effect.symbol,
                    triggered_on=data_date,
                    until=calendar.shift(data_date, days),
                    rule_id="S2",
                )
            elif effect.kind == "freeze_portfolio":
                self.freeze(
                    until=calendar.shift(data_date, effect.value or 0), reason=effect.note
                )
            elif effect.kind == "defense_on":
                self.set_defense(active=True, since=data_date)
            elif effect.kind == "defense_off":
                self.set_defense(active=False, since=None)
            elif effect.kind == "emergency_exit":
                self.freeze_emergency(until=calendar.shift(data_date, effect.value or 0))
            elif effect.kind == "defer_increment" and effect.symbol is not None:
                self._update_batch(
                    effect.symbol, effect.batch_no, {"defer_count": effect.value or 0}
                )
            elif effect.kind == "defer_reset" and effect.symbol is not None:
                for batch in self.list_batches():
                    if batch.symbol == effect.symbol and batch.defer_count:
                        self.save_batch(batch.model_copy(update={"defer_count": 0}))
            elif effect.kind == "batch_skipped" and effect.symbol is not None:
                self._update_batch(effect.symbol, effect.batch_no, {"status": "skipped"})
            elif effect.kind == "trailing_on" and effect.symbol is not None:
                self._update_batch(effect.symbol, effect.batch_no, {"trailing_active": True})

    def _update_batch(
        self, symbol: str, batch_no: int | None, changes: Mapping[str, Any]
    ) -> None:
        if batch_no is None:
            return
        batch = self.get_batch(symbol, batch_no)
        if batch is None:
            return
        self.save_batch(batch.model_copy(update=dict(changes)))

    def record_schedule(self, evaluation: PlaybookEvaluation) -> None:
        """Log the queued line of every directive (批次／預定日／順延次數／狀態)."""
        moment = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            for directive in evaluation.directives:
                batch = (
                    None
                    if directive.batch_no is None
                    else self.get_batch(directive.symbol, directive.batch_no)
                )
                conn.execute(
                    "INSERT INTO playbook_schedule "
                    "(symbol, batch_no, scheduled_date, defer_count, status, rule_id, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        directive.symbol,
                        directive.batch_no,
                        directive.execution_date.isoformat(),
                        0 if batch is None else batch.defer_count,
                        directive.status,
                        directive.rule_id,
                        moment,
                    ),
                )

    def record_directives(self, evaluation: PlaybookEvaluation) -> None:
        """Append every line to the audit log (風控 required R16).

        A line that places no order (順延／跳過／無動作) is written already
        ``settled``: there is no T+1 outcome coming for it, so leaving it in the
        settlement queue would make the queue lie about what is outstanding.
        """
        moment = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            for directive in evaluation.directives:
                conn.execute(
                    """
                    INSERT INTO playbook_directives
                        (created_at, rules_version, symbol, batch_no, action, shares, rule_id,
                         rule_summary, data_date, execution_date, reference_price, limit_low,
                         limit_high, limit_note, data_status, source, status, settled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        moment,
                        evaluation.rules_version,
                        directive.symbol,
                        directive.batch_no,
                        directive.action,
                        directive.shares,
                        directive.rule_id,
                        directive.rule_summary,
                        directive.data_date.isoformat(),
                        directive.execution_date.isoformat(),
                        _text(directive.reference_price),
                        _text(directive.limit_low),
                        _text(directive.limit_high),
                        directive.limit_note,
                        directive.data_status,
                        directive.source,
                        directive.status,
                        int(directive.action not in ORDER_ACTIONS),
                    ),
                )

    def directive_log(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM playbook_directives ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_directives(self, *, on_or_before: date | None = None) -> list[PendingDirective]:
        """Every logged line still waiting for its T+1 outcome, oldest first.

        ``on_or_before`` limits the result to lines whose 預定執行日 has arrived,
        which is what a settlement run on a given day should look at: a line
        scheduled for tomorrow has no opening price yet and is not "pending
        settlement", it is simply not due.

        Only 買進／賣出 lines are returned. 順延, 跳過 and 無動作 lines place no
        order, so they have no T+1 outcome to stamp; treating them as settleable
        would let a 順延 line count as a MISSED retry (CEO 裁決 E-2) it never
        made. :meth:`record_directives` marks them settled on the way in.
        """
        query = (
            "SELECT id, symbol, batch_no, action, shares, rule_id, rule_summary, data_date, "
            "execution_date, reference_price, limit_low, limit_high, limit_note, data_status, "
            "source, status FROM playbook_directives WHERE settled = 0 AND status = 'pending' "
            f"AND action IN ({_ORDER_ACTION_PLACEHOLDERS})"
        )
        params: tuple[str, ...] = ORDER_ACTIONS
        if on_or_before is not None:
            query += " AND execution_date <= ?"
            params = (*ORDER_ACTIONS, on_or_before.isoformat())
        with closing(self._connect()) as conn:
            rows = conn.execute(query + " ORDER BY id ASC", params).fetchall()
        return [
            PendingDirective(
                directive_id=int(row[0]),
                directive=Directive(
                    symbol=str(row[1]),
                    batch_no=None if row[2] is None else int(row[2]),
                    action=row[3],
                    shares=int(row[4]),
                    rule_id=row[5],
                    rule_summary=str(row[6]),
                    data_date=date.fromisoformat(str(row[7])),
                    execution_date=date.fromisoformat(str(row[8])),
                    reference_price=_decimal(row[9]),
                    limit_low=_decimal(row[10]),
                    limit_high=_decimal(row[11]),
                    limit_note=str(row[12] or ""),
                    data_status=str(row[13]),
                    source=str(row[14]),
                    status=row[15],
                ),
            )
            for row in rows
        ]

    def claim_directive(self, directive_id: int, *, status: str, open_price: Decimal) -> bool:
        """Claim one log row for settlement; ``False`` when it was already taken.

        This is the replay guard. The claim is a single conditional ``UPDATE``
        (``settled = 0`` in the ``WHERE``), so two settlement runs over the same
        day cannot both reach the book: the second one changes no rows, gets
        ``False`` back and leaves the shares alone. The book is only touched
        after a successful claim, never before it.
        """
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE playbook_directives SET settled = 1, settled_at = ?, "
                "settled_open_price = ?, status = ? WHERE id = ? AND settled = 0",
                (datetime.now(UTC).isoformat(), str(open_price), status, directive_id),
            )
            return cursor.rowcount == 1

    def settle(self, directive: Directive, *, fill_price: Decimal | None = None) -> None:
        """Apply a settled line to the book: fills move shares, MISSED moves nothing.

        Called with the directive **after** :func:`app.playbook.engine.settle_directive`
        has stamped its status, so this method never re-decides the outcome.

        ``fill_price`` is the 開盤價 the line actually filled at; the batch cost
        and the cash movement are both taken from it, because that is the number
        the money moved at. Without one (a caller replaying a line by hand) the
        參考價 stands in, which is the only other price the line carries.

        Cash moves here and nowhere else: a buy takes ``price × shares`` out of
        the pool and a sell puts it back, so 鐵律① reads a cash balance that has
        actually advanced rather than the opening figure forever.
        """
        if directive.status == "missed" and directive.batch_no is not None:
            # CEO 裁決 E-2: a MISSED line moves no shares, but it is not free --
            # the retry counter is what the R3-aligned ceiling reads.
            batch = self.get_batch(directive.symbol, directive.batch_no)
            if batch is not None:
                self.save_batch(
                    batch.model_copy(update={"missed_count": batch.missed_count + 1})
                )
        if directive.status != "executed" or directive.batch_no is None:
            self._mark_schedule(directive)
            return
        batch = self.get_batch(directive.symbol, directive.batch_no)
        if batch is None:
            self._mark_schedule(directive)
            return
        price = fill_price if fill_price is not None else directive.reference_price
        price = price or Decimal("0")
        if directive.action == "buy":
            batch = batch.model_copy(
                update={
                    "status": "open",
                    "entry_date": directive.execution_date,
                    "cost": price,
                    "shares": directive.shares,
                    "remaining_shares": directive.shares,
                    "peak_close": price,
                }
            )
            self.set_cash(self.portfolio_state().cash - price * Decimal(directive.shares))
        elif directive.action == "sell":
            moved = min(batch.remaining_shares, directive.shares)
            self.set_cash(self.portfolio_state().cash + price * Decimal(moved))
            remaining = max(0, batch.remaining_shares - directive.shares)
            changes: dict[str, Any] = {
                "remaining_shares": remaining,
                "status": "closed" if remaining == 0 else "open",
            }
            if directive.rule_id == "P1":
                changes["p1_done"] = True
            elif directive.rule_id == "P2":
                changes["p2_done"] = True
                changes["trailing_active"] = True
            elif directive.rule_id == "P3":
                changes["p3_last_date"] = directive.data_date
            batch = batch.model_copy(update=changes)
        self.save_batch(batch)
        self._mark_schedule(directive)

    def _mark_schedule(self, directive: Directive) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE playbook_schedule SET status = ?, updated_at = ? "
                "WHERE symbol = ? AND scheduled_date = ? AND rule_id = ? "
                "AND (batch_no IS ? OR batch_no = ?)",
                (
                    directive.status,
                    datetime.now(UTC).isoformat(),
                    directive.symbol,
                    directive.execution_date.isoformat(),
                    directive.rule_id,
                    directive.batch_no,
                    directive.batch_no,
                ),
            )

    def list_schedule(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM playbook_schedule ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]
