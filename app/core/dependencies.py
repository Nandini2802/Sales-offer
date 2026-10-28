from collections.abc import AsyncGenerator

from fastapi import Request
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.persistence.database import get_db_session
from app.services.session_service import SessionService
from app.services.walkthrough_access_service import WalkthroughEngine


async def get_db(
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    engine = request.app.state.clients.postgres

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

def get_session_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionService:
    return SessionService(db)

def get_walkthrough_engine(
    request: Request,
) -> WalkthroughEngine:
    return request.app.state.walkthrough_engine