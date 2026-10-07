"""F-1: a latest close that is zero, negative or not finite is no price.

任務單 `work/dispatch/2026-10-07-任務單-F-1-組合估值對不可用收盤價的防護.md`.
One definition (:mod:`app.data.price_guard`) is applied at three points: the
portfolio valuator (B′), ``build_book_context`` (A) and the advice endpoint.
These tests pin the acceptance conditions 1-3 end to end, plus the evidence
the risk review asked for that ``/api/bars`` itself passes such a bar through
unchanged (it is deliberately not guarded here; that is F-2).
"""

from __future__ import annotations

import ast
import logging
import math
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import app.api.advice as advice_module
from app.advice.book import (
    SYMBOL_UNVALUED_NOTE,
    UNVALUED_POSITIONS_NOTE,
    UNVALUED_POSITIONS_NOTE_CACHE_ONLY,
    build_book_context,
)
from app.advice.limits import PRICE_INPUT_LIMIT_IDS
from app.alerts import engine as alerts_engine
from app.api.deps import get_cached_valuator, get_valuator
from app.data import price_guard
from app.data.interface import PriceBar
from app.data.price_guard import usable_price
from app.main import app
from app.portfolio.summary import PortfolioSummary, Totals
from app.portfolio.valuation import PRICE_NOT_QUERIED, PositionValuator, PriceMode
from app.positions.models import Position
from app.services.fx import resolve_fx_quote
from app.settings.models import NetWorthSettings
from app.signals.service import compute_signals
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness
from tests.import_graph import APP_ROOT, imported_modules, offenders, reachable_app_modules

#: The bad closes the acceptance conditions name, as the wire spells them.
BAD_CLOSES = [pytest.param("0", id="zero"), pytest.param("-1", id="negative")]
MODES: list[PriceMode] = ["live", "cache_only"]

S = "2454"  # the symbol whose newest bar is bad
T = "2330"  # a normal holding next to it

#: A data-layer sentence riding on a *successful* load, so ``loaded.reason`` is
#: not ``None`` and "the card says ``reason=None``" is an observation, not a default.
SOURCE_SENTENCE = "來源暫時無法連線。"


def _bars(symbol: str, bad_close: str | None = None, *, count: int = 200) -> list[PriceBar]:
    """A normal series; with ``bad_close`` only the newest bar's close is replaced.

    Open/high/low of that bar stay normal, as a real source sending a bad close
    would leave them -- so nothing but the close itself can trip a guard.
    """
    bars = recent_bars(trending_closes(count), symbol=symbol)
    if bad_close is None:
        return bars
    return [*bars[:-1], bars[-1].model_copy(update={"close": Decimal(bad_close)})]


def _hold(harness: ApiHarness, symbol: str, quantity: str = "1000") -> None:
    response = harness.client.post(
        "/api/positions",
        json=position_payload(symbol=symbol, quantity=quantity, avg_cost="100"),
    )
    assert response.status_code == 201


def _report_net_worth(harness: ApiHarness) -> None:
    current = harness.settings.load()
    harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=99_000_000.0,
                    updated_at=datetime.now(UTC).isoformat(),
                )
            }
        )
    )


# --- the one definition --------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
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
    ],
)
def test_usable_price_is_the_one_definition(value: float | Decimal | None, expected: bool) -> None:
    assert usable_price(value) is expected


@pytest.mark.parametrize("value", [None, 0.0, -1.0, math.nan, math.inf, 1e-9, 550.0])
def test_the_alert_engine_guard_forwards_to_the_one_definition(value: float | None) -> None:
    # Same name, same value-or-None shape for the alert layer; the judgement
    # itself is the data-layer leaf's.
    expected = value if usable_price(value) else None
    assert alerts_engine.usable_price(value) == expected


def test_the_guard_module_is_a_leaf() -> None:
    # Any layer may depend on it, so it must depend on nothing in ``app``.
    path = APP_ROOT / "data" / "price_guard.py"
    assert imported_modules(path, "app.data.price_guard") == set()
    assert price_guard.__name__ == "app.data.price_guard"


# --- dependency direction (constraint 2) ----------------------------------------


def _portfolio_modules() -> tuple[str, ...]:
    package = APP_ROOT / "portfolio"
    modules = ["app.portfolio"]
    modules += [f"app.portfolio.{path.stem}" for path in sorted(package.glob("*.py"))]
    return tuple(dict.fromkeys(modules))


@pytest.mark.parametrize("forbidden", ["app.alerts", "app.advice"])
def test_the_portfolio_package_never_reaches_alerts_or_advice(forbidden: str) -> None:
    roots = _portfolio_modules()
    assert "app.portfolio.valuation" in roots
    reachable = reachable_app_modules(roots)
    assert "app.data.price_guard" in reachable
    assert offenders(reachable, forbidden) == []


