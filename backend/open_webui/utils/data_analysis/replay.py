"""Deterministic trajectory replay + export for interaction replay (Phase 2).

Two capabilities:

1. `export_trajectories(...)` — produce trajectory records (JSONL-ready) from the
   ledger, with optional PII redaction and a retention window. Feeds eval/training.

2. `replay_trajectory(traj, repo)` — re-execute the *recorded tool calls* (the SQL
   and chart args captured in the ledger) against the current tool implementation
   backed by a deterministic repository, and diff the outcome vs. what was recorded.
   This catches regressions ("would this trajectory's tool sequence still work
   today?") WITHOUT needing the LLM or a live provider.

Why tool-replay and not full LLM-replay: re-running the model is non-deterministic
and needs a provider. The tool layer is deterministic with InMemoryDatasetRepository,
so replaying the recorded actions is reproducible and CI-friendly. render_chart's
caption params (title/explanation_*) aren't in the ledger, but they don't affect
whether a render succeeds — only x/y/color/chart_type/query_id do, which we have, so
synthesized placeholders are sufficient for a faithful pass/fail replay (D11).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

_REDACT_FIELDS = ('user_prompt',)
_REDACT_REQUEST_FIELDS = ('system_prompt',)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _redact_trajectory(d: dict[str, Any]) -> dict[str, Any]:
    for turn in d.get('turns', []):
        for f in _REDACT_FIELDS:
            if turn.get(f):
                turn[f] = '[REDACTED]'
        req = turn.get('request') or {}
        for f in _REDACT_REQUEST_FIELDS:
            if req.get(f):
                req[f] = '[REDACTED]'
    return d


async def export_trajectories(
    *,
    chat_ids: list[str] | None = None,
    since_ts: int | None = None,
    redact: bool = False,
    include_deleted: bool = False,
    with_feedback: bool = True,
) -> list[dict[str, Any]]:
    """Build trajectory records for export.

    - `include_deleted=False` (default) honours soft-delete: user-removed chats are
      excluded (consent/retention).
    - `since_ts` applies a retention window (only chats with events at/after it).
    - `redact=True` masks free-text (user prompt, system prompt) for sharing.
    - `with_feedback=True` overlays thumbs ratings from Open WebUI's feedback table.
    """
    from open_webui.models.data_analysis_events import DataAnalysisEvents
    from open_webui.utils.data_analysis.trajectory import attach_feedback, build_trajectory

    if chat_ids is None:
        chat_ids = await DataAnalysisEvents.list_chat_ids(
            include_deleted=include_deleted, since_ts=since_ts
        )

    # New-chat `prompt.submitted` (and `chart.*`) fire before chat_id exists, so
    # they land chat-less. Pair each orphan to the chat whose first event lands
    # within ORPHAN_PAIR_WINDOW_MS after the orphan ts (forward-nearest).
    ORPHAN_PAIR_WINDOW_MS = 120_000  # 2 minutes is generous; first turn rarely takes longer
    orphans = await DataAnalysisEvents.list_orphan_events(
        ['prompt.submitted', 'chart.rendered', 'chart.viewed'], since_ts=since_ts
    )
    chat_events: dict[str, list] = {}
    chat_first_ts: dict[str, int] = {}
    for cid in chat_ids:
        evs = await DataAnalysisEvents.list_events_by_chat_id(cid, include_deleted=include_deleted)
        if not evs:
            continue
        chat_events[cid] = evs
        chat_first_ts[cid] = min(e.ts for e in evs)
    for orphan in orphans:
        best = None
        best_gap = None
        for cid, ts0 in chat_first_ts.items():
            gap = ts0 - orphan.ts
            if 0 <= gap <= ORPHAN_PAIR_WINDOW_MS and (best_gap is None or gap < best_gap):
                best, best_gap = cid, gap
        if best is not None:
            chat_events[best].append(orphan)

    out: list[dict[str, Any]] = []
    for cid, events in chat_events.items():
        d = build_trajectory(events).to_dict()
        if with_feedback:
            try:
                from open_webui.models.feedbacks import Feedbacks

                feedbacks = await Feedbacks.get_feedbacks_by_chat_id(cid)
                d = attach_feedback(d, [fb.model_dump() for fb in feedbacks])
            except Exception:  # noqa: BLE001 — feedback overlay is best-effort
                pass
        if redact:
            d = _redact_trajectory(d)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def replay_trajectory(traj: dict[str, Any], repo, user_id: str = 'replay') -> dict[str, Any]:
    """Re-execute the recorded tool calls of a trajectory deterministically.

    `traj` is a `Trajectory.to_dict()`. `repo` is a DatasetRepository (e.g.
    InMemoryDatasetRepository) — replay is only meaningful against deterministic
    data. Returns a report with per-action match/divergence and a summary.
    """
    import tempfile

    from open_webui.tools.data_analysis.tool_module import Tools
    from open_webui.utils.data_analysis import set_repository
    from open_webui.utils.data_analysis.chart_store import ChartStore
    from open_webui.utils.data_analysis.query_cache import QueryCache

    set_repository(repo)
    tools = Tools()
    tools.query_cache = QueryCache()
    tools.chart_store = ChartStore(Path(tempfile.mkdtemp(prefix='da-replay-')))
    user = {'id': user_id}

    results: list[dict[str, Any]] = []
    query_id_map: dict[str, str] = {}  # recorded query_id -> replayed query_id

    for turn in traj.get('turns', []):
        for action in turn.get('actions', []):
            et = action.get('event_type', '')
            args = action.get('args', {})
            recorded_success = bool(action.get('success', True))
            entry: dict[str, Any] = {'event_type': et, 'recorded_success': recorded_success}

            try:
                if et.startswith('tool.query_dataset'):
                    sql = args.get('sql') or args.get('query') or ''
                    res = tools.query_dataset(
                        dataset_id=args.get('dataset_id') or _dataset_from_sql(sql),
                        query=sql,
                        __user__=user,
                    )
                    new_qid = res.get('query_id')
                    rec_qid = (action.get('result') or {}).get('query_id')
                    if rec_qid and new_qid:
                        query_id_map[rec_qid] = new_qid
                    entry.update(replay_success=True, replayed_query_id=new_qid)

                elif et.startswith('tool.render_chart'):
                    # Pre-Phase-0 renders didn't record x/y, so they can't be
                    # faithfully replayed — classify as not-replayable (not diverged)
                    # rather than forcing a false failure on old trajectories.
                    if not args.get('x') and not args.get('y'):
                        entry.update(replay_success=None, note='render args (x/y) not recorded')
                        results.append(entry)
                        continue
                    rec_qid = args.get('query_id') or (action.get('result') or {}).get('query_id')
                    qid = query_id_map.get(rec_qid, rec_qid)
                    tools.render_chart(
                        query_id=qid,
                        chart_type=args.get('chart_type') or 'line',
                        x=args.get('x') or '',
                        y=args.get('y') or '',
                        title='replay',
                        explanation_source='replay',
                        explanation_method='replay',
                        explanation_fields=args.get('x') or '',
                        color=args.get('color') or '',
                        facet=args.get('facet') or '',
                        __user__=user,
                    )
                    entry.update(replay_success=True)
                else:
                    entry.update(replay_success=None, note='not replayable')
            except Exception as exc:  # noqa: BLE001 — replay must capture, not raise
                entry.update(replay_success=False, error=f'{type(exc).__name__}: {exc}')

            if entry.get('replay_success') is not None:
                entry['matches_recorded'] = entry['replay_success'] == recorded_success
            results.append(entry)

    replayable = [r for r in results if r.get('replay_success') is not None]
    diverged = [r for r in replayable if not r.get('matches_recorded')]
    return {
        'chat_id': traj.get('chat_id'),
        'ts': int(time.time() * 1000),
        'actions': results,
        'summary': {
            'total_actions': len(results),
            'replayable': len(replayable),
            'matches': len(replayable) - len(diverged),
            'diverged': len(diverged),
        },
    }


def _dataset_from_sql(sql: str) -> str:
    """Best-effort `FROM <table>` extraction so query_dataset can resolve the
    dataset when the recorded action didn't carry an explicit dataset_id."""
    lowered = sql.lower()
    idx = lowered.find('from ')
    if idx == -1:
        return ''
    rest = sql[idx + 5 :].strip()
    token = rest.split()[0] if rest else ''
    return token.strip().strip('`"').rstrip(';')
