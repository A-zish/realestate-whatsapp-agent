"""In-memory rate limits for a single Render instance.

Enough for a builder pilot. Keys are strings (IP, token, slug). Hits older
than the window are dropped on each check.
"""
from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, *, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        bucket = [t for t in self._hits[key] if now - t < window_s]
        if len(bucket) >= limit:
            self._hits[key] = bucket
            return False
        bucket.append(now)
        self._hits[key] = bucket
        return True


limiter = RateLimiter()


def client_ip(headers_host: dict | None, client_host: str | None) -> str:
    """Best-effort IP. Render sits behind a proxy and sets X-Forwarded-For."""
    forwarded = ""
    if headers_host:
        forwarded = (headers_host.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or client_host or "unknown"
