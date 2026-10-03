"""``data_refresh`` on the close-of-session cron (ADR-0010 D-4, revised 2026-10-03).

* T-1: with no override the job's trigger is one ``OrTrigger`` of exactly
  five weekday ``CronTrigger``s, each with an explicit zone, and only this job
  carries the 15-minute misfire grace; ``SCHEDULER_DATA_INTERVAL_MINUTES``
  restores the interval when valid and is ignored (with a warning) when not.
* T-2: the fire times, enumerated as a pure function of the trigger over
  2026-03-02..2026-11-10 -- daylight saving, weekends, the sector batches'
  quiet windows and the K-8 margins read from ``app.data.freshness``.
* T-3: the real ``MarketDataService`` (``cache_first``) on a fake clock with
  counting providers: the schedule never makes a source be asked more often
  than ADR-0009's ``judge()`` and cooldowns allow.
* T-4: exactly one ``data refresh run:`` line per run, ``startup`` first.

Nothing starts the scheduler loop and nothing may open a socket.
"""

from __future__ import annotations

import logging
import re
import socket
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app import scheduler as scheduler_module
from app.data.cache import PriceBarCache
from app.data.freshness import TW_POLICY, US_POLICY
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.service import MarketDataService
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from app.settings.store import SettingsStore

TAIPEI = ZoneInfo("Asia/Taipei")
NEW_YORK = ZoneInfo("America/New_York")

#: §1 of the tech-architect brief, verbatim: (zone, hour field, minute field).
EXPECTED_CRONS = {
    ("Asia/Taipei", "15", "10"),
    ("Asia/Taipei", "16", "30"),
    ("Asia/Taipei", "18", "30"),
    ("America/New_York", "18", "30"),
    ("America/New_York", "19-23", "0,30"),
}

#: K-8 margins over the freshness policy (brief §5).
TW_FIRST_MARGIN = timedelta(minutes=5)
TW_GAP_MARGIN = timedelta(minutes=20)
US_FIRST_MARGIN = timedelta(minutes=15)

#: §2: a data_refresh run may start up to the misfire grace late and is
#: budgeted 15 minutes; the sector batches' quiet window opens 5 minutes
#: before the capture and closes 15 minutes after the board refresh.
RUN_SPAN = timedelta(seconds=scheduler_module.DATA_REFRESH_MISFIRE_GRACE_SECONDS) + timedelta(
    minutes=15
)
QUIET_BEFORE_CAPTURE = timedelta(minutes=5)
QUIET_AFTER_REFRESH = timedelta(minutes=15)

RUN_LINE = re.compile(
    r"^data refresh run: trigger=(?P<trigger>startup|cron|interval) "
    r"taipei=(?P<taipei>\S+) new_york=(?P<new_york>\S+) "
    r"with_bars=(?P<with_bars>\d+) duration_ms=(?P<duration_ms>\d+) "
    r"outcome=(?P<outcome>ok|error)$"
)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsStore:
    store = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: store)
    monkeypatch.delenv(scheduler_module.DATA_INTERVAL_ENV, raising=False)
    return store


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(self: socket.socket, *args: object) -> None:
        raise AssertionError("data_refresh tests must not open a socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def _fields(trigger: CronTrigger) -> dict[str, str]:
    return {field.name: str(field) for field in trigger.fields}


def _crons(trigger: OrTrigger) -> list[CronTrigger]:
    crons = list(trigger.triggers)
    assert all(isinstance(cron, CronTrigger) for cron in crons)
    return crons


def _run_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith("data refresh run:")]


# --- T-1: structure -----------------------------------------------------------


def test_the_default_schedule_is_five_weekday_crons_with_explicit_zones(
    settings: SettingsStore,
) -> None:
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    job = engine.get_job("data_refresh")
    assert isinstance(job.trigger, OrTrigger)
    crons = _crons(job.trigger)
    assert len(crons) == 5
    seen = set()
    for cron in crons:
        fields = _fields(cron)
        assert fields["day_of_week"] == "mon-fri"
        seen.add((str(cron.timezone), fields["hour"], fields["minute"]))
    assert seen == EXPECTED_CRONS
    assert job.max_instances == 1 and job.coalesce is True


