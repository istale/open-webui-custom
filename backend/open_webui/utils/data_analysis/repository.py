from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    dtype: str
    nullable: bool
    unit: str | None
    semantic: str | None


@dataclass(frozen=True)
class DatasetMeta:
    id: str
    name: str
    description: str
    row_count: int
    column_count: int
    columns: list[ColumnMeta]
    updated_at: datetime
    tags: list[str]


@dataclass(frozen=True)
class QueryResult:
    df: pd.DataFrame
    row_count: int
    truncated: bool
    elapsed_ms: int
    cache_hit: bool


@dataclass(frozen=True)
class RepositoryHealth:
    available: bool
    latency_ms: int
    last_check: datetime
    backend_version: str | None
    notes: str | None


class RepositoryError(Exception):
    """Stable base exception for the vertical data repository boundary."""


class DatasetNotFoundError(RepositoryError):
    """Dataset does not exist or is not visible through this repository."""


class PermissionDeniedError(RepositoryError):
    """User is authenticated but does not have access to the requested dataset."""


class QueryValidationError(RepositoryError):
    """Query is syntactically invalid or violates repository safety rules."""


class QueryTimeoutError(RepositoryError):
    """Query exceeded the requested or configured timeout."""


class QuerySizeError(RepositoryError):
    """Query result exceeded the allowed size."""


class RepositoryUnavailableError(RepositoryError):
    """Underlying dataset system is unavailable or returned an unmapped transport error."""


@runtime_checkable
class DatasetRepository(Protocol):
    """Vertical workspace contract with the manufacturing dataset system.

    Implementations should keep transport/schema concerns behind this Protocol
    so tools and routes never need to know whether data came from local
    fixtures, an HTTP service, or a future production historian.
    """

    def list_datasets(self, *, user_id: str, tags: list[str] | None = None) -> list[DatasetMeta]:
        """List datasets visible to user_id, optionally filtered by tags."""

    def get_metadata(self, dataset_id: str, *, user_id: str) -> DatasetMeta:
        """Get full dataset metadata."""

    def execute_query(
        self,
        dataset_id: str,
        sql: str,
        *,
        user_id: str,
        max_rows: int = 10_000_000,
        timeout_s: int = 30,
    ) -> QueryResult:
        """Run a SELECT query and return the resulting DataFrame."""

    def get_value_at(
        self,
        dataset_id: str,
        *,
        user_id: str,
        column: str,
        index: dict[str, str],
    ) -> object:
        """Point lookup for drill-down and tooltip workflows."""

    def health_check(self) -> RepositoryHealth:
        """Return health of the underlying dataset system."""
