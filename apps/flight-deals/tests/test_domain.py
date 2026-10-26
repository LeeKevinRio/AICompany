"""Pure domain logic: dates, sampling, validation, rules, money, links, wording."""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest

from flight_deals.domain.currency import format_money, major_to_minor, minor_to_major_str
from flight_deals.domain.dates import expand_pairs, is_expired, sample_pairs
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DISCLAIMER,
    all_static_texts,
    ops_failure_message,
    price_alert_message,
    telegram_test_message,
)
from flight_deals.domain.models import DatePair, WatchSpec
from flight_deals.domain.rules import (
    AlertBaseline,
    Candidate,
    TriggeredItem,
    drop_percent,
    evaluate_price_alerts,
    ops_failure_key,
    price_item_key,
    should_rearm,
    telegram_test_key,
)
from flight_deals.domain.timeutil import taipei_date, to_utc_iso
from flight_deals.domain.validation import (
    setting_rules,
    validate_settings,
    validate_watch_input,
)

TODAY = date(2026, 10, 25)
SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
NOW = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)


def spec(**overrides: Any) -> WatchSpec:
    values: dict[str, Any] = dict(
        name="t",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        date_mode="flexible",
        depart_date=None,
        return_date=None,
        window_start=date(2026, 12, 1),
        window_end=date(2026, 12, 10),
        min_trip_days=4,
        max_trip_days=6,
        max_stops=None,
        budget_amount_minor=major_to_minor(12000, "TWD"),
    )
    values.update(overrides)
    return WatchSpec(**values)


# ---- dates & sampling ---------------------------------------------------------


def test_expand_flexible_round_trip_pairs_respect_window_and_lengths() -> None:
    pairs = expand_pairs(spec(), TODAY)
    assert pairs[0] == DatePair(date(2026, 12, 1), date(2026, 12, 5))
    assert all(4 <= (p.return_date - p.depart).days <= 6 for p in pairs if p.return_date)
    assert all(p.return_date and p.return_date <= date(2026, 12, 10) for p in pairs)
    assert len(pairs) == 15  # departs 12/1..12/6 with 4-6 day stays inside the window


def test_expand_fixed_only_queries_that_pair() -> None:  # AC-A3
    s = spec(
        date_mode="fixed",
        depart_date=date(2027, 7, 1),
        return_date=date(2027, 7, 6),
        window_start=None,
        window_end=None,
        min_trip_days=None,
        max_trip_days=None,
    )
    assert expand_pairs(s, TODAY) == [DatePair(date(2027, 7, 1), date(2027, 7, 6))]


def test_one_way_flexible_lists_each_departure_day() -> None:
    s = spec(trip_type="one_way", min_trip_days=None, max_trip_days=None)
    pairs = expand_pairs(s, TODAY)
    assert len(pairs) == 10 and all(p.return_date is None for p in pairs)


def test_past_dates_are_dropped_and_expiry_detected() -> None:  # AC-A9
    s = spec(window_start=date(2026, 10, 1), window_end=date(2026, 10, 20))
    assert is_expired(s, TODAY)
    partially = spec(window_start=date(2026, 10, 20), window_end=date(2026, 11, 5))
    assert all(p.depart >= TODAY for p in expand_pairs(partially, TODAY))


def test_sampling_caps_and_rotates_for_coverage() -> None:  # FR-B3 / FR-B4
    pairs = [DatePair(date(2026, 12, 1 + i)) for i in range(30)]
    seen: set[DatePair] = set()
    offset = 0
    for _ in range(3):
        sampled, offset, truncated = sample_pairs(pairs, 10, offset)
        assert truncated and len(sampled) == 10 and len(set(sampled)) == 10
        seen.update(sampled)
    assert seen == set(pairs)


def test_sampling_without_truncation_returns_all() -> None:
    pairs = [DatePair(date(2026, 12, 1))]
    assert sample_pairs(pairs, 12, 5) == (pairs, 0, False)


