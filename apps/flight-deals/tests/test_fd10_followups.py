"""Weekday summaries, the three follow-ups and module boundaries (ADR-0002 FD-10
Decisions 7, 9, 10, C-77, C-78, C-79)."""

from __future__ import annotations

import ast
import itertools
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from flight_deals.app import create_app
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    COMMAND_COMPARISON_DEFERRED,
    COMMAND_SCAN_COMPARISON_DEFERRED,
    COMMAND_SCAN_DEFERRED,
    COMMAND_SCAN_FOLLOW_UP,
    DIGEST_MAX_CHARS,
    DIGEST_MAX_WATCH_LINES,
    EXPLORATION_STALE_FALLBACK,
    MAINTENANCE_TABLE_LABELS,
    DigestRow,
    DigestSourceRow,
    all_static_texts,
    command_scan_queued,
    daily_digest_message,
    month_label,
    month_range_label,
)
from flight_deals.domain.models import ComparisonSpec, DatePair, ExplorationSpec, FlightSearch
from flight_deals.domain.trip_labels import depart_weekdays_label
from flight_deals.domain.weekdays import ALL_WEEKDAYS
from flight_deals.services.views import dates_text
from tests.conftest import FakeClock, FakeNotifier, Harness, ScriptedSource
from tests.test_commands import Bot, FakeInbox, bot_config, msg
from tests.test_digest import longest_route, row
from tests.test_fd10_weekdays import FLEX, fixed, window

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
TEMPLATES = SRC / "web" / "templates"
APP_JS = SRC / "web" / "static" / "app.js"
NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)
FORBIDDEN_SUMMARY_WORDS = ("週末", "平日", "假日")


