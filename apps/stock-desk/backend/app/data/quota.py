"""Cross-process daily request quota ledger, backed by the shared SQLite DB.

ADR-0005 (stock-desk 指數來源與美股額度管理), 決策三 "額度計數器":

Alpha Vantage's free tier has a hard daily request cap. The API process and
the scheduler process (``app/scheduler.py``) are two separate OS processes,
so an in-memory counter would let each of them independently believe it has
the full budget (``compose.yaml`` gives them a shared named volume precisely
so a *persisted, shared* counter is possible -- see ADR-0005 決策三 選項比較).

The gate is a single atomic SQL statement, not a "SELECT then UPDATE" pair:
a TOCTOU race between the two processes would otherwise let both slip a
request through when only one slot is left.

    INSERT INTO provider_quota_usage (...)
    VALUES (?, ?, 1, ?, ?)
    ON CONFLICT(provider, quota_date) DO UPDATE SET
        used = used + 1, updated_at = excluded.updated_at
    WHERE used < limit_value;

``cursor.rowcount == 0`` after this statement means the quota is exhausted:
the caller MUST NOT issue the HTTP request it was about to make. This is a
"reserve, then call" protocol -- the slot is spent the moment a caller
*decides* to call the upstream API, not after the call succeeds, because a
timeout or a malformed response has already consumed the vendor's quota
whether or not we got usable data back. There is deliberately no "release"
or "refund" method: a failed request's reservation is never given back.

None of the budget numbers themselves are hardcoded here. ADR-0005 決策三
records Alpha Vantage's free-tier daily cap as noted in ADR-0003 (queried
2026-07-23) -- but per this task's explicit constraint, that figure must live
only in configuration (environment variable / .env), never as a literal in
this module. If ``ALPHA_VANTAGE_DAILY_LIMIT`` is not set,
:func:`resolve_quota_config` raises :class:`QuotaConfigError` rather than
silently assuming a number nobody configured.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.data.cache import resolve_db_path

#: Environment variable names, exactly as named in ADR-0005 決策三 so the
#: ADR text and the code can be cross-referenced without translation.
DAILY_LIMIT_ENV_VAR = "ALPHA_VANTAGE_DAILY_LIMIT"
SAFETY_MARGIN_ENV_VAR = "ALPHA_VANTAGE_SAFETY_MARGIN"
RESET_TZ_ENV_VAR = "QUOTA_RESET_TZ"
MIN_INTERVAL_ENV_VAR = "ALPHA_VANTAGE_MIN_INTERVAL_SECONDS"

#: Safety margin default per ADR-0005 決策三 point 4 ("預設 2"). Not the daily
#: cap itself, so a hardcoded default here does not run afoul of the "no
#: literal cap in code" rule.
DEFAULT_SAFETY_MARGIN = 2
#: Reset timezone default per ADR-0005 決策三 point 4 -- explicitly flagged
#: there as "重置時區未查證"; UTC is the conservative placeholder pending
#: devops-sre verification (ADR-0005 尚缺的事實 #2).
DEFAULT_RESET_TZ = "UTC"
#: Client-side throttle default per ADR-0005 決策三 point 5: Alpha Vantage's
#: real per-minute limit is unverified, so this is *our own* conservative
#: number (<=5 req/min), not a claim about the vendor's actual limit.
DEFAULT_MIN_INTERVAL_SECONDS = 12.0

#: ``PRAGMA busy_timeout`` applied to every connection (milliseconds). Not an
#: environment-configured value per ADR-0005 決策三 point 3 -- it is an
#: internal contention-handling knob, not a budget number.
DEFAULT_BUSY_TIMEOUT_MS = 5_000

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS provider_quota_usage (
    provider    TEXT NOT NULL,
    quota_date  TEXT NOT NULL,
    used        INTEGER NOT NULL,
    limit_value INTEGER NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (provider, quota_date)
)
"""

