import json
import time
from typing import Any, Optional

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class DataCache:
    """Small cache wrapper with in-memory fallback and optional Redis."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._memory = {}
        self._redis = None
        if redis and redis_url:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def set(self, key: str, value: Any, ttl_sec: int = 60) -> None:
        payload = {"value": value, "expires_at": time.time() + ttl_sec}
        self._memory[key] = payload
        if self._redis is not None:
            self._redis.setex(key, ttl_sec, json.dumps(value))

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        payload = self._memory.get(key)
        if payload and payload["expires_at"] > now:
            return payload["value"]

        if self._redis is not None:
            raw = self._redis.get(key)
            if raw:
                return json.loads(raw)
        return None
