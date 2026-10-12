"""F-9a: ``check_currency`` is public, shared, and agrees with the position-side rule.

Design point (iv) and constraint C-5: ``app.data`` takes the expected currency
as a parameter (it never imports ``app.positions``), so the one thing to pin is
that injecting ``MARKET_CURRENCY[market]`` makes the bar check say exactly what
:func:`app.positions.models.currency_matches_market` says.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data import quality
from app.data.interface import Market, PriceBar
from app.data.quality import QualityIssueType, check_currency, check_price_bars
from app.positions.models import MARKET_CURRENCY, currency_matches_market
from tests.import_graph import imported_modules

DATA_ROOT = Path(__file__).resolve().parents[1] / "app" / "data"
_AS_OF = datetime(2024, 1, 2, 14, 0, tzinfo=UTC)
#: Includes near misses (case, whitespace) that must not be folded into a match.
CURRENCIES = ["TWD", "USD", "GBP", "JPY", "usd", "twd", " USD", "USD "]


def _bar(market: Market, currency: str, day: int = 2) -> PriceBar:
    return PriceBar(
        symbol="X",
        market=market,
        date=date(2024, 1, day),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        currency=currency,
        as_of=_AS_OF,
        source="stub",
    )


@pytest.mark.parametrize("market", sorted(MARKET_CURRENCY))
@pytest.mark.parametrize("currency", CURRENCIES)
def test_check_currency_is_equivalent_to_currency_matches_market(
    market: Market, currency: str
) -> None:
    issues = check_currency([_bar(market, currency)], MARKET_CURRENCY[market])
    assert (issues == []) is currency_matches_market(market, currency)


def test_equivalence_covers_both_outcomes_for_every_market() -> None:
    for market in MARKET_CURRENCY:
        outcomes = {currency_matches_market(market, currency) for currency in CURRENCIES}
        assert outcomes == {True, False}


def test_no_expected_currency_checks_nothing() -> None:
    assert check_currency([_bar("TW", "USD")], None) == []


def test_one_issue_per_differing_bar() -> None:
    bars = [_bar("TW", "TWD", 2), _bar("TW", "USD", 3), _bar("TW", "GBP", 4)]
    issues = check_currency(bars, "TWD")
    assert [issue.issue_type for issue in issues] == [QualityIssueType.CURRENCY_MISMATCH] * 2
    assert [issue.date for issue in issues] == [date(2024, 1, 3), date(2024, 1, 4)]


def test_check_price_bars_delegates_to_check_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, str | None]] = []

    def spy(bars: list[PriceBar], expected: str | None) -> list[quality.QualityIssue]:
        calls.append((len(bars), expected))
        return []

    monkeypatch.setattr(quality, "check_currency", spy)
    bars = [_bar("TW", "USD")]
    issues = check_price_bars(bars, expected_currency="TWD", reference_now=_AS_OF)
    assert calls == [(1, "TWD")]
    assert issues == []


def test_check_price_bars_reports_what_check_currency_reports() -> None:
    bars = [_bar("US", "USD", 2), _bar("US", "GBP", 3)]
    via_all = [
        issue
        for issue in check_price_bars(bars, expected_currency="USD", reference_now=_AS_OF)
        if issue.issue_type is QualityIssueType.CURRENCY_MISMATCH
    ]
    assert via_all == check_currency(bars, "USD")
    assert len(via_all) == 1


def test_the_private_name_is_gone() -> None:
    assert not hasattr(quality, "_check_currency")


def _positions_imports(names: set[str]) -> set[str]:
    return {name for name in names if name == "app.positions" or name.startswith("app.positions.")}


@pytest.mark.parametrize("name", ["quality", "service", "admission"])
def test_quality_and_service_do_not_import_positions(name: str) -> None:
    """KX-A1 / C-5: the bar check and the service take the currency as a parameter.

    Every spelling counts (``import``, ``from ... import``, aliases, relative
    forms): :func:`tests.import_graph.imported_modules` records both the
    module and ``module.name`` for each ``from`` import.
    """
    found = imported_modules(DATA_ROOT / f"{name}.py", f"app.data.{name}")
    assert _positions_imports(found) == set()


@pytest.mark.parametrize(
    "statement",
    [
        "from app.positions.models import MARKET_CURRENCY",
        "from app.positions.models import MARKET_CURRENCY as TABLE",
        "import app.positions",
        "import app.positions.models",
        "import app.positions.models as models",
        "from app import positions",
        "from app import positions as pos",
        "from ..positions import models",
        "from ..positions.models import MARKET_CURRENCY",
        "def f():\n    from app import positions\n",
    ],
)
def test_the_positions_guard_sees_every_import_spelling(tmp_path: Path, statement: str) -> None:
    source = tmp_path / "service.py"
    source.write_text(statement + "\n", encoding="utf-8")
    assert _positions_imports(imported_modules(source, "app.data.service")) != set()
