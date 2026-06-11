"""Small in-memory TTL cache."""

from __future__ import annotations

import time
from typing import TypeVar

T = TypeVar("T")


class TTLCache[T]:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        item = self._items.get(key)
        if item is None:
            return None

        expires_at, value = item
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self._items[key] = (time.monotonic() + ttl_seconds, value)

    def clear(self) -> None:
        self._items.clear()
