"""FastAPI application: server-rendered pages plus a small JSON write API.

Every state-changing request must come from ``fetch()`` with the custom
``X-Flight-Deals-Client`` header (403 otherwise); Host is restricted to loopback names.
Security headers are added by an outermost pure ASGI middleware, so early 400/403
answers carry them too (500 pages from ``ServerErrorMiddleware`` are out of reach).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from flight_deals.services import EXPLORATION_NOT_FOUND, Services
from flight_deals.services import airports as airport_lookup

WEB_DIR = Path(__file__).resolve().parent
CLIENT_HEADER = "X-Flight-Deals-Client"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

JsonBody = Annotated[dict[str, Any], Body()]
AIRPORTS_CACHE_CONTROL = "private, max-age=300"
NO_STORE = {"Cache-Control": "no-store"}
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class SecurityHeadersMiddleware:
    """Pure ASGI: add any missing security header to every HTTP response start."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)  # a route's own value wins
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def require_client_header(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """403 for state-changing requests that did not come from the page script."""
    if request.method not in SAFE_METHODS and not request.headers.get(CLIENT_HEADER):
        return JSONResponse(
            {"error": f"寫入請求必須由頁面腳本送出（缺少 {CLIENT_HEADER} header）"},
            status_code=403,
        )
    return await call_next(request)


def build_templates() -> Jinja2Templates:
    env = Environment(
        loader=FileSystemLoader(str(WEB_DIR / "templates")),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return Jinja2Templates(env=env)


def create_web_app(services: Services, *, lifespan: Lifespan | None = None) -> FastAPI:
    app = FastAPI(
        title="flight-deals",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    templates = build_templates()

    # The last middleware added runs first. Request order, outermost first:
    # SecurityHeaders -> TrustedHost (400, DNS rebinding) -> client header (403) -> router.
    app.add_middleware(BaseHTTPMiddleware, dispatch=require_client_header)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def page(request: Request, name: str, context: dict[str, Any], status: int = 200) -> Response:
        context = {"nav": name, **services.views.base_context(), **context}
        return templates.TemplateResponse(request, name, context, status_code=status)

    def not_found(request: Request, message: str) -> Response:
        return page(request, "not_found.html", {"message": message}, status=404)

    def form_context(
        mode: str, watch_id: int | None, values: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "watch_id": watch_id,
            "values": values,
            **services.views.form_options(values),
        }

    def errors_response(errors: dict[str, str], status: int = 422) -> JSONResponse:
        return JSONResponse({"ok": False, "errors": errors}, status_code=status)

    # ---- pages -----------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Response:
        return page(request, "index.html", services.views.list_page())

    @app.get("/watches/new", response_class=HTMLResponse)
    def new_watch(
        request: Request,
        from_exploration: str | None = None,
        depart: str | None = None,
        mode: str | None = None,
    ) -> Response:
        values = services.views.form_values(None)
        extra: dict[str, Any] = {}
        if from_exploration is not None:
            # Prefill only: nothing is written, the user still submits (FD-6 Decision 6).
            assert values is not None
            values, note, sampled = services.exploration_views.watch_prefill(
                values, from_exploration, depart, mode
            )
            extra = {"prefill_note": note, "prefill_sampled_note": sampled}
        return page(
            request,
            "watch_form.html",
            {**form_context("create", None, values), **extra},
        )

    @app.get("/explore", response_class=HTMLResponse)
    def explore(request: Request) -> Response:
        return page(request, "explore.html", services.exploration_views.explore_page())

    @app.get("/explorations/{exploration_id}", response_class=HTMLResponse)
    def exploration_detail(request: Request, exploration_id: int) -> Response:
        data = services.exploration_views.exploration_page(exploration_id)
        if data is None:
            return not_found(request, EXPLORATION_NOT_FOUND)
        return page(request, "exploration.html", data)

    @app.get("/watches/{watch_id}", response_class=HTMLResponse)
    def watch_detail(request: Request, watch_id: int) -> Response:
        data = services.views.detail_page(watch_id)
        if data is None:
            return not_found(request, "找不到此監看，可能已被刪除。")
        return page(request, "watch_detail.html", data)

    @app.get("/watches/{watch_id}/edit", response_class=HTMLResponse)
    def edit_watch(request: Request, watch_id: int) -> Response:
        values = services.views.form_values(watch_id)
        if values is None:
            return not_found(request, "找不到此監看，可能已被刪除。")
        return page(request, "watch_form.html", form_context("edit", watch_id, values))

    @app.get("/notifications", response_class=HTMLResponse)
    def notifications(request: Request) -> Response:
        return page(request, "notifications.html", services.views.notifications_page())

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> Response:
        return page(request, "settings.html", services.views.settings_page())

    # ---- JSON read API -----------------------------------------------------------

    @app.get("/api/airports")
    def api_airports(q: str = "") -> JSONResponse:
        # C-20: bounded input, at most MAX_RESULTS items, cacheable (static table).
        query = q.strip()
        if len(query) > airport_lookup.MAX_QUERY_LENGTH:
            return errors_response(
                {"q": f"搜尋文字最多 {airport_lookup.MAX_QUERY_LENGTH} 字"}, status=422
            )
        items = airport_lookup.suggest(query) if query else []
        return JSONResponse(
            {"items": items[: airport_lookup.MAX_RESULTS]},
            headers={"Cache-Control": AIRPORTS_CACHE_CONTROL},
        )

    @app.get("/api/watches/{watch_id}/scan-status")
    def api_scan_status(watch_id: int) -> JSONResponse:
        # C-30: read-only, whitelisted fields, never cached; polled by the detail page.
        status = services.views.scan_status(watch_id)
        if status is None:
            return JSONResponse(
                {"ok": False, "errors": {"_": "找不到此監看"}}, status_code=404, headers=NO_STORE
            )
        return JSONResponse(status, headers=NO_STORE)

    @app.get("/api/explorations/{exploration_id}/status")
    def api_exploration_status(exploration_id: int) -> JSONResponse:
        # C-46: read-only, four whitelisted fields, never cached, no header needed.
        status = services.exploration.status(exploration_id)
        if status is None:
            return JSONResponse(
                {"ok": False, "errors": {"_": EXPLORATION_NOT_FOUND}},
                status_code=404,
                headers=NO_STORE,
            )
        return JSONResponse(status, headers=NO_STORE)

    # ---- JSON write API ----------------------------------------------------------

    @app.post("/api/explorations")
    def api_create_exploration(payload: JsonBody) -> JSONResponse:
        result = services.exploration.create(payload)
        if result.status == "invalid":
            return errors_response(result.errors)
        if result.ok:
            return JSONResponse(
                {"ok": True, "id": result.exploration_id, "reused": result.status == "reused"},
                status_code=202 if result.status == "created" else 200,
            )
        body: dict[str, Any] = {"ok": False, "code": result.status, "message": result.message}
        if result.status == "quota":
            body.update(hourly_left=result.hourly_left, needed=result.needed)
        if result.exploration_id is not None:
            body["id"] = result.exploration_id
        return JSONResponse(body, status_code=409)

    @app.post("/api/watches")
    def api_create_watch(payload: JsonBody) -> JSONResponse:
        result = services.watches.create(payload)
        if not result.ok:
            return errors_response(result.errors)
        return JSONResponse({"ok": True, "id": result.watch_id}, status_code=201)

    @app.put("/api/watches/{watch_id}")
    def api_update_watch(watch_id: int, payload: JsonBody) -> JSONResponse:
        result = services.watches.update(watch_id, payload)
        if result.watch_id is None:
            return errors_response(result.errors, status=404)
        if not result.ok:
            return errors_response(result.errors)
        return JSONResponse({"ok": True, "id": watch_id})

    @app.post("/api/watches/{watch_id}/status")
    def api_set_status(watch_id: int, payload: JsonBody) -> JSONResponse:
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            return errors_response({"enabled": "enabled 必須是 true 或 false"})
        result = services.watches.set_enabled(watch_id, enabled)
        if result.watch_id is None:
            return errors_response(result.errors, status=404)
        if not result.ok:
            return errors_response(result.errors, status=409)
        return JSONResponse({"ok": True})

    @app.delete("/api/watches/{watch_id}")
    def api_delete_watch(watch_id: int) -> JSONResponse:
        if not services.watches.delete(watch_id):
            return errors_response({"_": "找不到此監看"}, status=404)
        return JSONResponse({"ok": True})

    @app.post("/api/watches/{watch_id}/scan")
    def api_scan_now(watch_id: int) -> JSONResponse:
        result = services.watches.request_scan(watch_id)
        if result.watch_id is None:
            return errors_response(result.errors, status=404)
        if not result.ok:
            return errors_response(result.errors, status=409)
        return JSONResponse({"ok": True, "message": result.message}, status_code=202)

    @app.post("/api/settings")
    def api_update_settings(payload: JsonBody) -> JSONResponse:
        errors = services.settings.update(payload)
        if errors:
            return errors_response(errors)
        return JSONResponse({"ok": True})

    @app.post("/api/telegram/test")
    def api_telegram_test() -> JSONResponse:
        result = services.notifications.send_test()
        if result.ok:
            return JSONResponse({"ok": True, "message": "測試訊息已送出，請到 Telegram 確認"})
        return JSONResponse({"ok": False, "error": result.error or "送出失敗"}, status_code=502)

    return app