def test_only_data_refresh_carries_the_misfire_grace(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    assert engine.get_job("data_refresh").misfire_grace_time == 900
    for job in engine.get_jobs():
        if job.id != "data_refresh":
            # Pending jobs only get the scheduler default once it starts.
            assert getattr(job, "misfire_grace_time", None) != 900


def test_a_valid_interval_env_restores_the_legacy_interval(
    settings: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(scheduler_module.DATA_INTERVAL_ENV, "1440")
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    trigger = engine.get_job("data_refresh").trigger
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(minutes=1440)


@pytest.mark.parametrize("raw", ["", "   "])
def test_a_blank_interval_env_keeps_the_cron_quietly(
    settings: SettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw: str,
) -> None:
    monkeypatch.setenv(scheduler_module.DATA_INTERVAL_ENV, raw)
    with caplog.at_level(logging.WARNING, logger="scheduler"):
        engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    assert isinstance(engine.get_job("data_refresh").trigger, OrTrigger)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("raw", ["daily", "0", "-5", "1.5"])
def test_a_nonsense_interval_env_keeps_the_cron_with_a_warning(
    settings: SettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw: str,
) -> None:
    monkeypatch.setenv(scheduler_module.DATA_INTERVAL_ENV, raw)
    with caplog.at_level(logging.WARNING, logger="scheduler"):
        engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    assert isinstance(engine.get_job("data_refresh").trigger, OrTrigger)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert scheduler_module.DATA_INTERVAL_ENV in warnings[0].getMessage()


def test_the_registration_line_names_the_mode(
    settings: SettingsStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="scheduler"):
        scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
        monkeypatch.setenv(scheduler_module.DATA_INTERVAL_ENV, "30")
        scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    lines = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("scheduler jobs registered")
    ]
    assert len(lines) == 2
    assert "15:10,16:30,18:30 (Asia/Taipei)" in lines[0]
    assert "18:30 then hours 19-23 at minutes 0,30 (America/New_York)" in lines[0]
    assert "legacy interval 30 min" in lines[1]


# --- T-2: fire times as a pure function of the trigger ------------------------

WINDOW_START = datetime(2026, 3, 2, tzinfo=TAIPEI)
WINDOW_END = datetime(2026, 11, 10, tzinfo=TAIPEI)


def _fire_times(trigger: OrTrigger | CronTrigger) -> list[datetime]:
    """Every fire time in the window, without starting a scheduler."""
    fires: list[datetime] = []
    previous: datetime | None = None
    now = WINDOW_START
    while True:
        fire = trigger.get_next_fire_time(previous, now)
        if fire is None or fire >= WINDOW_END:
            return fires
        fires.append(fire)
        previous = now = fire


@pytest.fixture(scope="module")
def cron_trigger() -> OrTrigger:
    return scheduler_module.data_refresh_cron_trigger()


def _by_zone(trigger: OrTrigger, zone: str) -> list[datetime]:
    return sorted(
        fire for cron in _crons(trigger) if str(cron.timezone) == zone for fire in _fire_times(cron)
    )


def test_the_combined_trigger_fires_at_exactly_the_union_of_its_parts(
    cron_trigger: OrTrigger,
) -> None:
    union = sorted(fire for cron in _crons(cron_trigger) for fire in _fire_times(cron))
    combined = _fire_times(cron_trigger)
    assert combined == union
    assert len(combined) > 2000  # ~7 months of weekdays at 14 points a day


def test_the_us_close_point_follows_new_york_daylight_saving(cron_trigger: OrTrigger) -> None:
    first_us = {
        fire.astimezone(UTC)
        for fire in _by_zone(cron_trigger, "America/New_York")
        if fire.astimezone(NEW_YORK).time() == scheduler_module.DATA_REFRESH_US_FIRST
    }
    # EST (UTC-5) before 2026-03-08, EDT (UTC-4) until 2026-11-01, EST again.
    assert datetime(2026, 3, 6, 23, 30, tzinfo=UTC) in first_us
    assert datetime(2026, 3, 9, 22, 30, tzinfo=UTC) in first_us
    assert datetime(2026, 10, 30, 22, 30, tzinfo=UTC) in first_us
    assert datetime(2026, 11, 2, 23, 30, tzinfo=UTC) in first_us


def test_no_point_fires_on_its_own_exchange_weekend(cron_trigger: OrTrigger) -> None:
    taipei = _by_zone(cron_trigger, "Asia/Taipei")
    new_york = _by_zone(cron_trigger, "America/New_York")
    assert taipei and new_york
    assert all(fire.astimezone(TAIPEI).weekday() < 5 for fire in taipei)
    assert all(fire.astimezone(NEW_YORK).weekday() < 5 for fire in new_york)


def _quiet_windows(day: date) -> list[tuple[datetime, datetime]]:
    """The sector batches' quiet windows on one Taipei weekday (brief §2)."""
    windows = []
    for hour in (int(h) for h in scheduler_module.SECTOR_JOBS_HOURS.split(",")):
        capture = datetime.combine(
            day, time(hour, scheduler_module.PIT_CAPTURE_MINUTE), tzinfo=TAIPEI
        )
        refresh = datetime.combine(
            day, time(hour, scheduler_module.SECTOR_REFRESH_MINUTE), tzinfo=TAIPEI
        )
        windows.append((capture - QUIET_BEFORE_CAPTURE, refresh + QUIET_AFTER_REFRESH))
    return windows


def test_no_run_reaches_into_a_sector_batch_window(cron_trigger: OrTrigger) -> None:
    for fire in _fire_times(cron_trigger):
        start = fire.astimezone(TAIPEI)
        end = start + RUN_SPAN
        for day in {start.date(), end.date()}:
            if day.weekday() >= 5:
                continue
            for opens, closes in _quiet_windows(day):
                assert end <= opens or start >= closes, (fire, opens, closes)


def test_k8_the_taipei_points_respect_the_tw_policy(cron_trigger: OrTrigger) -> None:
    per_day: dict[date, list[datetime]] = {}
    for fire in _by_zone(cron_trigger, "Asia/Taipei"):
        local = fire.astimezone(TAIPEI)
        per_day.setdefault(local.date(), []).append(local)
    assert per_day
    for day, fires in per_day.items():
        cutoff = datetime.combine(day, TW_POLICY.publish_cutoff, tzinfo=TAIPEI)
        assert fires[0] >= cutoff + TW_FIRST_MARGIN
        for earlier, later in zip(fires, fires[1:], strict=False):
            assert later - earlier >= TW_POLICY.recheck_cooldown + TW_GAP_MARGIN


def test_k8_the_new_york_points_respect_the_us_policy(cron_trigger: OrTrigger) -> None:
    per_day: dict[date, list[datetime]] = {}
    for fire in _by_zone(cron_trigger, "America/New_York"):
        local = fire.astimezone(NEW_YORK)
        per_day.setdefault(local.date(), []).append(local)
    assert per_day
    for day, fires in per_day.items():
        cutoff = datetime.combine(day, US_POLICY.publish_cutoff, tzinfo=NEW_YORK)
        assert fires[0] >= cutoff + US_FIRST_MARGIN


# --- T-3: the schedule against the real cooldowns -----------------------------


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class CountingProvider(MarketDataProvider):
    """A live source on the fake clock that publishes through ``last_day``.

    Each call is recorded at the clock's time and then advances the clock by
    ``latency``: a real fetch ends -- and is logged by the service -- a few
    seconds after the scheduled point, which is what the cooldowns see.
    """

    source_id = "counting"

    def __init__(
        self,
        clock: FakeClock,
        *,
        market: Market,
        last_day: date | None = None,
        fails: bool = False,
        latency: timedelta = timedelta(seconds=5),
    ) -> None:
        self._clock = clock
        self._market: Market = market
        self.last_day = last_day
        self.fails = fails
        self._latency = latency
        self.calls: list[datetime] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.calls.append(self._clock.now)
        self._clock.now += self._latency
        if self.fails or self.last_day is None:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=self._clock.now,
                source=self.source_id,
                reason="來源暫時無回應。",
            )
        first = max(start, self.last_day - timedelta(days=14))
        span = (min(end, self.last_day) - first).days + 1
        days = [first + timedelta(days=n) for n in range(span)]
        currency = "TWD" if self._market == "TW" else "USD"
        bars = [
            PriceBar(
                symbol=symbol,
                market=self._market,
                date=day,
                open=Decimal(100),
                high=Decimal(100),
                low=Decimal(100),
                close=Decimal(100),
                volume=1,
                currency=currency,
                as_of=self._clock.now,
                source=self.source_id,
            )
            for day in days
            if day.weekday() < 5
        ]
        return ProviderResult(
            bars=bars, status=DataStatus.FRESH, as_of=self._clock.now, source=self.source_id
        )


