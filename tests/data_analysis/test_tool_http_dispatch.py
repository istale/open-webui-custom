"""Unit tests for dispatch_tool_call.

Verifies that the centralised dispatch wires the live Tools instance, the
``__user__`` / ``__metadata__`` injections, and the aoh_trace_id propagation
into the ledger event payload — the byte-equivalent contract that lets HTTP
and (future) in-process replay share one execution path.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.tools.data_analysis.tool_module import Tools
from open_webui.utils.data_analysis import set_repository
from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.chart_store import ChartStore
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.query_cache import QueryCache
from open_webui.utils.data_analysis.tool_http_dispatch import (
    BUILTIN_TOOL_ID,
    ToolArgumentError,
    ToolNotFound,
    dispatch_tool_call,
)


@pytest.fixture()
def app_with_tools(tmp_path):
    set_repository(InMemoryDatasetRepository(LOCAL_FIXTURES))
    instance = Tools()
    instance.query_cache = QueryCache()
    instance.chart_store = ChartStore(tmp_path)
    app = SimpleNamespace(state=SimpleNamespace(TOOLS={BUILTIN_TOOL_ID: instance}))
    yield app, instance
    set_repository(None)


@pytest.fixture()
def event_loop_for_log_event():
    """Provide a running loop so schedule_log_event can fire its task.

    The tool emits ledger events via asyncio.create_task; tests don't
    care about the events themselves, only that the call doesn't crash.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


def test_list_datasets_returns_native_dict(app_with_tools, event_loop_for_log_event):
    app, _ = app_with_tools

    async def _run():
        return dispatch_tool_call(
            app=app, tool_name='list_datasets', args={},
            user_id='alice', chat_id='c1', message_id='m1', aoh_trace_id='trace-abc',
        )
    result = event_loop_for_log_event.run_until_complete(_run())
    assert result['schema_version'] == 1
    assert isinstance(result['items'], list)
    assert len(result['items']) > 0


def test_unknown_tool_raises_tool_not_found(app_with_tools):
    app, _ = app_with_tools
    with pytest.raises(ToolNotFound):
        dispatch_tool_call(app=app, tool_name='nope', args={}, user_id='alice')


def test_underscored_tool_name_rejected(app_with_tools):
    app, _ = app_with_tools
    with pytest.raises(ToolNotFound):
        dispatch_tool_call(app=app, tool_name='_secret', args={}, user_id='alice')


def test_reserved_dunder_arg_rejected(app_with_tools):
    app, _ = app_with_tools
    with pytest.raises(ToolArgumentError):
        dispatch_tool_call(
            app=app, tool_name='list_datasets',
            args={'__user__': {'id': 'mallory'}}, user_id='alice',
        )


def test_unknown_arg_rejected(app_with_tools):
    app, _ = app_with_tools
    with pytest.raises(ToolArgumentError):
        dispatch_tool_call(
            app=app, tool_name='list_datasets',
            args={'not_a_real_param': 1}, user_id='alice',
        )


def test_app_without_tools_state_raises(tmp_path):
    app = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(ToolNotFound):
        dispatch_tool_call(app=app, tool_name='list_datasets', args={}, user_id='alice')


def test_aoh_trace_id_lands_in_ledger_payload(app_with_tools, event_loop_for_log_event, monkeypatch):
    """The metadata.aoh_trace_id we pass in must show up in the emitted
    event payload so downstream consumers can join data_analysis_events
    to Pi/Hub agent_events on the same model-call trace.
    """
    app, _ = app_with_tools
    seen: list[dict] = []

    def _spy(**kwargs):
        seen.append(kwargs)
    monkeypatch.setattr(
        'open_webui.tools.data_analysis.tool_module.schedule_log_event',
        _spy,
    )

    async def _run():
        return dispatch_tool_call(
            app=app, tool_name='list_datasets', args={},
            user_id='alice', chat_id='c1', message_id='m1', aoh_trace_id='trace-xyz',
        )
    event_loop_for_log_event.run_until_complete(_run())

    succeeded = [e for e in seen if e['event_type'] == 'tool.list_datasets.succeeded']
    assert succeeded, 'expected a tool.list_datasets.succeeded ledger emit'
    assert succeeded[0]['payload'].get('aoh_trace_id') == 'trace-xyz'
    assert succeeded[0]['chat_id'] == 'c1'
    assert succeeded[0]['message_id'] == 'm1'


def test_dispatch_without_aoh_trace_id_omits_field(app_with_tools, event_loop_for_log_event, monkeypatch):
    """No aoh_trace_id passed in → payload must not contain the key.

    This guards backwards-compat: tools called by native middleware
    (no aoh_trace_id) keep producing the same ledger payload shape.
    """
    app, _ = app_with_tools
    seen: list[dict] = []

    def _spy(**kwargs):
        seen.append(kwargs)
    monkeypatch.setattr(
        'open_webui.tools.data_analysis.tool_module.schedule_log_event',
        _spy,
    )

    async def _run():
        return dispatch_tool_call(
            app=app, tool_name='list_datasets', args={},
            user_id='alice',
        )
    event_loop_for_log_event.run_until_complete(_run())

    succeeded = [e for e in seen if e['event_type'] == 'tool.list_datasets.succeeded']
    assert succeeded
    assert 'aoh_trace_id' not in succeeded[0]['payload']
