"""Test the GET /events/by-trace/<aoh_trace_id> endpoint for Stage 4.

This uses the actual app's get_db (which reads from a temporary sqlite
created by the test conftest) so we exercise the SQL path verbatim.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.models.data_analysis_events import DataAnalysisEvents
from open_webui.routers.data_analysis import router as data_analysis_router
from open_webui.utils.data_analysis.tool_http_dispatch import BUILTIN_TOOL_ID


SECRET = 'events-test-secret'


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', SECRET)
    app = FastAPI()
    app.state.TOOLS = {BUILTIN_TOOL_ID: object()}
    app.include_router(data_analysis_router, prefix='/api/v1/data-analysis')
    with TestClient(app) as c:
        yield c


def _seed_event(aoh_trace_id: str, event_type: str = 'tool.list_datasets.succeeded', user_id: str = 'alice'):
    asyncio.run(DataAnalysisEvents.bulk_insert([
        {
            'id': uuid.uuid4().hex,
            'ts': int(time.time() * 1000),
            'user_id': user_id,
            'user_org_id': None,
            'chat_id': 'chat-x',
            'message_id': 'msg-x',
            'workspace': 'data-analysis',
            'event_type': event_type,
            'schema_version': 1,
            'payload': {'aoh_trace_id': aoh_trace_id, 'count': 2},
            'dataset_id': None,
            'chart_type': None,
            'tool_name': 'list_datasets',
            'duration_ms': 11,
            'success': True,
            'error_code': None,
            'is_deleted': False,
            'deleted_at': None,
        },
    ]))


def _hdr():
    return {'X-Pi-Service-Token': SECRET, 'X-User-Id': 'alice'}


def test_finds_event_by_aoh_trace_id(client):
    tid = f'pi-test-{uuid.uuid4().hex[:8]}'
    _seed_event(tid)
    resp = client.get(f'/api/v1/data-analysis/events/by-trace/{tid}', headers=_hdr())
    assert resp.status_code == 200
    body = resp.json()
    assert body['count'] == 1
    assert body['events'][0]['payload']['aoh_trace_id'] == tid


def test_empty_when_no_match(client):
    resp = client.get('/api/v1/data-analysis/events/by-trace/pi-no-such-trace', headers=_hdr())
    assert resp.status_code == 200
    assert resp.json() == {'aoh_trace_id': 'pi-no-such-trace', 'count': 0, 'events': []}


def test_requires_service_token(client):
    resp = client.get('/api/v1/data-analysis/events/by-trace/pi-x')
    assert resp.status_code == 401


def test_returns_multiple_in_order(client):
    tid = f'pi-multi-{uuid.uuid4().hex[:8]}'
    _seed_event(tid, event_type='tool.query_dataset.succeeded')
    _seed_event(tid, event_type='tool.render_chart.succeeded')
    body = client.get(f'/api/v1/data-analysis/events/by-trace/{tid}', headers=_hdr()).json()
    assert body['count'] == 2
    types = [e['event_type'] for e in body['events']]
    assert types == sorted(types, key=lambda t: t)  # any order acceptable; key thing is both present
    assert 'tool.query_dataset.succeeded' in types
    assert 'tool.render_chart.succeeded' in types
