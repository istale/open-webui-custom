"""Stage 2 user-signal analysis: intents / satisfaction / fit."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.utils.data_analysis.fit import summarize_fit
from open_webui.utils.data_analysis.intents import extract_skeleton, summarize_intents
from open_webui.utils.data_analysis.satisfaction import summarize_satisfaction


def _render(chart_type, x='timestamp', y='temperature_c', success=True, error_code=None, dataset='sensor_readings'):
    return {
        'event_type': 'tool.render_chart.succeeded' if success else 'tool.render_chart.failed',
        'ts': 2, 'success': success, 'error_code': error_code,
        'args': {'chart_type': chart_type, 'x': x, 'y': y, 'dataset_id': dataset},
        'result': {'chart_id': f'c-{chart_type}'},
    }


def _query(dataset='sensor_readings', success=True):
    return {
        'event_type': 'tool.query_dataset.succeeded' if success else 'tool.query_dataset.failed',
        'ts': 1, 'success': success,
        'args': {'dataset_id': dataset, 'sql': f'SELECT * FROM {dataset}'},
        'result': {'query_id': 'q1'},
    }


def _turn(prompt, actions, charts_rendered=None, charts_viewed=None, mid='m1'):
    return {
        'message_id': mid, 'ts': 100, 'user_prompt': prompt,
        'request': {}, 'thinking': [],
        'actions': actions,
        'charts_rendered': charts_rendered or [],
        'charts_viewed': charts_viewed or [],
        'reward': None, 'outcome': {},
    }


def _traj(cid, turns, session_events=None):
    return {'chat_id': cid, 'user_id': 'u', 'session_events': session_events or [], 'turns': turns}


# -----------------------------------------------------------------------------
# intents
# -----------------------------------------------------------------------------
def test_skeleton_masks_identifiers_and_numbers():
    # snake_case + bare identifiers + numbers all get masked,
    # Chinese verbs / structure stay.
    skel = extract_skeleton('請用 sensor_readings 畫出 temperature_c 隨時間的趨勢圖，看 100 個樣本')
    assert 'sensor_readings' not in skel
    assert 'temperature_c' not in skel
    assert '___' in skel
    assert '畫出' in skel
    assert '趨勢圖' in skel
    assert '100' not in skel  # masked to #
    assert '#' in skel


def test_intents_groups_by_skeleton_and_counts_outcomes():
    trajs = [
        _traj('c1', [_turn('畫 temperature_c 的折線圖',
                           [_query(), _render('line')],
                           charts_rendered=['c-line'])]),
        _traj('c2', [_turn('畫 diameter_mm 的折線圖',
                           [_query(dataset='batch_quality'), _render('line', dataset='batch_quality')],
                           charts_rendered=['c-line'])]),
        _traj('c3', [_turn('畫 humidity 的折線圖',
                           [_query(), _render('line', success=False, error_code='VALUE')])]),
    ]
    res = summarize_intents(trajs, top=5)
    assert res['total_prompts'] == 3
    # All three prompts collapse to one skeleton "畫 ___ 的折線圖":
    assert res['unique_skeletons'] == 1
    top = res['top'][0]
    assert top['count'] == 3
    assert top['success'] == 2
    assert top['failure'] == 1
    assert top['failure_codes'] == {'VALUE': 1}
    assert set(top['datasets']) == {'sensor_readings', 'batch_quality'}


# -----------------------------------------------------------------------------
# satisfaction
# -----------------------------------------------------------------------------
def test_satisfaction_proxies():
    trajs = [
        # Chat A: 2 renders, both viewed, multi-turn, followup clicked.
        _traj('cA',
              [_turn('q1', [_render('line')], charts_rendered=['c1'], charts_viewed=['c1'], mid='m1'),
               _turn('q2', [_render('bar')], charts_rendered=['c2'], charts_viewed=['c2'], mid='m2')],
              session_events=[{'ts': 50, 'event_type': 'followup.clicked', 'payload': {}}]),
        # Chat B: 1 render, NOT viewed, single-turn, no followup.
        _traj('cB', [_turn('q3', [_render('line')], charts_rendered=['c3'], mid='m3')]),
        # Chat C: no chart at all.
        _traj('cC', [_turn('q4', [_query()], mid='m4')]),
    ]
    s = summarize_satisfaction(trajs)
    assert s['chats'] == 3
    assert s['turns'] == 4
    assert s['charts_rendered'] == 3
    assert s['charts_viewed'] == 2  # cA viewed 2, cB viewed 0
    assert s['chart_view_through_rate'] == round(2 / 3, 3)
    assert s['multi_turn_chat_rate'] == round(1 / 3, 3)  # only cA multi-turn
    assert s['chats_with_render'] == 2
    assert s['chats_with_followup_click'] == 1
    assert s['followup_click_rate_when_rendered'] == round(1 / 2, 3)


# -----------------------------------------------------------------------------
# fit
# -----------------------------------------------------------------------------
def test_fit_matches_and_flags_mismatches():
    trajs = [
        # Match: 趨勢 -> line ✅
        _traj('c1', [_turn('看 temperature_c 隨時間的趨勢', [_render('line')])]),
        # Match: 異常 -> control ✅
        _traj('c2', [_turn('看溫度有沒有異常', [_render('control')])]),
        # Mismatch: 分布 -> line ❌ (should be box/histogram)
        _traj('c3', [_turn('看 diameter_mm 的分布', [_render('line')])]),
        # No verb signal: skipped
        _traj('c4', [_turn('show me the data', [_render('bar')])]),
        # No render: skipped
        _traj('c5', [_turn('看趨勢就好', [_query()])]),
    ]
    f = summarize_fit(trajs)
    assert f['turns_with_render_and_verb'] == 3
    assert f['matched'] == 2
    assert f['mismatched'] == 1
    assert f['fit_rate'] == round(2 / 3, 3)
    assert f['turns_no_intent_verb'] == 1
    assert f['turns_no_render'] == 1
    mm = f['sample_mismatches'][0]
    assert '分布' in mm['verbs']
    assert mm['actual'] == ['line']
    assert 'box' in mm['expected_any_of']


def test_empty_trajectories_dont_crash():
    assert summarize_intents([]) == {'total_prompts': 0, 'unique_skeletons': 0, 'top': []}
    assert summarize_satisfaction([])['chats'] == 0
    assert summarize_fit([])['turns_with_render_and_verb'] == 0
