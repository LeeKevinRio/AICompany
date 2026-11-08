"""FD-19: the list card lists the next two date pairs by price and how many have a price.

Each test names the risk-ruling condition (R1-R9) it covers.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from flight_deals.domain.messages import (
    OVERHEAD_BIN_LABELS,
    OVERHEAD_BIN_NOTE,
    PRICE_SOURCE_NOTE,
    ROUND_TRIP_NOTE,
    SAMPLED_ONLY_NOTE,
    SPLIT_TICKET_LABEL,
    WEB_BOOKING_FALLBACK_NOTE,
    WEB_TEXTS,
    coverage_text,
    web_static_texts,
)
from flight_deals.services.views import list_page_notes
from tests.conftest import Harness
from tests.test_fd12_pages import BR_DIRECT, Node, TfsLinks, assert_wording_clean, get

MAIN = ("2026-12-11", "2026-12-16")
PAIRS = {
    ("2026-12-10", "2026-12-15"): 9_000,
    MAIN: 8_000,
    ("2026-12-12", "2026-12-17"): 8_500,
    ("2026-12-13", "2026-12-18"): 9_500,
}
WINDOW = {
    "date_mode": "flexible",
    "depart_date": None,
    "return_date": None,
    "window_start": "2026-12-10",
    "window_end": "2026-12-18",
    "min_trip_days": 5,
    "max_trip_days": 5,
}


def four_pairs(
    h: Harness, flights: dict[tuple[str, str | None], dict[str, Any]] | None = None, **kw: Any
) -> int:
    h.source.default_price = None
    for pair, price in PAIRS.items():
        h.source.prices[pair] = price
        h.source.flights[pair] = BR_DIRECT
    h.source.flights.update(flights or {})
    watch_id = h.create_watch(name="東京十二月", **{**WINDOW, **kw})
    h.scan(watch_id)
    return watch_id


def card(h: Harness) -> Node:
    return get(h, "/").main.find_all(None, "watch-card")[0]


def rows(h: Harness) -> list[Node]:
    return card(h).find_all("li", "more-pair")


def amounts(nodes: list[Node]) -> list[str]:
    return [n.find_all(None, "more-pair-amount")[0].text() for n in nodes]


def notes(h: Harness) -> str:
    return get(h, "/").main.find_all(None, "page-notes")[0].text()


# ---- order and population (R1) --------------------------------------------------------


def test_two_rows_follow_the_main_card_by_price(harness: Harness) -> None:
    four_pairs(harness)
    section = card(harness).find_all("section", "more-pairs")[0]
    assert section.find_all("h3")[0].text() == WEB_TEXTS.other_pairs_title
    assert amounts(rows(harness)) == ["TWD 8,500", "TWD 9,000"]
    assert "12/12" in rows(harness)[0].text() and "12/10" in rows(harness)[1].text()
    main = card(harness).find_all(None, "price-block")[0]
    assert "8,000" in main.text() and "8,000" not in section.text()
    # No rank or price-judging words in the new block (ruling points 1, 2).
    for word in ("第 2", "第 3", "低價", "最低", "最便宜", "前 3", "Top"):
        assert word not in section.text(), word


def test_rows_equal_detail_top_second_and_third(harness: Harness) -> None:
    watch_id = four_pairs(harness)
    with harness.repo.db.connect() as conn:
        # Cheaper than everything, but a cached price, another currency and an old
        # revision never count: not as a row, not in n, not in the detail top.
        conn.execute(
            "UPDATE price_observation SET price_kind = 'cached', amount_minor = 100"
            " WHERE watch_id = ? AND depart_date = '2026-12-12'",
            (watch_id,),
        )
        conn.execute(
            "UPDATE price_observation SET currency = 'JPY', amount_minor = 100"
            " WHERE watch_id = ? AND depart_date = '2026-12-13'",
            (watch_id,),
        )
        conn.execute(
            "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
            " price_kind, depart_date, return_date, amount_minor, currency, as_of,"
            " as_of_basis, fetched_at, carrier, stops, duration_minutes)"
            " SELECT scan_run_id, watch_id, watch_revision - 1, source, 'live', '2026-12-14',"
            " '2026-12-19', 100, currency, as_of, as_of_basis, fetched_at, carrier, stops,"
            " duration_minutes FROM price_observation WHERE watch_id = ?"
            " AND depart_date = '2026-12-10'",
            (watch_id,),
        )
    views = harness.services.views
    listed = views.list_page()["watches"][0]
    top = views.detail_page(watch_id)["top"]
    assert [(p["amount"], p["dates"]) for p in listed["more_pairs"]] == [
        (r["amount_text"], r["dates"]) for r in top[1:3]
    ]
    assert [p["amount"] for p in listed["more_pairs"]] == ["TWD 9,000"]
    assert listed["coverage_label"] == coverage_text(2, 4)


def test_rows_never_undercut_the_main_card(harness: Harness) -> None:
    four_pairs(harness)
    listed = harness.services.views.list_page()["watches"][0]
    main = int(listed["min_price"].split()[1].replace(",", ""))
    assert all(int(p["amount"].split()[1].replace(",", "")) >= main for p in listed["more_pairs"])


def test_fewer_pairs_fewer_rows(harness: Harness) -> None:
    harness.source.default_price = None
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    harness.source.prices[MAIN] = 8_000
    harness.scan(harness.create_watch(**WINDOW))
    assert amounts(rows(harness)) == ["TWD 9,000"]


def test_one_price_shows_no_block_but_keeps_the_coverage(harness: Harness) -> None:
    harness.source.default_price = None
    harness.source.prices[MAIN] = 8_000
    harness.scan(harness.create_watch(**WINDOW))
    assert not card(harness).find_all("section", "more-pairs")
    assert card(harness).find_all(None, "coverage")[0].text() == coverage_text(1, 4)


# ---- coverage and the sampling note (ruling points 3-5, 8) ----------------------------


def test_coverage_is_visible_body_text_on_the_card(harness: Harness) -> None:
    four_pairs(harness)
    line = card(harness).find_all(None, "coverage")
    assert len(line) == 1 and line[0].text() == "已查到價格 4／共 4 組日期"
    assert not line[0].in_details()


def test_no_coverage_for_a_single_pair(harness: Harness) -> None:
    harness.scan(harness.create_watch())
    assert not card(harness).find_all(None, "coverage")
    assert SAMPLED_ONLY_NOTE not in notes(harness)


def test_sampled_note_once_when_a_card_is_incomplete(harness: Harness) -> None:
    harness.source.default_price = None
    harness.source.prices[MAIN] = 8_000
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    harness.scan(harness.create_watch(**WINDOW))
    harness.scan(harness.create_watch(name="第二張", **WINDOW))
    page = get(harness, "/")
    assert page.count(SAMPLED_ONLY_NOTE) == 1
    assert page.count_visible(SAMPLED_ONLY_NOTE) == 1
    note = page.main.find_all(None, "page-notes")[0].find_all("p", "sampled-note")
    assert len(note) == 1 and not note[0].in_details()


def test_sampled_note_for_a_window_without_any_price(harness: Harness) -> None:
    harness.source.default_price = None
    harness.scan(harness.create_watch(**WINDOW))  # n = 0 of 4
    assert not card(harness).find_all(None, "coverage")  # coverage needs a price
    page = get(harness, "/")
    assert page.count_visible(SAMPLED_ONLY_NOTE) == 1


def test_no_sampled_note_when_every_pair_has_a_price(harness: Harness) -> None:
    four_pairs(harness)
    assert SAMPLED_ONLY_NOTE not in notes(harness)


def test_detail_page_shows_the_same_coverage(harness: Harness) -> None:
    watch_id = four_pairs(harness)
    page = get(harness, f"/watches/{watch_id}")
    assert page.count_visible("已查到價格 4／共 4 組日期") == 1
    sampled = page.main.find_all("p", "sampled-note")[0]
    assert "已查到價格 4／共 4 組日期" in sampled.text()


# ---- each row (R2, R3, R5, R6, R7, R8) --------------------------------------------------


def test_each_row_shows_its_fetched_time_and_stale(harness: Harness) -> None:
    four_pairs(harness)
    for row in rows(harness):
        assert row.find_all(None, "price-time")[0].text()
        assert WEB_TEXTS.stale_badge not in row.text()
    harness.clock.now += timedelta(days=3)
    for row in rows(harness):
        assert WEB_TEXTS.stale_badge in row.text()


def test_labels_stay_with_their_own_row(harness: Harness) -> None:
    four_pairs(
        harness,
        flights={("2026-12-12", "2026-12-17"): {**BR_DIRECT, "split_ticket": True}},
    )
    first, second = rows(harness)
    assert SPLIT_TICKET_LABEL in first.text() and SPLIT_TICKET_LABEL not in second.text()
    for row in (first, second):
        for flight in row.find_all(None, "flight"):
            assert SPLIT_TICKET_LABEL not in flight.text()
    labels = first.find_all(None, "price-labels")[0]
    assert not any("flight" in a.classes for a in labels.ancestors())


def test_rows_show_the_outbound_label_and_no_return(harness: Harness) -> None:
    four_pairs(harness)
    for row in rows(harness):
        flights = row.find_all("div", "flight")
        assert len(flights) == 1
        assert "去程" in flights[0].visible_text()
        assert "回程" not in row.text()


def test_each_row_button_sits_with_its_own_price(harness: Harness) -> None:
    four_pairs(harness)
    the_card = card(harness)
    section = the_card.find_all("section", "more-pairs")[0]
    expected_dates = ["12/12–12/17", "12/10–12/15"]
    row_links = []
    for row in rows(harness):
        links = row.find_all("a")
        assert len(links) == 1
        link = links[0]
        assert WEB_TEXTS.booking_button_short in link.text()
        assert "primary" not in link.classes and "button" in link.classes
        sr = link.find_all(None, "sr-only")[0].text()
        assert sr.startswith(f"（{expected_dates.pop(0)}）")
        row_links.append(link.attrs["href"])
    assert len(set(row_links)) == 2
    main_link = the_card.find_all(None, "card-foot")[0].find_all("a", "booking")
    assert len(main_link) == 1 and "primary" in main_link[0].classes
    assert section not in list(main_link[0].ancestors())
    order = list(the_card.descendants())
    assert order.index(main_link[0]) < order.index(section)


class NoLinks:
    """Link builder that never has an exact link, so every button is the fallback."""

    def url(self, search: Any) -> str | None:
        return None


def test_fallback_link_keeps_its_note_on_each_row(harness: Harness) -> None:
    harness.services.views._links = NoLinks()
    four_pairs(harness)
    for row in rows(harness):
        notes_in_row = row.find_all(None, "booking-note")
        assert [n.text() for n in notes_in_row] == [WEB_BOOKING_FALLBACK_NOTE]


def test_exact_link_has_no_fallback_note(harness: Harness) -> None:
    harness.services.views._links = TfsLinks()
    four_pairs(harness)
    for row in rows(harness):
        assert not row.find_all(None, "booking-note")
        assert "tfs=" in row.find_all("a")[0].attrs["href"]


def test_party_rows_say_total_price(harness: Harness) -> None:
    four_pairs(harness, adults=2)
    pax = harness.services.views.list_page()["watches"][0]["pax_note"]
    assert pax
    for row in rows(harness):
        assert pax in row.text()


def test_rows_are_display_only(harness: Harness) -> None:
    watch_id = four_pairs(harness)
    harness.source.prices[("2026-12-12", "2026-12-17")] = 8_200
    harness.scan(watch_id)
    the_card = card(harness)
    assert the_card.find_all(None, "price-block")[0].find_all(None, "delta")  # main has one
    assert not the_card.find_all("section", "more-pairs")[0].find_all(None, "delta")


# ---- page notes count the rows (R4) ----------------------------------------------------


def test_round_trip_notes_follow_a_row_when_the_main_card_has_no_flight(
    harness: Harness,
) -> None:
    harness.source.flight = None
    harness.source.default_price = None
    for pair, price in PAIRS.items():
        harness.source.prices[pair] = price
    harness.source.flights[("2026-12-12", "2026-12-17")] = {"split_ticket": True}
    harness.scan(harness.create_watch(**WINDOW))
    assert not card(harness).find_all(None, "price-block")[0].find_all(None, "price-labels")
    text = notes(harness)
    assert ROUND_TRIP_NOTE in text
    assert WEB_TEXTS.return_leg_explain in text
    assert PRICE_SOURCE_NOTE in text
    assert WEB_TEXTS.booking_hint in text


def test_note_conditions_count_a_row_when_the_main_card_has_nothing(harness: Harness) -> None:
    """R4 at the function level: a main card without flight or labels, a row with one."""
    plain = {
        "flight": None,
        "split_ticket_label": None,
        "overhead_bin_label": None,
        "booking_url": None,
    }
    row = {
        **plain,
        "min_price": "TWD 8,000",
        "is_round_trip": True,
        "return_flight": None,
        "coverage_incomplete": False,
        "more_pairs": [{**plain, "split_ticket_label": SPLIT_TICKET_LABEL, "booking_url": "u"}],
    }
    notes_on = list_page_notes([row])
    assert notes_on["round_trip"] and notes_on["booking"] and not notes_on["overhead_one_way"]
    one_way = {
        **row,
        "is_round_trip": False,
        "more_pairs": [{**plain, "overhead_bin_label": OVERHEAD_BIN_LABELS["one_way"]}],
    }
    notes_on = list_page_notes([one_way])
    assert notes_on["overhead_one_way"] and not notes_on["round_trip"]
    assert list_page_notes([{**row, "more_pairs": []}])["round_trip"] is False


def test_one_way_bag_note_follows_a_row(harness: Harness) -> None:
    harness.source.default_price = None
    for (depart, _), price in PAIRS.items():
        harness.source.prices[(depart, None)] = price
        harness.source.flights[(depart, None)] = BR_DIRECT
    harness.source.flights[("2026-12-12", None)] = {**BR_DIRECT, "overhead_bin_excluded": True}
    harness.scan(
        harness.create_watch(
            trip_type="one_way",
            **{**WINDOW, "min_trip_days": None, "max_trip_days": None},
        )
    )
    assert OVERHEAD_BIN_LABELS["one_way"] in rows(harness)[0].text()
    assert (
        OVERHEAD_BIN_LABELS["one_way"] not in card(harness).find_all(None, "price-block")[0].text()
    )
    assert OVERHEAD_BIN_NOTE in notes(harness)


# ---- wording (R9) and query count ------------------------------------------------------


def test_new_wording_is_in_the_static_texts_and_clean(harness: Harness) -> None:
    assert coverage_text(12, 834) in web_static_texts()
    assert SAMPLED_ONLY_NOTE in web_static_texts()
    four_pairs(harness, flights={MAIN: {**BR_DIRECT, "split_ticket": True}})
    assert_wording_clean(get(harness, "/"))


def test_list_page_queries_stay_one_per_watch(harness: Harness) -> None:
    four_pairs(harness)
    calls: list[int] = []
    repo = harness.services.watches._repo
    original = repo.snapshot_observations_for_watch

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    repo.snapshot_observations_for_watch = counted
    get(harness, "/")
    assert len(calls) == 1


def test_coverage_never_exceeds_the_total(harness: Harness) -> None:
    """R1 n <= total: a priced pair outside today's expansion still caps at total."""
    watch_id = four_pairs(harness)
    with harness.repo.db.connect() as conn:
        conn.execute(
            "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
            " price_kind, depart_date, return_date, amount_minor, currency, as_of,"
            " as_of_basis, fetched_at, carrier, stops, duration_minutes)"
            " SELECT scan_run_id, watch_id, watch_revision, source, price_kind, '2026-12-10',"
            " '2026-12-16', amount_minor, currency, as_of, as_of_basis, fetched_at, carrier,"
            " stops, duration_minutes FROM price_observation WHERE watch_id = ?"
            " AND depart_date = '2026-12-13'",
            (watch_id,),
        )
    assert card(harness).find_all(None, "coverage")[0].text() == coverage_text(4, 4)


def test_coverage_style_stays_body_text() -> None:
    """R10, reopen condition 2: the coverage line must not turn into fine print."""
    css = (Path(__file__).parents[1] / "src/flight_deals/web/static/app.css").read_text(
        encoding="utf-8"
    )
    rules = [line for line in css.splitlines() if line.startswith(".coverage ")]
    assert rules == [".coverage { margin: 0; font-size: inherit; color: var(--color-text); }"]