@pytest.fixture
def tg(
    tmp_path: Path, clock: FakeClock, source: ScriptedSource, notifier: FakeNotifier
) -> Iterator[Bot]:
    """Same assembly as ``tests.test_commands.bot``: Telegram commands on a fake inbox."""
    inbox = FakeInbox()
    app = create_app(
        bot_config(tmp_path),
        sources=[source],
        notifier=notifier,
        clock=clock,
        start_scheduler=False,
        inbox=inbox,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield Bot(app.state.assembly, client, clock, source, notifier, inbox)


# ---- the one label helper (C-77) -----------------------------------------------------


def test_label_helper_is_defined_once() -> None:  # C-77
    hits = [
        path
        for path in SRC.rglob("*.py")
        if "def depart_weekdays_label" in path.read_text(encoding="utf-8")
    ]
    assert hits == [SRC / "domain" / "trip_labels.py"]


def test_label_values() -> None:  # C-77, AC-D13
    assert depart_weekdays_label(ALL_WEEKDAYS) is None
    assert depart_weekdays_label((5, 4)) == "週五、週六出發"
    assert depart_weekdays_label((6, 0, 2)) == "週一、週三、週日出發"
    assert depart_weekdays_label((0,)) == "週一出發"


def test_all_127_labels_are_plain() -> None:  # C-77
    labels = []
    for size in range(1, 8):
        for combo in itertools.combinations(ALL_WEEKDAYS, size):
            label = depart_weekdays_label(combo)
            if size == 7:
                assert label is None
                continue
            assert label is not None and label.endswith("出發")
            labels.append(label)
    assert len(labels) == 126
    for label in labels:
        assert not any(word in label for word in FORBIDDEN_SUMMARY_WORDS), label
        assert not any(phrase in label for phrase in BANNED_PHRASES), label


def test_dates_text_appends_weekdays_for_windows_only() -> None:  # C-77
    flex = window(date(2026, 12, 1), date(2026, 12, 31))
    assert dates_text(flex) == "彈性 2026-12-01 ～ 2026-12-31，旅程 3–5 天"  # unchanged
    filtered = window(date(2026, 12, 1), date(2026, 12, 31), weekdays=(5, 4))
    assert dates_text(filtered) == "彈性 2026-12-01 ～ 2026-12-31，旅程 3–5 天，週五、週六出發"
    one_way = window(date(2026, 12, 1), date(2026, 12, 31), one_way=True, weekdays=(4,))
    assert dates_text(one_way) == "彈性出發 2026-12-01 ～ 2026-12-31，週五出發"
    # Fixed dates never show weekdays, whatever the field holds.
    assert dates_text(fixed(date(2026, 12, 10), date(2026, 12, 15), (4,))) == (
        "固定 2026-12-10 出發，2026-12-15 回程"
    )
    assert dates_text(fixed(date(2026, 12, 10), None, (4,))) == "固定 2026-12-10 出發"


def test_list_detail_and_digest_show_weekdays(harness: Harness) -> None:  # C-77, AC-D12
    filtered = harness.create_watch(**FLEX, depart_weekdays=[5, 4])
    plain = harness.create_watch(**{**FLEX, "name": "全選"})
    page = harness.client.get("/").text
    assert page.count("週五、週六出發") == 1
    detail = harness.services.views.detail_page(filtered)["watch"]
    assert detail["dates"].endswith("，週五、週六出發")
    assert detail["weekdays_label"] == "週五、週六出發"
    plain_detail = harness.services.views.detail_page(plain)["watch"]
    assert plain_detail["weekdays_label"] is None and "出發" not in plain_detail["dates"]
    text = harness.services.digest.compose(harness.clock())
    lines = [line for line in text.splitlines() if line.startswith("• ")]
    assert any("週五、週六出發" in line and "東京" in line for line in lines)
    assert any(line.startswith("• 全選") and "出發" not in line for line in lines)


def test_digest_row_keeps_fd9_wording_without_weekdays() -> None:  # C-77
    base = row("東京", "TPE", "NRT")
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        stale_after_hours=24,
        rows=[base],
    )
    line = next(line for line in text.splitlines() if line.startswith("• "))
    assert "出發" not in line
    with_days = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        stale_after_hours=24,
        rows=[replace(base, weekdays_label="週五、週六出發")],
    )
    new_line = next(line for line in with_days.splitlines() if line.startswith("• "))
    parts, new_parts = line.split("｜"), new_line.split("｜")
    assert new_parts == [*parts[:3], "週五、週六出發", *parts[3:]]  # after the cabin part


def test_digest_length_cap_with_six_weekdays_each() -> None:  # C-34 with weekdays (C-77)
    origin, destination = longest_route()
    label = depart_weekdays_label((0, 1, 2, 3, 4, 5))
    rows: list[DigestRow] = []
    for _ in range(200):
        base = row("名" * 80, origin, destination)
        rows.append(replace(base, weekdays_label=label))
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[DigestSourceRow("google_flights", "異常", "open")],
        last_scan_at=NOW,
        failed_scans_24h=12,
        stale_after_hours=24,
        rows=rows,
    )
    assert len(text) <= DIGEST_MAX_CHARS
    watch_lines = [line for line in text.splitlines() if line.startswith("• ")]
    assert 0 < len(watch_lines) <= DIGEST_MAX_WATCH_LINES
    assert all(str(label) in line for line in watch_lines)


def test_watch_command_shows_weekdays(tg: Bot) -> None:  # C-77, AC-T1
    filtered = tg.create_watch(**FLEX, depart_weekdays=[4, 5])
    plain = tg.create_watch(**{**FLEX, "name": "全選"})
    tg.send(msg(1, f"/watch {filtered}"), msg(2, f"/watch {plain}"))
    first, second = tg.notifier.sent[-2:]
    assert "日期：彈性 2026-12-01 ～ 2026-12-31，旅程 3–5 天，週五、週六出發" in first
    assert "日期：彈性 2026-12-01 ～ 2026-12-31，旅程 3–5 天\n" in second


