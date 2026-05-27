"""Rule-based scoring for LLM-in-the-loop eval (Phase 5).

Each check maps 1:1 to a system-prompt rule, so a failing candidate names the exact
rule it broke. These are the failure modes seen in live QA (freelance code, dataset
display-name guessing, missing render, placeholder chart urls).

LLM-as-judge (narrative quality) is intentionally OUT of v1 — added later behind a
flag; documented in docs/spec/llm-eval.md.
"""

from __future__ import annotations

from typing import Any

# Phrases that indicate a stale/expired query_id error (rule 5 recovery trigger).
_QID_ERROR_HINTS = ('expired', 'not found', 'not_found', 'query_id')


def _render_url(result: Any) -> str | None:
    """Extract the chart image url from a render_chart result.

    render_chart returns it nested under `attachment.url`; tolerate a flat `url` too.
    """
    if not isinstance(result, dict):
        return None
    att = result.get('attachment')
    if isinstance(att, dict) and att.get('url'):
        return att['url']
    return result.get('url')


def _candidate_signals(candidate: dict[str, Any]) -> dict[str, Any]:
    """Derive the rule checks from a CandidateRun-shaped dict.

    ``candidate`` has: final_content, executed_calls (list of
    {name, args, success, error?, result?}), error.
    """
    calls = candidate.get('executed_calls') or []
    final = candidate.get('final_content') or ''

    queries = [c for c in calls if c.get('name') == 'query_dataset']
    renders = [c for c in calls if c.get('name') == 'render_chart']

    first_query_idx = next((i for i, c in enumerate(calls) if c.get('name') == 'query_dataset'), None)
    first_render_idx = next((i for i, c in enumerate(calls) if c.get('name') == 'render_chart'), None)

    # recovered_query_id: a render failed with a query_id hint, and a later render succeeded.
    recovered = None
    failed_render_idx = next(
        (
            i
            for i, c in enumerate(renders)
            if not c.get('success') and any(h in str(c.get('error', '')).lower() for h in _QID_ERROR_HINTS)
        ),
        None,
    )
    if failed_render_idx is not None:
        recovered = any(c.get('success') for c in renders[failed_render_idx + 1 :])

    # embedded_real_url: a successful render's url string appears in the final answer.
    embedded = None
    success_urls = [u for c in renders if c.get('success') and (u := _render_url(c.get('result')))]
    if success_urls:
        embedded = any(url in final for url in success_urls)

    workflow_ok = None
    if renders:
        workflow_ok = (
            first_query_idx is not None
            and first_render_idx is not None
            and first_query_idx < first_render_idx
        )
    elif queries:
        workflow_ok = True

    return {
        'used_tools': bool(queries),
        'resolved_dataset': any(c.get('success') for c in queries) if queries else False,
        'render_succeeded': any(c.get('success') for c in renders) if renders else False,
        'recovered_query_id': recovered,
        'embedded_real_url': embedded,
        'tool_workflow_ok': workflow_ok,
    }


_CHECKS = (
    'used_tools',
    'resolved_dataset',
    'render_succeeded',
    'recovered_query_id',
    'embedded_real_url',
    'tool_workflow_ok',
)


def _verdict(candidate_val: Any, baseline_val: Any) -> str:
    """Per-check verdict comparing candidate to recorded baseline."""
    if candidate_val is None:
        return 'not_applicable'
    if baseline_val is None:
        return 'candidate_only'
    if candidate_val == baseline_val:
        return 'unchanged'
    return 'improved' if candidate_val and not baseline_val else 'regressed'


def score_candidate(case: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Score one candidate run against its eval case's recorded baseline.

    ``case`` is an EvalCase-shaped dict (needs `recorded` baseline signals);
    ``candidate`` is a CandidateRun-shaped dict. Returns per-check candidate/baseline/
    verdict plus an aggregate (regressed_checks, passed).
    """
    cand = _candidate_signals(candidate)
    base = case.get('recorded') or {}

    checks: dict[str, Any] = {}
    regressed: list[str] = []
    improved: list[str] = []
    for name in _CHECKS:
        cv = cand.get(name)
        bv = base.get(name)
        verdict = _verdict(cv, bv)
        checks[name] = {'candidate': cv, 'baseline': bv, 'verdict': verdict}
        if verdict == 'regressed':
            regressed.append(name)
        elif verdict == 'improved':
            improved.append(name)

    return {
        'chat_id': case.get('chat_id'),
        'message_id': case.get('message_id'),
        'error': candidate.get('error'),
        'checks': checks,
        'regressed_checks': regressed,
        'improved_checks': improved,
        # A run that errored out (no final answer) can't be said to pass.
        'passed': not regressed and candidate.get('error') is None,
    }


def summarize_eval_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-case score reports into an A/B verdict (mirrors replay rollup)."""
    from collections import Counter

    regressed_by_check: Counter = Counter()
    improved_by_check: Counter = Counter()
    regressed_cases: list[str | None] = []
    errored = 0
    for r in reports:
        if r.get('error'):
            errored += 1
        for name in r.get('regressed_checks', []):
            regressed_by_check[name] += 1
        for name in r.get('improved_checks', []):
            improved_by_check[name] += 1
        if r.get('regressed_checks'):
            regressed_cases.append(r.get('chat_id'))

    return {
        'cases': len(reports),
        'errored': errored,
        'regressed_cases': len(regressed_cases),
        'regressed_by_check': dict(regressed_by_check.most_common()),
        'improved_by_check': dict(improved_by_check.most_common()),
        # Gate: any regression (or no cases scored) fails the candidate.
        'passed': bool(reports) and not regressed_cases and errored == 0,
    }
