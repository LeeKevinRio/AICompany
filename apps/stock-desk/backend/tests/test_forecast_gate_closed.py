"""The forecast write gate stays closed while only B1 and B2 exist (ADR-0027 D-14).

B1 and B2 add pure modules and wire none of them: the scheduler registers no
``forecast_record`` job (nor any ``forecast*`` job), ``app.main`` mounts no
``/api/forecast`` or ``/api/outlook`` route, and neither ``app.main`` nor
``app.scheduler`` reaches ``app.forecast``, ``app.outlook``, ``app.ops_alert`` or
``app.dirdef`` through imports. Each scan has a teeth test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from apscheduler.schedulers.blocking import BlockingScheduler
from fastapi import FastAPI

from app import scheduler as scheduler_module
from app.main import app
from app.settings.store import SettingsStore
from tests.import_graph import offenders, reachable_app_modules

NEW_PACKAGES = ("app.forecast", "app.outlook", "app.ops_alert", "app.dirdef")
ENTRY_POINTS = ("app.main", "app.scheduler")
CLOSED_PREFIXES = ("/api/forecast", "/api/outlook")


def _forecast_jobs(engine: BlockingScheduler) -> list[str]:
    return sorted(job.id for job in engine.get_jobs() if job.id.startswith("forecast"))


def _closed_routes(application: FastAPI, prefix: str) -> list[str]:
    return sorted(
        path
        for route in application.routes
        if (path := getattr(route, "path", "")).startswith(prefix)
    )


def test_no_forecast_job_is_scheduled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: settings)
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    ids = {job.id for job in engine.get_jobs()}
    assert "forecast_record" not in ids
    assert _forecast_jobs(engine) == []


@pytest.mark.parametrize("prefix", CLOSED_PREFIXES)
def test_no_forecast_or_outlook_route_is_mounted(prefix: str) -> None:
    assert _closed_routes(app, prefix) == []


@pytest.mark.parametrize("package", NEW_PACKAGES)
def test_the_entry_points_reach_none_of_the_new_packages(package: str) -> None:
    assert offenders(reachable_app_modules(ENTRY_POINTS), package) == []


def test_the_job_scan_has_teeth() -> None:
    engine = BlockingScheduler(timezone="UTC")
    engine.add_job(lambda: None, trigger="interval", minutes=60, id="forecast_record")
    assert _forecast_jobs(engine) == ["forecast_record"]


def test_the_route_scan_has_teeth() -> None:
    probe = FastAPI()

    @probe.get("/api/outlook/symbols/{symbol}")
    def _outlook(symbol: str) -> dict[str, str]:  # pragma: no cover - never served
        return {}

    assert _closed_routes(probe, "/api/outlook") == ["/api/outlook/symbols/{symbol}"]


def test_the_reachability_scan_has_teeth() -> None:
    # band.py's one app.* import is the violation list in errors.py (C2), so a
    # walk from band reaches errors: the walk does follow app.forecast imports.
    reachable = reachable_app_modules(("app.forecast.band",))
    assert "app.forecast.errors" in reachable
    assert "app.forecast.errors" in offenders(reachable, "app.forecast")
