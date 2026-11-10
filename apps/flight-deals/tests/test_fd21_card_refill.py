"""FD-21: a round keeps checking pairs that move onto the card, and stale prices on the
list card get a refresh button that starts the same scan as 「立即查價」."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import WEB_TEXTS, web_static_texts
from flight_deals.domain.models import DatePair
from flight_deals.services import scan as scan_module
from tests.conftest import Harness
from tests.test_fd12_pages import Node, assert_wording_clean, get
from tests.test_fd16_return_leg import SPLIT, Lookup
from tests.test_fd20_card_pairs_requery import CARD, PRICES, WINDOW, card_departs, first_round, only

UP = 9_900


def entries(h: Harness, watch_id: int) -> list[dict[str, object]]:
    return list(h.repo.latest_scan_run_for_watch(watch_id).query_results)


def refilled(h: Harness, watch_id: int) -> list[str]:
    return [str(e["depart"]) for e in entries(h, watch_id) if e.get("refill")]


def card_up(h: Harness) -> None:
    for depart in CARD:
        pair = next(p for p in PRICES if p[0] == depart)
        h.source.prices[pair] = UP


# ---- scan ------------------------------------------------------------------------------


def test_pairs_that_move_onto_the_card_are_checked_too(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    card_up(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-11"))
    harness.scan(watch_id)
    # 12/13 (9,500 from the first round) moved onto the card and was checked as well.
    assert [e["depart"] for e in entries(harness, watch_id)] == [
        *CARD,
        "2026-12-11",
        "2026-12-13",
    ]
    assert refilled(harness, watch_id) == ["2026-12-13"]
    refill = entries(harness, watch_id)[-1]
    assert refill["pinned"] is True
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert DatePair(date(2026, 12, 13), date(2026, 12, 18)) in run.sampled_pairs
    assert len(run.sampled_pairs) == len(run.query_results)


def test_the_card_ends_the_round_with_this_rounds_prices(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    card_up(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-11"))
    harness.scan(watch_id)
    row = harness.services.views.list_page()["watches"][0]
    labels = {row["cheapest_fetched_label"], *(p["fetched_label"] for p in row["more_pairs"])}
    assert len(labels) == 1  # every price on the card is from this round
    assert not row["stale"]
    assert not any(p["stale"] for p in row["more_pairs"])


def test_no_refill_when_the_card_did_not_change(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    assert refilled(harness, watch_id) == []
    assert len(entries(harness, watch_id)) == 4


def test_a_tried_pair_is_never_tried_twice(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    # The card's pairs fail this round, so their old prices stay on the card.
    for depart in CARD:
        harness.source.prices.pop(next(p for p in PRICES if p[0] == depart))
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    departs = [e["depart"] for e in entries(harness, watch_id)]
    assert departs == [*CARD, "2026-12-13"]
    assert len(departs) == len(set(departs))


def test_refill_stops_at_its_limit(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    harness.source.default_price = None
    window = {**WINDOW, "window_end": "2026-12-31"}  # 17 pairs of 5 days
    watch_id = harness.create_watch(**window)
    every = {date(2026, 12, d) for d in range(10, 27)}
    for d in every:
        harness.source.prices[(d.isoformat(), (d + timedelta(days=5)).isoformat())] = 5_000
    monkeypatch.setattr(
        scan_module, "sample_pairs", lambda pairs, limit, offset: (list(pairs), 0, False)
    )
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    for pair in list(harness.source.prices):
        harness.source.prices[pair] = 9_000  # everything goes up: the card keeps changing
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-26"))
    harness.scan(watch_id)
    assert len(refilled(harness, watch_id)) == scan_module.REFILL_QUERY_LIMIT
    assert len(entries(harness, watch_id)) == 3 + 1 + scan_module.REFILL_QUERY_LIMIT


def test_hourly_limit_stops_the_refill_without_failing_the_round(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    card_up(harness)
    settings = harness.services.scan._settings
    original = settings.current
    # Room for the three card pairs and the one sample only; first_round's queries are
    # seven hours old, outside the one-hour window.
    monkeypatch.setattr(
        settings, "current", lambda: replace(original(), global_hourly_query_limit=4)
    )
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-11"))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert refilled(harness, watch_id) == []
    assert not run.global_limit_reached
    assert run.status == "ok"
    assert card_departs(harness)[0] == "12/13"  # the older price stays, marked by its time


def test_a_refilled_price_is_evaluated_for_alerts(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    card_up(harness)
    seen: list[str] = []
    original = harness.services.scan._evaluate_alerts

    def spy(watch: Any, run_id: int, candidates: list[Any]) -> Any:
        seen.extend(c.depart_date.isoformat() for c in candidates)
        return original(watch, run_id, candidates)

    monkeypatch.setattr(harness.services.scan, "_evaluate_alerts", spy)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-11"))
    harness.scan(watch_id)
    assert "2026-12-13" in seen


@pytest.fixture
def legs(harness: Harness) -> Lookup:
    scripted = Lookup()
    harness.services.scan._return_legs = scripted
    return scripted


def test_a_refilled_price_can_get_the_return_flight(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, legs: Lookup
) -> None:
    watch_id = first_round(harness)
    legs.calls.clear()
    card_up(harness)
    for pair in PRICES:  # segment refs and the split mark make a pair eligible
        harness.source.flights[pair] = SPLIT
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-11"))
    harness.scan(watch_id)
    # 12/13 (9,500) is this round's cheapest price, and it came from the refill.
    assert [c[0].pair.depart for c in legs.calls] == [date(2026, 12, 13)]


def test_a_crash_during_refill_keeps_the_run_consistent(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    card_up(harness)
    service = harness.services.scan
    original = service._query_pair

    def crash(watch: Any, pair: DatePair, run_id: int) -> Any:
        if pair.depart == date(2026, 12, 13):
            raise RuntimeError("boom")
        return original(watch, pair, run_id)

    monkeypatch.setattr(service, "_query_pair", crash)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-11"))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.status == "failed"
    assert len(run.sampled_pairs) == len(run.query_results) == 4


# ---- refresh button --------------------------------------------------------------------


def card(h: Harness) -> Node:
    return get(h, "/").main.find_all(None, "watch-card")[0]


def refresh_buttons(node: Node) -> list[Node]:
    return node.find_all("button", "refresh")


def test_no_refresh_button_on_fresh_prices(harness: Harness) -> None:
    first_round(harness)
    harness.clock.now -= timedelta(hours=7)
    assert refresh_buttons(card(harness)) == []


def test_each_stale_price_has_a_refresh_button(harness: Harness) -> None:
    watch_id = first_round(harness)
    harness.clock.now += timedelta(days=3)
    node = card(harness)
    metas = [m for m in node.find_all(None, "price-meta") if WEB_TEXTS.stale_badge in m.text()]
    assert len(metas) == 3  # main card plus the two rows
    for meta in metas:
        (button,) = refresh_buttons(meta)
        assert button.attrs["data-action"] == "scan-now"
        assert button.attrs["data-watch-id"] == str(watch_id)
        assert button.attrs["type"] == "button"
        assert button.text() == WEB_TEXTS.refresh_button
        assert button.attrs["aria-label"].startswith(WEB_TEXTS.refresh_label)
        assert "primary" not in button.classes


def test_no_refresh_button_on_a_paused_watch(harness: Harness) -> None:
    watch_id = first_round(harness)
    harness.services.watches.set_enabled(watch_id, False)
    harness.clock.now += timedelta(days=3)
    node = card(harness)
    assert WEB_TEXTS.stale_badge in node.text()
    assert refresh_buttons(node) == []


def test_detail_page_has_no_refresh_button(harness: Harness) -> None:
    watch_id = first_round(harness)
    harness.clock.now += timedelta(days=3)
    assert get(harness, f"/watches/{watch_id}").main.find_all("button", "refresh") == []


def test_refresh_wording_is_listed_and_clean(harness: Harness) -> None:
    assert WEB_TEXTS.refresh_button in web_static_texts()
    assert WEB_TEXTS.refresh_label in web_static_texts()
    first_round(harness)
    harness.clock.now += timedelta(days=3)
    assert_wording_clean(get(harness, "/"))


def test_refresh_button_style_is_scoped() -> None:
    css = (
        Path(__file__).resolve().parents[1] / "src" / "flight_deals" / "web" / "static" / "app.css"
    ).read_text(encoding="utf-8")
    assert ".price-meta .refresh {" in css
