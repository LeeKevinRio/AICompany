"""FD-22 round 1: the list page, simplified (risk ruling work/tasks/FD-22-風控裁決.md).

Each test names the ruling section it covers: package A (summary line and one collapsed
price-notes panel), B(a) (no change on the list), D#24 (party summary), and the batch-1
fixes P1 to P6 plus section 3 (icon-only buttons).
"""

from __future__ import annotations

import re
from pathlib import Path

from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DISCLAIMER,
    OVERHEAD_BIN_NOTE,
    PRICE_SOURCE_NOTE,
    ROUND_TRIP_NOTE,
    SAMPLED_ONLY_NOTE,
    WEB_TEXTS,
    web_static_texts,
)
from tests.conftest import Harness
from tests.test_fd12_pages import (
    BR_DIRECT,
    RETURN_EXPLAIN,
    Node,
    Page,
    assert_wording_clean,
    cheaper_second_round,
    flexible_round_trip,
    get,
    priced_one_way,
    priced_round_trip,
)
from tests.test_fd15_overhead_bin import MARKED, marked_one_way
from tests.test_fd19_more_pairs import MAIN, WINDOW

CSS = (
    Path(__file__).resolve().parents[1] / "src" / "flight_deals" / "web" / "static" / "app.css"
).read_text(encoding="utf-8")

SUMMARY_ROUND_TRIP = (
    "只涵蓋已取樣的日期；沒有標示不代表單張機票或含手提行李；回程要到 Google Flights 自己選。"
)
SUMMARY_PRICED = "只涵蓋已取樣的日期；沒有標示不代表含手提行李。"
PANEL_LABEL = "價格說明"


def _texts(node: Node) -> list[tuple[str, Node]]:
    out: list[tuple[str, Node]] = []
    for child in node.children:
        if isinstance(child, str):
            out.append((child, node))
        else:
            out.extend(_texts(child))
    return out


def notes_block(page: Page) -> Node:
    return page.main.find_all(None, "page-notes")[0]


def panel(page: Page) -> Node:
    (node,) = notes_block(page).find_all("details", "notes-more")
    return node


def panel_sentences(page: Page) -> list[str]:
    return [p.text() for p in panel(page).find_all("p")]


def first_card(page: Page) -> Node:
    return page.main.find_all(None, "watch-card")[0]


def marked_pairs(h: Harness) -> int:
    """Two pairs, both marked by Google, so the main card and its row carry labels."""
    h.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    h.source.prices[("2026-12-11", "2026-12-16")] = 8_000
    h.source.flights[("2026-12-10", "2026-12-15")] = MARKED
    h.source.flights[("2026-12-11", "2026-12-16")] = MARKED
    watch_id = flexible_round_trip(h)
    h.scan(watch_id)
    return watch_id


def partial_window(h: Harness) -> int:
    """Two of four pairs have a price, so coverage is incomplete (2 of 4)."""
    h.source.default_price = None
    h.source.prices[MAIN] = 8_000
    h.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    h.source.flights[MAIN] = BR_DIRECT
    h.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    watch_id = h.create_watch(**WINDOW)
    h.scan(watch_id)
    return watch_id


# ---- package A: DISCLAIMER and summary stay visible ------------------------------------


