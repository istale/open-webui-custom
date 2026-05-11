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