_RESERVE_SQL = """
INSERT INTO provider_quota_usage (provider, quota_date, used, limit_value, updated_at)
VALUES (?, ?, 1, ?, ?)
ON CONFLICT(provider, quota_date) DO UPDATE SET
    used = used + 1,
    updated_at = excluded.updated_at
WHERE used < limit_value
"""

_SELECT_SQL = """
SELECT used, limit_value, updated_at
FROM provider_quota_usage
WHERE provider = ? AND quota_date = ?
"""


class QuotaConfigError(ValueError):
    """A quota-related environment variable is missing or malformed.

    Deliberately a distinct type from a normal "provider unavailable" signal:
    callers (adapters) should catch this and degrade the same way they would
    an empty upstream response, but it is worth its own log line because it
    means *this deployment* is misconfigured, not that the vendor is down.
    """


@dataclass(frozen=True)
class QuotaConfig:
    """Resolved, env-sourced quota configuration for one provider."""

    daily_limit: int
    safety_margin: int
    reset_tz: str
    min_interval_seconds: float

    @property
    def effective_limit(self) -> int:
        """Usable daily budget after the safety margin (never negative)."""
        return max(0, self.daily_limit - self.safety_margin)


def _read_int_env(var_name: str, *, default: int | None) -> int:
    raw = os.environ.get(var_name)
    if raw is None or raw.strip() == "":
        if default is None:
            raise QuotaConfigError(
                f"{var_name} is not set; the daily request cap must be configured "
                "explicitly via environment variable, it has no built-in default."
            )
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise QuotaConfigError(f"{var_name}={raw!r} is not a valid integer") from exc