# ---- validation (AC-A1, AC-A2, AC-A4) ------------------------------------------


def base_input(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "destination": "NRT",
        "trip_type": "round_trip",
        "date_mode": "fixed",
        "depart_date": "2026-12-10",
        "return_date": "2026-12-15",
        "budget": "12000",
    }
    raw.update(overrides)
    return raw


def test_defaults_applied_on_create() -> None:
    outcome = validate_watch_input(base_input(), TODAY)
    assert outcome.spec is not None
    assert outcome.spec.origin == "TPE"
    assert outcome.spec.budget_amount_minor == 1_200_000
    assert outcome.spec.name == "TPE→NRT"


def test_flexible_settings_round_trip() -> None:
    outcome = validate_watch_input(
        base_input(
            date_mode="flexible",
            window_start="2027-06-01",
            window_end="2027-06-30",
            min_trip_days="4",
            max_trip_days="6",
        ),
        TODAY,
    )
    assert outcome.spec is not None
    assert outcome.spec.window_start == date(2027, 6, 1)
    assert (outcome.spec.min_trip_days, outcome.spec.max_trip_days) == (4, 6)


@pytest.mark.parametrize(
    ("overrides", "field"),
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
        ({"budget": "-5"}, "budget"),
        ({"budget": "abc"}, "budget"),
        ({"destination": "TPE"}, "destination"),
        ({"depart_date": "2026-10-01"}, "depart_date"),
        ({"max_stops": "5"}, "max_stops"),
        ({"destination": "TOKYO"}, "destination"),
    ],
)
def test_invalid_input_rejected_with_field_error(overrides: dict[str, Any], field: str) -> None:
    outcome = validate_watch_input(base_input(**overrides), TODAY)
    assert outcome.spec is None
    assert field in outcome.errors and outcome.errors[field]


def test_edit_keeps_unchanged_past_window_start() -> None:
    existing = spec(window_start=date(2026, 10, 1), window_end=date(2026, 12, 31))
    raw = base_input(
        date_mode="flexible",
        window_start="2026-10-01",
        window_end="2026-12-31",
        min_trip_days="4",
        max_trip_days="6",
        budget="9000",
    )
    assert validate_watch_input(raw, TODAY, existing).spec is not None
    assert validate_watch_input(raw, TODAY).spec is None


def test_settings_validation_rejects_zero_negative_and_text() -> None:  # AC-E4
    rules = setting_rules(30)
    for bad in ("0", "-1", "abc", ""):
        values, errors = validate_settings({"max_pairs_per_scan": bad}, rules)
        assert "max_pairs_per_scan" in errors and not values
    values, errors = validate_settings({"scan_interval_minutes": "10"}, rules)
    assert "scan_interval_minutes" in errors
    values, errors = validate_settings({"drop_threshold_bp": "600"}, rules)
    assert values == {"drop_threshold_bp": 600} and not errors
    _, errors = validate_settings({"unknown": "1"}, rules)
    assert "unknown" in errors


# ---- notification rules (AC-C1..C4, C-8) ----------------------------------------


def cand(
    amount_major: int, *, kind: str = "live", day: int = 10, currency: str = "TWD"
) -> Candidate:
    return Candidate(
        observation_id=None,
        depart_date=date(2026, 12, day),
        return_date=date(2026, 12, day + 5),
        amount_minor=major_to_minor(amount_major, currency),
        currency=currency,
        price_kind=kind,  # type: ignore[arg-type]
        source="google_flights",
        carrier="X",
        fetched_at=NOW,
    )


