
"""
Async PostgreSQL session management.

Responsibilities:
    - Create SQLAlchemy AsyncSession instances
    - Manage database session lifecycle
    - Roll back failed transactions

PostgreSQL engine creation and cleanup are handled
by app/core/clients.py.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)


async def get_db_session(
    engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a database session using the existing engine.

    One session is created per invocation.
    The session is automatically closed afterward.
    """

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        try:
            yield session

        except Exception:
            await session.rollback()
            raise
