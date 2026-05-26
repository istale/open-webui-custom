from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.replay import _redact_trajectory, replay_trajectory
from open_webui.utils.data_analysis.trajectory import build_trajectory


def _ev(ts, event_type, message_id=None, payload=None, **kw):
    return {
        'id': f'e{ts}', 'ts': ts, 'user_id': 'u', 'chat_id': 'c', 'message_id': message_id,
        'event_type': event_type, 'payload': payload or {},
        'success': kw.get('success', True), 'error_code': kw.get('error_code'),
        'duration_ms': None, 'tool_name': kw.get('tool_name'), 'dataset_id': kw.get('dataset_id'),
    }


def _repo():
    return InMemoryDatasetRepository(LOCAL_FIXTURES)


def test_replay_reproduces_successful_tool_sequence():
    events = [
        _ev(10, 'tool.query_dataset.succeeded', message_id='m1', tool_name='query_dataset',
            dataset_id='sensor_readings',
            payload={'sql': 'SELECT timestamp, temperature_c FROM sensor_readings', 'query_id': 'qA', 'row_count': 6}),
        _ev(20, 'tool.render_chart.succeeded', message_id='m1', tool_name='render_chart',
            payload={'chart_type': 'line', 'x': 'timestamp', 'y': 'temperature_c', 'query_id': 'qA', 'chart_id': 'cA'}),
    ]
    traj = build_trajectory(events).to_dict()
    report = replay_trajectory(traj, _repo())

    assert report['summary']['replayable'] == 2
    assert report['summary']['diverged'] == 0
    # the render's query_id was remapped to the freshly-produced one
    assert all(a.get('matches_recorded') for a in report['actions'])


def test_replay_reproduces_recorded_failure():
    # Recorded a render that referenced a non-existent column and FAILED.
    events = [
        _ev(10, 'tool.query_dataset.succeeded', message_id='m1', tool_name='query_dataset',
            dataset_id='sensor_readings',
            payload={'sql': 'SELECT temperature_c FROM sensor_readings', 'query_id': 'qA', 'row_count': 6}),
        _ev(20, 'tool.render_chart.failed', message_id='m1', tool_name='render_chart',
            success=False, error_code='VALUE',
            payload={'chart_type': 'bar', 'x': 'bin', 'y': 'count', 'query_id': 'qA', 'error_message': 'Unknown column(s): count'}),
    ]
    traj = build_trajectory(events).to_dict()
    report = replay_trajectory(traj, _repo())

    render = next(a for a in report['actions'] if a['event_type'].startswith('tool.render_chart'))
    assert render['replay_success'] is False  # reproduces the failure
    assert render['matches_recorded'] is True  # recorded fail == replay fail


def test_redaction_masks_free_text():
    d = {'turns': [{'user_prompt': 'secret question', 'request': {'system_prompt': 'sys', 'model': 'X'}}]}
    out = _redact_trajectory(d)
    assert out['turns'][0]['user_prompt'] == '[REDACTED]'
    assert out['turns'][0]['request']['system_prompt'] == '[REDACTED]'
    assert out['turns'][0]['request']['model'] == 'X'  # non-text preserved