def _read_float_env(var_name: str, *, default: float) -> float:
    raw = os.environ.get(var_name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise QuotaConfigError(f"{var_name}={raw!r} is not a valid number") from exc


def _read_str_env(var_name: str, *, default: str) -> str:
    raw = os.environ.get(var_name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def resolve_quota_config() -> QuotaConfig:
    """Read Alpha Vantage's quota configuration from environment variables.

    Raises :class:`QuotaConfigError` if ``ALPHA_VANTAGE_DAILY_LIMIT`` is
    unset/unparsable, or if any other variable is set but unparsable. The
    other three variables fall back to the ADR-0005 決策三 defaults above
    when unset.
    """
    daily_limit = _read_int_env(DAILY_LIMIT_ENV_VAR, default=None)
    safety_margin = _read_int_env(SAFETY_MARGIN_ENV_VAR, default=DEFAULT_SAFETY_MARGIN)
    reset_tz = _read_str_env(RESET_TZ_ENV_VAR, default=DEFAULT_RESET_TZ)
    min_interval_seconds = _read_float_env(
        MIN_INTERVAL_ENV_VAR, default=DEFAULT_MIN_INTERVAL_SECONDS
    )
    # Fail fast on a typo'd timezone name rather than silently falling back
    # to UTC and reporting a wrong reset boundary.
    try:
        ZoneInfo(reset_tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise QuotaConfigError(
            f"{RESET_TZ_ENV_VAR}={reset_tz!r} is not a known IANA timezone"
        ) from exc
    return QuotaConfig(
        daily_limit=daily_limit,
        safety_margin=safety_margin,
        reset_tz=reset_tz,
        min_interval_seconds=min_interval_seconds,
    )


def resolve_min_interval_seconds() -> float:
    """Read just the client-side throttle interval, independent of the daily cap.

    Adapters read this at construction time, before any request is made --
    unlike :func:`resolve_quota_config` (called per-request), construction
    must not fail just because ``ALPHA_VANTAGE_DAILY_LIMIT`` has not been
    configured yet.
    """
    return _read_float_env(MIN_INTERVAL_ENV_VAR, default=DEFAULT_MIN_INTERVAL_SECONDS)


@dataclass(frozen=True)
class QuotaUsage:
    """A snapshot of one provider's usage for one quota day."""

    provider: str
    quota_date: str
    used: int
    limit_value: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit_value - self.used)


@dataclass(frozen=True)
class QuotaReservation(QuotaUsage):
    """The outcome of one :meth:`QuotaLedger.reserve` call.

    ``granted=False`` means the day's quota was already exhausted *before*
    this call -- the caller must not issue the HTTP request it was about to
    make. ``used``/``limit_value`` reflect the ledger's state immediately
    after the attempted reservation either way.
    """

    granted: bool


def _quota_date(now: datetime, reset_tz: str) -> str:
    """The calendar date ``now`` falls on on the quota's reset timezone."""
    return now.astimezone(ZoneInfo(reset_tz)).date().isoformat()


class QuotaLedger:
    """SQLite (WAL mode) ledger of per-provider, per-day request usage.

    Shares the physical database file with :class:`app.data.cache.PriceBarCache`
    by default (same ``STOCK_DESK_DB_PATH`` resolution) so the API process and
    the scheduler process see the same counter -- see ``compose.yaml``'s
    shared named volume and ADR-0005 決策三 前置阻擋條件 P-1.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._busy_timeout_ms = busy_timeout_ms
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None puts the driver in autocommit mode so this
        # class can issue its own explicit BEGIN IMMEDIATE / COMMIT /
        # ROLLBACK instead of the driver's implicit transaction handling.
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        # busy_timeout is a per-connection session setting (unlike
        # journal_mode, which persists on disk), so it must be reissued here
        # on every connect -- this is what lets two processes (API +
        # scheduler) writing to the same file at the same moment wait for
        # each other's write lock instead of raising "database is locked".
        conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_TABLE_SQL)

    def reserve(
        self,
        provider: str,
        *,
        limit_value: int,
        now: datetime | None = None,
        reset_tz: str = DEFAULT_RESET_TZ,
    ) -> QuotaReservation:
        """Atomically reserve one request slot for ``provider`` today.

        Returns a :class:`QuotaReservation` whose ``granted`` is ``False``
        when the day's quota is already exhausted -- in which case the
        caller MUST NOT issue the HTTP request it was about to make (ADR-0005
        約束 Q-3). The reservation is not undone if the subsequent request
        then fails (ADR-0005 約束 Q-2): there is no refund/release method.
        """
        moment = now if now is not None else datetime.now(UTC)
        quota_date = _quota_date(moment, reset_tz)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    _RESERVE_SQL, (provider, quota_date, limit_value, moment.isoformat())
                )
                granted = cursor.rowcount > 0
                row = conn.execute(_SELECT_SQL, (provider, quota_date)).fetchone()
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        if row is None:  # pragma: no cover - defensive; the upsert above always creates this row
            raise RuntimeError(
                f"provider_quota_usage row for ({provider!r}, {quota_date!r}) "
                "missing immediately after upsert; this should be unreachable"
            )
        used, limit_value_stored, _updated_at = row
        return QuotaReservation(
            granted=granted,
            provider=provider,
            quota_date=quota_date,
            used=used,
            limit_value=limit_value_stored,
        )

    def status(
        self,
        provider: str,
        *,
        now: datetime | None = None,
        reset_tz: str = DEFAULT_RESET_TZ,
    ) -> QuotaUsage | None:
        """Read-only snapshot of today's usage for ``provider``.

        Returns ``None`` if no request has been reserved yet today (the row
        does not exist until the first :meth:`reserve` call of the day).
        Never itself reserves a slot -- intended for observability (e.g. a
        future ``GET /api/settings`` data-source block per ADR-0005 決策三
        point 6), not for the gating decision.
        """
        moment = now if now is not None else datetime.now(UTC)
        quota_date = _quota_date(moment, reset_tz)
        with closing(self._connect()) as conn:
            row = conn.execute(_SELECT_SQL, (provider, quota_date)).fetchone()
        if row is None:
            return None
        used, limit_value, _updated_at = row
        return QuotaUsage(
            provider=provider,
            quota_date=quota_date,
            used=used,
            limit_value=limit_value,
        )
