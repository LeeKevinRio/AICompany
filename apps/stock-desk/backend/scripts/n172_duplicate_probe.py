"""N-172 offline probe: duplicated playbook directive rows and what they did to the book.

Run from ``apps/stock-desk/backend`` against a *copy* of the DB::

    uv run --frozen python scripts/n172_duplicate_probe.py --db-path <copy of stock-desk.db>

Background (tech-architect, 2026-10-31, N-172 assessment section 2 and its addendum
section 3): ``GET /today`` re-runs the evaluation on every call and every call writes its
lines again, so one decision can sit in ``playbook_directives`` several times. One
evaluation stamps one shared ``created_at`` on every row it writes, so a decision written
twice shows up as one decision identity with more than one ``created_at``.

Decision identity (K1): ``(symbol, batch_no, rule_id, action, execution_date)``. SQLite's
``GROUP BY`` puts NULL ``batch_no`` values (S2) in one group, which is the ``IS`` match.

Categories (each is printed under its own heading):

* ``D-A``  -- K1 group, rule R1 buy, every row executed. The only category with an
  estimated overcharge: ``(k - 1) x shares x settled_open_price``, printed only when every
  guard below passes; otherwise the group is printed as needing manual review, with the
  reasons and without an amount.
* ``D-A'`` -- K1 group, rule R1 buy, every row missed: ``missed_count`` excess ``k - 1``.
* ``D-B``  -- one ``(symbol, batch_no)`` with more than one executed R1 buy on different
  execution dates; plus pending R1 buys on a batch that already has an executed R1 buy on
  another execution date. Disclosure only.
* ``D-C``  -- K1 group whose action is defer or skip (R2 / R3 / M1). Disclosure only.
* ``D-D``  -- K1 group of P1 / P2 (one-third reduction) / P3 sells. Disclosure only.
* ``D-E``  -- K1 group of S1 / S2 / P2 trailing-exit sells, and EMERGENCY sells grouped by
  ``(symbol, batch_no)`` across dates. Counts only.
* ``D-F``  -- any duplicate group above that still holds unsettled rows.
* ``D-G``  -- order rows still pending after their execution date, with the
  ``price_bars_cache`` facts for that symbol: a bar on the execution date or not, and
  bars after it or not. The probe does not say whether a gap is a holiday or missing data.

D-A guards (any hit means "needs manual review", no amount):
the same ``created_at`` repeated inside the group; more than one shares value or more than
one settled price; a missing or unparseable settled price; no batch row, or batch
``shares`` different from the row shares; ``total_deploy_set_at`` absent, unparseable, or
later than the group's first ``settled_at`` (cash was re-entered afterwards).

Output is facts only: categories, counts, ids, dates, shares, prices and the D-A estimate.
It states no conclusion and no advice.

Read-only by construction: the file is opened with SQLite's ``mode=ro`` URI plus
``PRAGMA query_only=ON``, it is never created, and only SELECT statements are sent. Output
goes to stdout only. When SQLite reads a WAL-mode database it may leave its own ``-wal`` /
``-shm`` sidecar files next to it; the database file itself is byte-identical afterwards.
Standard library only: no ``app`` import, no network.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCRIPT_VERSION = "1"
DEFAULT_DB_PATH = "./data/stock-desk.db"
DB_PATH_ENV_VAR = "STOCK_DESK_DB_PATH"

#: Detail text that only the P2 trailing-exit line carries (``engine.py``, 移動停利出清).
#: The one-third P2 reduction line says 「餘轉移動停利」 instead, so it never matches.
P2_TRAILING_MARKER = "移動停利觸發"

# ---------------------------------------------------------------- SQL (SELECT only)

#: tech-architect query 1, verbatim plus ORDER BY: every K1 group with more than one row.
K1_GROUPS_SQL = """
SELECT symbol, batch_no, rule_id, action, execution_date, COUNT(*) n,
       COUNT(DISTINCT created_at) calls, SUM(settled=0) unsettled,
       SUM(status='executed') executed, SUM(status='missed') missed,
       COUNT(DISTINCT shares) share_variants, COUNT(DISTINCT settled_open_price) price_variants,
       GROUP_CONCAT(id) ids
