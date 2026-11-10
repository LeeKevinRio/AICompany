"""FD-12 page structure: rendered HTML assertions for the card list, the main price card,
flight rows, folds, the single disclaimer and the Google Flights links (ADR-0002 FD-12
C-99, C-100, C-101, C-102).

The copy asserted here is the risk-approved wording of PRD v0.2 (45-row table), spelled out
on purpose: a drift between the approved text and the rendered page must fail a test.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import pytest

from flight_deals.domain.messages import (
    DETAIL_ALL_DEPARTED,
    DISCLAIMER,
    PRICE_SOURCE_NOTE,
    ROUND_TRIP_NOTE,
    SAMPLED_ONLY_NOTE,
    WEB_TEXTS,
    all_static_texts,
)
from flight_deals.domain.models import FlightSearch
from flight_deals.ports import SourceResult
from tests.conftest import CLIENT_HEADERS, Harness
from tests.test_comparison_service import Queue as ComparisonQueue
from tests.test_comparison_service import compared
from tests.test_fd12_snapshots import MONTH

# ---- approved copy (PRD v0.2) -------------------------------------------------------

BOOKING_BUTTON = "到 Google Flights 查看並訂票"
BOOKING_SHORT = "查看並訂票"
BOOKING_HINT = "開啟 Google Flights 該日期組合的結果頁（非直接訂位），請依航空公司與起降時刻選擇。"
RETURN_EXPLAIN = "只列去程航班；回程需在 Google Flights 選擇，價格可能因回程不同而改變。"
BEST_TITLE = "已查到最低價"
MANUAL_CHECK = "需人工查價"
MANUAL_LINK = "到 Google Flights 人工查價"
DELTA_EXPLAIN = "較前一輪＝與上一輪最低價的差額，可能是不同日期。"
ONE_ADULT = "1 位成人・經濟艙"
STALE_BADGE = "可能已過期"
UNEMBEDDED_FORM_HINT = "依實測，此組合常無法自動查價，可能需人工查價。"
GOOGLE_FLIGHTS_PATH = "/travel/flights"
LOCAL_TIME = "航班時刻為各機場當地時間。"
MANUAL_CHECK_EXPLAIN = WEB_TEXTS.manual_check_explain
NO_DISPLAYABLE_PRICE = "目前無可顯示的價格"

# ---- flight details a scripted source can attach to its quotes ------------------------

BR_DIRECT: dict[str, Any] = {
    "carrier": "長榮航空",
    "stops": 0,
    "flight_numbers": "BR184",
    "depart_time": "07:55",
    "arrive_time": "12:00",
    "arrive_day_offset": 0,
    "route_airports": "TPE,NRT",
}
CZ_TRANSFER: dict[str, Any] = {
    "carrier": "中國南方航空",
    "stops": 1,
    "flight_numbers": "CZ3088,CZ3575",
    "depart_time": "23:55",
    "arrive_time": "03:30",
    "arrive_day_offset": 1,
    "route_airports": "TPE,SZX,SHA",
}
LEGACY_KEYS = ("flight_numbers", "arrive_time", "arrive_day_offset", "route_airports")


# ---- a small HTML tree (stdlib only) ----------------------------------------------------

VOID_TAGS = {"meta", "link", "br", "input", "hr", "img", "col", "area", "base", "source"}


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    parent: Node | None = None
    children: list[Node | str] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def descendants(self) -> Iterator[Node]:
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()

    def ancestors(self) -> Iterator[Node]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def find_all(self, tag: str | None = None, cls: str | None = None) -> list[Node]:
        return [
            n
            for n in self.descendants()
            if (tag is None or n.tag == tag) and (cls is None or cls in n.classes)
        ]

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return " ".join(" ".join(parts).split())

    def visible_text(self) -> str:
        """Text a sighted reader sees: ``.sr-only`` parts are left out."""
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif "sr-only" not in child.classes:
                parts.append(child.visible_text())
        return " ".join(" ".join(parts).split())

    def in_details(self) -> bool:
        return any(a.tag == "details" for a in self.ancestors())

    def in_details_inside(self, boundary: Node) -> bool:
        for a in self.ancestors():
            if a is boundary:
                return False
            if a.tag == "details":
                return True
        return False


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs}, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        node: Node | None = self.current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data: str) -> None:
        self.current.children.append(data)


def parse(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    return builder.root


@dataclass
class Page:
    html: str
    root: Node

    @property
    def main(self) -> Node:
        return self.root.find_all("main")[0]

    def text_nodes(self) -> Iterator[tuple[str, Node]]:
        def walk(node: Node) -> Iterator[tuple[str, Node]]:
            for child in node.children:
                if isinstance(child, str):
                    yield child, node
                else:
                    yield from walk(child)

        yield from walk(self.root)

    def count(self, needle: str) -> int:
        """Occurrences in the whole HTML text, collapsed (details and sr-only included)."""
        return " ".join(self.html.split()).count(needle)

    def count_visible(self, needle: str) -> int:
        """Occurrences outside every <details> (the always-visible text)."""
        return sum(
            1 for text, node in self.text_nodes() if needle in text and not node.in_details()
        )

    def count_in_details(self, needle: str) -> int:
        return sum(1 for text, node in self.text_nodes() if needle in text and node.in_details())

    def links(self) -> list[Node]:
        return [a for a in self.root.find_all("a") if a.attrs.get("href")]

    def external_links(self) -> list[Node]:
        return [a for a in self.links() if a.attrs["href"].startswith(("http://", "https://"))]

    def plain_text(self, skip: frozenset[str] = frozenset({"script", "style", "pre"})) -> str:
        """Page text without scripts and the verbatim notification messages (<pre>)."""
        return " ".join(
            text
            for text, node in self.text_nodes()
            if node.tag not in skip and not any(a.tag in skip for a in node.ancestors())
        )

    def price_text(self) -> str:
        """Text a price can sit next to: the screen-reader table caption is left out."""
        return self.plain_text(frozenset({"script", "style", "pre", "caption"}))


def get(harness: Harness, url: str) -> Page:
    response = harness.client.get(url)
    assert response.status_code == 200, (url, response.status_code)
    return Page(response.text, parse(response.text))


# ---- scenario builders ----------------------------------------------------------------


class TfsLinks:
    """Deterministic link builder: the URL encodes the date pair it was built for."""

    def url(self, search: FlightSearch) -> str | None:
        ret = search.pair.return_date.isoformat() if search.pair.return_date else "-"
        return f"https://www.google.com/travel/flights/search?tfs={search.pair.depart}_{ret}"


def flexible_round_trip(h: Harness, **overrides: Any) -> int:
    """Two date pairs: 12/10-12/15 and 12/11-12/16."""
    return h.create_watch(
        name="東京十二月",
        date_mode="flexible",
        depart_date=None,
        return_date=None,
        window_start="2026-12-10",
        window_end="2026-12-16",
        min_trip_days=5,
        max_trip_days=5,
        **overrides,
    )


def priced_round_trip(h: Harness, **overrides: Any) -> int:
    """The cheaper pair (12/11-12/16, 8,000) is a one-stop +1 day flight; 12/10 is direct."""
    h.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    h.source.prices[("2026-12-11", "2026-12-16")] = 8_000
    h.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    h.source.flights[("2026-12-11", "2026-12-16")] = CZ_TRANSFER
    watch_id = flexible_round_trip(h, **overrides)
    h.scan(watch_id)
    return watch_id


def cheaper_second_round(h: Harness) -> int:
    """A watch whose price drops between two rounds, so a delta badge exists."""
    h.source.prices[("2027-01-10", "2027-01-15")] = 9_000
    watch_id = h.create_watch(
        name="東京一月", depart_date="2027-01-10", return_date="2027-01-15", destination="NRT"
    )
    h.scan(watch_id)
    h.clock.advance(hours=1)
    h.source.prices[("2027-01-10", "2027-01-15")] = 8_500
    h.scan(watch_id)
    return watch_id


def priced_one_way(h: Harness) -> int:
    h.source.prices[("2026-12-20", None)] = 5_000
    h.source.flights[("2026-12-20", None)] = BR_DIRECT
    watch_id = h.create_watch(
        name="大阪單程",
        destination="KIX",
        trip_type="one_way",
        depart_date="2026-12-20",
        return_date=None,
    )
    h.scan(watch_id)
    return watch_id


def done_exploration(h: Harness) -> int:
    service = h.services.exploration
    queued: list[int] = []
    service.hooks.schedule = queued.append
    service.hooks.scheduler_running = lambda: True
    h.source.default_price = 6_000
    h.source.flight = BR_DIRECT
    response = h.client.post("/api/explorations", json=MONTH, headers=CLIENT_HEADERS)
    assert response.status_code == 202, response.json()
    while queued:
        service.run(queued.pop(0))
    return int(response.json()["id"])


def done_comparison(h: Harness) -> int:
    h.source.default_price = 7_000
    h.source.flight = BR_DIRECT
    return compared(h, ComparisonQueue(h.services.comparison))


# ---- helpers on rendered pages ----------------------------------------------------------


def assert_clean_links(page: Page) -> None:
    """C-102: every external link goes to Google Flights, opens a new tab, no opener leak."""
    for link in page.external_links():
        href = link.attrs["href"]
        parsed = urlparse(href)
        assert parsed.scheme == "https", href
        assert parsed.netloc in {"www.google.com", "google.com"}, href
        assert parsed.path.startswith(GOOGLE_FLIGHTS_PATH), href
        assert link.attrs.get("target") == "_blank", href
        rel = set(link.attrs.get("rel", "").split())
        assert {"noopener", "noreferrer"} <= rel, href


def assert_one_disclaimer(page: Page) -> None:
    """C-101: the full DISCLAIMER once in the whole HTML, visible, outside any <details>."""
    assert page.count(DISCLAIMER) == 1
    assert page.count_visible(DISCLAIMER) == 1


def assert_wording_clean(page: Page) -> None:
    text = page.plain_text()
    assert "None" not in text
    assert "查票" not in text
    assert "未在頁面內嵌" not in text and "未內嵌" not in text
    assert "no result section" not in text and "Traceback" not in text
    # "訂票" only inside 「查看並訂票」 and the three approved sentences as a whole.
    leftover = (
        text.replace(DISCLAIMER, "")
        .replace(PRICE_SOURCE_NOTE, "")
        .replace(ROUND_TRIP_NOTE, "")
        .replace("查看並訂票", "")
    )
    assert "訂票" not in leftover
    assert "價格以 Google Flights 頁面為準" not in text
    for banned in ("最便宜", "推薦", "最佳", "超值", "目前最便宜"):
        assert banned not in text.replace("最便宜前 5 個日期", ""), banned
    assert not re.search(r"\sstyle=", page.html), "inline style"
    assert_clean_links(page)


def card(page: Page, watch_id: int) -> Node:
    cards = [
        c for c in page.root.find_all("article") if c.attrs.get("data-watch-id") == str(watch_id)
    ]
    assert len(cards) == 1
    return cards[0]


def main_card(page: Page, watch_id: int) -> Node:
    """The card without FD-19's extra pairs, which carry their own flights and links."""
    one = card(page, watch_id)
    one.children = [
        c for c in one.children if not (isinstance(c, Node) and "more-pairs" in c.classes)
    ]
    return one


