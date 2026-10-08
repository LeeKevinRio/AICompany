"""F-1b: an FX rate that is zero, negative or not finite is no rate.

Task F-1b (``work/dispatch/2026-10-07-*F-1b*.md``). One definition,
:func:`app.data.price_guard.usable_rate`, is applied where a rate reaches a
figure: the portfolio valuator's ``_lookup_fx`` (``fx_now`` and ``fx_open``
alike), the advice book's ``_resolve_fx`` (D5) and its scenario-2a log (KF-15).

An unusable latest rate is valued exactly like no rate at all (risk (a), D3):
the same ``UNAVAILABLE`` ``FxInfo``, the existing ``fx_now`` / ``fx_open``
tokens, no new token, and the earlier rates in the window are never fallen
back on (D4). That ``FxInfo`` carries no source note, whichever source answered:
no rate was applied, so there is no methodology to disclose (F1b-R10, revised
D3). The test names carry the KF / R / F1b-C numbers of the task.
"""

from __future__ import annotations

import ast
import inspect
import logging
import math
import re
import textwrap
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from app.advice import book as book_module
from app.advice.book import (
    FX_APPLIED_NOTE,
    FX_UNAVAILABLE_NOTE,
    NO_FX_QUOTE_NOTE,
    FxQuote,
    build_book_context,
)
from app.advice.limits import RiskBudget
from app.alerts.snapshot import build_snapshot
from app.api.deps import get_cached_valuator, get_fx_provider, get_market_resolver, get_valuator
from app.data import price_guard
from app.data.interface import DataStatus, Market
from app.data.price_guard import usable_price, usable_rate
from app.data.providers.fx import FxRate, FxRateLadder, FxRateProvider, FxRateResult
from app.main import app
from app.portfolio import valuation as valuation_module
from app.portfolio.summary import build_summary
from app.portfolio.valuation import FxInfo, PositionValuator, PriceMode
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore
from app.services.fx_notes import source_note
from app.settings.models import NetWorthSettings
from tests.advice_helpers import book_summary
from tests.api_helpers import FakePriceService, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.import_graph import APP_ROOT, imported_modules

#: The bad rates of the test matrix. 0 and -1 are what a source can hand back
#: today; NaN and +/-Infinity are rejected by ``FxRate`` itself (KF-6) and are
#: injected past it, as defence in depth (see :func:`_rate`).
BAD_RATES = [
    pytest.param(Decimal("0"), id="zero"),
    pytest.param(Decimal("-1"), id="negative"),
    pytest.param(Decimal("NaN"), id="nan"),
    pytest.param(Decimal("Infinity"), id="inf"),
    pytest.param(Decimal("-Infinity"), id="minus-inf"),
]
#: The rates a source can hand back through a validated ``FxRate`` (endpoints).
WIRE_BAD_RATES = [
    pytest.param(Decimal("0"), id="zero"),
    pytest.param(Decimal("-1"), id="negative"),
]
MODES: list[PriceMode] = ["live", "cache_only"]

PAIR = "USDTWD"
SYMBOL = "AAPL"
TWD_SYMBOL = "2330"
SOURCE = "f1b_fx"
BANK = "bank_of_taiwan"
YAHOO = "yfinance_fx"
#: A degradation sentence on a *successful* answer, so "``reason`` is passed
#: through" is an observation rather than a ``None`` default.
REASON = "source degraded for this test"
VALUATION_LOGGER = "app.portfolio.valuation"
BOOK_LOGGER = "app.advice.book"
#: The R-3 fixed string (trigger 1); grep target, pinned whole.
DROPPED_HEAD = "unusable fx rate dropped from valuation: "
#: The PR-RK2 2a line (trigger 0, F1b-C1).
UNAPPLIED_HEAD = "fx quote unavailable while valued holdings used a rate: "
APPLIED_HEAD = FX_APPLIED_NOTE.split("{", 1)[0]

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
OPENED = date(2024, 1, 2)
GOOD = Decimal("31.5")
EARLIER_GOOD = Decimal("30.5")
NOW = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
NET_WORTH = 99_000_000.0


def _rate(day: date, value: Decimal, source: str = SOURCE) -> FxRate:
    """One posted rate; a non-finite one is built without validation.

    ``FxRate`` rejects NaN and Infinity (KF-6, pinned below), so those reach a
    consumer only past the model -- a future cache read, a constructed object.
    ``model_construct`` stands in for that path: the guard must hold anyway.
    """
    if value.is_finite():
        return FxRate(pair=PAIR, date=day, rate=value, as_of=NOW, source=source)
    return FxRate.model_construct(pair=PAIR, date=day, rate=value, as_of=NOW, source=source)