FROM playbook_directives WHERE rule_id NOT IN ('EMERGENCY','REBALANCE')
GROUP BY symbol, batch_no, rule_id, action, execution_date HAVING COUNT(*) > 1
ORDER BY symbol, batch_no, execution_date, rule_id, action
"""

#: tech-architect query 2 plus the number of distinct execution dates and ORDER BY.
R1_EXECUTED_PER_BATCH_SQL = """
SELECT symbol, batch_no, COUNT(*) n, GROUP_CONCAT(id) ids,
       COUNT(DISTINCT execution_date) dates
FROM playbook_directives WHERE rule_id='R1' AND action='buy' AND status='executed'
GROUP BY symbol, batch_no HAVING COUNT(*) > 1
ORDER BY symbol, batch_no
"""

#: Pending R1 buys on a batch that already has an executed R1 buy on another date (D-B).
R1_PENDING_ON_FILLED_BATCH_SQL = """
SELECT p.id FROM playbook_directives p
WHERE p.rule_id='R1' AND p.action='buy' AND p.settled=0 AND p.status='pending'
  AND EXISTS (
    SELECT 1 FROM playbook_directives e
    WHERE e.rule_id='R1' AND e.action='buy' AND e.status='executed'
      AND e.symbol=p.symbol AND e.batch_no IS p.batch_no
      AND e.execution_date <> p.execution_date
  )
ORDER BY p.id
"""

#: tech-architect 4xx assessment Q2-bis, plus distinct dates and ORDER BY.
EMERGENCY_GROUPS_SQL = """
SELECT symbol, batch_no, COUNT(*) n, SUM(settled=0) unsettled, GROUP_CONCAT(id) ids,
       COUNT(DISTINCT execution_date) dates
FROM playbook_directives WHERE rule_id='EMERGENCY' AND action='sell'
GROUP BY symbol, batch_no HAVING COUNT(*) > 1
ORDER BY symbol, batch_no
"""

#: tech-architect query 3, verbatim.
STATE_SQL = """
SELECT key, value FROM playbook_state
WHERE key IN ('cash','total_deploy','total_deploy_set_at','total_deploy_source')
"""

#: Every directive row with the columns the categories print (parameter: P2 marker).
DIRECTIVE_ROWS_SQL = """
SELECT id, created_at, symbol, batch_no, rule_id, action, shares, execution_date, status,
       settled, settled_at, settled_open_price, instr(rule_summary, ?) > 0
FROM playbook_directives ORDER BY id
"""

BATCHES_SQL = """
SELECT symbol, batch_no, status, shares, remaining_shares, defer_count, missed_count
FROM playbook_batches
"""

#: Order rows still pending after their execution date (parameter: as-of date) -- D-G.
PENDING_PAST_SQL = """
SELECT id FROM playbook_directives
WHERE settled = 0 AND status = 'pending' AND action IN ('buy', 'sell')
  AND execution_date < ?
