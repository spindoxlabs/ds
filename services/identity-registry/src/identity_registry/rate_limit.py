"""A per-client request budget for the routes anyone can reach.

The public routes — DID documents, the trust and status lists, the STS, the
Issuer Service, the Credential Service — answer callers that hold no token yet,
so no identity can bound how often they are called. This bounds it per client
address instead: a token bucket of `RATE_PER_SECOND` refilled continuously, up to
`BURST`, and a `429` with `Retry-After` once it is empty.

The address is the one the ASGI server reports. Behind a proxy that is the
proxy's, unless the server is told to read the forwarded header from it
(uvicorn ``--proxy-headers`` with ``--forwarded-allow-ips``); this module never
reads a forwarded header itself, because any caller can write one.

In-process and per replica, deliberately: it is a floor under the cost a single
caller can impose on this process, not a quota. A shared quota belongs at the
edge.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict

from fastapi import HTTPException, Request, status

#: Sustained requests per second one client may make to the public routes.
RATE_PER_SECOND = 20.0
#: Requests one client may make at once before the sustained rate applies. A
#: DSP negotiation makes a handful of calls here in quick succession; this is
#: several negotiations' worth.
BURST = 60.0
#: Clients tracked at once. The least recently seen are forgotten first, which
#: hands a forgotten client a full bucket — the safe direction to err in.
MAX_CLIENTS = 10_000


class RateLimiter:
    """Token buckets keyed by client address."""

    def __init__(
        self,
        *,
        rate: float = RATE_PER_SECOND,
        burst: float = BURST,
        max_clients: int = MAX_CLIENTS,
        clock=time.monotonic,
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._max_clients = max_clients
        self._clock = clock
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def take(self, client: str) -> float:
        """Spend one request for *client*: ``0`` if allowed, else seconds to wait."""
        now = self._clock()
        tokens, seen = self._buckets.pop(client, (self._burst, now))
        tokens = min(self._burst, tokens + (now - seen) * self._rate)
        if tokens >= 1.0:
            tokens -= 1.0
            wait = 0.0
        else:
            wait = (1.0 - tokens) / self._rate
        self._buckets[client] = (tokens, now)
        while len(self._buckets) > self._max_clients:
            self._buckets.popitem(last=False)
        return wait


async def public_rate_limit(request: Request) -> None:
    """Router dependency for every public route. One budget per app instance."""
    limiter = getattr(request.app.state, "public_rate_limiter", None)
    if limiter is None:
        limiter = request.app.state.public_rate_limiter = RateLimiter()
    client = request.client.host if request.client else "unknown"
    wait = limiter.take(client)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(max(1, math.ceil(wait)))},
        )
