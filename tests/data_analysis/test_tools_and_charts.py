from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.tools.data_analysis.tool_module import Tools
from open_webui.utils.data_analysis import set_repository
from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.chart_renderer import SUPPORTED_CHART_TYPES, render_matplotlib_chart
from open_webui.utils.data_analysis.chart_store import ChartStore
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.query_cache import QueryCache


@pytest.fixture()
def repo():
    return InMemoryDatasetRepository(LOCAL_FIXTURES)


@pytest.fixture()
def tools(monkeypatch, repo, tmp_path):
    set_repository(repo)
    instance = Tools()
    instance.query_cache = QueryCache()
    instance.chart_store = ChartStore(tmp_path)
    yield instance
    set_repository(None)


def test_query_dataset_caches_full_result_and_returns_preview(tools):
    result = tools.query_dataset(
        'sensor_readings',
        'SELECT * FROM df ORDER BY timestamp',
        max_rows=2,
        __user__={'id': 'user-1'},
    )

    assert result['schema_version'] == 1
    assert result['row_count'] == 6
    assert len(result['preview']) == 2
    assert result['query_id']
    assert tools.query_cache.get(result['query_id'], user_id='user-1').df.shape[0] == 6


def test_get_dataset_schema(tools):
    result = tools.get_dataset_schema('sensor_readings', __user__={'id': 'user-1'})

    assert result['schema_version'] == 1
    assert result['dataset']['id'] == 'sensor_readings'
    assert any(column['semantic'] == 'spec_usl' for column in result['dataset']['columns'])


def test_render_chart_returns_image_attachment_and_files(tools):
    query = tools.query_dataset(
        'sensor_readings',
        'SELECT timestamp, temperature_c, spec_target, spec_usl, spec_lsl FROM df ORDER BY timestamp',
        __user__={'id': 'user-1'},
    )

    result = tools.render_chart(
        query['query_id'],
        'control',
        'timestamp',
        'temperature_c',
        'Temperature Control',
        'Line A sensors',
        'control chart with spec limits',
        'timestamp,temperature_c,spec_usl,spec_lsl',
        __user__={'id': 'user-1'},
        __metadata__={'chat_id': 'chat-1'},
    )

    attachment = result['attachment']
    record = tools.chart_store.get(attachment['id'])
    assert result['type'] == 'image'
    assert attachment['url'].endswith(f"/charts/{attachment['id']}.png")
    assert attachment['metadata']['audit']['raw_row_count'] == 6
    assert record.path.exists()
    assert record.thumb_path.exists()
    assert record.chat_id == 'chat-1'


def test_render_chart_cache_miss_mentions_query_id_expired(tools):
    with pytest.raises(ValueError, match='query_id .* expired or not found'):
        tools.render_chart(
            'missing',
            'line',
            'timestamp',
            'temperature_c',
            'Missing',
            'fixture',
            'line',
            'timestamp,temperature_c',
            __user__={'id': 'user-1'},
        )


def test_summarize_data_uses_cached_query_context(tools):
    query = tools.query_dataset('sensor_readings', 'SELECT * FROM df', __user__={'id': 'user-1'})
    result = tools.summarize_data(
        query['query_id'],
        'Sensor summary',
        'Temperature is stable.',
        '- No excursions; Batch B-1002 is slightly warmer',
        __user__={'id': 'user-1'},
    )

    assert result['schema_version'] == 1
    assert result['type'] == 'summary'
    assert result['metadata']['row_count'] == 6
    assert result['key_findings'] == ['No excursions', 'Batch B-1002 is slightly warmer']


@pytest.mark.parametrize('chart_type', sorted(SUPPORTED_CHART_TYPES))
def test_all_chart_types_render_png_and_thumbnail(tmp_path, chart_type):
    df = pd.DataFrame(
        {
            'timestamp': pd.date_range('2026-05-01', periods=8, freq='min'),
            'category': ['A', 'A', 'B', 'B', 'C', 'C', 'D', 'D'],
            'sensor': ['S1', 'S2', 'S1', 'S2', 'S1', 'S2', 'S1', 'S2'],
            'value': [10.0, 12.0, 9.5, 13.0, 8.0, 7.5, 3.0, 2.0],
            'weight': [1.0, 2.0, 1.5, 2.5, 1.0, 1.2, 0.5, 0.3],
            'spec_target': [10.0] * 8,
            'spec_usl': [14.0] * 8,
            'spec_lsl': [6.0] * 8,
        }
    )
    output_path = tmp_path / f'{chart_type}.png'
    thumb_path = tmp_path / f'{chart_type}.thumb.png'

    if chart_type in {'line', 'control', 'spc'}:
        x, y, color = 'timestamp', 'value', ''
    elif chart_type == 'scatter':
        x, y, color = 'weight', 'value', 'weight'
    elif chart_type == 'histogram':
        x, y, color = 'category', 'value', ''
    elif chart_type == 'heatmap':
        x, y, color = 'category', 'sensor', 'value'
    else:
        x, y, color = 'category', 'value', ''

    info = render_matplotlib_chart(
        df,
        chart_type=chart_type,
        x=x,
        y=y,
        color=color,
        title=f'{chart_type} chart',
        output_path=output_path,
        thumb_path=thumb_path,
    )

    assert output_path.exists()
    assert thumb_path.exists()
    assert info['raw_row_count'] == len(df)
    assert info['image_size_bytes'] > 0
