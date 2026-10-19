from functools import lru_cache

import redis

from backend.core.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis | None:
    """Shared Redis connection, or None when long-term memory is switched off.

    An empty `redis_url` disables the feature outright — tests and deployments without
    a Redis instance then take the same path as a Redis outage, which memory_service
    already treats as "no profile yet".

    `decode_responses=True` so callers get `str` back rather than `bytes`; the short
    timeouts keep a hung Redis from stalling a chat response, since a profile is a
    nice-to-have and never worth making the Sale wait for. One chat turn makes about
    five Redis calls, so at 2 s each an unreachable Redis alone blew the 5 s budget;
    a healthy Redis answers in milliseconds, so half a second is still generous.
    """
    settings = get_settings()
    if not settings.redis_url:
        return None

    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
