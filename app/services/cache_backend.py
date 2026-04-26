from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class RedisJsonCacheBackend:
    redis_url: str = ""
    key_prefix: str = "knowledgeops:retrieval:"
    socket_timeout_seconds: float = 0.2
    _client: object | None = field(default=None, init=False, repr=False)
    _available: bool = field(default=False, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    _last_error: str = field(default="", init=False, repr=False)
    _hits: int = field(default=0, init=False, repr=False)
    _misses: int = field(default=0, init=False, repr=False)
    _writes: int = field(default=0, init=False, repr=False)

    @property
    def enabled(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def available(self) -> bool:
        self._ensure_client()
        return self._available

    def get_json(self, key: str) -> dict[str, object] | None:
        client = self._ensure_client()
        if client is None:
            self._misses += 1
            return None
        try:
            raw = client.get(self._full_key(key))
        except Exception as exc:  # pragma: no cover - runtime fallback
            self._last_error = str(exc)
            self._available = False
            self._misses += 1
            return None
        if not raw:
            self._misses += 1
            return None
        self._hits += 1
        return json.loads(str(raw))

    def set_json(self, key: str, payload: dict[str, object], ttl_seconds: float) -> bool:
        client = self._ensure_client()
        if client is None:
            return False
        try:
            client.set(self._full_key(key), json.dumps(payload, ensure_ascii=False), ex=max(int(ttl_seconds), 1))
            self._writes += 1
            return True
        except Exception as exc:  # pragma: no cover - runtime fallback
            self._last_error = str(exc)
            self._available = False
            return False

    def stats(self) -> dict[str, object]:
        return {
            "backend": "redis" if self.available else "memory",
            "enabled": self.enabled,
            "available": self._available,
            "hits": self._hits,
            "misses": self._misses,
            "writes": self._writes,
            "last_error": self._last_error,
        }

    def _ensure_client(self):
        if self._initialized:
            return self._client if self._available else None

        self._initialized = True
        if not self.enabled:
            self._available = False
            return None

        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=self.socket_timeout_seconds,
                socket_timeout=self.socket_timeout_seconds,
            )
            client.ping()
            self._client = client
            self._available = True
            self._last_error = ""
            return client
        except Exception as exc:  # pragma: no cover - optional dependency / runtime env
            self._client = None
            self._available = False
            self._last_error = str(exc)
            return None

    def _full_key(self, key: str) -> str:
        return f"{self.key_prefix}{key}"
