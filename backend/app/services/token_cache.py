from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class CachedToken:
    access_token: str
    expires_at: float  # Unix timestamp


class TokenCache:
    def __init__(self, buffer_seconds: int = 300):
        self._lock = threading.RLock()
        self._cache: Dict[str, CachedToken] = {}
        self._buffer_seconds = buffer_seconds

    def get(self, account_id: str) -> Optional[str]:
        with self._lock:
            cached = self._cache.get(account_id)
            if not cached:
                return None
            if time.time() >= cached.expires_at - self._buffer_seconds:
                del self._cache[account_id]
                return None
            return cached.access_token

    def set(self, account_id: str, access_token: str, expires_in: int) -> None:
        with self._lock:
            expires_at = time.time() + expires_in
            self._cache[account_id] = CachedToken(
                access_token=access_token,
                expires_at=expires_at,
            )

    def delete(self, account_id: str) -> None:
        with self._lock:
            self._cache.pop(account_id, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


# Global token cache instance
token_cache = TokenCache()
