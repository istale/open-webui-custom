"""Single execution path for service-driven data-analysis tool calls.

Both the HTTP service router and any future in-process re-execution path
(for example ``replay_cli regression``) must construct the same
``__user__`` / ``__metadata__`` injections and invoke the same live
``Tools`` instance kept in ``app.state.TOOLS``. Centralising that here
guarantees byte-equivalent behaviour so trajectory replay stays trustable.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

log = logging.getLogger(__name__)

INTERNAL_PARAM_PREFIX = '__'
BUILTIN_TOOL_ID = 'builtin:data-analysis'


class ToolNotFound(LookupError):
    """Raised when the requested tool name is not registered on this app."""


class ToolArgumentError(ValueError):
    """Raised when the supplied args contain unknown or reserved keys."""


def _get_tool_instance(app) -> Any:
    tools_cache = getattr(app.state, 'TOOLS', {}) or {}
    instance = tools_cache.get(BUILTIN_TOOL_ID)
    if instance is None:
        raise ToolNotFound(f'{BUILTIN_TOOL_ID} is not registered on this app')
    return instance


def _resolve_method(instance: Any, name: str):
    if not name or name.startswith('_'):
        raise ToolNotFound(f'unknown tool: {name!r}')
    method = getattr(instance, name, None)
    if not callable(method):
        raise ToolNotFound(f'unknown tool: {name!r}')
    return method


def _filter_args(method, args: dict[str, Any] | None) -> dict[str, Any]:
    """Drop unknown args, reject reserved __ params, keep arg type guarantees to the tool itself."""
    sig = inspect.signature(method)
    accepted = {p for p in sig.parameters if not p.startswith(INTERNAL_PARAM_PREFIX)}
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if k.startswith(INTERNAL_PARAM_PREFIX):
            raise ToolArgumentError(f'argument {k!r} is reserved and cannot be passed by service caller')
        if k not in accepted:
            raise ToolArgumentError(f'unknown argument {k!r} for tool {method.__name__!r}')
        out[k] = v
    return out


def dispatch_tool_call(
    *,
    app,
    tool_name: str,
    args: dict[str, Any] | None,
    user_id: str,
    chat_id: str | None = None,
    message_id: str | None = None,
    aoh_trace_id: str | None = None,
) -> dict[str, Any]:
    """Execute one tool synchronously and return its dict result.

    Mirrors the injections that Open WebUI native chat middleware would
    normally provide so the tool implementation sees the same context
    regardless of caller (browser session or Pi service).
    """
    instance = _get_tool_instance(app)
    method = _resolve_method(instance, tool_name)
    filtered = _filter_args(method, args)

    user_ctx = {'id': user_id}
    metadata: dict[str, Any] = {}
    if chat_id:
        metadata['chat_id'] = chat_id
    if message_id:
        metadata['message_id'] = message_id
    if aoh_trace_id:
        metadata['aoh_trace_id'] = aoh_trace_id

    sig = inspect.signature(method)
    kwargs = dict(filtered)
    if '__user__' in sig.parameters:
        kwargs['__user__'] = user_ctx
    if '__metadata__' in sig.parameters:
        kwargs['__metadata__'] = metadata

    result = method(**kwargs)
    if not isinstance(result, dict):
        log.warning('tool %s returned non-dict result of type %s', tool_name, type(result).__name__)
    return result
