from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from open_webui.utils.auth import get_verified_user
from open_webui.utils.data_analysis.chart_store import get_chart_store
from open_webui.utils.data_analysis.event_logger import log_event
from open_webui.utils.data_analysis import get_repository

router = APIRouter()

FRONTEND_ALLOWED_EVENT_TYPES = {
    'workspace.opened',
    'dataset.selected',
    'prompt.submitted',
    'chart.rendered',
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
