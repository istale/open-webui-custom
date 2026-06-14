from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class QueryCacheEntry:
    query_id: str
    dataset_id: str
    sql: str
    df: 'pd.DataFrame'
    user_id: str
    row_count: int
    created_at: float
    expires_at: float


class QueryCache:
    """Small in-process LRU/TTL cache for full query DataFrames.

    The LLM receives only previews and statistics. Full result sets stay
    server-side and are referenced by query_id so render_chart can use the
    complete DataFrame without pushing million-row payloads through chat.
    """

    def __init__(self, max_entries: int = 64):
        self._max_entries = max_entries
        self._entries: dict[str, QueryCacheEntry] = {}
        self._access_times: dict[str, float] = {}
        self._lock = RLock()

    def put(
        self,
        *,
        dataset_id: str,
        sql: str,
        df: 'pd.DataFrame',
        user_id: str,
        row_count: int,
        ttl_s: int = 3600,
    ) -> str:
        now = time.time()
        query_id = uuid4().hex
        entry = QueryCacheEntry(
            query_id=query_id,
            dataset_id=dataset_id,
            sql=sql,
            df=df,
            user_id=user_id,
            row_count=row_count,
            created_at=now,
            expires_at=now + ttl_s,
        )
        with self._lock:
            self._entries[query_id] = entry
            self._access_times[query_id] = now
            self._evict(now)
        return query_id

    def get(self, query_id: str, *, user_id: str | None = None) -> QueryCacheEntry | None:
        now = time.time()
        with self._lock:
            entry = self._entries.get(query_id)
            if entry is None:
                return None
            if entry.expires_at <= now or (user_id is not None and entry.user_id != user_id):
                self._entries.pop(query_id, None)
                self._access_times.pop(query_id, None)
                return None
            self._access_times[query_id] = now
            return entry

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._access_times.clear()

    def _evict(self, now: float) -> None:
        expired = [query_id for query_id, entry in self._entries.items() if entry.expires_at <= now]
        for query_id in expired:
            self._entries.pop(query_id, None)
            self._access_times.pop(query_id, None)

        overflow = len(self._entries) - self._max_entries
        if overflow <= 0:
            return
        oldest = sorted(self._access_times.items(), key=lambda item: item[1])[:overflow]
        for query_id, _ in oldest:
            self._entries.pop(query_id, None)
            self._access_times.pop(query_id, None)


_query_cache = QueryCache()


def get_query_cache() -> QueryCache:
    return _query_cache
