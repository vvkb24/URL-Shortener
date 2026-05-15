"""Redis cache connection and operations."""

import redis

from app.config import REDIS_HOST, REDIS_PORT, CACHE_TTL_SECONDS


# Redis client — connection is lazy, established on first command
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True,  # Return strings instead of bytes
)


def cache_url(short_code: str, original_url: str) -> None:
    """Cache a short_code -> original_url mapping with TTL."""
    redis_client.setex(
        name=f"url:{short_code}",
        time=CACHE_TTL_SECONDS,
        value=original_url,
    )


def get_cached_url(short_code: str) -> str | None:
    """Retrieve a cached URL by short_code. Returns None on cache miss."""
    return redis_client.get(f"url:{short_code}")


def increment_clicks(short_code: str) -> None:
    """Increment the click counter in Redis for batch flushing later."""
    redis_client.incr(f"clicks:{short_code}")


def get_click_count(short_code: str) -> int:
    """Get the pending click count from Redis."""
    count = redis_client.get(f"clicks:{short_code}")
    return int(count) if count else 0


def delete_cached_url(short_code: str) -> None:
    """Remove a URL from the cache (used on deletion)."""
    redis_client.delete(f"url:{short_code}")


def check_health() -> bool:
    """Check if Redis is reachable."""
    try:
        return redis_client.ping()
    except Exception:
        return False
