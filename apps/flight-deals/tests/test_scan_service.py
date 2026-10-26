"""Scan + notification flow (AC-A6/A7/A9, AC-B1..B6, AC-C1..C9, C-6, C-8)."""

from __future__ import annotations

from typing import Any

from flight_deals.services.scan import ScanService
from tests.conftest import FakeClock, Harness, ScriptedSource

FLEX = {
    "date_mode": "flexible",
    "window_start": "2026-12-01",
    "window_end": "2026-12-31",
    "min_trip_days": 4,
    "max_trip_days": 6,
}


def notifications(h: Harness) -> list[Any]:
    return list(reversed(h.repo.list_notifications()))


def test_scan_records_complete_price(harness: Harness) -> None:  # AC-B1
    watch_id = harness.create_watch()
    outcome = harness.scan(watch_id)
    assert outcome.status == "ok" and outcome.queries_used == 1
    [obs] = harness.repo.observations_for_watch(watch_id)
    assert (obs.depart_date.isoformat(), obs.return_date.isoformat()) == (
        "2026-12-10",
        "2026-12-15",
    )
    assert obs.amount_minor == 1_000_000 and obs.currency == "TWD"
    assert obs.carrier == "測試航空" and obs.source == "google_flights"
    assert obs.fetched_at == harness.clock() and obs.price_kind == "live"
    assert harness.repo.get_watch(watch_id).last_scanned_at == harness.clock()


def test_query_cap_and_sampled_pairs_recorded(harness: Harness) -> None:  # AC-B2, AC-B3
    assert harness.services.settings.update({"max_pairs_per_scan": "5"}) == {}
    watch_id = harness.create_watch(**FLEX)
    outcome = harness.scan(watch_id)
    assert outcome.queries_used <= 5 and len(harness.source.calls) == 5
    [run] = harness.repo.scan_runs_for_watch(watch_id)
    assert run.limit_reached and run.total_pairs > 5 and len(run.sampled_pairs) == 5
    first = {p for p in run.sampled_pairs}
    harness.scan(watch_id)
    second = set(harness.repo.scan_runs_for_watch(watch_id)[0].sampled_pairs)
    assert first != second, "sampling rotates between scans"


def test_one_watch_failing_does_not_block_another(harness: Harness) -> None:  # AC-B4
    bad = harness.create_watch(depart_date="2026-12-01", return_date="2026-12-05")
    good = harness.create_watch()
    harness.source.fail_for.add(("2026-12-01", "2026-12-05"))
    assert harness.scan(bad).status == "failed"
    assert harness.scan(good).status == "ok"
    [run] = harness.repo.scan_runs_for_watch(bad)
    assert run.error_summary and "scripted error" in run.error_summary
    assert run.finished_at is not None
    assert harness.repo.count_observations(good) == 1


def test_breaker_opens_alerts_once_and_recovers(harness: Harness) -> None:  # AC-B5, C-9
    watch_id = harness.create_watch(**FLEX)
    harness.source.status_override = "error"
    harness.scan(watch_id)
    health = harness.repo.get_source_health("google_flights")
    assert health.breaker_state == "open"
    assert len(harness.source.calls) == 3, "breaker stops queries after threshold"
    ops = [n for n in notifications(harness) if n.kind == "ops_source_failure"]
    assert len(ops) == 1 and ops[0].status == "sent"

    harness.clock.advance(minutes=31)  # cooldown over -> half-open trial fails again
    harness.scan(watch_id)
    harness.clock.advance(minutes=31)
    harness.scan(watch_id)
    ops = [n for n in notifications(harness) if n.kind == "ops_source_failure"]
    assert len(ops) == 1, "no repeated alert before recovery"

    page = harness.services.views.settings_page()
    assert page["health"][0]["state"] == "異常"

    harness.source.status_override = None
    harness.clock.advance(minutes=31)
    harness.scan(watch_id)
    assert harness.repo.get_source_health("google_flights").breaker_state == "closed"
    assert harness.services.views.settings_page()["health"][0]["state"] == "正常"


def test_overlapping_scan_is_skipped_and_recorded(harness: Harness) -> None:  # AC-B6
    watch_id = harness.create_watch()
    scan: ScanService = harness.services.scan
    with scan.lock:
        outcome = scan.scan_watch(watch_id)
    assert outcome.status == "skipped_running"
    assert harness.source.calls == []
    assert harness.repo.recent_events()[0].kind == "scan_skipped"


