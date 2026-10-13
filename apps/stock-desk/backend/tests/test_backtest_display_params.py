"""F11-A-35: the backtest report's display thresholds, pinned and kept apart.

Lives outside every ``test_kelly_*.py`` on purpose. It is the one test file that
reads both threshold families -- product code may not (PRD D-14) -- and it only
states their *relation*, never ties one to the other.
"""

from __future__ import annotations

from app.backtest import display_params
from app.backtest.display_params import N_MIN_DISPLAY, N_WORST
from app.kelly.sample_gate import MIN_OOS_ROUND_TRIPS, SOFT_WARNING_ROUND_TRIPS
from tests.import_graph import APP_ROOT, imported_modules, module_path


def test_the_registered_values_are_pinned() -> None:
    """(1) quant-researcher's registered values (§6 方法論登記)."""
    assert N_MIN_DISPLAY == 30
    assert N_WORST == 5


def test_the_display_minimum_sits_between_the_two_kelly_thresholds() -> None:
    """(2) The relation only. Red means review, not an automatic edit (F11-L-2)."""
    assert MIN_OOS_ROUND_TRIPS <= N_MIN_DISPLAY <= SOFT_WARNING_ROUND_TRIPS, (
        f"MIN_OOS_ROUND_TRIPS={MIN_OOS_ROUND_TRIPS}、N_MIN_DISPLAY={N_MIN_DISPLAY}、"
        f"SOFT_WARNING_ROUND_TRIPS={SOFT_WARNING_ROUND_TRIPS} 的關係改變："
        "回 quant 與風控重審（F11-L-2），不得自動改值。"
    )


def test_the_module_imports_no_application_code() -> None:
    """(3) Nothing from ``app`` -- no threshold is read, re-exported or bound here."""
    path = module_path("app.backtest.display_params")
    assert path == APP_ROOT / "backtest" / "display_params.py"
    assert imported_modules(path, "app.backtest.display_params") == set()


def test_the_module_defines_exactly_the_two_names() -> None:
    public = {name for name in vars(display_params) if name.isupper()}
    assert public == {"N_MIN_DISPLAY", "N_WORST"}
