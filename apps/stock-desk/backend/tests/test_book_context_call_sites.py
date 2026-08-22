"""S-D6-1: every production caller of ``build_book_context`` names a market.

``app.advice.book.build_book_context`` defaults ``market`` to ``None``, which
makes it match a symbol in *any* market (``_matching``). That default exists
for hand-assembled contexts (the alert vocabulary's, and tests), but for a
production caller it would silently merge a TW holding with its US namesake and
hand cap 2 a sector gap computed over both -- the exact input D6's ETF/
unsupported-market sentences are chosen from.

risk-compliance's suggested S-D6-1 (``work/reviews/2026-08-16-品質債清償批-
覆核.md``) asked for that premise to be pinned rather than assumed. These tests
therefore spy on the *bound* name in each consumer module and drive the real
code path, so both a dropped keyword and a keyword that evaluates to ``None``
fail here -- neither of which a source-text grep would catch.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.advice import book_limits as book_limits_module
from app.advice.book import BookContext, build_book_context
from app.advice.book_limits import evaluate_book_limits
from app.advice.limits import RiskBudget
from app.alerts import snapshot as snapshot_module
from app.alerts.snapshot import build_snapshot
from app.api import advice as advice_module
from app.portfolio.valuation import PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from tests.advice_helpers import book_position, book_summary
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness


class _MarketSpy:
    """Records the ``market`` each call was given, then delegates for real."""

    def __init__(self) -> None:
        self.markets: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> BookContext:
        # Positional-only ``summary`` aside, every parameter is keyword-only,
        # so a caller that forgot ``market`` records the sentinel below rather
        # than raising -- the assertion, not an exception, is what reports it.
        self.markets.append(kwargs.get("market", "<omitted>"))
        return build_book_context(*args, **kwargs)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Any], _MarketSpy]]:
    """Installs the spy over one consumer module's bound ``build_book_context``."""
    recorder = _MarketSpy()

    def install(module: Any) -> _MarketSpy:
        monkeypatch.setattr(module, "build_book_context", recorder)
        return recorder

    yield install


def _assert_every_call_named_a_market(recorder: _MarketSpy) -> None:
    assert recorder.markets, "the path under test never reached build_book_context"
    for market in recorder.markets:
        assert market is not None
        assert market != "<omitted>"


def test_the_advice_endpoint_passes_the_requested_market(
    api_harness: ApiHarness, spy: Callable[[Any], _MarketSpy]
) -> None:
    recorder = spy(advice_module)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())

    assert api_harness.client.get("/api/advice/2330").json()["status"] == "ok"
    _assert_every_call_named_a_market(recorder)
    assert recorder.markets == ["TW"]


def test_the_book_limits_aggregate_passes_each_holdings_own_market(
    spy: Callable[[Any], _MarketSpy],
) -> None:
    recorder = spy(book_limits_module)
    summary = book_summary(
        book_position(1, "2330", market="TW"),
        book_position(2, "AAPL", market="US", currency="USD", fx_to_twd="31"),
    )

    evaluate_book_limits(summary, RiskBudget())
    _assert_every_call_named_a_market(recorder)
    # One context per (symbol, market) group, each carrying its own market --
    # never the ``None`` that would match both legs of a cross-listed symbol.
    assert sorted(recorder.markets) == ["TW", "US"]


def test_the_alert_snapshot_passes_the_market_it_was_asked_about(
    tmp_path: Path, spy: Callable[[Any], _MarketSpy]
) -> None:
    recorder = spy(snapshot_module)
    store = PositionStore(db_path=tmp_path / "positions.db")
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(600),
            currency="TWD",
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )
    service = FakePriceService()
    service.seed("2330", recent_bars(trending_closes(60), symbol="2330"))

    build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=store,
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        fx_provider=None,
        today=datetime.now(UTC).date(),
    )
    _assert_every_call_named_a_market(recorder)
    assert recorder.markets == ["TW"]


# --- The same premise for cap 5's pair (C5) ----------------------------------


class _KellySpy:
    """Records the ``kelly`` each call was given, then delegates for real."""

    def __init__(self) -> None:
        self.pairs: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> BookContext:
        self.pairs.append(kwargs.get("kelly", "<omitted>"))
        return build_book_context(*args, **kwargs)


def test_the_advice_endpoint_hands_cap_5_the_pair_it_has_stored(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stored pair that never reaches the context is a card stating a falsehood.

    ``build_book_context`` defaults ``kelly`` to ``None``, and ``None`` is the
    sentence "此標的尚未輸入…". So a caller that forgets the keyword does not fail
    loudly -- it tells the user they never entered an input they did enter. The
    spy watches the bound name and drives the real endpoint, so a dropped keyword
    and a keyword evaluating to ``None`` both fail here.
    """
    recorder = _KellySpy()
    monkeypatch.setattr(advice_module, "build_book_context", recorder)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0}
    )

    assert api_harness.client.get("/api/advice/2330").json()["status"] == "ok"

    assert recorder.pairs, "the endpoint never reached build_book_context"
    for pair in recorder.pairs:
        assert pair != "<omitted>"
        assert pair is not None
        assert pair.win_rate == 0.6


def test_the_portfolio_limits_endpoint_hands_each_holding_its_own_pair(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same premise on the overview, where the mapping is built in bulk."""
    recorder = _KellySpy()
    monkeypatch.setattr(book_limits_module, "build_book_context", recorder)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0}
    )

    assert api_harness.client.get("/api/portfolio/limits").status_code == 200

    assert recorder.pairs
    for pair in recorder.pairs:
        assert pair != "<omitted>"
        assert pair is not None
        assert pair.win_rate == 0.6
