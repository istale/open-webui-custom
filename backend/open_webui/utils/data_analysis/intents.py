"""User intent extraction & clustering (Stage 2, minimal).

Pure functions over trajectory dicts. Reads `user_prompt` text from each turn,
normalizes into a "skeleton" (identifiers / numbers masked) and groups by
skeleton to surface WHAT users actually ask. Smallest possible: no embeddings,
no ML, no new dependencies — just string normalization. The point is to make
the user-facing question dimension visible, so prompt changes can be aimed at
real questions instead of guessed ones.

Companion modules: `satisfaction.py` (are users happy with answers), `fit.py`
(does the model pick chart_types that match intent verbs).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# snake_case identifiers (dataset / column names like sensor_readings, temperature_c)
_SNAKE_RE = re.compile(r'\b[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+\b')
# Bare ascii identifiers >= 3 chars (catches things like diameter, batch, etc.)
_IDENT_RE = re.compile(r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b')
_NUM_RE = re.compile(r'\d+(?:\.\d+)?')
_WS_RE = re.compile(r'\s+')
_REPEAT_MASK_RE = re.compile(r'(?:___ ?){2,}')


def extract_skeleton(text: str) -> str:
    """Mask identifiers and numbers; keep verbs / structure words so grouping reflects
    the *shape* of the question rather than its literal subject."""
    if not text:
        return ''
    out = _SNAKE_RE.sub('___', text)
    out = _IDENT_RE.sub('___', out)
    out = _NUM_RE.sub('#', out)
    out = _WS_RE.sub(' ', out).strip()
    # Collapse runs of mask tokens like "___ ___ ___" -> "___" so different column
    # counts don't fragment what is structurally the same question.
    out = _REPEAT_MASK_RE.sub('___ ', out).strip()
    return out


def _outcome(actions: list[dict[str, Any]]) -> str:
    """Best-effort label for whether the assistant turn worked out."""
    has_render = any(a.get('event_type', '').startswith('tool.render_chart') for a in actions)
    if has_render:
        return 'success' if any(
            a.get('success') and a.get('event_type', '').startswith('tool.render_chart')
            for a in actions
        ) else 'failure'
    if any(not a.get('success', True) for a in actions):
        return 'failure'
    return 'success'


def summarize_intents(trajectories: list[dict[str, Any]], *, top: int = 20) -> dict[str, Any]:
    """Cluster user prompts by skeleton; per cluster report count, sample, dataset
    distribution, chart_types used, success/failure split, and failure codes."""
    groups: dict[str, dict[str, Any]] = {}
    n_prompts = 0
    for traj in trajectories:
        for turn in traj.get('turns', []):
            prompt = turn.get('user_prompt')
            if not prompt:
                continue
            n_prompts += 1
            skel = extract_skeleton(prompt)
            if not skel:
                continue
            g = groups.setdefault(
                skel,
                {
                    'skeleton': skel,
                    'count': 0,
                    'sample': prompt,
                    'datasets': Counter(),
                    'chart_types': Counter(),
                    'success': 0,
                    'failure': 0,
                    'failure_codes': Counter(),
                },
            )
            g['count'] += 1
            actions = turn.get('actions', [])
            for a in actions:
                args = a.get('args') or {}
                if args.get('dataset_id'):
                    g['datasets'][args['dataset_id']] += 1
                if a.get('event_type', '').startswith('tool.render_chart') and args.get('chart_type'):
                    g['chart_types'][args['chart_type']] += 1
                if not a.get('success', True) and a.get('error_code'):
                    g['failure_codes'][a['error_code']] += 1
            outcome = _outcome(actions)
            g[outcome] += 1

    items = sorted(groups.values(), key=lambda g: g['count'], reverse=True)[:top]
    for g in items:
        g['datasets'] = dict(g['datasets'].most_common())
        g['chart_types'] = dict(g['chart_types'].most_common())
        g['failure_codes'] = dict(g['failure_codes'].most_common())

    return {
        'total_prompts': n_prompts,
        'unique_skeletons': len(groups),
        'top': items,
    }
