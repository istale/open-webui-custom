from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from open_webui.utils.auth import get_verified_user
from open_webui.utils.data_analysis.chart_store import get_chart_store
from open_webui.utils.data_analysis.event_logger import log_event
from open_webui.utils.data_analysis import get_repository
from open_webui.utils.data_analysis.service_auth import verify_pi_service_token
from open_webui.utils.data_analysis.tool_http_dispatch import (
    BUILTIN_TOOL_ID,
    ToolArgumentError,
    ToolNotFound,
    dispatch_tool_call,
)

log = logging.getLogger(__name__)

router = APIRouter()

FRONTEND_ALLOWED_EVENT_TYPES = {
    'workspace.opened',
    'dataset.selected',
    'prompt.submitted',
    'chart.rendered',
    'chart.viewed',
    'stream.timeout',
    'stream.aborted',
    'followup.clicked',
}


class FrontendEventPayload(BaseModel):
    event_type: str
    chat_id: str | None = None
    message_id: str | None = None
    payload: dict = Field(default_factory=dict)
    dataset_id: str | None = None
    chart_type: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None


def _dataset_to_response(dataset) -> dict:
    return {
        'id': dataset.id,
        'name': dataset.name,
        'description': dataset.description,
        'row_count': dataset.row_count,
        'column_count': dataset.column_count,
        'updated_at': dataset.updated_at.isoformat(),
        'tags': dataset.tags,
    }


@router.get('/datasets')
async def list_datasets(tags: str = '', user=Depends(get_verified_user)):
    tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()] or None
    items = get_repository().list_datasets(user_id=user.id, tags=tag_list)
    return {'schema_version': 1, 'items': [_dataset_to_response(item) for item in items]}


@router.get('/charts/{chart_id}.png')
async def get_chart_png(
    chart_id: str,
    thumb: bool = Query(default=False),
    user=Depends(get_verified_user),
):
    """Serve a rendered chart PNG through Open WebUI's native auth dependency."""
    record = get_chart_store().get(chart_id)
    if record is None:
        raise HTTPException(status_code=404, detail='Chart not found')

    from open_webui.models.chats import Chats

    if record.chat_id:
        chat = await Chats.get_chat_by_id_and_user_id(record.chat_id, user.id)
        if chat is None:
            raise HTTPException(status_code=403, detail='Chart access denied')
    elif record.user_id != user.id:
        raise HTTPException(status_code=403, detail='Chart access denied')

    path = record.thumb_path if thumb else record.path
    if not path.exists():
        raise HTTPException(status_code=404, detail='Chart image file not found')

    return FileResponse(path, media_type='image/png')


@router.post('/events')
async def log_frontend_event(payload: FrontendEventPayload, user=Depends(get_verified_user)):
    """Accept whitelisted frontend analytics events without exposing backend tool events."""
    if payload.event_type not in FRONTEND_ALLOWED_EVENT_TYPES:
        raise HTTPException(status_code=400, detail='event_type not allowed from frontend')

    await log_event(
        event_type=payload.event_type,
        user_id=user.id,
        chat_id=payload.chat_id,
        message_id=payload.message_id,
        payload=payload.payload,
        dataset_id=payload.dataset_id,
        chart_type=payload.chart_type,
        duration_ms=payload.duration_ms,
        success=payload.error_code is None,
        error_code=payload.error_code,
    )
    return {'ok': True}


# ---------------------------------------------------------------------------
# Pi service-to-service tool surface
#
# These endpoints expose the same ``Tools`` class methods that Open WebUI
# native middleware dispatches in-process. They are intended for a Pi agent
# runtime acting on behalf of an end-user identified by ``X-User-Id``, and
# authorise only callers presenting ``X-Pi-Service-Token`` matching
# ``AOH_PI_SHARED_SECRET``. See docs/spec/tools-schema.md.
# ---------------------------------------------------------------------------


class _ToolCallBody(BaseModel):
    args: dict = Field(default_factory=dict)


@router.get('/tool-specs')
async def list_tool_specs(request: Request, ctx: dict = Depends(verify_pi_service_token)):
    """Return the OpenAI-style function specs for the data-analysis tools.

    The set is exactly what native middleware would surface to the model.
    Callers must reuse this spec verbatim when registering Pi-side tool
    handlers so the model sees the same schema regardless of transport.
    """
    instance = (getattr(request.app.state, 'TOOLS', {}) or {}).get(BUILTIN_TOOL_ID)
    if instance is None:
        raise HTTPException(status_code=503, detail=f'{BUILTIN_TOOL_ID} not registered on this app')
    from open_webui.utils.data_analysis.versions import TOOL_SPEC_VERSION
    from open_webui.utils.tools import get_tool_specs

    return {
        'schema_version': 1,
        'tool_spec_version': TOOL_SPEC_VERSION,
        'tools': get_tool_specs(instance),
    }


@router.post('/tools/{name}')
async def execute_tool(
    name: str,
    body: _ToolCallBody,
    request: Request,
    x_chat_id: Annotated[str | None, Header(alias='X-Chat-Id')] = None,
    x_message_id: Annotated[str | None, Header(alias='X-Message-Id')] = None,
    x_aoh_trace_id: Annotated[str | None, Header(alias='X-Aoh-Trace-Id')] = None,
    ctx: dict = Depends(verify_pi_service_token),
):
    """Execute one data-analysis tool on behalf of ``X-User-Id``.

    Auth/argument failures return 4xx with FastAPI's standard ``{detail: ...}``
    body. Tool-runtime exceptions return 200 with ``{ok: false, error_code,
    error_message}`` so the Pi agent loop can surface the failure to the
    model and continue without losing the turn.
    """
    try:
        result = dispatch_tool_call(
            app=request.app,
            tool_name=name,
            args=body.args,
            user_id=ctx['user_id'],
            chat_id=x_chat_id,
            message_id=x_message_id,
            aoh_trace_id=x_aoh_trace_id,
        )
    except ToolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolArgumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception('data-analysis tool dispatch failed: tool=%s user=%s', name, ctx['user_id'])
        return {
            'ok': False,
            'error_code': type(exc).__name__,
            'error_message': str(exc),
        }
    return {'ok': True, 'result': result}
