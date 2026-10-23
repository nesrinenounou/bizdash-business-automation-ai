"""Redis-backed cache/counters with an in-memory fallback, so dev and tests run without Redis
and a Redis outage degrades the app instead of breaking it."""
import logging, time
from typing import Optional

log = logging.getLogger("cache")


class Cache:
    def __init__(self, url: str = ""):
        self._mem: dict[str, tuple[str, float]] = {}
        self._redis = None
        if url:
            try:
                import redis
                client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1)
                client.ping()
                self._redis = client
            except Exception as exc:
                log.warning("Redis unavailable (%s): using in-memory cache", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    def _live(self, key: str) -> Optional[str]:
        item = self._mem.get(key)
        if item and (item[1] == 0 or item[1] > time.monotonic()):
            return item[0]
        self._mem.pop(key, None)
        return None

    def get(self, key: str) -> Optional[str]:
        if self._redis:
            try:
                return self._redis.get(key)
            except Exception as exc:
                log.warning("redis get failed: %s", exc)
        return self._live(key)

    def set(self, key: str, value: str, ttl: int = 0) -> None:
        if self._redis:
            try:
                self._redis.set(key, value, ex=ttl or None)
                return
            except Exception as exc:
                log.warning("redis set failed: %s", exc)
        self._mem[key] = (value, time.monotonic() + ttl if ttl else 0)

    def incr(self, key: str, ttl: int) -> int:
        """Atomic counter whose TTL starts at the first increment."""
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(key); pipe.expire(key, ttl, nx=True)
                return int(pipe.execute()[0])
            except Exception as exc:
                log.warning("redis incr failed: %s", exc)
        value = int(self._live(key) or 0) + 1
        old = self._mem.get(key)
        self._mem[key] = (str(value), old[1] if old and value > 1 else time.monotonic() + ttl)
        return value

    def delete(self, *keys: str) -> None:
        if self._redis:
            try:
                self._redis.delete(*keys)
            except Exception as exc:
                log.warning("redis delete failed: %s", exc)
        for k in keys:
            self._mem.pop(k, None)

    def clear(self) -> None:
        self._mem.clear()


from .config import settings  # noqa: E402

cache = Cache(settings.redis_url)