def evaluate(
    candidates: list[Candidate],
    *,
    budget: int | None = 10000,
    last: int | None = None,
    low: int | None = None,
    armed: bool = True,
    keys: set[str] | None = None,
    kind: str = "live",
    max_items: int = 5,
) -> list[TriggeredItem]:
    return evaluate_price_alerts(
        candidates,
        watch_id=1,
        price_kind=kind,  # type: ignore[arg-type]
        currency="TWD",
        budget_amount_minor=major_to_minor(budget, "TWD") if budget else None,
        notify_on_new_low=True,
        drop_threshold_bp=500,
        baseline=AlertBaseline(
            last_notified_amount_minor=major_to_minor(last, "TWD") if last else None,
            armed=armed,
            historical_min_amount_minor=major_to_minor(low, "TWD") if low else None,
        ),
        already_notified_keys=keys or set(),
        max_items=max_items,
    )


def test_below_budget_triggers() -> None:  # AC-C1
    items = evaluate([cand(9500)])
    assert items and items[0].reasons == ("below_budget",)


def test_drop_percentage_triggers_above_budget() -> None:  # AC-C2
    items = evaluate([cand(9400)], budget=9000, last=10000)
    assert items and items[0].reasons == ("drop_pct",) and items[0].drop_percent == 6
    assert evaluate([cand(9600)], budget=9000, last=10000) == []


def test_new_low_triggers() -> None:  # AC-C3
    items = evaluate([cand(8800)], budget=8000, low=9000)
    assert items and "new_low" in items[0].reasons


def test_same_pair_same_price_not_repeated() -> None:  # AC-C4
    c = cand(9500)
    key = price_item_key(1, "live", c.depart_date, c.return_date, c.amount_minor)
    assert evaluate([c], keys={key}) == []
    assert evaluate([cand(9400)], keys={key})  # price changed -> may trigger again


def test_cached_prices_never_compete_with_live_baseline() -> None:  # C-8
    cached = cand(5000, kind="cached")
    assert evaluate([cached], budget=None, low=9000, kind="live") == []
    live = evaluate([cand(8999)], budget=None, low=9000, kind="live")
    assert live and live[0].reasons == ("new_low",)


def test_currency_mismatch_excluded() -> None:
    assert evaluate([cand(100, currency="USD")]) == []


def test_merged_items_are_cheapest_first_and_capped() -> None:  # AC-C9
    items = evaluate([cand(9000 + i * 10, day=1 + i) for i in range(8)], max_items=5)
    assert len(items) == 5
    assert [i.candidate.amount_minor for i in items] == sorted(
        i.candidate.amount_minor for i in items
    )


def test_disarmed_budget_rule_and_rearm() -> None:
    assert evaluate([cand(9500)], armed=False) == []
    assert should_rearm(major_to_minor(10500, "TWD"), major_to_minor(10000, "TWD"))
    assert not should_rearm(major_to_minor(9500, "TWD"), major_to_minor(10000, "TWD"))


def test_drop_percent_is_integer_math() -> None:
    assert drop_percent(10000, 9400) == 6
    assert drop_percent(10000, 10100) == 0


def test_ops_key_uses_taipei_calendar_day() -> None:  # C-9
    late_utc = datetime(2026, 10, 25, 16, 30, tzinfo=UTC)  # 00:30 on 10/26 in Taipei
    assert ops_failure_key("google_flights", late_utc) == "ops:google_flights:2026-10-26"
    assert ops_failure_key("google_flights", NOW) == "ops:google_flights:2026-10-25"


def test_test_keys_are_unique_per_call() -> None:
    a = telegram_test_key(NOW)
    b = telegram_test_key(NOW.replace(microsecond=1))
    assert a != b


# ---- money, time, links ------------------------------------------------------------


def test_money_is_integer_minor_units() -> None:  # C-13
    assert major_to_minor(10088, "TWD") == 1008800
    assert format_money(1008800, "TWD") == "TWD 10,088"
    assert minor_to_major_str(1008850, "TWD") == "10,088.50"
    assert format_money(5000, "JPY") == "JPY 5,000"
    with pytest.raises(TypeError):
        major_to_minor(10.5, "TWD")  # type: ignore[arg-type]