def test_new_strings_are_static_and_clean() -> None:  # C-77
    texts = all_static_texts()
    for text in (
        "未查（星期篩選）",
        "請至少選一個出發星期",
        "所選日期區間內沒有符合出發星期的日子",
        "請縮小月份範圍或減少星期",
        COMMAND_COMPARISON_DEFERRED,
        COMMAND_SCAN_COMPARISON_DEFERRED,
        EXPLORATION_STALE_FALLBACK,
        "只比較所選月份內符合出發星期、且有查到價格的出發日。",
        "週五、週六出發",
        month_range_label(2026, 12, 2027, 2),
        "比價",
        "比價明細",
    ):
        assert text in texts, text
    for text in texts:
        assert not any(p in text for p in BANNED_PHRASES), text
        assert not any(word in text for word in FORBIDDEN_SUMMARY_WORDS), text


def test_month_range_label() -> None:  # C-77
    assert month_range_label(2026, 12, 2026, 12) == month_label(2026, 12) == "2026 年 12 月"
    assert month_range_label(2026, 12, 2027, 2) == "2026 年 12 月～2027 年 2 月"


def test_templates_and_script_have_no_advisory_words() -> None:  # C-77
    for path in [*TEMPLATES.glob("*.html"), APP_JS]:
        text = path.read_text(encoding="utf-8")
        for word in ("建議", "推薦", "最佳", "划算", "現在買", *FORBIDDEN_SUMMARY_WORDS):
            assert word not in text, (path.name, word)


# ---- F1: /status and /scan during a comparison (C-78) ----------------------------------


def running_comparison(tg: Bot, done: int = 3) -> int:
    spec = ComparisonSpec(
        "TPE",
        ("NRT", "KIX", "ICN", "BKK", "SIN", "HKG", "MNL", "CTS"),
        "one_way",
        date(2026, 12, 10),
        None,
        None,
    )
    comparison_id = tg.repo.insert_comparison(spec, tg.clock.now)
    with tg.assembly.database.connect() as conn:
        conn.execute(
            "UPDATE comparison SET status = 'running', done = ? WHERE id = ?",
            (done, comparison_id),
        )
    return int(comparison_id)


def status_lines(tg: Bot, update_id: int) -> list[str]:
    tg.send(msg(update_id, "/status"))
    return tg.notifier.sent[-1].splitlines()


def test_status_without_comparison_is_unchanged(tg: Bot) -> None:  # C-78
    lines = status_lines(tg, 1)
    assert lines[-1] == "探索：目前沒有進行中的探索"
    assert not any("比價" in line for line in lines)


def test_status_during_comparison(tg: Bot) -> None:  # C-78, AC-F1
    running_comparison(tg)
    lines = status_lines(tg, 1)
    assert lines[-2:] == [
        "探索：目前沒有進行中的探索",
        "比價：進行中（已查 3／共 8），排程掃描順延",
    ]


def test_status_with_range_exploration_and_comparison(tg: Bot) -> None:  # C-78
    spec = ExplorationSpec(
        "TPE",
        "NRT",
        "round_trip",
        2026,
        12,
        5,
        None,
        end_year=2027,
        end_month=2,
        depart_weekdays=(4, 5),
    )
    pairs = [DatePair(date(2026, 12, d)) for d in (4, 5)]
    tg.repo.insert_exploration(spec, pairs, tg.clock.now)
    running_comparison(tg, done=0)
    lines = status_lines(tg, 1)
    assert "2026 年 12 月～2027 年 2 月" in lines[-2] and lines[-2].endswith("已查 0／共 2")
    assert lines[-1] == "比價：進行中（已查 0／共 8），排程掃描順延"


def scan_reply(tg: Bot, watch_id: int, update_id: int) -> str:
    tg.send(msg(update_id, f"/scan {watch_id}"))
    return str(tg.notifier.sent[-1])


def test_scan_without_comparison_is_unchanged(tg: Bot) -> None:  # C-78
    tg.scheduler_on()
    watch_id = tg.create_watch()
    reply = scan_reply(tg, watch_id, 1)
    assert reply == "\n".join([command_scan_queued(watch_id, "TPE→NRT"), COMMAND_SCAN_FOLLOW_UP])
    assert tg.scans == [watch_id]