# --- source-level guards (constraints 1 and 6) ----------------------------------

#: The files that must not carry their own "is this close usable" threshold.
_NO_INLINE_CLOSE_THRESHOLD = (
    APP_ROOT / "portfolio" / "valuation.py",
    APP_ROOT / "advice" / "book.py",
    APP_ROOT / "api" / "advice.py",
    APP_ROOT / "alerts" / "snapshot.py",
)
_INLINE_CLOSE_THRESHOLD = re.compile(
    r"close\b[^#\n]*?(?:>|<=)\s*0(?![\d.])|(?<![\d.])0\s*(?:<|>=)[^#\n]*?\bclose\b"
)


@pytest.mark.parametrize("path", _NO_INLINE_CLOSE_THRESHOLD, ids=lambda path: path.name)
def test_no_inline_close_threshold_outside_the_one_definition(path: Path) -> None:
    hits = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if _INLINE_CLOSE_THRESHOLD.search(line)
    ]
    assert hits == []


def test_the_threshold_pattern_would_catch_an_inline_guard() -> None:
    # Guard the guard: a regex that matches nothing proves nothing.
    for line in (
        "if latest.close <= 0:",
        "priced = close if close > 0 else None",
        "ok = float(latest.close) > 0",
        "if 0 < close:",
    ):
        assert _INLINE_CLOSE_THRESHOLD.search(line), line
    assert not _INLINE_CLOSE_THRESHOLD.search("if usable_price(close):")


def test_the_api_layer_does_not_swallow_validation_errors_for_f1() -> None:
    # Constraint 6: the fix is upstream of the endpoints, never a try around one.
    api = APP_ROOT / "api"
    catching = sorted(
        path.name
        for path in api.glob("*.py")
        if "except ValidationError" in path.read_text(encoding="utf-8")
    )
    assert catching == ["alerts.py"]  # pre-existing (rule payload parsing), not F-1's
    for name in ("advice.py", "portfolio.py"):
        tree = ast.parse((api / name).read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.Try) for node in ast.walk(tree)), name


# --- B′: the valuator ----------------------------------------------------------


def _position(symbol: str = S) -> Position:
    now = datetime(2026, 10, 7, tzinfo=UTC)
    return Position(
        id=1,
        symbol=symbol,
        market="TW",
        quantity=Decimal(1000),
        avg_cost=Decimal(100),
        currency="TWD",
        opened_at=date(2024, 1, 2),
        instrument_type="stock",
        note=None,
        created_at=now,
        updated_at=now,
    )


def _valuator(service: FakePriceService, mode: PriceMode) -> PositionValuator:
    return PositionValuator(
        market_services={"TW": service},
        fx_provider=UnavailableFxProvider(),
        price_mode=mode,
    )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_an_unusable_newest_close_is_valued_exactly_like_no_bar(
    mode: PriceMode, bad_close: str, caplog: pytest.LogCaptureFixture
) -> None:
    bad = FakePriceService({S: _bars(S, bad_close, count=10)})
    empty = FakePriceService()
    with caplog.at_level(logging.WARNING, logger="app.portfolio.valuation"):
        got = _valuator(bad, mode).value_position(_position())
    reference = _valuator(empty, mode).value_position(_position())

    # The earlier, perfectly good bars in the window are not fallen back on.
    assert got == reference
    assert got.valuation.status == "insufficient_data"
    assert got.valuation.price is None
    assert got.valuation.missing == [PRICE_NOT_QUERIED if mode == "cache_only" else "price"]
    assert got.market_value_twd is None
    assert got.cost_twd is None
    assert got.change_basis is None

    [record] = [r for r in caplog.records if r.name == "app.portfolio.valuation"]
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert f"symbol={S}" in message
    assert f"date={date.today().isoformat()}" in message
    assert f"close={bad_close}" in message


@pytest.mark.parametrize("mode", MODES)
def test_a_usable_newest_close_is_unchanged(
    mode: PriceMode, caplog: pytest.LogCaptureFixture
) -> None:
    service = FakePriceService({S: _bars(S, count=10)})
    with caplog.at_level(logging.WARNING, logger="app.portfolio.valuation"):
        got = _valuator(service, mode).value_position(_position())
    assert got.valuation.status == "ok"
    assert got.valuation.price is not None
    assert got.change_basis is not None
    assert not [r for r in caplog.records if r.name == "app.portfolio.valuation"]


# --- A: build_book_context -------------------------------------------------------


def _empty_summary() -> PortfolioSummary:
    zero = Decimal(0)
    return PortfolioSummary(
        as_of="2026-10-07T00:00:00+00:00",
        totals=Totals(
            cost_twd=zero,
            market_value_twd=zero,
            unrealized_pnl_twd=zero,
            asset_contribution_twd=zero,
            fx_contribution_twd=zero,
            status="no_data",
        ),
        positions=[],
    )