class _DatedFx(FxRateProvider):
    """Answers with the rates it holds inside the asked window, else declines.

    ``past_end`` makes it misbehave the one way trigger 0 has to tolerate: it
    also returns its rates *after* the window's end (F1b-C1 (ii)).
    """

    source_id: ClassVar[str] = SOURCE

    def __init__(
        self,
        days: Mapping[date, Decimal],
        *,
        source: str = SOURCE,
        reason: str | None = REASON,
        past_end: bool = False,
    ) -> None:
        self._days = dict(days)
        self._source = source
        self._reason = reason
        self._past_end = past_end
        self.asks: list[tuple[date, date]] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.asks.append((start, end))
        rates = [
            _rate(day, value, self._source)
            for day, value in sorted(self._days.items())
            if start <= day and (self._past_end or day <= end)
        ]
        status = DataStatus.FRESH if rates else DataStatus.UNAVAILABLE
        return FxRateResult(
            rates=rates, status=status, as_of=NOW, source=self._source, reason=self._reason
        )


def _no_rate_info(source: str = SOURCE, reason: str | None = REASON) -> FxInfo:
    """What ``_lookup_fx``'s "no rate" branch builds for this provider (revised D3).

    ``source_note`` is empty for every source (F1b-R10): the source and reason
    are passed through, the unused rate's methodology sentence is not.
    """
    return FxInfo(
        pair=PAIR,
        as_of=None,
        source=source,
        data_status=DataStatus.UNAVAILABLE,
        source_note="",
        reason=reason,
    )


def _clock(today: date) -> Callable[[], datetime]:
    return lambda: datetime.combine(today, time(12), tzinfo=UTC)


def _us_service(end: date = TODAY) -> FakePriceService:
    service = FakePriceService()
    service.seed(
        SYMBOL,
        recent_bars(trending_closes(200, start=100.5), symbol=SYMBOL, market="US", end=end),
    )
    return service


