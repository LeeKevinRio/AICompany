"""``app.data.diagnose``: the whole-book "which holdings have no data" table."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.data.cache import PriceBarCache
from app.data.diagnose import (
    VERDICT_NONE,
    VERDICT_OK,
    VERDICT_STALE,
    diagnose_positions,
    render_report,
)
from app.data.interface import DataStatus, PriceBar, ProviderResult
from app.positions.models import PositionInput
from app.positions.store import PositionStore


def _bar(symbol: str, day: date) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market="TW",
        date=day,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        volume=1000,
        currency="TWD",
        as_of=datetime.now(UTC),
        source="twse",
    )


def _hold(store: PositionStore, symbol: str) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(10),
            currency="TWD",
            instrument_type="stock",
        )
    )


class _Service:
    """A ladder stand-in: answers per symbol, records what it was asked."""

    def __init__(self, answers: dict[str, ProviderResult]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def get_daily_bars(self, symbol: str, market: str, start: date, end: date) -> ProviderResult:
        self.asked.append(symbol)
        return self.answers[symbol]

    def get_cached_bars(self, symbol: str, market: str, start: date, end: date) -> ProviderResult:
        # The probe only runs the live ladder (load_bars); a cache-only read
        # here is a test wiring mistake and should fail loudly.
        raise NotImplementedError("diagnose --probe never reads cache-only")


def _weekday(days_ago: int) -> date:
    day = date.today() - timedelta(days=days_ago)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def test_cache_only_diagnosis_separates_ok_stale_and_missing(tmp_path: Path) -> None:
    db = tmp_path / "desk.db"
    positions = PositionStore(db_path=db)
    cache = PriceBarCache(db_path=db)
    for symbol in ("2330", "6147", "9999"):
        _hold(positions, symbol)
    # 2330 has the last three sessions; 6147 stopped 20 days ago, so the cache
    # has observed >= 2 sessions it lacks -- stale by sessions, not by calendar.
    cache.put([_bar("2330", _weekday(d)) for d in (1, 2, 3)], source="twse")
    cache.put([_bar("6147", _weekday(20))], source="tpex")

    rows = diagnose_positions(positions=positions, cache=cache)

    by_symbol = {r.symbol: r for r in rows}
    assert by_symbol["2330"].verdict == VERDICT_OK
    assert by_symbol["2330"].sessions_behind == 0
    assert by_symbol["6147"].verdict == VERDICT_STALE
    assert (by_symbol["6147"].sessions_behind or 0) >= 2
    assert by_symbol["9999"].verdict == VERDICT_NONE
    assert by_symbol["9999"].cached_bars == 0
    assert by_symbol["6147"].cached_sources == ("tpex",)
    assert all(r.probe_status is None for r in rows), "no probe requested -> nothing asked live"


def test_probe_reports_the_ladder_reason_for_a_symbol_without_data(tmp_path: Path) -> None:
    db = tmp_path / "desk.db"
    positions = PositionStore(db_path=db)
    cache = PriceBarCache(db_path=db)
    _hold(positions, "2330")
    _hold(positions, "6147")
    now = datetime.now(UTC)
    # The real ladder writes through to the cache; the stand-in does not, so
    # seed the bar it will answer with (otherwise the calendar is empty and the
    # verdict is honestly 無法判定 rather than 正常).
    cache.put([_bar("2330", _weekday(1))], source="twse")
    service = _Service(
        {
            "2330": ProviderResult(
                bars=[_bar("2330", _weekday(1))],
                status=DataStatus.FRESH,
                as_of=now,
                source="twse",
                staleness_minutes=0,
            ),
            "6147": ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source="none",
                staleness_minutes=None,
                reason="TPEx 回應版面無法辨識",
            ),
        }
    )

    rows = diagnose_positions(
        positions=positions, cache=cache, resolver={"TW": service}, probe=True
    )

    by_symbol = {r.symbol: r for r in rows}
    assert service.asked == ["2330", "6147"]
    assert by_symbol["2330"].verdict == VERDICT_OK
    assert by_symbol["2330"].probe_bars == 1
    assert by_symbol["6147"].verdict == VERDICT_NONE
    assert by_symbol["6147"].probe_status == "unavailable"
    assert "TPEx 回應版面無法辨識" in (by_symbol["6147"].probe_reason or "")

    report = render_report(rows, probed=True)
    assert "| 6147 |" in report and "無資料" in report
    assert "1 檔有問題：6147（無資料）" in report


def test_a_holiday_gap_with_no_observed_sessions_is_not_flagged_stale(tmp_path: Path) -> None:
    """qa-reviewer 2026-09-19: a long exchange holiday must not flag the whole book.

    Every held series stops on the same day (the market was closed after it),
    so the cache observes no session after that bar: ``sessions_behind`` is 0
    and every series reads 正常, however many calendar days have passed.
    """
    db = tmp_path / "desk.db"
    positions = PositionStore(db_path=db)
    cache = PriceBarCache(db_path=db)
    _hold(positions, "2330")
    _hold(positions, "2317")
    last = _weekday(8)
    cache.put([_bar("2330", last)], source="twse")
    cache.put([_bar("2317", last)], source="twse")

    rows = diagnose_positions(positions=positions, cache=cache)

    # The cache observed the last bar's own session and nothing after it.
    assert all(r.sessions_behind == 0 for r in rows)
    assert all(r.verdict == VERDICT_OK for r in rows)


def test_clear_cooldown_lifts_an_active_cooldown_only_when_asked(tmp_path: Path) -> None:
    db = tmp_path / "desk.db"
    positions = PositionStore(db_path=db)
    cache = PriceBarCache(db_path=db)
    _hold(positions, "6147")
    cache.record_attempt("6147", "TW", at=datetime.now(UTC) - timedelta(minutes=10))

    untouched = diagnose_positions(positions=positions, cache=cache)
    assert untouched[0].cooldown_active is True
    assert untouched[0].cooldown_cleared is False
    assert cache.last_attempt_at("6147", "TW") is not None

    cleared = diagnose_positions(positions=positions, cache=cache, clear_cooldown=True)
    assert cleared[0].cooldown_cleared is True
    assert cleared[0].cooldown_active is False
    assert cache.last_attempt_at("6147", "TW") is None
    assert "是（已清除）" in render_report(cleared, probed=False)
