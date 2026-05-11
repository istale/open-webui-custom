from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

EVENT_QUEUE_MAXSIZE = 10_000
BATCH_SIZE = 100
FLUSH_INTERVAL_S = 5.0

_event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=EVENT_QUEUE_MAXSIZE)
_worker_task: asyncio.Task | None = None
_stopping = False


async def log_event(
    *,
    event_type: str,
    user_id: str,
    chat_id: str | None = None,
    message_id: str | None = None,
    payload: dict[str, Any],
    schema_version: int = 1,
    dataset_id: str | None = None,
    chart_type: str | None = None,
    tool_name: str | None = None,
    duration_ms: int | None = None,
    success: bool = True,
    error_code: str | None = None,
    user_org_id: str | None = None,
) -> None:
    """Queue an analytics event without performing DB I/O on the caller path."""
    event = {
        'id': uuid4().hex,
        'ts': int(time.time() * 1000),
        'user_id': user_id,
        'user_org_id': user_org_id,
        'chat_id': chat_id,
        'message_id': message_id,
        'workspace': 'data-analysis',
        'event_type': event_type,
        'schema_version': schema_version,
        'payload': payload,
        'dataset_id': dataset_id,
        'chart_type': chart_type,
        'tool_name': tool_name,
        'duration_ms': duration_ms,
        'success': success,
        'error_code': error_code,
        'is_deleted': False,
        'deleted_at': None,
    }
    try:
        _event_queue.put_nowait(event)
    except asyncio.QueueFull:
        log.warning('data-analysis event queue full; dropped event_type=%s', event_type)


def schedule_log_event(**kwargs) -> None:
    """Fire-and-forget wrapper for sync tool functions.

    Tool execution must never fail or block because analytics is unavailable.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(log_event(**kwargs))
    except RuntimeError:
        log.warning('data-analysis event logger has no running loop; dropped event_type=%s', kwargs.get('event_type'))
    except Exception as exc:
        log.warning('data-analysis event scheduling failed: %s', exc)


def schedule_chat_lifecycle_events(
    *,
    user_id: str,
    metadata: dict[str, Any],
    output: list[dict[str, Any]],
    content: str,
    started_at: float,
) -> None:
    """Emit vertical chat lifecycle events from native completion output.

    Open WebUI owns the streaming state machine. The vertical only observes the
    finalized OR-style output items, so the core middleware hook stays tiny and
    cannot slow per-token streaming.
    """
    if not _is_data_analysis_context(metadata):
        return

    chat_id = metadata.get('chat_id')
    message_id = metadata.get('message_id')
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    reasoning_events = _reasoning_events_from_output(output, content)

    for event in reasoning_events:
        schedule_log_event(
            event_type='model.thinking_completed',
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            payload={
                'thinking_text': event['thinking_text'],
                'n_chars': len(event['thinking_text']),
            },
            duration_ms=event['duration_ms'],
        )

    schedule_log_event(
        event_type='message.assistant_completed',
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        payload={
            'message_id': message_id,
            'total_duration_ms': duration_ms,
            'tool_call_count': _count_output_items(output, 'function_call'),
            'n_chars': len(_visible_text_from_output(output, content)),
            'had_thinking': bool(reasoning_events),
        },
        duration_ms=duration_ms,
    )


def _is_data_analysis_context(metadata: dict[str, Any]) -> bool:
    if metadata.get('workspace_type') == 'data-analysis':
        return True
    tool_ids = metadata.get('tool_ids') or []
    return 'builtin:data-analysis' in tool_ids


def _reasoning_events_from_output(output: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    events = []
    for item in output:
        if item.get('type') != 'reasoning':
            continue
        text = _text_from_parts(item.get('content', [])) or _text_from_parts(item.get('summary', []))
        if not text:
            continue
        duration_ms = _duration_ms_from_item(item)
        events.append({'thinking_text': text, 'duration_ms': duration_ms})

    if events:
        return events

    tagged_text = _extract_tagged_thinking(content)
    if tagged_text:
        return [{'thinking_text': tagged_text, 'duration_ms': None}]

    return []


def _duration_ms_from_item(item: dict[str, Any]) -> int | None:
    duration = item.get('duration')
    if isinstance(duration, (int, float)):
        return int(duration * 1000)

    started_at = item.get('started_at')
    ended_at = item.get('ended_at')
    if isinstance(started_at, (int, float)) and isinstance(ended_at, (int, float)):
        return int((ended_at - started_at) * 1000)

    return None


def _count_output_items(output: list[dict[str, Any]], item_type: str) -> int:
    return sum(1 for item in output if item.get('type') == item_type)


def _visible_text_from_output(output: list[dict[str, Any]], fallback: str) -> str:
    text_parts = [
        _text_from_parts(item.get('content', []))
        for item in output
        if item.get('type') == 'message'
    ]
    text = ''.join(text_parts).strip()
    return text or fallback or ''


def _text_from_parts(parts: Any) -> str:
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ''

    text = []
    for part in parts:
        if isinstance(part, str):
            text.append(part)
        elif isinstance(part, dict):
            text.append(part.get('text') or part.get('summary') or '')
    return ''.join(text).strip()


def _extract_tagged_thinking(content: str) -> str:
    start = content.find('<think>')
    end = content.find('</think>')
    if start == -1 or end == -1 or end <= start:
        return ''
    return content[start + len('<think>') : end].strip()


def start_event_worker(app=None) -> None:
    global _worker_task, _stopping
    _stopping = False
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_flush_worker())
        if app is not None:
            app.state.DATA_ANALYSIS_EVENT_WORKER = _worker_task


async def stop_event_worker() -> None:
    global _stopping
    _stopping = True
    if _worker_task is not None and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    await _drain_queue()


async def _flush_worker() -> None:
    while not _stopping:
        batch = []
        try:
            event = await asyncio.wait_for(_event_queue.get(), timeout=FLUSH_INTERVAL_S)
            batch.append(event)
            while len(batch) < BATCH_SIZE:
                try:
                    batch.append(_event_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await _insert_batch(batch)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.warning('data-analysis event flush failed: %s; events_lost=%d', exc, len(batch))


async def _drain_queue() -> None:
    while not _event_queue.empty():
        batch = []
        while len(batch) < BATCH_SIZE:
            try:
                batch.append(_event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not batch:
            return
        try:
            await _insert_batch(batch)
        except Exception as exc:
            log.warning('data-analysis final event flush failed: %s; events_lost=%d', exc, len(batch))


async def _insert_batch(batch: list[dict]) -> None:
    if batch:
        from open_webui.models.data_analysis_events import DataAnalysisEvents

        await DataAnalysisEvents.bulk_insert(batch)


def reset_event_logger_for_tests() -> None:
    global _worker_task, _stopping
    _worker_task = None
    _stopping = False
    while not _event_queue.empty():
        try:
            _event_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