def _usd(position_id: int = 1, opened_at: date | None = OPENED) -> Position:
    return Position(
        id=position_id,
        symbol=SYMBOL,
        market="US",
        quantity=Decimal(137),
        avg_cost=Decimal(150),
        currency="USD",
        opened_at=opened_at,
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _valuator(fx: FxRateProvider, mode: PriceMode = "live") -> PositionValuator:
    return PositionValuator(
        market_services={"US": _us_service()},
        fx_provider=fx,
        clock=_clock(TODAY),
        price_mode=mode,
    )


def _records(caplog: pytest.LogCaptureFixture, name: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == name]


def _dropped(day: date, rate: Decimal, source: str = SOURCE) -> str:
    return f"{DROPPED_HEAD}pair={PAIR} date={day.isoformat()} rate={rate} source={source}"


# --- KF-1 / KF-2: the one definition --------------------------------------------


TRUTH_TABLE = [
    (None, False),
    (0.0, False),
    (-0.0, False),
    (-1.0, False),
    (math.nan, False),
    (math.inf, False),
    (-math.inf, False),
    (Decimal("0"), False),
    (Decimal("-1"), False),
    (Decimal("NaN"), False),
    (Decimal("sNaN"), False),
    (Decimal("Infinity"), False),
    (Decimal("-Infinity"), False),
    (0.0001, True),
    (550.0, True),
    (Decimal("0.01"), True),
    (Decimal("550"), True),
]


@pytest.mark.parametrize(("value", "expected"), TRUTH_TABLE)
def test_kf2_usable_rate_is_the_one_definition(
    value: float | Decimal | None, expected: bool
) -> None:
    # The same 17 cases as F-1's ``usable_price`` table, with the same answers;
    # a signalling NaN must not raise.
    assert usable_rate(value) is expected
    assert usable_price(value) is expected


def test_kf1_usable_rate_is_its_own_function_over_the_shared_helper() -> None:
    assert usable_rate is not usable_price
    assert usable_rate.__name__ == "usable_rate"
    tree = ast.parse(inspect.getsource(price_guard))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("usable_price", "usable_rate"):
        called = {
            node.func.id
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert called == {"_positive_finite"}, name
        assert ast.get_docstring(functions[name]), name


def test_kf1_usable_rate_is_defined_only_in_the_guard_module() -> None:
    defining = sorted(
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if re.search(r"^\s*def usable_rate\b", path.read_text(encoding="utf-8"), re.M)
    )
    assert defining == ["data/price_guard.py"]


def test_kf1_the_guard_module_stays_a_leaf_without_cjk() -> None:
    path = APP_ROOT / "data" / "price_guard.py"
    assert imported_modules(path, "app.data.price_guard") == set()
    assert not re.search(r"[\u3000-\u9fff\uff00-\uffef]", path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("relative", "calls"),
    [("portfolio/valuation.py", 1), ("advice/book.py", 2)],
)
def test_kf1_the_consumers_ask_the_one_definition(relative: str, calls: int) -> None:
    source = (APP_ROOT / relative).read_text(encoding="utf-8")
    assert "from app.data.price_guard import" in source
    assert source.count("usable_rate(") == calls


# --- KF-6: what the model itself rejects (evidence, not a guard) ----------------


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_kf6_fx_rate_rejects_non_finite_rates(value: Decimal) -> None:
    with pytest.raises(ValidationError):
        FxRate(pair=PAIR, date=TODAY, rate=value, as_of=NOW, source=SOURCE)


@pytest.mark.parametrize("value", [Decimal(0), Decimal(-1)])
def test_kf6_fx_rate_accepts_zero_and_negative_rates(value: Decimal) -> None:
    # Why the consumers have to judge: D1 keeps the model unvalidated (C).
    assert FxRate(pair=PAIR, date=TODAY, rate=value, as_of=NOW, source=SOURCE).rate == value


# --- KF-9: no inline rate threshold beside the one definition -------------------

#: Scoped on purpose (KF-9): a whole-repo grep would hit ``win_rate`` and others.
_NO_INLINE_RATE_THRESHOLD = (
    APP_ROOT / "portfolio" / "valuation.py",
    APP_ROOT / "advice" / "book.py",
    APP_ROOT / "services" / "fx.py",
    APP_ROOT / "alerts" / "snapshot.py",
    APP_ROOT / "api" / "advice.py",
    APP_ROOT / "api" / "portfolio.py",
    APP_ROOT / "api" / "settings.py",
)
_INLINE_RATE_THRESHOLD = re.compile(
    r"rate\b[^#\n]*?(?:>|<=)\s*0(?:\.0*)?(?![\d.])"
    r"|(?<![\d.])0(?:\.0*)?\s*(?:<|>=)[^#\n]*?rate\b"
)


@pytest.mark.parametrize("path", _NO_INLINE_RATE_THRESHOLD, ids=lambda path: path.name)
def test_kf9_no_inline_rate_threshold_outside_the_one_definition(path: Path) -> None:
    hits = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if _INLINE_RATE_THRESHOLD.search(line)
    ]
    assert hits == []


def test_kf9_the_rate_pattern_would_catch_an_inline_guard() -> None:
    # Guard the guard: a regex that matches nothing proves nothing.
    for line in (
        "if fx.rate is None or fx.rate <= 0.0:",
        "if fx.rate is not None and fx.rate > 0.0:",
        "if latest.rate <= 0:",
        "ok = float(latest.rate) > 0",
        "if 0 < fx_rate:",
        "if 0.0 >= rate:",
    ):
        assert _INLINE_RATE_THRESHOLD.search(line), line
    for line in (
        "if not usable_rate(latest.rate):",
        "if fx.rate is None or not usable_rate(fx.rate):",
        'rate=f"{fx.rate:g}",',
        "fx_to_twd=rate if rate is not None else 1.0,",
    ):
        assert not _INLINE_RATE_THRESHOLD.search(line), line


# --- KF-3 / KF-4 / KF-11: the valuator ------------------------------------------


@dataclass(frozen=True)
class Where:
    """Which lookup the bad rate lands on, and what the row must then say."""

    days: Callable[[Decimal], dict[date, Decimal]]
    opened_at: date
    missing: list[str]
    bad_day: date


WHERE = [
    pytest.param(
        Where(
            # The open date is earlier and good; today is bad, three days ago good.
            days=lambda bad: {OPENED: EARLIER_GOOD, TODAY - timedelta(days=3): GOOD, TODAY: bad},
            opened_at=OPENED,
            missing=["fx_now"],
            bad_day=TODAY,
        ),
        id="fx_now",
    ),
    pytest.param(
        Where(
            days=lambda bad: {OPENED - timedelta(days=3): EARLIER_GOOD, OPENED: bad, TODAY: GOOD},
            opened_at=OPENED,
            missing=["fx_open"],
            bad_day=OPENED,
        ),
        id="fx_open",
    ),
    pytest.param(
        Where(
            # Opened today: both rates are one (pair, target) -- one lookup (memo).
            days=lambda bad: {TODAY - timedelta(days=3): GOOD, TODAY: bad},
            opened_at=TODAY,
            missing=["fx_now", "fx_open"],
            bad_day=TODAY,
        ),
        id="both-same-target",
    ),
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", BAD_RATES)
@pytest.mark.parametrize("where", WHERE)
def test_kf3_an_unusable_latest_rate_is_valued_exactly_like_no_rate(
    where: Where, bad: Decimal, mode: PriceMode, caplog: pytest.LogCaptureFixture
) -> None:
    fx = _DatedFx(where.days(bad))
    positions = [_usd(1, where.opened_at), _usd(2, where.opened_at)]
    with caplog.at_level(logging.WARNING, logger=VALUATION_LOGGER):
        rows = _valuator(fx, mode).value_all(positions)

    for row in rows:
        valuation = row.valuation
        assert valuation.status == "insufficient_data"
        # The existing tokens, exactly; no new one (KF-5).
        assert valuation.missing == where.missing
        assert valuation.pnl_original is not None  # the price was fine
        assert row.market_value_twd is None
        assert row.cost_twd is None
        assert valuation.pnl_twd is None
        assert valuation.fx is not None
        assert valuation.fx_open is not None
        for token, info in (("fx_now", valuation.fx), ("fx_open", valuation.fx_open)):
            if token in where.missing:
                # D3: the "no rate" FxInfo, field for field -- not the answer's
                # status or date, which would disclose an unused rate.
                assert info == _no_rate_info(), token
                assert info.data_status is DataStatus.UNAVAILABLE
                assert info.as_of is None
            else:
                assert info.data_status is DataStatus.FRESH, token
                assert info.as_of is not None
    # KF-11 / R-3: one line per (pair, target) per pass, the fixed head, no reason.
    messages = [record.getMessage() for record in _records(caplog, VALUATION_LOGGER)]
    assert messages == [_dropped(where.bad_day, bad)]
    assert REASON not in messages[0]
    [record] = _records(caplog, VALUATION_LOGGER)
    assert record.levelno == logging.WARNING
    # Two holdings, one pass: each (pair, target) is asked once.
    targets = {TODAY, where.opened_at}
    assert len(fx.asks) == len(targets)


@pytest.mark.parametrize("bad", BAD_RATES)
@pytest.mark.parametrize("where", WHERE)
def test_kf3_live_and_cache_only_agree_on_the_fx_outcome(where: Where, bad: Decimal) -> None:
    # The FX path does not read the price mode; this dimension is regression only.
    outcomes = []
    for mode in MODES:
        [row] = _valuator(_DatedFx(where.days(bad)), mode).value_all([_usd(1, where.opened_at)])
        valuation = row.valuation
        outcomes.append((valuation.missing, valuation.fx, valuation.fx_open, row.market_value_twd))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("bad", BAD_RATES)
def test_kf4_an_earlier_good_rate_is_not_fallen_back_on(bad: Decimal) -> None:
    # Question 3: [target-3: good, target: bad] answers what an empty window does.
    target = TODAY
    with_bad = _DatedFx({target - timedelta(days=3): EARLIER_GOOD, target: bad})
    empty = _DatedFx({})
    got = _valuator(with_bad)._lookup_fx(PAIR, target)
    reference = _valuator(empty)._lookup_fx(PAIR, target)
    assert reference == (None, _no_rate_info())
    assert got == reference


@pytest.mark.parametrize("bad", BAD_RATES)
def test_kf4_an_earlier_bad_rate_does_not_block_a_good_latest_one(
    bad: Decimal, caplog: pytest.LogCaptureFixture
) -> None:
    # The reverse case: candidates are not filtered, only the latest is judged.
    target = TODAY
    fx = _DatedFx({target - timedelta(days=3): bad, target: EARLIER_GOOD})
    with caplog.at_level(logging.WARNING, logger=VALUATION_LOGGER):
        rate, info = _valuator(fx)._lookup_fx(PAIR, target)
    assert rate == EARLIER_GOOD
    assert info.data_status is DataStatus.FRESH
    assert info.as_of == target.isoformat()
    assert _records(caplog, VALUATION_LOGGER) == []


def test_a_tiny_positive_rate_is_still_a_rate(caplog: pytest.LogCaptureFixture) -> None:
    tiny = Decimal("1e-9")
    fx = _DatedFx({OPENED: tiny, TODAY: tiny})
    with caplog.at_level(logging.WARNING, logger=VALUATION_LOGGER):
        [row] = _valuator(fx).value_all([_usd()])
    assert row.valuation.status == "ok"
    assert row.market_value_twd is not None and row.market_value_twd > 0
    assert _records(caplog, VALUATION_LOGGER) == []


def test_kf3_both_no_rate_branches_are_one_helper() -> None:
    # D3: "no rate" and "unusable rate" are built by one function, so they
    # cannot drift; ``_lookup_fx`` builds no UNAVAILABLE FxInfo of its own.
    tree = ast.parse(textwrap.dedent(inspect.getsource(PositionValuator._lookup_fx)))
    called = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert called.count("_no_fx_rate") == 2
    # The one FxInfo built here is the success branch's.
    assert called.count("FxInfo") == 1
    assert callable(valuation_module._no_fx_rate)


def test_kf5_no_new_token_was_introduced() -> None:
    source = (APP_ROOT / "portfolio" / "valuation.py").read_text(encoding="utf-8")
    for token in ("fx_unusable", "rate_unusable", "fx_now_unusable", "fx_open_unusable"):
        assert token not in source


# --- F1b-R10 / F1b-R11: an unused rate carries no source note --------------------

#: The two real rung ids. Both have a non-empty standing note, so an empty
#: ``source_note`` on their UNAVAILABLE answer is withheld, not defaulted.
REAL_SOURCES = [BANK, YAHOO]
#: Open date of a holding whose open-date rate is unusable (invariant test).
OPENED_ON_BAD = OPENED + timedelta(days=30)
#: Open date with nothing published within the lookback window before it.
OPENED_ON_NOTHING = OPENED - timedelta(days=60)


def _assert_unused_rate_answer(answer: tuple[Decimal | None, FxInfo], source: str) -> None:
    """The revised D3 answer, field by field (F1b-R11)."""
    rate, info = answer
    assert rate is None
    assert info.data_status is DataStatus.UNAVAILABLE
    assert info.source_note == ""
    assert info.source == source
    assert info.reason == REASON
    assert info.as_of is None


@pytest.mark.parametrize("bad", BAD_RATES)
@pytest.mark.parametrize("source", REAL_SOURCES)
def test_f1b_r11_an_unusable_latest_rate_carries_no_source_note(
    source: str, bad: Decimal, caplog: pytest.LogCaptureFixture
) -> None:
    # Precondition: there is a methodology sentence that could be attached.
    assert source_note(source) != ""
    fx = _DatedFx({TODAY - timedelta(days=3): GOOD, TODAY: bad}, source=source)
    with caplog.at_level(logging.WARNING, logger=VALUATION_LOGGER):
        answer = _valuator(fx)._lookup_fx(PAIR, TODAY)
    _assert_unused_rate_answer(answer, source)
    # This cell went through the "latest rate is unusable" branch.
    assert [r.getMessage() for r in _records(caplog, VALUATION_LOGGER)] == [
        _dropped(TODAY, bad, source)
    ]


@pytest.mark.parametrize("source", REAL_SOURCES)
def test_f1b_r11_rates_all_after_the_target_carry_no_source_note(
    source: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert source_note(source) != ""
    fx = _DatedFx({TODAY + timedelta(days=1): GOOD}, source=source, past_end=True)
    # Precondition: the source did answer, with rates -- all of them too late.
    probe = _DatedFx({TODAY + timedelta(days=1): GOOD}, source=source, past_end=True)
    answered = probe.get_daily_rates(PAIR, TODAY - timedelta(days=7), TODAY)
    assert answered.status is DataStatus.FRESH
    assert answered.rates and all(rate.date > TODAY for rate in answered.rates)
    with caplog.at_level(logging.WARNING, logger=VALUATION_LOGGER):
        answer = _valuator(fx)._lookup_fx(PAIR, TODAY)
    _assert_unused_rate_answer(answer, source)
    # The "no candidates" branch, not the unusable-rate one.
    assert _records(caplog, VALUATION_LOGGER) == []


@pytest.mark.parametrize("source", REAL_SOURCES)
def test_f1b_r10_a_used_rate_keeps_its_source_note(source: str) -> None:
    # The success branch is untouched: the applied rate's note is disclosed.
    rate, info = _valuator(_DatedFx({TODAY: GOOD}, source=source))._lookup_fx(PAIR, TODAY)
    assert rate == GOOD
    assert info.data_status is DataStatus.FRESH
    assert info.source_note == source_note(source)
    assert info.source_note != ""


def test_f1b_r10_the_no_rate_helper_never_asks_for_a_source_note() -> None:
    # Revised D3: a literal empty string, not a call and not a condition.
    tree = ast.parse(textwrap.dedent(inspect.getsource(valuation_module._no_fx_rate)))
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert "FxInfo" in called  # guard the guard: the walk does see the calls
    assert "source_note" not in called
    notes = [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "source_note"
    ]
    assert len(notes) == 1
    assert isinstance(notes[0], ast.Constant)
    assert notes[0].value == ""


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
@pytest.mark.parametrize("source", REAL_SOURCES)
def test_f1b_r10_an_ok_row_never_holds_an_unavailable_rate(
    source: str, bad: Decimal, mode: PriceMode
) -> None:
    # Why an empty note cannot thin a disclosure: the consumers read the note
    # off ok rows only, and an ok row holds a used rate for both lookups.
    fx = _DatedFx({OPENED: EARLIER_GOOD, OPENED_ON_BAD: bad, TODAY: GOOD}, source=source)
    positions = [
        _usd(1, OPENED),
        _usd(2, OPENED_ON_BAD),
        _usd(3, OPENED_ON_NOTHING),
        _usd(4, None),
    ]
    rows = _valuator(fx, mode).value_all(positions)
    seen_ok = seen_unavailable = 0
    for row in rows:
        valuation = row.valuation
        infos = [info for info in (valuation.fx, valuation.fx_open) if info is not None]
        if valuation.status == "ok":
            seen_ok += 1
            assert valuation.fx is not None and valuation.fx_open is not None
            for info in (valuation.fx, valuation.fx_open):
                assert info.data_status is not DataStatus.UNAVAILABLE
                assert info.source_note == source_note(source) != ""
        for info in infos:
            if info.data_status is DataStatus.UNAVAILABLE:
                seen_unavailable += 1
                assert valuation.status == "insufficient_data"
                assert info.source_note == ""
    # Not vacuous: one ok row, and both no-rate branches were reached.
    assert seen_ok == 1
    assert seen_unavailable == 2


# --- KF-7 / R-1 / R-9: the book layer (D5) --------------------------------------


def _quote(rate: float | None) -> FxQuote:
    return FxQuote(
        pair=PAIR,
        rate=rate,
        as_of=YESTERDAY.isoformat(),
        source=BANK,
        status=DataStatus.FRESH,
        source_note=source_note(BANK),
    )


def _unavailable_note(status: str = "fresh", as_of: str | None = None) -> str:
    return FX_UNAVAILABLE_NOTE.format(
        currency="USD",
        pair=PAIR,
        status=status,
        source=BANK,
        as_of=as_of or YESTERDAY.isoformat(),
    )


@pytest.mark.parametrize("rate", [0.0, -1.0, -0.0])
def test_kf7_zero_and_negative_quotes_keep_their_note_byte_for_byte(rate: float) -> None:
    # R-1: the pre-F-1b output for these values, spelled out from the template.
    assert book_module._resolve_fx("USD", _quote(rate)) == (None, _unavailable_note(), None)


@pytest.mark.parametrize("rate", [math.nan, math.inf, -math.inf])
def test_kf7_non_finite_quotes_are_tightened_to_the_unavailable_note(rate: float) -> None:
    got_rate, note, applied = book_module._resolve_fx("USD", _quote(rate))
    assert got_rate is None
    assert applied is None
    assert note == _unavailable_note()
    # R-9: no "inf"/"nan" on the card, and no applied-rate sentence.
    assert note is not None
    assert "inf" not in note.lower()
    assert "nan" not in note.lower()
    assert not note.startswith(APPLIED_HEAD)

    book = build_book_context(
        book_summary(),
        symbol=SYMBOL,
        market="US",
        close=150.0,
        currency="USD",
        atr=3.0,
        fx=_quote(rate),
    )
    assert book.fx_rate is None
    assert book.context.fx_to_twd == 1.0
    assert book.context.close is None
    assert book.fx_note == _unavailable_note()
    assert book.price_withheld_note == _unavailable_note()
    assert not any(note.startswith(APPLIED_HEAD) for note in book.symbol_notes)


def test_kf7_a_missing_quote_keeps_the_no_quote_note() -> None:
    # D6: NO_FX_QUOTE_NOTE stays reserved for "no quote at all".
    assert book_module._resolve_fx("USD", None) == (
        None,
        NO_FX_QUOTE_NOTE.format(currency="USD"),
        None,
    )


def test_kf7_a_usable_quote_is_still_applied() -> None:
    rate, note, applied = book_module._resolve_fx("USD", _quote(31.5))
    assert rate == 31.5
    assert note is not None and note.startswith(APPLIED_HEAD)
    assert applied == _quote(31.5)


# --- trigger 0 (F1b-C1) and KF-15: the PR-RK2 2a line -----------------------------


def _alert_store(tmp_path: Path) -> PositionStore:
    store = PositionStore(db_path=tmp_path / "positions.db")
    store.create(
        PositionInput(
            symbol=SYMBOL,
            market="US",
            quantity=Decimal(137),
            avg_cost=Decimal(150),
            currency="USD",
            opened_at=OPENED,
            instrument_type="stock",
            note=None,
        )
    )
    return store


def _snapshot(store: PositionStore, fx: FxRateProvider) -> Any:
    """One alert snapshot: bars end yesterday, so the quote is asked for yesterday."""
    services: dict[Market, FakePriceService] = {"US": _us_service(YESTERDAY)}
    return build_snapshot(
        SYMBOL,
        "US",
        resolver=dict(services),
        store=store,
        valuator=PositionValuator(
            market_services=dict(services), fx_provider=fx, clock=_clock(TODAY)
        ),
        budget=RiskBudget(),
        fx_provider=fx,
        today=TODAY,
    )


def _unapplied(quote_source: str) -> str:
    return (
        f"{UNAPPLIED_HEAD}pair={PAIR} quote_source={quote_source} "
        f"valuation_source={BANK} valuation_as_of={TODAY.isoformat()}"
    )


#: The valuator's two lookups (today, the open date) are good on the bank rung;
#: only the quote's day (yesterday) carries the value under test.
_VALUED = {OPENED: EARLIER_GOOD, TODAY: GOOD}


@pytest.mark.parametrize(
    ("quote_day", "expected_source"),
    [
        pytest.param(Decimal("0"), BANK, id="zero-names-the-rung"),
        pytest.param(Decimal("-1"), BANK, id="negative-names-the-rung"),
        # KF-15: a finite Decimal beyond float range becomes +inf in the quote
        # (services/fx.py float()); before F-1b it was applied as "inf" and the
        # 2a line, guarded by ``> 0.0``, could never count it.
        pytest.param(Decimal("1e400"), BANK, id="overflow-to-inf-names-the-rung"),
    ],
)
def test_trigger0_an_unusable_quote_is_logged_with_its_rung(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, quote_day: Decimal, expected_source: str
) -> None:
    bank = _DatedFx({**_VALUED, YESTERDAY: quote_day}, source=BANK)
    yahoo = _DatedFx({}, source=YAHOO)
    ladder = FxRateLadder(primary=bank, backup=yahoo)
    with caplog.at_level(logging.WARNING):
        snap = _snapshot(_alert_store(tmp_path), ladder)

    assert [record.getMessage() for record in _records(caplog, BOOK_LOGGER)] == [
        _unapplied(expected_source)
    ]
    # The valuator's own latest rates were good: the bad day is earlier than
    # today's, so trigger 1 stays silent (D4's other half).
    assert _records(caplog, VALUATION_LOGGER) == []
    assert snap.price_cap_cause == _unavailable_note()
    assert not snap.reason or "inf" not in snap.reason.lower()


def test_trigger0_both_rungs_failing_is_logged_as_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ladder = FxRateLadder(primary=_DatedFx(_VALUED, source=BANK), backup=_DatedFx({}, source=YAHOO))
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        _snapshot(_alert_store(tmp_path), ladder)
    assert [record.getMessage() for record in _records(caplog, BOOK_LOGGER)] == [_unapplied("none")]


def test_trigger0_rates_all_after_the_quote_day_are_counted_too(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # F1b-C1 (ii): a rung that answers only with rates after ``on`` yields a
    # ``rate=None`` quote carrying the real rung id. It IS counted -- trigger 0
    # is an upper bound ("covers, may over-count"), never an exact count.
    bank = _DatedFx(_VALUED, source=BANK, past_end=True)
    ladder = FxRateLadder(primary=bank, backup=_DatedFx({}, source=YAHOO))
    with caplog.at_level(logging.WARNING, logger=BOOK_LOGGER):
        _snapshot(_alert_store(tmp_path), ladder)
    assert [record.getMessage() for record in _records(caplog, BOOK_LOGGER)] == [_unapplied(BANK)]


def test_kf15_the_2a_guard_asks_the_one_definition() -> None:
    source = inspect.getsource(book_module._log_unapplied_quote)
    assert "usable_rate(fx.rate)" in source
    assert "> 0.0" not in source


# --- R-2: the alert snapshot --------------------------------------------------------


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_r2_the_snapshot_withholds_the_price_caps_with_the_full_note(
    tmp_path: Path, bad: Decimal
) -> None:
    fx = _DatedFx({OPENED: bad, YESTERDAY: bad, TODAY: bad}, source=BANK)
    snap = _snapshot(_alert_store(tmp_path), fx)
    # Full text, not a prefix (R-2).
    assert snap.price_cap_cause == _unavailable_note()
    # Nothing was converted with the bad rate, so no methodology sentence.
    assert snap.fx_disclosure is None
    assert snap.fx_disclosure_without_quote is None
    assert snap.limits  # evaluated, not skipped by an exception


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_the_summary_under_the_snapshot_leaves_the_row_unvalued(
    tmp_path: Path, bad: Decimal
) -> None:
    fx = _DatedFx({OPENED: bad, TODAY: bad}, source=BANK)
    valuator = PositionValuator(
        market_services={"US": _us_service()}, fx_provider=fx, clock=_clock(TODAY)
    )
    summary = build_summary(_alert_store(tmp_path), valuator)
    assert summary.totals.status == "no_data"
    assert summary.totals.market_value_twd == 0
    assert summary.fx_disclosures == []


# --- endpoints: R-7 and the test-matrix point 4 ----------------------------------


def _serve(api_harness: ApiHarness, fx: FxRateProvider) -> None:
    """Card, overview, ``/limits`` and settings through one FX provider."""
    services: dict[Market, FakePriceService] = {
        "TW": api_harness.price_service,
        "US": _us_service(YESTERDAY),
    }
    clock = _clock(TODAY)
    valuator = PositionValuator(market_services=services, fx_provider=fx, clock=clock)
    cached = PositionValuator(
        market_services=services, fx_provider=fx, clock=clock, price_mode="cache_only"
    )
    app.dependency_overrides[get_market_resolver] = lambda: services
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_cached_valuator] = lambda: cached
    app.dependency_overrides[get_fx_provider] = lambda: fx


def _book(api_harness: ApiHarness, bad: Decimal, *, with_twd: bool = True) -> None:
    """A USD holding on a bad rate, beside (by default) a valued TWD holding."""
    _serve(api_harness, _DatedFx({OPENED: bad, YESTERDAY: bad, TODAY: bad}, source=BANK))
    store = api_harness.positions
    store.create(
        PositionInput(
            symbol=SYMBOL,
            market="US",
            quantity=Decimal(137),
            avg_cost=Decimal(150),
            currency="USD",
            opened_at=OPENED,
            instrument_type="stock",
            note=None,
        )
    )
    if with_twd:
        api_harness.price_service.seed(
            TWD_SYMBOL, recent_bars(trending_closes(200, start=500.0), symbol=TWD_SYMBOL)
        )
        store.create(
            PositionInput(
                symbol=TWD_SYMBOL,
                market="TW",
                quantity=Decimal(1000),
                avg_cost=Decimal(500),
                currency="TWD",
                opened_at=OPENED,
                instrument_type="stock",
                note=None,
            )
        )


def _report_net_worth(api_harness: ApiHarness) -> None:
    current = api_harness.settings.load()
    api_harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=NET_WORTH, updated_at=datetime.now(UTC).isoformat()
                )
            }
        )
    )


