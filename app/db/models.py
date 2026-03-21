from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, DateTime, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Subscriber(Base):
    __tablename__ = "subscribers"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    linguicards_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reminder_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reminder_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HealthState(Base):
    __tablename__ = "health_state"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    status_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

