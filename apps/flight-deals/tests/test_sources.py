"""Adapter contract tests (C-4, C-6, C-26, C-27, C-31) on recorded Google payloads."""

from __future__ import annotations

import importlib.metadata
import json
import re
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.models import DatePair, FlightSearch
from flight_deals.ports import ParseStats, SourceResult
from flight_deals.sources import google_flights, google_payload
from flight_deals.sources._support import Throttle, TTLCache, backoff_delay, call_with_timeout
from flight_deals.sources.fixture import FixtureSource
from flight_deals.sources.google_flights import (
    VERIFIED_FAST_FLIGHTS_VERSION,
    GoogleFlightsSource,
    build_query,
)
from flight_deals.sources.google_payload import (
    PayloadErrorStatus,
    PayloadFormatError,
    classify_itinerary,
    extract_payload,
    parse_payload,
)
from tests.conftest import FIXTURES, ROUNDTRIP_FIXTURE, FakeClock

APP_DIR = Path(__file__).resolve().parents[1]
SHA_PAYLOAD_FIXTURE = FIXTURES / "payload_TPE_SHA.json"

SEARCH = FlightSearch(
    origin="TPE",
    destination="NRT",
    pair=DatePair(date(2026, 12, 10), date(2026, 12, 15)),
    max_stops=1,
)
SHA_SEARCH = FlightSearch(
    origin="TPE", destination="SHA", pair=DatePair(date(2026, 12, 10)), max_stops=None
)


def sha_payload() -> Any:
    """Raw ds:1 payload recorded live for TPE->SHA (4 itineraries, 2 without a price)."""
    return json.loads(SHA_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))


def page_html(payload: Any, *, script_class: str = "ds:1") -> str:
    """Wrap a payload the way the results page embeds it."""
    data = json.dumps(payload, ensure_ascii=False)
    script = f"AF_initDataCallback({{key: 'ds:1', hash: '2', data:{data}, sideChannel: {{}}}});"
    return (
        "<!doctype html><html><head><script nonce=\"n\">var x = '<div>';</script></head>"
        f'<body><div>header</div><script class="{script_class}" nonce="n">{script}</script>'
        "<script class=\"ds:2\">AF_initDataCallback({key: 'ds:2', data:[1], sideChannel: {}});"
        "</script></body></html>"
    )


def itineraries(payload: Any) -> list[Any]:
    """The "other flights" section, payload[3][0]."""
    result: list[Any] = payload[3][0]
    return result


def best_itineraries(payload: Any) -> list[Any]:
    """The "best flights" section, payload[2][0]."""
    result: list[Any] = payload[2][0]
    return result


def other_only(payload: Any) -> Any:
    """Drop the "best flights" section so a variant exercises one list only."""
    payload[2] = None
    return payload


def unpriced_only(payload: Any) -> Any:
    other_only(payload)
    payload[3][0] = [k for k in itineraries(payload) if k[1][0] == []]
    return payload


class Recorder:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, _search: FlightSearch) -> Any:
        self.calls += 1
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, BaseException):
            raise response
        return response


def make_source(
    fetch: Any, clock: FakeClock, *, attempts: int = 2, timeout: float = 5.0
) -> tuple[GoogleFlightsSource, list[float]]:
    sleeps: list[float] = []
    source = GoogleFlightsSource(
        timeout_seconds=timeout,
        max_attempts=attempts,
        backoff_base_seconds=2.0,
        throttle=Throttle(0.0, sleep=sleeps.append),
        cache=TTLCache(600.0),
        fetch=fetch,
        clock=clock,
        sleep=sleeps.append,
    )
    return source, sleeps


def assert_contract(result: SourceResult, source_name: str) -> None:
    assert result.status == "ok"
    assert result.quotes
    for quote in result.quotes:
        assert quote.source == source_name
        assert quote.price_kind == "live"
        assert isinstance(quote.amount_minor, int) and not isinstance(quote.amount_minor, bool)
        assert quote.amount_minor > 0
        assert quote.currency == "TWD"
        assert quote.as_of.tzinfo is not None and quote.fetched_at.tzinfo is not None
        assert quote.as_of_basis == "fetch_time"
        assert quote.depart_date == date(2026, 12, 10)
        assert quote.return_date == date(2026, 12, 15)