def test_scan_during_comparison(tg: Bot) -> None:  # C-78, AC-F1
    tg.scheduler_on()
    watch_id = tg.create_watch()
    running_comparison(tg)
    reply = scan_reply(tg, watch_id, 1)
    assert reply.splitlines() == [
        command_scan_queued(watch_id, "TPE→NRT"),
        COMMAND_SCAN_COMPARISON_DEFERRED,
        COMMAND_SCAN_FOLLOW_UP,
    ]
    assert "比價進行中，掃描順延" in reply
    assert tg.scans == [watch_id]  # scheduled exactly once


def test_scan_during_exploration_keeps_its_note(tg: Bot) -> None:  # C-78
    tg.scheduler_on()
    watch_id = tg.create_watch()
    spec = ExplorationSpec("TPE", "NRT", "one_way", 2026, 12, None, None)
    tg.repo.insert_exploration(spec, [DatePair(date(2026, 12, 1))], tg.clock.now)
    reply = scan_reply(tg, watch_id, 1)
    assert reply.splitlines()[1] == COMMAND_SCAN_DEFERRED
    assert COMMAND_SCAN_COMPARISON_DEFERRED not in reply


# ---- F2: table counts (C-78) -----------------------------------------------------------


def test_table_counts_rows_and_one_statement(harness: Harness) -> None:  # C-78, AC-F2
    statements: list[str] = []
    database = harness.repo.db
    real = database.connect

    @contextmanager
    def traced() -> Any:
        with real() as conn:
            conn.set_trace_callback(statements.append)
            yield conn

    database.connect = traced
    try:
        counts = harness.repo.table_counts()
    finally:
        database.connect = real
    assert [name for name, _ in counts] == [
        "watch",
        "scan_run",
        "price_observation",
        "notification",
        "exploration",
        "comparison",
        "comparison_cell",
    ]
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1
    assert list(MAINTENANCE_TABLE_LABELS)[-2:] == ["comparison", "comparison_cell"]
    page = harness.client.get("/settings").text
    explore_at = page.index(">探索<")
    assert explore_at < page.index(">比價<") < page.index(">比價明細<")


# ---- F3: stale fallback lives in messages (C-78) ---------------------------------------


def test_stale_fallback_moved_to_messages() -> None:  # C-78, AC-F3
    template = (TEMPLATES / "exploration.html").read_text(encoding="utf-8")
    assert EXPLORATION_STALE_FALLBACK not in template
    assert "e.stale_fallback" in template
    source = (SRC / "domain" / "messages.py").read_text(encoding="utf-8")
    assert 'EXPLORATION_STALE_FALLBACK = "這是較早前查到的價格，可能已變動。"' in source


# ---- module boundaries (C-79) -----------------------------------------------------------


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_validation_does_not_import_dates() -> None:  # C-79
    assert "flight_deals.domain.dates" not in imports(SRC / "domain" / "validation.py")


def test_services_import_no_outer_layers() -> None:  # C-79
    for path in (SRC / "services").rglob("*.py"):
        for name in imports(path):
            assert not re.match(r"flight_deals\.(sources|scheduler|web)\b", name), (path, name)


def test_app_js_has_no_banned_apis() -> None:  # C-79
    script = APP_JS.read_text(encoding="utf-8")
    for api in ("getDay", "getUTCDay", "innerHTML"):
        assert api not in script, api


def test_weekdays_never_reach_a_query() -> None:  # Decision 10: FlightSearch unchanged
    assert "depart_weekdays" not in {f.name for f in fields(FlightSearch)}


def test_flight_search_is_built_only_in_domain() -> None:  # C-72
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "FlightSearch(" in p.read_text(encoding="utf-8")
    ]
    assert hits == ["domain/models.py"]
