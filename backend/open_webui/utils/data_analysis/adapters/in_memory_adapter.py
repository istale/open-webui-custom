from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Callable

import duckdb
import pandas as pd

from open_webui.utils.data_analysis.repository import (
    DatasetMeta,
    DatasetNotFoundError,
    PermissionDeniedError,
    QueryResult,
    QuerySizeError,
    QueryTimeoutError,
    QueryValidationError,
    RepositoryHealth,
    RepositoryUnavailableError,
)


class InMemoryDatasetRepository:
    """Development/test adapter backed by local manufacturing fixture DataFrames."""

    _FAULT_HANDLERS: dict[str, Callable[[], None]] = {
        '_FAULT_TIMEOUT': lambda: (_ for _ in ()).throw(
            QueryTimeoutError('Simulated timeout (fault injection)')
        ),
        '_FAULT_NOT_FOUND': lambda: (_ for _ in ()).throw(
            DatasetNotFoundError('Simulated not found (fault injection)')
        ),
        '_FAULT_DENIED': lambda: (_ for _ in ()).throw(
            PermissionDeniedError('Simulated permission denied (fault injection)')
        ),
        '_FAULT_INVALID': lambda: (_ for _ in ()).throw(
            QueryValidationError('Simulated invalid query (fault injection)')
        ),
        '_FAULT_TOO_LARGE': lambda: (_ for _ in ()).throw(
            QuerySizeError('Simulated size limit exceeded (fault injection)')
        ),
        '_FAULT_UNAVAILABLE': lambda: (_ for _ in ()).throw(
            RepositoryUnavailableError('Simulated external system down (fault injection)')
        ),
    }

    def __init__(self, datasets: dict[str, tuple[DatasetMeta, pd.DataFrame]]):
        self._data = dict(datasets)

    def list_datasets(self, *, user_id: str, tags: list[str] | None = None) -> list[DatasetMeta]:
        requested_tags = set(tags or [])
        return [
            meta
            for meta, _ in self._data.values()
            if not requested_tags or requested_tags.intersection(meta.tags)
        ]

    def get_metadata(self, dataset_id: str, *, user_id: str) -> DatasetMeta:
        return self._get_dataset(dataset_id)[0]

    def execute_query(
        self,
        dataset_id: str,
        sql: str,
        *,
        user_id: str,
        max_rows: int = 10_000_000,
        timeout_s: int = 30,
    ) -> QueryResult:
        started = time.perf_counter()
        self._apply_faults(sql)
        if '_FAULT_SLOW_3S' in sql:
            time.sleep(3)

        _, df = self._get_dataset(dataset_id)
        clean_sql = self._strip_fault_markers(sql)
        self._validate_select_sql(clean_sql)

        try:
            result_df = self._execute_duckdb(dataset_id, df, clean_sql)
        except duckdb.Error as exc:
            raise QueryValidationError(str(exc)) from exc

        truncated = '_FAULT_TRUNCATED' in sql
        if len(result_df) > max_rows:
            truncated = True
            result_df = result_df.head(max_rows)

        row_count = max_rows if '_FAULT_TRUNCATED' in sql else len(result_df)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return QueryResult(
            df=result_df,
            row_count=row_count,
            truncated=truncated,
            elapsed_ms=elapsed_ms,
            cache_hit=False,
        )

    def get_value_at(
        self,
        dataset_id: str,
        *,
        user_id: str,
        column: str,
        index: dict[str, str],
    ) -> object:
        _, df = self._get_dataset(dataset_id)
        if column not in df.columns:
            raise QueryValidationError(f'Unknown column: {column}')

        mask = pd.Series([True] * len(df), index=df.index)
        for key, value in index.items():
            if key not in df.columns:
                raise QueryValidationError(f'Unknown index column: {key}')
            mask &= df[key].astype(str) == str(value)

        matches = df.loc[mask, column]
        if matches.empty:
            raise DatasetNotFoundError('No row matched the requested point lookup')
        return matches.iloc[0]

    def health_check(self) -> RepositoryHealth:
        return RepositoryHealth(
            available=True,
            latency_ms=0,
            last_check=datetime.now(timezone.utc),
            backend_version='in-memory',
            notes=None,
        )

    def _get_dataset(self, dataset_id: str) -> tuple[DatasetMeta, pd.DataFrame]:
        try:
            return self._data[dataset_id]
        except KeyError as exc:
            raise DatasetNotFoundError(dataset_id) from exc

    def _apply_faults(self, sql: str) -> None:
        for marker, handler in self._FAULT_HANDLERS.items():
            if marker in sql:
                handler()

    @staticmethod
    def _strip_fault_markers(sql: str) -> str:
        return re.sub(r'_FAULT_[A-Z0-9_]+', '', sql)

    @staticmethod
    def _validate_select_sql(sql: str) -> None:
        stripped = sql.lstrip()
        if not re.match(r'^(select|with)\b', stripped, flags=re.IGNORECASE):
            raise QueryValidationError('Only SELECT statements are allowed')

    @staticmethod
    def _execute_duckdb(dataset_id: str, df: pd.DataFrame, sql: str) -> pd.DataFrame:
        table_name = re.sub(r'\W+', '_', dataset_id).strip('_') or 'dataset'
        with duckdb.connect(database=':memory:') as connection:
            connection.register('df', df)
            connection.register(table_name, df)
            return connection.execute(sql).fetchdf()
