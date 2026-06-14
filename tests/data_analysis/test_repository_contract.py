from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

import httpx
import pandas as pd
import pytest

from open_webui.utils.data_analysis import get_repository, set_repository
from open_webui.utils.data_analysis.adapters.http_adapter import HttpDatasetRepository
from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.repository import (
    ColumnMeta,
    DatasetMeta,
    DatasetNotFoundError,
    DatasetRepository,
    PermissionDeniedError,
    QueryResult,
    QuerySizeError,
    QueryTimeoutError,
    QueryValidationError,
    RepositoryError,
    RepositoryHealth,
    RepositoryUnavailableError,
)


@pytest.fixture()
def repo() -> InMemoryDatasetRepository:
    return InMemoryDatasetRepository(LOCAL_FIXTURES)


def test_in_memory_repository_satisfies_protocol(repo):
    assert isinstance(repo, DatasetRepository)


def test_list_datasets_and_tag_filter(repo):
    all_datasets = repo.list_datasets(user_id='u1')
    spc_datasets = repo.list_datasets(user_id='u1', tags=['spc'])

    assert {dataset.id for dataset in all_datasets} == {'sensor_readings', 'batch_quality'}
    assert [dataset.id for dataset in spc_datasets] == ['batch_quality']


def test_get_metadata(repo):
    metadata = repo.get_metadata('sensor_readings', user_id='u1')

    assert metadata.name == 'Line Sensor Readings'
    assert metadata.row_count == 6
    assert any(column.semantic == 'spec_usl' for column in metadata.columns)


def test_execute_query(repo):
    result = repo.execute_query(
        'sensor_readings',
        'SELECT sensor_id, avg(temperature_c) AS avg_temp FROM df GROUP BY sensor_id ORDER BY sensor_id',
        user_id='u1',
    )

    assert isinstance(result, QueryResult)
    assert list(result.df.columns) == ['sensor_id', 'avg_temp']
    assert result.row_count == 3
    assert result.truncated is False


def test_execute_query_respects_max_rows(repo):
    result = repo.execute_query(
        'sensor_readings',
        'SELECT * FROM df ORDER BY timestamp',
        user_id='u1',
        max_rows=2,
    )

    assert len(result.df) == 2
    assert result.row_count == 2
    assert result.truncated is True


def test_execute_query_rejects_non_select(repo):
    with pytest.raises(QueryValidationError):
        repo.execute_query('sensor_readings', 'DELETE FROM df', user_id='u1')


def test_get_value_at(repo):
    value = repo.get_value_at(
        'sensor_readings',
        user_id='u1',
        column='temperature_c',
        index={'sensor_id': 'TEMP-01', 'batch_id': 'B-1001'},
    )

    assert value == 74.9


def test_health_check(repo):
    health = repo.health_check()

    assert health.available is True
    assert health.backend_version == 'in-memory'


@pytest.mark.parametrize(
    ('marker', 'error_cls'),
    [
        ('_FAULT_TIMEOUT', QueryTimeoutError),
        ('_FAULT_NOT_FOUND', DatasetNotFoundError),
        ('_FAULT_DENIED', PermissionDeniedError),
        ('_FAULT_INVALID', QueryValidationError),
        ('_FAULT_TOO_LARGE', QuerySizeError),
        ('_FAULT_UNAVAILABLE', RepositoryUnavailableError),
    ],
)
def test_fault_injection_errors(repo, marker, error_cls):
    with pytest.raises(error_cls):
        repo.execute_query('sensor_readings', f'SELECT * FROM df -- {marker}', user_id='u1')


def test_fault_injection_slow_3s(monkeypatch, repo):
    sleeps = []
    monkeypatch.setattr('open_webui.utils.data_analysis.adapters.in_memory_adapter.time.sleep', sleeps.append)

    result = repo.execute_query('sensor_readings', 'SELECT * FROM df -- _FAULT_SLOW_3S', user_id='u1')

    assert sleeps == [3]
    assert result.row_count == 6


def test_fault_injection_truncated(repo):
    result = repo.execute_query(
        'sensor_readings',
        'SELECT * FROM df -- _FAULT_TRUNCATED',
        user_id='u1',
        max_rows=3,
    )

    assert len(result.df) == 3
    assert result.row_count == 3
    assert result.truncated is True


