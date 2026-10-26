"""Web layer (FastAPI + Jinja2). Depends on ``services`` only."""

from flight_deals.web.server import CLIENT_HEADER, create_web_app

__all__ = ["CLIENT_HEADER", "create_web_app"]
