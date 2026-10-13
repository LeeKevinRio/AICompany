"""F-9b PR-level risk conditions (風控 F9W-41, F9W-44, F9W-45).

``work/reviews/2026-10-13-F-9b-PR層級逐字審-F9W-40至F9W-48-風控.md``:

* F9W-41 -- W-c' beside a passing cache (C-34 (b)) reaches the alert push: the
  snapshot's ``reason`` and ``data_disclosure`` are the existing layer note,
  one space, and ``loaded.reason`` verbatim, and a fired message ends with it.
  Any change to the layer note or how it is joined goes back to risk review.
* F9W-44 -- tripwire for the C-14 residual: every equity rung ``deps`` builds
  has a non-blank ``str`` ``source_id``.
* F9W-45 -- the TAIEX reference number and its disclosure sentence come and go
  together, and a configuration error on the index path leaves both out with
  an ERROR log (not quietened).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app import scheduler
from app.advice.limits import RiskBudget
from app.alerts.engine import evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api import deps
from app.api import sectors_wording as wording
from app.data.cache import PriceBarCache
from app.data.gate_wording import UNIT_MISSING_REASON_TW
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers.alpha_vantage import AlphaVantageAdapter
from app.data.quota import QuotaLedger
from app.data.service import CurrencyLookupError
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.services.market import load_bars
from tests.alerts_helpers import add_rule, price_rule
from tests.api_helpers import UnavailableFxProvider
from tests.market_service_helpers import equity_service
from tests.test_api_sectors import _board, _build

NOW = datetime(2024, 1, 3, 8, 0, tzinfo=UTC)
DAY = date(2024, 1, 2)


def _bar(currency: str, *, source: str, day: date = DAY) -> PriceBar:
    return PriceBar(
        symbol="2330",
        market="TW",
        date=day,
        open=Decimal("600"),
        high=Decimal("600"),
        low=Decimal("600"),
        close=Decimal("600"),
        volume=1,
        currency="TWD",
        as_of=NOW,
        source=source,
    ).model_copy(update={"currency": currency})


class _Unlabelled(MarketDataProvider):
    """A live rung whose bars declare no unit (W-c')."""

    source_id = "finmind"

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=[_bar("", source="finmind")],
            status=DataStatus.FRESH,
            as_of=NOW,
            source="finmind",
            staleness_minutes=0,
        )


# --- F9W-41 -------------------------------------------------------------------------------


def test_f9w41_the_alert_push_carries_the_layer_note_then_the_w_c_prime_reason(
    tmp_path: Path,
) -> None:
    cache = PriceBarCache(db_path=tmp_path / "c.db")
    cache.put(
        [_bar("TWD", source="twse", day=date(2023, 12, 29))],
        source="twse",
        fetched_at=datetime(2023, 12, 29, 8, tzinfo=UTC),
    )
    service = equity_service(primary=_Unlabelled(), cache=cache, clock=lambda: NOW)
    loaded = load_bars(
        {"TW": service}, symbol="2330", market="TW", start=date(2023, 10, 1), end=DAY
    )
    assert loaded.status is DataStatus.CACHED_STALE  # C-34 (b), F9W-33 (b)
    assert loaded.reason is not None

    snapshot = build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=PositionStore(db_path=tmp_path / "positions.db"),
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        today=DAY,
    )

    expected = f"資料來自 cached_stale 層（{loaded.source}）。 {loaded.reason}"
    assert snapshot.data_disclosure == expected
    assert snapshot.reason == expected
    w_c_prime = UNIT_MISSING_REASON_TW.format(provider="finmind")
    assert expected.endswith(w_c_prime)  # whole, unaltered, its full stop included
    assert expected.count(w_c_prime.removesuffix("。")) == 1

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    add_rule(alerts, price_rule(above=True, threshold=100.0))
    result = evaluate_alerts(alerts, lambda _symbol, _market: snapshot, now=NOW)
    assert len(result.events) == 1
    assert result.events[0].message.endswith(expected)


# --- F9W-44 -------------------------------------------------------------------------------


@pytest.fixture
def isolated_yfinance() -> Iterator[None]:
    """Keep ``deps._default_yfinance`` (an ``lru_cache``) out of other tests.

    Building the resolver memoizes the one yfinance adapter for the process;
    clear it before and after so this test neither reuses nor leaves one.
    """
    deps._default_yfinance.cache_clear()
    yield
    if deps._default_yfinance.cache_info().currsize:
        deps._default_yfinance().close()
    deps._default_yfinance.cache_clear()


@pytest.mark.usefixtures("isolated_yfinance")
def test_f9w44_every_equity_rung_deps_builds_has_a_source_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tripwire for the C-14 residual (風控 F9W-44, after F9W-31 (a)).

    A rung without a non-blank ``str`` ``source_id`` would refuse W-c / W-c'
    bars with no sentence (C-14), so the equity reason could be ``None``. If
    this turns red, take it back to risk review together with that residual;
    do not just change the expectation.
    """
    monkeypatch.setattr(deps, "_default_cache", lambda: PriceBarCache(db_path=tmp_path / "w.db"))
    monkeypatch.setattr(
        deps,
        "AlphaVantageAdapter",
        lambda: AlphaVantageAdapter(ledger=QuotaLedger(db_path=tmp_path / "quota.db")),
    )
    resolver = deps._default_resolver.__wrapped__()  # bypass lru_cache
    markets: tuple[Market, ...] = ("TW", "US")
    seen: list[str] = []
    for market in markets:
        service = resolver[market]
        rungs = [service._primary, *service._backups]  # type: ignore[attr-defined]
        assert len(rungs) >= 2  # a primary and at least one backup
        for rung in rungs:
            source_id = getattr(rung, "source_id", None)
            assert isinstance(source_id, str), (market, rung)
            assert source_id.strip(), (market, rung)
            seen.append(source_id)
    assert seen == ["twse", "tpex", "finmind", "alpha_vantage", "yfinance"]


# --- F9W-45 -------------------------------------------------------------------------------


def test_f9w45_the_taiex_number_and_its_disclosure_come_and_go_together() -> None:
    with_reference = _build(_board(taiex=0.0123))
    without = _build(_board(taiex=None))

    assert with_reference["sectors"]
    assert {row["reference_taiex_return_L"] for row in with_reference["sectors"]} == {0.0123}
    assert wording.TAIEX_REFERENCE in with_reference["disclosures"]
    assert without["sectors"]
    assert {row["reference_taiex_return_L"] for row in without["sectors"]} == {None}
    assert wording.TAIEX_REFERENCE not in without["disclosures"]


def test_f9w45_a_configuration_error_leaves_the_reference_out_with_an_error_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class _Misconfigured:
        def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> object:
            raise CurrencyLookupError("no currency for market 'TW' at checkpoint provider")

        def get_cached_bars(self, symbol: str, market: Market, start: date, end: date) -> object:
            raise AssertionError("not read")

    monkeypatch.setattr(scheduler, "get_index_resolver", lambda: {"TW": _Misconfigured()})
    with caplog.at_level(logging.ERROR, logger=scheduler.logger.name):
        reference = scheduler.taiex_reference_return(date(2024, 1, 2), date(2024, 1, 31))

    assert reference is None
    [record] = [r for r in caplog.records if r.name == scheduler.logger.name]
    assert record.levelno == logging.ERROR  # not quietened (F9W-45)
    assert record.exc_info is not None and record.exc_info[0] is CurrencyLookupError
