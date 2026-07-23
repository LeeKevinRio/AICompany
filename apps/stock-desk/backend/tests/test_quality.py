"""Tests for the data quality checker: every issue type is triggered, none is auto-fixed."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.data.interface import PriceBar
from app.data.quality import QualityIssueType, check_price_bars

_AS_OF = datetime(2024, 1, 2, 14, 0, tzinfo=UTC)


def _bar(**overrides: object) -> PriceBar:
    defaults: dict[str, object] = {
        "symbol": "2330",
        "market": "TW",
        "date": date(2024, 1, 2),
        "open": Decimal("594.00"),
        "high": Decimal("598.00"),
        "low": Decimal("590.00"),
        "close": Decimal("594.00"),
        "volume": 1000,
        "currency": "TWD",
        "as_of": _AS_OF,
        "source": "twse",
    }
    defaults.update(overrides)
    return PriceBar.model_validate(defaults)


def test_no_issues_for_clean_bars() -> None:
    bars = [_bar(date=date(2024, 1, 1)), _bar(date=date(2024, 1, 2))]
    issues = check_price_bars(bars, expected_currency="TWD", reference_now=_AS_OF)
    assert issues == []


def test_detects_duplicate_row() -> None:
    bars = [_bar(date=date(2024, 1, 2)), _bar(date=date(2024, 1, 2))]
    issues = check_price_bars(bars, reference_now=_AS_OF)
    types = [issue.issue_type for issue in issues]
    assert QualityIssueType.DUPLICATE_ROW in types


def test_detects_future_date() -> None:
    future = _AS_OF.date() + timedelta(days=30)
    bars = [_bar(date=future)]
    issues = check_price_bars(bars, reference_now=_AS_OF)
    assert any(issue.issue_type is QualityIssueType.FUTURE_DATE for issue in issues)


def test_detects_currency_mismatch() -> None:
    bars = [_bar(currency="USD")]
    issues = check_price_bars(bars, expected_currency="TWD", reference_now=_AS_OF)
    assert any(issue.issue_type is QualityIssueType.CURRENCY_MISMATCH for issue in issues)


def test_detects_ohlc_high_below_low() -> None:
    bars = [
        _bar(high=Decimal("100"), low=Decimal("200"), open=Decimal("150"), close=Decimal("150"))
    ]
    issues = check_price_bars(bars, reference_now=_AS_OF)
    assert any(issue.issue_type is QualityIssueType.OHLC_INVALID for issue in issues)


def test_detects_ohlc_open_above_high() -> None:
    bars = [_bar(high=Decimal("100"), low=Decimal("90"), open=Decimal("150"), close=Decimal("95"))]
    issues = check_price_bars(bars, reference_now=_AS_OF)
    assert any(issue.issue_type is QualityIssueType.OHLC_INVALID for issue in issues)


def test_detects_missing_trading_day() -> None:
    bars = [_bar(date=date(2024, 1, 2))]
    calendar = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    issues = check_price_bars(bars, trading_calendar=calendar, reference_now=_AS_OF)
    missing = [
        issue for issue in issues if issue.issue_type is QualityIssueType.MISSING_TRADING_DAY
    ]
    assert {issue.date for issue in missing} == {date(2024, 1, 3), date(2024, 1, 4)}


def test_quality_checks_never_mutate_input_bars() -> None:
    bars = [_bar(date=date(2024, 1, 2)), _bar(date=date(2024, 1, 2))]
    before = list(bars)
    check_price_bars(bars, reference_now=_AS_OF)
    assert bars == before
