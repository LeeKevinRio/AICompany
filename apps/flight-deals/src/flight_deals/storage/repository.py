"""All SQL lives here. Maps rows to domain objects and small record types."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

from flight_deals.domain.models import (
    DatePair,
    NotificationKind,
    PriceKind,
    PriceQuote,
    Watch,
    WatchSpec,
    WatchStatus,
)
from flight_deals.domain.timeutil import parse_utc_iso, to_utc_iso
from flight_deals.storage.db import Database


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _pd(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _ts(value: datetime | None) -> str | None:
    return to_utc_iso(value) if value else None


def _pts(value: str | None) -> datetime | None:
    return parse_utc_iso(value) if value else None


def _req_ts(value: str) -> datetime:
    return parse_utc_iso(value)


# watch.airlines is the only list-valued column: upper-case codes, sorted, comma
# separated, NULL for "any airline" (ADR-0002 FD-5 Decision 1). These two functions are
# the single place that format is written and read.
def airlines_to_db(codes: Sequence[str]) -> str | None:
    unique = sorted({c.strip().upper() for c in codes if c.strip()})
    return ",".join(unique) if unique else None


def airlines_from_db(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(sorted({c for c in value.split(",") if c}))


@dataclass(frozen=True)
class ObservationRecord:
    id: int
    scan_run_id: int
    watch_id: int
    watch_revision: int
    source: str
    price_kind: PriceKind
    depart_date: date
    return_date: date | None
    amount_minor: int
    currency: str
    as_of: datetime
    as_of_basis: str
    fetched_at: datetime
    carrier: str | None
    stops: int | None
    duration_minutes: int | None
    depart_time: str | None = None


@dataclass(frozen=True)
class ScanRunRecord:
    id: int
    watch_id: int
    watch_revision: int
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    sampled_pairs: list[DatePair]
    total_pairs: int
    limit_reached: bool
    global_limit_reached: bool
    query_results: list[dict[str, Any]]
    queries_used: int
    error_summary: str | None


@dataclass(frozen=True)
class AlertStateRecord:
    last_notified_amount_minor: int | None
    last_notified_at: datetime | None
    armed: bool


@dataclass(frozen=True)
class NotificationItemRecord:
    item_key: str
    depart_date: date
    return_date: date | None
    amount_minor: int
    currency: str
    reasons: tuple[str, ...]
    carrier: str | None
    fetched_at: datetime


@dataclass(frozen=True)
class NotificationRecord:
    id: int
    watch_id: int | None
    watch_name: str | None
    kind: str
    rule: str | None
    price_kind: str | None
    dedupe_key: str
    status: str
    attempts: int
    message_text: str
    created_at: datetime
    sent_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class SourceHealthRecord:
    source: str
    enabled: bool
    breaker_state: str
    consecutive_failures: int
    open_until: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class SchedulerEventRecord:
    at: datetime
    kind: str
    detail: str | None


def _watch(row: sqlite3.Row) -> Watch:
    spec = WatchSpec(
        name=row["name"],
        origin=row["origin"],
        destination=row["destination"],
        trip_type=row["trip_type"],
        date_mode=row["date_mode"],
        depart_date=_pd(row["depart_date"]),
        return_date=_pd(row["return_date"]),
        window_start=_pd(row["window_start"]),
        window_end=_pd(row["window_end"]),
        min_trip_days=row["min_trip_days"],
        max_trip_days=row["max_trip_days"],
        max_stops=row["max_stops"],
        budget_amount_minor=row["budget_amount_minor"],
        currency=row["currency"],
        notify_on_new_low=bool(row["notify_on_new_low"]),
        adults=row["adults"],
        children=row["children"],
        cabin=row["cabin"],
        airlines=airlines_from_db(row["airlines"]),
        dep_hour_from=row["dep_hour_from"],
        dep_hour_to=row["dep_hour_to"],
    )
    return Watch(
        id=row["id"],
        spec=spec,
        status=row["status"],
        revision=row["revision"],
        sample_offset=row["sample_offset"],
        last_scanned_at=_pts(row["last_scanned_at"]),
        consecutive_failed_scans=row["consecutive_failed_scans"],
        created_at=_req_ts(row["created_at"]),
        updated_at=_req_ts(row["updated_at"]),
    )


def _observation(row: sqlite3.Row) -> ObservationRecord:
    return ObservationRecord(
        id=row["id"],
        scan_run_id=row["scan_run_id"],
        watch_id=row["watch_id"],
        watch_revision=row["watch_revision"],
        source=row["source"],
        price_kind=row["price_kind"],
        depart_date=date.fromisoformat(row["depart_date"]),
        return_date=_pd(row["return_date"]),
        amount_minor=row["amount_minor"],
        currency=row["currency"],
        as_of=_req_ts(row["as_of"]),
        as_of_basis=row["as_of_basis"],
        fetched_at=_req_ts(row["fetched_at"]),
        carrier=row["carrier"],
        stops=row["stops"],
        duration_minutes=row["duration_minutes"],
        depart_time=row["depart_time"],
    )


def _scan_run(row: sqlite3.Row) -> ScanRunRecord:
    return ScanRunRecord(
        id=row["id"],
        watch_id=row["watch_id"],
        watch_revision=row["watch_revision"],
        trigger=row["trigger"],
        started_at=_req_ts(row["started_at"]),
        finished_at=_pts(row["finished_at"]),
        status=row["status"],
        sampled_pairs=[DatePair.from_json(p) for p in json.loads(row["sampled_pairs"])],
        total_pairs=row["total_pairs"],
        limit_reached=bool(row["limit_reached"]),
        global_limit_reached=bool(row["global_limit_reached"]),
        query_results=json.loads(row["query_results"]),
        queries_used=row["queries_used"],
        error_summary=row["error_summary"],
    )


def _notification(row: sqlite3.Row) -> NotificationRecord:
    keys = row.keys()
    return NotificationRecord(
        id=row["id"],
        watch_id=row["watch_id"],
        watch_name=row["watch_name"] if "watch_name" in keys else None,
        kind=row["kind"],
        rule=row["rule"],
        price_kind=row["price_kind"],
        dedupe_key=row["dedupe_key"],
        status=row["status"],
        attempts=row["attempts"],
        message_text=row["message_text"],
        created_at=_req_ts(row["created_at"]),
        sent_at=_pts(row["sent_at"]),
        last_error=row["last_error"],
    )


def _spec_values(spec: WatchSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "origin": spec.origin,
        "destination": spec.destination,
        "trip_type": spec.trip_type,
        "date_mode": spec.date_mode,
        "depart_date": _d(spec.depart_date),
        "return_date": _d(spec.return_date),
        "window_start": _d(spec.window_start),
        "window_end": _d(spec.window_end),
        "min_trip_days": spec.min_trip_days,
        "max_trip_days": spec.max_trip_days,
        "max_stops": spec.max_stops,
        "budget_amount_minor": spec.budget_amount_minor,
        "currency": spec.currency,
        "notify_on_new_low": int(spec.notify_on_new_low),
        "adults": spec.adults,
        "children": spec.children,
        "cabin": spec.cabin,
        "airlines": airlines_to_db(spec.airlines),
        "dep_hour_from": spec.dep_hour_from,
        "dep_hour_to": spec.dep_hour_to,
    }


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- watches -------------------------------------------------------------

    def insert_watch(self, spec: WatchSpec, now: datetime) -> int:
        values = _spec_values(spec)
        values.update(created_at=to_utc_iso(now), updated_at=to_utc_iso(now))
        cols = ", ".join(values)
        marks = ", ".join(f":{k}" for k in values)
        with self.db.connect() as conn:
            cur = conn.execute(f"INSERT INTO watch ({cols}) VALUES ({marks})", values)
            return int(cast(int, cur.lastrowid))

    def update_watch_spec(
        self,
        watch_id: int,
        spec: WatchSpec,
        *,
        revision: int,
        status: WatchStatus,
        reset_progress: bool,
        now: datetime,
    ) -> None:
        values = _spec_values(spec)
        values.update(revision=revision, status=status, updated_at=to_utc_iso(now), id=watch_id)
        sets = [f"{k} = :{k}" for k in values if k != "id"]
        if reset_progress:
            sets += ["sample_offset = 0", "consecutive_failed_scans = 0"]
        with self.db.connect() as conn:
            conn.execute(f"UPDATE watch SET {', '.join(sets)} WHERE id = :id", values)

    def get_watch(self, watch_id: int) -> Watch | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM watch WHERE id = ?", (watch_id,)).fetchone()
        return _watch(row) if row else None

    def list_watches_with_last_results(self) -> list[tuple[Watch, list[dict[str, Any]]]]:
        """Every watch with its latest finished scan run's per-pair results (one query)."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT w.*, (SELECT s.query_results FROM scan_run s"
                "  WHERE s.watch_id = w.id AND s.finished_at IS NOT NULL"
                "  ORDER BY s.id DESC LIMIT 1) AS last_query_results"
                " FROM watch w ORDER BY w.id"
            ).fetchall()
        return [
            (_watch(r), json.loads(r["last_query_results"]) if r["last_query_results"] else [])
            for r in rows
        ]

    def list_watches(self) -> list[Watch]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM watch ORDER BY id").fetchall()
        return [_watch(r) for r in rows]

    def set_watch_status(self, watch_id: int, status: WatchStatus, now: datetime) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE watch SET status = ?, updated_at = ? WHERE id = ?",
                (status, to_utc_iso(now), watch_id),
            )

    def delete_watch(self, watch_id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM watch WHERE id = ?", (watch_id,))
            return cur.rowcount > 0

    def record_watch_scan(
        self,
        watch_id: int,
        *,
        scanned_at: datetime,
        sample_offset: int,
        consecutive_failed_scans: int,
        status: WatchStatus,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE watch SET last_scanned_at = ?, sample_offset = ?,"
                " consecutive_failed_scans = ?, status = ? WHERE id = ?",
                (
                    to_utc_iso(scanned_at),
                    sample_offset,
                    consecutive_failed_scans,
                    status,
                    watch_id,
                ),
            )

    # ---- scan runs -----------------------------------------------------------

    def insert_scan_run(
        self,
        *,
        watch_id: int,
        revision: int,
        trigger: str,
        started_at: datetime,
        sampled_pairs: Sequence[DatePair],
        total_pairs: int,
        limit_reached: bool,
    ) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO scan_run (watch_id, watch_revision, trigger, started_at, status,"
                " sampled_pairs, total_pairs, limit_reached)"
                " VALUES (?, ?, ?, ?, 'running', ?, ?, ?)",
                (
                    watch_id,
                    revision,
                    trigger,
                    to_utc_iso(started_at),
                    json.dumps([p.as_json() for p in sampled_pairs]),
                    total_pairs,
                    int(limit_reached),
                ),
            )
            return int(cast(int, cur.lastrowid))

    def finish_scan_run(
        self,
        scan_run_id: int,
        *,
        finished_at: datetime,
        status: str,
        query_results: list[dict[str, Any]],
        queries_used: int,
        global_limit_reached: bool,
        error_summary: str | None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE scan_run SET finished_at = ?, status = ?, query_results = ?,"
                " queries_used = ?, global_limit_reached = ?, error_summary = ? WHERE id = ?",
                (
                    to_utc_iso(finished_at),
                    status,
                    json.dumps(query_results, ensure_ascii=False),
                    queries_used,
                    int(global_limit_reached),
                    error_summary,
                    scan_run_id,
                ),
            )

    def queries_used_since(self, since: datetime) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(queries_used), 0) AS n FROM scan_run WHERE started_at >= ?",
                (to_utc_iso(since),),
            ).fetchone()
        return int(row["n"])

    def count_failed_scan_runs_since(self, since: datetime) -> int:
        """Scan runs that ended ``failed`` and started at or after ``since`` (one COUNT)."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM scan_run WHERE status = 'failed' AND started_at >= ?",
                (to_utc_iso(since),),
            ).fetchone()
        return int(row["n"])

    def scan_runs_for_watch(self, watch_id: int, limit: int = 20) -> list[ScanRunRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scan_run WHERE watch_id = ? ORDER BY started_at DESC, id DESC"
                " LIMIT ?",
                (watch_id, limit),
            ).fetchall()
        return [_scan_run(r) for r in rows]

    def latest_finished_scan_runs(self) -> dict[int, ScanRunRecord]:
        """Most recent finished scan run per watch."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT s.* FROM scan_run s JOIN ("
                "  SELECT watch_id, MAX(id) AS max_id FROM scan_run"
                "  WHERE finished_at IS NOT NULL GROUP BY watch_id"
                ") m ON s.id = m.max_id"
            ).fetchall()
        return {r["watch_id"]: _scan_run(r) for r in rows}

    def latest_scan_run_for_watch(self, watch_id: int) -> ScanRunRecord | None:
        """Most recently created scan run of one watch (running or finished)."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scan_run WHERE watch_id = ? ORDER BY id DESC LIMIT 1",
                (watch_id,),
            ).fetchone()
        return _scan_run(row) if row else None

    def latest_scan_run(self) -> ScanRunRecord | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scan_run ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return _scan_run(row) if row else None

    # ---- observations --------------------------------------------------------

    def insert_observation(
        self, *, scan_run_id: int, watch_id: int, revision: int, quote: PriceQuote
    ) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
                " price_kind, depart_date, return_date, amount_minor, currency, as_of,"
                " as_of_basis, fetched_at, carrier, stops, duration_minutes, depart_time)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scan_run_id,
                    watch_id,
                    revision,
                    quote.source,
                    quote.price_kind,
                    quote.depart_date.isoformat(),
                    _d(quote.return_date),
                    quote.amount_minor,
                    quote.currency,
                    to_utc_iso(quote.as_of),
                    quote.as_of_basis,
                    to_utc_iso(quote.fetched_at),
                    quote.carrier,
                    quote.stops,
                    quote.duration_minutes,
                    quote.depart_time,
                ),
            )
            return int(cast(int, cur.lastrowid))

    def min_amount(
        self,
        *,
        watch_id: int,
        revision: int,
        price_kind: str,
        currency: str,
        exclude_scan_run_id: int | None = None,
    ) -> int | None:
        sql = (
            "SELECT MIN(amount_minor) AS m FROM price_observation WHERE watch_id = ?"
            " AND watch_revision = ? AND price_kind = ? AND currency = ?"
        )
        params: list[Any] = [watch_id, revision, price_kind, currency]
        if exclude_scan_run_id is not None:
            sql += " AND scan_run_id != ?"
            params.append(exclude_scan_run_id)
        with self.db.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["m"]) if row["m"] is not None else None

    def observations_for_watch(
        self, watch_id: int, *, revision: int | None = None, limit: int | None = None
    ) -> list[ObservationRecord]:
        sql = "SELECT * FROM price_observation WHERE watch_id = ?"
        params: list[Any] = [watch_id]
        if revision is not None:
            sql += " AND watch_revision = ?"
            params.append(revision)
        sql += " ORDER BY fetched_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_observation(r) for r in rows]

    def old_revision_observations(
        self, watch_id: int, current_revision: int, limit: int = 50
    ) -> list[ObservationRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM price_observation WHERE watch_id = ? AND watch_revision < ?"
                " ORDER BY fetched_at DESC, id DESC LIMIT ?",
                (watch_id, current_revision, limit),
            ).fetchall()
        return [_observation(r) for r in rows]

    def count_observations(self, watch_id: int | None = None) -> int:
        with self.db.connect() as conn:
            if watch_id is None:
                row = conn.execute("SELECT COUNT(*) AS n FROM price_observation").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM price_observation WHERE watch_id = ?", (watch_id,)
                ).fetchone()
        return int(row["n"])

    # ---- alert state ---------------------------------------------------------

    def get_alert_state(self, watch_id: int, price_kind: str) -> AlertStateRecord:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM alert_state WHERE watch_id = ? AND price_kind = ?",
                (watch_id, price_kind),
            ).fetchone()
        if row is None:
            return AlertStateRecord(None, None, True)
        return AlertStateRecord(
            row["last_notified_amount_minor"], _pts(row["last_notified_at"]), bool(row["armed"])
        )

    def save_alert_state(self, watch_id: int, price_kind: str, state: AlertStateRecord) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO alert_state (watch_id, price_kind, last_notified_amount_minor,"
                " last_notified_at, armed) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(watch_id, price_kind) DO UPDATE SET"
                " last_notified_amount_minor = excluded.last_notified_amount_minor,"
                " last_notified_at = excluded.last_notified_at, armed = excluded.armed",
                (
                    watch_id,
                    price_kind,
                    state.last_notified_amount_minor,
                    _ts(state.last_notified_at),
                    int(state.armed),
                ),
            )

    def reset_alert_state(self, watch_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM alert_state WHERE watch_id = ?", (watch_id,))

    # ---- notifications -------------------------------------------------------

    def insert_notification(
        self,
        *,
        watch_id: int | None,
        kind: NotificationKind,
        rule: str | None,
        price_kind: str | None,
        observation_id: int | None,
        channel: str,
        dedupe_key: str,
        message_text: str,
        created_at: datetime,
        items: Iterable[NotificationItemRecord] = (),
    ) -> int | None:
        """Insert a pending notification; returns None if ``dedupe_key`` already exists."""
        try:
            with self.db.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO notification (watch_id, kind, rule, price_kind, observation_id,"
                    " channel, dedupe_key, status, attempts, message_text, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)",
                    (
                        watch_id,
                        kind,
                        rule,
                        price_kind,
                        observation_id,
                        channel,
                        dedupe_key,
                        message_text,
                        to_utc_iso(created_at),
                    ),
                )
                notification_id = int(cast(int, cur.lastrowid))
                conn.executemany(
                    "INSERT INTO notification_item (notification_id, item_key, depart_date,"
                    " return_date, amount_minor, currency, reasons, carrier, fetched_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            notification_id,
                            i.item_key,
                            i.depart_date.isoformat(),
                            _d(i.return_date),
                            i.amount_minor,
                            i.currency,
                            ",".join(i.reasons),
                            i.carrier,
                            to_utc_iso(i.fetched_at),
                        )
                        for i in items
                    ],
                )
                return notification_id
        except sqlite3.IntegrityError as exc:
            if "dedupe_key" in str(exc) or "UNIQUE" in str(exc):
                return None
            raise

    def update_notification(
        self,
        notification_id: int,
        *,
        status: str,
        attempts: int,
        sent_at: datetime | None,
        last_error: str | None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE notification SET status = ?, attempts = ?, sent_at = ?, last_error = ?"
                " WHERE id = ?",
                (status, attempts, _ts(sent_at), last_error, notification_id),
            )

    def get_notification(self, notification_id: int) -> NotificationRecord | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT n.*, w.name AS watch_name FROM notification n"
                " LEFT JOIN watch w ON w.id = n.watch_id WHERE n.id = ?",
                (notification_id,),
            ).fetchone()
        return _notification(row) if row else None

    def get_notification_by_key(self, dedupe_key: str) -> NotificationRecord | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM notification WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
        return _notification(row) if row else None

    def notified_item_keys(self, watch_id: int, price_kind: str) -> set[str]:
        """Item keys already sent or still in flight (pending/failed) for this watch."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT i.item_key FROM notification_item i"
                " JOIN notification n ON n.id = i.notification_id"
                " WHERE n.watch_id = ? AND n.price_kind = ?"
                " AND n.status IN ('pending', 'sent', 'failed')",
                (watch_id, price_kind),
            ).fetchall()
        return {r["item_key"] for r in rows}

    def notification_items(self, notification_id: int) -> list[NotificationItemRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_item WHERE notification_id = ? ORDER BY amount_minor",
                (notification_id,),
            ).fetchall()
        return [
            NotificationItemRecord(
                item_key=r["item_key"],
                depart_date=date.fromisoformat(r["depart_date"]),
                return_date=_pd(r["return_date"]),
                amount_minor=r["amount_minor"],
                currency=r["currency"],
                reasons=tuple(x for x in r["reasons"].split(",") if x),
                carrier=r["carrier"],
                fetched_at=_req_ts(r["fetched_at"]),
            )
            for r in rows
        ]

    def retryable_notifications(self, max_attempts: int) -> list[NotificationRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT n.*, w.name AS watch_name FROM notification n"
                " LEFT JOIN watch w ON w.id = n.watch_id"
                " WHERE n.kind IN ('price_alert', 'ops_source_failure', 'daily_digest')"
                " AND n.status IN ('pending', 'failed') AND n.attempts < ?"
                " ORDER BY n.id",
                (max_attempts,),
            ).fetchall()
        return [_notification(r) for r in rows]

    def list_notifications(self, limit: int = 200) -> list[NotificationRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT n.*, w.name AS watch_name FROM notification n"
                " LEFT JOIN watch w ON w.id = n.watch_id ORDER BY n.created_at DESC, n.id DESC"
                " LIMIT ?",
                (limit,),
            ).fetchall()
        return [_notification(r) for r in rows]

    # ---- source health -------------------------------------------------------

    def get_source_health(self, source: str) -> SourceHealthRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM source_health WHERE source = ?", (source,)).fetchone()
        return self._health(row) if row else None

    @staticmethod
    def _health(row: sqlite3.Row) -> SourceHealthRecord:
        return SourceHealthRecord(
            source=row["source"],
            enabled=bool(row["enabled"]),
            breaker_state=row["breaker_state"],
            consecutive_failures=row["consecutive_failures"],
            open_until=_pts(row["open_until"]),
            last_success_at=_pts(row["last_success_at"]),
            last_failure_at=_pts(row["last_failure_at"]),
            last_error=row["last_error"],
        )

    def save_source_health(self, record: SourceHealthRecord) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO source_health (source, enabled, breaker_state, consecutive_failures,"
                " open_until, last_success_at, last_failure_at, last_error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(source) DO UPDATE SET enabled = excluded.enabled,"
                " breaker_state = excluded.breaker_state,"
                " consecutive_failures = excluded.consecutive_failures,"
                " open_until = excluded.open_until, last_success_at = excluded.last_success_at,"
                " last_failure_at = excluded.last_failure_at, last_error = excluded.last_error",
                (
                    record.source,
                    int(record.enabled),
                    record.breaker_state,
                    record.consecutive_failures,
                    _ts(record.open_until),
                    _ts(record.last_success_at),
                    _ts(record.last_failure_at),
                    record.last_error,
                ),
            )

    def list_source_health(self) -> list[SourceHealthRecord]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM source_health ORDER BY source").fetchall()
        return [self._health(r) for r in rows]

    # ---- settings ------------------------------------------------------------

    def get_settings(self) -> dict[str, str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT key, value FROM app_setting").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def save_settings(self, values: dict[str, str], now: datetime) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT INTO app_setting (key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                " updated_at = excluded.updated_at",
                [(k, v, to_utc_iso(now)) for k, v in values.items()],
            )

    # ---- scheduler events ----------------------------------------------------

    def insert_event(self, at: datetime, kind: str, detail: str | None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO scheduler_event (at, kind, detail) VALUES (?, ?, ?)",
                (to_utc_iso(at), kind, detail),
            )

    def recent_events(self, limit: int = 20) -> list[SchedulerEventRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scheduler_event ORDER BY at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [SchedulerEventRecord(_req_ts(r["at"]), r["kind"], r["detail"]) for r in rows]
