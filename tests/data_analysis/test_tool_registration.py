from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Importing Open WebUI's Tool DB model normally runs startup migrations at
# module import time. These tests monkeypatch DB calls directly, so disabling
# migrations keeps the unit suite hermetic and avoids touching a developer DB.
os.environ.setdefault('ENABLE_DB_MIGRATIONS', 'false')

from open_webui.tools.data_analysis import (
    BUILTIN_TOOL_ID,
    PUBLIC_READ_GRANT,
    register_builtin_data_analysis_tool,
)
from open_webui.tools.data_analysis.tool_module import Tools
from open_webui.utils.data_analysis import set_repository


class _FakeRepo:
    def list_datasets(self, *, user_id: str, tags: list[str] | None = None):
        assert user_id == 'user-1'
        assert tags == ['production', 'line-a']
        from datetime import datetime, timezone

        from open_webui.utils.data_analysis.repository import ColumnMeta, DatasetMeta

        return [
            DatasetMeta(
                id='sensor_readings',
                name='Sensor Readings',
                description='Line A machine sensor readings.',
                row_count=1_000_000,
                column_count=3,
                columns=[
                    ColumnMeta(
                        name='timestamp',
                        dtype='datetime64[ns]',
                        nullable=False,
                        unit=None,
                        semantic='timestamp',
                    )
                ],
                updated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
                tags=['production', 'line-a'],
            )
        ]


def test_list_datasets_returns_schema_versioned_json_ready_payload():
    set_repository(_FakeRepo())
    try:
        result = Tools().list_datasets(tags='production, line-a', __user__={'id': 'user-1'})
    finally:
        set_repository(None)

    assert result['schema_version'] == 1
    assert result['items'][0]['id'] == 'sensor_readings'
    assert result['items'][0]['updated_at'] == '2026-05-11T00:00:00+00:00'
    assert result['items'][0]['columns'][0]['semantic'] == 'timestamp'


def test_register_builtin_data_analysis_tool_seeds_db_and_warms_both_caches(monkeypatch):
    async def run():
        calls = {}

        class FakeToolsModel:
            @staticmethod
            async def get_tool_by_id(tool_id):
                calls['get_tool_by_id'] = tool_id
                return None

            @staticmethod
            async def insert_new_tool(user_id, form_data, specs):
                calls['insert'] = {
                    'user_id': user_id,
                    'form_data': form_data,
                    'spec_names': [spec['name'] for spec in specs],
                }
                return SimpleNamespace(id=form_data.id)

            @staticmethod
            async def update_tool_by_id(tool_id, updated):
                raise AssertionError('new registration should insert, not update')

        class FakeToolForm:
            def __init__(self, id, name, content, meta, access_grants):
                self.id = id
                self.name = name
                self.content = content
                self.meta = SimpleNamespace(model_dump=lambda: meta)
                self.access_grants = access_grants

        monkeypatch.setattr(
            'open_webui.tools.data_analysis._get_tool_model_classes',
            lambda: (FakeToolForm, FakeToolsModel),
        )
        monkeypatch.setattr(
            'open_webui.tools.data_analysis._get_tool_specs',
            lambda instance: [
                {
                    'name': 'list_datasets',
                    'description': 'List datasets.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'tags': {'type': 'string'},
                            '__user__': {'type': 'object'},
                        },
                    },
                }
            ],
        )

        app = SimpleNamespace(state=SimpleNamespace(TOOLS={}, TOOL_CONTENTS={}))
        await register_builtin_data_analysis_tool(app)

        assert calls['get_tool_by_id'] == BUILTIN_TOOL_ID
        assert calls['insert']['user_id'] == 'system'
        assert calls['insert']['form_data'].access_grants == [PUBLIC_READ_GRANT]
        assert 'list_datasets' in calls['insert']['spec_names']
        assert '__user__' in calls['insert']['form_data'].content
        assert BUILTIN_TOOL_ID in app.state.TOOLS
        assert 'def list_datasets' in app.state.TOOL_CONTENTS[BUILTIN_TOOL_ID]

    asyncio.run(run())


def test_tool_result_matches_native_function_call_output_text_shape():
    set_repository(_FakeRepo())
    try:
        result = Tools().list_datasets(tags='production,line-a', __user__={'id': 'user-1'})
    finally:
        set_repository(None)

    output_item = {
        'type': 'function_call_output',
        'call_id': 'call_list_datasets',
        'output': [{'type': 'input_text', 'text': json.dumps(result, indent=2, ensure_ascii=False)}],
        'status': 'completed',
    }

    assert output_item['type'] == 'function_call_output'
    assert 'sensor_readings' in output_item['output'][0]['text']
