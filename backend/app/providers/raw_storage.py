"""S3-replaceable raw provider object storage contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import RLock

from app.providers.models import RawProviderObject


class RawProviderDataStore(ABC):
    @abstractmethod
    def put(self, item: RawProviderObject) -> str:
        """Durably store the original provider object and return its reference."""

    @abstractmethod
    def get(self, raw_id: str, merchant_id: str) -> RawProviderObject | None:
        """Retrieve an owned raw object."""


class InMemoryRawProviderDataStore(RawProviderDataStore):
    def __init__(self) -> None:
        self._items: dict[str, RawProviderObject] = {}
        self._lock = RLock()

    def put(self, item: RawProviderObject) -> str:
        with self._lock:
            self._items[item.id] = item
        return item.id

    def get(self, raw_id: str, merchant_id: str) -> RawProviderObject | None:
        with self._lock:
            item = self._items.get(raw_id)
        return item if item is not None and item.merchant_id == merchant_id else None
