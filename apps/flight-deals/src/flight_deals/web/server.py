"""FastAPI application: server-rendered pages plus a small JSON write API.

Every state-changing request must come from ``fetch()`` with the custom
``X-Flight-Deals-Client`` header (403 otherwise); Host is restricted to loopback names.
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
from starlette.middleware.trustedhost import TrustedHostMiddleware

from flight_deals.services import Services

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
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


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

    @app.middleware("http")
    async def require_client_header(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in SAFE_METHODS and not request.headers.get(CLIENT_HEADER):
            return JSONResponse(
                {"error": f"寫入請求必須由頁面腳本送出（缺少 {CLIENT_HEADER} header）"},
                status_code=403,
            )
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    # Added last so it runs first: reject unexpected Host headers (DNS rebinding).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def page(request: Request, name: str, context: dict[str, Any], status: int = 200) -> Response:
        context = {"nav": name, **services.views.base_context(), **context}
        return templates.TemplateResponse(request, name, context, status_code=status)

    def not_found(request: Request, message: str) -> Response:
        return page(request, "not_found.html", {"message": message}, status=404)

    def errors_response(errors: dict[str, str], status: int = 422) -> JSONResponse:
        return JSONResponse({"ok": False, "errors": errors}, status_code=status)

    # ---- pages -----------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Response:
        return page(request, "index.html", services.views.list_page())

    @app.get("/watches/new", response_class=HTMLResponse)
    def new_watch(request: Request) -> Response:
        return page(
            request,
            "watch_form.html",
            {"mode": "create", "watch_id": None, "values": services.views.form_values(None)},
        )

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
        return page(
            request, "watch_form.html", {"mode": "edit", "watch_id": watch_id, "values": values}
        )

    @app.get("/notifications", response_class=HTMLResponse)
    def notifications(request: Request) -> Response:
        return page(request, "notifications.html", services.views.notifications_page())

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> Response:
        return page(request, "settings.html", services.views.settings_page())

    # ---- JSON write API ----------------------------------------------------------

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