def _twd_market_value(body: dict[str, Any]) -> Decimal:
    rows = {row["symbol"]: row for row in body["positions"]}
    assert rows[TWD_SYMBOL]["valuation"]["status"] == "ok"
    return Decimal(rows[TWD_SYMBOL]["market_value_twd"])


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_r7_summary_is_partial_and_leaves_the_bad_row_out(
    api_harness: ApiHarness, bad: Decimal
) -> None:
    _book(api_harness, bad)
    response = api_harness.client.get("/api/portfolio/summary")
    assert response.status_code == 200
    body = response.json()
    rows = {row["symbol"]: row for row in body["positions"]}
    valuation = rows[SYMBOL]["valuation"]
    assert valuation["status"] == "insufficient_data"
    assert valuation["missing"] == ["fx_now", "fx_open"]
    assert rows[SYMBOL]["market_value_twd"] is None
    for key in ("fx", "fx_open"):
        assert valuation[key]["data_status"] == "unavailable", key
        assert valuation[key]["as_of"] is None, key
        # F1b-R11: ``_book`` answers on the bank rung, whose note is not empty,
        # so this is the unused rate's note being withheld, not a default.
        assert valuation[key]["source"] == BANK, key
        assert valuation[key]["source_note"] == "", key
    totals = body["totals"]
    assert totals["status"] == "partial"
    assert Decimal(totals["market_value_twd"]) == _twd_market_value(body)
    # The unused rate's source is not disclosed as if it had been applied.
    assert body["fx_disclosures"] == []


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_r7_limits_answer_and_withhold_gross_exposure(
    api_harness: ApiHarness, bad: Decimal
) -> None:
    _book(api_harness, bad)
    _report_net_worth(api_harness)
    response = api_harness.client.get("/api/portfolio/limits")
    assert response.status_code == 200
    checks = {check["limit_id"]: check for check in response.json()["limits"]}
    # The valued numerator over the reported net worth is far below the cap,
    # so only "the book is not fully valued" can make it not_evaluable.
    assert checks["gross_exposure"]["status"] == "not_evaluable"


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_r7_another_symbols_card_does_not_treat_the_book_as_complete(
    api_harness: ApiHarness, bad: Decimal
) -> None:
    _book(api_harness, bad)
    _report_net_worth(api_harness)
    response = api_harness.client.get(f"/api/advice/{TWD_SYMBOL}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["portfolio_context"]["book_fully_valued"] is False
    gross = [c for c in body["advice"]["limits_check"] if c["id"] == "gross_exposure"]
    assert [c["status"] for c in gross] == ["not_evaluable"]


@pytest.mark.parametrize("with_twd", [True, False], ids=["with-twd", "usd-only"])
@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_the_affected_symbols_own_card_answers(
    api_harness: ApiHarness, bad: Decimal, with_twd: bool
) -> None:
    _book(api_harness, bad, with_twd=with_twd)
    _report_net_worth(api_harness)
    response = api_harness.client.get(f"/api/advice/{SYMBOL}", params={"market": "US"})
    assert response.status_code == 200
    body = response.json()
    context = body["portfolio_context"]
    assert context["book_fully_valued"] is False
    assert context["close"] is None
    assert context["fx_to_twd"] == 1.0
    assert _unavailable_note() in body["context_notes"]
    assert not any(note.startswith(APPLIED_HEAD) for note in body["context_notes"])


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_r7_the_stored_yardstick_leaves_the_bad_row_out(
    api_harness: ApiHarness, bad: Decimal
) -> None:
    _book(api_harness, bad)
    summary = api_harness.client.get("/api/portfolio/summary").json()
    response = api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": NET_WORTH}}
    )
    assert response.status_code == 200
    stored = response.json()["settings"]["net_worth"]["valued_book_twd_at_report"]
    assert stored == pytest.approx(float(_twd_market_value(summary)))


@pytest.mark.parametrize("bad", WIRE_BAD_RATES)
def test_a_book_of_only_the_bad_row_stores_no_yardstick(
    api_harness: ApiHarness, bad: Decimal
) -> None:
    _book(api_harness, bad, with_twd=False)
    response = api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": NET_WORTH}}
    )
    assert response.status_code == 200
    assert response.json()["settings"]["net_worth"]["valued_book_twd_at_report"] is None
    limits = api_harness.client.get("/api/portfolio/limits")
    assert limits.status_code == 200