def test_timestamps_are_utc_and_travel_dates_unconverted() -> None:  # C-13
    assert to_utc_iso(NOW).endswith("+00:00")
    with pytest.raises(ValueError):
        to_utc_iso(datetime(2026, 1, 1))
    assert taipei_date(datetime(2026, 10, 25, 16, 30, tzinfo=UTC)) == date(2026, 10, 26)
    assert DatePair(date(2026, 12, 10), None).as_json() == ["2026-12-10", None]


def test_google_flights_link_contains_route_and_dates() -> None:  # FR-D5
    url = google_flights_url("TPE", "NRT", date(2026, 12, 10), date(2026, 12, 15))
    assert url.startswith("https://www.google.com/travel/flights?hl=zh-TW&curr=TWD&q=")
    assert unquote(url.split("q=", 1)[1]) == (
        "Flights to NRT from TPE on 2026-12-10 through 2026-12-15"
    )
    one_way = unquote(google_flights_url("TPE", "BKK", date(2027, 1, 2)).split("q=", 1)[1])
    assert one_way == "Flights to BKK from TPE on 2027-01-02"


# ---- message wording (FR-C4..C6, C-17) ---------------------------------------------


def test_price_alert_contains_required_fields() -> None:  # AC-C5
    items = evaluate([cand(9500)])
    text = price_alert_message(
        watch_name="東京", origin="TPE", destination="NRT", trip_type="round_trip", items=items
    )
    for needle in (
        "台北桃園 TPE → 東京成田 NRT",
        "12/10–12/15",
        "TWD 9,500",
        "航空公司：X",
        "查到時間：2026-10-25 12:00",
        "Google Flights",
        "https://www.google.com/travel/flights",
        "低於門檻",
        DISCLAIMER,
        "查到",
    ):
        assert needle in text


def test_no_advisory_wording_anywhere() -> None:  # AC-C6 / C-17
    items = evaluate([cand(9400, day=1), cand(8000, day=2)], budget=9000, last=10000, low=8500)
    texts = [
        price_alert_message(
            watch_name="w", origin="TPE", destination="NRT", trip_type="round_trip", items=items
        ),
        ops_failure_message(source="google_flights", error="blocked", now=NOW),
        telegram_test_message(NOW),
        *all_static_texts(),
    ]
    for text in texts:
        for phrase in BANNED_PHRASES:
            assert phrase not in text, (phrase, text)


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def wording_surfaces() -> dict[str, str]:
    """Every user-facing text surface the wording policy covers."""
    surfaces: dict[str, str] = {}
    for template in sorted((SRC / "web" / "templates").glob("*.html")):
        surfaces[f"web/templates/{template.name}"] = template.read_text(encoding="utf-8")
    surfaces["web/static/app.js"] = (SRC / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for module in (
        "services/views.py",
        "domain/messages.py",
        "domain/airports.py",
        "domain/validation.py",
    ):
        constants = _string_constants(SRC / module)
        if module == "domain/messages.py":
            # The banned list itself is the only place these phrases may appear.
            constants = [c for c in constants if c not in BANNED_PHRASES]
        surfaces[module] = "\n".join(constants)
    return surfaces


def test_banned_list_includes_compliance_additions() -> None:
    for phrase in ("保證", "穩賺", "划算", "超值", "值得", "搶", "錯過", "把握", "趁", "下手"):
        assert phrase in BANNED_PHRASES


def test_no_advisory_wording_in_templates_script_and_view_labels() -> None:  # C-17
    surfaces = wording_surfaces()
    assert len(surfaces) >= 9
    hits = [
        (name, phrase)
        for name, text in surfaces.items()
        for phrase in BANNED_PHRASES
        if phrase in text
    ]
    assert hits == []


def test_new_low_wording() -> None:
    from flight_deals.domain.messages import reason_label

    assert reason_label("new_low") == "此監看紀錄新低"
    for name, text in wording_surfaces().items():
        assert "歷史新低" not in text, name
