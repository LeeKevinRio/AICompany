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
  TOTAL_DEPLOY, S3 freeze, EMERGENCY_EXIT freeze and the M1 defense flag.
* ``playbook_directives`` -- every line ever produced, with its rules version,
  input provenance and T+1 outcome (風控 required R16).

The split between "decided" and "filled" is deliberate. Rule *state* (pause,
blacklist, freeze, deferral, skip) is applied the moment the rule fires, because
those are decisions about the schedule. Anything that depends on an order
actually filling -- shares, cost, the P1/P2/P3 marks -- is applied only by
:meth:`PlaybookStore.settle`, so a MISSED line (CEO 裁決七) leaves the book
untouched and is re-evaluated the next day.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.data.cache import resolve_db_path
from app.playbook.calendar import TradingCalendar
from app.playbook.models import (
    BatchState,
    Directive,
    PlaybookEvaluation,
    PortfolioState,
    RuleParams,
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
        data_status TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
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

#: Effects that only make sense once an order filled; :meth:`settle` applies
#: them, never :meth:`apply_effects`.
FILL_DEPENDENT_EFFECTS = frozenset(
    {"batch_entered", "batch_reduced", "batch_closed", "p1_done", "p2_done", "p3_marked"}
)


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _day(value: Any) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


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
                     defer_count, scheduled_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        return PortfolioState(
            cash=Decimal(state.get(STATE_CASH, "0")),
            total_deploy=Decimal(state.get(STATE_TOTAL_DEPLOY, "0")),
            freeze_until=_day(state.get(STATE_FREEZE_UNTIL)),
            freeze_reason=state.get(STATE_FREEZE_REASON),
            emergency_until=_day(state.get(STATE_EMERGENCY_UNTIL)),
            defense_active=state.get(STATE_DEFENSE_ACTIVE) == "1",
            defense_since=_day(state.get(STATE_DEFENSE_SINCE)),
        )

    def set_capital(self, *, cash: Decimal, total_deploy: Decimal) -> None:
        """Record the cash pool and the TOTAL_DEPLOY locked for this quarter."""
        self._set_state({STATE_CASH: str(cash), STATE_TOTAL_DEPLOY: str(total_deploy)})

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
        """The newest version whose effective date has arrived (defaults if none)."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload FROM playbook_rule_params WHERE effective_date <= ? "
                "ORDER BY effective_date DESC, version DESC LIMIT 1",
                (on_date.isoformat(),),
            ).fetchone()
        if row is None:
            return RuleParams(effective_date=on_date)
        return RuleParams.model_validate(json.loads(str(row[0])))

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
        """Append every line to the audit log (風控 required R16)."""
        moment = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            for directive in evaluation.directives:
                conn.execute(
                    """
                    INSERT INTO playbook_directives
                        (created_at, rules_version, symbol, batch_no, action, shares, rule_id,
                         rule_summary, data_date, execution_date, reference_price, limit_low,
                         limit_high, data_status, source, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        directive.data_status,
                        directive.source,
                        directive.status,
                    ),
                )

    def directive_log(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM playbook_directives ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def settle(self, directive: Directive) -> None:
        """Apply a settled line to the book: fills move shares, MISSED moves nothing.

        Called with the directive **after** :func:`app.playbook.engine.settle_directive`
        has stamped its status, so this method never re-decides the outcome.
        """
        if directive.status != "executed" or directive.batch_no is None:
            self._mark_schedule(directive)
            return
        batch = self.get_batch(directive.symbol, directive.batch_no)
        if batch is None:
            self._mark_schedule(directive)
            return
        if directive.action == "buy":
            price = directive.reference_price or Decimal("0")
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
        elif directive.action == "sell":
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
