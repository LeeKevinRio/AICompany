"""ADR-0020: one observation window for alerts, advice, signals, bars and portfolio.

The alert snapshot used to load 400 calendar days while ``/api/advice`` (and the
signals / bars / portfolio endpoints) loaded 540, so the same symbol on the same
day could show a 13.6% drawdown in a fired alert and 24% on the advice card. The
snapshot's docstring promised "the same numbers"; only these tests make that
promise checkable:

* T-1 -- both paths ask ``load_bars`` for the same ``start`` / ``end``.
* T-2 -- on a series whose old high sits ~450 days back (example C of
  ``work/research/警示-400-日窗與建議卡-540-日窗差異-分析-2026-10-04.md``), the
  window-sensitive fields agree value for value and ``drawdown_protection``
  fires on both sides.
* T-3 -- the window constant lives in a leaf module, ``app.signals`` cannot
  reach ``app.api``, and ``app.alerts`` reaches only the whitelisted ``app.api``
  modules (never ``app.api.signals``).
* T-4 -- the API re-export, the data-refresh window and the diagnose CLI all
  agree with the one definition.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

import app.alerts.snapshot as snapshot_module
import app.api.advice as advice_module
from app.advice.context import build_context
from app.advice.engine import evaluate_rule
from app.advice.limits import PortfolioContext, RiskBudget
from app.advice.loader import load_default_rules
from app.alerts.snapshot import build_snapshot
from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.diagnose import DEFAULT_LOOKBACK_DAYS as DIAGNOSE_LOOKBACK_DAYS
from app.data.interface import PriceBar
from app.portfolio.valuation import PositionValuator
from app.scheduler import DATA_REFRESH_LOOKBACK_DAYS
from app.services.market import LoadedBars, load_bars
from app.signals.service import compute_signals
from app.signals.window import OBSERVATION_LOOKBACK_DAYS
from tests.api_helpers import UnavailableFxProvider, position_payload
from tests.conftest import ApiHarness
from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    module_path,
    offenders,
    reachable_app_modules,
)

#: A Friday, so the newest bar is on the window's last day.
_TODAY = date(2026, 10, 2)
_SYMBOL = "2330"
_WINDOW_MODULE = "app.signals.window"
#: The context fields whose value depends on where the window starts.
_WINDOW_SENSITIVE_FIELDS = ("drawdown.current", "drawdown.max_drawdown", "volatility.annualized")


class _FixedDate(date):
    """``date`` whose ``today()`` is pinned, for the endpoint that reads the clock."""

    @classmethod
    def today(cls) -> _FixedDate:
        return cls(_TODAY.year, _TODAY.month, _TODAY.day)


def _example_c_close(day: date) -> float:
    """Example C: peak 100 ~450 calendar days back, slide to 70, rebound to 88, drift to 76."""
    age = (_TODAY - day).days
    if age > 450:
        return 80 + (600 - age) / 150 * 20
    if age > 330:
        return 100 - (450 - age) / 120 * 30
    if age > 300:
        return 70 + (330 - age) / 30 * 18
    return 88 - (300 - age) / 300 * 12


def _example_c_bars() -> list[PriceBar]:
    """Weekday bars over the 600 calendar days up to ``_TODAY``."""
    first = _TODAY - timedelta(days=600)
    days = (first + timedelta(days=offset) for offset in range(601))
    bars: list[PriceBar] = []
    for day in days:
        if day.weekday() >= 5:
            continue
        close = Decimal(str(round(_example_c_close(day), 2)))
        bars.append(
            PriceBar(
                symbol=_SYMBOL,
                market="TW",
                date=day,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000,
                currency="TWD",
                as_of=datetime(2026, 10, 2, 8, tzinfo=UTC),
                source="synthetic",
            )
        )
    return bars


def _snapshot(api_harness: ApiHarness) -> Any:
    return build_snapshot(
        _SYMBOL,
        "TW",
        resolver={"TW": api_harness.price_service},
        store=api_harness.positions,
        valuator=PositionValuator(
            market_services={"TW": api_harness.price_service},
            fx_provider=UnavailableFxProvider(),
        ),
        budget=RiskBudget(),
        today=_TODAY,
    )


def _advice(api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(advice_module, "date", _FixedDate)
    response = api_harness.client.get(f"/api/advice/{_SYMBOL}")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _recording_load_bars(
    calls: list[tuple[str, date, date]], label: str
) -> Callable[..., LoadedBars]:
    def recorder(*args: Any, **kwargs: Any) -> LoadedBars:
        calls.append((label, kwargs["start"], kwargs["end"]))
        return load_bars(*args, **kwargs)

    return recorder


def test_t1_snapshot_and_advice_request_the_same_window(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_harness.price_service.seed(_SYMBOL, _example_c_bars())
    calls: list[tuple[str, date, date]] = []
    monkeypatch.setattr(snapshot_module, "load_bars", _recording_load_bars(calls, "snapshot"))
    monkeypatch.setattr(advice_module, "load_bars", _recording_load_bars(calls, "advice"))

    _snapshot(api_harness)
    _advice(api_harness, monkeypatch)

    windows = {label: (start, end) for label, start, end in calls}
    assert set(windows) == {"snapshot", "advice"}
    assert windows["snapshot"] == windows["advice"]
    assert windows["snapshot"][1] == _TODAY


def test_t2_example_c_reads_the_same_numbers_in_the_alert_and_on_the_card(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_harness.price_service.seed(_SYMBOL, _example_c_bars())
    api_harness.client.post("/api/positions", json=position_payload())
    advice_signals: list[dict[str, Any]] = []

    def spy(symbol: str, bars: list[PriceBar]) -> dict[str, Any]:
        result = compute_signals(symbol, bars)
        advice_signals.append(result)
        return result

    monkeypatch.setattr(advice_module, "compute_signals", spy)

    snapshot = _snapshot(api_harness)
    body = _advice(api_harness, monkeypatch)

    assert snapshot.signals is not None
    assert len(advice_signals) == 1
    # Compared under the field names an alert rule and an advice rule select.
    alert_context = build_context(snapshot.signals, PortfolioContext(symbol=_SYMBOL))
    card_context = build_context(advice_signals[0], PortfolioContext(symbol=_SYMBOL))
    for field in _WINDOW_SENSITIVE_FIELDS:
        assert alert_context[field] is not None, field
        assert alert_context[field] == card_context[field], field
    # The old high (~450 days back) is inside the window on both sides.
    assert alert_context["drawdown.current"] == pytest.approx(-0.24)

    # Both sides judge the same rule on the same number: the card shows it ...
    assert body["status"] == "ok"
    card_ids = {rule["id"] for rule in body["advice"]["matched_rules"]}
    assert "drawdown_protection" in card_ids
    # ... and the alert snapshot's context fires the identical rule definition.
    rule = next(r for r in load_default_rules().rules if r.id == "drawdown_protection")
    assert evaluate_rule(rule, alert_context).matched


def _package_modules(package: str) -> tuple[str, ...]:
    """Every module of ``app.x``, enumerated from the source tree (not a hand list)."""
    root = APP_ROOT.joinpath(*package.split(".")[1:])
    modules = [package]
    for source in sorted(root.rglob("*.py")):
        if source.name == "__init__.py":
            parts = [package, *source.parent.relative_to(root).parts]
        else:
            parts = [package, *source.relative_to(root).with_suffix("").parts]
        modules.append(".".join(parts))
    return tuple(dict.fromkeys(modules))


#: The ``app.api`` modules ``app.alerts`` may reach today. ``app.api.kelly_wording``
#: is existing debt (``app.advice.limits`` imports it), recorded rather than fixed
#: here (ADR-0020 K-3); the list may shrink but must not grow.
_ALERTS_API_WHITELIST = frozenset({"app.api", "app.api.kelly_wording"})


def _owning_module(name: str) -> str:
    """``app.x.y`` for a reachable name, folding ``from app.x.y import Z`` onto ``app.x.y``."""
    return name if module_path(name) is not None else name.rsplit(".", 1)[0]


def test_t3_the_window_module_is_a_leaf() -> None:
    path = module_path(_WINDOW_MODULE)
    assert path is not None
    imported = imported_modules(path, _WINDOW_MODULE)
    assert imported == set(), f"{_WINDOW_MODULE} must import nothing from app: {imported}"
    # Belt and braces: no ``import app...`` in any spelling, relative ones included.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in the leaf module"
            assert not (node.module or "").startswith("app"), node.module
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("app") for alias in node.names)


def test_t3_signals_cannot_reach_the_api_layer() -> None:
    roots = _package_modules("app.signals")
    assert _WINDOW_MODULE in roots
    assert offenders(reachable_app_modules(roots), "app.api") == []


def test_t3_alerts_reach_only_whitelisted_api_modules() -> None:
    roots = _package_modules("app.alerts")
    assert "app.alerts.snapshot" in roots
    for root in roots:
        reachable = reachable_app_modules((root,))
        assert "app.api.signals" not in reachable, root
        reached = {_owning_module(name) for name in offenders(reachable, "app.api")}
        assert reached <= _ALERTS_API_WHITELIST, f"{root} reaches {reached - _ALERTS_API_WHITELIST}"


def test_t4_the_api_constant_is_the_shared_window() -> None:
    assert DEFAULT_LOOKBACK_DAYS == OBSERVATION_LOOKBACK_DAYS


def test_t4_the_refresh_window_covers_the_observation_window() -> None:
    # ADR-0012 C-13 pins the value itself (tests/test_market_panel_boundary.py);
    # this pins the relation, which is what readers actually depend on.
    assert DATA_REFRESH_LOOKBACK_DAYS >= OBSERVATION_LOOKBACK_DAYS


def test_t4_the_diagnose_window_equals_the_observation_window() -> None:
    assert DIAGNOSE_LOOKBACK_DAYS == OBSERVATION_LOOKBACK_DAYS
