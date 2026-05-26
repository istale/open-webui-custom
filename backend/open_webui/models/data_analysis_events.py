from __future__ import annotations

import time
import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, Column, Integer, JSON, Text, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.internal.db import Base, get_async_db_context

log = logging.getLogger(__name__)


class DataAnalysisEvent(Base):
    __tablename__ = 'data_analysis_events'

    id = Column(Text, primary_key=True)
    ts = Column(BigInteger, nullable=False)
    user_id = Column(Text, nullable=False)
    user_org_id = Column(Text, nullable=True)
    chat_id = Column(Text, nullable=True)
    message_id = Column(Text, nullable=True)
    workspace = Column(Text, nullable=False, default='data-analysis')
    event_type = Column(Text, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False)
    dataset_id = Column(Text, nullable=True)
    chart_type = Column(Text, nullable=True)
    tool_name = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_code = Column(Text, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(BigInteger, nullable=True)


class DataAnalysisEventModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ts: int
    user_id: str
    user_org_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    workspace: str = 'data-analysis'
    event_type: str
    schema_version: int = 1
    payload: dict = Field(default_factory=dict)
    dataset_id: Optional[str] = None
    chart_type: Optional[str] = None
    tool_name: Optional[str] = None
    duration_ms: Optional[int] = None
    success: bool = True
    error_code: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[int] = None


class DataAnalysisEventsTable:
    async def bulk_insert(self, events: list[dict], db: Optional[AsyncSession] = None) -> int:
        if not events:
            return 0

        rows = [DataAnalysisEventModel.model_validate(event).model_dump() for event in events]
        async with get_async_db_context(db) as db:
            await db.execute(insert(DataAnalysisEvent), rows)
            await db.commit()
        return len(rows)

    async def list_events_by_chat_id(
        self, chat_id: str, include_deleted: bool = False, db: Optional[AsyncSession] = None
    ) -> list[DataAnalysisEventModel]:
        """Return all events for one chat, ordered by ts then id (stable). Used by
        the trajectory builder / replay export."""
        async with get_async_db_context(db) as db:
            stmt = select(DataAnalysisEvent).where(DataAnalysisEvent.chat_id == chat_id)
            if not include_deleted:
                stmt = stmt.where(DataAnalysisEvent.is_deleted.is_(False))
            stmt = stmt.order_by(DataAnalysisEvent.ts.asc(), DataAnalysisEvent.id.asc())
            result = await db.execute(stmt)
            return [DataAnalysisEventModel.model_validate(row) for row in result.scalars().all()]

    async def list_chat_ids(
        self, include_deleted: bool = False, since_ts: Optional[int] = None, db: Optional[AsyncSession] = None
    ) -> list[str]:
        """Distinct chat_ids that have events (for batch export). Newest first."""
        async with get_async_db_context(db) as db:
            stmt = select(DataAnalysisEvent.chat_id).where(DataAnalysisEvent.chat_id.isnot(None))
            if not include_deleted:
                stmt = stmt.where(DataAnalysisEvent.is_deleted.is_(False))
            if since_ts is not None:
                stmt = stmt.where(DataAnalysisEvent.ts >= since_ts)
            result = await db.execute(stmt)
            seen: dict[str, None] = {}
            for cid in result.scalars().all():
                if cid is not None:
                    seen[cid] = None
            return list(seen.keys())

    async def mark_deleted(self, chat_id: str, db: Optional[AsyncSession] = None) -> int:
        deleted_at = int(time.time() * 1000)
        async with get_async_db_context(db) as db:
            result = await db.execute(
                update(DataAnalysisEvent)
                .where(DataAnalysisEvent.chat_id == chat_id)
                .values(is_deleted=True, deleted_at=deleted_at)
            )
            await db.commit()
            return int(result.rowcount or 0)

    async def mark_deleted_by_user_id(self, user_id: str, db: Optional[AsyncSession] = None) -> int:
        deleted_at = int(time.time() * 1000)
        async with get_async_db_context(db) as db:
            result = await db.execute(
                update(DataAnalysisEvent)
                .where(DataAnalysisEvent.user_id == user_id, DataAnalysisEvent.chat_id.isnot(None))
                .values(is_deleted=True, deleted_at=deleted_at)
            )
            await db.commit()
            return int(result.rowcount or 0)

    async def mark_deleted_safely(self, chat_id: str, db: Optional[AsyncSession] = None) -> None:
        try:
            await self.mark_deleted(chat_id=chat_id, db=db)
        except Exception as exc:
            log.warning('failed to soft-delete data-analysis events for chat_id=%s: %s', chat_id, exc)

    async def mark_deleted_by_user_id_safely(self, user_id: str, db: Optional[AsyncSession] = None) -> None:
        try:
            await self.mark_deleted_by_user_id(user_id=user_id, db=db)
        except Exception as exc:
            log.warning('failed to soft-delete data-analysis events for user_id=%s: %s', user_id, exc)


DataAnalysisEvents = DataAnalysisEventsTable()
