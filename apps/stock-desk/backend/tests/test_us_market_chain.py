"""The US ladder as assembled: five layers, and the reason that comes back.

ADR-0005 決策四 defines the US chain as ``TTL 內快取 -> Alpha Vantage ->
yfinance -> 任何快取（含過期）-> unavailable``. Each rung is exercised here with
fake providers, plus the two properties the assembly exists to guarantee:

* ``cache_first`` is what makes layer 0 real, and it must stay off for TW
  (ADR-0005 constraint D-1) -- a service built the TW way calls its provider on
  every request, no matter how warm the cache is;
* whatever reason a rung gave for declining (quota spent, no API key, source
  unreachable) has to survive all the way to what the API layer shows. Losing
  it turns three very different situations into one opaque "no data".
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.data.cache import PriceBarCache
from app.data.interface import (
    DataStatus,
    MarketDataProvider,
    PriceBar,
    ProviderResult,
)
from app.data.service import MarketDataService
from app.services.market import load_bars
from tests.api_helpers import recent_bars, trending_closes

_END = date(2026, 7, 26)
_START = _END - timedelta(days=100)
_NOW = datetime(2026, 7, 26, 6, 0, tzinfo=UTC)

QUOTA_SPENT = "Alpha Vantage 今日查詢額度已用罄，本次不呼叫主來源，請由備援來源接手。"
NO_API_KEY = "Alpha Vantage API key 尚未設定，暫不可用。"
YF_DOWN = "yfinance 連線逾時或發生錯誤，暫不可用。"


class FakeProvider(MarketDataProvider):
    """A provider that either answers or declines with a stated reason."""

    def __init__(
        self,
        source_id: str,
        *,
        bars: list[PriceBar] | None = None,
        reason: str | None = None,
        raises: bool = False,
    ) -> None:
        # ``source_id`` is a ClassVar on the ABC; per-instance ids are what
        # make a two-provider ladder legible in one test file.
        self.source_id = source_id  # type: ignore[misc]
        self._bars = bars or []
        self._reason = reason
        self._raises = raises
        self.calls = 0

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        if not self._bars:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=_NOW,
                source=self.source_id,
                staleness_minutes=None,
                reason=self._reason,
            )
        return ProviderResult(
            bars=[bar for bar in self._bars if start <= bar.date <= end],
            status=DataStatus.FRESH,
            as_of=_NOW,
            source=self.source_id,
            staleness_minutes=0,
        )


def _us_bars(count: int = 20) -> list[PriceBar]:
    return recent_bars(
        trending_closes(count), symbol="AAPL", market="US", source="fake_us", end=_END
    )


def _us_service(
    tmp_path: Path,
    *,
    primary: FakeProvider,
    backup: FakeProvider,
    cache: PriceBarCache | None = None,
    clock: datetime = _NOW,
) -> MarketDataService:
    """The US ladder exactly as ``app/api/deps.py`` composes it."""
    return MarketDataService(
        primary=primary,
        backups=[backup],
        cache=cache or PriceBarCache(db_path=tmp_path / "us.db"),
        clock=lambda: clock,
        cache_first=True,
    )


# --- The ladder, rung by rung ------------------------------------------------


def test_the_primary_answers_and_is_reported_fresh(tmp_path: Path) -> None:
    primary = FakeProvider("alpha_vantage", bars=_us_bars())
    backup = FakeProvider("yfinance", bars=_us_bars())
    result = _us_service(tmp_path, primary=primary, backup=backup).get_daily_bars(
        "AAPL", "US", _START, _END
    )
    assert result.status is DataStatus.FRESH
    assert result.source == "alpha_vantage"
    assert backup.calls == 0


def test_a_spent_quota_degrades_to_yfinance(tmp_path: Path) -> None:
    primary = FakeProvider("alpha_vantage", reason=QUOTA_SPENT)
    backup = FakeProvider("yfinance", bars=_us_bars())
    result = _us_service(tmp_path, primary=primary, backup=backup).get_daily_bars(
        "AAPL", "US", _START, _END
    )
    assert result.status is DataStatus.BACKUP
    assert result.source == "yfinance"
    # A rung that answered has nothing to explain.
    assert result.reason is None


def test_both_sources_down_falls_back_to_the_cache_with_the_reasons(
    tmp_path: Path,
) -> None:
    cache = PriceBarCache(db_path=tmp_path / "us.db")
    cache.put(_us_bars(), source="fake_us", fetched_at=_NOW - timedelta(days=3))
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage", reason=NO_API_KEY),
        backup=FakeProvider("yfinance", reason=YF_DOWN),
        cache=cache,
    )
    result = service.get_daily_bars("AAPL", "US", _START, _END)
    assert result.status is DataStatus.CACHED_STALE
    assert result.is_within_ttl is False
    assert result.reason is not None
    # Both rungs' own wording, in ladder order: "served from cache" alone does
    # not say whether the key is missing or the vendor is down.
    assert NO_API_KEY.rstrip("。") in result.reason
    assert YF_DOWN.rstrip("。") in result.reason


def test_nothing_anywhere_is_unavailable_carrying_every_reason(tmp_path: Path) -> None:
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage", reason=NO_API_KEY),
        backup=FakeProvider("yfinance", reason=YF_DOWN),
    )
    result = service.get_daily_bars("AAPL", "US", _START, _END)
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []
    assert result.reason is not None
    assert NO_API_KEY.rstrip("。") in result.reason
    assert YF_DOWN.rstrip("。") in result.reason


def test_a_provider_that_raises_is_reported_not_hidden(tmp_path: Path) -> None:
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage", raises=True),
        backup=FakeProvider("yfinance", reason=YF_DOWN),
    )
    result = service.get_daily_bars("AAPL", "US", _START, _END)
    assert result.reason is not None
    assert "alpha_vantage" in result.reason
    assert "非預期錯誤" in result.reason


def test_a_silent_provider_produces_no_invented_reason(tmp_path: Path) -> None:
    """A provider that degrades without a word is that provider's gap.

    The service states what it was told and nothing more -- it must not fill
    the silence with a guess about why.
    """
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage"),
        backup=FakeProvider("yfinance"),
    )
    assert service.get_daily_bars("AAPL", "US", _START, _END).reason is None


# --- Layer 0, and the TW behaviour it must not touch -------------------------


def test_layer_zero_serves_a_fresh_cache_without_spending_quota(tmp_path: Path) -> None:
    primary = FakeProvider("alpha_vantage", bars=_us_bars())
    backup = FakeProvider("yfinance", bars=_us_bars())
    service = _us_service(tmp_path, primary=primary, backup=backup)

    service.get_daily_bars("AAPL", "US", _START, _END)
    assert primary.calls == 1
    result = service.get_daily_bars("AAPL", "US", _START, _END)

    # The second read never reaches Alpha Vantage: this is the whole reason
    # layer 0 exists (a page reload must not burn a day's budget).
    assert primary.calls == 1
    assert result.status is DataStatus.CACHED_STALE
    assert result.is_within_ttl is True


def test_an_expired_cache_does_not_short_circuit_the_ladder(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "us.db")
    cache.put(_us_bars(), source="fake_us", fetched_at=_NOW - timedelta(days=3))
    primary = FakeProvider("alpha_vantage", bars=_us_bars())
    service = _us_service(
        tmp_path,
        primary=primary,
        backup=FakeProvider("yfinance"),
        cache=cache,
    )
    result = service.get_daily_bars("AAPL", "US", _START, _END)
    assert primary.calls == 1
    assert result.status is DataStatus.FRESH


def test_a_tw_shaped_service_still_calls_its_provider_every_time(tmp_path: Path) -> None:
    """ADR-0005 D-1: ``cache_first`` defaults off and TW keeps that default."""
    primary = FakeProvider("twse", bars=_us_bars())
    service = MarketDataService(
        primary=primary,
        cache=PriceBarCache(db_path=tmp_path / "tw.db"),
        clock=lambda: _NOW,
    )
    for _ in range(3):
        result = service.get_daily_bars("AAPL", "US", _START, _END)
    assert primary.calls == 3
    assert result.status is DataStatus.FRESH


# --- All the way out to the API's data envelope ------------------------------


def test_the_reason_reaches_the_data_envelope(tmp_path: Path) -> None:
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage", reason=QUOTA_SPENT),
        backup=FakeProvider("yfinance", reason=YF_DOWN),
    )
    loaded = load_bars(
        {"US": service}, symbol="AAPL", market="US", start=_START, end=_END
    )
    meta = loaded.meta()
    assert loaded.bars == []
    assert isinstance(meta["reason"], str)
    # The loader's own sentence stays (it is what every market says), and the
    # data layer's explanation is appended rather than replacing it.
    assert "沒有可用的日線資料" in meta["reason"]
    assert "額度已用罄" in meta["reason"]
    assert "yfinance" in meta["reason"]


def test_the_envelope_reports_ttl_freshness_for_a_layer_zero_hit(tmp_path: Path) -> None:
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage", bars=_us_bars()),
        backup=FakeProvider("yfinance"),
    )
    service.get_daily_bars("AAPL", "US", _START, _END)
    meta = load_bars(
        {"US": service}, symbol="AAPL", market="US", start=_START, end=_END
    ).meta()
    # ADR-0005 D-2: both fields, or the reader cannot tell "cached but updated
    # today" from "cached and out of date".
    assert meta["status"] == DataStatus.CACHED_STALE.value
    assert meta["is_within_ttl"] is True


def test_a_live_rung_reports_no_ttl_answer(tmp_path: Path) -> None:
    service = _us_service(
        tmp_path,
        primary=FakeProvider("alpha_vantage", bars=_us_bars()),
        backup=FakeProvider("yfinance"),
    )
    meta = load_bars(
        {"US": service}, symbol="AAPL", market="US", start=_START, end=_END
    ).meta()
    assert meta["status"] == DataStatus.FRESH.value
    assert meta["is_within_ttl"] is None
