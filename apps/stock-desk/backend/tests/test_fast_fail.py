"""Fast-fail behaviour when every source in a ladder is unreachable.

Covers Lane 1 of the 2026-08-13 穩定與速度衝刺 dispatch: with the pre-existing
``app/data/http.py`` defaults (10s uniform timeout, 3 retries, 1+2+4s backoff)
a single unreachable HTTP call could take up to 47s, and the production TW
ladder (twse -> tpex -> finmind, three providers, see ``app/api/deps.py``)
could therefore take up to ~141s end to end -- the "約 58s" figure on record
undersold it. This module has two kinds of test:

* a pure formula check on :func:`app.data.http.estimate_unreachable_chain_worst_case_seconds`,
  the single function both this test suite and any future report can call
  instead of re-deriving the arithmetic;
* an end-to-end check wiring the *real* adapters exactly as
  ``app/api/deps.py`` does, through a mock transport that raises a transport
  error and a fake "clock" fed to ``RateLimitedClient``'s injectable
  ``sleep_fn`` -- so the elapsed time asserted on is a deterministic count of
  requested waits, never a real ``time.sleep``, per this task's constraint
  against slowing down the suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.data import http
from app.data.cache import PriceBarCache
from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, PriceBar
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR, AlphaVantageAdapter
from app.data.providers.finmind import TOKEN_ENV_VAR as FINMIND_TOKEN_ENV_VAR
from app.data.providers.finmind import FinMindAdapter
from app.data.providers.tpex import TpexAdapter
from app.data.providers.twse import TwseAdapter
from app.data.providers.yfinance import YFinanceAdapter
from app.data.quota import DAILY_LIMIT_ENV_VAR, SAFETY_MARGIN_ENV_VAR, QuotaLedger
from app.data.service import MarketDataService

START = date(2024, 1, 1)
END = date(2024, 1, 31)

# The TW and US ladder depths exactly as ``app/api/deps.py`` assembles them
# (``_default_resolver``): TW = primary (twse) + 2 backups (tpex, finmind);
# US = primary (alpha_vantage) + 1 backup (yfinance).
TW_PROVIDER_COUNT = 3
US_PROVIDER_COUNT = 2

# Pre-fix reference numbers, kept here only as a comment (not re-derived from
# the old, now-removed constants) so a reader can see the before/after
# without archaeology: old worst case per unreachable HTTP call was
# 4 attempts * 10s + (1+2+4)s backoff = 47s, i.e. TW ~141s / US ~94s.


@dataclass
class _FakeClock:
    """Accumulates requested wait time without ever actually sleeping."""

    total_seconds: float = field(default=0.0)

    def advance(self, seconds: float) -> None:
        self.total_seconds += seconds


def _bar(symbol: str, trade_date: date, *, source: str) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market="TW",
        date=trade_date,
        open=Decimal("594.00"),
        high=Decimal("598.00"),
        low=Decimal("590.00"),
        close=Decimal("594.00"),
        volume=1000,
        currency="TWD",
        as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        source=source,
    )


def _unreachable_handler(clock: _FakeClock) -> httpx.MockTransport:
    """A transport whose every call "spends" one connect-timeout worth of
    (fake) time and then fails, simulating a host that never completes the
    TCP/TLS handshake -- the "source unreachable" scenario this task targets.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        clock.advance(http.DEFAULT_CONNECT_TIMEOUT_SECONDS)
        raise httpx.ConnectTimeout("simulated unreachable host", request=request)

    return httpx.MockTransport(handler)


def _unreachable_client(clock: _FakeClock) -> RateLimitedClient:
    """A client using the production retry/backoff defaults verbatim (no
    adapter in ``app/data/providers`` overrides ``max_retries``/
    ``backoff_seconds``), wired to the fake clock instead of real sleep.
    """
    return RateLimitedClient(
        min_interval_seconds=0.0,
        transport=_unreachable_handler(clock),
        sleep_fn=clock.advance,
    )


class TestWorstCaseFormula:
    """The formula alone, independent of any I/O."""

    def test_single_provider_worst_case(self) -> None:
        # (max_retries + 1) attempts * connect_timeout + backoff sum
        # = 2 * 2.0s + 1.0s = 5.0s.
        assert http.estimate_unreachable_chain_worst_case_seconds(1) == pytest.approx(5.0)

    def test_tw_ladder_worst_case_is_seconds_not_minutes(self) -> None:
        worst_case = http.estimate_unreachable_chain_worst_case_seconds(TW_PROVIDER_COUNT)
        assert worst_case == pytest.approx(15.0)
        # Sanity bound: nowhere near the old ~141s three-provider chain.
        assert worst_case < 20.0

    def test_us_ladder_worst_case_is_seconds_not_minutes(self) -> None:
        worst_case = http.estimate_unreachable_chain_worst_case_seconds(US_PROVIDER_COUNT)
        assert worst_case == pytest.approx(10.0)
        # Sanity bound: nowhere near the old ~94s two-provider chain.
        assert worst_case < 20.0


