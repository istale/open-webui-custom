from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from open_webui.models.chats import Chats
from open_webui.utils.auth import get_verified_user
from open_webui.utils.data_analysis.chart_store import get_chart_store

router = APIRouter()


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
