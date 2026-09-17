"""Refuse oversized uploads before their body is read.

Starlette parses a multipart body (and spools file parts to disk) before an
endpoint runs, so a size check inside the endpoint would come after a huge
upload had already been received. This middleware checks the declared
``Content-Length`` first; the server guarantees a body is never longer than
declared. Uploads without a declared length are refused for the same reason.
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class UploadSizeLimit:
    """ASGI middleware limiting the request body size of one POST endpoint."""

    def __init__(self, app: ASGIApp, *, path: str, max_bytes: int) -> None:
        self._app = app
        self._path = path
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, or answer 411 or 413 without reading its body."""
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != self._path:
            await self._app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is None:
            response = JSONResponse({"detail": "Uploads must declare a Content-Length."}, 411)
        elif not declared.isdigit():
            response = JSONResponse({"detail": "Invalid Content-Length."}, 400)
        elif int(declared) > self._max_bytes:
            limit_mb = self._max_bytes // (1024 * 1024)
            response = JSONResponse({"detail": f"Uploads are limited to {limit_mb} MB."}, 413)
        else:
            await self._app(scope, receive, send)
            return
        await response(scope, receive, send)
