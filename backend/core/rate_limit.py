"""Minimal per-IP throttle for endpoints reachable with no account.

The public customer chat endpoints (anonymous session creation, anonymous ask) are the
only ones in this app an unauthenticated caller can hit repeatedly for free — every other
route sits behind `require_role`, which already caps abuse to whoever holds a valid
internal/customer JWT. Without this, one visitor could script thousands of LLM calls.

In-process sliding window, no new dependency (no `slowapi`/Redis in requirements.txt).
Deliberately scoped: per-process only, resets on restart, not shared across workers.
Acceptable at this app's current single-instance scale; revisit with Redis if it is ever
run with multiple backend workers/processes.

`/auth/login` gets its own bucket: without one, a password can be guessed at bcrypt speed
for as long as the attacker likes. It is kept apart from the anonymous chat budget so a
visitor who used up their chat allowance can still sign in from the same address.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from backend.core.config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)

LOGIN_ATTEMPTS_PER_WINDOW = 10
LOGIN_WINDOW_SECONDS = 300
# Above this many tracked buckets, buckets with no hit inside any window are dropped, so
# one-off visitors do not accumulate in memory until the next restart.
_MAX_TRACKED_BUCKETS = 10_000

_TOO_MANY_REQUESTS_MESSAGE = "Quá nhiều yêu cầu, vui lòng thử lại sau ít phút."


def _client_ip(request: Request) -> str:
    """The address to throttle on, honouring X-Forwarded-For only as far as it is trustworthy.

    Behind a proxy every request's socket peer is the proxy itself, so throttling on it puts
    all visitors in one bucket. But X-Forwarded-For is client-settable: trusting it outright
    lets one visitor forge a new IP per request and bypass the limit completely. So the value
    is only read when `trusted_proxy_count` says how many proxies actually sit in front, and
    then only the hop that many places from the right — the last entry a trusted proxy wrote.
    Anything further left was supplied by the client and is ignored.
    """
    peer = request.client.host if request.client else "unknown"

    hops = settings.trusted_proxy_count
    if hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    chain = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if not chain:
        return peer

    return chain[-hops] if len(chain) >= hops else chain[0]


def _consume(bucket: str, limit: int, window_seconds: float) -> None:
    """Record one hit in `bucket`, raising 429 once `limit` hits fall inside the window."""
    now = time.monotonic()
    if len(_hits) > _MAX_TRACKED_BUCKETS:
        _forget_idle_buckets(now)

    hits = _hits[bucket]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()

    if len(hits) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_TOO_MANY_REQUESTS_MESSAGE)

    hits.append(now)


def _forget_idle_buckets(now: float) -> None:
    longest_window = max(settings.anonymous_rate_limit_window_seconds, LOGIN_WINDOW_SECONDS)
    for bucket in [key for key, hits in _hits.items() if not hits or now - hits[-1] > longest_window]:
        del _hits[bucket]


def anonymous_rate_limit(request: Request) -> None:
    """FastAPI dependency: raise 429 once an IP exceeds the configured window/count."""
    _consume(
        f"anonymous:{_client_ip(request)}",
        settings.anonymous_rate_limit_per_window,
        settings.anonymous_rate_limit_window_seconds,
    )


def login_rate_limit(request: Request) -> None:
    """FastAPI dependency: raise 429 once an IP exceeds the login attempt budget."""
    _consume(f"login:{_client_ip(request)}", LOGIN_ATTEMPTS_PER_WINDOW, LOGIN_WINDOW_SECONDS)
