"""FastAPI application entrypoint for the Stock Desk backend."""

from datetime import UTC, datetime

from fastapi import FastAPI

SERVICE_NAME = "backend"

app = FastAPI(title="Stock Desk Backend", version="0.1.0")


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