def _hold(store: PositionStore, symbol: str, market: Market) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market=market,
            quantity=Decimal(10),
            avg_cost=Decimal(100),
            currency="TWD" if market == "TW" else "USD",
            opened_at=date(2025, 1, 2),
            instrument_type="stock",
        )
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    clock: FakeClock,
    providers: dict[Market, list[CountingProvider]],
    holdings: list[tuple[str, Market]],
) -> scheduler_module.DataRefreshRun:
    cache = PriceBarCache(tmp_path / "cache.db")
    resolver = {
        market: MarketDataService(
            primary=chain[0], backups=chain[1:], cache=cache, clock=clock, cache_first=True
        )
        for market, chain in providers.items()
    }
    positions = PositionStore(db_path=tmp_path / "positions.db")
    for symbol, market in holdings:
        _hold(positions, symbol, market)
    monkeypatch.setattr(scheduler_module, "get_market_resolver", lambda: resolver)
    monkeypatch.setattr(scheduler_module, "get_position_store", lambda: positions)
    return scheduler_module.DataRefreshRun(scheduled="cron", clock=clock)


def _fires_between(start: datetime, end: datetime) -> Iterator[datetime]:
    trigger = scheduler_module.data_refresh_cron_trigger()
    previous: datetime | None = None
    now = start
    while True:
        fire = trigger.get_next_fire_time(previous, now)
        if fire is None or fire >= end:
            return
        yield fire
        previous = now = fire


