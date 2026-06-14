"""Integration tests for the Pi service HTTP endpoints.

Spins up a minimal FastAPI app with only the data_analysis router so the
tests run without booting all of main.py. Verifies the wire-level contract
that Pi will hit: spec discovery, tool dispatch, auth, and structured
error shapes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.routers.data_analysis import router as data_analysis_router
from open_webui.tools.data_analysis.tool_module import Tools
from open_webui.utils.data_analysis import set_repository
from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.chart_store import ChartStore
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.query_cache import QueryCache
from open_webui.utils.data_analysis.tool_http_dispatch import BUILTIN_TOOL_ID


SECRET = 'test-shared-secret-xyz'


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', SECRET)

    set_repository(InMemoryDatasetRepository(LOCAL_FIXTURES))
    instance = Tools()
    instance.query_cache = QueryCache()
    instance.chart_store = ChartStore(tmp_path)

    app = FastAPI()
    app.state.TOOLS = {BUILTIN_TOOL_ID: instance}
    app.state.TOOL_CONTENTS = {BUILTIN_TOOL_ID: 'stub'}
    app.include_router(data_analysis_router, prefix='/api/v1/data-analysis')

    with TestClient(app) as c:
        yield c
    set_repository(None)


def _hdr(extra: dict | None = None) -> dict:
    base = {'X-Pi-Service-Token': SECRET, 'X-User-Id': 'alice'}
    if extra:
        base.update(extra)
    return base


# ---- tool-specs ----------------------------------------------------------


def test_tool_specs_returns_versioned_function_list(client):
    resp = client.get('/api/v1/data-analysis/tool-specs', headers=_hdr())
    assert resp.status_code == 200
    body = resp.json()
    assert body['schema_version'] == 1
    assert body['tool_spec_version']
    assert isinstance(body['tools'], list)
    names = {spec['name'] for spec in body['tools']}
    assert {'list_datasets', 'query_dataset', 'render_chart', 'summarize_data', 'get_dataset_schema'}.issubset(names)


def test_tool_specs_401_without_token(client):
    resp = client.get('/api/v1/data-analysis/tool-specs', headers={'X-User-Id': 'alice'})
    assert resp.status_code == 401


def test_tool_specs_503_when_secret_unset(monkeypatch, tmp_path):
    monkeypatch.delenv('AOH_PI_SHARED_SECRET', raising=False)
    set_repository(InMemoryDatasetRepository(LOCAL_FIXTURES))
    instance = Tools()
    instance.query_cache = QueryCache()
    instance.chart_store = ChartStore(tmp_path)
    app = FastAPI()
    app.state.TOOLS = {BUILTIN_TOOL_ID: instance}
    app.include_router(data_analysis_router, prefix='/api/v1/data-analysis')
    with TestClient(app) as c:
        resp = c.get('/api/v1/data-analysis/tool-specs', headers={'X-Pi-Service-Token': 'x', 'X-User-Id': 'alice'})
    set_repository(None)
    assert resp.status_code == 503


# ---- POST /tools/{name} success path -------------------------------------


def test_dispatch_list_datasets_ok(client):
    resp = client.post(
        '/api/v1/data-analysis/tools/list_datasets',
        headers=_hdr({'X-Chat-Id': 'c1', 'X-Aoh-Trace-Id': 'tr-1'}),
        json={'args': {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['result']['schema_version'] == 1
    assert isinstance(body['result']['items'], list)


def test_dispatch_query_then_render_end_to_end(client):
    # 1. query — return query_id
    q = client.post(
        '/api/v1/data-analysis/tools/query_dataset',
        headers=_hdr(),
        json={'args': {
            'dataset_id': 'sensor_readings',
            'query': 'SELECT * FROM df ORDER BY timestamp',
            'max_rows': 3,
        }},
    )
    assert q.status_code == 200
    qid = q.json()['result']['query_id']
    assert qid

    # 2. render — chart attachment with backend-generated id
    r = client.post(
        '/api/v1/data-analysis/tools/render_chart',
        headers=_hdr(),
        json={'args': {
            'query_id': qid,
            'chart_type': 'line',
            'x': 'timestamp',
            'y': 'temperature_c',
            'title': 'demo',
            'explanation_source': 'sensor_readings',
            'explanation_method': 'line plot of temperature over time',
            'explanation_fields': 'timestamp,temperature_c',
        }},
    )
    assert r.status_code == 200, r.json()
    rb = r.json()
    assert rb['ok'] is True
    assert rb['result']['type'] == 'image'
    assert rb['result']['attachment']['url'].endswith('.png')
    assert rb['result']['attachment']['id']


# ---- POST /tools/{name} error shapes -------------------------------------


def test_unknown_tool_returns_404(client):
    resp = client.post('/api/v1/data-analysis/tools/nope', headers=_hdr(), json={'args': {}})
    assert resp.status_code == 404


def test_unknown_arg_returns_400(client):
    resp = client.post(
        '/api/v1/data-analysis/tools/list_datasets',
        headers=_hdr(),
        json={'args': {'bogus': 1}},
    )
    assert resp.status_code == 400


def test_dunder_arg_returns_400(client):
    resp = client.post(
        '/api/v1/data-analysis/tools/list_datasets',
        headers=_hdr(),
        json={'args': {'__user__': {'id': 'mallory'}}},
    )
    assert resp.status_code == 400


def test_tool_runtime_error_returns_200_with_ok_false(client):
    """Tool raised internally → 200 with structured error so Pi loop can continue."""
    resp = client.post(
        '/api/v1/data-analysis/tools/query_dataset',
        headers=_hdr(),
        json={'args': {
            'dataset_id': 'no-such-dataset',
            'query': 'SELECT 1',
        }},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is False
    assert body['error_code']
    assert body['error_message']


def test_missing_token_returns_401(client):
    resp = client.post(
        '/api/v1/data-analysis/tools/list_datasets',
        headers={'X-User-Id': 'alice'},
        json={'args': {}},
    )
    assert resp.status_code == 401


def test_missing_user_id_returns_400(client):
    resp = client.post(
        '/api/v1/data-analysis/tools/list_datasets',
        headers={'X-Pi-Service-Token': SECRET},
        json={'args': {}},
    )
    assert resp.status_code == 400
