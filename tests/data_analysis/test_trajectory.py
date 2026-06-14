from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.utils.data_analysis.trajectory import attach_feedback, build_trajectory


def _ev(ts, event_type, message_id=None, payload=None, **kw):
    base = {
        'id': f'e{ts}',
        'ts': ts,
        'user_id': 'user-1',
        'chat_id': 'chat-1',
        'message_id': message_id,
        'event_type': event_type,
        'payload': payload or {},
        'success': kw.get('success', True),
        'error_code': kw.get('error_code'),
        'duration_ms': kw.get('duration_ms'),
        'tool_name': kw.get('tool_name'),
    }
    return base


def test_build_trajectory_reconstructs_full_turn():
    events = [
        _ev(100, 'workspace.opened', payload={'entry_path': 'sidebar'}),
        _ev(110, 'dataset.selected', payload={'dataset_id': 'batch_quality', 'from': 'row'}),
        _ev(120, 'prompt.submitted', payload={'prompt_text': 'draw diameter bar', 'model': 'MiniMax-M2.7'}),
        _ev(130, 'model.request_prepared', message_id='m1', payload={
            'model': 'MiniMax-M2.7', 'tool_ids': ['builtin:data-analysis'],
            'prompt_version': 'da-sys-2026-05-27', 'tool_spec_version': 'da-tools-2026-05-27',
            'system_prompt': 'You are... [Workspace context]',
        }),
        _ev(140, 'model.thinking_completed', message_id='m1', payload={'n_chars': 42}, duration_ms=1000),
        _ev(150, 'tool.query_dataset.succeeded', message_id='m1', tool_name='query_dataset',
            payload={'sql': 'SELECT diameter_mm FROM batch_quality', 'query_id': 'q1', 'row_count': 5}),
        _ev(160, 'tool.render_chart.failed', message_id='m1', tool_name='render_chart',
            success=False, error_code='VALUE',
            payload={'chart_type': 'bar', 'x': 'bin', 'y': 'count', 'error_message': 'Unknown column(s): count', 'query_id': 'q1'}),
        _ev(170, 'tool.render_chart.succeeded', message_id='m1', tool_name='render_chart',
            payload={'chart_type': 'bar', 'x': 'bin', 'y': 'count', 'chart_id': 'c1', 'query_id': 'q2'}),
        _ev(180, 'message.assistant_completed', message_id='m1',
            payload={'tool_call_count': 2, 'usage': {'total_tokens': 150}}),
        _ev(190, 'chart.rendered', payload={'chart_id': 'c1', 'chart_type': 'bar'}),
    ]

    traj = build_trajectory(events)

    assert traj.chat_id == 'chat-1'
    assert len(traj.session_events) == 2  # workspace.opened + dataset.selected
    assert len(traj.turns) == 1

    turn = traj.turns[0]
    assert turn.user_prompt == 'draw diameter bar'
    assert turn.request['model'] == 'MiniMax-M2.7'
    assert turn.request['prompt_version'] == 'da-sys-2026-05-27'
    assert turn.request['tool_spec_version'] == 'da-tools-2026-05-27'
    assert len(turn.thinking) == 1
    # actions ordered, with args + result lifted
    assert [a.event_type for a in turn.actions] == [
        'tool.query_dataset.succeeded',
        'tool.render_chart.failed',
        'tool.render_chart.succeeded',
    ]
    fail = turn.actions[1]
    assert fail.success is False and fail.error_code == 'VALUE'
    assert fail.args['x'] == 'bin' and fail.args['y'] == 'count'  # structured failure args
    assert turn.outcome['usage'] == {'total_tokens': 150}
    assert turn.charts_rendered == ['c1']  # chart.rendered attached by chart_id


def test_chart_viewed_and_feedback_reward():
    events = [
        _ev(130, 'model.request_prepared', message_id='m1', payload={'model': 'X'}),
        _ev(170, 'tool.render_chart.succeeded', message_id='m1', tool_name='render_chart',
            payload={'chart_type': 'line', 'x': 't', 'y': 'v', 'chart_id': 'c1', 'query_id': 'q1'}),
        _ev(180, 'message.assistant_completed', message_id='m1', payload={'tool_call_count': 1}),
        _ev(200, 'chart.viewed', payload={'chart_id': 'c1', 'chart_type': 'line'}),
    ]
    d = build_trajectory(events).to_dict()
    assert d['turns'][0]['charts_viewed'] == ['c1']

    d = attach_feedback(d, [{'data': {'message_id': 'm1', 'rating': 1, 'reason': 'clear'}}])
    assert d['turns'][0]['reward'] == {'rating': 1, 'reason': 'clear', 'comment': None}


def test_build_trajectory_handles_unordered_and_multiturn():
    events = [
        _ev(300, 'message.assistant_completed', message_id='m2', payload={'tool_call_count': 0}),
        _ev(130, 'model.request_prepared', message_id='m1', payload={'model': 'X'}),
        _ev(250, 'prompt.submitted', payload={'prompt_text': 'second'}),
        _ev(120, 'prompt.submitted', payload={'prompt_text': 'first'}),
        _ev(280, 'model.request_prepared', message_id='m2', payload={'model': 'X'}),
        _ev(180, 'message.assistant_completed', message_id='m1', payload={'tool_call_count': 0}),
    ]
    traj = build_trajectory(events)
    assert [t.message_id for t in traj.turns] == ['m1', 'm2']
    assert traj.turns[0].user_prompt == 'first'
    assert traj.turns[1].user_prompt == 'second'
