"""Answer an unhandled exception with a 500 that still passes through CORS.

Starlette's ``ServerErrorMiddleware`` -- the layer that turns an unhandled
exception into ``500 Internal Server Error`` -- always sits *outside* every
middleware the app adds, CORS included. Its response therefore carries no
``Access-Control-Allow-Origin``, and the browser reports a CORS failure and
``net::ERR_FAILED`` instead of the 500, hiding what actually went wrong (N-154:
a migration race read as a CORS bug).

:class:`CorsVisibleServerErrorMiddleware` sits inside CORS and sends that same
plain-text 500 itself, so CORS decorates it like any other response. It then
re-raises the exception unchanged: ``ServerErrorMiddleware`` sees a response
already started, sends nothing more and lets the exception reach the server,
which logs the traceback exactly as before (and ``TestClient`` still raises it
unless told not to). An exception after the response has started is only
re-raised -- a second response cannot be sent then.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY = b"Internal Server Error"


class CorsVisibleServerErrorMiddleware:
    """Send a plain 500 for an unhandled exception, then re-raise it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            if not response_started:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(_BODY)).encode("latin-1")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": _BODY})
            raise
