from __future__ import annotations

from urllib.parse import quote_plus

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine.url import make_url

from app.db.models import Base


class Database:
    def __init__(self, database_url: str) -> None:
        self._database_url_str = database_url
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    async def init(self) -> None:
        await self._ensure_database_exists()
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _ensure_database_exists(self) -> None:
        """
        Best-effort database auto-create for PostgreSQL.

        Requires that the credentials in DATABASE_URL have permission to CREATE DATABASE.
        If permissions are missing, we just proceed and let the later connection fail clearly.
        """
        url = make_url(self._database_url_str)
        target_db = url.database
        if not target_db:
            return

        # Always check/create from the maintenance DB so we don't depend on being able
        # to connect to the target DB first (which can fail with non-obvious errors).
        maintenance_dsn = _asyncpg_dsn(url, "postgres")
        try:
            conn = await asyncpg.connect(maintenance_dsn)
        except Exception:
            return

        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname=$1",
                target_db,
            )
            if exists:
                return

            await conn.execute(f'CREATE DATABASE "{target_db}"')
        except Exception:
            # Permission issues (no CREATE DATABASE) are handled by letting the
            # later normal connection/table creation fail clearly.
            return
        finally:
            await conn.close()


def _asyncpg_dsn(url, database: str) -> str:
    """
    Convert a SQLAlchemy URL like `postgresql+asyncpg://user:pass@host:5432/dbname`
    into an asyncpg DSN like `postgresql://user:pass@host:5432/dbname`.
    """
    username = url.username or ""
    password = url.password or ""
    host = url.host or "localhost"
    port = url.port or 5432

    # Password/user may contain special chars; quote them for DSN safety.
    username_q = quote_plus(str(username))
    password_q = quote_plus(str(password))

    return f"postgresql://{username_q}:{password_q}@{host}:{port}/{database}"

