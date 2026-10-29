"""N-156 disclosure on the four endpoints (ADR-0032 Decision 2, K-5 ~ K-7, DL-2 ~ DL-4).

* ``GET /api/settings`` -- ``settings_fallback`` over all sixteen combinations,
  equal to what :mod:`app.settings.fallback_wording` builds for the same
  sections (the router passes it through); ``None`` when nothing fell back.
* A fallback ``net_worth`` is never "not entered yet" on the settings page:
  ``freshness`` is ``fallback``, no figure, no 「尚未輸入」 note, only the
  currency reminder (風控 第 1 項 三處表格).
* ``GET /api/advice/{symbol}`` and ``GET /api/portfolio/limits`` --
  ``settings_fallback_notice`` is N-1 / N-2 / N-3 / ``None`` by
  ``risk_budget`` and ``net_worth`` only; ``None`` on ``insufficient_data``.
* The Kelly screen -- the line beside cap 5's effective value, for
  ``risk_budget`` only and only with a value to stand beside.
* DL-8 and DL-9 -- the two facts the F-4 / alerts and cost_model copy rest on.
"""

from __future__ import annotations

import ast
import itertools
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import RiskBudget
from app.api.settings import NET_WORTH_ABSENT_NOTE, NET_WORTH_CURRENCY_NOTE
from app.settings import fallback_wording as wording
from app.settings.models import AlertSettings, AppSettings, CostModelSettings, NetWorthSettings
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.import_graph import APP_ROOT, imported_modules
from tests.settings_fallback_helpers import SECTIONS, break_sections
from tests.test_api_kelly_disclosures import _attempt, _imported
from tests.test_settings_fallback_wording import KELLY, N1, N2, N3

COMBOS: list[tuple[str, ...]] = [
    combo for size in range(len(SECTIONS) + 1) for combo in itertools.combinations(SECTIONS, size)
]

#: Saved in every section before a combination is broken, so a section that is
#: *not* broken visibly keeps its stored value.
STORED = AppSettings(
    risk_budget=RiskBudget(max_position_weight=0.07),
    cost_model=CostModelSettings(slippage_bps=7.5),
    alerts=AlertSettings(cooldown_minutes=15),
    net_worth=NetWorthSettings(
        total_net_worth_twd=2_000_000.0,
        # Fresh whenever the suite runs: the freshness rule reads the clock.
        updated_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    ),
)


def _combo_id(combo: tuple[str, ...]) -> str:
    return "+".join(combo) or "none"


def _seed(harness: ApiHarness, combo: tuple[str, ...]) -> None:
    harness.settings.save(STORED)
    break_sections(harness.settings, combo)


def _held(harness: ApiHarness) -> None:
    harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    harness.client.post("/api/positions", json=position_payload())


def _expected_notice(combo: tuple[str, ...]) -> str | None:
    budget, net_worth = "risk_budget" in combo, "net_worth" in combo
    return N3 if budget and net_worth else N1 if budget else N2 if net_worth else None


# --- GET /api/settings: 16 combinations ------------------------------------------------


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_settings_page_discloses_exactly_the_fallback_sections(
    api_harness: ApiHarness, combo: tuple[str, ...]
) -> None:
    """DL-2 / K-7: the block, the items, the markers and the panels, per combination."""
    _seed(api_harness, combo)

    body = api_harness.client.get("/api/settings").json()

    expected = wording.settings_fallback(combo)
    if expected is None:
        assert body["settings_fallback"] is None
    else:
        assert body["settings_fallback"] == expected.model_dump(mode="json")
        assert body["settings_fallback"]["sections"] == list(combo)
        assert set(body["settings_fallback"]["section_markers"]) == set(combo)
    for section in SECTIONS:
        value = body["settings"][section]
        if section == "net_worth" and section not in combo:
            continue  # restated with its freshness below
        source = AppSettings() if section in combo else STORED
        assert value == getattr(source, section).model_dump(mode="json"), section


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_a_fallback_net_worth_is_never_shown_as_not_entered(
    api_harness: ApiHarness, combo: tuple[str, ...]
) -> None:
    """風控 第 1 項 三處: badge, stored figure and notes all leave 「尚未輸入」 behind."""
    _seed(api_harness, combo)

    block = api_harness.client.get("/api/settings").json()["net_worth"]

    if "net_worth" in combo:
        assert block == {
            "total_net_worth_twd": None,
            "updated_at": None,
            "age_days": None,
            "freshness": "fallback",
            "notes": [NET_WORTH_CURRENCY_NOTE],
            "warnings": [],
        }
    else:
        assert block["freshness"] != "fallback"
        assert block["total_net_worth_twd"] == 2_000_000.0
    assert NET_WORTH_ABSENT_NOTE not in block["notes"]


def test_a_missing_net_worth_row_is_still_not_entered(api_harness: ApiHarness) -> None:
    """The contrast: no row is the honest 「尚未輸入」, with its note (K-2)."""
    body = api_harness.client.get("/api/settings").json()
    assert body["settings_fallback"] is None
    assert body["net_worth"]["freshness"] == "absent"
    assert body["net_worth"]["notes"] == [NET_WORTH_ABSENT_NOTE, NET_WORTH_CURRENCY_NOTE]


