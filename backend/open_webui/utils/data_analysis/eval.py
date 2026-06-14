"""LLM-in-the-loop eval harness (Phase 5).

Re-run a captured turn's INPUT against a candidate (different prompt / model /
params) and observe what the candidate does, so we can score it vs. the recorded
baseline (see scoring.py). Complements deterministic tool-replay (replay.py): replay
freezes the LLM and re-runs tools; eval re-runs the LLM, and still runs its tool
calls deterministically against an in-memory repository.

Scope (v1): single-turn. A turn is evaluable only if its request snapshot has
`message_count <= 2` (system + user) and it carries a user prompt; multi-turn turns
are marked not-evaluable because the snapshot stores message_count, not the full
prior history (interaction-replay §7 version/schema gating).

The live LLM call is injected as ``complete`` so the harness is unit-testable with a
fake; the default is ``llm_client.complete``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

CompleteFn = Callable[..., Awaitable[dict[str, Any]]]

MAX_STEPS = 6  # bound the agentic tool-call loop


@dataclass
class EvalCase:
    chat_id: str | None
    message_id: str | None
    system_prompt: str
    user_prompt: str
    tool_ids: list[str]
    model: str | None
    params: dict[str, Any]
    recorded: dict[str, Any]  # baseline signals lifted from the recorded turn
    reward: dict[str, Any] | None = None


@dataclass
class CandidateRun:
    final_content: str | None
    executed_calls: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    error: str | None = None


def _recorded_signals(turn: dict[str, Any]) -> dict[str, Any]:
    """Lift baseline (recorded) signals from a trajectory turn for comparison."""
    actions = turn.get('actions', [])
    queries = [a for a in actions if a.get('event_type', '').startswith('tool.query_dataset')]
    renders = [a for a in actions if a.get('event_type', '').startswith('tool.render_chart')]
    first_query_ts = min((a.get('ts', 0) for a in queries), default=None)
    first_render_ts = min((a.get('ts', 0) for a in renders), default=None)
    return {
        'used_tools': bool(queries),
        'resolved_dataset': any(a.get('success') for a in queries),
        'render_succeeded': any(a.get('success') for a in renders),
        'tool_workflow_ok': (
            first_query_ts is not None
            and first_render_ts is not None
            and first_query_ts <= first_render_ts
        )
        if renders
        else (True if queries else None),
        'chart_rendered': bool(turn.get('charts_rendered')),
    }


def build_eval_cases(traj: dict[str, Any]) -> list[EvalCase]:
    """Return the evaluable single-turn cases of a trajectory.

    Non-evaluable turns (multi-turn, or missing input) are skipped — callers that
    want a full accounting should compare against len(traj['turns']).
    """
    cases: list[EvalCase] = []
    for turn in traj.get('turns', []):
        req = turn.get('request') or {}
        user_prompt = turn.get('user_prompt')
        system_prompt = req.get('system_prompt')
        message_count = req.get('message_count')
        # Single-turn gate: need input + a single-exchange request.
        if not user_prompt or not system_prompt:
            continue
        if isinstance(message_count, int) and message_count > 2:
            continue
        cases.append(
            EvalCase(
                chat_id=traj.get('chat_id'),
                message_id=turn.get('message_id'),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_ids=req.get('tool_ids') or [],
                model=req.get('model'),
                params=req.get('params') or {},
                recorded=_recorded_signals(turn),
                reward=turn.get('reward'),
            )
        )
    return cases


def _make_tools(repo):
    from open_webui.tools.data_analysis.tool_module import Tools
    from open_webui.utils.data_analysis import set_repository
    from open_webui.utils.data_analysis.chart_store import ChartStore
    from open_webui.utils.data_analysis.query_cache import QueryCache

    set_repository(repo)
    tools = Tools()
    tools.query_cache = QueryCache()
    tools.chart_store = ChartStore(Path(tempfile.mkdtemp(prefix='da-eval-')))
    return tools


def _execute_call(tools, name: str, args: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """Execute one model tool call deterministically; never raises."""
    record: dict[str, Any] = {'name': name, 'args': args}
    try:
        if name == 'list_datasets':
            res = tools.list_datasets(__user__=user)
            record.update(success=True, result={'datasets': res})
        elif name == 'query_dataset':
            res = tools.query_dataset(
                dataset_id=args.get('dataset_id') or '',
                query=args.get('query') or args.get('sql') or '',
                __user__=user,
            )
            record.update(success=True, result=res)
        elif name == 'render_chart':
            res = tools.render_chart(
                query_id=args.get('query_id') or '',
                chart_type=args.get('chart_type') or 'line',
                x=args.get('x') or '',
                y=args.get('y') or '',
                title=args.get('title') or 'eval',
                explanation_source=args.get('explanation_source') or 'eval',
                explanation_method=args.get('explanation_method') or 'eval',
                explanation_fields=args.get('explanation_fields') or (args.get('x') or ''),
                color=args.get('color') or '',
                facet=args.get('facet') or '',
                __user__=user,
            )
            record.update(success=True, result=res)
        else:
            record.update(success=False, error=f'unknown tool: {name}')
    except Exception as exc:  # noqa: BLE001 — capture tool failure, don't raise
        record.update(success=False, error=f'{type(exc).__name__}: {exc}', error_code=_err_code(exc))
    return record


def _err_code(exc: Exception) -> str:
    return exc.__class__.__name__.replace('Error', '').upper() or 'ERROR'


async def run_candidate(
    case: EvalCase,
    repo,
    *,
    complete: CompleteFn,
    candidate_system: str | None = None,
    candidate_model: str | None = None,
    params: dict[str, Any] | None = None,
    system_suffix: str | None = None,
    user_id: str = 'eval',
) -> CandidateRun:
    """Drive a bounded agentic tool-call loop for one eval case.

    ``complete`` is the provider step fn (injected for testability). Tool calls the
    candidate emits are executed deterministically against ``repo`` and their results
    fed back, until the candidate returns a final message or MAX_STEPS is reached.
    """
    from open_webui.utils.data_analysis.llm_client import DATA_ANALYSIS_TOOL_SCHEMAS

    tools = _make_tools(repo)
    user = {'id': user_id}
    system = candidate_system if candidate_system is not None else case.system_prompt
    if system_suffix:
        system = f'{system}\n{system_suffix}'
    model = candidate_model if candidate_model is not None else case.model
    params = params if params is not None else case.params

    messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': case.user_prompt},
    ]
    run = CandidateRun(final_content=None)

    try:
        for step in range(MAX_STEPS):
            run.steps = step + 1
            out = await complete(
                messages=messages,
                tools=DATA_ANALYSIS_TOOL_SCHEMAS,
                params=params,
                model=model,
            )
            tool_calls = out.get('tool_calls') or []
            if not tool_calls:
                run.final_content = out.get('content')
                break
            # Echo the assistant tool-call message, then append each tool result.
            messages.append({'role': 'assistant', 'content': out.get('content'), 'tool_calls': [
                {'id': tc.get('id') or f'call_{step}_{i}', 'type': 'function',
                 'function': {'name': tc['name'], 'arguments': _json(tc.get('arguments', {}))}}
                for i, tc in enumerate(tool_calls)
            ]})
            for i, tc in enumerate(tool_calls):
                rec = _execute_call(tools, tc['name'], tc.get('arguments', {}), user)
                run.executed_calls.append(rec)
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.get('id') or f'call_{step}_{i}',
                    'content': _json(rec.get('result') if rec.get('success') else {'error': rec.get('error')}),
                })
        else:
            run.error = f'max steps ({MAX_STEPS}) reached without a final answer'
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the eval batch
        run.error = f'{type(exc).__name__}: {exc}'
    return run


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return '{}'
