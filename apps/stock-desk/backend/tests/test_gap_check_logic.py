"""Pure-logic tests of ``scripts/gap_check.py``: calendar parsing, rate limit, comparison, codes.

ADR-0030 supplement 8 point 5 (d), (f) and S-18a "point 5 (d), (f)". All data is synthetic and
no test connects to a network (an autouse guard makes any socket connect fail the test).
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import date, timedelta
from email.message import Message
from io import BytesIO
from typing import Any

import pytest

from tests.gap_check_world import (
    POISON_INDEX,
    SECURITY_PAGE,
    FakeCalendar,
    FakeClock,
    load_script,
    month_body,
    period_of,
    roc,
    weekdays,
)

gc: Any = load_script()


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    yield


# --- ROC dates and month boundaries -------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("115/11/02", date(2026, 11, 2)),
        (" 92/01/02", date(2003, 1, 2)),
        ("99/12/31", date(2010, 12, 31)),
        ("100/01/03", date(2011, 1, 3)),
        ("113/02/29", date(2024, 2, 29)),  # a leap day
        ("115/12/31", date(2026, 12, 31)),
        ("115/01/01", date(2026, 1, 1)),
        ("115/02/29", None),  # not a leap year
        ("115/13/01", None),
        ("115/00/10", None),
        ("2026/11/02", None),
        ("115-11-02", None),
        ("115/11/2", None),
        ("", None),
        (None, None),
        (20261102, None),
    ],
)
def test_roc_year_is_converted_to_the_western_year(cell: object, expected: date | None) -> None:
    assert gc.roc_to_date(cell) == expected


def test_the_synthetic_roc_text_round_trips_for_every_year_of_the_range() -> None:
    for year in (1999, 2003, 2010, 2011, 2024, 2026):
        day = date(year, 12, 31)
        assert gc.roc_to_date(roc(day)) == day


def test_months_between_crosses_the_year_boundary() -> None:
    assert gc.months_between(date(2025, 12, 15), date(2026, 1, 3)) == [(2025, 12), (2026, 1)]
    assert gc.months_between(date(2026, 1, 31), date(2026, 1, 31)) == [(2026, 1)]
    assert gc.months_between(date(2025, 11, 30), date(2026, 3, 1)) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)
    ]  # fmt: skip


def test_the_check_period_is_500_days_before_the_run_date_through_the_day_before() -> None:
    start, end = gc.check_period(date(2026, 11, 19))
    assert (start, end) == (date(2025, 7, 7), date(2026, 11, 18))
    assert (date(2026, 11, 19) - start).days == 500
    assert gc.months_between(start, end)[0] == (2025, 7)
    assert gc.months_between(start, end)[-1] == (2026, 11)
    assert len(gc.months_between(start, end)) == 17
    # The end never comes from any record: it depends on the run date alone.
    assert gc.check_period(date(2026, 1, 1))[1] == date(2025, 12, 31)


def test_a_month_with_a_row_of_another_month_is_unusable() -> None:
    body = month_body([date(2026, 10, 30), date(2026, 11, 2)])
    assert gc.parse_month(body, 2026, 11) is None
    assert gc.parse_month(body, 2026, 10) is None


def test_a_month_parses_to_exactly_its_dates_and_reads_no_other_cell() -> None:
    days = weekdays(date(2026, 11, 1), date(2026, 11, 30))
    assert gc.parse_month(month_body(days), 2026, 11) == frozenset(days)


# --- 307 pages, bad JSON and unexpected content are "unchecked" ---------------------------------

GOOD = month_body([date(2026, 11, 2)])
BAD_BODIES = {
    "security page": SECURITY_PAGE,
    "empty": b"",
    "bad json": b'{"stat": "OK", ',
    "not utf8": b"\xff\xfe\x00",
    "json list": b"[]",
    "json string": b'"OK"',
    "stat not ok": b'{"stat": "no data", "fields": ["\xe6\x97\xa5\xe6\x9c\x9f"], "data": []}',
    "no fields": b'{"stat": "OK", "data": [["115/11/02"]]}',
    "wrong first field": b'{"stat": "OK", "fields": ["x"], "data": [["115/11/02"]]}',
    "empty data": '{"stat": "OK", "fields": ["日期"], "data": []}'.encode(),
    "data not list": '{"stat": "OK", "fields": ["日期"], "data": "x"}'.encode(),
    "row not list": '{"stat": "OK", "fields": ["日期"], "data": ["115/11/02"]}'.encode(),
    "empty row": '{"stat": "OK", "fields": ["日期"], "data": [[]]}'.encode(),
    "bad date": '{"stat": "OK", "fields": ["日期"], "data": [["115/02/30"]]}'.encode(),
    "date not text": '{"stat": "OK", "fields": ["日期"], "data": [[1151102]]}'.encode(),
    "too large": b" " * ((1 << 20) + 1),
}


@pytest.mark.parametrize("name", sorted(BAD_BODIES))
def test_an_unexpected_body_makes_the_month_unchecked(name: str) -> None:
    assert gc.parse_month(BAD_BODIES[name], 2026, 11) is None
    calendar = gc.fetch_calendar(
        [(2026, 11)],
        get=lambda _u: (200, BAD_BODIES[name]),
        clock=FakeClock(),
        sleep=lambda _s: None,
    )
    assert calendar.checked == () and calendar.unchecked == ("2026-11",)
    assert calendar.dates == frozenset()


@pytest.mark.parametrize("status", [307, 301, 302, 403, 404, 429, 500, 503, 0])
def test_a_non_200_answer_is_unchecked_even_with_a_good_body(status: int) -> None:
    calendar = gc.fetch_calendar(
        [(2026, 11)], get=lambda _u: (status, GOOD), clock=FakeClock(), sleep=lambda _s: None
    )
    assert calendar.checked == () and calendar.unchecked == ("2026-11",)


def test_a_network_error_makes_the_month_unchecked_and_is_not_estimated() -> None:
    def boom(_url: str) -> tuple[int, bytes]:
        raise OSError("synthetic network error")

    calendar = gc.fetch_calendar(
        [(2026, 10), (2026, 11)], get=boom, clock=FakeClock(), sleep=lambda _s: None
    )
    assert calendar.checked == () and calendar.dates == frozenset()
    assert calendar.unchecked == ("2026-10", "2026-11")


# --- rate limit (fake clock; nothing really sleeps) ---------------------------------------------


def _months(count: int) -> list[tuple[int, int]]:
    return [(2025 + (6 + i) // 12, (6 + i) % 12 + 1) for i in range(count)]


def test_requests_are_newest_first_one_per_month_and_at_least_six_seconds_apart() -> None:
    months = _months(8)
    cal = FakeCalendar(weekdays(date(2025, 7, 1), date(2026, 2, 28)))
    clock = FakeClock()
    stamps: list[float] = []

    def get(url: str) -> tuple[int, bytes]:
        stamps.append(clock.now)
        return cal(url)

    result = gc.fetch_calendar(months, get=get, clock=clock, sleep=clock.sleep)
    asked = [u.rsplit("date=", 1)[1] for u in cal.urls]
    assert asked == [f"{y:04d}{m:02d}01" for y, m in sorted(months, reverse=True)]
    assert len(set(asked)) == len(asked) == 8  # no retry, no repeat
    assert all(b - a >= 6.0 for a, b in zip(stamps, stamps[1:], strict=False))
    assert len(clock.sleeps) == 7 and all(s <= 6.0 for s in clock.sleeps)
    assert result.checked == tuple(f"{y:04d}-{m:02d}" for y, m in months)
    assert result.unchecked == ()


def test_the_gap_after_a_failed_request_is_doubled_and_then_returns_to_six() -> None:
    months = _months(4)  # asked newest first: 2025-10, 2025-09, 2025-08, 2025-07
    cal = FakeCalendar(weekdays(date(2025, 7, 1), date(2025, 10, 31)), bad={"2025-09"})
    clock = FakeClock()
    stamps: list[float] = []

    def get(url: str) -> tuple[int, bytes]:
        stamps.append(clock.now)
        return cal(url)

    result = gc.fetch_calendar(months, get=get, clock=clock, sleep=clock.sleep)
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    assert gaps[0] >= 6.0  # after the good 2025-10
    assert gaps[1] >= 12.0  # after the failed 2025-09
    assert 6.0 <= gaps[2] < 12.0  # after the good 2025-08: back to the base gap
    assert result.unchecked == ("2025-09",)


@pytest.mark.parametrize("status", [403, 429, 503])
def test_a_block_status_ends_the_fetching_and_the_rest_is_unchecked(status: int) -> None:
    months = _months(6)
    cal = FakeCalendar(weekdays(date(2025, 7, 1), date(2025, 12, 31)), statuses={"2025-11": status})
    clock = FakeClock()
    result = gc.fetch_calendar(months, get=cal, clock=clock, sleep=clock.sleep)
    assert len(cal.urls) == 2  # 2025-12 good, 2025-11 blocked, then nothing more is asked
    assert result.checked == ("2025-12",)
    assert result.unchecked == ("2025-07", "2025-08", "2025-09", "2025-10", "2025-11")


def test_three_failures_in_a_row_end_the_fetching_two_do_not() -> None:
    months = _months(8)
    cal = FakeCalendar(
        weekdays(date(2025, 7, 1), date(2026, 2, 28)), bad={"2026-02", "2026-01", "2025-12"}
    )
    result = gc.fetch_calendar(months, get=cal, clock=FakeClock(), sleep=lambda _s: None)
    assert len(cal.urls) == 3
    assert result.checked == () and len(result.unchecked) == 8
    cal2 = FakeCalendar(weekdays(date(2025, 7, 1), date(2026, 2, 28)), bad={"2026-02", "2026-01"})
    result2 = gc.fetch_calendar(months, get=cal2, clock=FakeClock(), sleep=lambda _s: None)
    assert len(cal2.urls) == 8
    assert result2.unchecked == ("2026-01", "2026-02")


def test_the_urls_asked_are_the_fixed_source_only() -> None:
    cal = FakeCalendar(weekdays(date(2026, 10, 1), date(2026, 11, 30)))
    gc.fetch_calendar([(2026, 10), (2026, 11)], get=cal, clock=FakeClock(), sleep=lambda _s: None)
    assert cal.urls == [
        "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date=20261101",
        "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date=20261001",
    ]


# --- the real GET (a fake opener: nothing connects) ---------------------------------------------


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = BytesIO(body)

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_a: object) -> None:
        return None


class _Opener:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def open(self, request: urllib.request.Request, timeout: float) -> _Response:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return _Response(bytes(str(self.outcome), "utf-8"))


def test_the_request_carries_only_a_generic_user_agent_and_the_fixed_url() -> None:
    opener = _Opener("x")
    url = gc.CALENDAR_URL_TEMPLATE.format(year=2026, month=11)
    assert gc.http_get(url, opener=opener) == (200, b"x")
    (request,) = opener.requests
    assert request.get_method() == "GET" and request.data is None
    assert request.full_url == url
    assert request.header_items() == [("User-agent", gc.USER_AGENT)]
    assert gc.USER_AGENT == "gap-check/1.0 (read-only, low rate)"
    assert opener.timeouts == [gc.REQUEST_TIMEOUT_SECONDS]
    parsed = urllib.parse.urlsplit(request.full_url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https", "www.twse.com.tw", "/rwd/zh/TAIEX/MI_5MINS_HIST"
    )  # fmt: skip
    assert parsed.query == "response=json&date=20261101"


def test_the_opener_follows_no_redirect_and_has_no_cookie_handler() -> None:
    director = gc.build_opener()
    names = {type(h).__name__ for h in director.handlers}
    assert "HTTPCookieProcessor" not in names and "_NoRedirect" in names
    assert "HTTPRedirectHandler" not in names  # replaced by the no-redirect subclass
    handler = gc._NoRedirect()
    request = urllib.request.Request("https://www.twse.com.tw/x")
    assert (
        handler.redirect_request(request, None, 307, "Temporary", {}, "https://elsewhere/") is None
    )


def test_a_307_answer_comes_back_as_a_status_not_a_followed_redirect() -> None:
    error = urllib.error.HTTPError(
        "https://www.twse.com.tw/x",
        307,
        "Temporary Redirect",
        Message(),
        BytesIO(SECURITY_PAGE),
    )
    status, body = gc.http_get("https://www.twse.com.tw/x", opener=_Opener(error))
    assert (status, body) == (307, SECURITY_PAGE)


def test_a_network_error_of_the_opener_is_an_oserror() -> None:
    with pytest.raises(OSError):
        gc.http_get("https://www.twse.com.tw/x", opener=_Opener(urllib.error.URLError("down")))


# --- result codes (point 5 (f)) and the comparison (point 5 (d)) --------------------------------


def _calendar(official: list[date], *, bad: set[str] | None = None) -> Any:
    start, end = period_of(date(2026, 11, 19))
    months = gc.months_between(start, end)
    return gc.fetch_calendar(
        months,
        get=FakeCalendar(official, bad=bad or ()),
        clock=FakeClock(),
        sleep=lambda _s: None,
    )


def _world_days() -> tuple[date, date, list[date]]:
    start, end = period_of(date(2026, 11, 19))
    return start, end, weekdays(start, end, holidays=[date(2026, 10, 10)])


def test_every_month_unobtainable_is_calendar_unavailable() -> None:
    start, end, official = _world_days()
    cache = [d for d in official if d != official[40]]  # even with a gap in the cache
    calendar = _calendar(
        official, bad={f"{y:04d}-{m:02d}" for y, m in gc.months_between(start, end)}
    )
    found = gc.compare(cache, calendar, start=start, end=end)
    assert found.result == "calendar_unavailable" and found.checked == ()
    assert found.official_not_in_cache == () and found.cache_not_in_official == ()


def test_a_gap_with_unchecked_months_is_gaps_found() -> None:
    start, end, official = _world_days()
    gap = official[-30]
    cache = [d for d in official if d != gap]
    calendar = _calendar(official, bad={"2025-08", "2025-09"})
    found = gc.compare(cache, calendar, start=start, end=end)
    assert found.unchecked == ("2025-08", "2025-09")
    assert found.official_not_in_cache == (gap,)
    assert found.result == "gaps_found"


def test_only_a_cache_day_the_official_calendar_lacks_is_gaps_found() -> None:
    start, end, official = _world_days()
    extra = date(2026, 10, 10)  # a synthetic holiday the cache wrongly holds
    cache = [*official, extra]
    found = gc.compare(cache, _calendar(official), start=start, end=end)
    assert found.cache_not_in_official == (extra,)
    assert found.official_not_in_cache == () and found.not_covered == ()
    assert found.unchecked == ()
    assert found.result == "gaps_found"


def test_a_cache_day_in_an_unchecked_month_is_not_judged() -> None:
    start, end, official = _world_days()
    extra = date(2026, 10, 10)
    found = gc.compare(
        [*official, extra], _calendar(official, bad={"2026-10"}), start=start, end=end
    )
    assert found.cache_not_in_official == ()
    assert found.result == "no_gaps_in_checked_months"


def test_only_days_the_cache_does_not_cover_are_not_gaps() -> None:
    start, end, official = _world_days()
    lo, hi = official[30], official[-20]
    cache = [d for d in official if lo <= d <= hi]
    found = gc.compare(cache, _calendar(official), start=start, end=end)
    assert (found.cache_start, found.cache_end) == (lo, hi)
    assert found.not_covered == tuple(d for d in official if d < lo or d > hi)
    assert len(found.not_covered) == 30 + 19
    assert found.official_not_in_cache == () and found.cache_not_in_official == ()
    assert found.result == "no_gaps_in_checked_months" and found.result != "gaps_found"


def test_unchecked_months_without_a_gap_are_no_gaps_in_checked_months() -> None:
    start, end, official = _world_days()
    found = gc.compare(
        official, _calendar(official, bad={"2026-03", "2025-12"}), start=start, end=end
    )
    assert found.unchecked == ("2025-12", "2026-03")
    assert found.result == "no_gaps_in_checked_months"


def test_all_checked_no_gap_and_full_coverage_is_no_gaps_found() -> None:
    start, end, official = _world_days()
    found = gc.compare(official, _calendar(official), start=start, end=end)
    assert found.unchecked == () and found.not_covered == ()
    assert found.official_not_in_cache == () and found.cache_not_in_official == ()
    assert found.result == "no_gaps_found"
    assert len(found.checked) == 17


def test_an_empty_cache_period_lists_every_official_day_as_not_covered() -> None:
    start, end, official = _world_days()
    found = gc.compare([date(2020, 1, 2)], _calendar(official), start=start, end=end)
    assert found.cache_start is None and found.cache_end is None
    assert found.not_covered == tuple(official)
    assert found.result == "no_gaps_in_checked_months"


def test_cache_days_outside_the_period_do_not_widen_the_coverage_or_count() -> None:
    start, end, official = _world_days()
    outside = [start - timedelta(days=30), date(2026, 11, 19), date(2026, 11, 20)]
    found = gc.compare([*official, *outside], _calendar(official), start=start, end=end)
    assert (found.cache_start, found.cache_end) == (official[0], official[-1])
    assert found.result == "no_gaps_found"


@pytest.mark.parametrize(
    ("checked", "unchecked", "not_covered", "only_official", "only_cache", "expected"),
    [
        ((), ("a",), (1,), (1,), (1,), "calendar_unavailable"),  # first condition wins
        (("a",), ("b",), (), (1,), (), "gaps_found"),
        (("a",), (), (1,), (), (1,), "gaps_found"),
        (("a",), (), (1,), (), (), "no_gaps_in_checked_months"),
        (("a",), ("b",), (), (), (), "no_gaps_in_checked_months"),
        (("a",), (), (), (), (), "no_gaps_found"),
    ],
)
def test_decide_takes_the_first_condition_that_holds(
    checked: Any,
    unchecked: Any,
    not_covered: Any,
    only_official: Any,
    only_cache: Any,
    expected: str,
) -> None:
    assert (
        gc.decide(
            checked=checked,
            unchecked=unchecked,
            not_covered=not_covered,
            official_not_in_cache=only_official,
            cache_not_in_official=only_cache,
        )
        == expected
    )


def test_the_four_codes_are_exactly_the_set_of_the_ruling() -> None:
    assert gc.RESULT_CODES == (
        "calendar_unavailable",
        "gaps_found",
        "no_gaps_found",
        "no_gaps_in_checked_months",
    )


def test_index_values_of_the_calendar_never_enter_the_comparison() -> None:
    start, end, official = _world_days()
    found = gc.compare(official, _calendar(official), start=start, end=end)
    assert POISON_INDEX not in repr(found)


# --- ASCII digits only (qa N-6) -----------------------------------------------------------------

#: Code points of the digit zero in three other scripts: fullwidth, Arabic-Indic, Devanagari.
ZEROS = (0xFF10, 0x0660, 0x0966)


def _other_digits(text: str, zero: int) -> str:
    """``text`` with every ASCII digit written in another script (``str.isdigit`` is still true)."""
    return "".join(chr(zero + int(c)) if c in "0123456789" else c for c in text)


@pytest.mark.parametrize("zero", ZEROS)
def test_a_value_written_in_other_digits_is_on_no_whitelist_shape(zero: int) -> None:
    def other(text: str) -> str:
        return _other_digits(text, zero)

    assert other("2026-11-02").isdigit() is False and other("20261102").isdigit()
    for line in (
        f"period_start={other('2026-11-02')}",
        f"period_end={other('2026-11-02')}",
        f"cache_range_start={other('2026-11-02')}",
        f"cache_range_end={other('2026-11-02')}",
        f"cache_not_covered_dates={other('2026-11-02')}",
        f"official_not_in_cache_dates=2026-11-02,{other('2026-11-03')}",
        f"cache_not_in_official_dates={other('2026-11-02')}",
        f"months_checked={other('2026-11')}",
        f"months_unchecked=2026-11,{other('2026-10')}",
        f"cache_not_covered_count={other('19')}",
        f"official_not_in_cache_count={other('19')}",
        f"cache_not_in_official_count={other('19')}",
    ):
        assert not gc.on_whitelist(line), line
        assert not gc.is_screen_line(line)
    assert gc.on_whitelist("period_start=2026-11-02")  # the ASCII form still passes


def test_the_same_lines_in_ascii_digits_pass_each_shape() -> None:
    for line in (
        "period_start=2025-07-07",
        "months_checked=2025-07,2025-08",
        "cache_not_covered_count=19",
        "official_not_in_cache_dates=2026-04-15,2026-04-16",
        "cache_range_end=none",
    ):
        assert gc.on_whitelist(line), line


@pytest.mark.parametrize("zero", ZEROS)
def test_a_roc_date_in_other_digits_is_unreadable(zero: int) -> None:
    cell = _other_digits("115/11/02", zero)
    assert gc.roc_to_date(cell) is None
    assert gc.roc_to_date("115/11/02") == date(2026, 11, 2)
    body = ('{"stat": "OK", "fields": ["日期"], "data": [["' + cell + '"]]}').encode()
    assert gc.parse_month(body, 2026, 11) is None


@pytest.mark.parametrize("zero", ZEROS)
def test_the_run_folder_pattern_takes_ascii_digits_only(zero: int) -> None:
    assert gc.RUN_FOLDER_PATTERN.fullmatch("20261119-100000")
    assert not gc.RUN_FOLDER_PATTERN.fullmatch(_other_digits("20261119-100000", zero))


def test_render_refuses_a_non_ascii_line_even_if_the_whitelist_were_to_pass_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start, end, official = _world_days()
    found = gc.compare(official, _calendar(official), start=start, end=end)
    lines = gc.render(found, git_head="a" * 40, script_sha256_lf="b" * 64)
    assert all(line.isascii() for line in lines)
    monkeypatch.setattr(gc, "on_whitelist", lambda _line: True)  # only the ASCII check is left
    with pytest.raises(RuntimeError):
        gc.render(found, git_head="é" * 40, script_sha256_lf="b" * 64)


def test_no_pattern_of_the_script_uses_the_shorthand_digit_class() -> None:
    import ast

    from tests.gap_check_world import SCRIPT_PATH

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "\\d" in node.value
    ]
    assert offenders == []
    # The compiled patterns agree: none of them matches a digit of another script.
    patterns = [p for _name, p in gc.WHITELIST] + [gc._ROC_DATE, gc.RUN_FOLDER_PATTERN]
    assert not any("\\d" in p.pattern for p in patterns)


def test_the_trade_date_check_of_the_copy_reads_ascii_digits_only() -> None:
    import ast

    from tests.gap_check_world import SCRIPT_PATH

    func = next(
        n
        for n in ast.walk(ast.parse(SCRIPT_PATH.read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "read_trade_dates"
    )
    patterns = [
        n.value
        for n in ast.walk(func)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "{4}" in n.value
    ]
    assert patterns == ["[0-9]{4}-[0-9]{2}-[0-9]{2}"]