def test_the_fallback_freshness_is_set_exactly_when_the_section_is_listed(
    api_harness: ApiHarness,
) -> None:
    """One source: ``fallback`` and ``"net_worth" in sections`` come from one read."""
    for combo in COMBOS:
        _seed(api_harness, combo)
        body = api_harness.client.get("/api/settings").json()
        listed = body["settings_fallback"] is not None and (
            "net_worth" in body["settings_fallback"]["sections"]
        )
        assert (body["net_worth"]["freshness"] == "fallback") is listed, combo


# --- advice and portfolio limits: N-1 / N-2 / N-3 --------------------------------------


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_advice_and_gauge_sentences_follow_risk_budget_and_net_worth(
    api_harness: ApiHarness, combo: tuple[str, ...]
) -> None:
    """DL-3: three sentences, and ``None`` for cost_model / alerts alone."""
    _held(api_harness)
    _seed(api_harness, combo)
    expected = _expected_notice(combo)

    advice = api_harness.client.get("/api/advice/2330").json()
    gauge = api_harness.client.get("/api/portfolio/limits").json()

    assert advice["status"] == "ok"
    assert advice["settings_fallback_notice"] == expected
    assert gauge["settings_fallback_notice"] == expected


@pytest.mark.parametrize("combo", [("risk_budget",), ("net_worth",), ("risk_budget", "net_worth")])
def test_an_insufficient_advice_response_carries_no_sentence(
    api_harness: ApiHarness, combo: tuple[str, ...]
) -> None:
    """比照 ``advice.py`` insufficient path: no cap list, nothing to qualify."""
    _seed(api_harness, combo)
    body = api_harness.client.get("/api/advice/9999").json()
    assert body["status"] == "insufficient_data"
    assert body["settings_fallback_notice"] is None


def test_the_sentence_is_null_not_empty_when_nothing_fell_back(api_harness: ApiHarness) -> None:
    """K-7: ``None``, never ``""``."""
    _held(api_harness)
    for path in ("/api/advice/2330", "/api/portfolio/limits"):
        assert api_harness.client.get(path).json()["settings_fallback_notice"] is None


def test_a_net_worth_fallback_leaves_cap_3_not_evaluable(api_harness: ApiHarness) -> None:
    """What N-2 says is what cap 3 does: no denominator, not evaluable."""
    _held(api_harness)
    _seed(api_harness, ("net_worth",))
    limits = api_harness.client.get("/api/advice/2330").json()["advice"]["limits_check"]
    cap_3 = next(check for check in limits if check["index"] == 3)
    assert cap_3["status"] == "not_evaluable"


# --- Kelly: beside the effective value, risk_budget only ---------------------------------


def _kelly_block(harness: ApiHarness, combo: tuple[str, ...]) -> dict[str, Any]:
    _seed(harness, combo)
    _attempt(harness)
    harness.kelly_inputs.upsert(_imported())
    response = harness.client.get("/api/kelly-inputs/2330/disclosures")
    assert response.status_code == 200, response.text
    block: dict[str, Any] = response.json()["disclosures"]
    return block


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_kelly_line_appears_for_a_risk_budget_fallback_only(
    api_harness: ApiHarness, combo: tuple[str, ...]
) -> None:
    """第 4 項 / DL 第 7 項: the value stays, the line stands beside it."""
    block = _kelly_block(api_harness, combo)

    assert block["effective_cap"] is not None
    if "risk_budget" in combo:
        assert block["settings_fallback_notice"] == KELLY
        # Computed on the default budget (0.25 x 0.25 = 6.25%), and still shown.
        assert block["effective_cap"]["value"] == "6.25%"
    else:
        assert block["settings_fallback_notice"] is None


def test_the_kelly_line_needs_a_value_to_stand_beside(api_harness: ApiHarness) -> None:
    """No effective value on screen (a hand-keyed row), no line."""
    _seed(api_harness, ("risk_budget",))
    api_harness.kelly_inputs.upsert(_imported(source="backtest_overridden"))
    _attempt(api_harness)
    block = api_harness.client.get("/api/kelly-inputs/2330/disclosures").json()["disclosures"]
    assert block["effective_cap"] is None
    assert block["settings_fallback_notice"] is None


# --- DL-8: the defaults F-4 and the alerts marker rest on ---------------------------------


def test_alert_defaults_are_evaluate_and_push() -> None:
    """DL-8: if either default ever changes, F-4 and the alerts marker go back to risk."""
    defaults = AlertSettings()
    assert defaults.enabled is True
    assert defaults.notify_webhooks is True


# --- DL-9: who reads the stored cost_model -----------------------------------------------

#: Every module outside ``app/settings`` that may read the stored ``cost_model``:
#: the backtest endpoint (as its default rates) and the settings endpoint
#: itself. A new reader means the cost_model marker goes back to risk (DL-9).
STORED_COST_MODEL_READERS = frozenset({"app.api.backtest", "app.api.settings"})


def _reads_cost_model_attribute(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Attribute) and node.attr == "cost_model" for node in ast.walk(tree)
    )


def test_only_the_backtest_reads_the_stored_cost_model() -> None:
    readers = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT.parent)
        module = ".".join(relative.with_suffix("").parts).removesuffix(".__init__")
        if module.startswith("app.settings"):
            continue
        imports_settings = any(
            name.startswith("app.settings") for name in imported_modules(path, module)
        )
        if imports_settings and _reads_cost_model_attribute(path):
            readers.add(module)
    assert readers == STORED_COST_MODEL_READERS
