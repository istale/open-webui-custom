"""Trajectory reconstruction for interaction replay (Phase 1).

A *trajectory* is the canonical, ordered (input -> actions -> outcome) view of a
data-analysis chat, rebuilt purely from the `data_analysis_events` ledger. The
ledger already captures the request snapshot (model.request_prepared), every tool
call with its args (tool.*), thinking, and the assistant outcome
(message.assistant_completed) — so no coupling to the native chat document is
needed.

`build_trajectory` is a pure function over a list of event dicts (unit-testable);
`load_trajectory` is the async DB wrapper.

Correlation rules (see implementation-notes D9):
- Assistant-turn events share `message_id` -> grouped into a Turn.
- `prompt.submitted` has no message_id (fired before the assistant message
  exists) -> paired to the next turn by ts ordering.
- `chart.rendered` (frontend, no message_id) -> attached to the turn whose
  render produced its chart_id.
- `workspace.opened` / `dataset.selected` -> session-level timeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolAction:
    ts: int
    tool_name: str | None
    event_type: str
    success: bool
    error_code: str | None
    duration_ms: int | None
    args: dict[str, Any]
    result: dict[str, Any]


@dataclass
class Turn:
    message_id: str | None
    ts: int
    user_prompt: str | None = None
    request: dict[str, Any] | None = None
    thinking: list[dict[str, Any]] = field(default_factory=list)
    actions: list[ToolAction] = field(default_factory=list)
    outcome: dict[str, Any] | None = None
    charts_rendered: list[str] = field(default_factory=list)
    reward: dict[str, Any] | None = None  # Phase 3


@dataclass
class Trajectory:
    chat_id: str | None
    user_id: str | None
    session_events: list[dict[str, Any]] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'chat_id': self.chat_id,
            'user_id': self.user_id,
            'session_events': self.session_events,
            'turns': [
                {**asdict(turn), 'actions': [asdict(a) for a in turn.actions]} for turn in self.turns
            ],
        }


# Tool args / result fields we lift out of the raw payload onto the action.
_ARG_KEYS = ('sql', 'query', 'dataset_id', 'x', 'y', 'color', 'facet', 'chart_type', 'query_id')
_RESULT_KEYS = (
    'query_id',
    'chart_id',
    'row_count',
    'truncated',
    'image_size_bytes',
    'statistics',
    'error_message',
)
_SESSION_EVENT_TYPES = ('workspace.opened', 'dataset.selected', 'stream.timeout', 'stream.aborted')


def _as_dict(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    # pydantic model
    if hasattr(event, 'model_dump'):
        return event.model_dump()
    raise TypeError(f'unsupported event type: {type(event)!r}')


def _payload(ev: dict[str, Any]) -> dict[str, Any]:
    p = ev.get('payload')
    return p if isinstance(p, dict) else {}


def build_trajectory(events: list[Any]) -> Trajectory:
    """Reconstruct a Trajectory from a chat's events (any order)."""
    evs = sorted((_as_dict(e) for e in events), key=lambda e: (e.get('ts') or 0, e.get('id') or ''))

    chat_id = next((e.get('chat_id') for e in evs if e.get('chat_id')), None)
    user_id = next((e.get('user_id') for e in evs if e.get('user_id')), None)

    # 1. Group assistant-turn events by message_id, preserving first-seen order.
    turns_by_msg: dict[str, Turn] = {}
    order: list[str] = []
    pending_prompts: list[dict[str, Any]] = []
    session_events: list[dict[str, Any]] = []
    chart_rendered: list[dict[str, Any]] = []

    def _turn_for(msg_id: str, ts: int) -> Turn:
        if msg_id not in turns_by_msg:
            turns_by_msg[msg_id] = Turn(message_id=msg_id, ts=ts)
            order.append(msg_id)
        return turns_by_msg[msg_id]

    for ev in evs:
        et = ev.get('event_type', '')
        mid = ev.get('message_id')
        ts = ev.get('ts') or 0
        pl = _payload(ev)

        if et in _SESSION_EVENT_TYPES:
            session_events.append({'ts': ts, 'event_type': et, 'payload': pl})
            continue

        if et == 'prompt.submitted':
            pending_prompts.append({'ts': ts, 'payload': pl})
            continue

        if et == 'chart.rendered':
            chart_rendered.append({'ts': ts, 'payload': pl})
            continue

        if not mid:
            continue

        turn = _turn_for(mid, ts)

        if et == 'model.request_prepared':
            turn.request = pl
        elif et == 'model.thinking_completed':
            turn.thinking.append({'n_chars': pl.get('n_chars'), 'duration_ms': ev.get('duration_ms')})
        elif et == 'message.assistant_completed':
            turn.outcome = pl
        elif et.startswith('tool.'):
            args = {k: pl[k] for k in _ARG_KEYS if k in pl}
            # dataset_id lives in the event column, not the payload; lift it in
            # so replay can re-issue query_dataset against the right dataset.
            if ev.get('dataset_id') and 'dataset_id' not in args:
                args['dataset_id'] = ev['dataset_id']
            turn.actions.append(
                ToolAction(
                    ts=ts,
                    tool_name=ev.get('tool_name'),
                    event_type=et,
                    success=bool(ev.get('success', True)),
                    error_code=ev.get('error_code'),
                    duration_ms=ev.get('duration_ms'),
                    args=args,
                    result={k: pl[k] for k in _RESULT_KEYS if k in pl},
                )
            )

    turns = [turns_by_msg[m] for m in order]
    for turn in turns:
        turn.actions.sort(key=lambda a: a.ts)

    # 2. Pair each user prompt with the first turn that starts at/after it.
    pending_prompts.sort(key=lambda p: p['ts'])
    for prompt in pending_prompts:
        target = next((t for t in turns if t.ts >= prompt['ts'] and t.user_prompt is None), None)
        target = target or next((t for t in reversed(turns) if t.user_prompt is None), None)
        if target is not None:
            target.user_prompt = prompt['payload'].get('prompt_text')

    # 3. Attach chart.rendered to the turn whose render produced that chart_id.
    chart_to_turn = {
        a.result.get('chart_id'): t
        for t in turns
        for a in t.actions
        if a.result.get('chart_id')
    }
    for cr in chart_rendered:
        cid = cr['payload'].get('chart_id')
        turn = chart_to_turn.get(cid)
        if turn is not None and cid not in turn.charts_rendered:
            turn.charts_rendered.append(cid)

    return Trajectory(chat_id=chat_id, user_id=user_id, session_events=session_events, turns=turns)


async def load_trajectory(chat_id: str, include_deleted: bool = False) -> Trajectory:
    """Load a chat's events from the ledger and build its trajectory."""
    from open_webui.models.data_analysis_events import DataAnalysisEvents

    events = await DataAnalysisEvents.list_events_by_chat_id(chat_id, include_deleted=include_deleted)
    return build_trajectory(events)