def test_blocked_result_writes_no_observation(harness: Harness) -> None:  # C-6
    watch_id = harness.create_watch()
    harness.source.status_override = "blocked"
    outcome = harness.scan(watch_id)
    assert outcome.status == "failed"
    assert harness.repo.count_observations(watch_id) == 0
    [run] = harness.repo.scan_runs_for_watch(watch_id)
    assert run.query_results[0]["status"] == "blocked"


def test_no_data_is_not_a_failure(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.source.default_price = None
    assert harness.scan(watch_id).status == "ok"
    assert harness.repo.get_source_health("google_flights").consecutive_failures == 0


def test_paused_watch_not_scanned_then_resumed(harness: Harness) -> None:  # AC-A7
    watch_id = harness.create_watch()
    harness.services.watches.set_enabled(watch_id, False)
    assert harness.scan(watch_id).status == "not_scannable"
    assert harness.source.calls == [] and notifications(harness) == []
    harness.services.watches.set_enabled(watch_id, True)
    assert harness.scan(watch_id).status == "ok"


def test_expired_watch_marked_and_not_scanned(harness: Harness) -> None:  # AC-A9
    watch_id = harness.create_watch(depart_date="2026-10-30", return_date="2026-11-02")
    harness.clock.advance(days=6)
    assert harness.scan(watch_id).status == "expired"
    assert harness.repo.get_watch(watch_id).status == "expired"
    assert harness.source.calls == []
    other = harness.create_watch(depart_date="2026-11-05", return_date="2026-11-08")
    harness.clock.advance(days=10)
    assert harness.services.scan.expire_sweep() == [other]


def test_global_hourly_limit(harness: Harness) -> None:
    harness.services.settings.update({"global_hourly_query_limit": "3"})
    watch_id = harness.create_watch(**FLEX)
    outcome = harness.scan(watch_id)
    assert outcome.queries_used == 3 and outcome.status == "partial"
    [run] = harness.repo.scan_runs_for_watch(watch_id)
    assert run.global_limit_reached
    harness.scan(watch_id)
    assert len(harness.source.calls) == 3, "budget is shared within the hour"
    harness.clock.advance(hours=1, minutes=1)
    harness.scan(watch_id)
    assert len(harness.source.calls) == 6


def test_below_budget_alert_and_no_repeat(harness: Harness) -> None:  # AC-C1, AC-C4
    watch_id = harness.create_watch(budget=10000)
    harness.source.default_price = 9500
    harness.scan(watch_id)
    [alert] = notifications(harness)
    assert alert.kind == "price_alert" and alert.status == "sent" and alert.rule == "below_budget"
    assert "低於門檻" in harness.notifier.sent[0]
    harness.scan(watch_id)
    assert len(notifications(harness)) == 1


def test_drop_alert_above_budget(harness: Harness) -> None:  # AC-C2
    watch_id = harness.create_watch(budget=10000)
    harness.source.default_price = 10000
    harness.scan(watch_id)  # 10000 <= budget -> notified, baseline 10000
    harness.source.default_price = 10600
    harness.scan(watch_id)  # back above budget -> re-armed, nothing sent
    harness.services.watches.update(
        watch_id,
        {
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": 9000,
        },
    )
    harness.source.default_price = 9400  # above new budget 9000, 6% below 10000
    harness.scan(watch_id)
    last = notifications(harness)[-1]
    assert last.rule == "drop_pct" and "較上次通知下跌 6%" in last.message_text


def test_new_low_alert(harness: Harness) -> None:  # AC-C3
    watch_id = harness.create_watch(budget=8000)
    harness.source.default_price = 9000
    harness.scan(watch_id)
    assert notifications(harness) == []
    harness.source.default_price = 8800
    harness.scan(watch_id)
    [alert] = notifications(harness)
    assert alert.rule == "new_low" and "此監看紀錄新低" in alert.message_text


def test_failed_delivery_not_marked_and_retried_with_cap(harness: Harness) -> None:  # AC-C7
    watch_id = harness.create_watch(budget=10000)
    harness.source.default_price = 9500
    harness.notifier.fail_with = "ConnectError: unreachable"
    harness.scan(watch_id)
    [alert] = notifications(harness)
    assert alert.status == "failed" and alert.attempts == 1
    assert harness.repo.get_alert_state(watch_id, "live").last_notified_amount_minor is None
    harness.scan(watch_id)  # same price: no duplicate, but retry happens
    [alert] = notifications(harness)
    assert alert.attempts == 2
    harness.notifier.fail_with = None
    harness.scan(watch_id)
    [alert] = notifications(harness)
    assert alert.status == "sent" and alert.attempts == 3
    assert harness.repo.get_alert_state(watch_id, "live").last_notified_amount_minor == 950_000


def test_retry_cap_is_respected(harness: Harness) -> None:
    watch_id = harness.create_watch(budget=10000)
    harness.source.default_price = 9500
    harness.notifier.fail_with = "down"
    for _ in range(5):
        harness.scan(watch_id)
    [alert] = notifications(harness)
    assert alert.status == "failed" and alert.attempts == 3


def test_merged_message_for_many_matches(harness: Harness) -> None:  # AC-C9
    watch_id = harness.create_watch(budget=12000, **FLEX)
    prices = iter(range(9000, 20000, 37))
    harness.source.price_fn = lambda _query: next(prices)
    harness.scan(watch_id)
    [alert] = notifications(harness)
    items = harness.repo.notification_items(alert.id)
    assert len(items) == 5
    assert [i.amount_minor for i in items] == sorted(i.amount_minor for i in items)
    assert len(harness.notifier.sent) == 1


def test_stale_after_repeated_failed_scans(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.source.status_override = "blocked"
    for _ in range(3):
        harness.scan(watch_id)
        harness.clock.advance(minutes=31)
    assert harness.repo.get_watch(watch_id).status == "stale"
    harness.source.status_override = None
    harness.clock.advance(minutes=31)
    harness.scan(watch_id)
    assert harness.repo.get_watch(watch_id).status == "active"


def test_cached_fallback_never_moves_live_low(
    config: Any, clock: FakeClock, notifier: Any
) -> None:  # C-8
    from fastapi.testclient import TestClient

    from flight_deals.app import create_app

    live = ScriptedSource(clock, name="google_flights", price_kind="live")
    cached = ScriptedSource(clock, name="travelpayouts", price_kind="cached", default_price=5000)
    app = create_app(
        config, sources=[live, cached], notifier=notifier, clock=clock, start_scheduler=False
    )
    with TestClient(app, base_url="http://127.0.0.1"):
        services = app.state.assembly.services
        result = services.watches.create(
            {
                "destination": "NRT",
                "depart_date": "2026-12-10",
                "return_date": "2026-12-15",
                "budget": 1000,
            }
        )
        watch_id = result.watch_id
        live.default_price = 9000
        services.scan.scan_watch(watch_id)  # live history low 9000
        live.status_override = "error"
        clock.advance(minutes=1)
        services.scan.scan_watch(watch_id)  # cached 5000 recorded as fallback
        repo = services.watches._repo
        kinds = {o.price_kind for o in repo.observations_for_watch(watch_id)}
        assert kinds == {"live", "cached"}
        live.status_override = None
        live.default_price = 8900
        clock.advance(minutes=1)
        services.scan.scan_watch(watch_id)
        live_alerts = [
            n
            for n in repo.list_notifications()
            if n.kind == "price_alert" and n.price_kind == "live"
        ]
        assert live_alerts and live_alerts[0].rule == "new_low"


def test_edit_route_bumps_revision_and_keeps_history(harness: Harness) -> None:  # AC-A6
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    base = {
        "destination": "NRT",
        "trip_type": "round_trip",
        "date_mode": "fixed",
        "depart_date": "2026-12-10",
        "return_date": "2026-12-15",
    }
    harness.services.watches.update(watch_id, {**base, "budget": 11000})
    assert harness.repo.get_watch(watch_id).revision == 1
    harness.services.watches.update(watch_id, {**base, "destination": "HND", "budget": 11000})
    watch = harness.repo.get_watch(watch_id)
    assert watch.revision == 2
    assert harness.repo.count_observations(watch_id) == 1
    detail = harness.services.views.detail_page(watch_id)
    assert detail["has_prices"] is False
    assert detail["old_prices"] and detail["old_prices"][0]["revision"] == 1