@pytest.mark.parametrize("close", [0.0, -1.0, math.nan, math.inf])
def test_the_book_context_withholds_close_and_atr_together(close: float) -> None:
    summary = _empty_summary()
    bad = build_book_context(summary, symbol=S, close=close, currency="TWD", atr=3.0)
    missing = build_book_context(summary, symbol=S, close=None, currency="TWD", atr=None)

    assert bad.context.close is None
    assert bad.context.atr is None
    # No note of its own: the result is the "no price" context, field for field.
    assert bad == missing


def test_the_book_context_keeps_a_usable_close_and_its_atr() -> None:
    book = build_book_context(_empty_summary(), symbol=S, close=550.0, currency="TWD", atr=3.0)
    assert book.context.close == 550.0
    assert book.context.atr == 3.0


# --- acceptance 1: GET /api/advice/{symbol} --------------------------------------


@pytest.fixture
def signal_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = compute_signals

    def spy(symbol: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(symbol)
        return real(symbol, *args, **kwargs)

    monkeypatch.setattr(advice_module, "compute_signals", spy)
    return calls


@pytest.fixture
def fx_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    real = resolve_fx_quote

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(advice_module, "resolve_fx_quote", spy)
    return calls


@pytest.mark.parametrize("held", [False, True], ids=["not-held", "held"])
@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_advice_on_an_unusable_newest_close_is_insufficient_data(
    api_harness: ApiHarness,
    signal_spy: list[str],
    fx_spy: list[dict[str, Any]],
    bad_close: str,
    held: bool,
) -> None:
    api_harness.price_service.seed(S, _bars(S, bad_close))
    api_harness.price_service.seed(T, _bars(T))
    api_harness.price_service.reason = SOURCE_SENTENCE
    _hold(api_harness, T)
    if held:
        _hold(api_harness, S)
    # Precondition: the load itself carries a sentence the card must not quote.
    assert api_harness.client.get(f"/api/bars/{S}").json()["reason"]

    response = api_harness.client.get(f"/api/advice/{S}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["advice"] is None
    assert body["reason"] is None
    assert body["held"] is held
    assert body["portfolio_context"]["close"] is None
    assert body["portfolio_context"]["atr"] is None
    assert signal_spy == []
    assert fx_spy == []

    other = api_harness.client.get(f"/api/advice/{T}")
    assert other.status_code == 200
    assert other.json()["status"] == "ok"
    assert signal_spy == [T]


def test_advice_still_quotes_the_data_layer_reason_when_there_is_no_bar(
    api_harness: ApiHarness,
) -> None:
    # The existing ``latest is None`` path keeps its reason; only the F-1 entry
    # into it drops one that would name the wrong cause.
    api_harness.price_service.reason = SOURCE_SENTENCE
    body = api_harness.client.get(f"/api/advice/{S}").json()
    assert body["status"] == "insufficient_data"
    assert body["reason"] is not None
    assert body["reason"].endswith(SOURCE_SENTENCE)


# --- acceptance 2: summary and limits -------------------------------------------


def _use_valuator(harness: ApiHarness, service: FakePriceService, mode: PriceMode) -> None:
    valuator = PositionValuator(
        market_services={"TW": service}, fx_provider=harness.fx_provider, price_mode=mode
    )
    app.dependency_overrides[get_valuator] = lambda: valuator


def _book_with_bad_holding(harness: ApiHarness, bad_close: str, mode: PriceMode) -> None:
    harness.price_service.seed(S, _bars(S, bad_close))
    harness.price_service.seed(T, _bars(T))
    _use_valuator(harness, harness.price_service, mode)
    _hold(harness, S)
    _hold(harness, T)
    _report_net_worth(harness)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_summary_leaves_the_bad_holding_out_of_the_totals(
    api_harness: ApiHarness, bad_close: str, mode: PriceMode
) -> None:
    _book_with_bad_holding(api_harness, bad_close, mode)

    response = api_harness.client.get("/api/portfolio/summary")

    assert response.status_code == 200
    body = response.json()
    rows = {row["symbol"]: row for row in body["positions"]}
    valuation = rows[S]["valuation"]
    assert valuation["status"] == "insufficient_data"
    assert valuation["price"] is None
    assert valuation["missing"] == [PRICE_NOT_QUERIED if mode == "cache_only" else "price"]
    assert rows[S]["market_value_twd"] is None
    assert rows[T]["valuation"]["status"] == "ok"
    totals = body["totals"]
    assert totals["status"] == "partial"
    assert Decimal(totals["market_value_twd"]) == Decimal(rows[T]["market_value_twd"])
    assert Decimal(totals["cost_twd"]) == Decimal(rows[T]["cost_twd"])


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_limits_list_the_bad_holding_as_unvalued_and_withhold_gross_exposure(
    api_harness: ApiHarness, bad_close: str, mode: PriceMode
) -> None:
    _book_with_bad_holding(api_harness, bad_close, mode)

    response = api_harness.client.get("/api/portfolio/limits")

    assert response.status_code == 200
    body = response.json()
    checks = {check["limit_id"]: check for check in body["limits"]}
    unvalued = SYMBOL_UNVALUED_NOTE.format(count=1)
    for limit_id, check in checks.items():
        if limit_id == "gross_exposure":
            continue
        reasons = [entry["reason"] for entry in check["excluded"] if entry["symbol"] == S]
        assert len(reasons) == 1, limit_id
        assert reasons[0].startswith(unvalued), limit_id
    notes = {
        "live": UNVALUED_POSITIONS_NOTE.format(count=1),
        "cache_only": UNVALUED_POSITIONS_NOTE_CACHE_ONLY.format(count=1),
    }
    assert notes[mode] in body["notes"]
    assert all(note not in body["notes"] for key, note in notes.items() if key != mode)
    assert checks["gross_exposure"]["status"] == "not_evaluable"


@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_limits_withhold_the_price_caps_when_only_the_loaded_bars_are_bad(
    api_harness: ApiHarness, bad_close: str
) -> None:
    # The two paths read bars separately: here the valuator sees a good close
    # while ``load_bars`` hands the endpoint a bad newest bar (A, 縱深).
    valuator_service = FakePriceService({S: _bars(S), T: _bars(T)})
    _use_valuator(api_harness, valuator_service, "live")
    api_harness.price_service.seed(S, _bars(S, bad_close))
    api_harness.price_service.seed(T, _bars(T))
    _hold(api_harness, S)
    _hold(api_harness, T)
    _report_net_worth(api_harness)

    summary = api_harness.client.get("/api/portfolio/summary").json()
    assert {row["symbol"]: row["valuation"]["status"] for row in summary["positions"]} == {
        S: "ok",
        T: "ok",
    }
    response = api_harness.client.get("/api/portfolio/limits")

    assert response.status_code == 200
    checks = {check["limit_id"]: check for check in response.json()["limits"]}
    assert PRICE_INPUT_LIMIT_IDS
    for limit_id in PRICE_INPUT_LIMIT_IDS:
        excluded = [entry["symbol"] for entry in checks[limit_id]["excluded"]]
        assert S in excluded, limit_id
        assert T not in excluded, limit_id
    # The bars T was loaded from are fine, so its own price cap is compared.
    assert checks["per_trade_loss"]["worst_symbol"] == T


@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_advice_on_a_held_symbol_whose_loaded_bar_alone_is_bad(
    api_harness: ApiHarness, bad_close: str, signal_spy: list[str]
) -> None:
    # Same split for the advice card: its cache-only valuator sees a good close
    # (the default harness wiring reads the same fake, so swap the resolver's).
    good_service = FakePriceService({S: _bars(S), T: _bars(T)})
    _hold(api_harness, S)
    api_harness.price_service.seed(S, _bars(S, bad_close))
    valuator = PositionValuator(
        market_services={"TW": good_service},
        fx_provider=api_harness.fx_provider,
        price_mode="cache_only",
    )
    app.dependency_overrides[get_cached_valuator] = lambda: valuator

    response = api_harness.client.get(f"/api/advice/{S}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["reason"] is None
    assert body["portfolio_context"]["close"] is None
    assert body["portfolio_context"]["position_market_value_twd"] > 0.0
    assert signal_spy == []


# --- evidence for the risk review: /api/bars passes the bar through -------------


@pytest.mark.parametrize("bad_close", BAD_CLOSES)
def test_the_bars_endpoint_serves_the_bad_newest_close_unchanged(
    api_harness: ApiHarness, bad_close: str
) -> None:
    # Not a guard: proof that ``/api/bars`` does not filter (F-2 owns that), so
    # the decision card's R-2-a branch is what keeps the figure off the card.
    api_harness.price_service.seed(S, _bars(S, bad_close))
    response = api_harness.client.get(f"/api/bars/{S}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bars"][-1]["close"] == bad_close
    assert body["bars"][-1]["date"] == date.today().isoformat()


def test_no_new_missing_token_was_introduced() -> None:
    # Constraint 3 / R-1: no ``price_unusable`` token unless risk-compliance
    # withdraws its approval of the existing ones.
    source = (APP_ROOT / "portfolio" / "valuation.py").read_text(encoding="utf-8")
    assert "price_unusable" not in source
