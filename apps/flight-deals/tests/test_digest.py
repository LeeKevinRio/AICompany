"""Daily digest: schedule, settings, dedupe, retries and wording (FD-4 FR-DG, C-32, C-34)."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.app import assemble
from flight_deals.config import Config
from flight_deals.domain.airports import PLACES, route_label
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DIGEST_MAX_CHARS,
    DIGEST_MAX_WATCH_LINES,
    DISCLAIMER,
    NO_PRICE_ALERT_NOTE,
    SAMPLED_ONLY_NOTE,
    DigestRow,
    DigestSourceRow,
    daily_digest_message,
)
from flight_deals.domain.rules import digest_key
from flight_deals.notify.telegram import MAX_MESSAGE_LENGTH
from flight_deals.scheduler.jobs import (
    DIGEST_CATCHUP_JOB_ID,
    DIGEST_CHECK_JOB_ID,
    DIGEST_JOB_ID,
    DIGEST_RECHECK_JOB_ID,
)
from flight_deals.storage.repository import SourceHealthRecord
from tests.conftest import CLIENT_HEADERS, FakeClock, FakeLock, FakeNotifier, Harness

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"


def taipei(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    """Aware UTC datetime for a 2026 Asia/Taipei wall-clock time (UTC+8, no DST)."""
    return datetime(2026, month, day, hour, minute, tzinfo=UTC) - timedelta(hours=8)


def digests(harness: Harness) -> list[Any]:
    return [n for n in harness.repo.list_notifications() if n.kind == "daily_digest"]


def send(harness: Harness, moment: datetime) -> str:
    harness.clock.now = moment
    return str(harness.services.digest.send_if_due(moment))


# ---- schedule / dedupe (C-32) -------------------------------------------------------


def test_sends_on_time_and_only_once_per_day(harness: Harness) -> None:  # AC-DG1, AC-DG2
    harness.create_watch()
    harness.create_watch(destination="KIX")
    assert send(harness, taipei(26, 7, 59)) == "not_yet"
    assert send(harness, taipei(26, 8, 0)) == "sent"
    assert send(harness, taipei(26, 8, 0)) == "handled"
    assert send(harness, taipei(26, 23, 59)) == "handled"
    assert len(harness.notifier.sent) == 1
    [record] = digests(harness)
    assert record.status == "sent" and record.dedupe_key == "digest:2026-10-26"
    assert (record.watch_id, record.rule, record.price_kind) == (None, None, None)
    assert send(harness, taipei(27, 8, 0)) == "sent"  # next day
    assert len(harness.notifier.sent) == 2


def test_late_start_catches_up_same_day_only(harness: Harness) -> None:  # AC-DG14
    # Service was off at 08:00 on 10/26 and 10/27; it starts at 10:00 on 10/27.
    assert send(harness, taipei(27, 10, 0)) == "sent"
    assert [d.dedupe_key for d in digests(harness)] == ["digest:2026-10-27"]


def test_wake_from_sleep_hourly_check_sends(harness: Harness) -> None:
    assert send(harness, taipei(26, 15, 0)) == "sent"


def test_disabled_sends_nothing_not_even_suppressed(harness: Harness) -> None:  # AC-DG4
    harness.notifier.configured = False
    assert harness.services.settings.update({"digest_enabled": False}) == {}
    assert send(harness, taipei(26, 9, 0)) == "disabled"
    assert digests(harness) == []
    assert harness.services.settings.update({"digest_enabled": True}) == {}
    harness.notifier.configured = True
    assert send(harness, taipei(26, 9, 1)) == "sent"


def test_not_configured_is_suppressed_and_counts_as_handled(harness: Harness) -> None:  # AC-DG5
    harness.notifier.configured = False
    assert send(harness, taipei(26, 8, 0)) == "suppressed"
    [record] = digests(harness)
    assert record.status == "suppressed" and record.attempts == 0
    harness.notifier.configured = True
    assert send(harness, taipei(26, 9, 0)) == "handled"
    assert harness.services.notifications.retry_pending() == 0
    assert harness.notifier.sent == []


def test_failure_retries_same_day_only_up_to_cap(harness: Harness) -> None:  # AC-DG13
    harness.notifier.fail_with = "HTTP 502: bad gateway"
    assert send(harness, taipei(26, 8, 0)) == "failed"
    [record] = digests(harness)
    assert record.status == "failed" and record.last_error == "HTTP 502: bad gateway"
    assert send(harness, taipei(26, 9, 0)) == "retry_failed"
    assert harness.services.notifications.retry_pending() == 0  # third attempt, still failing
    assert digests(harness)[0].attempts == 3
    harness.notifier.fail_with = None
    assert send(harness, taipei(26, 10, 0)) == "retry_failed"  # cap reached
    assert harness.services.notifications.retry_pending() == 0
    assert harness.notifier.sent == []


def test_failed_digest_recovers_then_never_repeats(harness: Harness) -> None:
    harness.notifier.fail_with = "timeout"
    assert send(harness, taipei(26, 8, 0)) == "failed"
    harness.notifier.fail_with = None
    harness.clock.now = taipei(26, 8, 30)
    assert harness.services.notifications.retry_pending() == 1  # retried by a scan round
    assert send(harness, taipei(26, 9, 0)) == "handled"
    assert len(harness.notifier.sent) == 1


def test_yesterdays_failed_digest_is_not_sent_today(harness: Harness) -> None:
    harness.notifier.fail_with = "timeout"
    assert send(harness, taipei(26, 8, 0)) == "failed"
    harness.notifier.fail_with = None
    harness.clock.now = taipei(27, 7, 0)
    assert harness.services.notifications.retry_pending() == 0
    assert harness.notifier.sent == []
    assert send(harness, taipei(27, 8, 0)) == "sent"
    assert len(harness.notifier.sent) == 1 and "2026-10-27" in harness.notifier.sent[0]


def test_changing_time_later_does_not_send_twice(harness: Harness) -> None:  # AC-DG2
    assert send(harness, taipei(26, 8, 0)) == "sent"
    assert harness.services.settings.update({"digest_time": "21:00"}) == {}
    assert send(harness, taipei(26, 21, 0)) == "handled"
    assert len(harness.notifier.sent) == 1


def test_new_time_applies(harness: Harness) -> None:  # AC-DG3
    assert harness.services.settings.update({"digest_time": "09:30"}) == {}
    assert send(harness, taipei(26, 8, 0)) == "not_yet"
    assert send(harness, taipei(26, 9, 29)) == "not_yet"
    assert send(harness, taipei(26, 9, 30)) == "sent"


def test_digest_key_is_unique(harness: Harness) -> None:
    kwargs: dict[str, Any] = dict(
        watch_id=None,
        kind="daily_digest",
        rule=None,
        price_kind=None,
        observation_id=None,
        channel="telegram",
        dedupe_key=digest_key(date(2026, 10, 26)),
        message_text="x",
        created_at=harness.clock(),
    )
    assert harness.repo.insert_notification(**kwargs) is not None
    assert harness.repo.insert_notification(**kwargs) is None
    assert harness.services.notifications.send_daily_digest("digest:2026-10-26", "y") is None


# ---- scheduler wiring ---------------------------------------------------------------


@pytest.fixture
def unstarted(tmp_path: Path) -> Iterator[Any]:
    notifier = FakeNotifier()
    built = assemble(
        Config(db_path=tmp_path / "d.db"),
        sources=[],
        notifier=notifier,
        clock=FakeClock(datetime.now(UTC)),
    )
    yield built, notifier
    built.scheduler.shutdown()


def test_settings_listener_only_schedules(unstarted: Any) -> None:  # C-32
    built, notifier = unstarted
    services = built.services
    assert services.settings.update({"digest_time": "09:30", "digest_enabled": True}) == {}
    assert notifier.attempts == 0 and notifier.sent == []
    job = built.scheduler.scheduler.get_job(DIGEST_JOB_ID)
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert (fields["hour"], fields["minute"]) == ("9", "30")
    assert str(job.trigger.timezone) == "Asia/Taipei"
    assert built.scheduler.scheduler.get_job(DIGEST_RECHECK_JOB_ID) is not None


def test_started_scheduler_has_digest_jobs_and_next_scan_ignores_them(
    tmp_path: Path,
) -> None:
    clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
    notifier = FakeNotifier(configured=False)
    built = assemble(Config(db_path=tmp_path / "d.db"), sources=[], notifier=notifier, clock=clock)
    # Push today's digest time far away so nothing fires during the test.
    built.services.settings.update({"digest_enabled": False})
    try:
        built.scheduler.start(FakeLock(held=True))
        ids = {job.id for job in built.scheduler.scheduler.get_jobs()}
        assert {DIGEST_JOB_ID, DIGEST_CHECK_JOB_ID} <= ids
        assert built.scheduler.next_run_time() is None  # no watches: no scan is due
    finally:
        built.scheduler.shutdown()


def test_catchup_is_queued_after_startup_scans(tmp_path: Path) -> None:
    clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
    built = assemble(
        Config(db_path=tmp_path / "d.db"), sources=[], notifier=FakeNotifier(), clock=clock
    )
    for i in range(2):
        built.services.watches.create(
            {
                "destination": "NRT",
                "depart_date": "2027-03-10",
                "return_date": "2027-03-15",
                "budget": 12000 + i,
            }
        )
    scheduler = built.scheduler
    scheduler.sync_all(startup=True)
    scheduler.schedule_digest(startup=True)
    jobs = {job.id: job for job in scheduler.scheduler.get_jobs()}
    startup = [j for i, j in jobs.items() if i.startswith("startup:")]
    assert len(startup) == 2
    catchup = jobs[DIGEST_CATCHUP_JOB_ID]
    assert all(catchup.trigger.run_date > j.trigger.run_date for j in startup)
    scheduler.shutdown()


def test_scheduler_never_sends_from_listener_thread_source() -> None:  # C-32
    code = (SRC / "scheduler" / "jobs.py").read_text(encoding="utf-8")
    listener = code.split("def on_settings_changed", 1)[1].split("\n    def ", 1)[0]
    assert "send_if_due" not in listener


# ---- settings validation (C-32) -----------------------------------------------------


def post(harness: Harness, payload: dict[str, Any]) -> Any:
    return harness.client.post("/api/settings", json=payload, headers=CLIENT_HEADERS)


@pytest.mark.parametrize("value", ["8:00", "24:00", "08:00:00", "", "9:3x", "25:00", " 08:00", 800])
def test_digest_time_rejected(harness: Harness, value: object) -> None:
    before = harness.services.settings.current()
    response = post(harness, {"digest_time": value})
    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"digest_time"}
    assert harness.services.settings.current() == before


@pytest.mark.parametrize("value", ["yes", "on", 1, None, "2"])
def test_digest_enabled_rejected(harness: Harness, value: object) -> None:
    response = post(harness, {"digest_enabled": value})
    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"digest_enabled"}


def test_digest_settings_accepted_and_shown(harness: Harness) -> None:
    current = harness.services.settings.current()
    assert (current.digest_enabled, current.digest_time) == (True, "08:00")
    assert post(harness, {"digest_enabled": False, "digest_time": "09:30"}).status_code == 200
    current = harness.services.settings.current()
    assert (current.digest_enabled, current.digest_time) == (False, "09:30")
    for flag in ("1", "true", True):
        assert post(harness, {"digest_enabled": flag}).status_code == 200
        assert harness.services.settings.current().digest_enabled is True
    page = harness.services.views.settings_page()
    assert page["digest_enabled"] is True and page["digest_time"] == "09:30"
    assert harness.client.get("/settings").status_code == 200


def test_invalid_stored_digest_values_fall_back(harness: Harness) -> None:
    harness.repo.save_settings({"digest_enabled": "yes", "digest_time": "8:00"}, harness.clock())
    current = harness.services.settings.current()
    assert (current.digest_enabled, current.digest_time) == (True, "08:00")


def test_mixed_settings_update(harness: Harness) -> None:
    response = post(harness, {"scan_interval_minutes": "180", "digest_time": "07:15"})
    assert response.status_code == 200
    current = harness.services.settings.current()
    assert (current.scan_interval_minutes, current.digest_time) == (180, "07:15")
    bad = post(harness, {"scan_interval_minutes": "0", "digest_time": "7:15"})
    assert set(bad.json()["errors"]) == {"scan_interval_minutes", "digest_time"}


# ---- content (C-34) -----------------------------------------------------------------


def test_digest_content_change_and_no_price(harness: Harness) -> None:  # AC-DG7..DG9
    a = harness.create_watch(name="東京")
    harness.create_watch(name="大阪", destination="KIX")
    harness.source.prices[("2026-12-10", "2026-12-15")] = 10_000
    harness.clock.now = taipei(25, 20, 0)
    harness.scan(a)
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_400
    harness.clock.now = taipei(26, 7, 0)
    harness.scan(a)
    assert send(harness, taipei(26, 8, 0)) == "sent"
    text = harness.notifier.sent[-1]  # earlier entries are price alerts from the scans
    lines = text.splitlines()
    tokyo = next(line for line in lines if line.startswith("• 東京"))
    osaka = next(line for line in lines if line.startswith("• 大阪"))
    assert "TWD 9,400（12/10–12/15）" in tokyo and "較前一日 -TWD 600" in tokyo
    assert "尚無價格" in osaka and "較前一日 —" in osaka and "TWD 0" not in osaka
    assert "啟用中的監看：2 個" in text
    assert text.rstrip().endswith(NO_PRICE_ALERT_NOTE)
    assert DISCLAIMER in text and SAMPLED_ONLY_NOTE in text
    record = digests(harness)[0]
    assert record.message_text == text


def test_digest_flat_and_up(harness: Harness) -> None:  # AC-DG8
    a = harness.create_watch(name="甲")
    harness.source.default_price = 9_000
    harness.clock.now = taipei(25, 20, 0)
    harness.scan(a)
    harness.clock.now = taipei(26, 7, 0)
    harness.scan(a)
    text = harness.services.digest.compose(taipei(26, 8, 0))
    assert "較前一日 持平" in text
    harness.source.default_price = 9_450
    harness.clock.now = taipei(26, 7, 30)
    harness.scan(a)
    assert "較前一日 +TWD 450" in harness.services.digest.compose(taipei(26, 8, 0))


def test_digest_lists_only_enabled_watches(harness: Harness) -> None:  # AC-DG6, FR-DG8
    paused = harness.create_watch(name="停用的")
    harness.services.watches.set_enabled(paused, False)
    text = harness.services.digest.compose(taipei(26, 8, 0))
    assert "目前沒有啟用中的監看" in text
    assert "• " not in text and "停用的" not in text
    assert DISCLAIMER in text and NO_PRICE_ALERT_NOTE in text
    assert "上次掃描：—" in text


def test_digest_source_state_matches_health_page(harness: Harness) -> None:  # AC-DG10
    harness.create_watch()
    base = SourceHealthRecord("google_flights", True, "closed", 0, None, None, None, None)
    cases = [
        (base, "Google Flights 未知（尚未查詢）"),
        (
            SourceHealthRecord(
                "google_flights", True, "closed", 0, None, taipei(26, 1), None, None
            ),
            "Google Flights 正常",
        ),
        (
            SourceHealthRecord(
                "google_flights",
                True,
                "open",
                3,
                taipei(26, 9),
                taipei(25, 1),
                taipei(26, 1),
                "secret-ish internal error text",
            ),
            "Google Flights 異常（斷路器開啟，暫停查詢）",
        ),
    ]
    for record, expected in cases:
        harness.repo.save_source_health(record)
        text = harness.services.digest.compose(taipei(26, 8, 0))
        assert f"資料源：{expected}" in text
        assert "secret-ish internal error text" not in text  # never last_error
        health = harness.services.views.settings_page()["health"][0]["state"]
        assert expected.startswith(f"Google Flights {health}")


def test_failed_scan_count_last_24_hours(harness: Harness) -> None:  # FR-DG5
    watch_id = harness.create_watch()
    harness.source.status_override = "error"
    for hour in (1, 3, 5):  # failed runs within 24 h of 10/26 08:00
        harness.clock.now = taipei(26, hour)
        harness.scan(watch_id)
    harness.clock.now = taipei(25, 7)  # older than 24 h
    harness.scan(watch_id)
    harness.source.status_override = None
    harness.clock.now = taipei(26, 6)
    harness.scan(watch_id)  # ok run, not counted
    text = harness.services.digest.compose(taipei(26, 8, 0))
    assert "過去 24 小時查價失敗的掃描：3 次" in text
    assert "上次掃描：2026-10-26 06:00（台北時間）" in text


def test_notification_log_shows_daily_digest_label(harness: Harness) -> None:  # AC-DG15
    send(harness, taipei(26, 8, 0))
    rows = harness.services.views.notifications_page()["notifications"]
    assert rows[0]["kind"] == "每日摘要"
    assert "每日摘要" in rows[0]["text"]


def row(
    name: str, origin: str = "TPE", destination: str = "NRT", amount: int | None = 9_400_00
) -> DigestRow:
    return DigestRow(
        name=name,
        origin=origin,
        destination=destination,
        currency="TWD",
        amount_minor=amount,
        depart_date=date(2026, 12, 10) if amount else None,
        return_date=date(2026, 12, 15) if amount else None,
        delta_minor=-60_000 if amount else None,
        data_stale=True,
        watch_stale=True,
    )


def longest_route() -> tuple[str, str]:
    codes = sorted(PLACES, key=lambda p: len(route_label(p.code, p.code)), reverse=True)
    return codes[0].code, codes[1].code


def test_digest_length_cap_with_200_long_watches() -> None:  # AC-DG16, C-34
    origin, destination = longest_route()
    rows = [row("名" * 80, origin, destination) for _ in range(200)]
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[DigestSourceRow("google_flights", "異常", "open")],
        last_scan_at=taipei(26, 7),
        failed_scans_24h=12,
        stale_after_hours=24,
        rows=rows,
    )
    assert len(text) <= DIGEST_MAX_CHARS < MAX_MESSAGE_LENGTH
    watch_lines = [line for line in text.splitlines() if line.startswith("• ")]
    assert 0 < len(watch_lines) <= DIGEST_MAX_WATCH_LINES
    assert f"另有 {200 - len(watch_lines)} 個監看未列出" in text
    assert DISCLAIMER in text and text.rstrip().endswith(NO_PRICE_ALERT_NOTE)
    assert "名" * 21 not in text  # names truncated to 20 characters


def test_digest_30_watches_names_hidden_count() -> None:
    rows = [row(f"監看{i}") for i in range(30)]
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        rows=rows,
        stale_after_hours=24,
    )
    assert sum(line.startswith("• ") for line in text.splitlines()) == 20
    assert "另有 10 個監看未列出" in text


def test_digest_wording_has_no_banned_phrases(harness: Harness) -> None:  # AC-DG12
    texts = [
        daily_digest_message(
            day=date(2026, 10, 26),
            sources=[DigestSourceRow("google_flights", "正常", "half_open")],
            last_scan_at=taipei(26, 7),
            failed_scans_24h=1,
            stale_after_hours=24,
            rows=[row("a"), row("b", amount=None), *[row(str(i)) for i in range(25)]],
        ),
        daily_digest_message(
            day=date(2026, 10, 26),
            sources=[],
            last_scan_at=None,
            failed_scans_24h=0,
            rows=[],
            stale_after_hours=24,
        ),
    ]
    tree = ast.parse((SRC / "services" / "digest.py").read_text(encoding="utf-8"))
    texts += [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    tree = ast.parse((SRC / "cli.py").read_text(encoding="utf-8"))
    texts += [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    hits = [(phrase, t) for t in texts for phrase in BANNED_PHRASES if phrase in t]
    assert hits == []


def test_stale_marker_states_threshold_and_delta_note_caveat() -> None:  # risk review
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        rows=[row("a")],
        stale_after_hours=12,
    )
    assert "此價格逾 12 小時未重查" in text
    assert "資料已過舊" not in text
    assert "兩個最低價可能是不同日期，差額不代表同一行程的漲跌。" in text


def test_compose_uses_stale_after_hours_setting(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.clock.now = taipei(25, 1)
    harness.scan(watch_id)
    assert harness.services.settings.update({"stale_after_hours": "6"}) == {}
    text = harness.services.digest.compose(taipei(26, 8, 0))
    assert "此價格逾 6 小時未重查" in text


def test_list_page_explains_delta(harness: Harness) -> None:
    harness.create_watch()
    page = harness.client.get("/").text
    assert "較前一輪：目前最低價與上一輪掃描結束時最低價的差額" in page
    assert "兩個最低價可能是不同日期" in page


def test_next_scan_time_ignores_earlier_digest_job(tmp_path: Path) -> None:  # qa M3
    clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
    built = assemble(
        Config(db_path=tmp_path / "d.db"),
        sources=[],
        notifier=FakeNotifier(configured=False),
        clock=clock,
    )
    built.services.settings.update({"digest_enabled": False})
    built.services.watches.create(
        {
            "destination": "NRT",
            "depart_date": "2027-03-10",
            "return_date": "2027-03-15",
            "budget": 12000,
        }
    )
    scheduler = built.scheduler
    try:
        scheduler.start(FakeLock(held=True))
        inner = scheduler.scheduler
        inner.pause()  # nothing runs while the job times are inspected
        scan_times = [
            j.next_run_time
            for j in inner.get_jobs()
            if j.id.startswith(("watch:", "startup:")) and j.next_run_time is not None
        ]
        assert scan_times
        earlier = min(scan_times) - timedelta(seconds=5)
        inner.modify_job(DIGEST_CHECK_JOB_ID, next_run_time=earlier)
        assert inner.get_job(DIGEST_CHECK_JOB_ID).next_run_time == earlier
        assert scheduler.next_run_time() == min(scan_times)
    finally:
        scheduler.shutdown()
