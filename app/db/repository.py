from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import HealthState, Subscriber


class Repository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def add_subscriber(self, chat_id: int) -> None:
        async with self._sessionmaker() as session:
            session.add(Subscriber(chat_id=chat_id))
            try:
                await session.commit()
            except Exception:
                await session.rollback()

    async def list_subscribers(self) -> list[int]:
        async with self._sessionmaker() as session:
            res = await session.execute(select(Subscriber.chat_id))
            return [row[0] for row in res.all()]

    async def get_health_state(self) -> dict[str, Any] | None:
        async with self._sessionmaker() as session:
            res = await session.execute(select(HealthState).where(HealthState.id == 1))
            row = res.scalar_one_or_none()
            return None if row is None else row.status_json

    async def set_health_state(self, status: dict[str, Any]) -> None:
        async with self._sessionmaker() as session:
            res = await session.execute(select(HealthState).where(HealthState.id == 1))
            row = res.scalar_one_or_none()
            if row is None:
                session.add(HealthState(id=1, status_json=status))
            else:
                row.status_json = status
            await session.commit()

