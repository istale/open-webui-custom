from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('ENABLE_DB_MIGRATIONS', 'false')

from open_webui.tools.data_analysis.tool_module import Tools
from open_webui.utils.data_analysis import set_repository
from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.event_fixtures import P0_EVENT_FIXTURES
from open_webui.utils.data_analysis.event_logger import (
    log_event,
    reset_event_logger_for_tests,
    schedule_chat_lifecycle_events,
    start_event_worker,
    stop_event_worker,
)
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.query_cache import QueryCache


def test_p0_event_fixtures_cover_catalog():
    event_types = {event['event_type'] for event in P0_EVENT_FIXTURES}

    assert len(P0_EVENT_FIXTURES) == 13
    assert event_types == {
        'workspace.opened',
        'dataset.selected',
        'prompt.submitted',
        'model.thinking_completed',
        'tool.query_dataset.succeeded',
        'tool.query_dataset.failed',
        'tool.render_chart.succeeded',
        'tool.render_chart.failed',
        'chart.rendered',
        'message.assistant_completed',
        'stream.timeout',
        'stream.aborted',
        'followup.clicked',
    }


def test_event_model_and_migration_define_schema_version_and_soft_delete():
    model_source = Path('backend/open_webui/models/data_analysis_events.py').read_text()
    migration_source = Path('backend/open_webui/migrations/versions/e5f6a7b8c9d0_add_data_analysis_events.py').read_text()

    assert "schema_version: int = 1" in model_source
    assert "workspace: str = 'data-analysis'" in model_source
    assert 'is_deleted: bool = False' in model_source
    assert "sa.Column('schema_version'" in migration_source
    assert "sa.Column('is_deleted'" in migration_source


def test_frontend_event_whitelist_is_frontend_only():
    router_source = Path('backend/open_webui/routers/data_analysis.py').read_text()
    allowed = {
        'workspace.opened',
        'dataset.selected',
        'prompt.submitted',
        'chart.rendered',
        'stream.timeout',
        'stream.aborted',
        'followup.clicked',
    }

    for event_type in allowed:
        assert event_type in router_source
    assert 'tool.query_dataset.succeeded' not in router_source


def test_event_worker_batches_without_blocking_tool_path(monkeypatch):
    async def run():
        reset_event_logger_for_tests()
        inserted = []

        async def fake_insert_batch(events):
            inserted.extend(events)

        monkeypatch.setattr('open_webui.utils.data_analysis.event_logger._insert_batch', fake_insert_batch)

        start_event_worker()
        await log_event(
            event_type='workspace.opened',
            user_id='user-1',
            payload={'entry_path': 'sidebar'},
        )
        await stop_event_worker()

        assert len(inserted) == 1
        assert inserted[0]['event_type'] == 'workspace.opened'
        assert inserted[0]['schema_version'] == 1

    asyncio.run(run())


def test_tool_query_and_render_emit_backend_events(monkeypatch, tmp_path):
    emitted = []
    monkeypatch.setattr('open_webui.tools.data_analysis.tool_module.schedule_log_event', lambda **kwargs: emitted.append(kwargs))

    set_repository(InMemoryDatasetRepository(LOCAL_FIXTURES))
    try:
        tools = Tools()
        tools.query_cache = QueryCache()
        query = tools.query_dataset(
            'sensor_readings',
            'SELECT timestamp, temperature_c, spec_target, spec_usl, spec_lsl FROM df ORDER BY timestamp',
            __user__={'id': 'user-1'},
            __metadata__={'chat_id': 'chat-1', 'message_id': 'msg-1'},
        )
        tools.render_chart(
            query['query_id'],
            'line',
            'timestamp',
            'temperature_c',
            'Trend',
            'fixture',
            'line',
            'timestamp,temperature_c',
            __user__={'id': 'user-1'},
            __metadata__={'chat_id': 'chat-1', 'message_id': 'msg-1'},
        )
    finally:
        set_repository(None)

    event_types = [event['event_type'] for event in emitted]
    assert 'tool.query_dataset.succeeded' in event_types
    assert 'tool.render_chart.succeeded' in event_types
    assert all(event['chat_id'] == 'chat-1' for event in emitted)


def test_chat_lifecycle_events_emit_for_vertical_context(monkeypatch):
    emitted = []
    monkeypatch.setattr('open_webui.utils.data_analysis.event_logger.schedule_log_event', lambda **kwargs: emitted.append(kwargs))

    schedule_chat_lifecycle_events(
        user_id='user-1',
        metadata={
            'workspace_type': 'data-analysis',
            'chat_id': 'chat-1',
            'message_id': 'msg-1',
        },
        output=[
            {
                'type': 'reasoning',
                'duration': 2,
                'content': [{'type': 'output_text', 'text': 'Need query then chart.'}],
            },
            {
                'type': 'function_call',
                'name': 'query_dataset',
            },
            {
                'type': 'message',
                'content': [{'type': 'output_text', 'text': 'Here is the trend.'}],
            },
        ],
        content='Here is the trend.',
        started_at=0,
    )

    event_types = [event['event_type'] for event in emitted]
    assert event_types == ['model.thinking_completed', 'message.assistant_completed']
    assert emitted[0]['payload']['thinking_text'] == 'Need query then chart.'
    assert emitted[0]['duration_ms'] == 2000
    assert emitted[1]['payload']['tool_call_count'] == 1
    assert emitted[1]['payload']['had_thinking'] is True


def test_chat_lifecycle_events_skip_non_vertical_context(monkeypatch):
    emitted = []
    monkeypatch.setattr('open_webui.utils.data_analysis.event_logger.schedule_log_event', lambda **kwargs: emitted.append(kwargs))

    schedule_chat_lifecycle_events(
        user_id='user-1',
        metadata={'chat_id': 'chat-1', 'message_id': 'msg-1'},
        output=[],
        content='Generic chat response',
        started_at=0,
    )

    assert emitted == []


def test_core_hooks_are_recorded_in_source():
    main_source = Path('backend/open_webui/main.py').read_text()
    chats_source = Path('backend/open_webui/models/chats.py').read_text()
    middleware_source = Path('backend/open_webui/utils/middleware.py').read_text()

    assert 'start_event_worker(app)' in main_source
    assert 'await stop_event_worker()' in main_source
    assert 'mark_deleted_safely' in chats_source
    assert 'mark_deleted_by_user_id_safely' in chats_source
    assert 'schedule_chat_lifecycle_events' in middleware_source