ORDER BY execution_date, id
"""

TABLE_EXISTS_SQL = "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?"

#: Bar dates of one symbol in any market (parameter: symbol) -- D-G.
BAR_DATES_SQL = "SELECT DISTINCT trade_date FROM price_bars_cache WHERE symbol = ?"

STATE_KEYS = ("cash", "total_deploy", "total_deploy_set_at", "total_deploy_source")


# ---------------------------------------------------------------- facts as read


@dataclass(frozen=True)
class Row:
    """One ``playbook_directives`` row, values as stored."""

    id: int
    created_at: str
    symbol: str
    batch_no: int | None
    rule_id: str
    action: str
    shares: int
    execution_date: str
    status: str
    settled: int
    settled_at: str | None
    settled_open_price: str | None
    p2_trailing: bool


@dataclass(frozen=True)
class Batch:
    status: str
    shares: int
    remaining_shares: int
    defer_count: int
    missed_count: int


@dataclass(frozen=True)
class K1Group:
    """One K1 identity with more than one row (aggregates straight from SQL)."""

    symbol: str
    batch_no: int | None
    rule_id: str
    action: str
    execution_date: str
    n: int
    calls: int
    unsettled: int
    executed: int
    missed: int
    share_variants: int
    price_variants: int
    ids: list[int]


@dataclass(frozen=True)
class BatchGroup:
    """Rows of one ``(symbol, batch_no)`` across dates (D-B executed R1, EMERGENCY)."""

    symbol: str
    batch_no: int | None
    n: int
    unsettled: int
    dates: int
    ids: list[int]


@dataclass(frozen=True)
class PastPending:
    row: Row
    bar_table_present: bool
    bar_on_execution_date: bool
    bars_after: int
    first_bar_after: str | None
    latest_bar: str | None


@dataclass
class Snapshot:
    """Everything the SELECTs returned; classification works on this alone."""

    rows: dict[int, Row]
    batches: dict[tuple[str, int], Batch]
    state: dict[str, str]
    k1_groups: list[K1Group]
    r1_executed_per_batch: list[BatchGroup]
    r1_pending_on_filled: list[int]
    emergency_groups: list[BatchGroup]
    past_pending: list[PastPending]
    as_of: date


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open ``path`` read-only; refuses a missing file instead of creating one."""
    if not path.is_file():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
    except BaseException:
        conn.close()
        raise
    return conn


def _ids(text: object) -> list[int]:
    return sorted(int(part) for part in str(text).split(",") if part.strip())


def _batch_no(value: object) -> int | None:
    return None if value is None else int(str(value))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(TABLE_EXISTS_SQL, (name,)).fetchone() is not None


def load(conn: sqlite3.Connection, *, as_of: date) -> Snapshot:
    """Read every fact the report needs; only SELECT statements are issued."""
    if not _table_exists(conn, "playbook_directives"):
        raise sqlite3.OperationalError("no such table: playbook_directives")
    rows: dict[int, Row] = {}
    for r in conn.execute(DIRECTIVE_ROWS_SQL, (P2_TRAILING_MARKER,)):
        rows[int(r[0])] = Row(
            id=int(r[0]),
            created_at=str(r[1]),
            symbol=str(r[2]),
            batch_no=_batch_no(r[3]),
            rule_id=str(r[4]),
            action=str(r[5]),
            shares=int(r[6]),
            execution_date=str(r[7]),
            status=str(r[8]),
            settled=int(r[9]),
            settled_at=None if r[10] is None else str(r[10]),
            settled_open_price=None if r[11] is None else str(r[11]),
            p2_trailing=bool(r[12]),
        )
    batches: dict[tuple[str, int], Batch] = {}
    if _table_exists(conn, "playbook_batches"):
        for b in conn.execute(BATCHES_SQL):
            batches[(str(b[0]), int(b[1]))] = Batch(
                status=str(b[2]),
                shares=int(b[3]),
                remaining_shares=int(b[4]),
                defer_count=int(b[5]),
                missed_count=int(b[6]),
            )
    state: dict[str, str] = {}
    if _table_exists(conn, "playbook_state"):
        state = {str(k): str(v) for k, v in conn.execute(STATE_SQL)}
    k1_groups = [
        K1Group(
            symbol=str(g[0]),
            batch_no=_batch_no(g[1]),
            rule_id=str(g[2]),
            action=str(g[3]),
            execution_date=str(g[4]),
            n=int(g[5]),
            calls=int(g[6]),
            unsettled=int(g[7]),
            executed=int(g[8]),
            missed=int(g[9]),
            share_variants=int(g[10]),
            price_variants=int(g[11]),
            ids=_ids(g[12]),
        )
        for g in conn.execute(K1_GROUPS_SQL)
    ]
    r1_executed = [
        BatchGroup(str(g[0]), _batch_no(g[1]), int(g[2]), 0, int(g[4]), _ids(g[3]))
        for g in conn.execute(R1_EXECUTED_PER_BATCH_SQL)
    ]
    r1_pending_on_filled = [int(r[0]) for r in conn.execute(R1_PENDING_ON_FILLED_BATCH_SQL)]
    emergency = [
        BatchGroup(str(g[0]), _batch_no(g[1]), int(g[2]), int(g[3]), int(g[5]), _ids(g[4]))
        for g in conn.execute(EMERGENCY_GROUPS_SQL)
    ]
    past_ids = [int(r[0]) for r in conn.execute(PENDING_PAST_SQL, (as_of.isoformat(),))]
    bars_present = _table_exists(conn, "price_bars_cache")
    bar_dates: dict[str, list[str]] = {}
    past: list[PastPending] = []
    for directive_id in past_ids:
        row = rows[directive_id]
        if not bars_present:
            past.append(PastPending(row, False, False, 0, None, None))
            continue
        if row.symbol not in bar_dates:
            bar_dates[row.symbol] = sorted(
                str(d[0]) for d in conn.execute(BAR_DATES_SQL, (row.symbol,))
            )
        dates = bar_dates[row.symbol]
        after = [d for d in dates if d > row.execution_date]
        past.append(
            PastPending(
                row=row,
                bar_table_present=True,
                bar_on_execution_date=row.execution_date in dates,
                bars_after=len(after),
                first_bar_after=after[0] if after else None,
                latest_bar=dates[-1] if dates else None,
            )
        )
    return Snapshot(
        rows=rows,
        batches=batches,
        state=state,
        k1_groups=k1_groups,
        r1_executed_per_batch=r1_executed,
        r1_pending_on_filled=r1_pending_on_filled,
        emergency_groups=emergency,
        past_pending=past,
        as_of=as_of,
    )


