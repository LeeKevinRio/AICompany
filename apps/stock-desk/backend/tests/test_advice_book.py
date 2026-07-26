"""Tests for the positions -> risk-budget context adapter (``app/advice/book.py``)."""

from __future__ import annotations

from decimal import Decimal

from app.advice.book import EQUITY_BASIS_NOTE, GROSS_EXPOSURE_NOTE, build_book_context
from app.data.interface import DataStatus
from app.portfolio.summary import PortfolioSummary, SummaryPosition, Totals
from app.portfolio.valuation import PriceInfo, Valuation


def _valuation(price: str | None) -> Valuation:
    if price is None:
        return Valuation(
            status="insufficient_data",
            missing=["price"],
            price=None,
            pnl_original=None,
            pnl_twd=None,
            asset_contribution_twd=None,
            fx_contribution_twd=None,
        )
    return Valuation(
        status="ok",
        missing=[],
        price=PriceInfo(
            value=Decimal(price),
            as_of="2026-07-24",
            source="fake",
            data_status=DataStatus.FRESH,
        ),
        pnl_original=None,
        pnl_twd=Decimal(0),
        asset_contribution_twd=Decimal(0),
        fx_contribution_twd=Decimal(0),
    )


def _position(
    position_id: int,
    symbol: str,
    *,
    quantity: str = "1000",
    avg_cost: str = "500",
    price: str | None = "600",
    currency: str = "TWD",
    market: str = "TW",
) -> SummaryPosition:
    return SummaryPosition(
        id=position_id,
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        avg_cost=Decimal(avg_cost),
        currency=currency,  # type: ignore[arg-type]
        instrument_type="stock",
        opened_at="2024-01-02",
        note=None,
        valuation=_valuation(price),
    )


def _summary(*positions: SummaryPosition, market_value: str = "600000") -> PortfolioSummary:
    ok = [p for p in positions if p.valuation.status == "ok"]
    return PortfolioSummary(
        as_of="2026-07-25T00:00:00+00:00",
        totals=Totals(
            cost_twd=Decimal("500000"),
            market_value_twd=Decimal(market_value),
            unrealized_pnl_twd=Decimal("100000"),
            asset_contribution_twd=Decimal("100000"),
            fx_contribution_twd=Decimal(0),
            status="complete" if len(ok) == len(positions) else "partial",
        ),
        positions=list(positions),
    )


def test_held_symbol_rolls_up_quantity_cost_and_value() -> None:
    summary = _summary(_position(1, "2330"))
    book = build_book_context(summary, symbol="2330", market="TW", close=600.0, currency="TWD")
    assert book.held is True
    assert book.position_ids == [1]
    context = book.context
    assert context.quantity == 1000.0
    assert context.position_market_value_twd == 600_000.0
    assert context.position_cost_twd == 500_000.0
    assert context.total_equity_twd == 600_000.0
    assert context.fx_to_twd == 1.0


def test_multiple_lots_of_one_symbol_are_summed() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2330", quantity="500"))
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.position_ids == [1, 2]
    assert book.context.quantity == 1500.0
    assert book.context.position_market_value_twd == 900_000.0


def test_symbol_matching_is_case_insensitive_and_market_aware() -> None:
    summary = _summary(_position(1, "aapl", market="US", currency="USD", price=None))
    assert build_book_context(summary, symbol="AAPL").held is True
    assert build_book_context(summary, symbol="AAPL", market="TW").held is False


def test_candidate_context_is_zeroed_not_fabricated() -> None:
    summary = _summary(_position(1, "2330"))
    book = build_book_context(summary, symbol="2454", market="TW", close=900.0, currency="TWD")
    assert book.held is False
    assert book.position_ids == []
    assert book.context.position_market_value_twd == 0.0
    assert book.context.quantity == 0.0
    # No holding means no cost basis: ``None``, not a zero that reads as -100%.
    assert book.context.position_cost_twd is None


def test_gross_exposure_is_left_unset_with_the_reason_stated() -> None:
    book = build_book_context(_summary(_position(1, "2330")), symbol="2330", close=600.0)
    assert book.context.gross_exposure_twd is None
    assert GROSS_EXPOSURE_NOTE in book.notes
    assert EQUITY_BASIS_NOTE in book.notes


def test_unvalued_positions_are_excluded_and_disclosed() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2454", price=None))
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert any("無法估值" in note for note in book.notes)


def test_a_symbols_own_unvalued_lot_is_excluded_and_disclosed() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2330", price=None))
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.context.quantity == 1000.0  # only the valued lot
    assert any("此標的有 1 筆持倉無法估值" in note for note in book.notes)


def test_a_foreign_currency_holding_drops_the_price_rather_than_guess_an_fx_rate() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    book = build_book_context(summary, symbol="AAPL", market="US", close=200.0, currency="USD")
    # Without an FX source the price is withheld, so price-based caps report
    # not_evaluable instead of being scaled by an invented 1.0 rate.
    assert book.context.close is None
    assert any("沒有可用的匯率換算來源" in note for note in book.notes)


def test_a_symbol_held_in_two_currencies_drops_the_price() -> None:
    summary = _summary(
        _position(1, "AAPL", market="US", currency="USD", price="200"),
        _position(2, "AAPL", market="US", currency="TWD", price="6000"),
    )
    book = build_book_context(summary, symbol="AAPL", market="US", close=200.0)
    assert book.currency is None
    assert book.context.close is None
    assert any("橫跨多種計價幣別" in note for note in book.notes)


def test_sector_and_kelly_inputs_stay_absent() -> None:
    book = build_book_context(_summary(_position(1, "2330")), symbol="2330", close=600.0)
    assert book.context.sector is None
    assert book.context.sector_market_value_twd is None
    assert book.context.win_rate is None
    assert book.context.payoff_ratio is None


def test_atr_is_passed_through_when_supplied() -> None:
    book = build_book_context(
        _summary(_position(1, "2330")), symbol="2330", close=600.0, atr=12.5
    )
    assert book.context.atr == 12.5