def test_google_flights_contract_on_recorded_sha_payload(clock: FakeClock) -> None:  # C-26
    source, _ = make_source(Recorder(page_html(sha_payload())), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "ok" and result.error is None
    # Both sections: 5 "best" + 4 "other" itineraries, no duplicates (FD-5 batch 2).
    assert result.parse_stats == ParseStats(
        itineraries=9, priced=7, unpriced=2, malformed=0, best=5, other=4
    )
    assert sorted(q.amount_minor for q in result.quotes) == [
        463300, 463300, 622100, 783300, 882100, 1265500, 1476300,
    ]  # fmt: skip
    for quote in result.quotes:
        assert quote.source == "google_flights" and quote.price_kind == "live"
        assert isinstance(quote.amount_minor, int) and not isinstance(quote.amount_minor, bool)
        assert quote.currency == "TWD" and quote.as_of_basis == "fetch_time"
        assert quote.as_of.tzinfo is not None and quote.fetched_at.tzinfo is not None
        assert quote.depart_date == date(2026, 12, 10) and quote.return_date is None
        assert quote.stops == 1 and quote.carrier
    cheapest = min(result.quotes, key=lambda q: q.amount_minor)
    assert cheapest.amount_minor == 463300 and cheapest.carrier == "中國南方航空"
    assert cheapest.duration_minutes == 130 + 135
    other = [q for q in result.quotes if q.amount_minor == 1265500]
    assert other[0].duration_minutes == 145 + 140


def test_build_query_is_round_trip_with_two_legs_and_no_integration() -> None:
    query = build_query(SEARCH)
    assert query.get_trip_type() == "round-trip"
    assert len(query.flight_data) == 2
    assert query.currency == "TWD" and query.language == "zh-TW"


def test_parse_payload_counts_on_recorded_fixture() -> None:  # C-26
    page = parse_payload(sha_payload())
    assert page.stats == ParseStats(
        itineraries=9, priced=7, unpriced=2, malformed=0, best=5, other=4
    )
    assert [r["price"] for r in page.records] == [4633, 4633, 6221, 7833, 8821, 12655, 14763]
    assert [r["type"] for r in page.records] == ["CZ", "CZ", "CX", "ZH", "CX", "multi", "multi"]
    assert all(len(r["airlines"]) == 2 for r in page.records[-2:])
    assert not page.no_results
    other = parse_payload(other_only(sha_payload()))  # the FD-3 view: "other" only
    assert other.stats == ParseStats(itineraries=4, priced=2, unpriced=2, malformed=0, other=4)
    assert [r["price"] for r in other.records] == [12655, 14763]


def test_variant_all_unpriced_is_no_data(clock: FakeClock) -> None:  # C-26, AC-T3
    source, _ = make_source(Recorder(page_html(unpriced_only(sha_payload()))), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "no_data" and result.quotes == () and result.error is None
    assert result.parse_stats == ParseStats(
        itineraries=2, priced=0, unpriced=2, malformed=0, other=2
    )


@pytest.mark.parametrize("bad_price", ["12,655", 12655.0, True, 0, -5, None])
def test_variant_non_int_price_is_malformed(bad_price: Any) -> None:  # C-26
    payload = other_only(sha_payload())
    itineraries(payload)[0][1][0][1] = bad_price
    page = parse_payload(payload)
    assert page.stats == ParseStats(itineraries=4, priced=1, unpriced=2, malformed=1, other=4)
    assert [r["price"] for r in page.records] == [14763]


def test_variant_malformed_only_is_blocked(clock: FakeClock) -> None:  # C-27, AC-T4b
    payload = unpriced_only(sha_payload())
    itineraries(payload)[0][1] = "unexpected"
    source, _ = make_source(Recorder(page_html(payload)), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "blocked" and not result.quotes
    assert result.parse_stats == ParseStats(
        itineraries=2, priced=0, unpriced=1, malformed=1, other=2
    )


def test_variant_priced_plus_malformed_is_ok_with_count(clock: FakeClock) -> None:  # C-27
    payload = other_only(sha_payload())
    itineraries(payload)[2][1] = [[None, "n/a"], "token"]
    source, _ = make_source(Recorder(page_html(payload)), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "ok" and len(result.quotes) == 2
    assert result.parse_stats == ParseStats(
        itineraries=4, priced=2, unpriced=1, malformed=1, other=4
    )


@pytest.mark.parametrize(
    "absent",
    [
        lambda p: p.__setitem__(3, None),  # whole section None (seen live)
        lambda p: p[3].__setitem__(0, None),  # section present, list None
    ],
    ids=["section-none", "list-none"],
)
def test_variant_both_sections_absent_is_no_embedded_results(
    clock: FakeClock, absent: Any
) -> None:  # C-26, C-27, FD-5 batch 2
    payload = other_only(sha_payload())
    absent(payload)
    source, _ = make_source(Recorder(page_html(payload)), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "no_data" and not result.quotes and not result.is_failure
    assert result.extra == {"reason": "no_embedded_results"}
    assert result.parse_stats == ParseStats(0, 0, 0, 0)


@pytest.mark.parametrize(
    "other",
    [{"a": 1}, "results", 42, [], [{"a": 1}], ["x"]],
    ids=["dict", "str", "int", "empty-list", "list-dict", "list-str"],
)
def test_other_section_bad_shape_is_blocked_even_with_best(
    clock: FakeClock, other: Any
) -> None:  # only a whole-None payload[3] counts as absent
    payload = sha_payload()  # "best" present and priced
    payload[3] = other
    source, _ = make_source(Recorder(page_html(payload)), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "blocked" and not result.quotes
    with pytest.raises(PayloadFormatError):
        parse_payload(payload)


def test_other_none_with_best_none_is_no_embedded_results(clock: FakeClock) -> None:
    payload = sha_payload()
    payload[2] = None
    payload[3] = None
    result = make_source(Recorder(page_html(payload)), clock)[0].search(SHA_SEARCH)
    assert result.status == "no_data" and result.extra == {"reason": "no_embedded_results"}


def test_other_none_with_best_data_is_ok(clock: FakeClock) -> None:
    payload = sha_payload()
    payload[3] = None
    result = make_source(Recorder(page_html(payload)), clock)[0].search(SHA_SEARCH)
    assert result.status == "ok" and result.extra == {}
    assert result.parse_stats == ParseStats(
        itineraries=5, priced=5, unpriced=0, malformed=0, best=5
    )


def test_duplicate_key_normalises_departure_time() -> None:
    payload = sha_payload()
    twin = json.loads(json.dumps(itineraries(payload)[0]))
    first = itineraries(payload)[0][0][2][0]
    first[8] = [17]  # 17:00 written as [17] in one section...
    twin[0][2][0][8] = [17, 0]  # ...and as [17, 0] in the other
    best_itineraries(payload).append(twin)
    page = parse_payload(payload)
    assert page.stats.best == 6 and page.stats.itineraries == 9  # merged as one
    assert [r["price"] for r in page.records].count(12655) == 1


def test_same_price_and_carrier_but_other_airport_is_not_merged() -> None:
    payload = sha_payload()
    twin = json.loads(json.dumps(itineraries(payload)[0]))
    twin[0][2][0][3] = "TSA"  # departs from another airport, all else equal
    best_itineraries(payload).append(twin)
    page = parse_payload(payload)
    assert page.stats.itineraries == 10
    assert [r["price"] for r in page.records].count(12655) == 2


def test_variant_only_best_section_is_ok(clock: FakeClock) -> None:  # one section None
    payload = sha_payload()
    payload[3][0] = None
    source, _ = make_source(Recorder(page_html(payload)), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "ok" and result.extra == {}
    assert result.parse_stats == ParseStats(
        itineraries=5, priced=5, unpriced=0, malformed=0, best=5
    )
    assert min(q.amount_minor for q in result.quotes) == 463300


def test_variant_only_other_section_is_ok(clock: FakeClock) -> None:
    payload = sha_payload()
    payload[2] = "not a section"  # the optional section is lenient
    result = make_source(Recorder(page_html(payload)), clock)[0].search(SHA_SEARCH)
    assert result.status == "ok"
    assert sorted(q.amount_minor for q in result.quotes) == [1265500, 1476300]


def test_duplicates_across_sections_are_merged() -> None:
    payload = sha_payload()
    best_itineraries(payload).append(itineraries(payload)[0])  # same itinerary twice
    page = parse_payload(payload)
    assert page.stats == ParseStats(
        itineraries=9, priced=7, unpriced=2, malformed=0, best=6, other=4
    )
    assert [r["price"] for r in page.records].count(12655) == 1
    # Same carrier and times but a different price is a different itinerary.
    copy = json.loads(json.dumps(itineraries(payload)[0]))
    copy[1][0][1] = 12000
    best_itineraries(payload).append(copy)
    assert parse_payload(payload).stats.priced == 8
    # Same price and carrier, different routing (the two CZ 4,633 fares) stay apart.
    assert [r["price"] for r in page.records].count(4633) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"not": "a list"},
        [1, 2, 3],
        [None, None, None, "results"],
        [None, None, None, []],
        [None, None, None, [{"a": 1}]],
        [None, None, None, [[]]],
    ],
    ids=["dict", "too-short", "results-str", "results-empty", "itins-dict", "itins-empty"],
)
def test_variant_bad_top_level_shape_is_blocked(clock: FakeClock, payload: Any) -> None:
    source, _ = make_source(Recorder(page_html(payload)), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "blocked" and not result.quotes
    assert result.parse_stats is not None


def test_optional_fields_fall_back_to_none(clock: FakeClock) -> None:  # Decision 1
    payload = other_only(sha_payload())
    itineraries(payload)[0][0] = "flight info changed"
    page = parse_payload(payload)
    assert page.stats.priced == 2
    assert page.records[0] == {
        "type": None,
        "price": 12655,
        "airlines": [],
        "flights": [],
        "depart_time": None,
    }
    source, _ = make_source(Recorder(page_html(payload)), clock)
    quote = min(source.search(SHA_SEARCH).quotes, key=lambda q: q.amount_minor)
    assert quote.amount_minor == 1265500
    assert quote.carrier is None and quote.stops is None and quote.duration_minutes is None


def test_classify_itinerary_shapes() -> None:  # Decision 1: only k[1][0] == [] is unpriced
    assert classify_itinerary([[], [[None, 100], "t"]]) == "priced"
    assert classify_itinerary([[], [[], "t"]]) == "unpriced"
    assert classify_itinerary([[], [None, "t"]]) == "malformed"
    assert classify_itinerary([[], [[None], "t"]]) == "malformed"
    assert classify_itinerary([[], []]) == "malformed"
    assert classify_itinerary([[]]) == "malformed"
    assert classify_itinerary("x") == "malformed"


# ---- extract_payload: HTML cases (C-26) -------------------------------------------------

ERROR_STATUS_HTML = (
    "<script class=\"ds:1\">AF_initDataCallback({key: 'ds:1', hash: '1', data:null, "
    "errorHasStatus: true, sideChannel: {}});</script>"
)


def test_extract_payload_reads_ds1_script() -> None:
    assert extract_payload(page_html(sha_payload())) == sha_payload()


def test_extract_payload_accepts_extra_classes() -> None:
    assert extract_payload(page_html([1, 2], script_class="xx ds:1 yy")) == [1, 2]


@pytest.mark.parametrize(
    "html",
    [
        "",
        "   ",
        "<html><body>captcha</body></html>",
        page_html([1], script_class="ds:10"),
        "<script class=\"ds:1\">AF_initDataCallback({key: 'ds:1'});</script>",
        '<script class="ds:1">AF_initDataCallback({data:[1, 2, oops], sideChannel: {}});</script>',
    ],
    ids=["empty", "blank", "no-script", "other-class", "no-data-field", "bad-json"],
)
def test_extract_payload_rejects_pages_without_usable_data(html: str) -> None:
    with pytest.raises(PayloadFormatError):
        extract_payload(html)


def test_extract_payload_error_status() -> None:
    with pytest.raises(PayloadErrorStatus):
        extract_payload(ERROR_STATUS_HTML)


def test_extract_payload_handles_large_pages_quickly() -> None:
    filler = "".join(f'<div class="c{i}"><span>x</span></div>' for i in range(60_000))
    html = page_html(sha_payload()).replace("<div>header</div>", filler)
    assert len(html) > 2_000_000
    started = time.perf_counter()
    assert parse_payload(extract_payload(html)).stats.priced == 7
    assert time.perf_counter() - started < 1.0


# ---- status table through the adapter (C-27) ---------------------------------------------


def test_error_status_page_is_no_data(clock: FakeClock) -> None:
    source, _ = make_source(Recorder(ERROR_STATUS_HTML), clock)
    result = source.search(SHA_SEARCH)
    assert result.status == "no_data" and not result.quotes
    assert result.parse_stats == ParseStats(0, 0, 0, 0)


@pytest.mark.parametrize(
    "response",
    ["", "<html><body>unusual traffic</body></html>", None, ["not", "html"]],
    ids=["empty", "no-script", "none", "not-a-string"],
)
def test_blank_or_unparseable_is_blocked_not_no_data(clock: FakeClock, response: Any) -> None:
    fetch = Recorder(response)
    source, _ = make_source(fetch, clock)
    result = source.search(SEARCH)
    assert result.status == "blocked"
    assert not result.quotes and result.parse_stats == ParseStats(0, 0, 0, 0)
    assert fetch.calls == 1, "blocked responses are not hammered with retries"


def test_fetch_exception_is_error_without_stats(clock: FakeClock) -> None:
    source, _ = make_source(Recorder(IndexError("inside the fetcher")), clock, attempts=1)
    result = source.search(SEARCH)
    assert result.status == "error" and result.parse_stats is None


def test_network_error_retries_with_exponential_backoff(clock: FakeClock) -> None:
    fetch = Recorder(ConnectionError("reset"), ConnectionError("reset"), ConnectionError("reset"))
    source, sleeps = make_source(fetch, clock, attempts=3)
    result = source.search(SEARCH)
    assert result.status == "error" and result.attempts == 3 and fetch.calls == 3
    assert [s for s in sleeps if s > 0] == [2.0, 4.0]
    assert backoff_delay(2.0, 3) == 8.0


def test_error_then_success_recovers(clock: FakeClock) -> None:
    fetch = Recorder(ConnectionError("reset"), page_html(sha_payload()))
    source, _ = make_source(fetch, clock, attempts=2)
    result = source.search(SHA_SEARCH)
    assert result.status == "ok" and result.attempts == 2


def test_hard_timeout(clock: FakeClock) -> None:
    release = threading.Event()

    def slow(_search: FlightSearch) -> Any:
        release.wait(2)
        return page_html(sha_payload())

    source, _ = make_source(slow, clock, attempts=1, timeout=0.05)
    started = time.monotonic()
    result = source.search(SEARCH)
    release.set()
    assert result.status == "error" and "timeout" in (result.error or "")
    assert time.monotonic() - started < 1.5


def test_parsing_runs_outside_the_timeout(
    clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-26
    real_parse = google_payload.parse_payload

    def slow_parse(payload: Any) -> Any:
        time.sleep(0.3)
        return real_parse(payload)

    monkeypatch.setattr(google_flights, "parse_payload", slow_parse)
    source, _ = make_source(Recorder(page_html(sha_payload())), clock, attempts=1, timeout=0.1)
    assert source.search(SHA_SEARCH).status == "ok"


def test_every_non_error_result_has_parse_stats(clock: FakeClock) -> None:  # C-27
    responses = [
        page_html(sha_payload()),
        page_html(unpriced_only(sha_payload())),
        ERROR_STATUS_HTML,
        "",
        page_html({"x": 1}),
    ]
    for response in responses:
        source, _ = make_source(Recorder(response), clock, attempts=1)
        result = source.search(SHA_SEARCH)
        assert result.status != "error" and result.parse_stats is not None, response[:60]
        assert all(q.amount_minor > 0 for q in result.quotes)


def test_ttl_cache_serves_repeat_queries_without_outbound_call(clock: FakeClock) -> None:
    fetch = Recorder(page_html(sha_payload()))
    source, _ = make_source(fetch, clock)
    first = source.search(SHA_SEARCH)
    second = source.search(SHA_SEARCH)
    assert fetch.calls == 1
    assert second.from_cache and second.attempts == 0 and second.quotes == first.quotes
    assert second.parse_stats == first.parse_stats


# ---- upstream version tripwire (C-31) ----------------------------------------------------


def test_verified_version_matches_installed_and_locked() -> None:
    assert importlib.metadata.version("fast-flights") == VERIFIED_FAST_FLIGHTS_VERSION
    lock = (APP_DIR / "uv.lock").read_text(encoding="utf-8")
    match = re.search(r'name = "fast-flights"\nversion = "([^"]+)"', lock)
    assert match and match.group(1) == VERIFIED_FAST_FLIGHTS_VERSION
    pyproject = (APP_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert '"fast-flights>=3.1.0,<4"' in pyproject


def test_ttl_cache_expires() -> None:
    now = [0.0]
    cache: TTLCache[str, int] = TTLCache(10.0, clock=lambda: now[0])
    cache.put("a", 1)
    assert cache.get("a") == 1
    now[0] = 11.0
    assert cache.get("a") is None


def test_throttle_enforces_min_interval_with_jitter() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    throttle = Throttle(1.5, 1.0, sleep=fake_sleep, clock=lambda: now[0], rng=lambda: 0.5)
    throttle.wait()
    throttle.wait()
    assert sleeps == [2.0]


def test_call_with_timeout_returns_value() -> None:
    assert call_with_timeout(lambda: 42, 1.0) == 42


def test_fixture_source_contract(clock: FakeClock) -> None:
    source = FixtureSource(ROUNDTRIP_FIXTURE, clock=clock)
    result = source.search(SEARCH)
    assert_contract(result, "fixture")


def test_fixture_source_forced_blocked(clock: FakeClock) -> None:
    source = FixtureSource(ROUNDTRIP_FIXTURE, clock=clock, forced_status="blocked")
    result = source.search(SEARCH)
    assert result.status == "blocked" and not result.quotes
