"""Tests for the Phase 1 heartbeat scheduler placeholder."""

from datetime import UTC, datetime

from app.scheduler import heartbeat_message


def test_heartbeat_message_prefix() -> None:
    message = heartbeat_message()
    assert message.startswith("scheduler heartbeat ")


def test_heartbeat_message_timestamp_is_parseable_iso8601() -> None:
    fixed = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
    message = heartbeat_message(fixed)
    timestamp = message.removeprefix("scheduler heartbeat ")
    parsed = datetime.fromisoformat(timestamp)
    assert parsed == fixed
    assert parsed.tzinfo is not None
