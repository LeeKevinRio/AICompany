"""F-9b0 commit 0-2: ``classify_currency``, the one W-c / W-c' split (ADR-0024 D-2 (1), D-5).

Pinned: the three outcomes, ``mismatch`` over ``missing``, exact comparison
(``usd`` is a mismatch), and two equivalences -- with ``check_currency`` (its
"differs" set is mismatch plus missing) and with the position-side rule
``currency_matches_market`` (C-5). The KX-A1 import guard for ``quality`` and
``service`` lives in ``test_f9a_check_currency.py`` and stays green.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import product

import pytest

from app.data.interface import Market, PriceBar
from app.data.quality import check_currency, classify_currency
from app.positions.models import MARKET_CURRENCY, currency_matches_market

_AS_OF = datetime(2024, 1, 2, 14, 0, tzinfo=UTC)
#: Blank declarations: what an adapter that reads the upstream value verbatim
#: (F-9c) would hand over when the upstream says nothing.
BLANKS = ["", " ", "  ", "\t"]
#: Non-blank values, including near misses that must never fold into a match.
DECLARED = ["TWD", "USD", "GBP", "usd", "twd", " USD", "USD ", "Usd"]
VALUES = DECLARED + BLANKS


def _bar(currency: str, day: int = 2, market: Market = "US") -> PriceBar:
    bar = PriceBar(
        symbol="X",
        market=market,
        date=date(2024, 1, day),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        currency="USD",
        as_of=_AS_OF,
        source="stub",
    )
    # ``PriceBar`` refuses a blank currency today; ``model_copy`` skips
    # validation so the blank case F-9c will produce can be classified now.
    return bar.model_copy(update={"currency": currency})


def test_an_empty_series_is_ok() -> None:
    assert classify_currency([], "USD") == "ok"


def test_matching_bars_are_ok() -> None:
    assert classify_currency([_bar("USD", 2), _bar("USD", 3)], "USD") == "ok"


@pytest.mark.parametrize("value", ["usd", "GBP", "TWD", " USD", "USD ", "Usd"])
def test_a_different_declaration_is_mismatch_without_case_folding(value: str) -> None:
    assert classify_currency([_bar(value)], "USD") == "mismatch"


@pytest.mark.parametrize("value", BLANKS)
def test_a_blank_declaration_is_missing(value: str) -> None:
    assert classify_currency([_bar(value)], "USD") == "missing"


@pytest.mark.parametrize("order", ["mismatch_first", "missing_first"])
def test_mismatch_wins_over_missing_in_either_order(order: str) -> None:
    pair = [_bar("GBP", 2), _bar("", 3)]
    bars = pair if order == "mismatch_first" else list(reversed(pair))
    assert classify_currency([_bar("USD", 1), *bars], "USD") == "mismatch"


def test_missing_among_matching_bars_is_missing() -> None:
    assert classify_currency([_bar("USD", 2), _bar("  ", 3), _bar("USD", 4)], "USD") == "missing"


@pytest.mark.parametrize("expected", ["TWD", "USD"])
@pytest.mark.parametrize("value", VALUES)
def test_one_bar_differs_exactly_when_it_is_mismatch_or_missing(expected: str, value: str) -> None:
    """``check_currency``'s "differs" equals mismatch ∪ missing, bar by bar."""
    verdict = classify_currency([_bar(value)], expected)
    assert (check_currency([_bar(value)], expected) != []) is (verdict in {"mismatch", "missing"})


@pytest.mark.parametrize("expected", ["TWD", "USD"])
@pytest.mark.parametrize("values", list(product(["USD", "TWD", "usd", ""], repeat=3)))
def test_a_series_differs_exactly_when_it_is_not_ok(
    expected: str, values: tuple[str, str, str]
) -> None:
    bars = [_bar(value, day) for day, value in enumerate(values, start=2)]
    issues = check_currency(bars, expected)
    verdict = classify_currency(bars, expected)
    assert (issues != []) is (verdict != "ok")
    # The verdict is determined by which kinds of difference the issues hold.
    differing = {bar.currency for bar in bars if bar.currency != expected}
    if any(value.strip() for value in differing):
        assert verdict == "mismatch"
    elif differing:
        assert verdict == "missing"
    else:
        assert verdict == "ok"
    assert len(issues) == sum(bar.currency != expected for bar in bars)


@pytest.mark.parametrize("market", sorted(MARKET_CURRENCY))
@pytest.mark.parametrize("value", VALUES)
def test_ok_is_equivalent_to_currency_matches_market(market: Market, value: str) -> None:
    """C-5: injecting ``MARKET_CURRENCY[market]`` agrees with the position-side rule."""
    verdict = classify_currency([_bar(value, market=market)], MARKET_CURRENCY[market])
    assert (verdict == "ok") is currency_matches_market(market, value)


def test_the_equivalence_covers_every_outcome_for_every_market() -> None:
    for market, expected in MARKET_CURRENCY.items():
        outcomes = {classify_currency([_bar(v, market=market)], expected) for v in VALUES}  # type: ignore[arg-type]
        assert outcomes == {"ok", "mismatch", "missing"}
