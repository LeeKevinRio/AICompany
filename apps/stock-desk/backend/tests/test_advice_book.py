"""Tests for the positions -> risk-budget context adapter (``app/advice/book.py``)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.advice import book as book_module
from app.advice.book import (
    EQUITY_BASIS_NOTE,
    GROSS_EXPOSURE_NOTE,
    FxQuote,
    build_book_context,
    self_reported_net_worth,
)
from app.data.interface import DataStatus
from app.portfolio.summary import PortfolioSummary, SummaryPosition, Totals
from app.portfolio.valuation import PriceInfo, Valuation
from tests.advice_helpers import reported_net_worth


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
    # AC-9.2: no reported net worth, so the numerator is not offered either and
    # the standing note is the one this product shipped with.
    book = build_book_context(_summary(_position(1, "2330")), symbol="2330", close=600.0)
    assert book.context.gross_exposure_twd is None
    assert book.context.net_worth is None
    assert GROSS_EXPOSURE_NOTE in book.notes
    assert EQUITY_BASIS_NOTE in book.notes


# --- FR-9: the reported net worth on its way into the context ----------------


def test_a_reported_net_worth_turns_the_valued_book_into_the_numerator() -> None:
    book = build_book_context(
        _summary(_position(1, "2330")),
        symbol="2330",
        close=600.0,
        net_worth=reported_net_worth(1_500_000.0),
    )
    assert book.context.gross_exposure_twd == 600_000.0
    assert book.context.net_worth is not None
    assert book.context.net_worth.amount_twd == 1_500_000.0
    assert book.context.book_fully_valued is True
    # The standing note now describes the ratio that exists, not the one that
    # does not, and says which half the user supplied.
    assert GROSS_EXPOSURE_NOTE not in book.notes
    assert any("自報的帳戶總淨值" in note for note in book.notes)


def test_the_equity_basis_is_untouched_by_a_reported_net_worth() -> None:
    # AC-9.6 at the adapter: option B changes what cap 3 divides by and nothing
    # else. ``total_equity_twd`` -- caps 1 and 4's denominator -- must be the
    # same number with and without the new input.
    summary = _summary(_position(1, "2330"))
    without = build_book_context(summary, symbol="2330", close=600.0)
    with_net_worth = build_book_context(
        summary, symbol="2330", close=600.0, net_worth=reported_net_worth(9_000_000.0)
    )
    assert without.context.total_equity_twd == with_net_worth.context.total_equity_twd
    assert (
        without.context.position_market_value_twd
        == with_net_worth.context.position_market_value_twd
    )


def test_an_unvalued_position_marks_the_book_as_incomplete() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2454", price=None))
    book = build_book_context(
        summary, symbol="2330", close=600.0, net_worth=reported_net_worth(1_500_000.0)
    )
    assert book.context.book_fully_valued is False


def test_an_empty_book_counts_as_fully_valued() -> None:
    book = build_book_context(_summary(market_value="0"), symbol="2330", close=600.0)
    assert book.context.book_fully_valued is True


def test_self_reported_net_worth_measures_the_age_of_the_report() -> None:
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    reported = self_reported_net_worth(
        2_000_000.0, (now - timedelta(days=9, hours=1)).isoformat(), now=now
    )
    assert reported is not None
    assert reported.amount_twd == 2_000_000.0
    assert reported.age_days == 9


def test_self_reported_net_worth_reads_a_naive_timestamp_as_utc() -> None:
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    reported = self_reported_net_worth(2_000_000.0, "2026-08-01T12:00:00", now=now)
    assert reported is not None
    assert reported.age_days == 4


def test_self_reported_net_worth_is_withheld_when_it_cannot_be_trusted() -> None:
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    # Nothing entered, a non-positive amount, no timestamp, or one that cannot
    # be read: none of these can be shown to be a fresh positive denominator,
    # so none of them is passed on as one.
    assert self_reported_net_worth(None, now.isoformat(), now=now) is None
    assert self_reported_net_worth(0.0, now.isoformat(), now=now) is None
    assert self_reported_net_worth(-5.0, now.isoformat(), now=now) is None
    assert self_reported_net_worth(2_000_000.0, None, now=now) is None
    assert self_reported_net_worth(2_000_000.0, "上週", now=now) is None


def test_a_future_timestamp_is_not_a_negative_age() -> None:
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    reported = self_reported_net_worth(
        2_000_000.0, (now + timedelta(days=3)).isoformat(), now=now
    )
    assert reported is not None
    assert reported.age_days == 0


def test_unvalued_positions_are_excluded_and_disclosed() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2454", price=None))
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert any("無法估值" in note for note in book.notes)


def test_a_symbols_own_unvalued_lot_is_excluded_and_disclosed() -> None:
    summary = _summary(_position(1, "2330"), _position(2, "2330", price=None))
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.context.quantity == 1000.0  # only the valued lot
    assert any("此標的有 1 筆持倉無法估值" in note for note in book.notes)


def _fx(
    rate: float | None = 31.5,
    *,
    pair: str = "USDTWD",
    status: DataStatus = DataStatus.FRESH,
    as_of: str | None = "2026-07-24",
    source: str = "fake_fx",
    source_note: str = "此匯率來源未經查證。",
) -> FxQuote:
    return FxQuote(
        pair=pair,
        rate=rate,
        as_of=as_of,
        source=source,
        status=status,
        source_note=source_note,
    )


def test_a_foreign_currency_holding_without_a_quote_drops_the_price() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    book = build_book_context(summary, symbol="AAPL", market="US", close=200.0, currency="USD")
    # Without an FX quote the price is withheld, so price-based caps report
    # not_evaluable instead of being scaled by an invented 1.0 rate.
    assert book.context.close is None
    assert book.fx_rate is None
    assert any("不以 1.0 匯率代入" in note for note in book.notes)
    # The reason must be about the conversion, not about the price.
    assert any("無法取得匯率換算" in note for note in book.notes)


def test_a_supplied_rate_makes_the_price_caps_evaluable() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    book = build_book_context(
        summary,
        symbol="AAPL",
        market="US",
        close=200.0,
        currency="USD",
        atr=4.0,
        fx=_fx(),
    )
    assert book.context.close == 200.0
    assert book.context.fx_to_twd == 31.5
    assert book.context.atr == 4.0
    assert book.fx_rate == 31.5
    assert book.context.price_twd() == 6300.0


def test_the_applied_rate_carries_its_freshness_date_and_source_into_notes() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    book = build_book_context(
        summary,
        symbol="AAPL",
        market="US",
        close=200.0,
        currency="USD",
        fx=_fx(status=DataStatus.CACHED_STALE, as_of="2026-07-20"),
    )
    note = book.fx_note or ""
    assert "cached_stale" in note
    assert "2026-07-20" in note
    assert "fake_fx" in note
    # The source's standing disclosure rides along with the number it qualifies.
    assert "此匯率來源未經查證。" in book.notes


def test_an_unavailable_quote_still_reports_its_status_and_source() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    book = build_book_context(
        summary,
        symbol="AAPL",
        market="US",
        close=200.0,
        currency="USD",
        atr=4.0,
        fx=_fx(None, status=DataStatus.UNAVAILABLE, as_of=None),
    )
    assert book.context.close is None
    assert book.context.fx_to_twd == 1.0  # never applied: close is None
    assert book.context.price_twd() is None
    # ATR is in the foreign currency too, so it is dropped rather than compared
    # against TWD amounts.
    assert book.context.atr is None
    note = book.fx_note or ""
    assert "unavailable" in note
    assert "無法取得匯率換算" in note
    assert "無法取得價格" in note  # named only to say it is *not* the cause


def test_a_quote_for_the_wrong_pair_is_refused() -> None:
    # A candidate quoted in a currency the resolver did not price: a USDTWD
    # rate is not "close enough" to convert a EUR amount.
    summary = _summary(_position(1, "2330"))
    book = build_book_context(
        summary, symbol="SAP", market="US", close=200.0, currency="EUR", fx=_fx()
    )
    assert book.context.close is None
    assert "EURTWD" in (book.fx_note or "")
    assert "USDTWD" in (book.fx_note or "")


def test_a_non_positive_rate_is_refused() -> None:
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", price="200"))
    book = build_book_context(
        summary, symbol="AAPL", market="US", close=200.0, currency="USD", fx=_fx(0.0)
    )
    assert book.context.close is None


def test_a_twd_holding_needs_no_quote_and_gets_no_fx_note() -> None:
    book = build_book_context(
        _summary(_position(1, "2330")), symbol="2330", close=600.0, currency="TWD", fx=_fx()
    )
    assert book.context.fx_to_twd == 1.0
    assert book.fx_rate == 1.0
    assert book.fx_note is None


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


def test_book_imports_no_adapter() -> None:
    # F-1: this layer stays a pure function. The caller resolves the rate; if an
    # adapter import appeared here, every test of it would need a network mock.
    tree = ast.parse(Path(book_module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        module = ""
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
        elif isinstance(node, ast.Import):
            module = node.names[0].name
        assert not module.startswith("app.data.providers"), module


def test_no_default_rate_literal_lurks_in_the_conversion_path() -> None:
    # F-2: the only 1.0 in this module is the TWD identity and the field
    # placeholder that is provably never applied (``close`` is None with it).
    source = Path(book_module.__file__).read_text(encoding="utf-8")
    assert "不以 1.0 匯率代入" in source
    assert "fx_to_twd=rate if rate is not None else 1.0" in source


def test_atr_is_passed_through_when_supplied() -> None:
    book = build_book_context(
        _summary(_position(1, "2330")), symbol="2330", close=600.0, atr=12.5
    )
    assert book.context.atr == 12.5
