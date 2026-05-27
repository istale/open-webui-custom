from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('ENABLE_DB_MIGRATIONS', 'false')

from open_webui.utils.data_analysis.fewshot import format_fewshot_block, mine_fewshot


def _turn(*, mid, prompt, reward=None, failures=0, rendered=True, chart_type='line', dataset='sensor_readings',
          prompt_version='v1', tool_spec_version='t1'):
    actions = [
        {'event_type': 'tool.query_dataset.succeeded', 'ts': 1, 'success': True,
         'args': {'dataset_id': dataset, 'sql': 'SELECT timestamp, temperature_c FROM df'}, 'result': {'query_id': 'q'}},
    ]
    for i in range(failures):
        actions.append({'event_type': 'tool.render_chart.failed', 'ts': 2 + i, 'success': False,
                        'args': {'chart_type': chart_type, 'x': 'timestamp', 'y': 'temperature_c'}, 'result': {}})
    if rendered:
        actions.append({'event_type': 'tool.render_chart.succeeded', 'ts': 9, 'success': True,
                        'args': {'chart_type': chart_type, 'x': 'timestamp', 'y': 'temperature_c'}, 'result': {'chart_id': 'c'}})
    return {
        'message_id': mid,
        'ts': 100,
        'user_prompt': prompt,
        'request': {'prompt_version': prompt_version, 'tool_spec_version': tool_spec_version},
        'actions': actions,
        'charts_rendered': ['c'] if rendered else [],
        'charts_viewed': [],
        'reward': reward,
    }


def _traj(chat_id, turns):
    return {'chat_id': chat_id, 'user_id': 'u', 'session_events': [], 'turns': turns}


def test_thumbs_down_excluded_clean_included():
    trajs = [
        _traj('c1', [_turn(mid='m1', prompt='trend A', reward={'rating': 1})]),       # thumbs up -> in
        _traj('c2', [_turn(mid='m2', prompt='trend B', reward={'rating': -1})]),      # thumbs down -> out
        _traj('c3', [_turn(mid='m3', prompt='trend C', reward=None)]),                # clean no rating -> in
    ]
    bank = mine_fewshot(trajs, per_cluster=10)
    prompts = {ex['user_request'] for ex in bank}
    assert 'trend A' in prompts
    assert 'trend C' in prompts
    assert 'trend B' not in prompts


def test_single_recovery_ok_thrashing_excluded():
    trajs = [
        _traj('c1', [_turn(mid='m1', prompt='one retry', failures=1)]),   # 1 fail + render -> in
        _traj('c2', [_turn(mid='m2', prompt='thrash', failures=3)]),      # >1 fail -> out
    ]
    bank = mine_fewshot(trajs, per_cluster=10)
    prompts = {ex['user_request'] for ex in bank}
    assert 'one retry' in prompts
    assert 'thrash' not in prompts
    # The exemplar teaches the clean path: failed renders dropped, only successes kept.
    one = next(ex for ex in bank if ex['user_request'] == 'one retry')
    assert all(s['tool'] in ('query_dataset', 'render_chart') for s in one['tool_sequence'])
    assert len(one['tool_sequence']) == 2  # query + the successful render only


def test_version_gate_and_replay_gate():
    trajs = [
        _traj('c1', [_turn(mid='m1', prompt='current', prompt_version='v2', tool_spec_version='t2')]),
        _traj('c2', [_turn(mid='m2', prompt='stale', prompt_version='v1', tool_spec_version='t1')]),
    ]
    bank = mine_fewshot(trajs, current_prompt_version='v2', current_tool_spec_version='t2', per_cluster=10)
    assert {ex['user_request'] for ex in bank} == {'current'}

    # Replay gate: only chats that passed replay are mineable.
    reports = [{'chat_id': 'c1', 'summary': {'diverged': 1, 'replayable': 1}}]  # c1 diverged
    bank2 = mine_fewshot(trajs, replay_reports=reports, current_prompt_version='v2', current_tool_spec_version='t2')
    assert bank2 == []


def test_diversity_dedup_and_format():
    # Two identical clean turns in the same (chart_type, dataset) cluster.
    trajs = [
        _traj('c1', [_turn(mid='m1', prompt='same', chart_type='line')]),
        _traj('c2', [_turn(mid='m2', prompt='same', chart_type='line')]),
    ]
    # Identical content -> deduped to one regardless of per_cluster.
    bank = mine_fewshot(trajs, per_cluster=2)
    assert len(bank) == 1

    block = format_fewshot_block(bank)
    assert '[Few-shot examples' in block
    assert 'call query_dataset' in block
    assert 'call render_chart' in block
    assert format_fewshot_block([]) == ''


def test_per_cluster_cap():
    # Distinct prompts, same cluster -> capped at per_cluster.
    trajs = [
        _traj('c1', [_turn(mid='m1', prompt='a', chart_type='bar')]),
        _traj('c2', [_turn(mid='m2', prompt='b', chart_type='bar')]),
        _traj('c3', [_turn(mid='m3', prompt='c', chart_type='bar')]),
    ]
    bank = mine_fewshot(trajs, per_cluster=2)
    assert len(bank) == 2
