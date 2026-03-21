from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import HealthState, Subscriber


def _is_daily_reminder_ready(row: Subscriber) -> bool:
    return bool(
        row.linguicards_username
        and row.reminder_time
        and row.reminder_timezone
    )


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

    async def get_subscriber(self, chat_id: int) -> Subscriber | None:
        async with self._sessionmaker() as session:
            res = await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))
            return res.scalar_one_or_none()

    async def set_linguicards_username(self, chat_id: int, username: str) -> None:
        async with self._sessionmaker() as session:
            res = await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))
            row = res.scalar_one_or_none()
            if row is None:
                session.add(Subscriber(chat_id=chat_id, linguicards_username=username))
            else:
                row.linguicards_username = username
            await session.commit()

    async def set_daily_reminder(self, chat_id: int, time_hhmm: str, timezone: str) -> None:
        async with self._sessionmaker() as session:
            res = await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))
            row = res.scalar_one_or_none()
            if row is None:
                session.add(
                    Subscriber(
                        chat_id=chat_id,
                        reminder_time=time_hhmm,
                        reminder_timezone=timezone,
                    )
                )
            else:
                row.reminder_time = time_hhmm
                row.reminder_timezone = timezone
            await session.commit()

    async def clear_daily_reminder(self, chat_id: int) -> None:
        async with self._sessionmaker() as session:
            res = await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))
            row = res.scalar_one_or_none()
            if row is None:
                return
            row.reminder_time = None
            row.reminder_timezone = None
            await session.commit()

    async def list_subscribers_for_daily_reminders(self) -> list[Subscriber]:
        async with self._sessionmaker() as session:
            res = await session.execute(select(Subscriber))
            rows = list(res.scalars().all())
        return [r for r in rows if _is_daily_reminder_ready(r)]