# ---------------------------------------------------------------- classification


@dataclass
class DAResult:
    """One R1-buy K1 group: computable (amount set) or manual review (reasons set)."""

    group: K1Group
    shares: int | None = None
    price: Decimal | None = None
    first_settled_at: str | None = None
    amount: Decimal | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class Classified:
    d_a: list[DAResult]
    d_a_prime: list[DAResult]
    r1_mixed: list[DAResult]
    d_b: list[BatchGroup]
    d_b_same_date_only: int
    d_b_pending: list[int]
    d_c: list[K1Group]
    d_d: list[K1Group]
    d_e: list[K1Group]
    d_e_emergency: list[BatchGroup]
    other: list[tuple[K1Group, str]]
    d_f: list[tuple[str, list[int]]]


def _instant(text: str | None) -> datetime | None:
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _batch_of(snapshot: Snapshot, symbol: str, batch_no: int | None) -> Batch | None:
    return None if batch_no is None else snapshot.batches.get((symbol, batch_no))


def _evaluate_r1_buy(group: K1Group, snapshot: Snapshot) -> DAResult:
    """Apply the D-A guards to one executed R1-buy K1 group."""
    members = [snapshot.rows[i] for i in group.ids]
    result = DAResult(group=group)
    reasons = result.reasons
    if group.calls != group.n:
        reasons.append(
            f"same created_at repeated (rows={group.n} distinct_created_at={group.calls})"
        )
    if group.share_variants != 1:
        reasons.append(f"shares not uniform (variants={group.share_variants})")
    else:
        result.shares = members[0].shares
    if group.price_variants > 1:
        reasons.append(f"settled_open_price not uniform (variants={group.price_variants})")
    elif any(m.settled_open_price is None for m in members):
        reasons.append("settled_open_price missing on some row")
    else:
        text = members[0].settled_open_price
        try:
            price = Decimal(str(text))
        except InvalidOperation:
            reasons.append(f"settled_open_price unparseable ({text!r})")
        else:
            if price.is_finite():
                result.price = price
            else:
                reasons.append(f"settled_open_price unparseable ({text!r})")
    batch = _batch_of(snapshot, group.symbol, group.batch_no)
    if batch is None:
        reasons.append("no playbook_batches row for this batch")
    elif result.shares is not None and batch.shares != result.shares:
        reasons.append(f"batch shares {batch.shares} != row shares {result.shares}")
    stamps = [(_instant(m.settled_at), m.settled_at) for m in members]
    if any(instant is None for instant, _ in stamps):
        reasons.append("settled_at missing or unparseable on some row")
    else:
        first: datetime | None = None
        try:
            first, result.first_settled_at = min(
                ((instant, text) for instant, text in stamps if instant is not None),
                key=lambda pair: pair[0],
            )
        except TypeError:
            reasons.append("settled_at values not comparable (mixed time zone awareness)")
        set_at_text = snapshot.state.get("total_deploy_set_at")
        set_at = _instant(set_at_text)
        if set_at_text is None:
            reasons.append("total_deploy_set_at absent")
        elif set_at is None:
            reasons.append(f"total_deploy_set_at unparseable ({set_at_text!r})")
        elif first is not None:
            try:
                later = set_at > first
            except TypeError:
                reasons.append("total_deploy_set_at and settled_at not comparable")
            else:
                if later:
                    reasons.append(
                        f"total_deploy_set_at {set_at_text} is later than first settled_at "
                        f"{result.first_settled_at} (total_deploy_source="
                        f"{snapshot.state.get('total_deploy_source', '(absent)')})"
                    )
    if not reasons and result.shares is not None and result.price is not None:
        result.amount = (group.n - 1) * result.shares * result.price
    return result


