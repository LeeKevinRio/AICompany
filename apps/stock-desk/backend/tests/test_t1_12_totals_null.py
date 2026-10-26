"""T1-12: ``Totals`` amounts are ``null`` when nothing could be valued.

ADR-0025 D-12 / AV-16, impact assessment T1-01 (attachment A-5). When
``status == "no_data"`` -- the empty book included -- the five amounts are
``None``; ``partial`` and ``complete`` are unchanged. The two internal
consumers that used to read ``totals.market_value_twd`` now sum the valued
rows through :func:`app.portfolio.summary.valued_market_value_twd`, so no
code path reads a ``None`` total as ``0`` and internal behaviour is unchanged
digit for digit.

Groups follow A-5: T1 contract, T2 validator, C1 grep guard, C2 equality,
T4 consumers, plus the A-4 change-column pairing.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.advice.book import _book_equity, self_reported_net_worth
from app.advice.limits import GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL, RiskBudget
from app.alerts.snapshot import build_snapshot
from app.data.cache import PriceBarCache
from app.data.interface import Market, PriceBar
from app.dividends.store import DividendEventStore
from app.portfolio.price_change import ChangeScreen
from app.portfolio.summary import PortfolioSummary, Totals, build_summary, valued_market_value_twd
from app.portfolio.valuation import PositionValuator
from app.positions.models import Currency, PositionInput
from app.positions.store import PositionStore
from app.settings.models import NetWorthSettings
from app.settings.net_worth import NET_WORTH_NO_VALUED_BOOK_NOTE
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness

AMOUNTS = (
    "cost_twd",
    "market_value_twd",
    "unrealized_pnl_twd",
    "asset_contribution_twd",
    "fx_contribution_twd",
)
NET_WORTH_TWD = 5_000_000.0


def _summary_body(harness: ApiHarness) -> dict[str, Any]:
    response = harness.client.get("/api/portfolio/summary")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _hold(harness: ApiHarness, symbol: str, *, priced: bool) -> None:
    if priced:
        harness.price_service.seed(symbol, recent_bars(trending_closes(200), symbol=symbol))
    response = harness.client.post("/api/positions", json=position_payload(symbol=symbol))
    assert response.status_code in (200, 201)


def _report_net_worth(harness: ApiHarness) -> None:
    current = harness.settings.load()
    harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=NET_WORTH_TWD,
                    updated_at=datetime.now(UTC).isoformat(),
                )
            }
        )
    )


def _overview_caps(harness: ApiHarness) -> dict[str, dict[str, Any]]:
    body = harness.client.get("/api/portfolio/limits").json()
    return {check["limit_id"]: check for check in body["limits"]}


def _card_caps(harness: ApiHarness, symbol: str) -> dict[str, dict[str, Any]]:
    body = harness.client.get(f"/api/advice/{symbol}").json()
    assert body["status"] == "ok"
    return {check["id"]: check for check in body["advice"]["limits_check"]}


# --- T1: the JSON contract (AC-B4b-1) ----------------------------------------------


def test_t1_an_unpriced_book_serves_every_amount_as_null(api_harness: ApiHarness) -> None:
    _hold(api_harness, "2330", priced=False)
    _hold(api_harness, "2454", priced=False)
    totals = _summary_body(api_harness)["totals"]
    assert totals["status"] == "no_data"
    for name in AMOUNTS:
        assert totals[name] is None, name


def test_t1_an_empty_book_serves_every_amount_as_null(api_harness: ApiHarness) -> None:
    body = _summary_body(api_harness)
    assert body["positions"] == []
    assert body["totals"]["status"] == "no_data"
    for name in AMOUNTS:
        assert body["totals"][name] is None, name


def test_t1_a_partial_book_still_serves_string_amounts(api_harness: ApiHarness) -> None:
    _hold(api_harness, "2330", priced=True)
    _hold(api_harness, "2454", priced=False)
    totals = _summary_body(api_harness)["totals"]
    assert totals["status"] == "partial"
    for name in AMOUNTS:
        assert isinstance(totals[name], str), name
    assert Decimal(totals["market_value_twd"]) > 0


def test_t1_a_complete_book_still_serves_string_amounts(api_harness: ApiHarness) -> None:
    _hold(api_harness, "2330", priced=True)
    totals = _summary_body(api_harness)["totals"]
    assert totals["status"] == "complete"
    for name in AMOUNTS:
        assert isinstance(totals[name], str), name


# --- T2: the validator holds both directions --------------------------------------


def _amounts(value: Decimal | None) -> dict[str, Decimal | None]:
    return dict.fromkeys(AMOUNTS, value)


@pytest.mark.parametrize("field", AMOUNTS)
def test_t2_no_data_with_any_amount_set_is_rejected(field: str) -> None:
    amounts = _amounts(None)
    amounts[field] = Decimal(0)
    with pytest.raises(ValidationError, match="no_data totals must have every amount None"):
        Totals(**amounts, status="no_data")


@pytest.mark.parametrize("status", ["partial", "complete"])
@pytest.mark.parametrize("field", AMOUNTS)
def test_t2_a_valued_status_with_any_amount_none_is_rejected(field: str, status: str) -> None:
    amounts = _amounts(Decimal(1))
    amounts[field] = None
    with pytest.raises(ValidationError, match="must have every amount set"):
        Totals.model_validate({**amounts, "status": status})


@pytest.mark.parametrize(
    ("value", "status"),
    [(None, "no_data"), (Decimal(0), "partial"), (Decimal(0), "complete")],
)
def test_t2_the_legal_shapes_construct(value: Decimal | None, status: str) -> None:
    totals = Totals.model_validate({**_amounts(value), "status": status})
    assert totals.market_value_twd == value


# --- C1: nothing outside the summary module reads a totals amount -----------------

_APP = Path(__file__).resolve().parents[1] / "app"
_SUMMARY_MODULE = _APP / "portfolio" / "summary.py"
#: Direct ``.totals.<amount>`` reads only. Aliasing (``t = s.totals; t.x``),
#: ``getattr`` and ``model_dump()["totals"]`` are not caught; those are left to
#: review (A-5 C1/C3).
_TOTALS_AMOUNT_READ = re.compile(
    r"\.totals\.(cost_twd|market_value_twd|unrealized_pnl_twd|asset_contribution_twd|fx_contribution_twd)"
)


def test_c1_the_pattern_catches_the_old_read() -> None:
    assert _TOTALS_AMOUNT_READ.search("float(summary.totals.market_value_twd)")
    assert _TOTALS_AMOUNT_READ.search("x = summary.totals.cost_twd")
    assert not _TOTALS_AMOUNT_READ.search("summary.totals.status")


def test_c1_no_app_module_reads_a_totals_amount() -> None:
    hits = [
        f"{path.relative_to(_APP)}:{number}"
        for path in sorted(_APP.rglob("*.py"))
        if path != _SUMMARY_MODULE
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _TOTALS_AMOUNT_READ.search(line)
    ]
    assert hits == []


# --- C2: the helper equals the total wherever a total exists ----------------------


def _store_and_valuator(
    tmp_path: Path, *, priced: tuple[str, ...], held: tuple[str, ...]
) -> tuple[PositionStore, PositionValuator]:
    prices = FakePriceService()
    for symbol in priced:
        prices.seed(symbol, recent_bars(trending_closes(30), symbol=symbol))
    store = PositionStore(db_path=tmp_path / "positions.db")
    for index, symbol in enumerate(held):
        store.create(
            PositionInput(
                symbol=symbol,
                market="TW",
                quantity=Decimal(1000 + 250 * index),
                avg_cost=Decimal("90"),
                currency="TWD",
                opened_at=date(2024, 1, 2),
                instrument_type="stock",
                note=None,
            ),
            now=datetime.now(UTC),
        )
    valuator = PositionValuator(market_services={"TW": prices}, fx_provider=UnavailableFxProvider())
    return store, valuator


@pytest.mark.parametrize(
    ("priced", "status"),
    [(("2330",), "partial"), (("2330", "2454", "2317"), "complete")],
)
def test_c2_the_helper_and_book_equity_equal_the_total(
    tmp_path: Path, priced: tuple[str, ...], status: str
) -> None:
    store, valuator = _store_and_valuator(tmp_path, priced=priced, held=("2330", "2454", "2317"))
    summary = build_summary(store, valuator)
    assert summary.totals.status == status
    total = summary.totals.market_value_twd
    assert total is not None
    assert valued_market_value_twd(summary.positions) == total
    equity, valued, count = _book_equity(summary)
    assert equity == float(total)
    assert (valued, count) == (len(priced), 3)


def test_c2_the_helper_is_zero_for_a_book_with_nothing_valued(tmp_path: Path) -> None:
    store, valuator = _store_and_valuator(tmp_path, priced=(), held=("2330",))
    summary = build_summary(store, valuator)
    assert summary.totals.market_value_twd is None
    assert valued_market_value_twd(summary.positions) == Decimal(0)
    assert valued_market_value_twd([]) == Decimal(0)
    assert _book_equity(summary) == (0.0, 0, 1)


def test_c2_the_helper_skips_unvalued_rows(tmp_path: Path) -> None:
    store, valuator = _store_and_valuator(tmp_path, priced=("2330",), held=("2330", "2454"))
    summary = build_summary(store, valuator)
    [valued_row] = [p for p in summary.positions if p.valuation.status == "ok"]
    assert valued_row.market_value_twd is not None
    assert valued_market_value_twd(summary.positions) == valued_row.market_value_twd


# --- T4: consumers (AC-B4b-3) ------------------------------------------------------


def test_t4a_an_unpriced_book_withholds_gross_exposure_on_both_surfaces(
    api_harness: ApiHarness,
) -> None:
    # The book holds 2454 with no price; the card is asked about 2330, which has
    # bars but is not held, so the book stays no_data.
    _hold(api_harness, "2454", priced=False)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    _report_net_worth(api_harness)
    assert _summary_body(api_harness)["totals"]["status"] == "no_data"

    for caps in (_overview_caps(api_harness), _card_caps(api_harness, "2330")):
        gross = caps["gross_exposure"]
        assert gross["status"] == "not_evaluable"
        assert gross["observed"] is None
        assert gross["detail"].startswith(GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL)
        for limit_id in (
            "single_position_weight",
            "sector_weight",
            "per_trade_loss",
            "kelly_fraction",
        ):
            assert caps[limit_id]["status"] == "not_evaluable", limit_id


def test_t4b_an_empty_book_with_a_net_worth_is_pinned_as_it_stands(
    api_harness: ApiHarness,
) -> None:
    # Pinned, not judged (A-5 T4 (b)): the overview withholds cap 3 for an empty
    # book while the card still computes 0% against the reported net worth.
    _report_net_worth(api_harness)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    overview = _overview_caps(api_harness)["gross_exposure"]
    assert overview["status"] == "not_evaluable"
    assert overview["observed"] is None
    assert "帳本內沒有任何持倉" in overview["detail"]
    card = _card_caps(api_harness, "2330")["gross_exposure"]
    assert card["status"] == "passed"
    assert card["observed"] == 0.0


def test_t4c_reporting_a_net_worth_on_an_unpriced_book_stores_no_yardstick(
    api_harness: ApiHarness,
) -> None:
    _hold(api_harness, "2454", priced=False)
    response = api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": NET_WORTH_TWD}}
    )
    assert response.status_code == 200
    assert NET_WORTH_NO_VALUED_BOOK_NOTE in response.json()["net_worth"]["notes"]
    stored = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    assert stored["valued_book_twd_at_report"] is None


def test_t4d_the_alert_snapshot_survives_an_unpriced_book(tmp_path: Path) -> None:
    prices = FakePriceService()
    prices.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    store, _ = _store_and_valuator(tmp_path, priced=(), held=("2454",))
    valuator = PositionValuator(market_services={"TW": prices}, fx_provider=UnavailableFxProvider())
    assert build_summary(store, valuator).totals.status == "no_data"
    snap = build_snapshot(
        "2330",
        "TW",
        resolver={"TW": prices},
        store=store,
        valuator=valuator,
        budget=RiskBudget(),
        net_worth=self_reported_net_worth(NET_WORTH_TWD, datetime.now(UTC).isoformat()),
    )
    assert snap.limits
    gross = next(check for check in snap.limits if check.id == "gross_exposure")
    assert gross.status == "not_evaluable"


# --- A-4: a null total does not null a row's change -------------------------------

_MON = date(2026, 10, 5)
_FRI = date(2026, 10, 2)


def _us_bars(symbol: str, closes: list[tuple[date, str]]) -> list[PriceBar]:
    market: Market = "US"
    return [
        PriceBar(
            symbol=symbol,
            market=market,
            date=day,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=1,
            currency="USD",
            as_of=datetime(2026, 10, 5, 7, 0, tzinfo=UTC),
            source="yfinance",
        )
        for day, close in closes
    ]


def test_a4_a_priced_us_row_without_fx_keeps_its_change_while_totals_are_null(
    tmp_path: Path,
) -> None:
    prices = FakePriceService(source="yfinance")
    prices.seed("AAPL", _us_bars("AAPL", [(_FRI, "250.00"), (_MON, "245.00")]))
    bar_cache = PriceBarCache(db_path=tmp_path / "bars.db")
    # The calendar the cache has observed: Fri and Mon.
    bar_cache.put(_us_bars("AAPL", [(_FRI, "1"), (_MON, "1")]), source="yfinance")
    store = PositionStore(db_path=tmp_path / "positions.db")
    currency: Currency = "USD"
    store.create(
        PositionInput(
            symbol="AAPL",
            market="US",
            quantity=Decimal("10"),
            avg_cost=Decimal("200"),
            currency=currency,
            opened_at=date(2026, 1, 5),
            instrument_type="stock",
            note=None,
        ),
        now=datetime(2026, 10, 5, 7, 0, tzinfo=UTC),
    )
    valuator = PositionValuator(
        market_services={"US": prices},
        fx_provider=UnavailableFxProvider(),
        clock=lambda: datetime(2026, 10, 5, 7, 0, tzinfo=UTC),
    )
    screen = ChangeScreen(
        ex_dates=DividendEventStore(db_path=tmp_path / "dividends.db"), calendar=bar_cache
    )
    summary: PortfolioSummary = build_summary(store, valuator, change_screen=screen)
    assert summary.totals.status == "no_data"
    assert summary.totals.market_value_twd is None
    [row] = summary.positions
    assert row.valuation.status != "ok"
    assert row.change is not None
