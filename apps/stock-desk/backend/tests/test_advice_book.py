"""Tests for the positions -> risk-budget context adapter (``app/advice/book.py``)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.advice import book as book_module
from app.advice.book import (
    EQUITY_BASIS_NOTE,
    GROSS_EXPOSURE_NOTE,
    FxQuote,
    build_book_context,
    self_reported_net_worth,
)
from app.advice.limits import (
    NET_WORTH_STALE_AFTER_DAYS,
    RiskBudget,
    evaluate_limits,
    suggest_quantity_range,
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
    sector: str | None = None,
    fx_to_twd: str = "1",
) -> SummaryPosition:
    valuation = _valuation(price)
    # Mirrors what the valuator contributes to ``totals``: present only when the
    # position could be valued, and already converted to TWD. ``fx_to_twd``
    # stands in for the valuator's F0/F1 (equal here), so a foreign fixture
    # carries a TWD contribution that differs from its own-currency price.
    value = None
    cost = None
    if valuation.status == "ok":
        rate = Decimal(fx_to_twd)
        value = Decimal(quantity) * Decimal(str(price)) * rate
        cost = Decimal(quantity) * Decimal(avg_cost) * rate
    return SummaryPosition(
        id=position_id,
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        avg_cost=Decimal(avg_cost),
        currency=currency,  # type: ignore[arg-type]
        instrument_type="stock",
        opened_at="2024-01-02",
        sector=sector,
        note=None,
        valuation=valuation,
        market_value_twd=value,
        cost_twd=cost,
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
    note = next(n for n in book.notes if "自報的帳戶總淨值" in n)
    # The same readable form the cap's own disclosure uses -- these two
    # sentences sit next to each other on the card.
    assert "2026-07-24 23:51（台北時間）" in note
    assert "015754" not in note


def test_an_expired_net_worth_is_not_described_as_the_current_denominator() -> None:
    # The present-tense note would otherwise sit beside a cap reporting
    # not_evaluable *because* the figure expired, describing a division this
    # context does not perform.
    book = build_book_context(
        _summary(_position(1, "2330")),
        symbol="2330",
        close=600.0,
        net_worth=reported_net_worth(1_500_000.0, age_days=NET_WORTH_STALE_AFTER_DAYS),
    )
    note = next(n for n in book.notes if "帳戶總淨值" in n)
    assert f"已超過 {NET_WORTH_STALE_AFTER_DAYS} 天未更新" in note
    assert "not_evaluable" in note
    assert "為分子" not in note
    # And the cap agrees with the note.
    check = next(
        c for c in evaluate_limits(RiskBudget(), book.context) if c.id == "gross_exposure"
    )
    assert check.status == "not_evaluable"


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


# --- FX1: the roll-up and the caps must share one currency -------------------


def _us_book() -> PortfolioSummary:
    """A book of one USD holding (1000 x $200 @ 31.5) and one TWD holding.

    The USD holding is worth NT$6,300,000 -- 91% of the NT$6,900,000 book -- and
    only NT$200,000 if its own-currency price is mistaken for a TWD one.
    """
    return _summary(
        _position(
            1,
            "AAPL",
            market="US",
            currency="USD",
            price="200",
            avg_cost="150",
            fx_to_twd="31.5",
        ),
        _position(2, "2330"),
        market_value="6900000",
    )


def test_a_foreign_holding_is_rolled_up_in_twd_not_in_its_own_currency() -> None:
    # The numerator of cap 1 sits over ``total_equity_twd``: rolling this
    # position up at its USD price would divide dollars by dollars-times-31.5
    # and report 3% of the book where the truth is 91% -- an understatement of
    # risk, the one direction these caps must never err in.
    book = build_book_context(
        _us_book(), symbol="AAPL", market="US", close=200.0, currency="USD", fx=_fx()
    )
    context = book.context
    assert context.position_market_value_twd == pytest.approx(6_300_000.0)
    assert context.position_cost_twd == pytest.approx(4_725_000.0)
    assert context.total_equity_twd == pytest.approx(6_900_000.0)
    assert context.position_weight() == pytest.approx(6_300_000.0 / 6_900_000.0)
    # Both halves of this ratio are TWD, so it is a return, not an exchange rate.
    assert context.unrealized_pnl_pct() == pytest.approx(200 / 150 - 1)
    # And the cap says what the numbers say.
    check = next(
        c for c in evaluate_limits(RiskBudget(), context) if c.id == "single_position_weight"
    )
    assert check.status == "violated"


def test_the_share_suggestion_for_a_foreign_holding_stays_in_one_currency() -> None:
    # Same context, one step further down: ``notional_caps`` compares the TWD
    # cap against the position's market value and divides the gap by the TWD
    # price. A dollar-denominated market value there would invent headroom under
    # a cap that is already breached and suggest *buying more* of it.
    book = build_book_context(
        _us_book(), symbol="AAPL", market="US", close=200.0, currency="USD", fx=_fx()
    )
    budget = RiskBudget()
    assert suggest_quantity_range(budget, book.context, action="add") is None
    trim = suggest_quantity_range(budget, book.context, action="reduce")
    assert trim is not None
    # 0.15 x 6.9M = NT$1,035,000 of headroom, NT$6,300 a share.
    assert trim.min_shares == 836
    assert trim.max_shares == 1000  # never more than the holding
    assert trim.restores_compliance is True


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


def test_sector_stays_absent_until_the_holding_declares_one() -> None:
    # FR-12 added the field, not a guess: an unclassified holding still yields
    # no sector and no sector total. The Kelly inputs remain unsourced.
    book = build_book_context(_summary(_position(1, "2330")), symbol="2330", close=600.0)
    assert book.context.sector is None
    assert book.context.sector_market_value_twd is None
    assert book.context.sector_gap == "unfiled"
    assert book.context.win_rate is None
    assert book.context.payoff_ratio is None


def test_sector_total_sums_every_valued_holding_in_the_same_industry() -> None:
    # AC-12.4: the cap's numerator is the whole industry, not just this symbol.
    summary = _summary(
        _position(1, "2330", sector="半導體業"),  # 1000 x 600
        _position(2, "2303", sector="半導體業", quantity="500", price="100"),
        _position(3, "1101", sector="水泥工業", quantity="500", price="40"),
    )
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.context.sector == "半導體業"
    assert book.context.sector_market_value_twd == pytest.approx(650_000.0)
    assert not any("未填產業別" in note for note in book.notes)


def test_unclassified_holdings_are_disclosed_as_a_possible_understatement() -> None:
    # AC-12.5: holdings outside every bucket make each industry look smaller,
    # so the ratio is reported with that caveat rather than silently.
    summary = _summary(
        _position(1, "2330", sector="半導體業"),
        _position(2, "2317", quantity="500", price="100"),  # no sector stated
    )
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.context.sector_market_value_twd == pytest.approx(600_000.0)
    note = next(note for note in book.notes if "未填產業別" in note)
    # The count alone hides the size of the hole, so the risk-approved sentence
    # carries the market value and its share of equity as well (50,000 of the
    # 600,000 book -- ``_summary`` fixes the total at 600,000).
    assert "1 筆" in note
    assert "50,000 元" in note
    assert "8.33%" in note
    # And it says what an understated ratio does to a ``passed`` verdict.
    assert "通過判定" in note


def test_the_understatement_disclosure_is_dropped_without_a_denominator() -> None:
    # A share of nothing is not a number. Unreachable in practice (an
    # unclassified valued row is itself part of equity), and the equity-based
    # caps report ``not_evaluable`` here anyway.
    summary = _summary(
        _position(1, "2330", sector="半導體業"),
        _position(2, "2317", quantity="500", price="100"),
        market_value="0",
    )
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert not any("未填產業別" in note for note in book.notes)


def test_an_unvalued_holding_is_left_out_of_the_sector_total() -> None:
    summary = _summary(
        _position(1, "2330", sector="半導體業"),
        _position(2, "2303", sector="半導體業", price=None),
    )
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.context.sector_market_value_twd == pytest.approx(600_000.0)


def test_one_symbol_filed_under_two_industries_yields_no_sector() -> None:
    summary = _summary(
        _position(1, "2330", sector="半導體業"),
        _position(2, "2330", sector="電子零組件業"),
    )
    book = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert book.context.sector is None
    assert book.context.sector_market_value_twd is None
    assert book.context.sector_gap == "mixed"
    assert any("不只一種產業別" in note for note in book.notes)
    # The note carries the fix risk-compliance asked for alongside the refusal.
    assert any("統一為同一種產業別" in note for note in book.notes)


def test_a_candidate_has_no_sector_to_measure() -> None:
    # AC-12.6 / candidate mode: nothing is inferred from the symbol itself.
    summary = _summary(_position(1, "2330", sector="半導體業"))
    book = build_book_context(summary, symbol="2454", close=900.0, currency="TWD")
    assert book.held is False
    assert book.context.sector is None
    assert book.context.sector_gap == "no_position"


def test_a_holding_in_a_market_without_a_taxonomy_is_its_own_state() -> None:
    # AC-12.6: TWSE categories are TW-only, so a US holding is not "missing a
    # value" -- there is nothing it could be filed under yet, and cap 2 must not
    # tell its owner to fill one in (the API would answer that with a 422).
    # Covered here rather than in ``test_api_advice`` because that harness has
    # no US price source, so a US card never gets built there.
    summary = _summary(_position(1, "AAPL", market="US", currency="USD", fx_to_twd="31"))
    book = build_book_context(summary, symbol="AAPL", market="US", close=200.0)
    assert book.context.sector is None
    assert book.context.sector_gap == "unsupported_market"


def test_a_symbol_held_in_both_markets_keeps_the_actionable_state() -> None:
    # The TW leg is the one that would turn the cap on, so the sentence that
    # names the action is the true one here.
    summary = _summary(
        _position(1, "2330", market="TW"),
        _position(2, "2330", market="US", currency="USD", fx_to_twd="31"),
    )
    book = build_book_context(summary, symbol="2330", close=600.0)
    assert book.context.sector_gap == "unfiled"


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
