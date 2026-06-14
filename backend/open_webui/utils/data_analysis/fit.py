"""Intent-to-tool fit (Stage 2, minimal).

For each turn that carries both an intent verb (e.g. 趨勢 / 異常 / 比較 / 關係)
and a rendered chart_type, check whether the chosen chart matches what that verb
typically calls for. Mismatches surface "the model rendered, but did it pick the
right form?" — the kind of semantic-fail that rule-based eval misses.

Intentionally tiny: a static verb→expected-chart map, no NLP. False positives
are fine; the output is a *prompt for the human to look*, not a verdict.
"""

from __future__ import annotations

from typing import Any

# Chinese + English intent verbs → expected chart_types (any-of match).
# Add to this map as new domain language appears (intents subcommand surfaces it).
_VERB_TO_CHARTS: dict[str, set[str]] = {
    # Chinese
    '趨勢': {'line', 'control', 'spc'},
    '異常': {'control', 'spc', 'box'},
    '管制': {'control', 'spc'},
    '分布': {'box', 'histogram'},
    '比較': {'bar', 'box'},
    '關係': {'scatter'},
    '相關': {'scatter'},
    '占比': {'pareto', 'pie'},
    '排名': {'bar', 'pareto'},
    '隨時間': {'line', 'control', 'spc'},
    # English
    'trend': {'line', 'control', 'spc'},
    'anomaly': {'control', 'spc', 'box'},
    'distribution': {'box', 'histogram'},
    'compare': {'bar', 'box'},
    'correlation': {'scatter'},
    'relationship': {'scatter'},
    'over time': {'line', 'control', 'spc'},
}


def _verbs_in(prompt: str) -> list[str]:
    if not prompt:
        return []
    lower = prompt.lower()
    found = []
    for verb in _VERB_TO_CHARTS:
        # ASCII verbs match case-insensitively; Chinese matches as-is.
        needle = verb.lower() if verb.isascii() else verb
        haystack = lower if verb.isascii() else prompt
        if needle in haystack:
            found.append(verb)
    return found


def _rendered_chart_types(actions: list[dict[str, Any]]) -> list[str]:
    return [
        (a.get('args') or {}).get('chart_type')
        for a in actions
        if a.get('event_type', '').startswith('tool.render_chart')
        and a.get('success')
        and (a.get('args') or {}).get('chart_type')
    ]


def summarize_fit(trajectories: list[dict[str, Any]], *, sample_limit: int = 10) -> dict[str, Any]:
    matched = 0
    mismatched = 0
    no_signal = 0
    not_rendered = 0
    mismatches: list[dict[str, Any]] = []

    for traj in trajectories:
        for turn in traj.get('turns', []):
            actions = turn.get('actions', [])
            charts = _rendered_chart_types(actions)
            if not charts:
                not_rendered += 1
                continue
            prompt = turn.get('user_prompt') or ''
            verbs = _verbs_in(prompt)
            if not verbs:
                no_signal += 1
                continue
            expected: set[str] = set()
            for v in verbs:
                expected |= _VERB_TO_CHARTS[v]
            actual = set(charts)
            if actual & expected:
                matched += 1
            else:
                mismatched += 1
                if len(mismatches) < sample_limit:
                    mismatches.append({
                        'sample_prompt': prompt[:120],
                        'verbs': verbs,
                        'expected_any_of': sorted(expected),
                        'actual': sorted(actual),
                    })

    with_signal = matched + mismatched

    def _rate(num: int, denom: int) -> float | None:
        return round(num / denom, 3) if denom else None

    return {
        'turns_with_render_and_verb': with_signal,
        'matched': matched,
        'mismatched': mismatched,
        'fit_rate': _rate(matched, with_signal),
        'turns_no_intent_verb': no_signal,
        'turns_no_render': not_rendered,
        'sample_mismatches': mismatches,
    }