def _at(day: date, hour: int, minute: int, zone: ZoneInfo = TAIPEI) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=zone)


def test_tw_a_session_not_yet_published_is_asked_again_only_after_the_cooldown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    today, yesterday = date(2026, 3, 4), date(2026, 3, 3)  # Wednesday, Tuesday
    clock = FakeClock(_at(yesterday, 18, 30))
    provider = CountingProvider(clock, market="TW", last_day=yesterday)
    run = _wire(monkeypatch, tmp_path, clock, {"TW": [provider]}, [("2330", "TW")])
    with caplog.at_level(logging.INFO):
        run()  # yesterday's 18:30 point: the cache now holds yesterday's close

        def calls_at(hour: int, minute: int) -> int:
            before = len(provider.calls)
            clock.now = _at(today, hour, minute)
            run()
            return len(provider.calls) - before

        # 15:10: today is expected now; the source still only has yesterday.
        assert calls_at(15, 10) == 1
        # 15:40 (e.g. a restart): inside the 1h cooldown of that answer.
        assert calls_at(15, 40) == 0
        # The close is published before 16:30, which is past the cooldown.
        provider.last_day = today
        assert calls_at(16, 30) == 1
        # 18:30: the cache holds today's session; nobody is asked.
        assert calls_at(18, 30) == 0
    for record in caplog.records:
        message = record.getMessage().lower()
        assert "http" not in message and "apikey" not in message


def test_tw_failing_sources_get_at_most_one_round_per_point_and_respect_the_cooldown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    start = _at(date(2026, 3, 2), 0, 0)  # Monday; crosses the US DST switch
    clock = FakeClock(start)
    primary = CountingProvider(clock, market="TW", fails=True)
    backup = CountingProvider(clock, market="TW", fails=True)
    run = _wire(monkeypatch, tmp_path, clock, {"TW": [primary, backup]}, [("2330", "TW")])
    per_day: dict[date, int] = {}
    for fire in _fires_between(start, start + timedelta(days=14)):
        clock.now = fire
        before = (len(primary.calls), len(backup.calls))
        run()
        rounds = len(primary.calls) - before[0]
        assert rounds <= 1 and len(backup.calls) - before[1] == rounds
        if rounds:
            day = fire.astimezone(TAIPEI).date()
            per_day[day] = per_day.get(day, 0) + 1
    assert primary.calls, "a failing source was never asked"
    for earlier, later in zip(primary.calls, primary.calls[1:], strict=False):
        assert later - earlier >= TW_POLICY.recheck_cooldown
    # Brief §3: 3 Taipei points + ~4 rounds in the US window, far under ADR-0009's 24.
    # The 7-per-day ceiling assumes fetches take time (CountingProvider latency
    # 5s): attempts are recorded after the fetch, so the US window's hourly
    # retries get pushed to every 1.5h. With zero latency the bound is 9, still
    # far below ADR-0009's accepted ceiling of 24.
    assert max(per_day.values()) <= 7


