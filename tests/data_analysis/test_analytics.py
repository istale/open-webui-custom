from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.utils.data_analysis.analytics import (
    summarize_replay_reports,
    summarize_trajectories,
)


def test_summarize_trajectories_clusters_failures_and_engagement():
    trajs = [
        {
            'turns': [
                {
                    'actions': [
                        {'success': True},
                        {'success': False, 'error_code': 'VALUE', 'args': {'chart_type': 'bar'}},
                        {'success': False, 'error_code': 'VALUE', 'args': {'chart_type': 'bar'}},
                    ],
                    'outcome': {'usage': {'total_tokens': 100}},
                    'reward': {'rating': 1},
                    'charts_rendered': ['c1'],
                    'charts_viewed': ['c1'],
                },
                {
                    'actions': [{'success': True}],
                    'outcome': {'usage': {'total_tokens': 50}},
                    'charts_rendered': ['c2'],
                    'charts_viewed': [],
                },
            ]
        }
    ]
    s = summarize_trajectories(trajs)
    assert s['chats'] == 1 and s['turns'] == 2
    assert s['tool_calls'] == 4 and s['tool_failures'] == 2
    assert s['self_correction_turns'] == 1  # first turn had 2 failures
    assert s['failures_by_error_code'] == {'VALUE': 2}
    assert s['failures_by_chart_type'] == {'bar': 2}
    assert s['total_tokens'] == 150
    assert s['reward_distribution'] == {'1': 1}
    assert s['charts_rendered'] == 2 and s['charts_viewed'] == 1
    assert s['chart_view_through_rate'] == 0.5


def test_summarize_replay_reports_verdict():
    reports = [
        {'chat_id': 'a', 'summary': {'total_actions': 2, 'replayable': 2, 'matches': 2, 'diverged': 0}},
        {'chat_id': 'b', 'summary': {'total_actions': 3, 'replayable': 3, 'matches': 2, 'diverged': 1}},
    ]
    v = summarize_replay_reports(reports)
    assert v['diverged'] == 1 and v['passed'] is False
    assert v['diverged_chats'] == ['b']