def test_dtos_are_frozen():
    column = ColumnMeta('temperature_c', 'float64', False, 'celsius', 'measurement')
    metadata = DatasetMeta(
        id='d1',
        name='Dataset',
        description='desc',
        row_count=1,
        column_count=1,
        columns=[column],
        updated_at=datetime.now(timezone.utc),
        tags=[],
    )
    result = QueryResult(pd.DataFrame({'x': [1]}), 1, False, 0, False)
    health = RepositoryHealth(True, 0, datetime.now(timezone.utc), 'test', None)

    for dto in [column, metadata, result, health]:
        with pytest.raises(FrozenInstanceError):
            dto.__setattr__('__test_mutation__', 'nope')


def test_all_errors_inherit_repository_error():
    for error_cls in [
        DatasetNotFoundError,
        PermissionDeniedError,
        QueryValidationError,
        QueryTimeoutError,
        QuerySizeError,
        RepositoryUnavailableError,
    ]:
        assert issubclass(error_cls, RepositoryError)


def test_dependency_injection_round_trip(repo):
    set_repository(repo)
    try:
        assert get_repository() is repo
    finally:
        set_repository(None)


def _http_repo_for(handler):
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url='https://manufacturing.example/api',
        headers={
            'Authorization': 'Bearer test-token',
            'X-Protocol-Version': HttpDatasetRepository.PROTOCOL_VERSION,
        },
    )
    return HttpDatasetRepository('https://manufacturing.example/api', 'test-token', client=client)


def _dataset_dto():
    return {
        'id': 'sensor_readings',
        'name': 'Line Sensor Readings',
        'description': 'desc',
        'row_count': 6,
        'column_count': 1,
        'columns': [
            {
                'name': 'timestamp',
                'dtype': 'datetime64[ns]',
                'nullable': False,
                'unit': None,
                'semantic': 'timestamp',
            }
        ],
        'updated_at': '2026-05-01T08:05:00+00:00',
        'tags': ['manufacturing'],
    }


def test_http_adapter_sends_protocol_header_and_transforms_dto():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={'items': [_dataset_dto()]})

    repo = _http_repo_for(handler)
    datasets = repo.list_datasets(user_id='u1')

    assert seen_headers['x-protocol-version'] == 'v1'
    assert datasets[0].id == 'sensor_readings'
    assert datasets[0].columns[0].semantic == 'timestamp'


@pytest.mark.parametrize(
    ('code', 'error_cls'),
    [
        ('DATASET_NOT_FOUND', DatasetNotFoundError),
        ('PERMISSION_DENIED', PermissionDeniedError),
        ('QUERY_INVALID', QueryValidationError),
        ('QUERY_TIMEOUT', QueryTimeoutError),
        ('QUERY_TOO_LARGE', QuerySizeError),
        ('UNKNOWN', RepositoryUnavailableError),
    ],
)
def test_http_error_mapping(code, error_cls):
    repo = _http_repo_for(
        lambda request: httpx.Response(400, json={'code': code, 'message': f'{code} message'})
    )

    with pytest.raises(error_cls):
        repo.get_metadata('sensor_readings', user_id='u1')


def test_http_retries_network_errors_then_succeeds():
    attempts = {'count': 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts['count'] += 1
        if attempts['count'] < 3:
            raise httpx.NetworkError('temporary network failure')
        return httpx.Response(200, json={'items': [_dataset_dto()]})

    repo = _http_repo_for(handler)
    datasets = repo.list_datasets(user_id='u1')

    assert attempts['count'] == 3
    assert datasets[0].id == 'sensor_readings'


def test_http_does_not_parse_magic_fault_strings():
    observed_sql = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_sql.update(__import__('json').loads(request.content))
        return httpx.Response(
            200,
            json={'records': [{'ok': 1}]},
            headers={'X-Row-Count': '1', 'X-Truncated': 'false', 'X-Elapsed-Ms': '9', 'X-Cache': 'miss'},
        )

    repo = _http_repo_for(handler)
    result = repo.execute_query('sensor_readings', 'SELECT * FROM df -- _FAULT_TIMEOUT', user_id='u1')

    assert observed_sql['sql'] == 'SELECT * FROM df -- _FAULT_TIMEOUT'
    assert result.row_count == 1
