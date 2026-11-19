"""Only job ``forecast_record`` is wired, and there is still no route (ADR-0030 D-10, S-11, K-3).

ADR-0030 D-10 kept this file until the wiring PR and changed it there to
"only job ``forecast_record`` is allowed, still no route": the scheduler
registers exactly one ``forecast*`` job, ``forecast_record``; ``app.main``
mounts no ``/api/forecast`` or ``/api/outlook`` route (D-4 point 6) and reaches
none of ``app.forecast``, ``app.outlook``, ``app.dirdef`` or ``app.ops_alert``
through imports (K-3); ``app.scheduler`` still does not reach ``app.ops_alert``
(D-10: unused). Each scan has a teeth test.
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
CLOSED_PREFIXES = ("/api/forecast", "/api/outlook")


def _forecast_jobs(engine: BlockingScheduler) -> list[str]:
    return sorted(job.id for job in engine.get_jobs() if job.id.startswith("forecast"))


def _closed_routes(application: FastAPI, prefix: str) -> list[str]:
    return sorted(
        path
        for route in application.routes
        if (path := getattr(route, "path", "")).startswith(prefix)
    )


def test_the_one_forecast_job_is_forecast_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: settings)
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    assert _forecast_jobs(engine) == ["forecast_record"]


@pytest.mark.parametrize("prefix", CLOSED_PREFIXES)
def test_no_forecast_or_outlook_route_is_mounted(prefix: str) -> None:
    assert _closed_routes(app, prefix) == []


@pytest.mark.parametrize("package", NEW_PACKAGES)
def test_the_api_reaches_none_of_the_new_packages(package: str) -> None:
    assert offenders(reachable_app_modules(("app.main",)), package) == []


def test_the_scheduler_does_not_reach_ops_alert() -> None:
    assert offenders(reachable_app_modules(("app.scheduler",)), "app.ops_alert") == []


def test_the_job_scan_has_teeth() -> None:
    engine = BlockingScheduler(timezone="UTC")
    engine.add_job(lambda: None, trigger="interval", minutes=60, id="forecast_record")
    engine.add_job(lambda: None, trigger="interval", minutes=60, id="forecast_extra")
    assert _forecast_jobs(engine) == ["forecast_extra", "forecast_record"]


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
    # And the scheduler now does reach the core.
    assert offenders(reachable_app_modules(("app.scheduler",)), "app.forecast") != []
