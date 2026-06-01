"""Satisfaction proxy signals (Stage 2, minimal).

When thumbs are sparse, satisfaction has to be inferred. Four cheap proxies
read straight off the existing ledger:

- chart-view-through:   rendered charts that got looked at
- followup-click:       chats where the user clicked at least one suggested follow-up
- multi-turn rate:      chats with >1 assistant turn (engagement OR refinement)
- avg-turns-per-chat:   same, as a magnitude

Each is approximate — none is a substitute for explicit feedback — but together
they surface whether prompt changes are landing or being abandoned.
"""

from __future__ import annotations

from typing import Any


def summarize_satisfaction(trajectories: list[dict[str, Any]]) -> dict[str, Any]:
    n_chats = len(trajectories)
    rendered = 0
    viewed = 0
    chats_with_render = 0
    chats_with_followup = 0
    multi_turn_chats = 0
    total_turns = 0

    for traj in trajectories:
        turns = traj.get('turns', []) or []
        total_turns += len(turns)
        if len(turns) > 1:
            multi_turn_chats += 1

        chat_renders = 0
        chat_viewed = set()
        for turn in turns:
            chat_renders += len(turn.get('charts_rendered') or [])
            for cid in turn.get('charts_viewed') or []:
                chat_viewed.add(cid)
        rendered += chat_renders
        viewed += len(chat_viewed)
        if chat_renders > 0:
            chats_with_render += 1

        if any(
            (e.get('event_type') == 'followup.clicked')
            for e in traj.get('session_events') or []
        ):
            chats_with_followup += 1

    def _rate(num: int, denom: int) -> float | None:
        return round(num / denom, 3) if denom else None

    return {
        'chats': n_chats,
        'turns': total_turns,
        'avg_turns_per_chat': _rate(total_turns, n_chats),
        'multi_turn_chat_rate': _rate(multi_turn_chats, n_chats),
        'charts_rendered': rendered,
        'charts_viewed': viewed,
        'chart_view_through_rate': _rate(viewed, rendered),
        'chats_with_render': chats_with_render,
        'chats_with_followup_click': chats_with_followup,
        'followup_click_rate_when_rendered': _rate(chats_with_followup, chats_with_render),
    }
