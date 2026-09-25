"""FastAPI application entrypoint for the Stock Desk backend."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    advice,
    alerts,
    backtest,
    bars,
    directory,
    event_study,
    kelly,
    leverage,
    playbook,
    portfolio,
    positions,
    sectors,
    settings,
    signals,
)
from app.services.sector_runtime import process_gate_runtime

SERVICE_NAME = "backend"

#: Frontend dev server origin allowed to call this API during development.
FRONTEND_DEV_ORIGIN = "http://localhost:3000"

app = FastAPI(title="Stock Desk Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_DEV_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(positions.router)
app.include_router(portfolio.router)
app.include_router(bars.router)
app.include_router(signals.router)
app.include_router(advice.router)
app.include_router(leverage.router)
app.include_router(backtest.router)
app.include_router(event_study.router)
app.include_router(settings.router)
app.include_router(alerts.router)
app.include_router(directory.router)
app.include_router(playbook.router)
app.include_router(kelly.router)
app.include_router(sectors.router)
# The sector card's gate inputs come from the services layer, wired here so the
# read-only router never reaches it (ADR-0012 D-1, C-5).
sectors.install_gate_runtime(app, process_gate_runtime)


@app.get("/health")
def health() -> dict[str, str]:
    """Return service liveness with a UTC ISO8601 timestamp.

    The ``as_of`` field follows the company data convention that every
    response object carries the time at which it was produced.
    """
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "as_of": datetime.now(UTC).isoformat(),
    }