def classify(snapshot: Snapshot) -> Classified:
    out = Classified([], [], [], [], 0, [], [], [], [], [], [], [])
    for group in snapshot.k1_groups:
        members = [snapshot.rows[i] for i in group.ids]
        if group.rule_id == "R1" and group.action == "buy":
            if group.executed == group.n:
                out.d_a.append(_evaluate_r1_buy(group, snapshot))
            elif group.missed == group.n:
                result = DAResult(group=group)
                if group.calls != group.n:
                    result.reasons.append(
                        f"same created_at repeated (rows={group.n} "
                        f"distinct_created_at={group.calls})"
                    )
                out.d_a_prime.append(result)
            else:
                result = DAResult(group=group)
                result.reasons.append(
                    f"not all executed and not all missed (executed={group.executed} "
                    f"missed={group.missed} other={group.n - group.executed - group.missed})"
                )
                out.r1_mixed.append(result)
        elif group.action in ("defer", "skip"):
            out.d_c.append(group)
        elif group.action == "sell" and group.rule_id in ("P1", "P2", "P3"):
            trailing = {m.p2_trailing for m in members}
            if group.rule_id == "P2" and trailing == {True, False}:
                out.other.append((group, "P2 rows mix trailing-exit and one-third reduction"))
            elif group.rule_id == "P2" and trailing == {True}:
                out.d_e.append(group)
            else:
                out.d_d.append(group)
        elif group.action == "sell" and group.rule_id in ("S1", "S2"):
            out.d_e.append(group)
        else:
            out.other.append((group, "no category for this rule/action"))
        if group.unsettled:
            unsettled = [m.id for m in members if m.settled == 0]
            out.d_f.append((f"K1 {_key(group)}", unsettled))
    for bg in snapshot.r1_executed_per_batch:
        if bg.dates > 1:
            out.d_b.append(bg)
        else:
            out.d_b_same_date_only += 1
    out.d_b_pending = list(snapshot.r1_pending_on_filled)
    out.d_e_emergency = list(snapshot.emergency_groups)
    for bg in snapshot.emergency_groups:
        if bg.unsettled:
            unsettled = [i for i in bg.ids if snapshot.rows[i].settled == 0]
            out.d_f.append(
                (f"EMERGENCY sell symbol={bg.symbol} batch_no={_no(bg.batch_no)}", unsettled)
            )
    return out


# ---------------------------------------------------------------- output


def _no(batch_no: int | None) -> str:
    return "NULL" if batch_no is None else str(batch_no)


def _ids_text(ids: Sequence[int]) -> str:
    return ",".join(str(i) for i in ids) if ids else "-"


