"""FD-23: follow-ups of the FD-22 UI simplification (work/tasks/FD-23.md).

Items 3, 8 and 9 are built as ruled in work/tasks/FD-23-風控裁決.md (heading and fallback
sentence, price caption on every other-pair row, the 200-notification note).
The FD-22 risk ruling wording is checked verbatim by the FD-22 tests, which stay unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

from flight_deals.domain.messages import SETTINGS_STATUS_HEADING, WEB_TEXTS
from tests.conftest import Harness
from tests.test_fd12_pages import CZ_TRANSFER, Node, Page, get, priced_round_trip
from tests.test_fd19_more_pairs import PAIRS, four_pairs

WEB = Path(__file__).resolve().parents[1] / "src" / "flight_deals" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
MACROS = (WEB / "templates" / "_macros.html").read_text(encoding="utf-8")
FD23_CSS = re.sub(
    r"/\*.*?\*/",
    "",
    CSS[CSS.index("/* FD-23 follow-ups") : CSS.index("/* FD-22 round 2")],
    flags=re.S,
)
EXPLORE_INTRO = "每個出發日各查一次（最多 31 次），完成後顯示價格日曆。"
CLOCK_PATH = "M12 7v5l3 2"


def _media(css: str, query: str) -> str:
    """Body of the first `@media (<query>) { ... }` block (the blocks here nest one level)."""
    opener = f"@media ({query}) {{"
    start = css.index(opener) + len(opener)
    depth, end = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(css[end], 0)
        end += 1
    return css[start : end - 1]


def _stops_spans(scope: Node) -> list[Node]:
    return [s for s in scope.find_all("span", "flight-meta") if s.find_all("svg")]


def _mixed_pairs(harness: Harness) -> int:
    """Four pairs, all direct except the first one (one stop)."""
    return four_pairs(harness, flights={next(iter(PAIRS)): CZ_TRANSFER})


def _assert_icon_with_words(spans: list[Node]) -> None:
    kinds = set()
    for span in spans:
        svg = span.find_all("svg")[0]
        assert svg.attrs.get("aria-hidden") == "true"
        words = span.text().split("・")[0]
        assert words == "直飛" or words.startswith("轉機 "), words
        kinds.add("direct" if words == "直飛" else "stop")
        assert CLOCK_PATH not in str([svg.attrs, [n.attrs for n in svg.descendants()]])
    assert kinds == {"direct", "stop"}


# ---- 1: distribution grid columns ---------------------------------------------------------


def test_distribution_grid_is_three_columns_on_a_phone_and_two_at_360() -> None:
    phone = _media(FD23_CSS, "max-width: 600px")
    assert ".heat-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in phone
    narrow = _media(FD23_CSS, "max-width: 380px")
    assert ".heat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in narrow
    # The narrow rule comes after the phone rule, so it wins at 360 px.
    assert FD23_CSS.index("max-width: 380px") > FD23_CSS.index("max-width: 600px")


def test_distribution_cells_keep_their_content(harness: Harness) -> None:
    page = get(harness, f"/watches/{four_pairs(harness)}")
    cell = page.main.find_all("div", "heat")[0]
    assert cell.find_all("div", "heat-date") and cell.find_all("div", "heat-price")
    assert cell.find_all("span", "sr-only")
    assert cell.text().count("回 ") == 1


# ---- 2: direct / connecting icons ---------------------------------------------------------


def test_list_cards_show_the_icon_with_the_original_words(harness: Harness) -> None:
    _mixed_pairs(harness)
    card = get(harness, "/").main.find_all(None, "watch-card")[0]
    assert [s for li in card.find_all("li", "more-pair") for s in _stops_spans(li)]
    assert [s for s in _stops_spans(card) if not any(a.tag == "li" for a in s.ancestors())]
    _assert_icon_with_words(_stops_spans(card))


def test_detail_page_shows_the_icon_with_the_original_words(harness: Harness) -> None:
    page = get(harness, f"/watches/{_mixed_pairs(harness)}")
    _assert_icon_with_words(_stops_spans(page.main))
    assert _stops_spans(page.main.find_all("section", "price-card")[0])
    assert _stops_spans(page.main.find_all("table", "pair-table")[0])


def test_every_flight_with_a_known_stop_count_has_the_icon(harness: Harness) -> None:
    page = get(harness, f"/watches/{priced_round_trip(harness)}")
    flights = page.main.find_all("div", "flight")
    assert flights
    for flight in flights:
        meta = flight.find_all("span", "flight-meta")[0]
        if meta.text() not in {"", "—"}:
            assert meta.find_all("svg"), meta.text()


def test_the_clock_is_not_used_for_stops() -> None:
    start = MACROS.index("{% macro flight(")
    macro = MACROS[start : MACROS.index("endmacro", start)]
    assert "i-clock" not in macro
    assert '"i-direct" if f.stops_kind == "direct" else "i-stop"' in macro
    assert FD23_CSS.count(".flight-meta .icon") == 1


# ---- 3: settings form and the reserved heading --------------------------------------------


def test_retention_fields_sit_in_a_two_column_grid(harness: Harness) -> None:
    page = get(harness, "/settings")
    (grid,) = page.main.find_all("div", "retention-grid")
    assert "grid" in grid.classes
    names = {n.attrs.get("name") for n in grid.find_all("input")}
    assert {"retention_days", "notification_retention_days"} <= names
    wide = _media(FD23_CSS, "min-width: 601px")
    assert ".grid.retention-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in wide
    # A phone keeps the grid's own single column: no phone rule touches it.
    assert "retention-grid" not in _media(FD23_CSS, "max-width: 600px")


# ---- 4: data source card ------------------------------------------------------------------


def test_data_source_card_has_the_same_cells_and_no_new_state_word(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/settings")
    table = page.main.find_all("table", "health-table")[0]
    row = table.find_all("tbody")[0].find_all("tr")[0]
    assert [c.attrs["data-label"] for c in row.find_all("td")] == [
        "資料源",
        "狀態",
        "斷路器",
        "連續失敗",
        "最近成功",
        "最近失敗",
    ]
    assert [td.attrs["class"].split()[-1] for td in row.find_all("td")] == [
        "h-name",
        "h-state",
        "h-breaker",
        "h-failures",
        "h-success",
        "h-failure",
    ]
    allowed = {h["state"] for h in harness.services.views.settings_page()["health"]}
    words = {b.text() for b in table.find_all("span", "badge")}
    assert words and words <= allowed, words


def test_data_source_card_css_only_rearranges_on_a_phone() -> None:
    phone = _media(FD23_CSS, "max-width: 600px")
    rules = re.findall(r"[^{}]*health-table[^{}]*\{[^{}]*\}", phone)
    assert rules
    for rule in rules:
        assert "display: none" not in rule, rule
        # The only generated content is the empty line break after the row's last cell.
        assert "content:" not in rule or 'tr::after { content: "";' in rule, rule
    assert "health-table" not in FD23_CSS.replace(phone, "")


# ---- 5: exploration comparison entry ------------------------------------------------------


def test_comparison_entry_is_a_secondary_link_in_the_page_head(harness: Harness) -> None:
    page = get(harness, "/explore")
    (head,) = page.main.find_all("div", "page-head")
    (link,) = head.find_all("a", "head-link")
    assert link.attrs["href"] == "/explore/compare" and link.text() == "前往多目的地比價"
    assert not ({"button", "primary"} & link.classes)
    assert not page.main.find_all(None, "entry-card")
    assert "多目的地比價" not in [h.text() for h in page.main.find_all("h2")]
    entries = [a for a in page.main.find_all("a") if a.attrs.get("href") == "/explore/compare"]
    assert len(entries) == 1


def test_exploration_opening_is_unchanged_and_has_no_panel(harness: Harness) -> None:
    page = get(harness, "/explore")
    assert page.count(EXPLORE_INTRO) == 1 and WEB_TEXTS.explore_intro == EXPLORE_INTRO
    assert not page.main.find_all(None, "notes-more")
    assert "價格說明" not in page.html


# ---- 6: weekday picker --------------------------------------------------------------------


def test_weekday_picker_is_a_four_column_grid_on_a_phone(harness: Harness) -> None:
    page = get(harness, "/explore")
    (row,) = page.main.find_all("div", "weekday-grid")
    assert len(row.find_all("label", "weekday-option")) == 7
    phone = _media(FD23_CSS, "max-width: 600px")
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in phone
    assert ".weekday-grid" in phone and ".weekday-grid" not in FD23_CSS.replace(phone, "")


def test_watch_form_weekday_row_is_not_re_laid_out(harness: Harness) -> None:
    assert not get(harness, "/watches/new").main.find_all(None, "weekday-grid")


# ---- 7: list card spacing -----------------------------------------------------------------


def test_fetched_line_gets_two_more_pixels_on_the_main_block_only(harness: Harness) -> None:
    rules = re.findall(r"[^{}]*\.price-meta \{[^{}]*\}", FD23_CSS)
    assert [r.strip() for r in rules] == [
        ".watch-card .price-block > .price-meta { margin-top: 2px; }"
    ]
    # The selector reaches only a price-meta that is a direct child of the main price block.
    four_pairs(harness)
    card = get(harness, "/").main.find_all(None, "watch-card")[0]
    block = card.find_all("div", "price-block")[0]
    inside = [n for n in block.children if isinstance(n, Node) and "price-meta" in n.classes]
    assert len(inside) == 1
    for row in card.find_all("li", "more-pair"):
        for meta in row.find_all("div", "price-meta"):
            assert not any("price-block" in a.classes for a in meta.ancestors())
            assert meta.parent is not None and "price-block" not in meta.parent.classes


# ---- 10: table roles ----------------------------------------------------------------------


def _assert_table_roles(table: Node) -> None:
    assert table.attrs.get("role") == "table"
    for group in [*table.find_all("thead"), *table.find_all("tbody")]:
        assert group.attrs.get("role") == "rowgroup"
    for row in table.find_all("tr"):
        assert row.attrs.get("role") == "row"
    for th in table.find_all("th"):
        assert th.attrs.get("role") == "columnheader"
    cells = table.find_all("td")
    assert cells
    for td in cells:
        assert td.attrs.get("role") == "cell"


def test_card_tables_keep_their_table_roles(harness: Harness) -> None:
    watch_id = _mixed_pairs(harness)
    priced_round_trip(harness)
    for url, wanted in (
        ("/notifications", "notif-table"),
        ("/settings", "stack-table"),
        (f"/watches/{watch_id}", "pair-table"),
    ):
        page: Page = get(harness, url)
        tables = [t for t in page.main.find_all("table") if wanted in t.classes]
        assert tables, url
        for table in tables:
            _assert_table_roles(table)


def test_settings_count_table_is_not_a_card_and_has_no_forced_roles(harness: Harness) -> None:
    priced_round_trip(harness)
    page = get(harness, "/settings")
    stack = [t for t in page.main.find_all("table") if "stack-table" in t.classes]
    assert len(stack) >= 2  # data sources and the last-round usage; events appear on demand
    count = [t for t in page.main.find_all("table") if "fit" in t.classes]
    assert count and not count[0].attrs.get("role")


# ---- 3 (risk ruling): database status heading ---------------------------------------------


def test_database_status_heading_and_fallback_are_verbatim(harness: Harness) -> None:
    from flight_deals.domain.messages import SETTINGS_STATUS_UNAVAILABLE

    assert SETTINGS_STATUS_HEADING == "資料庫狀態"
    assert SETTINGS_STATUS_UNAVAILABLE == "資料庫狀態暫時無法取得。"
    headings = [h.text() for h in get(harness, "/settings").main.find_all("h2")]
    assert headings.count("資料庫狀態") == 1 and headings.count("資料維護") == 1
    # The form's heading and the permanent sentence under it stay as they were.
    assert headings.index("資料庫狀態") < headings.index("資料維護")
    assert "調降保留期不會立即刪除資料" in get(harness, "/settings").main.text()


def test_fallback_sentence_replaces_the_old_one(harness: Harness) -> None:
    harness.services.views.retention = None  # no maintenance block: the fallback shows
    page = get(harness, "/settings")
    assert "資料維護資訊暫時無法取得" not in page.html
    assert page.main.text().count("資料庫狀態暫時無法取得。") == 1


# ---- 8 (risk ruling): price caption on every other-pair row -------------------------------


def _pair_rows(harness: Harness) -> list[Node]:
    card = get(harness, "/").main.find_all(None, "watch-card")[0]
    return card.find_all("li", "more-pair")


def _one_way_four(harness: Harness, **kw: object) -> int:
    harness.source.default_price = None
    for day, price in (("12-10", 9_000), ("12-11", 8_000), ("12-12", 8_500), ("12-13", 9_500)):
        harness.source.prices[(f"2026-{day}", None)] = price
    watch_id = harness.create_watch(
        name="單程十二月",
        trip_type="one_way",
        date_mode="flexible",
        depart_date=None,
        return_date=None,
        window_start="2026-12-10",
        window_end="2026-12-13",
        min_trip_days=None,
        max_trip_days=None,
        **kw,  # type: ignore[arg-type]
    )
    harness.scan(watch_id)
    return watch_id


def _assert_caption(rows: list[Node], text: str | None) -> None:
    assert rows
    for row in rows:
        head = row.find_all("div", "more-pair-head")[0]
        order = [c.classes for c in head.children if isinstance(c, Node)]
        captions = row.find_all("span", "more-pair-caption")
        if text is None:
            assert not captions
            continue
        assert [c.text() for c in captions] == [text]
        assert text not in row.text().replace(captions[0].text(), "", 1)
        assert order[0] == {"more-pair-amount"}
        assert order[1] == {"more-pair-caption"} and order[2] == {"more-pair-dates"}
        assert "sr-only" not in captions[0].classes and "aria-hidden" not in captions[0].attrs
        assert not row.find_all("div", "price-sub")


def test_other_pairs_carry_the_caption_for_one_adult_round_trip(harness: Harness) -> None:
    four_pairs(harness)
    _assert_caption(_pair_rows(harness), "來回總價")


def test_other_pairs_carry_the_party_caption_once_for_several_adults(harness: Harness) -> None:
    four_pairs(harness, adults=2)
    rows = _pair_rows(harness)
    _assert_caption(rows, "來回・2 人總價")
    for row in rows:
        assert row.text().count("2 人總價") == 1


def test_other_pairs_carry_the_party_caption_once_for_one_way_party(harness: Harness) -> None:
    _one_way_four(harness, adults=2)
    rows = _pair_rows(harness)
    _assert_caption(rows, "2 人總價")
    for row in rows:
        assert row.text().count("2 人總價") == 1


def test_one_adult_one_way_rows_have_no_caption_element(harness: Harness) -> None:
    _one_way_four(harness)
    rows = _pair_rows(harness)
    _assert_caption(rows, None)
    assert "來回總價" not in "".join(r.text() for r in rows)


def test_caption_style_matches_the_main_card_price_sub() -> None:
    rule = re.findall(r"\.more-pair-caption \{[^{}]*\}", FD23_CSS)
    assert rule == [".more-pair-caption { font-size: var(--text-sm); color: var(--color-text); }"]
    assert "muted" not in rule[0]


# ---- 9 (risk ruling): the 200-notification note ------------------------------------------


def _fill_log(harness: Harness, total: int) -> None:
    while len(harness.repo.list_notifications(total + 10)) < total:
        harness.clock.advance(minutes=1)
        harness.services.notifications.send_test()


def test_limit_note_text_and_constant_are_shared() -> None:
    import inspect

    from flight_deals.domain.messages import NOTIFICATIONS_LIST_LIMIT, web_static_texts
    from flight_deals.storage.repository import Repository

    assert NOTIFICATIONS_LIST_LIMIT == 200
    default = inspect.signature(Repository.list_notifications).parameters["limit"].default
    assert default == NOTIFICATIONS_LIST_LIMIT
    note = "此頁只列出最新 {limit} 筆通知（含收合的部分），再更早的通知不會顯示。"
    assert WEB_TEXTS.notifications_limit_note == note
    assert any(note in t for t in web_static_texts())
    assert WEB_TEXTS.settings_status_unavailable in web_static_texts()


def test_limit_note_texts_pass_the_banned_phrase_check() -> None:
    from flight_deals.domain.messages import BANNED_PHRASES

    for field in (
        WEB_TEXTS.notifications_limit_note,
        WEB_TEXTS.settings_status_unavailable,
        SETTINGS_STATUS_HEADING,
    ):
        for banned in BANNED_PHRASES:
            assert banned not in field, (banned, field)
        assert "None" not in field


def test_exactly_the_limit_shows_no_note(harness: Harness) -> None:
    _fill_log(harness, 200)
    page = get(harness, "/notifications")
    assert not page.main.find_all(None, "notifications-limit-note")
    assert "此頁只列出最新" not in page.html


def test_one_past_the_limit_shows_the_note_after_the_fold(harness: Harness) -> None:
    _fill_log(harness, 201)
    page = get(harness, "/notifications")
    tables = page.main.find_all("table")
    shown = len(tables[0].find_all("tbody")[0].find_all("tr"))
    folded = len(tables[1].find_all("tbody")[0].find_all("tr"))
    assert (shown, folded) == (20, 180)
    fold = page.main.find_all("details", "older-notifications")[0]
    assert fold.find_all("summary")[0].text() == "顯示更早的通知（180 筆）"
    (note,) = page.main.find_all("p", "notifications-limit-note")
    assert note.text() == "此頁只列出最新 200 筆通知（含收合的部分），再更早的通知不會顯示。"
    assert not note.in_details() and "sr-only" not in note.classes
    # Right after the fold, inside main (before the footer).
    siblings = [c for c in fold.parent.children if isinstance(c, Node)] if fold.parent else []
    assert siblings.index(note) == siblings.index(fold) + 1
    assert note.text() not in page.root.find_all("footer")[0].text()


def test_the_201st_row_never_reaches_the_page(harness: Harness) -> None:
    _fill_log(harness, 201)
    view = harness.services.views.notifications_page()
    assert len(view["notifications"]) == 200 and view["notifications_has_more"] is True


def test_a_priced_201st_row_stays_off_the_page_and_off_the_footer_note(harness: Harness) -> None:
    from flight_deals.domain.messages import PRICE_SOURCE_NOTE

    priced_round_trip(harness)  # the oldest row: a price notification for 8,000
    assert len(harness.repo.list_notifications(1000)) == 1
    control = get(harness, "/notifications")
    assert "8,000" in control.main.text() and PRICE_SOURCE_NOTE in control.html
    _fill_log(harness, 201)  # 200 newer rows without a price push it to the 201st place
    page = get(harness, "/notifications")
    bodies = [t.find_all("tbody")[0].find_all("tr") for t in page.main.find_all("table")]
    assert sum(len(b) for b in bodies) == 200
    assert page.main.find_all("p", "notifications-limit-note")
    assert "8,000" not in page.main.text()
    assert PRICE_SOURCE_NOTE not in page.html


# ---- art re-check: distribution cell foot and data source card lines -----------------------


def test_stale_clock_sits_on_the_return_line_with_the_words_in_the_cell(
    harness: Harness,
) -> None:
    watch_id = four_pairs(harness)
    harness.clock.advance(hours=200)
    cells = get(harness, f"/watches/{watch_id}").main.find_all("div", "heat")
    assert cells
    for cell in cells:
        (foot,) = cell.find_all("div", "heat-foot")
        (clock,) = foot.find_all("span", "heat-clock")
        assert clock.find_all("svg")[0].attrs["aria-hidden"] == "true"
        assert clock.find_all(None, "sr-only")[0].text() == WEB_TEXTS.stale_badge
        assert foot.text().startswith("回 ")
        assert not cell.find_all("div", "heat-date")[0].find_all("span", "heat-clock")
    # Same position at 360 px: no rule moves it, and the corner word is on the date line.
    assert ".heat-foot" not in _media(FD23_CSS, "max-width: 380px")
    assert "position: absolute" not in FD23_CSS[FD23_CSS.index(".heat-grid .heat-foot") :]


def test_data_source_card_is_four_lines_on_a_phone() -> None:
    phone = _media(FD23_CSS, "max-width: 600px")
    order = {
        name: int(m.group(1))
        for name in ("h-name", "h-state", "h-breaker", "h-failures", "h-success", "h-failure")
        if (m := re.search(rf"td\.{name} \{{ order: (\d+);", phone))
    }
    assert order == {
        "h-name": 1,
        "h-state": 2,
        "h-breaker": 4,
        "h-failures": 5,
        "h-success": 6,
        "h-failure": 7,
    }
    assert 'tr::after { content: ""; order: 3; flex: 0 0 100%;' in phone
    for name in ("h-success", "h-failure"):
        assert re.search(rf"td\.{name} \{{ order: \d; flex: 1 0 100%; \}}", phone)
    for name in ("h-name", "h-state", "h-breaker", "h-failures"):
        assert not re.search(rf"td\.{name} \{{[^}}]*flex: 1 0 100%", phone)
