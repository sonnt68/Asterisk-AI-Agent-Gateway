"""Browser request protections layered on strict session cookies."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BrowserOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, allowed_origin: str) -> None:
        super().__init__(app)
        self.allowed_origin = allowed_origin.rstrip("/")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        unsafe = request.method not in {"GET", "HEAD", "OPTIONS"}
        has_session = bool(request.cookies.get("gateway_session"))
        if unsafe and has_session:
            origin = (request.headers.get("origin") or "").rstrip("/")
            if origin != self.allowed_origin:
                return JSONResponse(
                    {"detail": "Browser request origin is not allowed"}, status_code=403
                )
        return await call_next(request)
