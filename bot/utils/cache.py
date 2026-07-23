"""Simple TTL cache for Shelfie bot."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


class Cache:
    """Simple in-memory TTL cache."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and hasn't expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if entry["expires_at"] < datetime.utcnow():
                # Expired - remove and return None
                del self._cache[key]
                return None
            return entry["value"]

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set a value in the cache with TTL."""
        async with self._lock:
            self._cache[key] = {
                "value": value,
                "expires_at": datetime.utcnow() + timedelta(seconds=ttl),
            }

    async def clear(self) -> None:
        """Clear the entire cache."""
        async with self._lock:
            self._cache.clear()