def test_us_each_series_is_asked_at_most_once_per_cooldown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Friday 2026-02-27, just before the first New York point: the series is
    # fetched on that Friday's close and the simulation runs two weeks on.
    start = _at(date(2026, 2, 27), 18, 0, NEW_YORK)
    clock = FakeClock(start)

    class Publishing(CountingProvider):
        """Publishes each NY session exactly at ``US_POLICY.publish_cutoff``."""

        def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
            self.last_day = US_POLICY.latest_completed_session(self._clock.now)
            return super().get_daily_bars(symbol, start, end)

    provider = Publishing(clock, market="US")
    run = _wire(monkeypatch, tmp_path, clock, {"US": [provider]}, [("AAPL", "US"), ("MSFT", "US")])
    for fire in _fires_between(start, start + timedelta(days=14)):
        clock.now = fire
        run()
    for symbol_offset in (0, 1):
        # Calls alternate AAPL, MSFT within a run (holdings are sorted).
        calls = provider.calls[symbol_offset::2]
        assert calls
        for earlier, later in zip(calls, calls[1:], strict=False):
            assert later - earlier >= US_POLICY.recheck_cooldown
    # The documented limit (ADR-0010 D-4 revision): the cooldown is counted from
    # the end of the previous fetch, so each weekday's fetch lands one point
    # later than the last, and a weekend resets it.
    first_week = [
        call.astimezone(NEW_YORK).strftime("%a %H:%M")
        for call in provider.calls[::2]
        if date(2026, 3, 2) <= call.astimezone(NEW_YORK).date() < date(2026, 3, 7)
    ]
    assert first_week == ["Mon 18:30", "Tue 19:00", "Wed 19:30", "Thu 20:00", "Fri 20:30"]
    second_monday = [
        call.astimezone(NEW_YORK).strftime("%a %H:%M")
        for call in provider.calls[::2]
        if call.astimezone(NEW_YORK).date() == date(2026, 3, 9)
    ]
    assert second_monday == ["Mon 18:30"]


# --- T-4: one log line per run ------------------------------------------------


def test_each_run_logs_exactly_one_line_startup_first(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    seen_today: list[date | None] = []

    def refresh(*, today: date | None = None) -> int:
        seen_today.append(today)
        return 3

    monkeypatch.setattr(scheduler_module, "refresh_market_data", refresh)
    clock = FakeClock(datetime(2026, 3, 6, 23, 30, tzinfo=UTC))  # NY Fri 18:30, Taipei Sat
    run = scheduler_module.DataRefreshRun(scheduled="cron", clock=clock)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        assert run() == 3
        assert len(_run_lines(caplog)) == 1
        clock.now += timedelta(minutes=30)
        assert run() == 3
    records = _run_lines(caplog)
    assert len(records) == 2
    first, second = (RUN_LINE.match(r.getMessage()) for r in records)
    assert first is not None and second is not None
    assert first["trigger"] == "startup" and second["trigger"] == "cron"
    assert first["taipei"] == "2026-03-07T07:30+08:00"
    assert first["new_york"] == "2026-03-06T18:30-05:00"
    assert first["with_bars"] == "3" and first["outcome"] == "ok"
    assert all(r.levelno == logging.INFO for r in records)
    # K-9: the Taipei date, never behind New York's.
    assert seen_today == [date(2026, 3, 7), date(2026, 3, 7)]


@pytest.mark.parametrize(("env", "later"), [(None, "cron"), ("30", "interval")])
def test_the_registered_job_logs_its_trigger(
    settings: SettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    env: str | None,
    later: str,
) -> None:
    if env is not None:
        monkeypatch.setenv(scheduler_module.DATA_INTERVAL_ENV, env)
    monkeypatch.setattr(scheduler_module, "refresh_market_data", lambda **_: 0)
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    job = engine.get_job("data_refresh")
    with caplog.at_level(logging.INFO, logger="scheduler"):
        job.func()
        job.func()
        job.func()
    matches = [RUN_LINE.match(r.getMessage()) for r in _run_lines(caplog)]
    assert all(match is not None for match in matches)
    triggers = [match["trigger"] for match in matches if match is not None]
    assert triggers == ["startup", later, later]


def test_a_failed_run_logs_error_then_reraises_and_stays_scheduled(
    settings: SettingsStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explode(*, today: date | None = None) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "refresh_market_data", explode)
    run = scheduler_module.DataRefreshRun(
        scheduled="cron", clock=FakeClock(datetime(2026, 3, 4, 7, 10, tzinfo=UTC))
    )
    with caplog.at_level(logging.INFO, logger="scheduler"), pytest.raises(RuntimeError):
        run()
    records = _run_lines(caplog)
    assert len(records) == 1 and records[0].levelno == logging.ERROR
    match = RUN_LINE.match(records[0].getMessage())
    assert match is not None and match["outcome"] == "error"

    caplog.clear()
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    with caplog.at_level(logging.INFO, logger="scheduler"):
        engine.get_job("data_refresh").func()  # _guarded: must not raise
    messages = [r.getMessage() for r in caplog.records]
    error_line = next(i for i, m in enumerate(messages) if m.startswith("data refresh run:"))
    guard_line = next(i for i, m in enumerate(messages) if "data_refresh failed" in m)
    assert error_line < guard_line
    assert "outcome=error" in messages[error_line]
    assert engine.get_job("data_refresh") is not None
    for message in messages:
        assert "http" not in message.lower() and "apikey" not in message.lower()
