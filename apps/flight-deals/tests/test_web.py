"""Web pages and JSON API (AC-A*, AC-B7, AC-C8, AC-D*, AC-E*, C-12, C-14)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from flight_deals.app import create_app
from flight_deals.config import Config
from flight_deals.web.server import WEB_DIR
from tests.conftest import CLIENT_HEADERS, FakeClock, FakeNotifier, Harness, ScriptedSource

VALID = {
    "destination": "NRT",
    "trip_type": "round_trip",
    "date_mode": "fixed",
    "depart_date": "2026-12-10",
    "return_date": "2026-12-15",
    "budget": "12000",
}


def post(h: Harness, url: str, body: Any = None) -> Any:
    return h.client.post(url, json=body if body is not None else {}, headers=CLIENT_HEADERS)


def test_create_minimal_watch_and_list(harness: Harness) -> None:  # AC-A1
    response = post(
        harness,
        "/api/watches",
        {
            "destination": "nrt",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": 12000,
        },
    )
    assert response.status_code == 201
    watch = harness.repo.get_watch(response.json()["id"])
    assert watch.spec.origin == "TPE" and watch.spec.destination == "NRT"
    page = harness.client.get("/").text
    assert "TPE→NRT" in page and "尚未查價" in page and "啟用中" in page
    detail = harness.client.get(f"/watches/{watch.id}").text
    assert "1 位成人" in detail and "經濟艙" in detail


def test_flexible_settings_shown_on_detail(harness: Harness) -> None:  # AC-A2
    body = {
        **VALID,
        "date_mode": "flexible",
        "window_start": "2027-06-01",
        "window_end": "2027-06-30",
        "min_trip_days": "4",
        "max_trip_days": "6",
    }
    watch_id = post(harness, "/api/watches", body).json()["id"]
    page = harness.client.get(f"/watches/{watch_id}").text
    assert "2027-06-01" in page and "2027-06-30" in page and "4–6 天" in page


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"destination": ""}, "destination"),
        ({"return_date": "2026-12-01"}, "return_date"),
        (
            {
                "date_mode": "flexible",
                "window_start": "2026-12-01",
                "window_end": "2026-12-31",
                "min_trip_days": "7",
                "max_trip_days": "5",
            },
            "min_trip_days",
        ),
        ({"budget": "0"}, "budget"),
        ({"destination": "TPE"}, "destination"),
        ({"depart_date": "2026-01-01"}, "depart_date"),
    ],
)
def test_invalid_submissions_rejected(
    harness: Harness, override: dict[str, Any], field: str
) -> None:
    response = post(harness, "/api/watches", {**VALID, **override})  # AC-A4
    assert response.status_code == 422
    assert field in response.json()["errors"]
    assert harness.repo.list_watches() == []


def test_list_shows_price_or_not_yet(harness: Harness) -> None:  # AC-A5
    ids = [harness.create_watch(destination=d) for d in ("NRT", "KIX", "BKK")]
    harness.scan(ids[0])
    page = harness.client.get("/").text
    assert page.count("尚未查價") >= 2
    assert "TWD 10,000" in page


def test_edit_form_and_update(harness: Harness) -> None:  # AC-A6 via API
    watch_id = harness.create_watch()
    assert harness.client.get(f"/watches/{watch_id}/edit").status_code == 200
    response = harness.client.put(
        f"/api/watches/{watch_id}", json={**VALID, "destination": "HND"}, headers=CLIENT_HEADERS
    )
    assert response.status_code == 200
    assert harness.repo.get_watch(watch_id).revision == 2


def test_old_revision_prices_labelled(harness: Harness) -> None:  # AC-A6
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.client.put(
        f"/api/watches/{watch_id}", json={**VALID, "destination": "HND"}, headers=CLIENT_HEADERS
    )
    page = harness.client.get(f"/watches/{watch_id}").text
    assert "舊設定" in page and "尚未查到價格" in page


def test_disable_enable_and_delete(harness: Harness) -> None:  # AC-A7, AC-A8
    watch_id = harness.create_watch()
    assert post(harness, f"/api/watches/{watch_id}/status", {"enabled": False}).status_code == 200
    assert harness.repo.get_watch(watch_id).status == "paused"
    assert "已停用" in harness.client.get("/").text
    assert post(harness, f"/api/watches/{watch_id}/scan").status_code == 409
    assert post(harness, f"/api/watches/{watch_id}/status", {"enabled": True}).status_code == 200
    response = harness.client.delete(f"/api/watches/{watch_id}", headers=CLIENT_HEADERS)
    assert response.status_code == 200
    assert harness.client.get(f"/watches/{watch_id}").status_code == 404
    assert (
        harness.client.delete(f"/api/watches/{watch_id}", headers=CLIENT_HEADERS).status_code == 404
    )


def test_delete_requires_confirmation_in_page_script() -> None:  # AC-A8
    script = (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "window.confirm(" in script
    assert re.search(r"if \(!confirmed\) return;", script)


def test_scan_now_runs_and_writes_history(harness: Harness) -> None:  # AC-B7
    watch_id = harness.create_watch()
    harness.services.watches.hooks.trigger_scan = lambda wid: harness.scan(wid, "manual") and None
    response = post(harness, f"/api/watches/{watch_id}/scan")
    assert response.status_code == 202
    assert harness.repo.count_observations(watch_id) == 1
    assert harness.repo.scan_runs_for_watch(watch_id)[0].trigger == "manual"


def test_detail_sections(harness: Harness) -> None:  # AC-D1..D5, AC-B3
    harness.services.settings.update({"max_pairs_per_scan": "4"})
    watch_id = harness.create_watch(
        date_mode="flexible",
        window_start="2026-12-01",
        window_end="2026-12-20",
        min_trip_days=4,
        max_trip_days=5,
    )
    harness.source.price_fn = lambda q: 9000 + q.pair.depart.day * 100
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    harness.source.price_fn = lambda q: 8500 + q.pair.depart.day * 100
    harness.scan(watch_id)
    page = harness.client.get(f"/watches/{watch_id}").text
    assert "最低價趨勢" in page and "<polyline" in page
    prices = [int(p.replace(",", "")) for p in re.findall(r"查到 TWD ([\d,]+)", page)[:4]]
    assert prices == sorted(prices)
    assert "依出發日的價格分布" in page and "heat-cheap" in page
    assert "本次取樣的日期組合" in page and "達上限" in page
    # Current-revision rows link the exact tfs search (FD-5 Decision 7).
    assert "https://www.google.com/travel/flights/search?tfs=" in page
    assert 'badge warn">可能已過期' not in page
    harness.clock.advance(hours=30)
    stale_page = harness.client.get(f"/watches/{watch_id}").text
    assert stale_page.count('badge warn">可能已過期') >= 4  # AC-D4


def test_empty_detail_state(harness: Harness) -> None:  # AC-D6
    watch_id = harness.create_watch()
    response = harness.client.get(f"/watches/{watch_id}")
    assert response.status_code == 200 and "尚未查到價格" in response.text


def test_notification_log_page(harness: Harness) -> None:  # AC-C8
    watch_id = harness.create_watch(budget=10500)
    harness.scan(watch_id)
    harness.notifier.fail_with = "boom"
    post(harness, "/api/telegram/test")
    page = harness.client.get("/notifications").text
    assert "價格通知" in page and "低於門檻" in page and "TWD 10,000" in page
    assert "成功" in page and "失敗" in page and "boom" in page


def test_settings_health_page(harness: Harness) -> None:  # AC-E1, AC-E5
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    page = harness.client.get("/settings").text
    for needle in (
        "資料源狀態",
        "Google Flights",
        "正常",
        "上次掃描",
        "下次預計掃描",
        "最近一輪各監看查詢次數",
        "對外查詢次數",
    ):
        assert needle in page


def test_settings_update_and_validation(harness: Harness) -> None:  # AC-E4
    bad = post(harness, "/api/settings", {"scan_interval_minutes": "0", "max_pairs_per_scan": "x"})
    assert bad.status_code == 422
    assert set(bad.json()["errors"]) == {"scan_interval_minutes", "max_pairs_per_scan"}
    good = post(
        harness,
        "/api/settings",
        {
            "scan_interval_minutes": "180",
            "max_pairs_per_scan": "8",
            "drop_threshold_bp": "300",
            "stale_after_hours": "12",
            "global_hourly_query_limit": "40",
        },
    )
    assert good.status_code == 200
    current = harness.services.settings.current()
    assert (current.scan_interval_minutes, current.max_pairs_per_scan) == (180, 8)
    assert current.drop_threshold_bp == 300 and current.stale_after_hours == 12


def test_telegram_test_send_reports_result(harness: Harness) -> None:  # AC-E3
    ok = post(harness, "/api/telegram/test")
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert harness.notifier.sent and "測試訊息" in harness.notifier.sent[-1]
    harness.notifier.fail_with = "HTTP 401: Unauthorized"
    failed = post(harness, "/api/telegram/test")
    assert failed.status_code == 502 and "401" in failed.json()["error"]


def test_telegram_status_never_reveals_token(tmp_path: Path, clock: FakeClock) -> None:  # AC-E2
    token = "123456789:AAFakeTokenValue_for-tests-only"
    config = Config(db_path=tmp_path / "t.db", telegram_bot_token=token, telegram_chat_id="42")
    app = create_app(config, sources=[ScriptedSource(clock)], clock=clock, start_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        page = client.get("/settings").text
        assert "已設定" in page and token not in page and "AAFakeTokenValue" not in page
    unconfigured = create_app(
        Config(db_path=tmp_path / "u.db"),
        sources=[],
        notifier=FakeNotifier(configured=False),
        clock=clock,
        start_scheduler=False,
    )
    with TestClient(unconfigured, base_url="http://127.0.0.1") as client:
        page = client.get("/settings").text
        assert "未設定" in page and "BotFather" in page


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "/api/watches"),
        ("PUT", "/api/watches/1"),
        ("POST", "/api/watches/1/status"),
        ("DELETE", "/api/watches/1"),
        ("POST", "/api/watches/1/scan"),
        ("POST", "/api/settings"),
        ("POST", "/api/telegram/test"),
    ],
)
def test_writes_without_client_header_are_forbidden(
    harness: Harness, method: str, url: str
) -> None:
    harness.create_watch()
    response = harness.client.request(method, url, json=VALID)  # C-12
    assert response.status_code == 403
    assert harness.notifier.sent == []
    assert len(harness.repo.list_watches()) == 1


def test_untrusted_host_rejected(harness: Harness) -> None:  # C-12 / AC-E6
    assert harness.client.get("/", headers={"host": "evil.example"}).status_code == 400
    assert harness.client.get("/", headers={"host": "localhost"}).status_code == 200
    assert (
        harness.client.get("/").headers["content-security-policy"].startswith("default-src 'self'")
    )


def test_pages_load_no_external_resources(harness: Harness) -> None:  # C-14
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    for url in (
        "/",
        "/watches/new",
        f"/watches/{watch_id}",
        f"/watches/{watch_id}/edit",
        "/notifications",
        "/settings",
    ):
        html = harness.client.get(url).text
        for tag in re.findall(r"<(?:script|link|img|iframe)\b[^>]*>", html):
            assert (
                "http://" not in tag
                and "https://" not in tag
                and "//" not in tag.replace("/static/", "")
            ), tag
        assert re.search(r"<form[^>]*\bmethod=", html) is None, "no native form POST"


def test_static_assets_are_local_plain_files() -> None:  # C-14
    static = WEB_DIR / "static"
    assert sorted(p.suffix for p in static.iterdir()) == [".css", ".js"]
    js = (static / "app.js").read_text(encoding="utf-8")
    css = (static / "app.css").read_text(encoding="utf-8")
    assert "http://" not in js and "https://" not in js and "import " not in js
    assert "@import" not in css and "url(" not in css
    assert "prefers-color-scheme: dark" in css


def test_disclaimer_shown(harness: Harness) -> None:  # FR-C5
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    assert "價格為查到當下的參考值" in harness.client.get(f"/watches/{watch_id}").text


def test_notifier_default_unconfigured_is_suppressed(tmp_path: Path, clock: FakeClock) -> None:
    notifier = FakeNotifier(configured=False)
    source = ScriptedSource(clock)
    app = create_app(
        Config(db_path=tmp_path / "x.db"),
        sources=[source],
        notifier=notifier,
        clock=clock,
        start_scheduler=False,
    )
    with TestClient(app, base_url="http://127.0.0.1"):
        services = app.state.assembly.services
        watch_id = services.watches.create({**VALID, "budget": 20000}).watch_id
        services.scan.scan_watch(watch_id)
        [record] = services.watches._repo.list_notifications()
        assert record.status == "suppressed" and notifier.attempts == 0


def test_every_page_has_footer_disclaimer_from_constant(harness: Harness) -> None:
    from flight_deals.domain.messages import DISCLAIMER

    base = (WEB_DIR / "templates" / "base.html").read_text(encoding="utf-8")
    assert DISCLAIMER not in base and "{{ disclaimer }}" in base
    watch_id = harness.create_watch()
    for url in (
        "/",
        "/watches/new",
        f"/watches/{watch_id}",
        f"/watches/{watch_id}/edit",
        "/notifications",
        "/settings",
        "/watches/9999",
    ):
        html = harness.client.get(url).text
        footer = html.split('<footer class="site-footer">', 1)[1]
        assert DISCLAIMER in footer, url


def test_date_inputs_have_taipei_today_min(harness: Harness) -> None:
    html = harness.client.get("/watches/new").text
    assert html.count('min="2026-10-25"') == 4  # FakeClock 04:00Z = 12:00 Asia/Taipei


def test_list_column_and_sampling_notes(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    assert "已查到最低價" in harness.client.get("/").text
    harness.client.put(
        f"/api/watches/{watch_id}", json={**VALID, "destination": "HND"}, headers=CLIENT_HEADERS
    )
    harness.scan(watch_id)
    page = harness.client.get(f"/watches/{watch_id}").text
    top = page.split("最便宜的日期組合", 1)[1].split("</section>", 1)[0]
    old = page.split("舊設定的價格紀錄", 1)[1].split("</section>", 1)[0]
    for section in (top, old):
        assert "只涵蓋已取樣的日期" in section
        assert "價格為查到當下的參考值" in section
    assert "muted-badge" not in page


def test_every_status_value_has_badge_style() -> None:
    css = (WEB_DIR / "static" / "app.css").read_text(encoding="utf-8")
    values = {
        "status": ("active", "paused", "stale", "expired"),
        "health": ("ok", "warn", "down", "unknown"),
        "notif": ("pending", "sent", "failed", "suppressed"),
        "run": ("running", "ok", "partial", "failed"),
        "q": ("ok", "no_data", "blocked", "error", "skipped", "currency_mismatch"),
    }
    missing = [
        f".{prefix}-{value}"
        for prefix, items in values.items()
        for value in items
        if re.search(rf"\.{prefix}-{value}(?![\w-])", css) is None
    ]
    assert missing == []
