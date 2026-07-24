"""FastAPI application entrypoint for the Stock Desk backend."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import portfolio, positions

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
