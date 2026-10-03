"""ADR-0016 (close-only D1): the day-over-day change screen, F1-F8 and D-5.

T-1 (table-driven fail-closed conditions and boundaries) and T-6 (import graph,
``.change`` grep). Every row goes through the real ``PositionValuator`` so the
basis is exactly what ``_resolve_price`` read out of one ``ProviderResult``.
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.portfolio.price_change import (
    ADJUSTED_SOURCE_SUFFIX,
    PCT_QUANTUM,
    SHOW_WHEN_COVERAGE_UNKNOWN,
    TW_DAILY_PRICE_LIMIT_PCT,
    TW_DAILY_PRICE_LIMIT_TOLERANCE_PCT,
    ChangeScreen,
    CoverageNotYetJudged,
    CoverageQuery,
    ExDateCoverage,
    PriceChange,
    change_pct,
)
from app.portfolio.valuation import (
    ChangeBasis,
    PositionValuation,
    PositionValuator,
    PriceInfo,
    PriceService,
    Valuation,
)
from app.positions.models import Position
from tests.api_helpers import UnavailableFxProvider
from tests.import_graph import offenders, reachable_app_modules

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=UTC)  # Monday
MON = date(2026, 10, 5)
FRI = date(2026, 10, 2)
THU = date(2026, 10, 1)
SAT = date(2026, 10, 3)

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def _bar(day: date, close: str, *, source: str = "twse", market: Market = "TW") -> PriceBar:
    return PriceBar(
        symbol="2330",
        market=market,
        date=day,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1,
        currency="TWD" if market == "TW" else "USD",
        as_of=NOW,
        source=source,
    )


class _Prices(PriceService):
    """Answers every symbol with ``bars``, counting calls."""

    def __init__(self, bars: list[PriceBar]) -> None:
        self.bars = bars
        self.calls = 0
        self.cached_calls = 0

    def _result(self, start: date, end: date) -> ProviderResult:
        window = [bar for bar in self.bars if start <= bar.date <= end]
        if not window:
            return ProviderResult(bars=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="none")
        return ProviderResult(bars=window, status=DataStatus.FRESH, as_of=NOW, source="twse")

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        self.calls += 1
        return self._result(start, end)

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        self.cached_calls += 1
        return self._result(start, end)


@dataclass
class _ExDates:
    events: dict[tuple[str, Market], set[date]] = field(default_factory=dict)
    calls: int = 0

    def ex_dates_between(
        self, keys: Collection[tuple[str, Market]], start: date, end: date
    ) -> Mapping[tuple[str, Market], frozenset[date]]:
        self.calls += 1
        return {
            key: frozenset(day for day in days if start <= day <= end)
            for key, days in self.events.items()
            if key in keys
        }


@dataclass
class _Calendar:
    days: dict[Market, set[date]] = field(default_factory=dict)
    calls: list[Market] = field(default_factory=list)

    def market_trading_days(self, market: Market, start: date, end: date) -> frozenset[date]:
        self.calls.append(market)
        return frozenset(day for day in self.days.get(market, set()) if start <= day <= end)


class _Raising:
    def ex_dates_between(
        self, keys: Collection[tuple[str, Market]], start: date, end: date
    ) -> Mapping[tuple[str, Market], frozenset[date]]:
        raise RuntimeError("database is locked")


@dataclass
class _FixedCoverage:
    verdict: ExDateCoverage
    asked: list[CoverageQuery] = field(default_factory=list)

    def coverage(self, queries: Sequence[CoverageQuery]) -> Mapping[CoverageQuery, ExDateCoverage]:
        self.asked.extend(queries)
        return {query: self.verdict for query in queries}


def _position(*, market: Market = "TW", symbol: str = "2330", pid: int = 1) -> Position:
    return Position(
        id=pid,
        symbol=symbol,
        market=market,
        quantity=Decimal("1000"),
        avg_cost=Decimal("500"),
        currency="TWD" if market == "TW" else "USD",
        opened_at=date(2026, 1, 5),
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _valued(bars: list[PriceBar], *, market: Market = "TW") -> tuple[Position, PositionValuation]:
    position = _position(market=market)
    valuator = PositionValuator(
        market_services={market: _Prices(bars)},
        fx_provider=UnavailableFxProvider(),
        clock=lambda: NOW,
    )
    return position, valuator.value_position(position)


def _screen(
    rows: list[tuple[Position, PositionValuation]],
    *,
    ex_dates: _ExDates | None = None,
    calendar: _Calendar | None = None,
) -> list[PriceChange | None]:
    screen = ChangeScreen(ex_dates=ex_dates or _ExDates(), calendar=calendar or _Calendar())
    return screen.screen(rows)


def _one(
    bars: list[PriceBar],
    *,
    market: Market = "TW",
    ex_dates: _ExDates | None = None,
    calendar: _Calendar | None = None,
) -> PriceChange | None:
    row = _valued(bars, market=market)
    return _screen([row], ex_dates=ex_dates, calendar=calendar)[0]


# --- the shown case, and its serialization ------------------------------------


def test_monday_change_is_against_friday_close_and_serializes_as_strings() -> None:
    calendar = _Calendar(days={"TW": {THU, FRI, MON}})
    change = _one([_bar(THU, "1060.00"), _bar(FRI, "1072.00"), _bar(MON, "1085.25")],
                  calendar=calendar)  # fmt: skip
    assert change is not None
    assert change.basis_date == FRI
    assert change.basis_kind == "close"
    assert change.basis_price == Decimal("1072.00")
    assert change.model_dump(mode="json") == {
        "pct": "1.2360",
        "basis_kind": "close",
        "basis_date": "2026-10-02",
        "basis_price": "1072.00",
    }


def test_empty_calendar_does_not_withhold() -> None:
    assert _one([_bar(FRI, "100"), _bar(MON, "101")], calendar=_Calendar()) is not None


def test_change_pct_quantizes_half_up_to_four_places() -> None:
    assert PCT_QUANTUM == Decimal("0.0001")
    # 1/3 % -> 0.3333; 2/3 % -> 0.6667
    assert change_pct(Decimal("300.01"), Decimal("300")) == Decimal("0.0033")
    assert change_pct(Decimal("100.66665"), Decimal("100")) == Decimal("0.6667")
    assert change_pct(Decimal("100.00005"), Decimal("100")) == Decimal("0.0001")  # half up
    assert change_pct(Decimal("99.99995"), Decimal("100")) == Decimal("-0.0001")
    assert change_pct(Decimal("90"), Decimal("100")) == Decimal("-10.0000")


def test_change_pct_never_returns_negative_zero() -> None:
    pct = change_pct(Decimal("99.999999"), Decimal("100"))
    assert str(pct) == "0.0000"
    assert str(change_pct(Decimal("100"), Decimal("100"))) == "0.0000"


# --- F1-F8: each condition withholds -----------------------------------------


@pytest.mark.parametrize(
    ("label", "bars", "market"),
    [
        ("F1 no bars at all", [], "TW"),
        ("F2 a single bar in the window", [_bar(MON, "100")], "TW"),
        ("F3 sources differ", [_bar(FRI, "100", source="tpex"), _bar(MON, "101")], "TW"),
        (
            "F3 back-adjusted latest",
            [_bar(FRI, "100"), _bar(MON, "101", source="twse+divadj")],
            "TW",
        ),
        (
            "F3 back-adjusted both",
            [_bar(FRI, "100", source="twse+divadj"), _bar(MON, "101", source="twse+divadj")],
            "TW",
        ),
        ("F4 zero basis", [_bar(FRI, "0"), _bar(MON, "101")], "TW"),
        ("F7 TW above +11%", [_bar(FRI, "100"), _bar(MON, "111.01")], "TW"),
        ("F7 TW below -11%", [_bar(FRI, "100"), _bar(MON, "88.99")], "TW"),
    ],
)
def test_per_row_conditions_withhold(label: str, bars: list[PriceBar], market: Market) -> None:
    assert _one(bars, market=market) is None, label


def test_f1_market_without_a_price_service_withholds() -> None:
    position = _position(market="US", symbol="AAPL")
    valuator = PositionValuator(
        market_services={}, fx_provider=UnavailableFxProvider(), clock=lambda: NOW
    )
    assert _screen([(position, valuator.value_position(position))]) == [None]


def test_f1_non_positive_price_withholds() -> None:
    assert _one([_bar(FRI, "100"), _bar(MON, "0")]) is None


def test_f4_basis_not_before_price_withholds() -> None:
    latest = _bar(MON, "101")
    same_day = _bar(MON, "100")
    position, valued = _valued([_bar(FRI, "100"), latest])
    forged = PositionValuation(
        valuation=valued.valuation,
        cost_twd=valued.cost_twd,
        market_value_twd=valued.market_value_twd,
        change_basis=ChangeBasis(latest=latest, previous=same_day),
    )
    assert _screen([(position, forged)]) == [None]


def test_f5_series_missing_an_observed_session_withholds() -> None:
    calendar = _Calendar(days={"TW": {THU, FRI, MON}})
    # The series skipped Friday, which the market traded.
    assert _one([_bar(THU, "100"), _bar(MON, "101")], calendar=calendar) is None


@pytest.mark.parametrize(
    ("ex_date", "shown"),
    [
        (FRI, True),  # ex_date == basis_date: the basis already trades ex.
        (SAT, False),  # strictly inside the window
        (MON, False),  # ex_date == price_date
        (THU, True),  # before the window
    ],
)
def test_f6_known_ex_date_window(ex_date: date, shown: bool) -> None:
    ex_dates = _ExDates(events={("2330", "TW"): {ex_date}})
    change = _one([_bar(FRI, "100"), _bar(MON, "99")], ex_dates=ex_dates)
    assert (change is not None) is shown


def test_f6_matches_the_normalized_symbol() -> None:
    position = _position(symbol=" 2330 ")
    valuator = PositionValuator(
        market_services={"TW": _Prices([_bar(FRI, "100"), _bar(MON, "99")])},
        fx_provider=UnavailableFxProvider(),
        clock=lambda: NOW,
    )
    ex_dates = _ExDates(events={("2330", "TW"): {MON}})
    assert _screen([(position, valuator.value_position(position))], ex_dates=ex_dates) == [None]


@pytest.mark.parametrize(
    ("close", "market", "shown"),
    [
        ("111", "TW", True),  # exactly +11%: not *beyond* the threshold
        ("89", "TW", True),  # exactly -11%
        ("111.00004", "TW", True),  # +11.00004% quantizes to 11.0000: not beyond
        ("111.0001", "TW", False),  # +11.0001%
        ("88.9999", "TW", False),  # -11.0001%
        ("120", "US", True),  # F7 is TW only
        ("75", "US", True),
    ],
)
def test_f7_threshold_boundary(close: str, market: Market, shown: bool) -> None:
    change = _one([_bar(FRI, "100", market=market), _bar(MON, close, market=market)],
                  market=market)  # fmt: skip
    assert (change is not None) is shown


def test_f7_constants_mirror_the_sector_insurance_without_importing_it() -> None:
    from app.sectors.definition import UniverseRules

    rules = UniverseRules()
    assert TW_DAILY_PRICE_LIMIT_PCT == Decimal(str(rules.daily_price_limit)) * 100
    assert (
        TW_DAILY_PRICE_LIMIT_TOLERANCE_PCT == Decimal(str(rules.daily_price_limit_tolerance)) * 100
    )


def test_f3_suffix_is_the_adjusters_label() -> None:
    from app.dividends.adjust import ADJUSTED_SOURCE_SUFFIX as ADJUST_SUFFIX

    assert ADJUSTED_SOURCE_SUFFIX == ADJUST_SUFFIX


def test_intraday_priced_row_is_withheld_until_d7() -> None:
    position, valued = _valued([_bar(FRI, "100"), _bar(MON, "101")])
    assert valued.valuation.price is not None
    intraday_price = valued.valuation.price.model_copy(update={"price_kind": "intraday_quote"})
    forged = PositionValuation(
        valuation=valued.valuation.model_copy(update={"price": intraday_price}),
        cost_twd=valued.cost_twd,
        market_value_twd=valued.market_value_twd,
        change_basis=valued.change_basis,
    )
    assert _screen([(position, forged)]) == [None]


def test_a_price_not_read_from_the_basis_bars_is_withheld() -> None:
    position, valued = _valued([_bar(FRI, "100"), _bar(MON, "101")])
    assert valued.valuation.price is not None
    other = valued.valuation.price.model_copy(update={"value": Decimal("102")})
    forged = PositionValuation(
        valuation=valued.valuation.model_copy(update={"price": other}),
        cost_twd=valued.cost_twd,
        market_value_twd=valued.market_value_twd,
        change_basis=valued.change_basis,
    )
    assert _screen([(position, forged)]) == [None]


class _RaisingCalendar:
    def market_trading_days(self, market: Market, start: date, end: date) -> frozenset[date]:
        raise RuntimeError("calendar read failed")


class _RaisingCoverage:
    def coverage(self, queries: Sequence[CoverageQuery]) -> Mapping[CoverageQuery, ExDateCoverage]:
        raise RuntimeError("coverage rule failed")


def _screen_failures(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == "app.portfolio.price_change" and record.levelno >= logging.ERROR
    ]


@pytest.mark.parametrize(
    "screen",
    [
        pytest.param(ChangeScreen(ex_dates=_Raising(), calendar=_Calendar()), id="ex-date lookup"),
        pytest.param(ChangeScreen(ex_dates=_ExDates(), calendar=_RaisingCalendar()), id="calendar"),
        pytest.param(
            ChangeScreen(
                ex_dates=_ExDates(), calendar=_Calendar(), coverage_rule=_RaisingCoverage()
            ),
            id="D-5 coverage rule",
        ),
    ],
)
@pytest.mark.allow_price_change_error
def test_a_failing_dependency_withholds_the_book_without_raising(
    screen: ChangeScreen, caplog: pytest.LogCaptureFixture
) -> None:
    rows = [_valued([_bar(FRI, "100"), _bar(MON, "101")]) for _ in range(2)]
    # Without the failure both rows would be shown.
    healthy = ChangeScreen(ex_dates=_ExDates(), calendar=_Calendar())
    assert all(change is not None for change in healthy.screen(rows))
    with caplog.at_level(logging.ERROR, logger="app.portfolio.price_change"):
        assert screen.screen(rows) == [None, None]
    failures = _screen_failures(caplog)
    assert len(failures) == 1
    assert failures[0].exc_info is not None
    assert failures[0].exc_info[0] is RuntimeError


def test_insufficient_fx_does_not_withhold_the_price_change() -> None:
    # A US holding with no FX rate is insufficient_data for TWD totals, but its
    # price and the previous close are both known and in the same currency.
    position, valued = _valued(
        [_bar(FRI, "100", market="US"), _bar(MON, "102", market="US")], market="US"
    )
    assert valued.valuation.status == "insufficient_data"
    change = _screen([(position, valued)])[0]
    assert change is not None
    assert change.pct == Decimal("2.0000")


# --- K-7: one ex-date read per book, one calendar read per market --------------


def test_lookups_are_batched_per_book() -> None:
    bars = [_bar(FRI, "100"), _bar(MON, "101")]
    us_bars = [_bar(FRI, "100", market="US"), _bar(MON, "101", market="US")]
    rows = [_valued(bars) for _ in range(5)] + [_valued(us_bars, market="US") for _ in range(3)]
    ex_dates = _ExDates()
    calendar = _Calendar()
    changes = _screen(rows, ex_dates=ex_dates, calendar=calendar)
    assert all(change is not None for change in changes)
    assert ex_dates.calls == 1
    assert sorted(calendar.calls) == ["TW", "US"]


def test_no_lookup_when_nothing_survives_the_row_checks() -> None:
    ex_dates = _ExDates()
    calendar = _Calendar()
    assert _screen([_valued([_bar(MON, "100")])], ex_dates=ex_dates, calendar=calendar) == [None]
    assert ex_dates.calls == 0
    assert calendar.calls == []


# --- D-5: coverage stub and its conservative behaviour -------------------------


def test_coverage_stub_answers_unknown_for_every_row() -> None:
    query = CoverageQuery(
        symbol="2330", market="TW", latest_source="twse", basis_date=FRI, price_date=MON
    )
    assert CoverageNotYetJudged().coverage([query]) == {query: "unknown"}


def test_unknown_coverage_still_shows_the_change() -> None:
    # D-5: coverage unknown -> shown as usual; the residual risk is D-6's
    # disclosure, not this screen's. Flipping the policy is a decision, not a fix.
    assert SHOW_WHEN_COVERAGE_UNKNOWN is True
    row = _valued([_bar(FRI, "100"), _bar(MON, "101")])
    rule = _FixedCoverage("unknown")
    screen = ChangeScreen(ex_dates=_ExDates(), calendar=_Calendar(), coverage_rule=rule)
    assert screen.screen([row])[0] is not None
    assert rule.asked == [
        CoverageQuery(
            symbol="2330", market="TW", latest_source="twse", basis_date=FRI, price_date=MON
        )
    ]


def test_known_coverage_shows_the_change() -> None:
    row = _valued([_bar(FRI, "100"), _bar(MON, "101")])
    screen = ChangeScreen(
        ex_dates=_ExDates(), calendar=_Calendar(), coverage_rule=_FixedCoverage("known")
    )
    assert screen.screen([row])[0] is not None


def test_known_ex_date_wins_over_any_coverage_verdict() -> None:
    row = _valued([_bar(FRI, "100"), _bar(MON, "95")])
    rule = _FixedCoverage("known")
    screen = ChangeScreen(
        ex_dates=_ExDates(events={("2330", "TW"): {MON}}),
        calendar=_Calendar(),
        coverage_rule=rule,
    )
    assert screen.screen([row]) == [None]
    assert rule.asked == []


def test_default_screen_uses_the_stub() -> None:
    screen = ChangeScreen(ex_dates=_ExDates(), calendar=_Calendar())
    assert isinstance(screen.coverage_rule, CoverageNotYetJudged)


# --- K-1 / K-8: the public valuation schema --------------------------------------


def test_valuation_and_price_info_carry_no_change_field() -> None:
    forbidden = re.compile(r"change|basis|pct|prev", re.IGNORECASE)
    assert not [name for name in Valuation.model_fields if forbidden.search(name)]
    assert not [name for name in PriceInfo.model_fields if forbidden.search(name)]
    assert PriceInfo.model_fields["price_kind"].default == "daily_close"


def test_change_basis_is_not_serialized() -> None:
    _, valued = _valued([_bar(FRI, "100"), _bar(MON, "101")])
    assert valued.change_basis is not None
    assert "change_basis" not in valued.valuation.model_dump(mode="json")


# --- T-6: import graph (K-3) and nobody downstream reads `.change` (K-4) -----------


@pytest.mark.parametrize(
    "forbidden", ["app.dividends.adjust", "app.sectors", "app.data.market_panel"]
)
def test_price_change_import_graph(forbidden: str) -> None:
    reachable = reachable_app_modules(("app.portfolio.price_change",))
    assert "app.portfolio.price_change" in reachable
    assert offenders(reachable, forbidden) == []


#: Packages that must never read the change column (K-4). ``limits`` lives in
#: ``app/advice`` (``limits.py`` / ``book_limits.py``) and is covered by it.
_NO_CHANGE_READERS = ("advice", "alerts", "kelly", "playbook", "signals")
_CHANGE_READ = re.compile(r"""\.change\b|\[\s*["']change["']\s*\]|["']change["']\s*\)""")


def _reader_sources() -> list[Path]:
    files = [path for package in _NO_CHANGE_READERS for path in (APP_ROOT / package).rglob("*.py")]
    files += [path for path in APP_ROOT.rglob("*limit*.py") if path not in files]
    return sorted(files)


def test_reader_scan_covers_the_limits_modules() -> None:
    names = {path.name for path in _reader_sources()}
    assert {"limits.py", "book_limits.py"} <= names


def test_no_downstream_module_reads_the_change_column() -> None:
    hits = [
        f"{path.relative_to(APP_ROOT)}:{number}"
        for path in _reader_sources()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _CHANGE_READ.search(line)
    ]
    assert hits == []


def test_only_the_summary_endpoint_injects_a_change_screen() -> None:
    """Every ``build_summary`` call outside ``portfolio_summary`` passes no screen (D-3)."""
    injecting: list[str] = []
    plain: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef):
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "build_summary"
                ):
                    where = f"{path.relative_to(APP_ROOT)}::{func.name}"
                    keywords = {keyword.arg for keyword in node.keywords}
                    (injecting if "change_screen" in keywords else plain).append(where)
    assert injecting == ["api/portfolio.py::portfolio_summary"]
    assert sorted(plain) == [
        "alerts/snapshot.py::build_snapshot",
        "api/advice.py::get_advice",
        "api/portfolio.py::portfolio_limits",
        "api/settings.py::_review_reported_net_worth",
    ]
