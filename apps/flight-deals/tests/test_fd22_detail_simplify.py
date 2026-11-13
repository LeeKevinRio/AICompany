"""FD-22 round 2: the detail page, the notification log, settings and the exploration opening
(risk ruling work/tasks/FD-22-風控裁決.md: package E #40 to #43, P8, P10 to P13, section 2 and 3).

Each test names the ruling item it covers. Round 1 (the list page) is tested in
test_fd22_list_simplify.py.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from flight_deals.config import Limits
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DISCLAIMER,
    OVERHEAD_BIN_NOTE,
    PRICE_SOURCE_NOTE,
    ROUND_TRIP_NOTE,
    SAMPLED_ONLY_NOTE,
    WEB_TEXTS,
    fetched_range_label,
    web_static_texts,
)
from flight_deals.services.views import NOTIFICATIONS_SHOWN
from tests.conftest import CLIENT_HEADERS, Harness
from tests.test_fd12_pages import (
    BOOKING_HINT,
    RETURN_EXPLAIN,
    Node,
    Page,
    assert_wording_clean,
    cheaper_second_round,
    get,
    priced_one_way,
    priced_round_trip,
)
from tests.test_fd15_overhead_bin import marked_one_way
from tests.test_fd16_return_leg import LISTED, Lookup, lookup, scanned
from tests.test_fd19_more_pairs import four_pairs
from tests.test_fd22_list_simplify import marked_pairs, partial_window
from tests.test_web import VALID

__all__ = ["lookup"]  # the fixture is reused from the FD-16 tests

CSS = (
    Path(__file__).resolve().parents[1] / "src" / "flight_deals" / "web" / "static" / "app.css"
).read_text(encoding="utf-8")

SUMMARY_ROUND_TRIP = (
    "只涵蓋已取樣的日期；沒有標示不代表單張機票或含手提行李；回程要到 Google Flights 自己選。"
)
SUMMARY_PRICED = "只涵蓋已取樣的日期；沒有標示不代表含手提行李。"
PANEL_LABEL = "價格說明"
LEGEND = "只含已取樣日期。低＝較便宜三分之一、高＝較貴三分之一。"
EXPLORE_INTRO = "每個出發日各查一次（最多 31 次），完成後顯示價格日曆。"
ARROWS = "▼▲↑↓⬆⬇△▽→←⇧⇩"
# The round-2 block of app.css, comments removed so only rules are inspected.
ROUND_TWO_CSS = re.sub(r"/\*.*?\*/", "", CSS[CSS.rindex("/* FD-22 round 2") :], flags=re.S)


def detail(h: Harness, watch_id: int) -> Page:
    return get(h, f"/watches/{watch_id}")


def notes_block(page: Page) -> Node:
    return page.main.find_all(None, "page-notes")[0]


def panel(page: Page) -> Node:
    (node,) = notes_block(page).find_all("details", "notes-more")
    return node


def price_card(page: Page) -> Node:
    return page.main.find_all("section", "price-card")[0]


def section_with(page: Page, title: str) -> Node:
    return next(
        s for s in page.main.find_all("section", "card") if title in s.find_all("h2")[0].text()
    )


def order_of(page: Page, *selectors: tuple[str | None, str]) -> list[int]:
    """Document positions of the first node matching each (tag, class)."""
    nodes = list(page.main.descendants())
    positions = []
    for tag, cls in selectors:
        match = next(n for n in nodes if (tag is None or n.tag == tag) and cls in n.classes)
        positions.append(nodes.index(match))
    return positions


# ---- package E #40: summary line, one panel, before the main card ----------------------


def test_disclaimer_and_summary_are_visible_and_before_the_main_card(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness))
    summary = notes_block(page).find_all("p", "page-summary")
    assert len(summary) == 1 and summary[0].text() == SUMMARY_ROUND_TRIP
    assert page.count(DISCLAIMER) == 1 and page.count_in_details(DISCLAIMER) == 0
    assert page.count(SUMMARY_ROUND_TRIP) == 1 and page.count_in_details(SUMMARY_ROUND_TRIP) == 0
    disclaimer, summary_pos, panel_pos, card_pos = order_of(
        page,
        ("p", "disclaimer"),
        ("p", "page-summary"),
        ("details", "notes-more"),
        (None, "price-card"),
    )
    assert disclaimer < summary_pos < panel_pos < card_pos
    # Same size and colour as the disclaimer (ruling: never smaller, never muted).
    assert "muted" not in notes_block(page).find_all("p", "page-summary")[0].classes


def test_one_way_and_other_priced_pages_get_the_shorter_summary(harness: Harness) -> None:
    page = detail(harness, priced_one_way(harness))
    assert notes_block(page).find_all("p", "page-summary")[0].text() == SUMMARY_PRICED
    assert SUMMARY_ROUND_TRIP not in page.html


def test_without_a_price_there_is_only_the_disclaimer(harness: Harness) -> None:
    page = detail(harness, harness.create_watch())
    assert not page.main.find_all(None, "notes-more") and not page.main.find_all(
        None, "page-summary"
    )
    assert page.count(DISCLAIMER) == 1 and page.count(PRICE_SOURCE_NOTE) == 0


def test_the_panel_is_collapsed_with_the_fixed_label(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness))
    node = panel(page)
    assert "open" not in node.attrs
    (summary,) = node.find_all("summary")
    assert summary.text() == PANEL_LABEL
    assert WEB_TEXTS.price_notes_summary == PANEL_LABEL
    # Exactly one panel on the page, and no popover, modal or tooltip stand-in.
    assert len(page.main.find_all("details", "notes-more")) == 1
    assert "popover" not in page.html and 'role="dialog"' not in page.html


def test_panel_sentences_once_for_a_round_trip_page(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness))
    sentences = [p.text() for p in panel(page).find_all("p")]
    assert sentences == [
        PRICE_SOURCE_NOTE,
        SAMPLED_ONLY_NOTE,
        RETURN_EXPLAIN,
        ROUND_TRIP_NOTE,
        WEB_TEXTS.local_time_explain,
    ]
    for sentence in sentences:
        assert page.count(sentence) == 1, sentence
        assert page.count_in_details(sentence) == 1, sentence
    assert OVERHEAD_BIN_NOTE not in page.html


def test_panel_uses_the_listed_sentence_when_a_return_flight_is_shown(
    harness: Harness, lookup: Lookup
) -> None:
    page = detail(harness, scanned(harness))
    sentences = [p.text() for p in panel(page).find_all("p")]
    assert LISTED in sentences and RETURN_EXPLAIN not in sentences
    assert page.count(LISTED) == 1


def test_panel_sentences_once_for_a_marked_one_way_page(harness: Harness) -> None:
    page = detail(harness, marked_one_way(harness))
    sentences = [p.text() for p in panel(page).find_all("p")]
    assert sentences == [
        PRICE_SOURCE_NOTE,
        SAMPLED_ONLY_NOTE,
        OVERHEAD_BIN_NOTE,
        WEB_TEXTS.local_time_explain,
    ]
    assert ROUND_TRIP_NOTE not in page.html and RETURN_EXPLAIN not in page.html


def test_panel_has_no_overhead_sentence_without_a_mark(harness: Harness) -> None:
    page = detail(harness, priced_one_way(harness))
    sentences = [p.text() for p in panel(page).find_all("p")]
    assert OVERHEAD_BIN_NOTE not in sentences and ROUND_TRIP_NOTE not in sentences
    assert sentences == [PRICE_SOURCE_NOTE, SAMPLED_ONLY_NOTE, WEB_TEXTS.local_time_explain]


def test_the_main_card_no_longer_holds_the_moved_sentences(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness))
    card = price_card(page)
    assert not card.find_all(None, "return-explain") and not card.find_all(None, "flight-note")
    text = card.text()
    for moved in (RETURN_EXPLAIN, ROUND_TRIP_NOTE, WEB_TEXTS.local_time_explain):
        assert moved not in text


def test_coverage_is_once_on_the_page_before_the_main_card(harness: Harness) -> None:
    page = detail(harness, partial_window(harness))
    label = "已查到價格 2／共 4 組日期"
    assert page.count(label) == 1 and page.count_visible(label) == 1
    coverage, card_pos = order_of(page, ("p", "coverage"), (None, "price-card"))
    assert coverage < card_pos
    assert notes_block(page).find_all("p", "coverage")[0].text() == label
    # It is no longer part of the sampled-only sentence.
    assert label not in panel(page).text()


def test_booking_hint_stays_right_under_the_main_button(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness))
    cta = price_card(page).find_all(None, "cta")[0]
    children = [c for c in cta.children if not isinstance(c, str)]
    assert children[0].tag == "a" and "cta-button" in children[0].classes
    assert children[1].tag == "p" and children[1].text() == BOOKING_HINT
    assert page.count(BOOKING_HINT) == 1 and page.count_in_details(BOOKING_HINT) == 0
    assert BOOKING_HINT not in panel(page).text()


def test_delta_explain_and_the_change_chip_stay_visible(harness: Harness) -> None:
    page = detail(harness, cheaper_second_round(harness))
    card = price_card(page)
    assert "較前一輪" in card.text()
    note = card.find_all(None, "delta-explain")[0]
    assert note.find_all("p")[0].text() == WEB_TEXTS.delta_explain
    assert page.count_visible(WEB_TEXTS.delta_explain) == 1


# ---- P8, P10 -----------------------------------------------------------------------------


def test_last_scan_row_is_gone_but_coverage_stays(harness: Harness) -> None:
    page = detail(harness, partial_window(harness))
    assert "上次查價" not in page.plain_text()
    assert "已查到價格 2／共 4 組日期" in page.plain_text()


def test_limit_sentences_stay_outside_the_folded_group(harness: Harness) -> None:
    harness.services.settings.update({"max_pairs_per_scan": "4"})
    watch_id = harness.create_watch(
        date_mode="flexible",
        window_start="2026-12-01",
        window_end="2026-12-20",
        min_trip_days=4,
        max_trip_days=5,
    )
    harness.scan(watch_id)
    page = detail(harness, watch_id)
    assert page.count(WEB_TEXTS.limit_reached_note) == 1
    assert page.count_visible(WEB_TEXTS.limit_reached_note) == 1
    group = page.main.find_all("details", "diagnostics")[0]
    assert WEB_TEXTS.limit_reached_note not in group.text()
    assert "open" not in group.attrs
    assert group.find_all("summary")[0].text() == WEB_TEXTS.diagnostics_summary == "紀錄與診斷"


def test_the_group_holds_the_record_folds_and_the_old_sentence_follows_its_table(
    harness: Harness,
) -> None:
    watch_id = priced_round_trip(harness)
    harness.client.put(
        f"/api/watches/{watch_id}", json={**VALID, "destination": "HND"}, headers=CLIENT_HEADERS
    )
    harness.scan(watch_id)
    page = detail(harness, watch_id)
    group = page.main.find_all("details", "diagnostics")[0]
    titles = [s.text() for s in group.find_all("summary")]
    for needed in ("最近價格紀錄", "本次取樣的日期組合", "最近掃描", "舊設定的價格紀錄"):
        assert any(t.startswith(needed) for t in titles), (needed, titles)
    old_fold = next(
        d
        for d in group.find_all("details", "fold")
        if d.find_all("summary")[0].text().startswith("舊設定")
    )
    assert WEB_TEXTS.old_revision_note in old_fold.text()
    assert page.count(WEB_TEXTS.old_revision_note) == 1
    # The watch settings fold stays outside the group.
    assert not any("監看設定" in s.text() for s in group.find_all("summary"))


# ---- action buttons ----------------------------------------------------------------------


def test_delete_and_stop_keep_their_words(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness))
    head = page.main.find_all(None, "page-head")[0]
    texts = [b.text() for b in head.find_all("button")]
    assert "刪除" in texts and "停用" in texts and WEB_TEXTS.scan_now_label in texts
    assert not head.find_all("svg")


# ---- first-round forms on the detail page ------------------------------------------------


def test_fetch_time_has_the_prefix_and_no_year(harness: Harness) -> None:  # P2
    page = detail(harness, marked_pairs(harness))
    times = [t.text() for t in price_card(page).find_all("span", "price-time")]
    assert times == ["查到 10/25 12:00"]
    assert "查到時間" not in price_card(page).text()


def test_stale_chip_and_marks_have_icons_and_the_old_words(harness: Harness) -> None:  # P5, #19
    watch_id = marked_pairs(harness)
    harness.clock.advance(hours=200)
    page = detail(harness, watch_id)
    card = price_card(page)
    stale = [b for b in card.find_all("span", "badge") if WEB_TEXTS.stale_badge in b.text()]
    assert stale and all(b.find_all("svg") and b.text() == WEB_TEXTS.stale_badge for b in stale)
    marks = [b for b in card.find_all("span", "badge") if "mark" in b.classes]
    assert marks and all(b.find_all("svg") and b.text() for b in marks)
    assert all(s.attrs.get("aria-hidden") == "true" for s in page.main.find_all("svg")), (
        "every icon is decorative"
    )


def test_leg_words_keep_their_text_next_to_an_arrow(harness: Harness) -> None:  # P3
    page = detail(harness, priced_round_trip(harness))
    legs = price_card(page).find_all("span", "flight-leg")
    assert legs and all(leg.text() in ("去程", "回程") for leg in legs)
    assert all(leg.find_all("svg") for leg in legs)


def test_route_line_has_codes_and_full_names_for_readers(harness: Harness) -> None:  # P4
    page = detail(harness, priced_round_trip(harness))
    line = page.main.find_all("p", "route-line")[0]
    assert "TPE" in line.visible_text() and "⇄" in line.visible_text()
    assert "機場" in line.attrs.get("title", "") or "桃園" in line.attrs.get("title", "")
    assert line.find_all(None, "sr-only")
    one_way = detail(harness, priced_one_way(harness)).main.find_all("p", "route-line")[0]
    assert "→" in one_way.visible_text() and "・單程" in one_way.visible_text()


def test_party_line_rules_of_d24_apply_to_the_detail_page(harness: Harness) -> None:
    round_trip = detail(harness, priced_round_trip(harness))
    sub = price_card(round_trip).find_all("div", "price-sub")
    assert [s.text() for s in sub] == ["來回總價"]
    one_way = detail(harness, priced_one_way(harness))
    assert not price_card(one_way).find_all("div", "price-sub")
    several = detail(harness, priced_round_trip(harness, adults=2, children=1))
    assert "2 大 1 小總價" in price_card(several).text()
    business = detail(harness, priced_round_trip(harness, cabin="business"))
    assert "商務艙" in price_card(business).find_all("div", "price-sub")[0].text()


# ---- #41 other date pairs as rows on a phone ---------------------------------------------


def test_the_caption_is_printed_once_under_the_title_not_in_the_head(harness: Harness) -> None:
    page = detail(harness, four_pairs(harness))
    section = section_with(page, "其他日期組合")
    captions = section.find_all("p", "price-caption")
    assert [c.text() for c in captions] == ["來回總價"]
    order = [
        n
        for n in section.descendants()
        if n.tag in ("h2", "p", "table") and (n.tag != "p" or "price-caption" in n.classes)
    ]
    assert [n.tag for n in order[:3]] == ["h2", "p", "table"]
    assert not page.main.find_all(None, "th-sub")
    headers = [th.text() for th in section.find_all("th")]
    assert "航班" in headers and "連結" in headers and all("來回總價" not in h for h in headers)


def test_every_row_keeps_all_its_cells(harness: Harness) -> None:
    page = detail(harness, four_pairs(harness))
    section = section_with(page, "其他日期組合")
    rows = section.find_all("tr", None)[1:]
    assert len(rows) == 3
    for row in rows:
        classes = [c for td in row.find_all("td") for c in td.classes]
        for needed in ("cell-dates", "cell-price", "cell-flight", "cell-link"):
            assert needed in classes, (needed, row.text())
        assert re.fullmatch(
            r"查到 \d{2}/\d{2} \d{2}:\d{2}", row.find_all("span", "price-time")[0].text()
        )
        assert row.find_all("div", "cell-amount") and row.find_all("a")


def test_rows_with_a_cached_price_a_mismatch_and_several_people_lose_nothing(
    harness: Harness,
) -> None:
    from tests.test_fd12_pages import BR_DIRECT

    harness.source.currency = "JPY"
    watch_id = priced_round_trip(harness, adults=2, children=1)
    page = detail(harness, watch_id)
    recent = next(
        d
        for d in page.main.find_all("details", "fold")
        if d.find_all("summary")[0].text().startswith("最近價格紀錄")
    )
    rows = recent.find_all("tbody")[0].find_all("tr")
    assert rows
    for row in rows:
        text = row.text()
        assert "幣別不符，不參與通知" in text and "2 大 1 小總價" in text
        assert row.find_all("td", "cell-flight") and row.find_all("td", "cell-link")
    harness.source.currency = None
    harness.source._kind = "cached"
    harness.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    mixed = harness.create_watch(name="快取價", destination="OSA")
    harness.scan(mixed)
    cached_page = detail(harness, mixed)
    holders = cached_page.main.find_all("td", "cell-price")
    assert holders and all("快取價，非即時" in h.visible_text() for h in holders)
    assert all("Google Flights" in h.visible_text() for h in holders)


def test_stale_rows_keep_chip_and_words(harness: Harness) -> None:
    watch_id = four_pairs(harness)
    harness.clock.advance(hours=200)
    page = detail(harness, watch_id)
    rows = section_with(page, "其他日期組合").find_all("tbody")[0].find_all("tr")
    assert rows
    for row in rows:
        chips = [b for b in row.find_all("span", "badge") if WEB_TEXTS.stale_badge in b.text()]
        assert chips and chips[0].find_all("svg")


def test_the_phone_css_turns_the_rows_into_cards_without_hiding_a_cell() -> None:
    media = ROUND_TWO_CSS
    block = media[media.index("@media (max-width: 600px)") :].split("@media (min-width: 601px)")[0]
    assert "table.pair-table td" in block and "display: block" in block
    assert "table.pair-table thead" in block and "clip-path: inset(50%)" in block
    assert "display: none" not in block and "visibility: hidden" not in block
    # The table keeps its desktop form: nothing outside the phone query hides or reflows it.
    outside = media[: media.index("@media (max-width: 600px)")]
    for rule in re.findall(r"[^{}]*pair-table[^{}]*\{[^{}]*\}", outside):
        assert "display" not in rule and "min-width" not in rule, rule


# ---- #42, #43 distribution ---------------------------------------------------------------


def distribution(page: Page) -> Node:
    return section_with(page, "依出發日的價格分布")


def test_cells_show_date_amount_and_return_day_and_no_time(harness: Harness) -> None:  # #42
    page = detail(harness, four_pairs(harness))
    cells = distribution(page).find_all("div", "heat")
    assert len(cells) == 4
    for cell in cells:
        assert re.search(r"\d{2}/\d{2} 週.", cell.find_all("div", "heat-date")[0].text())
        assert "TWD" in cell.find_all("div", "heat-price")[0].text()
        assert re.search(r"回 \d{2}/\d{2}", cell.text())
        assert not cell.find_all("div", "heat-time")
        assert not re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", cell.text())


def test_the_fetch_range_sits_above_the_grid(harness: Harness) -> None:  # #42
    watch_id = four_pairs(harness)
    page = detail(harness, watch_id)
    line = distribution(page).find_all("p", "heat-range")[0]
    assert re.fullmatch(
        r"查到時間：\d{2}/\d{2} \d{2}:\d{2}(～(\d{2}/\d{2} )?\d{2}:\d{2})?", line.text()
    )
    view = harness.services.views.detail_page(watch_id)
    assert view["distribution_fetched_label"] == line.text()
    assert (
        fetched_range_label(
            min(d["fetched_at"] for d in view["distribution"]),
            max(d["fetched_at"] for d in view["distribution"]),
        )
        == line.text()
    )
    pos_line, pos_grid = order_of(page, ("p", "heat-range"), ("div", "heat-grid"))
    assert pos_line < pos_grid


def test_low_and_high_words_replace_symbols_and_the_middle_has_none(harness: Harness) -> None:
    page = detail(harness, four_pairs(harness))
    section = distribution(page)
    cells = section.find_all("div", "heat")
    for cell in cells:
        ranks = [r.text() for r in cell.find_all("span", "heat-rank")]
        if "heat-cheap" in cell.classes:
            assert ranks == ["低"]
            assert "較便宜三分之一" in cell.text()
        elif "heat-pricey" in cell.classes:
            assert ranks == ["高"]
            assert "較貴三分之一" in cell.text()
        else:
            assert ranks == [] and "中段" in cell.text()
        assert all(r.attrs.get("aria-hidden") == "true" for r in cell.find_all("span", "heat-rank"))
    assert {"heat-cheap", "heat-pricey"} <= {c for cell in cells for c in cell.classes}
    # No triangles or arrows anywhere in the section, and no glyph in the heat CSS.
    assert not any(ch in section.text() for ch in ARROWS)
    rules = "\n".join(m.group(0) for m in re.finditer(r"[^{}]*\.heat[^{}]*\{[^{}]*\}", CSS))
    assert not any(ch in rules for ch in ARROWS)


def test_a_stale_cell_has_a_clock_and_the_spoken_words(harness: Harness) -> None:  # #42
    watch_id = four_pairs(harness)
    harness.clock.advance(hours=200)
    page = detail(harness, watch_id)
    cells = distribution(page).find_all("div", "heat")
    assert cells
    for cell in cells:
        (clock,) = cell.find_all("span", "heat-clock")
        assert clock.find_all("svg") and clock.find_all("svg")[0].attrs["aria-hidden"] == "true"
        spoken = clock.find_all(None, "sr-only")[0].text()
        assert spoken == WEB_TEXTS.stale_badge
        assert WEB_TEXTS.stale_badge not in cell.visible_text()
        assert not cell.find_all("div", "badge")


def test_the_clock_sits_on_the_return_line_and_cannot_cover_other_lines(harness: Harness) -> None:
    watch_id = four_pairs(harness)
    harness.clock.advance(hours=200)
    page = detail(harness, watch_id)
    for cell in distribution(page).find_all("div", "heat"):
        # FD-23 (art re-check suggestion 1): the clock moved from the date line to the end of
        # the return line, so a stale cell stays at three lines; never on the date line.
        assert not cell.find_all("div", "heat-date")[0].find_all("span", "heat-clock")
        assert cell.find_all("div", "heat-foot")[0].find_all("span", "heat-clock")
    rule = ROUND_TWO_CSS[ROUND_TWO_CSS.index(".heat-grid .heat-clock {") :].split("}")[0]
    assert "position: absolute" not in rule


def test_a_fresh_cell_has_no_clock(harness: Harness) -> None:
    page = detail(harness, four_pairs(harness))
    assert not distribution(page).find_all("span", "heat-clock")


def test_several_people_keep_the_total_note_on_every_cell(harness: Harness) -> None:
    page = detail(harness, priced_round_trip(harness, adults=2, children=1))
    cells = distribution(page).find_all("div", "heat")
    assert cells and all("2 大 1 小總價" in c.text() for c in cells)


def test_the_coverage_bar_is_decorative_and_exactly_n_over_total(harness: Harness) -> None:
    page = detail(harness, partial_window(harness))
    (bar,) = notes_block(page).find_all("progress", "coverage-bar")
    assert bar.attrs["aria-hidden"] == "true"
    assert (bar.attrs["value"], bar.attrs["max"]) == ("2", "4")
    assert page.count("已查到價格 2／共 4 組日期") == 1


def test_inner_folds_of_the_group_drop_their_own_frame() -> None:
    start = ROUND_TWO_CSS.index("details.diagnostics > .fold-body > details.fold >")
    rule = ROUND_TWO_CSS[start:].split("}")[0]
    assert "border: 0" in rule and "background: none" in rule


def test_the_fetch_range_shows_the_year_when_it_is_not_this_year() -> None:
    now = datetime(2027, 1, 3, tzinfo=UTC)
    old = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
    old_end = datetime(2026, 10, 25, 4, 2, tzinfo=UTC)
    assert fetched_range_label(old, old_end, now) == "查到時間：2026-10-25 12:00～12:02"
    this_year = datetime(2027, 1, 2, 4, 0, tzinfo=UTC)
    assert fetched_range_label(this_year, this_year, now) == "查到時間：01/02 12:00"
    # A range crossing the new year shows the year on both ends.
    assert fetched_range_label(old, this_year, now) == (
        "查到時間：2026-10-25 12:00～2027-01-02 12:00"
    )
    # Without ``now`` (exploration pages) nothing changes.
    assert fetched_range_label(old, old_end) == "查到時間：10/25 12:00～12:02"


def test_the_legend_is_verbatim_with_swatches_and_a_clock(harness: Harness) -> None:  # #43
    page = detail(harness, four_pairs(harness))
    section = distribution(page)
    assert section.find_all("p", "distribution-legend")[0].text() == LEGEND
    assert WEB_TEXTS.distribution_legend == LEGEND
    assert page.count(LEGEND) == 1
    key = section.find_all("ul", "heat-key")[0]
    assert key.attrs.get("aria-hidden") == "true"
    items = [li.text() for li in key.find_all("li")]
    assert items == ["低", "中", "高", WEB_TEXTS.stale_badge]
    swatches = key.find_all("span", "heat-swatch")
    assert [
        next(c for c in s.classes if c.startswith("heat-") and c != "heat-swatch") for s in swatches
    ] == [
        "heat-cheap",
        "heat-mid",
        "heat-pricey",
    ]
    assert key.find_all("li")[3].find_all("svg")
    assert not any(ch in key.text() for ch in ARROWS)
    assert "顏色：綠" not in page.html


# ---- trend caption -----------------------------------------------------------------------


def test_trend_caption_is_the_ruled_sentence(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    harness.clock.advance(hours=7)
    harness.source.prices[("2026-12-11", "2026-12-16")] = 7_000
    harness.scan(watch_id)
    page = detail(harness, watch_id)
    view = harness.services.views.detail_page(watch_id)["trend"]
    expected = f"最高 {view['high_text']}・最低 {view['low_text']}（每點為一次掃描的最低價）"
    assert view["high_text"] != view["low_text"]
    caption = page.main.find_all("figcaption")[0]
    assert caption.text() == expected
    assert "目前設定版本" not in page.html and "title" not in caption.attrs


# ---- notification log (P11) --------------------------------------------------------------


def test_notification_rows_keep_the_full_amount_and_reason(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/notifications")
    table = page.main.find_all("table")[0]
    assert "stack-table" in table.classes
    row = table.find_all("tbody")[0].find_all("tr")[0]
    cells = {td.attrs.get("data-label"): td for td in row.find_all("td")}
    assert set(cells) == {"建立時間", "監看", "類型", "觸發原因", "價格", "結果", "嘗試", "內容"}
    notification = harness.services.views.notifications_page()["notifications"][0]
    assert cells["價格"].find_all("span", "n-amount")[0].text() == notification["price"]
    assert re.match(r"TWD [\d,]{5,}", notification["price"])
    assert (
        cells["觸發原因"].text().endswith(notification["reasons"])
        and notification["reasons"] != "—"
    )
    assert "text-overflow" not in CSS and "line-clamp" not in CSS


def _log_with_test_rows(harness: Harness, extra: int) -> None:
    """Price notifications from three watches plus ``extra`` test messages (no price)."""
    priced_round_trip(harness)
    priced_one_way(harness)
    cheaper_second_round(harness)
    for _ in range(extra):
        harness.clock.advance(minutes=5)
        harness.services.notifications.send_test()


def _log_rows(table: Node) -> list[Node]:
    return table.find_all("tbody")[0].find_all("tr")


def test_log_lists_the_newest_ones_and_folds_the_rest(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # M1 4a, 4b, 4d
    assert NOTIFICATIONS_SHOWN == 20
    _log_with_test_rows(harness, 3)
    all_rows = harness.services.views.notifications_page()["notifications"]
    assert len(all_rows) >= 6
    monkeypatch.setattr("flight_deals.services.views.NOTIFICATIONS_SHOWN", 4)
    page = get(harness, "/notifications")
    tables = page.main.find_all("table")
    fold = page.main.find_all("details", "older-notifications")[0]
    assert len(tables) == 2 and "open" not in fold.attrs
    shown, folded = _log_rows(tables[0]), _log_rows(tables[1])
    assert len(shown) == 4 and len(folded) == len(all_rows) - 4
    # The label is verbatim with the real folded count; only the count cuts, order is kept.
    assert fold.find_all("summary")[0].text() == f"顯示更早的通知（{len(folded)} 筆）"
    created = [r.find_all("span", "n-created")[0].text() for r in (*shown, *folded)]
    assert created == [n["created"] for n in all_rows]
    assert tables[1].in_details()
    # Same card format and fields inside the fold.
    labels = ["建立時間", "監看", "類型", "觸發原因", "價格", "結果", "嘗試", "內容"]
    for row in (*shown, *folded):
        assert [td.attrs["data-label"] for td in row.find_all("td")] == labels
    # No paging and no dynamic loading.
    assert "page=" not in page.html and "fetch(" not in page.html


def test_the_twenty_first_notification_is_the_first_one_folded(harness: Harness) -> None:
    _log_with_test_rows(harness, 20)
    rows = harness.services.views.notifications_page()
    assert len(rows["recent_notifications"]) == 20
    assert rows["older_notifications"][0] == rows["notifications"][20]
    page = get(harness, "/notifications")
    fold = page.main.find_all("details", "older-notifications")[0]
    assert fold.find_all("summary")[0].text() == (
        f"顯示更早的通知（{len(rows['older_notifications'])} 筆）"
    )


def test_no_fold_when_twenty_or_fewer(harness: Harness) -> None:
    priced_round_trip(harness)
    assert not get(harness, "/notifications").main.find_all("details", "older-notifications")


def test_price_source_note_shows_when_only_a_folded_row_has_a_price(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # M1 4c, 4d
    priced_round_trip(harness)  # the only price notification is the oldest one
    for _ in range(3):
        harness.clock.advance(minutes=5)
        harness.services.notifications.send_test()
    monkeypatch.setattr("flight_deals.services.views.NOTIFICATIONS_SHOWN", 2)
    page = get(harness, "/notifications")
    fold = page.main.find_all("details", "older-notifications")[0]
    assert any("TWD" in td.text() for td in fold.find_all("td", "n-price"))
    first = page.main.find_all("table")[0]
    assert not any("TWD" in td.text() for td in first.find_all("td", "n-price"))
    assert page.count_visible(PRICE_SOURCE_NOTE) == 1 and page.count_visible(DISCLAIMER) >= 1


def test_rows_without_a_price_have_no_orphan_dash(harness: Harness) -> None:  # M1 2c
    _log_with_test_rows(harness, 1)
    page = get(harness, "/notifications")
    table = page.main.find_all("table")[0]
    empty = [
        td
        for td in table.find_all("td", "n-price")
        if td.find_all("span", "n-amount")[0].text() == "—"
    ]
    assert empty
    for td in empty:
        # The dash stays in the DOM for readers (label from data-label); the phone CSS takes
        # it out of sight, so it is never a bare dash without a label.
        assert td.attrs["data-label"] == "價格" and "n-noprice" in td.classes
    start = ROUND_TWO_CSS.index("table.notif-table td.n-noprice")
    block = ROUND_TWO_CSS[start:].split("}")[0]
    assert "clip-path: inset(50%)" in block and "display: none" not in block


def test_log_card_keeps_amount_notes_reason_and_result_visible(harness: Harness) -> None:
    priced_round_trip(harness, adults=2, children=1)
    page = get(harness, "/notifications")
    row = _log_rows(page.main.find_all("table")[0])[0]
    price = row.find_all("td", "n-price")[0]
    assert price.find_all("span", "n-amount")[0].text().startswith("TWD")
    assert "2 大 1 小總價" in price.text()  # pax_note stays visible, right after the amount
    assert not any("sr-only" in n.classes for n in price.descendants())
    result = row.find_all("td", "n-result")[0]
    assert result.find_all("span", "badge") and not result.in_details()
    assert not row.find_all("td", "n-reason")[0].in_details()
    assert row.find_all("span", "n-kind-chip")[0].text()
    sent = row.find_all(None, "n-sent")
    assert not sent or sent[0].text().startswith("送出 ")


def test_log_cells_hold_real_label_elements(harness: Harness) -> None:
    """Codex HIGH: labels are elements in every cell, not CSS generated content."""
    _log_with_test_rows(harness, 1)
    page = get(harness, "/notifications")
    rows = _log_rows(page.main.find_all("table")[0])
    assert rows
    for row in rows:
        for td in row.find_all("td"):
            labels = td.find_all("span", "n-label")
            assert len(labels) == 1, td.text()
            assert labels[0].text() == td.attrs["data-label"] + "："
    # The message fold keeps its visible word and the label reads "內容：" before it.
    body = rows[0].find_all("td", "n-body")[0]
    assert body.find_all("summary")[0].text() == "查看"
    assert body.attrs["data-label"] == "內容"


def test_log_css_has_no_generated_labels_and_no_display_contents() -> None:
    assert "display: contents" not in ROUND_TWO_CSS
    assert "notif-table td::before" not in ROUND_TWO_CSS
    positive = ROUND_TWO_CSS.replace(":not(.notif-table)", "")
    assert not re.search(r"notif-table[^{}]*::before", positive)
    # The generic generated-label rule of the other card tables skips the log.
    assert "table.stack-table:not(.notif-table) td[data-label]::before" in ROUND_TWO_CSS


def _rule(selector: str, css: str = ROUND_TWO_CSS) -> str:
    return css[css.index(selector) :].split("}")[0]


def test_log_phone_css_keeps_five_labels_for_readers_only_and_three_visible() -> None:
    """Five cells (time, watch, type, price, message) read their label aloud only; reason,
    result and tries keep it visible. The fifth cell, the message fold, was approved in the
    FD-22 round 2 risk confirmation (C3, written): summary stays visible "查看", readers hear
    "內容：查看", the full text is never cut, and result and error text stay outside the fold."""
    media = ROUND_TWO_CSS[ROUND_TWO_CSS.index("@media (max-width: 600px)") :].split(
        "@media (min-width: 601px)"
    )[0]
    sr_rule = _rule("table.notif-table td.n-time > .n-label", media)
    for hidden in ("n-time", "n-watch", "n-kind", "n-price", "n-body"):
        assert f"table.notif-table td.{hidden} > .n-label" in sr_rule
    for shown in ("n-reason", "n-result", "n-tries"):
        assert f"td.{shown} > .n-label" not in sr_rule
    assert "clip-path: inset(50%)" in sr_rule and "display: none" not in sr_rule
    visible = _rule("table.notif-table .n-label {", media)
    assert "display: inline" in visible and "muted" in visible
    # The amount is never clipped, shrunk or hidden.
    amount = _rule("table.notif-table .n-amount", media)
    assert "nowrap" in amount and "overflow" not in amount and "font-size" not in amount
    # A long watch name wraps; the price moves down as a whole (no ellipsis anywhere).
    assert "flex-wrap: wrap" in ROUND_TWO_CSS and "text-overflow" not in ROUND_TWO_CSS


def test_log_labels_are_hidden_on_desktop() -> None:
    desktop = ROUND_TWO_CSS[ROUND_TWO_CSS.index("@media (min-width: 601px)") :]
    assert "display: none" in _rule("table.notif-table .n-label", desktop)


def test_log_message_fold_keeps_the_full_text_and_result_stays_outside(harness: Harness) -> None:
    priced_round_trip(harness)
    row = _log_rows(get(harness, "/notifications").main.find_all("table")[0])[0]
    body = row.find_all("td", "n-body")[0]
    assert body.find_all("pre", "message")[0].text().strip()
    assert not row.find_all("td", "n-result")[0].in_details()


def test_card_table_wrappers_do_not_claim_to_scroll_sideways(harness: Harness) -> None:
    watch_id = four_pairs(harness)
    for url in (f"/watches/{watch_id}", "/notifications", "/settings"):
        page = get(harness, url)
        for table in page.main.find_all("table"):
            if {"stack-table", "pair-table"} & table.classes:
                label = table.parent.attrs.get("aria-label", "")
                assert label and "可橫向捲動" not in label, url


def test_notification_phone_css_keeps_text_whole() -> None:
    block = CSS[CSS.rindex("@media (max-width: 600px)") :]
    assert "table.stack-table td.num { white-space: normal; }" in block
    assert "overflow-wrap: anywhere" in block
    assert 'content: attr(data-label) "："' in block


def test_notification_page_has_no_panel_and_keeps_its_footer_sentences(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/notifications")
    assert not page.main.find_all(None, "notes-more") and not page.main.find_all(
        None, "page-summary"
    )
    assert PANEL_LABEL not in page.html and SUMMARY_ROUND_TRIP not in page.html
    assert page.count_visible(DISCLAIMER) >= 1
    assert page.count_visible(PRICE_SOURCE_NOTE) == 1
    assert_wording_clean(page)


# ---- exploration opening (#48) and settings (P12) ----------------------------------------


def test_exploration_opening_is_verbatim_and_there_is_no_panel(harness: Harness) -> None:
    page = get(harness, "/explore")
    assert page.count(EXPLORE_INTRO) == 1 and WEB_TEXTS.explore_intro == EXPLORE_INTRO
    assert "最多連續 3 個月）內符合出發星期" not in page.html
    assert not page.main.find_all(None, "notes-more") and PANEL_LABEL not in page.html
    # The other always-visible sentences stay as they were.
    assert page.count(DISCLAIMER) == 1 and page.count_in_details(DISCLAIMER) == 0


def test_exploration_opening_count_is_the_configured_limit() -> None:
    assert f"（最多 {Limits().exploration_max_cells} 次）" in WEB_TEXTS.explore_intro


def test_settings_steps_fold_and_addresses_wrap(harness: Harness) -> None:
    harness.services.views._telegram_configured = False
    page = get(harness, "/settings")
    fold = page.main.find_all("details", "telegram-steps")[0]
    assert "open" not in fold.attrs
    assert fold.find_all("summary")[0].text() == WEB_TEXTS.tech_details_summary
    assert fold.find_all("ol", "steps") and "getUpdates" in fold.text()
    assert ".steps, .steps li, .steps code { overflow-wrap: anywhere; }" in CSS
    # The state sentence stays outside the fold.
    assert "目前不會送出任何通知" in page.main.text()
    assert "目前不會送出任何通知" not in fold.text()


def test_settings_tables_become_cards_with_labels_and_add_no_state_words(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/settings")
    health = next(t for t in page.main.find_all("table") if "stack-table" in t.classes)
    cells = health.find_all("tbody")[0].find_all("tr")[0].find_all("td")
    assert [c.attrs.get("data-label") for c in cells] == [
        "資料源",
        "狀態",
        "斷路器",
        "連續失敗",
        "最近成功",
        "最近失敗",
    ]
    state_words = {
        b.text()
        for b in page.main.find_all("span", "badge")
        if any(c.startswith("health-") for c in b.classes)
    }
    view = harness.services.views.settings_page()
    allowed = {h["state"] for h in view["health"]} | {"已設定", "未設定"}
    if view["command_status"]:
        allowed.add(view["command_status"]["label"])
    assert state_words <= allowed, state_words
    assert not page.main.find_all(None, "notes-more")


# ---- wording, CSS scope, contrast --------------------------------------------------------


def test_new_wording_is_listed_verbatim_and_clean() -> None:
    texts = web_static_texts()
    for sentence in (
        LEGEND,
        EXPLORE_INTRO,
        PANEL_LABEL,
        "紀錄與診斷",
        "低",
        "中",
        "高",
        "最高 {high}・最低 {low}（每點為一次掃描的最低價）",
    ):
        assert any(sentence in t for t in texts), sentence
    for field in (
        WEB_TEXTS.distribution_legend,
        WEB_TEXTS.heat_low,
        WEB_TEXTS.heat_mid,
        WEB_TEXTS.heat_high,
        WEB_TEXTS.trend_caption,
        WEB_TEXTS.diagnostics_summary,
        WEB_TEXTS.explore_intro,
    ):
        for banned in BANNED_PHRASES:
            assert banned not in field, (banned, field)
        assert "None" not in field


def test_detail_notification_explore_and_settings_pages_pass_the_wording_checks(
    harness: Harness,
) -> None:
    watch_id = priced_round_trip(harness)
    for url in (f"/watches/{watch_id}", "/notifications", "/explore", "/settings"):
        assert_wording_clean(get(harness, url))


def test_round_two_css_is_scoped_away_from_the_list_page() -> None:
    block = ROUND_TWO_CSS
    selectors = [
        s.strip()
        for m in re.finditer(r"([^{}@]+)\{", block)
        for s in m.group(1).split(",")
        if s.strip() and not s.strip().startswith("media")
    ]
    scoped = (
        ".route-line",
        ".price-caption",
        ".price-card",
        "pair-table",
        "stack-table",
        ".heat",
        ".steps",
        "td.cell-dates",
        ".diagnostics",
        "notif-table",
    )
    for selector in selectors:
        assert any(token in selector for token in scoped), selector
        assert "watch-card" not in selector and "more-pair" not in selector, selector


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_corner_words_and_clock_pass_contrast_in_both_themes() -> None:
    root = re.search(r":root \{(.*?)\n\}", CSS, re.S)
    dark = re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\n  \}", CSS, re.S)
    assert root and dark
    light_tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-f]{6});", root.group(1)))
    dark_tokens = {
        **light_tokens,
        **dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-f]{6});", dark.group(1))),
    }
    rank = "\n".join(m.group(0) for m in re.finditer(r"[^{}]*\.heat-rank[^{}]*\{[^{}]*\}", CSS))
    clock = "\n".join(m.group(0) for m in re.finditer(r"[^{}]*\.heat-clock \{[^{}]*\}", CSS))
    assert "color: var(--color-text);" in rank and "color: var(--color-text);" in clock
    for tokens in (light_tokens, dark_tokens):
        for cell in ("--color-heat-cheap", "--color-heat-mid", "--color-heat-pricey"):
            assert _ratio(tokens["--color-text"], tokens[cell]) >= 4.5, cell
        # Swatch outline is the only non-text edge of the key: 3:1 against the card.
        assert _ratio(tokens["--color-input-border"], tokens["--color-surface"]) >= 3.0


def test_settings_count_table_fits_the_phone_width(harness: Harness) -> None:
    # FD-22 (GM measurement): the two-column count table hid its numbers behind the
    # wrapper's horizontal scroll at 390 px because table.data has min-width 640px.
    page = get(harness, "/settings")
    assert any("fit" in t.classes for t in page.main.find_all("table", "data"))
    css = (
        Path(__file__).resolve().parents[1] / "src" / "flight_deals" / "web" / "static" / "app.css"
    ).read_text(encoding="utf-8")
    assert ".table-wrap > table.data.fit { min-width: 0; }" in css
