from collections import OrderedDict
from collections.abc import Callable
from ipaddress import ip_address
from math import ceil
from threading import Lock
from time import monotonic

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import AppError, ErrorCode
from app.core.response import error_response


class IPRateLimiter:
    """Process-local fixed windows starting on each IP's first request."""

    def __init__(
        self,
        requests: int,
        window_seconds: int,
        max_ips: int,
        clock: Callable[[], float] = monotonic,
    ):
        if requests <= 0 or window_seconds <= 0 or max_ips <= 0:
            raise ValueError("Rate limit settings must be positive")
        self.requests = requests
        self.window_seconds = window_seconds
        self.max_ips = max_ips
        self.clock = clock
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def retry_after(self, ip: str) -> int:
        """Consume one request; return zero if allowed, else seconds to retry."""
        with self._lock:
            now = self.clock()
            # Insertion order is expiry order; accesses never extend a window.
            while self._windows and next(iter(self._windows.values()))[0] <= now:
                self._windows.popitem(last=False)
            window = self._windows.get(ip)
            if window is None:
                if len(self._windows) >= self.max_ips:
                    # ponytail: fail closed at capacity; shared storage if scale demands it.
                    # Do not evict live entries: IP churn must not reset other quotas.
                    expires, _ = next(iter(self._windows.values()))
                    return max(1, ceil(expires - now))
                window = (now + self.window_seconds, 0)
            expires, count = window
            if count >= self.requests:
                return max(1, ceil(expires - now))
            self._windows[ip] = (expires, count + 1)
            return 0


class IPRateLimitMiddleware:
    def __init__(self, app: ASGIApp, limiter: IPRateLimiter):
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].rstrip("/") == "/api/v1/problems"
        ):
            # Only use the server's client address, never parse forwarding headers here.
            # Uvicorn may rewrite this ONLY for explicitly trusted proxy peers.
            client = scope.get("client")
            try:
                ip = str(ip_address(client[0])) if client else "unknown"
            except ValueError:
                ip = "unknown"
            retry_after = self.limiter.retry_after(ip)
            if retry_after:
                response = error_response(
                    AppError(
                        code=ErrorCode.RATE_LIMITED,
                        message="Too many requests. Please retry later.",
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