class TestTwLadderAllUnreachable:
    """Real ``TwseAdapter``/``TpexAdapter``/``FinMindAdapter``, wired exactly
    like ``app/api/deps.py``'s TW ladder, all unreachable."""

    def _service(
        self, tmp_path: Path, clock: _FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> MarketDataService:
        monkeypatch.setenv(FINMIND_TOKEN_ENV_VAR, "fixture-test-token-not-real")
        primary = TwseAdapter(client=_unreachable_client(clock))
        backups = [
            TpexAdapter(client=_unreachable_client(clock)),
            FinMindAdapter(client=_unreachable_client(clock)),
        ]
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        return MarketDataService(primary=primary, backups=backups, cache=cache)

    def test_falls_through_to_unavailable_within_the_estimated_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = _FakeClock()
        service = self._service(tmp_path, clock, monkeypatch)

        result = service.get_daily_bars("2330", "TW", START, END)

        # Semantics unchanged: no live source, no cache -> unavailable, empty
        # bars, never fabricated data (same as test_service.py's
        # test_all_providers_fail_and_no_cache_returns_unavailable).
        assert result.status is DataStatus.UNAVAILABLE
        assert result.bars == []
        assert result.staleness_minutes is None

        expected = http.estimate_unreachable_chain_worst_case_seconds(TW_PROVIDER_COUNT)
        assert clock.total_seconds == pytest.approx(expected)
        assert clock.total_seconds < 20.0

    def test_falls_through_to_cache_within_the_estimated_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = _FakeClock()
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        cache.put(
            [
                _bar("2330", date(2024, 1, 2), source="twse"),
            ],
            source="twse",
            fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC),
        )
        monkeypatch.setenv(FINMIND_TOKEN_ENV_VAR, "fixture-test-token-not-real")
        primary = TwseAdapter(client=_unreachable_client(clock))
        backups = [
            TpexAdapter(client=_unreachable_client(clock)),
            FinMindAdapter(client=_unreachable_client(clock)),
        ]
        service = MarketDataService(
            primary=primary,
            backups=backups,
            cache=cache,
            clock=lambda: datetime(2024, 1, 2, 11, 0, tzinfo=UTC),
        )

        result = service.get_daily_bars("2330", "TW", START, END)

        # Degradation to the cache rung, with staleness disclosed, unchanged.
        assert result.status is DataStatus.CACHED_STALE
        assert result.staleness_minutes == 60
        assert result.source == "twse"

        expected = http.estimate_unreachable_chain_worst_case_seconds(TW_PROVIDER_COUNT)
        assert clock.total_seconds == pytest.approx(expected)


class TestUsLadderAllUnreachable:
    """Real ``AlphaVantageAdapter``/``YFinanceAdapter``, wired exactly like
    ``app/api/deps.py``'s US ladder (``cache_first=True``), all unreachable."""

    def _service(
        self, tmp_path: Path, clock: _FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> MarketDataService:
        monkeypatch.setenv(API_KEY_ENV_VAR, "fixture-test-key-not-real")
        monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "25")
        monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")
        ledger = QuotaLedger(db_path=tmp_path / "quota.db")
        primary = AlphaVantageAdapter(
            client=_unreachable_client(clock), ledger=ledger, min_interval_seconds=0.0
        )
        backup = YFinanceAdapter(client=_unreachable_client(clock))
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        return MarketDataService(
            primary=primary, backups=[backup], cache=cache, cache_first=True
        )

    def test_falls_through_to_unavailable_within_the_estimated_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = _FakeClock()
        service = self._service(tmp_path, clock, monkeypatch)

        result = service.get_daily_bars("AAPL", "US", START, END)

        assert result.status is DataStatus.UNAVAILABLE
        assert result.bars == []

        expected = http.estimate_unreachable_chain_worst_case_seconds(US_PROVIDER_COUNT)
        assert clock.total_seconds == pytest.approx(expected)
        assert clock.total_seconds < 20.0
