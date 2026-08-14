"""The data-age check behind the 資料過舊 notice: real trading days, not a buffer.

C4 (``work/機會清單.md``): the front end had been standing in a "more than 10
calendar days" buffer because no trading calendar reached it, and the threshold
was flagged as an unsourced estimate. These tests pin the replacement --
``trading_days_behind``, counted from sessions the cache actually observed --
and, above all, its **direction of failure**: an unmodelled closure (農曆年、
颱風假、an ad-hoc suspension) must never be counted as a session the series is
missing, because that is precisely the false alarm B1 of
``work/reviews/risk-fix-review.md`` was raised about.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.data.cache import PriceBarCache
from app.data.calendar import TradingCalendar
from app.data.interface import Market
from app.services.market import (
    LoadedBars,
    load_bars,
    trading_days_behind_market,
)
from tests.api_helpers import FakePriceService, recent_bars, trending_closes
from tests.conftest import ApiHarness

# A Monday, so the weekday-fallback trap is exercised on real weekdays.
MONDAY = date(2026, 8, 3)


def _cache(tmp_path: Path) -> PriceBarCache:
    return PriceBarCache(db_path=tmp_path / "bars.db")


def _seed(cache: PriceBarCache, *, symbol: str, market: Market, days: list[date]) -> None:
    """Put one bar per date into the cache, the way a provider fetch would."""
    for day in days:
        cache.put(recent_bars([100.0], symbol=symbol, market=market, end=day), source="fake")


# --------------------------------------------------------------------------
# TradingCalendar.observed_days_after -- observation only, never the fallback
# --------------------------------------------------------------------------


def test_observed_days_after_counts_only_days_the_market_was_seen_to_trade() -> None:
    calendar = TradingCalendar([MONDAY, MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)])
    assert calendar.observed_days_after(MONDAY) == 2


def test_observed_days_after_is_zero_at_the_latest_observed_day() -> None:
    calendar = TradingCalendar([MONDAY, MONDAY + timedelta(days=1)])
    assert calendar.observed_days_after(MONDAY + timedelta(days=1)) == 0


def test_observed_days_after_never_invents_a_session_from_the_weekday_rule() -> None:
    """The B1 regression, at the primitive: unobserved weekdays are not sessions.

    ``is_trading_day`` answers a day outside the observed range with Mon-Fri,
    which is what a forward-looking 預定執行日 needs and what a staleness gap
    must never use -- ``trading_days_between`` would count all four unobserved
    weekdays here as missed sessions.
    """
    calendar = TradingCalendar([MONDAY])
    assert calendar.is_trading_day(MONDAY + timedelta(days=1)) is True
    assert calendar.trading_days_between(MONDAY, MONDAY + timedelta(days=4)) == 4
    assert calendar.observed_days_after(MONDAY) == 0


def test_observed_days_after_on_an_empty_calendar_is_zero() -> None:
    assert TradingCalendar(()).observed_days_after(MONDAY) == 0


# --------------------------------------------------------------------------
# PriceBarCache.market_trading_days -- the observed calendar itself
# --------------------------------------------------------------------------


def test_market_trading_days_is_the_union_over_every_symbol(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY, MONDAY + timedelta(days=1)])
    _seed(cache, symbol="^TWII", market="TW", days=[MONDAY + timedelta(days=2)])

    assert cache.market_trading_days("TW", MONDAY, MONDAY + timedelta(days=7)) == frozenset(
        {MONDAY, MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)}
    )


def test_market_trading_days_does_not_mix_the_two_markets(tmp_path: Path) -> None:
    """TW and US keep different calendars; one must never vouch for the other."""
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY])
    _seed(cache, symbol="AAPL", market="US", days=[MONDAY + timedelta(days=1)])

    assert cache.market_trading_days("TW", MONDAY, MONDAY + timedelta(days=7)) == frozenset(
        {MONDAY}
    )


def test_market_trading_days_respects_the_requested_window(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY, MONDAY + timedelta(days=5)])

    assert cache.market_trading_days("TW", MONDAY, MONDAY + timedelta(days=1)) == frozenset(
        {MONDAY}
    )


def test_market_trading_days_is_empty_when_nothing_was_ever_observed(tmp_path: Path) -> None:
    assert _cache(tmp_path).market_trading_days("TW", MONDAY, MONDAY + timedelta(days=7)) == (
        frozenset()
    )


# --------------------------------------------------------------------------
# trading_days_behind_market -- the judgement, and the direction it fails in
# --------------------------------------------------------------------------


def test_no_calendar_source_is_unknown_rather_than_fresh() -> None:
    assert (
        trading_days_behind_market(
            None, market="TW", last_bar_date=MONDAY, today=MONDAY + timedelta(days=7)
        )
        is None
    )


def test_a_calendar_that_observed_nothing_is_unknown(tmp_path: Path) -> None:
    """Empty cache: "we cannot judge", never "the data is current"."""
    assert (
        trading_days_behind_market(
            _cache(tmp_path),
            market="TW",
            last_bar_date=MONDAY,
            today=MONDAY + timedelta(days=7),
        )
        is None
    )


def test_no_last_bar_date_is_unknown(tmp_path: Path) -> None:
    assert (
        trading_days_behind_market(
            _cache(tmp_path), market="TW", last_bar_date=None, today=MONDAY
        )
        is None
    )


def test_up_to_date_series_is_zero_sessions_behind(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY, MONDAY + timedelta(days=1)])

    assert (
        trading_days_behind_market(
            cache,
            market="TW",
            last_bar_date=MONDAY + timedelta(days=1),
            today=MONDAY + timedelta(days=1),
        )
        == 0
    )


def test_one_missed_session_is_one_the_threshold_the_risk_review_asked_for(
    tmp_path: Path,
) -> None:
    """門檻降回 1 交易日: a single session the series is missing is reportable."""
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY])
    _seed(cache, symbol="2317", market="TW", days=[MONDAY, MONDAY + timedelta(days=1)])

    assert (
        trading_days_behind_market(
            cache, market="TW", last_bar_date=MONDAY, today=MONDAY + timedelta(days=1)
        )
        == 1
    )


def test_a_multi_session_outage_counts_every_missed_session(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY])
    _seed(
        cache,
        symbol="2317",
        market="TW",
        days=[MONDAY + timedelta(days=offset) for offset in range(4)],
    )

    assert (
        trading_days_behind_market(
            cache, market="TW", last_bar_date=MONDAY, today=MONDAY + timedelta(days=3)
        )
        == 3
    )


def test_an_unmodelled_closure_does_not_fire_a_false_stale_alarm(tmp_path: Path) -> None:
    """The B1 case, end to end: 農曆年 / 颱風假 / any ad-hoc suspension.

    Nine calendar days pass with the market shut. No series produced a bar on
    any of them, so no session is counted and the gap stays 0 -- no holiday
    table, no yearly upkeep, and no alarm on the first day back.
    """
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY])
    _seed(cache, symbol="2317", market="TW", days=[MONDAY])

    assert (
        trading_days_behind_market(
            cache, market="TW", last_bar_date=MONDAY, today=MONDAY + timedelta(days=9)
        )
        == 0
    )


def test_a_closure_followed_by_a_reopened_session_counts_only_the_session(
    tmp_path: Path,
) -> None:
    """Trading resumes after a long closure: exactly one session was missed."""
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY])
    _seed(cache, symbol="2317", market="TW", days=[MONDAY, MONDAY + timedelta(days=9)])

    assert (
        trading_days_behind_market(
            cache, market="TW", last_bar_date=MONDAY, today=MONDAY + timedelta(days=9)
        )
        == 1
    )


def test_a_market_wide_outage_reads_as_unknown_gap_not_as_a_wrong_number(
    tmp_path: Path,
) -> None:
    """When the whole data layer is stale the calendar stops advancing too.

    The documented blind spot: this check reports 0 and the *source*-side
    disclosure (``status`` / ``staleness_minutes`` / ``is_within_ttl``) is what
    carries that case, exactly as R4 split the two.
    """
    cache = _cache(tmp_path)
    _seed(cache, symbol="2330", market="TW", days=[MONDAY])
    _seed(cache, symbol="2317", market="TW", days=[MONDAY])

    assert (
        trading_days_behind_market(
            cache, market="TW", last_bar_date=MONDAY, today=MONDAY + timedelta(days=30)
        )
        == 0
    )


# --------------------------------------------------------------------------
# load_bars / the data envelope
# --------------------------------------------------------------------------


def test_loaded_bars_meta_publishes_the_gap() -> None:
    assert LoadedBars(trading_days_behind=2).meta()["trading_days_behind"] == 2


def test_load_bars_without_a_calendar_source_reports_unknown() -> None:
    service = FakePriceService()
    service.seed("2330", recent_bars(trending_closes(5)))
    today = date.today()

    loaded = load_bars(
        {"TW": service},
        symbol="2330",
        market="TW",
        start=today - timedelta(days=30),
        end=today,
    )

    assert loaded.trading_days_behind is None
    assert loaded.meta()["trading_days_behind"] is None


def test_load_bars_reports_the_gap_when_a_calendar_source_is_given(tmp_path: Path) -> None:
    today = date.today()
    service = FakePriceService()
    # The symbol's own series stops two days before today...
    service.seed("2330", recent_bars(trending_closes(5), end=today - timedelta(days=2)))
    # ...while the market went on trading on both of them.
    cache = _cache(tmp_path)
    _seed(
        cache,
        symbol="2317",
        market="TW",
        days=[today - timedelta(days=2), today - timedelta(days=1), today],
    )

    loaded = load_bars(
        {"TW": service},
        symbol="2330",
        market="TW",
        start=today - timedelta(days=30),
        end=today,
        calendar_source=cache,
    )

    assert loaded.trading_days_behind == 2


def test_an_empty_result_leaves_the_gap_unknown(tmp_path: Path) -> None:
    """No bars means no ``last_bar_date`` to measure from -- not a gap of 0."""
    today = date.today()
    loaded = load_bars(
        {"TW": FakePriceService()},
        symbol="2330",
        market="TW",
        start=today - timedelta(days=30),
        end=today,
        calendar_source=_cache(tmp_path),
    )

    assert loaded.trading_days_behind is None


# --------------------------------------------------------------------------
# GET /api/advice -- the endpoint that publishes the notice
# --------------------------------------------------------------------------


def test_advice_reports_an_unknown_gap_when_the_calendar_has_seen_nothing(
    api_harness: ApiHarness,
) -> None:
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200)))

    body = api_harness.client.get("/api/advice/2330").json()

    assert body["data"]["trading_days_behind"] is None


def test_advice_reports_the_sessions_the_series_is_behind(api_harness: ApiHarness) -> None:
    today = date.today()
    api_harness.price_service.seed(
        "2330", recent_bars(trending_closes(200), end=today - timedelta(days=1))
    )
    # Another symbol traded today; 2330's series stops yesterday.
    _seed(api_harness.bar_cache, symbol="2317", market="TW", days=[today - timedelta(days=1)])
    _seed(api_harness.bar_cache, symbol="2317", market="TW", days=[today])

    body = api_harness.client.get("/api/advice/2330").json()

    assert body["data"]["last_bar_date"] == (today - timedelta(days=1)).isoformat()
    assert body["data"]["trading_days_behind"] == 1