def _key(group: K1Group) -> str:
    return (
        f"symbol={group.symbol} batch_no={_no(group.batch_no)} rule={group.rule_id} "
        f"action={group.action} execution_date={group.execution_date}"
    )


def _counts(group: K1Group) -> str:
    return (
        f"rows={group.n} distinct_created_at={group.calls} executed={group.executed} "
        f"missed={group.missed} unsettled={group.unsettled}"
    )


def _batch_text(batch: Batch | None) -> str:
    if batch is None:
        return "batch: (no playbook_batches row)"
    return (
        f"batch: status={batch.status} shares={batch.shares} "
        f"remaining_shares={batch.remaining_shares} defer_count={batch.defer_count} "
        f"missed_count={batch.missed_count}"
    )


def _row_text(row: Row) -> str:
    return (
        f"id={row.id} created_at={row.created_at} execution_date={row.execution_date} "
        f"status={row.status} settled={row.settled} shares={row.shares} "
        f"settled_open_price={row.settled_open_price or '-'} settled_at={row.settled_at or '-'}"
    )


def fingerprint_of(data: bytes) -> str:
    """SHA-256 of ``data`` with line endings normalised to LF (git autocrlf safe)."""
    return hashlib.sha256(b"\n".join(data.splitlines()) + b"\n").hexdigest()


def script_fingerprint() -> str:
    """:func:`fingerprint_of` this very file."""
    return fingerprint_of(Path(__file__).read_bytes())


