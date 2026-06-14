from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import httpx
import pandas as pd

from open_webui.utils.data_analysis.repository import (
    ColumnMeta,
    DatasetMeta,
    DatasetNotFoundError,
    PermissionDeniedError,
    QueryResult,
    QuerySizeError,
    QueryTimeoutError,
    QueryValidationError,
    RepositoryError,
    RepositoryHealth,
    RepositoryUnavailableError,
)


class HttpDatasetRepository:
    """HTTP adapter for the external manufacturing data platform."""

    PROTOCOL_VERSION = 'v1'

    _ERROR_MAPPING = {
        'DATASET_NOT_FOUND': DatasetNotFoundError,
        'PERMISSION_DENIED': PermissionDeniedError,
        'QUERY_INVALID': QueryValidationError,
        'QUERY_TIMEOUT': QueryTimeoutError,
        'QUERY_TOO_LARGE': QuerySizeError,
    }

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_s: int = 30,
        retries: int = 2,
        client: httpx.Client | None = None,
    ):
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={
                'Authorization': f'Bearer {service_token}',
                'X-Protocol-Version': self.PROTOCOL_VERSION,
            },
            timeout=timeout_s,
        )
        self._retries = retries

    def list_datasets(self, *, user_id: str, tags: list[str] | None = None) -> list[DatasetMeta]:
        params: dict[str, Any] = {'user_id': user_id}
        if tags:
            params['tags'] = ','.join(tags)
        response = self._get('/datasets', params=params)
        return [self._dataset_meta_from_dto(item) for item in response.get('items', [])]

    def get_metadata(self, dataset_id: str, *, user_id: str) -> DatasetMeta:
        response = self._get(f'/datasets/{dataset_id}', params={'user_id': user_id})
        return self._dataset_meta_from_dto(response)

    def execute_query(
        self,
        dataset_id: str,
        sql: str,
        *,
        user_id: str,
        max_rows: int = 10_000_000,
        timeout_s: int = 30,
    ) -> QueryResult:
        response = self._post(
            f'/datasets/{dataset_id}/query',
            json={
                'sql': sql,
                'user_id': user_id,
                'max_rows': max_rows,
                'timeout_s': timeout_s,
                'format': 'arrow',
            },
            expect_json=False,
        )
        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            payload = response.json()
            df = pd.DataFrame(payload.get('records', []))
        else:
            df = pd.read_feather(BytesIO(response.content))
        return QueryResult(
            df=df,
            row_count=int(response.headers.get('X-Row-Count', len(df))),
            truncated=response.headers.get('X-Truncated', '').lower() == 'true',
            elapsed_ms=int(response.headers.get('X-Elapsed-Ms', '0')),
            cache_hit=response.headers.get('X-Cache', '').lower() == 'hit',
        )

    def get_value_at(
        self,
        dataset_id: str,
        *,
        user_id: str,
        column: str,
        index: dict[str, str],
    ) -> object:
        response = self._get(
            f'/datasets/{dataset_id}/value',
            params={'user_id': user_id, 'column': column, **index},
        )
        return response.get('value')

    def health_check(self) -> RepositoryHealth:
        try:
            response = self._get('/healthz')
            return RepositoryHealth(
                available=True,
                latency_ms=int(response.get('_elapsed_ms', 0)),
                last_check=datetime.now(timezone.utc),
                backend_version=response.get('version'),
                notes=None,
            )
        except RepositoryUnavailableError as exc:
            return RepositoryHealth(
                available=False,
                latency_ms=-1,
                last_check=datetime.now(timezone.utc),
                backend_version=None,
                notes=str(exc),
            )

    def _get(self, path: str, **kwargs):
        return self._request('GET', path, **kwargs)

    def _post(self, path: str, **kwargs):
        return self._request('POST', path, **kwargs)

    def _request(self, method: str, path: str, *, expect_json: bool = True, **kwargs):
        last_exc: RepositoryError | None = None
        for _attempt in range(self._retries + 1):
            try:
                response = self._client.request(method, path, **kwargs)
                self._raise_for_external_error(response)
                return response.json() if expect_json else response
            except (DatasetNotFoundError, PermissionDeniedError, QueryValidationError, QuerySizeError) as exc:
                raise exc
            except QueryTimeoutError as exc:
                last_exc = exc
            except httpx.TimeoutException as exc:
                last_exc = QueryTimeoutError(f'External system timeout: {exc}')
            except httpx.NetworkError as exc:
                last_exc = RepositoryUnavailableError(f'Network error: {exc}')

        raise last_exc or RepositoryUnavailableError('External system request failed')

    def _raise_for_external_error(self, response: httpx.Response) -> None:
        if 200 <= response.status_code < 300:
            return

        try:
            payload = response.json()
        except Exception:
            payload = {'code': self._fallback_code_for_status(response.status_code), 'message': response.text}

        code = payload.get('code') or self._fallback_code_for_status(response.status_code)
        message = payload.get('message') or 'External system error'
        error_cls = self._ERROR_MAPPING.get(code, RepositoryUnavailableError)
        raise error_cls(message)

    @staticmethod
    def _fallback_code_for_status(status_code: int) -> str:
        if status_code == 404:
            return 'DATASET_NOT_FOUND'
        if status_code == 403:
            return 'PERMISSION_DENIED'
        if status_code == 400:
            return 'QUERY_INVALID'
        if status_code == 408:
            return 'QUERY_TIMEOUT'
        if status_code == 413:
            return 'QUERY_TOO_LARGE'
        return 'UNAVAILABLE'

    @staticmethod
    def _dataset_meta_from_dto(dto: dict) -> DatasetMeta:
        return DatasetMeta(
            id=dto['id'],
            name=dto['name'],
            description=dto.get('description', ''),
            row_count=int(dto['row_count']),
            column_count=int(dto.get('column_count', len(dto.get('columns', [])))),
            columns=[
                ColumnMeta(
                    name=column['name'],
                    dtype=column['dtype'],
                    nullable=column.get('nullable', True),
                    unit=column.get('unit'),
                    semantic=column.get('semantic'),
                )
                for column in dto.get('columns', [])
            ],
            updated_at=HttpDatasetRepository._parse_datetime(dto['updated_at']),
            tags=list(dto.get('tags', [])),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        normalized = value.replace('Z', '+00:00')
        return datetime.fromisoformat(normalized)
