# AEGIS v6.0 - Quantum AI Futures Extension | Purpose: Async cache wrapper using Redis when available, fallback TTL dict.
import asyncio
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._redis = None
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        try:
            import redis.asyncio as redis  # type: ignore
            self._redis = redis.from_url(redis_url, decode_responses=True)
        except Exception as exc:
            logger.warning("[quantum.cache] Redis unavailable, using in-memory TTL cache: %s", exc)
            self._redis = None

    async def get(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                value = await self._redis.get(key)
                if value is None:
                    return None
                return json.loads(value)
            except Exception as exc:
                logger.warning("[quantum.cache] Redis GET failed, fallback in-memory: %s", exc)

        async with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expiry, value = item
            if time.time() >= expiry:
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._redis is not None:
            try:
                await self._redis.setex(key, ttl_seconds, json.dumps(value))
                return
            except Exception as exc:
                logger.warning("[quantum.cache] Redis SETEX failed, fallback in-memory: %s", exc)

        async with self._lock:
            self._store[key] = (time.time() + max(1, ttl_seconds), value)
