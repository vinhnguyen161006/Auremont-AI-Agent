import time
from functools import lru_cache

from qdrant_client import QdrantClient

from backend.core.config import get_settings


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=settings.qdrant_timeout_seconds,
    )


_KNOWN_COLLECTIONS_ATTR = "_salesmate_known_collections"
_COLLECTION_EXISTS_TTL_SECONDS = 60.0


def collection_exists_cached(client: QdrantClient, name: str) -> bool:
    """`client.collection_exists`, remembering a positive answer for a minute.

    Every chat turn asked Qdrant whether the document and cache collections exist before
    querying them — an extra network round trip each, on the hot path, for a fact that
    changes only when an Admin resets the cache. Only "exists" is remembered: a missing
    collection is re-checked every time so the first ingestion is picked up at once. The
    memo lives on the client object, so a test double never inherits another test's answer.
    """
    known: dict[str, float] = vars(client).setdefault(_KNOWN_COLLECTIONS_ATTR, {})
    now = time.monotonic()
    if known.get(name, 0.0) > now:
        return True
    exists = bool(client.collection_exists(name))
    if exists:
        known[name] = now + _COLLECTION_EXISTS_TTL_SECONDS
    else:
        known.pop(name, None)
    return exists


def forget_collection(client: QdrantClient, name: str) -> None:
    """Drop the remembered "exists" after deleting `name`."""
    vars(client).get(_KNOWN_COLLECTIONS_ATTR, {}).pop(name, None)