def flight_blocks(node: Node) -> list[Node]:
    return node.find_all("div", "flight")


def link_with_text(node: Node, text: str) -> list[Node]:
    return [a for a in node.find_all("a") if text in a.text() and a.attrs.get("href")]


class BrokenLinks:
    """A link builder that cannot build a tfs link: pages fall back to route and dates."""

    def url(self, search: FlightSearch) -> str | None:
        raise RuntimeError("no tfs")


FALLBACK_NOTE = "連結只帶航線與日期；人數、艙等、篩選請在 Google 重選"


def test_fallback_links_carry_the_visible_note(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    harness.services.views._links = BrokenLinks()
    harness.services.exploration_views._links = BrokenLinks()
    harness.services.comparison_views._links = BrokenLinks()
    listing = get(harness, "/")
    one = card(listing, watch_id)
    assert link_with_text(one, BOOKING_SHORT), "the button stays with the fallback link"
    assert FALLBACK_NOTE in one.visible_text()
    detail = get(harness, f"/watches/{watch_id}")
    price_card = detail.main.find_all("section", "price-card")[0]
    assert FALLBACK_NOTE in price_card.visible_text()
    exploration = get(harness, f"/explorations/{done_exploration(harness)}")
    comparison = get(harness, f"/comparisons/{done_comparison(harness)}")
    for page in (listing, detail, exploration, comparison):
        assert page.count_visible(FALLBACK_NOTE) >= 1
        assert_clean_links(page)
        # Inside a fold too, the note sits in the same cell as the link it explains.
        for link_cell in page.main.find_all("td", "cell-link"):
            assert FALLBACK_NOTE in link_cell.visible_text()
    # One note beside every fallback link on the exploration page (one per priced cell).
    calendar = exploration.main.find_all("table", "calendar")[0]
    for cell in calendar.find_all("td", "cal-cell"):
        if link_with_text(cell, BOOKING_SHORT):
            assert FALLBACK_NOTE in cell.visible_text()


# ======================================================================================
# List (cards)
# ======================================================================================


def test_list_card_shows_airline_flight_times_and_booking_link(harness: Harness) -> None:
    harness.services.views._links = TfsLinks()
    watch_id = priced_round_trip(harness)
    page = get(harness, "/")
    one = main_card(page, watch_id)
    text = one.text()
    # Cheapest pair is 12/11-12/16 at 8,000: price, flight and link all come from that row.
    assert BEST_TITLE in text and "TWD 8,000" in text and "TWD 9,000" not in text
    assert "中國南方航空" in text and "CZ 3088 → CZ 3575" in text
    assert "23:55" in text and "03:30" in text and "+1" in text
    assert "TPE" in text and "SHA" in text and "轉機 1 次" in text and "SZX" in text
    assert "長榮航空" not in text and "BR 184" not in text
    booking = link_with_text(one, BOOKING_SHORT)
    assert len(booking) == 1
    assert booking[0].attrs["href"].endswith("tfs=2026-12-11_2026-12-16")
    assert "2026-12-10" not in booking[0].attrs["href"]
    assert booking[0].attrs["target"] == "_blank"
    assert {"noopener", "noreferrer"} <= set(booking[0].attrs["rel"].split())
    assert "（另開新分頁）" in booking[0].text()
    assert BOOKING_BUTTON not in text  # the short label on cards
    assert "去程" in text and "來回總價" in text and ONE_ADULT in text
    assert "1 人總價" not in page.price_text()


def test_list_one_way_has_no_leg_label_or_return_wording(harness: Harness) -> None:
    watch_id = priced_one_way(harness)
    page = get(harness, "/")
    one = card(page, watch_id)
    text = one.text()
    assert "長榮航空" in text and "BR 184" in text and "07:55" in text and "12:00" in text
    assert "直飛" in text
    assert "去程" not in text and "來回總價" not in text
    assert RETURN_EXPLAIN not in page.plain_text()
    assert ONE_ADULT in text


def test_list_round_trip_card_has_only_the_outbound_flight(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    page = get(harness, "/")
    blocks = flight_blocks(main_card(page, watch_id))
    assert len(blocks) == 1
    assert "去程" in blocks[0].text()
    # The return date lives in the dates line, never in the flight block.
    assert "12/16" not in blocks[0].text() and "回" not in blocks[0].text().replace("回程", "")
    assert "回程航班" not in page.plain_text()


def test_list_notes_sit_once_in_the_collapsed_panel(harness: Harness) -> None:
    priced_round_trip(harness)
    cheaper_second_round(harness)  # the second round gives a delta badge
    page = get(harness, "/")
    assert_one_disclaimer(page)
    # FD-22 ruling section 1 (package A) replaces FD-13 M2 / FD-12 R10 / FD-16 for the list:
    # these sentences now sit once in the collapsed price-notes panel. The list shows no
    # change sentence (CEO decision on #9, option (a)).
    assert page.count_in_details(RETURN_EXPLAIN) == 1 and page.count(RETURN_EXPLAIN) == 1
    assert page.count_in_details(BOOKING_HINT) == 1 and page.count(BOOKING_HINT) == 1
    assert page.count(DELTA_EXPLAIN) == 0
    # Disclaimer sits before the first card.
    order = [n for n in page.main.descendants() if "disclaimer" in n.classes or n.tag == "article"]
    assert "disclaimer" in order[0].classes
    assert_wording_clean(page)


def test_list_party_totals_replace_the_one_adult_summary(harness: Harness) -> None:
    watch_id = priced_round_trip(harness, adults=2, children=1)
    page = get(harness, "/")
    one = card(page, watch_id)
    block = one.find_all("div", "price-block")[0]
    assert "2 大 1 小總價" in block.text()
    assert "1 位成人" not in one.text()
    # The budget in the folded conditions names the party too (C-40 (e)).
    conditions = one.find_all("details", "fold")[0]
    assert "預算" in conditions.text() and "2 大 1 小總價" in conditions.text()


def test_list_secondary_actions_are_tucked_in_more(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    page = get(harness, "/")
    one = card(page, watch_id)
    more = one.find_all("details", "more")
    assert len(more) == 1 and "open" not in more[0].attrs
    inside = {b.attrs.get("data-action") for b in more[0].find_all("button")}
    assert {"set-enabled", "delete-watch"} <= inside
    # "scan now" stays one tap away; JS hooks are intact.
    scan = [b for b in one.find_all("button") if b.attrs.get("data-action") == "scan-now"]
    assert len(scan) == 1 and scan[0].attrs["data-watch-id"] == str(watch_id)
    delete = [b for b in one.find_all("button") if b.attrs.get("data-action") == "delete-watch"]
    assert delete[0].attrs["data-watch-name"] == "東京十二月"
    # Edit conditions are folded; no "條件：不限" text.
    assert "條件：不限" not in page.plain_text()
    assert one.find_all("details", "fold")


def test_list_unpriced_card_has_manual_link_not_booking_button(harness: Harness) -> None:
    harness.services.views._links = TfsLinks()
    watch_id = harness.create_watch(name="尚未查價")
    page = get(harness, "/")
    one = card(page, watch_id)
    text = one.text()
    assert "尚未查價" in text
    assert BOOKING_SHORT not in text and BEST_TITLE not in text
    manual = link_with_text(one, MANUAL_LINK)
    assert len(manual) == 1 and manual[0].attrs["href"].endswith("tfs=2026-12-10_2026-12-15")
    assert page.count_visible(BOOKING_HINT) == 0
    assert_one_disclaimer(page)
    assert_wording_clean(page)


def test_list_manual_check_badge_has_collapsed_explanation(harness: Harness) -> None:
    def no_embedded(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights",
            "no_data",
            harness.clock(),
            error="no result section embedded in the page",
            extra={"reason": "no_embedded_results"},
        )

    harness.source.handler = no_embedded
    watch_id = harness.create_watch(name="沒有結果")
    harness.scan(watch_id)
    page = get(harness, "/")
    one = card(page, watch_id)
    assert MANUAL_CHECK in one.text()
    assert one.find_all("details", "explain"), "the long explanation is collapsed"
    assert (
        "Google 未在頁面內嵌" not in page.plain_text()
        or page.count_visible("Google 未在頁面內嵌") == 0
    )
    assert "no result section" not in page.html
    assert_wording_clean(page)


def test_list_stale_price_is_flagged_next_to_the_price(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    harness.clock.advance(hours=200)
    page = get(harness, "/")
    one = card(page, watch_id)
    assert STALE_BADGE in one.text()
    assert one.find_all("span", "price-time"), "visible fetch time next to the price"
    # Stale warnings are never inside a <details>.
    assert page.count_in_details(STALE_BADGE) == 0


def test_list_empty_state_is_short(harness: Harness) -> None:
    page = get(harness, "/")
    assert "還沒有監看。" in page.plain_text()
    assert "建立一個監看後" not in page.plain_text()
    assert_one_disclaimer(page)
    assert not page.root.find_all("article")


def test_list_legacy_rows_show_dashes_not_none(harness: Harness) -> None:
    # No flight details attached: the pre-FD-12 shape of a quote.
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    watch_id = harness.create_watch(name="舊資料")
    harness.scan(watch_id)
    page = get(harness, "/")
    one = card(page, watch_id)
    text = one.text()
    assert "測試航空" in text and "—" in text
    assert BOOKING_SHORT in text, "the booking button stays for legacy rows"
    assert_wording_clean(page)


# ======================================================================================
# Detail
# ======================================================================================


def test_detail_main_card_comes_first_with_cta_and_disclaimer(harness: Harness) -> None:
    harness.services.views._links = TfsLinks()
    watch_id = priced_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    main = page.main
    cards = main.find_all("section", "price-card")
    assert len(cards) == 1
    price_card = cards[0]
    # Order in the document: disclaimer, sampled-only note, main card, then everything else.
    seq = [
        n
        for n in main.descendants()
        if "disclaimer" in n.classes
        or "sampled-note" in n.classes
        or "price-card" in n.classes
        or (n.tag == "section" and "card" in n.classes)
        or n.tag == "details"
    ]
    assert [("disclaimer" in n.classes, "sampled-note" in n.classes) for n in seq[:2]] == [
        (True, False),
        (False, True),
    ]
    assert "price-card" in seq[2].classes
    assert all("price-card" not in n.classes for n in seq[3:])
    text = price_card.text()
    assert BEST_TITLE in text and "TWD 8,000" in text
    assert "中國南方航空" in text and "CZ 3088 → CZ 3575" in text and "03:30" in text
    assert "當地時間" in text
    cta = link_with_text(price_card, BOOKING_BUTTON)
    assert len(cta) == 1
    assert cta[0].attrs["href"].endswith("tfs=2026-12-11_2026-12-16")
    assert BOOKING_HINT in text
    assert RETURN_EXPLAIN in text
    assert_one_disclaimer(page)
    assert page.count(SAMPLED_ONLY_NOTE) == 1 and page.count_visible(SAMPLED_ONLY_NOTE) == 1
    assert page.count_visible(RETURN_EXPLAIN) == 1
    assert_wording_clean(page)


def test_detail_main_card_is_not_emphasised(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    price_card = page.main.find_all("section", "price-card")[0]
    # Same chrome as a list card: only the shared card classes, no badge or ribbon in the title.
    assert price_card.classes == {"price-card"}
    title = price_card.find_all("h2")[0]
    assert title.text() == BEST_TITLE
    assert not title.find_all("span") and not title.find_all("svg")
    assert not [n for n in price_card.descendants() if n.classes & {"ribbon", "best", "recommend"}]


def test_detail_secondary_tables_are_collapsed_details(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    folds = {d.find_all("summary")[0].text(): d for d in page.main.find_all("details", "fold")}
    titles = {name.split("（")[0].split(" ")[0] for name in folds}
    for needed in ("最近價格紀錄", "本次取樣的日期組合", "最近掃描", "監看設定"):
        assert any(name.startswith(needed) for name in folds), (needed, list(folds))
    assert titles
    for detail in page.main.find_all("details", "fold"):
        assert "open" not in detail.attrs
    # Counts in the summary are real row counts.
    recent = next(d for name, d in folds.items() if name.startswith("最近價格紀錄"))
    rows = recent.find_all("tbody")[0].find_all("tr")
    assert f"（{len(rows)} 筆）" in recent.find_all("summary")[0].text()
    # The collapsed content is still in the HTML (works without JavaScript).
    assert "TWD 8,000" in recent.text()
    # Prices in a fold carry their own fetch time.
    assert recent.find_all("span", "price-time")


def test_detail_other_pairs_table_has_flight_and_link_per_row(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    section = next(
        s
        for s in page.main.find_all("section", "card")
        if "其他日期組合" in s.find_all("h2")[0].text()
    )
    headers = [th.text() for th in section.find_all("th")]
    assert any(h.startswith("查到價格") for h in headers)
    assert "航班" in headers and "連結" in headers
    rows = section.find_all("tbody")[0].find_all("tr")
    assert len(rows) == 1  # the best pair is the main card, the other pair is listed
    text = rows[0].text()
    assert "TWD 9,000" in text and "長榮航空" in text and "BR 184" in text and "07:55" in text
    assert link_with_text(rows[0], BOOKING_SHORT)
    assert "查到價格" not in text  # header only


def test_detail_single_adult_has_summary_but_no_per_price_total(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    price_card = page.main.find_all("section", "price-card")[0]
    assert ONE_ADULT in price_card.text()
    assert "1 人總價" not in page.price_text()


def test_detail_party_totals_on_every_price(harness: Harness) -> None:
    watch_id = priced_round_trip(harness, adults=2, children=1)
    page = get(harness, f"/watches/{watch_id}")
    main = page.main
    price_card = main.find_all("section", "price-card")[0]
    assert "2 大 1 小總價" in price_card.text()
    # Every price element on the page is followed by the party note within its cell/card.
    for amount in main.find_all("div", "cell-amount"):
        parent_text = amount.parent.text() if amount.parent else ""
        assert "2 大 1 小總價" in parent_text, parent_text
    for heat in main.find_all("div", "heat"):
        assert "2 大 1 小總價" in heat.text()
    assert "1 位成人" not in page.plain_text().replace("1 位成人・經濟艙", "")


def test_detail_one_way_has_no_return_wording(harness: Harness) -> None:
    watch_id = priced_one_way(harness)
    page = get(harness, f"/watches/{watch_id}")
    text = page.plain_text()
    assert RETURN_EXPLAIN not in text and "來回總價" not in text
    price_card = page.main.find_all("section", "price-card")[0]
    assert "去程" not in price_card.text()
    assert "長榮航空" in price_card.text() and "BR 184" in price_card.text()
    assert_one_disclaimer(page)
    assert_wording_clean(page)


def test_detail_delta_sentence_is_visible_once_in_the_main_card(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    harness.scan(watch_id)
    harness.clock.advance(hours=1)
    harness.source.prices[("2026-12-10", "2026-12-15")] = 8_000
    harness.scan(watch_id)
    page = get(harness, f"/watches/{watch_id}")
    price_card = page.main.find_all("section", "price-card")[0]
    assert "較前一輪" in price_card.text()
    assert DELTA_EXPLAIN in price_card.text()
    assert page.count_visible(DELTA_EXPLAIN) == 1 and page.count(DELTA_EXPLAIN) == 1
    # Falls and rises use the same pill shape: one shared class, no motion.
    assert price_card.find_all("span", "delta")


def test_detail_row_source_only_when_the_page_is_not_all_live(harness: Harness) -> None:
    live_id = priced_round_trip(harness)
    live = get(harness, f"/watches/{live_id}")
    row_source = "Google Flights（即時價）"
    # Only the page-level line carries it; no row repeats the source.
    assert live.count(row_source) == 1
    assert live.count("價格來源：" + row_source) == 1
    harness.source._kind = "cached"
    mixed_id = harness.create_watch(name="快取價", destination="OSA")
    harness.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    harness.scan(mixed_id)
    mixed = get(harness, f"/watches/{mixed_id}")
    assert "價格來源：" not in mixed.plain_text()
    # A cached price is never the live minimum, so it appears in the recent-price rows.
    holders = mixed.main.find_all("td", "cell-price")
    assert holders
    for holder in holders:
        assert "Google Flights" in holder.visible_text()
        assert "快取價，非即時" in holder.visible_text()


def test_detail_legacy_rows_keep_the_layout(harness: Harness) -> None:
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    page = get(harness, f"/watches/{watch_id}")
    price_card = page.main.find_all("section", "price-card")[0]
    assert "測試航空" in price_card.text() and "—" in price_card.text()
    assert link_with_text(price_card, BOOKING_BUTTON)
    assert_one_disclaimer(page)
    assert_wording_clean(page)


def test_detail_without_prices_is_short_and_keeps_manual_link(harness: Harness) -> None:
    watch_id = harness.create_watch(name="空的")
    page = get(harness, f"/watches/{watch_id}")
    assert "尚未查到價格。" in page.plain_text()
    assert not page.main.find_all("section", "price-card")
    assert page.count_visible("排程會依掃描週期自動查價") == 0
    assert page.count_in_details("排程會依掃描週期自動查價") == 1
    assert page.count(SAMPLED_ONLY_NOTE) == 0 or page.count(SAMPLED_ONLY_NOTE) == 1
    assert_one_disclaimer(page)
    # The settings link keeps its wording and the "first date pair" hint visible (R2).
    assert link_with_text(page.main, MANUAL_LINK)
    assert page.count_visible("帶入第一組日期") == 1
    assert_wording_clean(page)


def test_detail_diagnostics_never_leak_adapter_text(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)

    def no_embedded(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights",
            "no_data",
            harness.clock(),
            error="no result section embedded in the page",
            extra={"reason": "no_embedded_results"},
        )

    harness.source.handler = no_embedded
    harness.clock.advance(hours=1)
    harness.scan(watch_id, "manual")
    page = get(harness, f"/watches/{watch_id}")
    assert "no result section" not in page.html
    sampling = next(d for d in page.main.find_all("details", "fold") if "本次取樣" in d.text())
    assert MANUAL_CHECK in sampling.text() and "查詢失敗" not in sampling.text()
    assert_wording_clean(page)


def test_detail_unknown_error_is_a_generic_label(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)

    def boom(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "error", harness.clock(), error="KeyError: 'secret-detail'"
        )

    harness.source.handler = boom
    harness.clock.advance(hours=1)
    harness.scan(watch_id, "manual")
    page = get(harness, f"/watches/{watch_id}")
    assert "KeyError" not in page.html and "secret-detail" not in page.html
    assert "查詢失敗" in page.main.text()


# ======================================================================================
# Exploration and comparison
# ======================================================================================


def test_exploration_result_page_structure(harness: Harness) -> None:
    exploration_id = done_exploration(harness)
    page = get(harness, f"/explorations/{exploration_id}")
    assert_one_disclaimer(page)
    text = page.main.text()
    assert ONE_ADULT in text and "1 人總價" not in page.price_text()
    # Return-leg sentence sits above the calendar, visible.
    assert page.count_visible(RETURN_EXPLAIN) == 1
    explain = next(n for n in page.main.descendants() if "return-explain" in n.classes)
    calendar = page.main.find_all("table", "calendar")[0]
    nodes = list(page.main.descendants())
    assert nodes.index(explain) < nodes.index(calendar)
    assert page.count_visible(BOOKING_HINT) == 1
    cells = [td for td in calendar.find_all("td", "cal-cell") if td.find_all("div", "flight")]
    assert cells, "priced calendar cells carry a compact flight"
    for cell in cells:
        assert "長榮航空" in cell.text() and "BR 184" in cell.text()
        assert "07:55" in cell.text() and "12:00" in cell.text() and "直飛" in cell.text()
        assert link_with_text(cell, BOOKING_SHORT)
    top5 = [t for t in page.main.find_all("table", "flights")][0]
    assert "去程航班" in [th.text() for th in top5.find_all("th")]
    for row in top5.find_all("tbody")[0].find_all("tr"):
        assert "BR 184" in row.text() and link_with_text(row, BOOKING_SHORT)
    assert_wording_clean(page)


def test_exploration_calendar_cells_stay_compact(harness: Harness) -> None:
    exploration_id = done_exploration(harness)
    page = get(harness, f"/explorations/{exploration_id}")
    calendar = page.main.find_all("table", "calendar")[0]
    cells = [td for td in calendar.find_all("td", "cal-cell") if td.find_all("div", "flight")]
    assert cells
    for cell in cells:
        # The leg label and airports are on the page-level sentence / top-5 table, not per cell.
        assert "去程" not in cell.visible_text()
        assert "TPE" not in cell.visible_text() and "NRT" not in cell.visible_text()


def test_exploration_calendar_note_is_visible_text(harness: Harness) -> None:
    exploration_id = done_exploration(harness)
    page = get(harness, f"/explorations/{exploration_id}")
    note = "每格為該出發日單次查到的最低價；低／中／高只與本次已查到的價格相比。"
    assert page.count_visible(note) == 1


def test_exploration_manual_cells_use_the_short_label(harness: Harness) -> None:
    def no_embedded(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights",
            "no_data",
            harness.clock(),
            error="no result section embedded in the page",
            extra={"reason": "no_embedded_results"},
        )

    harness.source.handler = no_embedded
    service = harness.services.exploration
    queued: list[int] = []
    service.hooks.schedule = queued.append
    service.hooks.scheduler_running = lambda: True
    response = harness.client.post("/api/explorations", json=MONTH, headers=CLIENT_HEADERS)
    assert response.status_code == 202
    while queued:
        service.run(queued.pop(0))
    page = get(harness, f"/explorations/{int(response.json()['id'])}")
    assert MANUAL_CHECK in page.main.text()
    assert "no result section" not in page.html
    assert "請用查票連結" not in page.html
    assert_one_disclaimer(page)
    assert_wording_clean(page)


def test_exploration_progress_page_has_one_disclaimer(harness: Harness) -> None:
    service = harness.services.exploration
    queued: list[int] = []
    service.hooks.schedule = queued.append
    service.hooks.scheduler_running = lambda: True
    response = harness.client.post("/api/explorations", json=MONTH, headers=CLIENT_HEADERS)
    assert response.status_code == 202
    page = get(harness, f"/explorations/{int(response.json()['id'])}")
    assert page.root.find_all("section") and page.html.count('id="exploration-progress"') == 1
    assert_one_disclaimer(page)


def test_comparison_result_page_structure(harness: Harness) -> None:
    comparison_id = done_comparison(harness)
    page = get(harness, f"/comparisons/{comparison_id}")
    assert_one_disclaimer(page)
    assert ONE_ADULT in page.main.text() and "1 人總價" not in page.price_text()
    assert page.count_visible(RETURN_EXPLAIN) == 1
    assert page.count_visible("只依總價由低到高排列，未比較飛行時間、轉機與行李。") == 1
    table = page.main.find_all("table", "comparison")[0]
    headers = [th.text() for th in table.find_all("th")]
    assert "去程航班" in headers and "飛行時間（不含轉機等候）" in headers
    for banned in ("航空", "轉機", "出發時刻"):
        assert banned not in headers
    rows = table.find_all("tbody")[0].find_all("tr")
    assert rows
    for row in rows:
        assert "長榮航空" in row.text() and "BR 184" in row.text()
        assert "07:55" in row.text() and "12:00" in row.text()
        assert link_with_text(row, BOOKING_SHORT)
        assert row.find_all("span", "price-time"), "each price shows its fetch time"
    assert_wording_clean(page)


# ======================================================================================
# Forms, settings and cross-page rules
# ======================================================================================


@pytest.mark.parametrize("url", ["/explore", "/explore/compare"])
def test_form_pages_have_one_disclaimer_and_the_short_hint(harness: Harness, url: str) -> None:
    page = get(harness, url)
    assert_one_disclaimer(page)
    hints = [n for n in page.root.descendants() if "data-unembedded-hint" in n.attrs]
    if url == "/explore":
        assert len(hints) == 1 and hints[0].text() == UNEMBEDDED_FORM_HINT
    assert_wording_clean(page)


def test_watch_form_hint_and_footer(harness: Harness) -> None:
    page = get(harness, "/watches/new")
    hint = [n for n in page.root.descendants() if "data-unembedded-hint" in n.attrs]
    assert len(hint) == 1 and hint[0].text() == UNEMBEDDED_FORM_HINT
    assert "hidden" in hint[0].attrs, "the JS hook keeps toggling it"
    assert page.count(DISCLAIMER) == 1  # footer copy on a page without prices
    assert_wording_clean(page)


def test_settings_raw_errors_only_inside_technical_details(harness: Harness) -> None:
    harness.services.health.record_failure("google_flights", "ReadTimeout: raw adapter text")
    page = get(harness, "/settings")
    assert "ReadTimeout: raw adapter text" in page.html
    assert page.count_visible("ReadTimeout: raw adapter text") == 0
    assert page.count_in_details("ReadTimeout: raw adapter text") == 1
    details = [d for d in page.main.find_all("details") if "ReadTimeout" in d.text()]
    assert len(details) == 1 and "open" not in details[0].attrs
    assert_wording_clean(page)


def test_every_page_has_valid_links_and_no_forbidden_wording(harness: Harness) -> None:
    harness.services.views._links = TfsLinks()
    watch_id = priced_round_trip(harness)
    priced_one_way(harness)
    harness.create_watch(name="尚未查價", destination="OKA")
    exploration_id = done_exploration(harness)
    comparison_id = done_comparison(harness)
    urls = [
        "/",
        f"/watches/{watch_id}",
        f"/explorations/{exploration_id}",
        f"/comparisons/{comparison_id}",
        "/explore",
        "/explore/compare",
        "/watches/new",
        "/notifications",
        "/settings",
    ]
    for url in urls:
        page = get(harness, url)
        assert_wording_clean(page)
        if url == "/notifications":
            # Stored Telegram messages (<pre>) quote the disclaimer themselves.
            assert page.count_visible(DISCLAIMER) >= 1
            continue
        assert page.count(DISCLAIMER) == 1, url
        assert page.count_in_details(DISCLAIMER) == 0, url


def test_required_visible_items_are_never_inside_details(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    harness.clock.advance(hours=200)
    detail = get(harness, f"/watches/{watch_id}")
    listing = get(harness, "/")
    for page in (detail, listing):
        assert page.count_in_details(DISCLAIMER) == 0
    # FD-22 ruling section 1: on the list the other sentences live in the collapsed panel.
    for needle in (RETURN_EXPLAIN, BOOKING_HINT):
        assert detail.count_in_details(needle) == 0, needle
        assert listing.count_in_details(needle) == 1, needle
    assert detail.count_in_details(SAMPLED_ONLY_NOTE) == 0
    # The stale badge of the main card and of a list card is outside every <details>.
    for page, selector in ((detail, "price-card"), (listing, "price-block")):
        holder = next(
            n for n in page.main.descendants() if selector in n.classes and not n.in_details()
        )
        badges = [b for b in holder.find_all("span", "badge") if STALE_BADGE in b.text()]
        assert badges, selector
        assert not any(b.in_details_inside(holder) for b in badges)
    # Every price element sits next to a visible fetch time, at any depth.
    for page in (detail, listing):
        for amount in page.main.find_all("span", "price-amount"):
            block = amount.parent.parent if amount.parent and amount.parent.parent else None
            assert block is not None and block.find_all("span", "price-time")
        for amount in page.main.find_all("div", "cell-amount"):
            cell = amount.parent
            assert cell is not None and cell.find_all("span", "price-time")


def test_main_has_no_animation_or_inline_style_hooks() -> None:
    from flight_deals.web.server import WEB_DIR

    css = (WEB_DIR / "static" / "app.css").read_text(encoding="utf-8")
    assert "@keyframes" not in css
    assert not re.search(r"(^|[;{\s])animation(-[a-z-]+)?\s*:", css)
    assert "transition: all" not in css
    # innerHTML never appears in the page script (CSP + XSS rule).
    assert "innerHTML" not in (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    for name in ("index", "watch_detail", "exploration", "comparison", "settings", "_macros"):
        source = (WEB_DIR / "templates" / f"{name}.html").read_text(encoding="utf-8")
        assert "style=" not in source, name


# ---- risk-gate first comparison (M1 to M6 and suggestions) ------------------------------------


def one_way_exploration(h: Harness) -> int:
    service = h.services.exploration
    queued: list[int] = []
    service.hooks.schedule = queued.append
    service.hooks.scheduler_running = lambda: True
    h.source.default_price = 6_000
    h.source.flight = BR_DIRECT
    body = {**MONTH, "trip_type": "one_way", "trip_days": None}
    response = h.client.post("/api/explorations", json=body, headers=CLIENT_HEADERS)
    assert response.status_code == 202, response.json()
    while queued:
        service.run(queued.pop(0))
    return int(response.json()["id"])


def one_way_comparison(h: Harness) -> int:
    h.source.default_price = 7_000
    h.source.flight = BR_DIRECT
    return compared(
        h, ComparisonQueue(h.services.comparison), trip_type="one_way", return_date=None
    )


def test_price_source_note_once_on_every_page_with_prices(harness: Harness) -> None:  # M2 / #46
    watch_id = priced_round_trip(harness)
    exploration_id = done_exploration(harness)
    comparison_id = done_comparison(harness)
    assert harness.notifier.sent  # the log below shows a price
    for url in (
        "/",
        f"/watches/{watch_id}",
        f"/explorations/{exploration_id}",
        f"/comparisons/{comparison_id}",
        "/explore",
        "/explore/compare",
        "/notifications",
    ):
        page = get(harness, url)
        if url == "/":
            # FD-22 ruling section 1: the list keeps it once, first in the collapsed panel.
            assert page.count(PRICE_SOURCE_NOTE) == 1
            assert page.count_in_details(PRICE_SOURCE_NOTE) == 1
            assert_one_disclaimer(page)
            continue
        assert page.count_visible(PRICE_SOURCE_NOTE) == 1, url
        if url != "/notifications":  # the log also keeps the sent Telegram text
            assert page.count(PRICE_SOURCE_NOTE) == 1, url
            assert page.count_in_details(PRICE_SOURCE_NOTE) == 0, url
            assert_one_disclaimer(page)


def test_price_source_note_sits_right_after_the_disclaimer(harness: Harness) -> None:  # M2
    watch_id = priced_round_trip(harness)
    # FD-22 ruling section 1 replaces M2 for the list ("/"): there the summary line and the
    # collapsed panel follow DISCLAIMER (see test_fd22_list_simplify).
    for url in (f"/watches/{watch_id}", f"/explorations/{done_exploration(harness)}"):
        html = get(harness, url).html
        between = html.split(DISCLAIMER, 1)[1].split(PRICE_SOURCE_NOTE, 1)[0]
        assert "<details" not in between and "<section" not in between, url
        assert len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", between))) == 0, url


def test_price_source_note_absent_without_any_price(harness: Harness) -> None:
    watch_id = harness.create_watch()
    for url in ("/", f"/watches/{watch_id}", "/explore", "/explore/compare", "/notifications"):
        assert PRICE_SOURCE_NOTE not in get(harness, url).html, url


def test_booking_hint_is_the_new_sentence(harness: Harness) -> None:  # M1
    page = get(harness, f"/watches/{priced_round_trip(harness)}")
    assert page.count_visible("請依航空公司與起降時刻選擇") == 1
    assert "請依航班號碼選擇" not in page.html


def test_one_stop_rows_say_flight_time_excludes_the_layover(harness: Harness) -> None:  # M3
    watch_id = priced_round_trip(harness)
    transfer = "轉機 1 次（SZX）・飛行 3 小時（不含轉機等候）"
    assert transfer in get(harness, "/").plain_text()
    page = get(harness, f"/watches/{watch_id}")
    assert transfer in page.plain_text()
    assert "直飛・3 小時" in page.plain_text()  # nonstop rows are unchanged
    assert "直飛・飛行" not in page.plain_text()


def test_comparison_duration_column_says_it_excludes_the_layover(harness: Harness) -> None:  # M3
    page = get(harness, f"/comparisons/{done_comparison(harness)}")
    table = page.main.find_all("table", "comparison")[0]
    assert "飛行時間（不含轉機等候）" in [th.text() for th in table.find_all("th")]


def test_local_time_sentence_on_results_and_in_list_help(harness: Harness) -> None:  # M4
    exploration = get(harness, f"/explorations/{done_exploration(harness)}")
    comparison = get(harness, f"/comparisons/{done_comparison(harness)}")
    for page in (exploration, comparison):
        assert page.count_visible(LOCAL_TIME) == 1 and page.count(LOCAL_TIME) == 1
    priced_round_trip(harness)
    listing = get(harness, "/")
    assert listing.count_in_details(LOCAL_TIME) == 1


def test_flight_column_heading_round_trip(harness: Harness) -> None:  # M5
    for url in (
        f"/explorations/{done_exploration(harness)}",
        f"/comparisons/{done_comparison(harness)}",
    ):
        assert '<th scope="col">去程航班</th>' in get(harness, url).html, url


def test_flight_column_heading_one_way(harness: Harness) -> None:  # M5
    for url in (
        f"/explorations/{one_way_exploration(harness)}",
        f"/comparisons/{one_way_comparison(harness)}",
    ):
        html = get(harness, url).html
        assert "去程航班" not in html and '<th scope="col">航班</th>' in html, url


def test_recent_explorations_state_party_and_cabin(harness: Harness) -> None:  # M6
    done_exploration(harness)
    text = get(harness, "/explore").main.text()
    assert "來回・不限｜1 位成人・經濟艙" in text


def test_exploration_party_line_has_no_price_caption(harness: Harness) -> None:
    page = get(harness, f"/explorations/{done_exploration(harness)}")
    facts = page.main.find_all("dl", "facts")[0].text()
    assert ONE_ADULT in facts and "來回總價" not in facts


def test_comparison_price_times_are_labelled(harness: Harness) -> None:
    text = get(harness, f"/comparisons/{done_comparison(harness)}").main.text()
    assert "查到時間 2026-10-25 12:00" in text


def test_detail_dates_show_weekdays(harness: Harness) -> None:
    page = get(harness, f"/watches/{priced_round_trip(harness)}")
    assert "12/11（週五）–12/16（週三）" in page.main.text()


def test_scheduler_events_sit_in_technical_details(harness: Harness) -> None:
    harness.repo.insert_event(harness.clock(), "scan_skipped", "watch:1 lock held")
    page = get(harness, "/settings")
    assert page.count_in_details("scan_skipped") == 1
    assert page.count_visible("scan_skipped") == 0
    assert "技術細節：排程事件" in page.html


# ---- risk-gate re-review (N1, N2) ------------------------------------------------------------


def not_embedded_source(h: Harness) -> None:
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", h.clock(), extra={"reason": "no_embedded_results"}
        )

    h.source.handler = handler


def test_detail_manual_check_explains_inside_details(harness: Harness) -> None:  # N1
    not_embedded_source(harness)
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    page = get(harness, f"/watches/{watch_id}")
    assert page.count_visible(MANUAL_CHECK) >= 1
    assert page.count(MANUAL_CHECK_EXPLAIN) == 1
    assert page.count_in_details(MANUAL_CHECK_EXPLAIN) == 1
    assert page.count_visible(MANUAL_CHECK_EXPLAIN) == 0


def test_detail_manual_check_explained_without_a_no_price_card(harness: Harness) -> None:  # N1
    harness.source._kind = "cached"  # observations exist, none can be shown as the main card
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.source._kind = "live"
    not_embedded_source(harness)
    harness.clock.advance(hours=7)
    harness.scan(watch_id)
    page = get(harness, f"/watches/{watch_id}")
    assert not page.main.find_all("section", "empty")
    assert page.count_in_details(MANUAL_CHECK_EXPLAIN) == 1


def test_detail_without_manual_check_has_no_explanation(harness: Harness) -> None:  # N1
    page = get(harness, f"/watches/{priced_round_trip(harness)}")
    assert page.count(MANUAL_CHECK_EXPLAIN) == 0


def test_detail_manual_link_sits_in_the_no_price_card_once(harness: Harness) -> None:  # N1
    watch_id = harness.create_watch()
    page = get(harness, f"/watches/{watch_id}")
    (card,) = page.main.find_all("section", "empty")
    assert MANUAL_LINK in card.text() and "帶入第一組日期" in card.text()
    assert page.count_visible(MANUAL_LINK) == 1


def test_detail_with_prices_keeps_the_manual_link_below(harness: Harness) -> None:  # R2
    page = get(harness, f"/watches/{priced_round_trip(harness)}")
    assert page.main.find_all("p", "settings-link")
    assert page.count_visible(MANUAL_LINK) == 1 and "帶入第一組日期" in page.main.text()


def test_list_manual_check_card_says_no_displayable_price(harness: Harness) -> None:  # N2
    not_embedded_source(harness)
    watch_id = harness.create_watch(name="東京")
    harness.scan(watch_id)
    text = card(get(harness, "/"), watch_id).text()
    assert NO_DISPLAYABLE_PRICE in text and "尚未查價" not in text
    assert MANUAL_CHECK in text


def test_list_ended_card_says_no_displayable_price(harness: Harness) -> None:  # N2
    watch_id = harness.create_watch(name="東京")
    harness.scan(watch_id)
    harness.clock.advance(days=60)
    harness.repo.set_watch_status(watch_id, "expired", harness.clock())
    text = card(get(harness, "/"), watch_id).text()
    assert NO_DISPLAYABLE_PRICE in text and "尚未查價" not in text and "已結束" in text


def test_list_never_scanned_card_keeps_not_scanned(harness: Harness) -> None:  # N2
    watch_id = harness.create_watch(name="東京")
    text = card(get(harness, "/"), watch_id).text()
    assert "尚未查價" in text and NO_DISPLAYABLE_PRICE not in text


def test_list_priced_card_has_neither_no_price_label(harness: Harness) -> None:  # N2
    watch_id = priced_round_trip(harness)
    text = card(get(harness, "/"), watch_id).text()
    assert "尚未查價" not in text and NO_DISPLAYABLE_PRICE not in text


def test_no_displayable_price_is_policy_checked() -> None:  # N2, #47
    assert NO_DISPLAYABLE_PRICE in all_static_texts()


# ======================================================================================
# FD-14: split-ticket note
# ======================================================================================


def test_split_ticket_note_once_and_visible_on_round_trip_pages(harness: Harness) -> None:
    watch_id = priced_round_trip(harness)
    exploration_id = done_exploration(harness)
    comparison_id = done_comparison(harness)
    for url in (
        "/",
        f"/watches/{watch_id}",
        f"/explorations/{exploration_id}",
        f"/comparisons/{comparison_id}",
    ):
        page = get(harness, url)
        assert page.count(ROUND_TRIP_NOTE) == 1, url
        if url == "/":
            # FD-22 ruling section 1 (replaces the FD-16 "always visible" rule on the list).
            assert page.count_in_details(ROUND_TRIP_NOTE) == 1
        else:
            assert page.count_visible(ROUND_TRIP_NOTE) == 1, url
            assert page.count_in_details(ROUND_TRIP_NOTE) == 0, url
        note = next(
            n for n in page.main.descendants() if ROUND_TRIP_NOTE in n.text() and n.tag == "p"
        )
        assert "return-explain" in note.classes, url  # keeps its place on the phone layout


def test_split_ticket_note_absent_on_one_way_pages(harness: Harness) -> None:
    watch_id = priced_one_way(harness)
    for url in (
        "/",
        f"/watches/{watch_id}",
        f"/explorations/{one_way_exploration(harness)}",
        f"/comparisons/{one_way_comparison(harness)}",
    ):
        assert ROUND_TRIP_NOTE not in get(harness, url).html, url


def test_split_ticket_note_absent_without_a_price(harness: Harness) -> None:
    watch_id = harness.create_watch()
    for url in ("/", f"/watches/{watch_id}"):
        assert ROUND_TRIP_NOTE not in get(harness, url).html, url


def test_split_ticket_note_once_on_a_mixed_list(harness: Harness) -> None:
    priced_round_trip(harness)
    priced_one_way(harness)
    assert get(harness, "/").count(ROUND_TRIP_NOTE) == 1


def test_split_ticket_note_stays_when_only_mismatched_cells_are_priced(
    harness: Harness,
) -> None:  # FD-14 R3: top5 is empty, the calendar still shows amounts and links
    harness.source.currency = "JPY"
    exploration_id = done_exploration(harness)
    html = get(harness, f"/explorations/{exploration_id}").html
    assert RETURN_EXPLAIN not in html
    assert ROUND_TRIP_NOTE in html


def test_split_ticket_note_is_not_written_back_into_old_notifications(
    harness: Harness,
) -> None:  # FD-14 R6: the log shows the text as it was sent
    priced_round_trip(harness)
    record = harness.repo.list_notifications()[0]
    assert ROUND_TRIP_NOTE in record.message_text  # a round-trip alert carries it now
    old_text = record.message_text.replace(ROUND_TRIP_NOTE, "").rstrip()
    harness.repo.update_notification_text(record.id, old_text)

    page = get(harness, "/notifications")
    assert ROUND_TRIP_NOTE not in page.html
    assert page.count_in_details(old_text.splitlines()[0]) == 1


def test_one_way_notifications_never_carry_the_split_ticket_note(harness: Harness) -> None:
    priced_one_way(harness)
    assert harness.notifier.sent
    assert ROUND_TRIP_NOTE not in get(harness, "/notifications").html


def test_split_ticket_note_stays_on_a_detail_page_without_a_main_card(
    harness: Harness,
) -> None:  # FD-14 risk re-review: other-currency records still show amounts and links
    harness.source.currency = "JPY"
    watch_id = priced_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    assert not page.main.find_all("section", "price-card")
    assert page.count(ROUND_TRIP_NOTE) == 1
    assert page.count_visible(ROUND_TRIP_NOTE) == 1
    assert page.count_in_details(ROUND_TRIP_NOTE) == 0


def test_round_trip_note_stays_when_every_date_has_departed(harness: Harness) -> None:
    harness.source.currency = "JPY"  # FD-16 R3: the folded records can still show labels
    watch_id = priced_round_trip(harness)
    harness.clock.advance(days=120)
    page = get(harness, f"/watches/{watch_id}")
    assert DETAIL_ALL_DEPARTED in page.html
    assert page.count_visible(ROUND_TRIP_NOTE) == 1


def test_one_way_detail_without_a_main_card_has_no_split_ticket_note(harness: Harness) -> None:
    harness.source.currency = "JPY"
    watch_id = priced_one_way(harness)
    assert ROUND_TRIP_NOTE not in get(harness, f"/watches/{watch_id}").html
