"""Cross-site request guard: state-changing requests must carry a custom header.

CORS stops another site from *reading* this API's responses, but not from
*sending* "simple" requests to it: a page the user happens to open can
auto-submit ``<form method=POST action="http://localhost:8000/...">`` with no
body, or with a multipart body, and FastAPI's JSON content-type check never
runs for those. That is enough to trigger an emergency exit, acknowledge every
alert, or import positions without the user knowing.

A browser never adds a custom header to a form post or an image load, and a
script that adds one triggers a CORS preflight that only the frontend origin
passes. Requiring :data:`CLIENT_HEADER` on every unsafe method therefore closes
that path for every current and future endpoint, without a per-route opt-in.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

#: Header the frontend sends on every state-changing request. Its value is not
#: checked; only a same-origin script (or a non-browser client) can set it.
CLIENT_HEADER = "X-Stock-Desk-Client"

#: Methods that must not change state, and so need no header.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

MISSING_HEADER_DETAIL = f"寫入型請求必須帶 {CLIENT_HEADER} header"

_HEADER_KEY = CLIENT_HEADER.lower().encode("latin-1")


class RequireClientHeaderMiddleware:
    """Reject any non-safe HTTP request that lacks :data:`CLIENT_HEADER` with 403."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        if any(key == _HEADER_KEY for key, _ in scope["headers"]):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": MISSING_HEADER_DETAIL}, ensure_ascii=False).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
