"""Provider client for LLM-in-the-loop eval (Phase 5).

This is the ONLY module in the data-analysis vertical that performs live LLM I/O.
Keeping the network seam isolated means trajectory/replay/analytics stay pure and
offline, and eval is the single place that needs a key + connectivity.

It speaks the OpenAI-compatible chat-completions protocol against the endpoint
configured in the environment (MiniMax by default):

    MINIMAX_BASE_URL   e.g. https://api.minimax.chat/v1
    MINIMAX_API_KEY
    MINIMAX_MODEL      default model id

`complete()` takes the running message list (so an agentic tool-call loop can feed
tool results back) and returns a normalized step:

    {'tool_calls': [{'id', 'name', 'arguments': dict}, ...], 'content': str | None}
"""

from __future__ import annotations

import json
import os
from typing import Any

# Compact, model-visible schema for the data-analysis tools. Mirrors the native
# Open WebUI function schema closely enough for the model to emit valid calls
# during eval. (We don't import the Tools class here to keep this seam dependency
# light; the executor in eval.py is the source of truth for actual execution.)
DATA_ANALYSIS_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'list_datasets',
            'description': 'List available datasets and their ids. Call this if you do not know the exact dataset_id.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'query_dataset',
            'description': 'Run SQL (table name `df`) against a dataset and cache the rows. Returns a query_id.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dataset_id': {'type': 'string', 'description': 'The dataset id (NOT a display name).'},
                    'query': {'type': 'string', 'description': "SQL over table `df`."},
                },
                'required': ['dataset_id', 'query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'render_chart',
            'description': 'Render a chart from a previous query_id. Returns a chart image url.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query_id': {'type': 'string'},
                    'chart_type': {'type': 'string'},
                    'x': {'type': 'string'},
                    'y': {'type': 'string'},
                    'title': {'type': 'string'},
                    'explanation_source': {'type': 'string'},
                    'explanation_method': {'type': 'string'},
                    'explanation_fields': {'type': 'string'},
                    'color': {'type': 'string'},
                    'facet': {'type': 'string'},
                },
                'required': ['query_id', 'chart_type', 'x', 'y'],
            },
        },
    },
]


class LLMClientError(RuntimeError):
    pass


def _config() -> tuple[str, str, str]:
    base = os.environ.get('MINIMAX_BASE_URL', '').rstrip('/')
    key = os.environ.get('MINIMAX_API_KEY', '')
    model = os.environ.get('MINIMAX_MODEL', '')
    if not base or not key:
        raise LLMClientError(
            'MINIMAX_BASE_URL and MINIMAX_API_KEY must be set to run LLM-in-the-loop eval.'
        )
    return base, key, model


def _normalize_choice(message: dict[str, Any]) -> dict[str, Any]:
    """Normalize an OpenAI-style assistant message into our step shape."""
    tool_calls = []
    for tc in message.get('tool_calls') or []:
        fn = tc.get('function') or {}
        raw_args = fn.get('arguments')
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        tool_calls.append({'id': tc.get('id') or '', 'name': fn.get('name') or '', 'arguments': args})
    return {'tool_calls': tool_calls, 'content': message.get('content')}


async def complete(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Issue one chat-completion step against the configured endpoint.

    Returns a normalized ``{'tool_calls': [...], 'content': str | None}`` step.
    Raises ``LLMClientError`` on transport/config failure (eval should surface it,
    not silently score a non-answer as a failure).
    """
    import aiohttp

    base, key, default_model = _config()
    tools = DATA_ANALYSIS_TOOL_SCHEMAS if tools is None else tools
    params = params or {}

    body: dict[str, Any] = {
        'model': model or default_model,
        'messages': messages,
        'tools': tools,
    }
    for k in ('temperature', 'top_p', 'max_tokens', 'seed'):
        if k in params and params[k] is not None:
            body[k] = params[k]

    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    url = f'{base}/chat/completions'

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise LLMClientError(f'completion HTTP {resp.status}: {text[:500]}')
                data = await resp.json()
    except aiohttp.ClientError as exc:
        raise LLMClientError(f'completion transport error: {exc}') from exc

    choices = data.get('choices') or []
    if not choices:
        raise LLMClientError('completion returned no choices')
    return _normalize_choice(choices[0].get('message') or {})