def render(snapshot: Snapshot, *, db_path: Path, now_utc: datetime, fingerprint: str) -> str:
    c = classify(snapshot)
    lines: list[str] = []
    out = lines.append
    manual = "NEEDS_MANUAL_REVIEW (需人工判讀)"

    out("N-172 duplicate-directive probe (read-only: SQLite mode=ro + PRAGMA query_only=ON)")
    out(f"script_version: {SCRIPT_VERSION}")
    out(f"script_sha256_lf: {fingerprint}")
    out(
        "script_commit: not embedded; run: "
        "git log -1 --format=%H -- scripts/n172_duplicate_probe.py"
    )
    out(f"db_path: {db_path}")
    out(f"run_at_utc: {now_utc.astimezone(UTC).isoformat()}")
    out(f"as_of (D-G lists pending rows with execution_date < as_of): {snapshot.as_of}")
    out("")
    out("== playbook_state ==")
    for key in STATE_KEYS:
        out(f"{key}: {snapshot.state.get(key, '(absent)')}")
    out("")

    computable = [r for r in c.d_a if r.amount is not None]
    total = sum((r.amount for r in computable if r.amount is not None), Decimal("0"))
    out("== Summary ==")
    out(f"playbook_directives rows: {len(snapshot.rows)}")
    out(f"K1 duplicate groups (EMERGENCY and REBALANCE excluded): {len(snapshot.k1_groups)}")
    out(
        f"D-A: groups={len(c.d_a)} computable={len(computable)} "
        f"manual_review={len(c.d_a) - len(computable)} "
        f"estimated_overcharge_total(computable only)={total}"
    )
    out(f"D-A': groups={len(c.d_a_prime)}")
    out(f"R1 buy groups neither all executed nor all missed: {len(c.r1_mixed)}")
    out(
        f"D-B: batches={len(c.d_b)} pending_r1_on_filled_batch={len(c.d_b_pending)} "
        f"(same-execution_date-only batches, covered by D-A: {c.d_b_same_date_only})"
    )
    out(f"D-C: groups={len(c.d_c)}")
    out(f"D-D: groups={len(c.d_d)}")
    out(f"D-E: k1_groups={len(c.d_e)} emergency_groups={len(c.d_e_emergency)}")
    out(f"other duplicate groups: {len(c.other)}")
    out(f"D-F: groups_with_unsettled_rows={len(c.d_f)}")
    out(f"D-G: pending_rows_past_execution_date={len(snapshot.past_pending)}")
    out("")

    out("== D-A: R1 buy, same K1, all executed ==")
    out("estimate = (rows - 1) x shares x settled_open_price; printed only when no guard hits")
    out(f"count: {len(c.d_a)}")
    for r in c.d_a:
        out(f"[D-A] {_key(r.group)}")
        out(f"  {_counts(r.group)} ids={_ids_text(r.group.ids)}")
        out(
            f"  shares={r.shares if r.shares is not None else '-'} "
            f"settled_open_price={r.price if r.price is not None else '-'} "
            f"first_settled_at={r.first_settled_at or '-'}"
        )
        out(f"  {_batch_text(_batch_of(snapshot, r.group.symbol, r.group.batch_no))}")
        if r.amount is not None and r.shares is not None:
            out(f"  estimated_overcharge = ({r.group.n} - 1) x {r.shares} x {r.price} = {r.amount}")
        else:
            out(f"  {manual}")
            for reason in r.reasons:
                out(f"    reason: {reason}")
    out("")

    out("== D-A': R1 buy, same K1, all missed ==")
    out(f"count: {len(c.d_a_prime)}")
    for r in c.d_a_prime:
        batch = _batch_of(snapshot, r.group.symbol, r.group.batch_no)
        out(f"[D-A'] {_key(r.group)}")
        out(f"  {_counts(r.group)} ids={_ids_text(r.group.ids)}")
        out(f"  {_batch_text(batch)}")
        if r.reasons:
            out(f"  {manual}")
            for reason in r.reasons:
                out(f"    reason: {reason}")
        else:
            out(f"  missed_count_excess = {r.group.n} - 1 = {r.group.n - 1}")
    out("")

    out("== R1 buy, same K1, neither all executed nor all missed ==")
    out(f"count: {len(c.r1_mixed)}")
    for r in c.r1_mixed:
        out(f"[R1-mixed] {_key(r.group)}")
        out(f"  {_counts(r.group)} ids={_ids_text(r.group.ids)}")
        for i in r.group.ids:
            out(f"    {_row_text(snapshot.rows[i])}")
        out(f"  {_batch_text(_batch_of(snapshot, r.group.symbol, r.group.batch_no))}")
        out(f"  {manual}")
        for reason in r.reasons:
            out(f"    reason: {reason}")
    out("")

    out("== D-B: one batch, more than one executed R1 buy, different execution dates ==")
    out("disclosure only; no amount")
    out(f"count: {len(c.d_b)}")
    for bg in c.d_b:
        out(
            f"[D-B] symbol={bg.symbol} batch_no={_no(bg.batch_no)} executed_r1_rows={bg.n} "
            f"distinct_execution_dates={bg.dates} ids={_ids_text(bg.ids)}"
        )
        for i in bg.ids:
            out(f"    {_row_text(snapshot.rows[i])}")
        out(f"  {_batch_text(_batch_of(snapshot, bg.symbol, bg.batch_no))}")
    out("-- pending R1 buy rows on a batch that already has an executed R1 buy on another date --")
    out(f"count: {len(c.d_b_pending)}")
    for i in c.d_b_pending:
        row = snapshot.rows[i]
        out(f"[D-B-pending] symbol={row.symbol} batch_no={_no(row.batch_no)}")
        out(f"    {_row_text(row)}")
        out(f"  {_batch_text(_batch_of(snapshot, row.symbol, row.batch_no))}")
    out("")

    out("== D-C: defer / skip, same K1 ==")
    out("disclosure only")
    out(f"count: {len(c.d_c)}")
    for g in c.d_c:
        out(f"[D-C] {_key(g)}")
        out(f"  {_counts(g)} ids={_ids_text(g.ids)}")
        out(f"  {_batch_text(_batch_of(snapshot, g.symbol, g.batch_no))}")
    out("")

    out("== D-D: P1 / P2 one-third / P3 sell, same K1 ==")
    out("disclosure only; no amount")
    out(f"count: {len(c.d_d)}")
    for g in c.d_d:
        out(f"[D-D] {_key(g)}")
        out(f"  {_counts(g)} executed_beyond_first={max(g.executed - 1, 0)} ids={_ids_text(g.ids)}")
        for i in g.ids:
            out(f"    {_row_text(snapshot.rows[i])}")
        out(f"  {_batch_text(_batch_of(snapshot, g.symbol, g.batch_no))}")
    out("")

    out("== D-E: S1 / S2 / P2 trailing-exit sell (same K1), EMERGENCY sell (same batch) ==")
    out("counts only")
    out(f"count: k1_groups={len(c.d_e)} emergency_groups={len(c.d_e_emergency)}")
    for g in c.d_e:
        variant = " (P2 trailing-exit)" if g.rule_id == "P2" else ""
        out(f"[D-E] {_key(g)}{variant}")
        out(f"  {_counts(g)} ids={_ids_text(g.ids)}")
    for bg in c.d_e_emergency:
        out(
            f"[D-E EMERGENCY] symbol={bg.symbol} batch_no={_no(bg.batch_no)} rows={bg.n} "
            f"unsettled={bg.unsettled} distinct_execution_dates={bg.dates} "
            f"ids={_ids_text(bg.ids)}"
        )
    out("")

    out("== Other duplicate K1 groups (no category) ==")
    out(f"count: {len(c.other)}")
    for g, why in c.other:
        out(f"[other] {_key(g)}")
        out(f"  {_counts(g)} ids={_ids_text(g.ids)} note: {why}")
    out("")

    out("== D-F: duplicate groups that still hold unsettled rows ==")
    out(f"count: {len(c.d_f)}")
    for label, unsettled in c.d_f:
        out(f"[D-F] {label} unsettled_ids={_ids_text(unsettled)}")
        for i in unsettled:
            out(f"    {_row_text(snapshot.rows[i])}")
    out("")

    out("== D-G: order rows still pending after their execution date ==")
    out("bar facts read from price_bars_cache by symbol (any market); no holiday judgement")
    out(f"count: {len(snapshot.past_pending)}")
    for p in snapshot.past_pending:
        row = p.row
        out(
            f"[D-G] id={row.id} symbol={row.symbol} batch_no={_no(row.batch_no)} "
            f"rule={row.rule_id} action={row.action} shares={row.shares} "
            f"execution_date={row.execution_date} created_at={row.created_at}"
        )
        if not p.bar_table_present:
            out("  price_bars_cache: (table absent)")
            continue
        out(
            f"  bar_on_execution_date={'yes' if p.bar_on_execution_date else 'no'} "
            f"bars_after_execution_date={p.bars_after} "
            f"first_bar_after={p.first_bar_after or '-'} latest_bar={p.latest_bar or '-'}"
        )
        if not p.bar_on_execution_date and p.bars_after > 0:
            out("  fact: no bar on execution_date and later bars exist")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI


def _parse_as_of(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from error


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    now_utc: datetime | None = None,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="n172_duplicate_probe.py",
        description="Read-only N-172 probe: duplicated playbook directive rows.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=f"DB file (a copy); default ${DB_PATH_ENV_VAR} or {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--as-of",
        type=_parse_as_of,
        default=None,
        help="D-G cutoff date YYYY-MM-DD (default: this machine's local date)",
    )
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        # A redirected Windows console may pick a legacy code page; never die mid-report.
        sys.stdout.reconfigure(errors="backslashreplace")
    environment = os.environ if env is None else env
    path = Path(args.db_path or environment.get(DB_PATH_ENV_VAR, DEFAULT_DB_PATH))
    as_of: date = args.as_of or today or date.today()
    try:
        with closing(open_read_only(path)) as conn:
            snapshot = load(conn, as_of=as_of)
    except (FileNotFoundError, sqlite3.Error) as error:
        print(f"cannot read the DB: {error}", file=sys.stderr)
        return 2
    moment = now_utc if now_utc is not None else datetime.now(UTC)
    print(
        render(snapshot, db_path=path.resolve(), now_utc=moment, fingerprint=script_fingerprint())
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
