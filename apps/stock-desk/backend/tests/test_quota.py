"""Tests for the cross-process daily quota ledger (ADR-0005 決策三)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.data.quota import (
    DAILY_LIMIT_ENV_VAR,
    MIN_INTERVAL_ENV_VAR,
    RESET_TZ_ENV_VAR,
    SAFETY_MARGIN_ENV_VAR,
    QuotaConfigError,
    QuotaLedger,
    resolve_min_interval_seconds,
    resolve_quota_config,
)

NOON = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _ledger(tmp_path: Path) -> QuotaLedger:
    return QuotaLedger(db_path=tmp_path / "quota.db")


def test_reserve_grants_slots_up_to_the_limit(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    first = ledger.reserve("alpha_vantage", limit_value=2, now=NOON)
    second = ledger.reserve("alpha_vantage", limit_value=2, now=NOON)
    third = ledger.reserve("alpha_vantage", limit_value=2, now=NOON)

    assert (first.granted, first.used) == (True, 1)
    assert (second.granted, second.used) == (True, 2)
    assert (third.granted, third.used) == (False, 2)
    assert third.remaining == 0


def test_reserve_is_a_single_atomic_upsert_not_select_then_update(tmp_path: Path) -> None:
    """Q-1: gate decision is one INSERT ... ON CONFLICT ... WHERE statement."""
    import app.data.quota as quota_module

    assert quota_module._RESERVE_SQL.strip().upper().startswith("INSERT")
    assert "ON CONFLICT" in quota_module._RESERVE_SQL
    assert "WHERE USED < LIMIT_VALUE" in quota_module._RESERVE_SQL.upper()
    # Exactly one INSERT/UPDATE/DELETE keyword combination performing the gate;
    # no separate SELECT precedes it in the same statement string.
    assert quota_module._RESERVE_SQL.strip().upper().count("SELECT") == 0


def test_denied_reservation_does_not_change_used_count(tmp_path: Path) -> None:
    """Q-2: a request that never happens (denied reservation) must not move used."""
    ledger = _ledger(tmp_path)
    ledger.reserve("alpha_vantage", limit_value=1, now=NOON)
    denied = ledger.reserve("alpha_vantage", limit_value=1, now=NOON)
    denied_again = ledger.reserve("alpha_vantage", limit_value=1, now=NOON)

    assert denied.granted is False
    assert denied.used == 1
    assert denied_again.used == 1  # never crept upward from repeated denials


def test_failed_downstream_request_is_not_refunded(tmp_path: Path) -> None:
    """Q-2: reservation happens before the call; a simulated timeout afterwards
    must not roll back the counter -- there is deliberately no refund API."""
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve("alpha_vantage", limit_value=5, now=NOON)
    assert reservation.granted is True

    # Simulate "the HTTP call then timed out" -- nothing calls back into the
    # ledger to undo the reservation, by design.
    status = ledger.status("alpha_vantage", now=NOON)
    assert status is not None
    assert status.used == 1


def test_reservations_are_scoped_per_provider(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("alpha_vantage", limit_value=1, now=NOON)
    other = ledger.reserve("some_other_provider", limit_value=1, now=NOON)
    assert other.granted is True
    assert other.used == 1


def test_reservations_reset_on_a_new_quota_date(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("alpha_vantage", limit_value=1, now=NOON)
    exhausted = ledger.reserve("alpha_vantage", limit_value=1, now=NOON)
    assert exhausted.granted is False

    next_day = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
    fresh_day = ledger.reserve("alpha_vantage", limit_value=1, now=next_day)
    assert fresh_day.granted is True
    assert fresh_day.quota_date == "2026-07-27"


def test_quota_date_uses_the_configured_reset_timezone(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    # 23:30 UTC on 2026-07-26 is already 2026-07-27 in Asia/Taipei (UTC+8).
    late_utc = datetime(2026, 7, 26, 23, 30, tzinfo=UTC)
    reservation = ledger.reserve(
        "alpha_vantage", limit_value=1, now=late_utc, reset_tz="Asia/Taipei"
    )
    assert reservation.quota_date == "2026-07-27"

    reservation_utc = ledger.reserve(
        "alpha_vantage", limit_value=1, now=late_utc, reset_tz="UTC"
    )
    assert reservation_utc.quota_date == "2026-07-26"


def test_status_is_none_before_any_reservation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    assert ledger.status("alpha_vantage", now=NOON) is None


def test_status_does_not_itself_reserve_a_slot(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("alpha_vantage", limit_value=1, now=NOON)
    for _ in range(5):
        status = ledger.status("alpha_vantage", now=NOON)
        assert status is not None
        assert status.used == 1  # unaffected by repeated status() reads


def test_two_ledger_instances_on_the_same_db_path_share_state(tmp_path: Path) -> None:
    """Simulates two OS processes (API + scheduler) pointed at the same file."""
    db_path = tmp_path / "shared.db"
    api_process_ledger = QuotaLedger(db_path=db_path)
    scheduler_process_ledger = QuotaLedger(db_path=db_path)

    api_process_ledger.reserve("alpha_vantage", limit_value=2, now=NOON)
    scheduler_process_ledger.reserve("alpha_vantage", limit_value=2, now=NOON)
    third = api_process_ledger.reserve("alpha_vantage", limit_value=2, now=NOON)

    assert third.granted is False
    assert third.used == 2


def test_every_connection_sets_busy_timeout(tmp_path: Path) -> None:
    ledger = QuotaLedger(db_path=tmp_path / "quota.db", busy_timeout_ms=1234)
    with ledger._connect() as conn:  # noqa: SLF001 - white-box check of the pragma
        (value,) = conn.execute("PRAGMA busy_timeout").fetchone()
    assert value == 1234


class TestResolveQuotaConfig:
    def test_raises_when_daily_limit_env_var_is_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(DAILY_LIMIT_ENV_VAR, raising=False)
        with pytest.raises(QuotaConfigError, match=DAILY_LIMIT_ENV_VAR):
            resolve_quota_config()

    def test_raises_when_daily_limit_is_not_an_integer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "not-a-number")
        with pytest.raises(QuotaConfigError):
            resolve_quota_config()

    def test_effective_limit_subtracts_the_safety_margin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "3")
        config = resolve_quota_config()
        assert config.daily_limit == 10
        assert config.safety_margin == 3
        assert config.effective_limit == 7

    def test_effective_limit_uses_default_safety_margin_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.delenv(SAFETY_MARGIN_ENV_VAR, raising=False)
        config = resolve_quota_config()
        assert config.effective_limit == 10 - config.safety_margin

    def test_effective_limit_never_goes_negative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "1")
        monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "99")
        config = resolve_quota_config()
        assert config.effective_limit == 0

    def test_reset_tz_defaults_to_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.delenv(RESET_TZ_ENV_VAR, raising=False)
        config = resolve_quota_config()
        assert config.reset_tz == "UTC"
        assert ZoneInfo(config.reset_tz) is not None

    def test_raises_on_unknown_timezone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.setenv(RESET_TZ_ENV_VAR, "Not/AZone")
        with pytest.raises(QuotaConfigError):
            resolve_quota_config()

    def test_min_interval_seconds_defaults_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.delenv(MIN_INTERVAL_ENV_VAR, raising=False)
        config = resolve_quota_config()
        assert config.min_interval_seconds > 0

    def test_min_interval_seconds_is_read_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
        monkeypatch.setenv(MIN_INTERVAL_ENV_VAR, "3.5")
        config = resolve_quota_config()
        assert config.min_interval_seconds == 3.5


class TestResolveMinIntervalSeconds:
    def test_does_not_require_daily_limit_to_be_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(DAILY_LIMIT_ENV_VAR, raising=False)
        monkeypatch.delenv(MIN_INTERVAL_ENV_VAR, raising=False)
        # Must not raise even though the daily limit itself is unconfigured.
        value = resolve_min_interval_seconds()
        assert value > 0

    def test_reads_from_env_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(MIN_INTERVAL_ENV_VAR, "7.0")
        assert resolve_min_interval_seconds() == 7.0
