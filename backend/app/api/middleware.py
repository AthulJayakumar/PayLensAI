"""Small pilot security and structured-observability middleware."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("paylens.api")


class SecurityObservabilityMiddleware(BaseHTTPMiddleware):
    """Add pilot throttling, security headers, request IDs, and safe JSON logs."""
    def __init__(self, app, *, requests_per_minute: int = 120) -> None:
        super().__init__(app)
        self.limit = requests_per_minute
        self.windows: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        # Bound caller-provided IDs before reflecting them into responses/logs.
        started = time.perf_counter()
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:100]
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self.windows[client]
        # Retain only timestamps inside the rolling one-minute rate window.
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= self.limit and request.url.path != "/health":
            return JSONResponse(status_code=429, content={"error": {"code": "RATE_LIMITED", "message": "Too many requests."}})
        window.append(now)
        response = await call_next(request)
        # Reduce browser attack surface without logging payment/provider payloads.
        response.headers.update({
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "X-Request-ID": request_id,
        })
        logger.info(json.dumps({"event": "http_request", "request_id": request_id, "method": request.method,
                                "path": request.url.path, "status": response.status_code,
                                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}))
        return response
