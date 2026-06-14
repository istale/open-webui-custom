"""Aggregate analytics over trajectories for enhancement (Phase 4).

Pure functions (unit-testable) that turn a list of trajectory dicts into the
signals you'd watch to improve the system: tool failure clustering, in-turn
self-correction (retry) rates, chart-type failure rates, and token totals.
Feeds the regression-eval gate and any dashboard.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_trajectories(trajectories: list[dict[str, Any]]) -> dict[str, Any]:
    n_chats = len(trajectories)
    n_turns = 0
    tool_calls = 0
    tool_failures = 0
    fail_by_code: Counter = Counter()
    fail_by_chart_type: Counter = Counter()
    retry_turns = 0  # turns with >1 failed tool action (self-correction)
    total_tokens = 0
    rewards = Counter()  # rating distribution
    charts_rendered = 0
    charts_viewed = 0

    for traj in trajectories:
        for turn in traj.get('turns', []):
            n_turns += 1
            turn_failures = 0
            for action in turn.get('actions', []):
                tool_calls += 1
                if not action.get('success', True):
                    tool_failures += 1
                    turn_failures += 1
                    if action.get('error_code'):
                        fail_by_code[action['error_code']] += 1
                    ct = (action.get('args') or {}).get('chart_type')
                    if ct:
                        fail_by_chart_type[ct] += 1
            if turn_failures > 1:
                retry_turns += 1

            outcome = turn.get('outcome') or {}
            usage = outcome.get('usage') or {}
            total_tokens += usage.get('total_tokens') or 0

            reward = turn.get('reward') or {}
            if reward.get('rating') is not None:
                rewards[str(reward['rating'])] += 1

            charts_rendered += len(turn.get('charts_rendered') or [])
            charts_viewed += len(turn.get('charts_viewed') or [])

    return {
        'chats': n_chats,
        'turns': n_turns,
        'tool_calls': tool_calls,
        'tool_failures': tool_failures,
        'tool_failure_rate': round(tool_failures / tool_calls, 4) if tool_calls else 0.0,
        'self_correction_turns': retry_turns,
        'failures_by_error_code': dict(fail_by_code.most_common()),
        'failures_by_chart_type': dict(fail_by_chart_type.most_common()),
        'total_tokens': total_tokens,
        'reward_distribution': dict(rewards),
        'charts_rendered': charts_rendered,
        'charts_viewed': charts_viewed,
        'chart_view_through_rate': round(charts_viewed / charts_rendered, 4)
        if charts_rendered
        else 0.0,
    }


def summarize_replay_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up replay_trajectory() reports into a regression verdict."""
    total = replayable = matches = diverged = 0
    diverged_chats: list[str] = []
    for r in reports:
        s = r.get('summary', {})
        total += s.get('total_actions', 0)
        replayable += s.get('replayable', 0)
        matches += s.get('matches', 0)
        d = s.get('diverged', 0)
        diverged += d
        if d:
            diverged_chats.append(r.get('chat_id'))
    return {
        'chats_replayed': len(reports),
        'total_actions': total,
        'replayable': replayable,
        'matches': matches,
        'diverged': diverged,
        'diverged_chats': diverged_chats,
        'passed': diverged == 0,
    }
