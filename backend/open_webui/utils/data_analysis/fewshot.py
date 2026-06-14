"""Few-shot mining from high-reward trajectories (Phase 6).

Select exemplary turns from captured trajectories and distill them into a curated
few-shot bank (`request -> ideal tool sequence`) that can prime the model toward the
tool workflow it already nailed. v1 is an OFFLINE artifact: mine to a versioned
bank, validate it via Phase 5 eval (`eval --fewshot`), and only then consider live
injection.

Pure + testable: `mine_fewshot(trajectories, ...)` takes trajectory dicts (and
optional replay reports) and returns exemplar dicts. No DB / network here.

Known gap: the ledger stores `message.assistant_completed.n_chars`, not the assistant
answer TEXT, so an exemplar's `final_answer` is unavailable (None). The teaching
signal we DO have — the exact SQL + chart args (the ideal tool sequence) — is the
valuable part; the final prose is mostly "here is the chart ![](url)". Documented like
the render-caption gap (notes D11).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Map a tool event_type to the model-facing tool name.
_TOOL_NAME = {
    'tool.query_dataset': 'query_dataset',
    'tool.render_chart': 'render_chart',
    'tool.list_datasets': 'list_datasets',
    'tool.summarize_data': 'summarize_data',
}


def _tool_name(event_type: str) -> str | None:
    for prefix, name in _TOOL_NAME.items():
        if event_type.startswith(prefix):
            return name
    return None


def _is_thumbs_up(reward: dict[str, Any] | None) -> bool | None:
    """Return True (up), False (down), or None (no rating)."""
    if not reward:
        return None
    rating = reward.get('rating')
    if rating is None:
        return None
    try:
        return float(rating) > 0
    except (TypeError, ValueError):
        return str(rating).lower() in ('up', 'good', 'positive', '1')


def _turn_quality(turn: dict[str, Any]) -> dict[str, Any]:
    """Compute selection signals for a turn."""
    actions = turn.get('actions', [])
    failures = sum(1 for a in actions if not a.get('success', True))
    rendered = bool(turn.get('charts_rendered'))
    thumb = _is_thumbs_up(turn.get('reward'))
    return {'failures': failures, 'rendered': rendered, 'thumb': thumb, 'n_actions': len(actions)}


def _turn_is_exemplary(q: dict[str, Any]) -> bool:
    # Explicit thumbs-down disqualifies regardless of cleanliness.
    if q['thumb'] is False:
        return False
    # Thumbs-up always qualifies (user vouched for it).
    if q['thumb'] is True:
        return q['n_actions'] > 0
    # No rating: accept clean turns, or a single recover-and-retry that still rendered.
    if q['failures'] == 0:
        return q['n_actions'] > 0
    if q['failures'] == 1 and q['rendered']:
        return True
    return False  # thrashing (>1 failure) is not exemplary


def _ideal_tool_sequence(turn: dict[str, Any]) -> list[dict[str, Any]]:
    """The successful tool calls, in order — drops failed attempts so the exemplar
    teaches the clean path even if the original turn self-corrected."""
    seq = []
    for a in turn.get('actions', []):
        if not a.get('success', True):
            continue
        name = _tool_name(a.get('event_type', ''))
        if not name:
            continue
        seq.append({'tool': name, 'args': a.get('args') or {}})
    return seq


def _cluster_key(seq: list[dict[str, Any]]) -> tuple:
    """Diversity bucket: (chart_type, dataset_id) of the sequence."""
    chart_type = next(
        (a['args'].get('chart_type') for a in seq if a['tool'] == 'render_chart' and a['args'].get('chart_type')),
        None,
    )
    dataset = next((a['args'].get('dataset_id') for a in seq if a['args'].get('dataset_id')), None)
    return (chart_type, dataset)


def _content_hash(user_request: str | None, seq: list[dict[str, Any]]) -> str:
    blob = json.dumps({'u': user_request, 's': seq}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _rank(exemplar: dict[str, Any]) -> tuple:
    """Sort key (descending preference): thumbs-up first, then more tool steps."""
    q = exemplar['_q']
    return (1 if q['thumb'] is True else 0, len(exemplar['tool_sequence']))


def mine_fewshot(
    trajectories: list[dict[str, Any]],
    *,
    replay_reports: list[dict[str, Any]] | None = None,
    current_prompt_version: str | None = None,
    current_tool_spec_version: str | None = None,
    per_cluster: int = 2,
    max_examples: int | None = None,
    redact: bool = False,
) -> list[dict[str, Any]]:
    """Select exemplary turns and format them into a few-shot bank.

    Gates, in order (interaction-replay §4 / D16 discipline):
      1. reward & cleanliness (thumbs-up, or clean / single-recovery turn);
      2. still-works — if `replay_reports` given, the chat must have passed replay;
      3. version-gate — `prompt_version`/`tool_spec_version` match current (when given);
      4. diversity/dedup — at most `per_cluster` per (chart_type, dataset), deduped by
         content hash, capped to `max_examples`.
    """
    passed_chats: set | None = None
    if replay_reports is not None:
        passed_chats = {
            r.get('chat_id')
            for r in replay_reports
            if r.get('summary', {}).get('diverged', 0) == 0
            and r.get('summary', {}).get('replayable', 0) > 0
        }

    candidates: list[dict[str, Any]] = []
    for traj in trajectories:
        chat_id = traj.get('chat_id')
        if passed_chats is not None and chat_id not in passed_chats:
            continue
        for turn in traj.get('turns', []):
            req = turn.get('request') or {}
            # 3. version-gate
            if current_prompt_version is not None and req.get('prompt_version') != current_prompt_version:
                continue
            if current_tool_spec_version is not None and req.get('tool_spec_version') != current_tool_spec_version:
                continue

            q = _turn_quality(turn)
            # 1. reward & cleanliness
            if not _turn_is_exemplary(q):
                continue
            seq = _ideal_tool_sequence(turn)
            if not seq:
                continue

            user_request = turn.get('user_prompt')
            exemplar = {
                'user_request': '[REDACTED]' if redact and user_request else user_request,
                'tool_sequence': seq,
                'final_answer': None,  # not stored in the ledger (see module docstring)
                'provenance': {
                    'chat_id': chat_id,
                    'message_id': turn.get('message_id'),
                    'prompt_version': req.get('prompt_version'),
                    'tool_spec_version': req.get('tool_spec_version'),
                    'reward': turn.get('reward'),
                },
                '_q': q,
                '_cluster': _cluster_key(seq),
                '_hash': _content_hash(user_request, seq),
            }
            candidates.append(exemplar)

    # 4. dedup by content hash, then keep best per cluster.
    seen: set = set()
    deduped: list[dict[str, Any]] = []
    for ex in candidates:
        if ex['_hash'] in seen:
            continue
        seen.add(ex['_hash'])
        deduped.append(ex)

    deduped.sort(key=_rank, reverse=True)
    per_cluster_count: dict[tuple, int] = {}
    kept: list[dict[str, Any]] = []
    for ex in deduped:
        key = ex['_cluster']
        if per_cluster_count.get(key, 0) >= per_cluster:
            continue
        per_cluster_count[key] = per_cluster_count.get(key, 0) + 1
        kept.append(ex)
        if max_examples is not None and len(kept) >= max_examples:
            break

    # Strip internal bookkeeping fields before returning the bank.
    for ex in kept:
        ex.pop('_q', None)
        ex.pop('_cluster', None)
        ex.pop('_hash', None)
    return kept


def format_fewshot_block(exemplars: list[dict[str, Any]]) -> str:
    """Render a few-shot bank into a system-prompt-appendable text block.

    Used by `eval --fewshot` to validate that injecting the bank improves scores,
    and (later, behind review) by the live prompt builder.
    """
    if not exemplars:
        return ''
    lines = ['', '[Few-shot examples — ideal tool usage from past high-quality answers]']
    for i, ex in enumerate(exemplars, 1):
        lines.append(f'Example {i}:')
        if ex.get('user_request'):
            lines.append(f'  User: {ex["user_request"]}')
        for step in ex.get('tool_sequence', []):
            lines.append(f'  call {step["tool"]}({json.dumps(step.get("args", {}), ensure_ascii=False)})')
    return '\n'.join(lines)