def test_disclaimer_and_summary_are_visible_and_before_the_first_card(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    block = notes_block(page)
    (disclaimer,) = block.find_all("p", "disclaimer")
    (summary,) = block.find_all("p", "page-summary")
    for node in (disclaimer, summary):
        assert not node.in_details()
        assert "sr-only" not in node.classes
    assert disclaimer.text() == DISCLAIMER
    # Document order: DISCLAIMER, summary, panel, then the first card.
    order = [
        n
        for n in page.main.descendants()
        if n in (disclaimer, summary, panel(page)) or "watch-card" in n.classes
    ]
    assert order[:3] == [disclaimer, summary, panel(page)]
    assert "watch-card" in order[3].classes
    # Nothing between DISCLAIMER and the summary line.
    siblings = [c for c in block.children if isinstance(c, Node)]
    assert siblings[:3] == [disclaimer, summary, panel(page)]
    # The two lines are never inside the panel.
    assert DISCLAIMER not in panel(page).text()
    assert summary.text() not in panel(page).text()


def test_summary_line_is_one_of_three(harness: Harness) -> None:
    # Round trip: the long form.
    priced_round_trip(harness)
    page = get(harness, "/")
    assert [p.text() for p in notes_block(page).find_all("p", "page-summary")] == [
        SUMMARY_ROUND_TRIP
    ]
    assert page.count(SUMMARY_PRICED) == 0


def test_summary_line_for_a_one_way_page(harness: Harness) -> None:
    priced_one_way(harness)
    page = get(harness, "/")
    assert [p.text() for p in notes_block(page).find_all("p", "page-summary")] == [SUMMARY_PRICED]
    assert page.count(SUMMARY_ROUND_TRIP) == 0
    assert page.count(SUMMARY_PRICED) == 1


def test_one_way_card_mixed_with_a_round_trip_gets_the_round_trip_form(harness: Harness) -> None:
    priced_round_trip(harness)
    priced_one_way(harness)
    page = get(harness, "/")
    assert [p.text() for p in notes_block(page).find_all("p", "page-summary")] == [
        SUMMARY_ROUND_TRIP
    ]


def test_without_a_price_only_the_sampled_note_shows_and_there_is_no_panel(
    harness: Harness,
) -> None:
    harness.source.default_price = None
    harness.scan(harness.create_watch(**WINDOW))  # n = 0 of 4
    page = get(harness, "/")
    block = notes_block(page)
    assert not block.find_all("details")
    assert not block.find_all("p", "page-summary")
    (note,) = block.find_all("p", "sampled-note")
    assert note.text() == SAMPLED_ONLY_NOTE and not note.in_details()
    assert page.count(PANEL_LABEL) == 0


def test_without_any_price_or_gap_there_is_only_the_disclaimer(harness: Harness) -> None:
    harness.create_watch()  # one pair, never scanned: no price, no coverage gap
    block = notes_block(get(harness, "/"))
    assert [p.text() for p in block.find_all("p")] == [DISCLAIMER]


# ---- package A: the one panel ---------------------------------------------------------


def expected_panel(notes: dict[str, bool]) -> list[str]:
    """The old list_page_notes() order and conditions, spelled out."""
    lines = [PRICE_SOURCE_NOTE] if notes["priced"] else []
    if notes["sampled"]:
        lines.append(SAMPLED_ONLY_NOTE)
    if notes["round_trip"]:
        lines.append(
            WEB_TEXTS.return_leg_explain_listed
            if notes["return_listed"]
            else WEB_TEXTS.return_leg_explain
        )
        lines.append(ROUND_TRIP_NOTE)
    elif notes["overhead_one_way"]:
        lines.append(OVERHEAD_BIN_NOTE)
    if notes["booking"]:
        lines.append(WEB_TEXTS.booking_hint)
    if notes["priced"]:
        lines.append(WEB_TEXTS.local_time_explain)
    return lines


def test_panel_is_collapsed_with_the_fixed_label_and_visible_text(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    node = panel(page)
    assert "open" not in node.attrs
    (summary,) = [c for c in node.children if isinstance(c, Node) and c.tag == "summary"]
    assert summary.visible_text() == PANEL_LABEL
    assert page.count(PANEL_LABEL) == 1  # one panel for the whole page
    # No popover, modal or tooltip.
    assert "popover" not in page.html and 'role="dialog"' not in page.html
    # The panel sits right under the summary line, inside the page-notes block.
    assert node.parent is notes_block(page)


def test_panel_sentences_once_for_a_round_trip_page(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    notes = harness.services.views.list_page()["notes"]
    assert panel_sentences(page) == expected_panel(notes)
    for sentence in (PRICE_SOURCE_NOTE, RETURN_EXPLAIN, ROUND_TRIP_NOTE, WEB_TEXTS.booking_hint):
        assert page.count(sentence) == 1
        assert page.count_in_details(sentence) == 1
    assert OVERHEAD_BIN_NOTE not in page.html
    # The merged "說明": the time sentence is a panel line, not a second <details>.
    assert page.count(WEB_TEXTS.local_time_explain) == 1
    assert not panel(page).find_all("details")
    assert not [d for d in notes_block(page).find_all("details") if d is not panel(page)]


def test_panel_sentences_once_for_a_one_way_page(harness: Harness) -> None:
    marked_one_way(harness)
    page = get(harness, "/")
    notes = harness.services.views.list_page()["notes"]
    assert notes["overhead_one_way"] and not notes["round_trip"]
    assert panel_sentences(page) == expected_panel(notes)
    assert page.count(OVERHEAD_BIN_NOTE) == 1 and ROUND_TRIP_NOTE not in page.html


def test_panel_has_the_sampled_note_only_when_coverage_is_incomplete(harness: Harness) -> None:
    partial_window(harness)
    page = get(harness, "/")
    notes = harness.services.views.list_page()["notes"]
    assert notes["sampled"]
    assert panel_sentences(page) == expected_panel(notes)
    assert page.count(SAMPLED_ONLY_NOTE) == 1 and page.count_in_details(SAMPLED_ONLY_NOTE) == 1


def test_panel_without_the_sampled_note_when_every_pair_has_a_price(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    assert not harness.services.views.list_page()["notes"]["sampled"]
    assert SAMPLED_ONLY_NOTE not in page.html


def test_panel_text_is_never_collapsed_to_the_summary_alone(harness: Harness) -> None:
    """Each sentence of the panel is one full <p> (not shortened or merged)."""
    priced_round_trip(harness)
    lines = panel_sentences(get(harness, "/"))
    assert len(lines) == len(set(lines))
    assert all(line.endswith(("。", "。）")) for line in lines)


# ---- wording is listed and clean -----------------------------------------------------


def test_new_wording_is_listed_verbatim_and_clean(harness: Harness) -> None:
    texts = web_static_texts()
    for text in (SUMMARY_ROUND_TRIP, SUMMARY_PRICED, PANEL_LABEL, "人數與艙等"):
        assert text in texts, text
    assert WEB_TEXTS.page_summary_round_trip == SUMMARY_ROUND_TRIP
    assert WEB_TEXTS.page_summary_priced == SUMMARY_PRICED
    assert WEB_TEXTS.price_notes_summary == PANEL_LABEL
    assert WEB_TEXTS.pax_cabin_label == "人數與艙等"
    for text in texts:
        assert not any(phrase in text for phrase in BANNED_PHRASES), text
    priced_round_trip(harness)
    cheaper_second_round(harness)
    assert_wording_clean(get(harness, "/"))


# ---- CSS: size and colour of the summary and the panel ----------------------------------


def rule_blocks(selector_part: str) -> list[str]:
    """Every CSS rule block whose selector list mentions `selector_part`."""
    return [
        m.group(0)
        for m in re.finditer(r"[^{}]*\{[^{}]*\}", CSS)
        if selector_part in m.group(0).split("{")[0]
    ]


def test_summary_and_panel_are_body_size_in_the_text_colour() -> None:
    assert "--text-base: 15px;" in CSS
    assert ".page-notes .page-summary" in CSS
    for part in (".page-summary", ".notes-more"):
        blocks = rule_blocks(part)
        assert blocks, part
        joined = "\n".join(blocks)
        assert "font-size: var(--text-base);" in joined
        assert "color: var(--color-text);" in joined
        # Never muted or shrunk anywhere.
        for block in blocks:
            assert "muted" not in block, block
            assert "--text-sm" not in block and "--text-xs" not in block, block
            assert not re.search(r"font-size:\s*(1[0-4]px)", block), block
    assert ".coverage { margin: 0; font-size: inherit; color: var(--color-text); }" in CSS


def test_price_labels_still_wrap_instead_of_truncating() -> None:
    assert ".price-labels .badge { white-space: normal; }" in CSS
    assert "text-overflow" not in CSS and "-webkit-line-clamp" not in CSS


def test_no_floating_or_fixed_buttons() -> None:
    assert "position: fixed" not in CSS and "position: sticky" not in CSS


def test_tokens_exist_for_both_themes_and_there_is_no_fresh_token() -> None:
    dark = CSS.split("prefers-color-scheme: dark", 1)[1].split("* { box-sizing", 1)[0]
    assert "--color-mark-fg:" in CSS.split("@media", 1)[0]
    assert "--color-mark-fg:" in dark and "--color-mark-bg:" in dark
    for name in (
        "--color-stale-fg",
        "--color-down-fg",
        "--color-up-fg",
        "--color-flat-fg",
        "--color-state-on",
        "--color-state-off-fg",
        "--color-state-bad-fg",
        "--color-state-warn-fg",
        "--color-bar-fill",
        "--color-bar-track",
    ):
        assert name + ":" in CSS, name
    assert "--color-fresh" not in CSS and "i-fresh" not in CSS  # risk ruling P1


# ---- B(a): no change on the list ------------------------------------------------------


def test_list_has_no_change_chip_or_sentence(harness: Harness) -> None:
    watch_id = cheaper_second_round(harness)
    assert harness.services.views.list_page()["watches"][0]["delta"] is not None
    page = get(harness, "/")
    assert not page.main.find_all(None, "delta")
    assert WEB_TEXTS.delta_explain not in page.html
    assert WEB_TEXTS.delta_explain_detail not in page.html
    assert "較前一輪" not in page.html
    # The detail page keeps it.
    detail = get(harness, f"/watches/{watch_id}")
    assert detail.main.find_all(None, "delta")
    assert detail.count(WEB_TEXTS.delta_explain) == 1


# ---- D#24: party summary --------------------------------------------------------------


def price_sub(page: Page) -> list[Node]:
    return first_card(page).find_all(None, "price-sub")


def test_one_adult_economy_round_trip_shows_only_the_total_price_caption(
    harness: Harness,
) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    (sub,) = price_sub(page)
    assert sub.text() == "來回總價"
    # Outside the collapsed conditions the card never says who flies or in which cabin.
    card = first_card(page)
    shown = " ".join(
        t for t, n in _texts(card) if not any(a.tag == "details" for a in n.ancestors())
    )
    assert "1 位成人" not in shown and "經濟艙" not in shown


def test_one_adult_economy_one_way_drops_the_line_but_keeps_the_trip_in_the_route(
    harness: Harness,
) -> None:
    priced_one_way(harness)
    page = get(harness, "/")
    assert price_sub(page) == []
    (meta,) = first_card(page).find_all("p", "card-meta")
    assert "・單程" in meta.visible_text() and "→" in meta.visible_text()


def test_several_people_keep_the_line_unchanged(harness: Harness) -> None:
    harness.source.default_price = 9_000
    harness.source.flight = BR_DIRECT
    watch_id = harness.create_watch(adults=2, children=1)
    harness.scan(watch_id)
    row = harness.services.views.list_page()["watches"][0]
    page = get(harness, "/")
    (sub,) = price_sub(page)
    assert sub.text() == f"{row['price_caption']}・{row['cabin_label']}"
    assert row["pax_note"] and row["pax_note"] in sub.text() or "總價" in sub.text()


def test_another_cabin_keeps_the_line_unchanged(harness: Harness) -> None:
    harness.source.default_price = 9_000
    harness.source.flight = BR_DIRECT
    harness.scan(harness.create_watch(cabin="business"))
    page = get(harness, "/")
    (sub,) = price_sub(page)
    assert sub.text() == "來回總價・1 位成人・商務艙"


def test_conditions_fold_has_the_party_and_cabin_row(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    fold = first_card(page).find_all("details", "fold-inline")[0]
    dts = [d.text() for d in fold.find_all("dt")]
    dds = [d.text() for d in fold.find_all("dd")]
    assert "人數與艙等" in dts
    assert dds[dts.index("人數與艙等")] == "1 位成人・經濟艙"


# ---- P2: fetch time ------------------------------------------------------------------


def test_fetch_time_has_the_prefix_and_no_year_in_the_current_year(harness: Harness) -> None:
    marked_pairs(harness)
    page = get(harness, "/")
    times = [t.text() for t in first_card(page).find_all("span", "price-time")]
    assert len(times) == 2  # main card and its row
    assert all(re.fullmatch(r"查到 \d{2}/\d{2} \d{2}:\d{2}", t) for t in times), times
    assert times[0] == "查到 10/25 12:00"
    assert "查到時間" not in first_card(page).text()
    assert "天前" not in first_card(page).text() and "小時前" not in first_card(page).text()


def test_fetch_time_shows_the_year_when_it_is_not_this_year(harness: Harness) -> None:
    harness.source.prices[("2027-03-10", "2027-03-15")] = 9_000
    harness.source.flights[("2027-03-10", "2027-03-15")] = BR_DIRECT
    watch_id = harness.create_watch(depart_date="2027-03-10", return_date="2027-03-15")
    harness.scan(watch_id)
    harness.clock.advance(days=70)  # 2027-01-03: the price was fetched last year
    page = get(harness, "/")
    (time,) = first_card(page).find_all("span", "price-time")
    assert time.text() == "查到 2026-10-25 12:00"


def test_the_clock_icon_only_marks_a_stale_price(harness: Harness) -> None:
    marked_pairs(harness)
    fresh = first_card(get(harness, "/"))
    assert "i-clock" not in fresh.text()
    assert not [s for s in fresh.find_all("svg") if "M12 7v5l3 2" in str(s.children)]
    harness.clock.advance(hours=200)
    page = get(harness, "/")
    card = first_card(page)
    badges = [b for b in card.find_all("span", "badge") if WEB_TEXTS.stale_badge in b.text()]
    assert len(badges) == 2  # main card and row
    for badge in badges:
        assert badge.find_all("svg")  # the clock lives in the stale chip, next to the words
        assert badge.visible_text() == WEB_TEXTS.stale_badge
    # The fetch time itself carries no icon.
    for time in card.find_all("span", "price-time"):
        assert not time.find_all("svg")


# ---- P3: leg words -------------------------------------------------------------------


def test_every_flight_row_has_the_visible_outbound_word(harness: Harness) -> None:
    marked_pairs(harness)
    card = first_card(get(harness, "/"))
    flights = card.find_all("div", "flight")
    assert len(flights) == 2  # main card and one row
    for flight in flights:
        (leg,) = flight.find_all("span", "flight-leg")
        assert leg.visible_text() == "去程"
        assert "sr-only" not in leg.classes
        # The arrow sits next to the word; it is decorative.
        assert all(s.attrs.get("aria-hidden") == "true" for s in leg.find_all("svg"))


# ---- P1: no positive freshness marker ------------------------------------------------


def test_no_fresh_marker_anywhere(harness: Harness) -> None:
    marked_pairs(harness)
    page = get(harness, "/")
    html = page.html
    for word in ("新鮮", "已確認", "最新", "i-fresh", "color-fresh"):
        assert word not in html, word
    # Also with a stale price on the page.
    harness.clock.advance(hours=200)
    html = get(harness, "/").html
    for word in ("新鮮", "已確認", "i-fresh"):
        assert word not in html, word


# ---- P6: coverage bar ----------------------------------------------------------------


def test_coverage_bar_matches_n_over_total_and_is_hidden_from_readers(harness: Harness) -> None:
    partial_window(harness)
    card = first_card(get(harness, "/"))
    (text,) = card.find_all("p", "coverage")
    match = re.fullmatch(r"已查到價格 (\d+)／共 (\d+) 組日期", text.text())
    assert match, text.text()
    checked, total = int(match.group(1)), int(match.group(2))
    assert (checked, total) == (2, 4)
    (bar,) = card.find_all("progress", "coverage-bar")
    assert int(bar.attrs["value"]) == checked and int(bar.attrs["max"]) == total
    assert bar.attrs.get("aria-hidden") == "true"
    # Text stays body size and in the text colour; the bar adds no completion estimate.
    assert not bar.text()
    assert "完成" not in card.text() and "預計" not in card.text()


def test_coverage_bar_is_proportional_without_a_minimum_fill(harness: Harness) -> None:
    harness.source.default_price = None
    harness.source.prices[MAIN] = 8_000
    harness.scan(harness.create_watch(**{**WINDOW, "window_end": "2026-12-31"}))
    row = harness.services.views.list_page()["watches"][0]
    card = first_card(get(harness, "/"))
    (bar,) = card.find_all("progress", "coverage-bar")
    assert int(bar.attrs["value"]) == row["coverage_checked"] == 1
    assert int(bar.attrs["max"]) == row["coverage_total"] > 4
    assert "min-width" not in "\n".join(rule_blocks("coverage-bar"))


# ---- DOM order inside a card (FD-19 with the new parts) -----------------------------


def test_card_dom_order(harness: Harness) -> None:
    marked_pairs(harness)
    harness.clock.advance(hours=200)
    card = first_card(get(harness, "/"))
    order = list(card.descendants())

    def index(node: Node) -> int:
        return next(i for i, n in enumerate(order) if n is node)

    block = card.find_all(None, "price-block")[0]
    amount = block.find_all("span", "price-amount")[0]
    labels = block.find_all(None, "price-labels")[0]
    meta = block.find_all(None, "price-meta")[0]
    stale = [b for b in meta.find_all("span", "badge") if WEB_TEXTS.stale_badge in b.text()][0]
    dates = block.find_all(None, "price-dates")[0]
    flight = card.find_all("div", "flight")[0]
    coverage = card.find_all(None, "coverage-block")[0]
    main_button = card.find_all("a", "booking")[0]
    pairs = card.find_all("section", "more-pairs")[0]
    sequence = [amount, labels, meta, stale, dates, flight, coverage, main_button, pairs]
    positions = [index(n) for n in sequence]
    assert positions == sorted(positions) and len(set(positions)) == len(positions)
    # The labels and the time sit in the price block, with the price.
    assert labels.parent is block and meta.parent is block
    # Every row keeps its own labels and button in the row, after the main card's button.
    (row,) = pairs.find_all("li", "more-pair")
    row_labels = row.find_all(None, "price-labels")
    assert row_labels and row_labels[0].parent is row
    row_button = row.find_all("a", "booking")[0]
    assert index(row_button) > index(main_button)
    assert index(row.find_all(None, "more-pair-amount")[0]) < index(row_labels[0])


def test_the_google_labels_keep_icon_and_full_sentence_in_a_blue_chip(harness: Harness) -> None:
    marked_pairs(harness)
    card = first_card(get(harness, "/"))
    chips = card.find_all(None, "price-labels")[0].find_all("span", "badge")
    assert chips
    for chip in chips:
        assert "mark" in chip.classes
        assert chip.find_all("svg")
        assert chip.visible_text() in set(web_static_texts())  # the unchanged sentence


# ---- icons and actions ---------------------------------------------------------------


def test_every_icon_on_the_list_is_decorative(harness: Harness) -> None:
    marked_pairs(harness)
    harness.clock.advance(hours=200)
    page = get(harness, "/")
    svgs = page.main.find_all("svg")
    assert svgs
    assert all(s.attrs.get("aria-hidden") == "true" for s in svgs)
    assert all(s.attrs.get("focusable") == "false" for s in svgs)


def test_icon_buttons_keep_their_names_and_the_busy_label(harness: Harness) -> None:
    watch_id = marked_pairs(harness)
    harness.clock.advance(hours=200)
    card = first_card(get(harness, "/"))
    scan_buttons = [
        b
        for b in card.find_all("button", "icon-btn")
        if b.attrs.get("data-action") == "scan-now" and "refresh" not in b.classes
    ]
    assert len(scan_buttons) == 1
    refresh = card.find_all("button", "refresh")
    assert len(refresh) == 2
    for button in (*scan_buttons, *refresh):
        assert button.text() == ""
        assert button.attrs["title"] == button.attrs["aria-label"]
        assert button.attrs["data-busy-label"] == "查價中…"
        assert button.attrs["data-watch-id"] == str(watch_id)
        assert "primary" not in button.classes
        assert button.find_all("svg")
    assert scan_buttons[0].attrs["aria-label"] == "立即查價"
    assert all(b.attrs["aria-label"].startswith("刷新價格（") for b in refresh)
    (more,) = card.find_all("summary", "icon-btn")
    assert more.attrs["aria-label"] == more.attrs["title"] == "更多"
    assert more.text() == ""
    # 44px touch size, same size on every width.
    (block,) = [b for b in rule_blocks(".icon-btn") if b.split("{")[0].strip() == ".icon-btn"]
    assert "width: var(--touch-target)" in block and "height: var(--touch-target)" in block


def test_no_detail_button_and_last_scan_moved_into_more(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/")
    card = first_card(page)
    assert not [a for a in card.find_all("a") if a.text() == "詳情"]
    scanned = card.find_all("p", "card-scanned")
    assert len(scanned) == 1
    assert scanned[0].text().startswith("上次查價 ")
    assert any(a.tag == "details" and "more" in a.classes for a in scanned[0].ancestors())


def test_status_dot_and_chips_keep_their_words(harness: Harness) -> None:
    active = harness.create_watch(name="啟用")
    paused = harness.create_watch(name="暫停", destination="KIX")
    harness.services.watches.set_enabled(paused, False)
    page = get(harness, "/")
    cards = {c.attrs["data-watch-id"]: c for c in page.main.find_all(None, "watch-card")}
    dot = cards[str(active)].find_all("span", "state-dot")[0]
    assert dot.text() == "啟用中" and "sr-only" in dot.find_all("span")[0].classes
    chip = cards[str(paused)].find_all("span", "state-chip")[0]
    assert chip.visible_text() == "已停用" and chip.find_all("svg")
    assert "is-off" in cards[str(paused)].classes
    # No colour-only state: the word is always in the DOM, the icon is extra.
    assert not cards[str(paused)].find_all("span", "state-dot")


def test_route_line_keeps_codes_and_puts_full_names_in_title_and_sr_text(
    harness: Harness,
) -> None:
    priced_round_trip(harness)
    card = first_card(get(harness, "/"))
    (meta,) = card.find_all("p", "card-meta")
    assert meta.visible_text() == "台北桃園 TPE ⇄ 東京成田 NRT"  # no "・來回" (it has 來回總價)
    assert "TPE" in meta.attrs["title"] and "NRT" in meta.attrs["title"]
    assert "台灣桃園國際機場" in meta.attrs["title"]
    sr = [s for s in meta.find_all("span", "sr-only")]
    assert sr and "台灣桃園國際機場 TPE" in sr[0].text() and "來回" in sr[0].text()


# ---- the detail page is untouched by the shared macros --------------------------------


def test_detail_page_keeps_its_old_markers(harness: Harness) -> None:
    watch_id = marked_pairs(harness)
    harness.clock.advance(hours=200)
    page = get(harness, f"/watches/{watch_id}")
    main = page.main
    # Full fetch time, no list-only icons, labels not recoloured.
    assert "查到時間 2026-10-25 12:00" in page.html
    assert not main.find_all("svg")
    assert not main.find_all(None, "icon-btn") and not main.find_all("button", "refresh")
    assert not [b for b in main.find_all("span", "badge") if "mark" in b.classes]
    stale = [b for b in main.find_all("span", "badge") if WEB_TEXTS.stale_badge in b.text()]
    assert stale and all(b.text() == WEB_TEXTS.stale_badge for b in stale)
    # Outbound word and the party line stay as before.
    assert any("去程" in f.text() for f in main.find_all("div", "flight"))
    assert "來回總價・1 位成人・經濟艙" in main.find_all(None, "price-card")[0].text()
    # DISCLAIMER stays outside every <details>.
    assert page.count_in_details(DISCLAIMER) == 0 and page.count(DISCLAIMER) == 1


def test_detail_refresh_still_has_no_icon_button(harness: Harness) -> None:
    watch_id = marked_pairs(harness)
    harness.clock.advance(hours=200)
    assert get(harness, f"/watches/{watch_id}").main.find_all("button", "refresh") == []


def test_list_still_has_one_disclaimer(harness: Harness) -> None:
    marked_pairs(harness)
    page = get(harness, "/")
    assert page.count(DISCLAIMER) == 1 and page.count_in_details(DISCLAIMER) == 0


def test_round_trip_summary_for_a_price_without_flight_data_or_marks() -> None:
    """A priced round-trip row with no flight and no mark still gets the round-trip summary
    (ruling: "any round-trip price or mark"); the panel conditions stay as they were."""
    from flight_deals.services.views import list_page_notes

    row = {
        "min_price": "TWD 9,000",
        "more_pairs": [],
        "flight": None,
        "split_ticket_label": None,
        "overhead_bin_label": None,
        "return_flight": None,
        "booking_url": None,
        "coverage_incomplete": False,
        "is_round_trip": True,
    }
    notes = list_page_notes([row])
    assert notes["priced"] and notes["summary_round_trip"]
    assert not notes["round_trip"]  # panel round-trip sentences keep their old condition
    assert not list_page_notes([{**row, "is_round_trip": False}])["summary_round_trip"]
    assert not list_page_notes([{**row, "min_price": None}])["summary_round_trip"]
