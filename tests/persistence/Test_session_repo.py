
"""
Integration tests for SessionRepository.

Uses the existing PostgreSQL engine from clients.py.

Test data is rolled back after each test.
No permanent test records are created.
"""

import uuid

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.persistence.repositories.session_repo import (
    SessionRepository,
)


TEST_SESSION_DATA = {
    "user_id": "005J9000000HpVQIA0",
    "user_role": "broker",
    "source": "danube_host",
    "app_source": "web_app",
    "title": "",
}


@pytest_asyncio.fixture
async def db():
    clients = await create_service_clients()

    try:
        async with clients.postgres.connect() as connection:
            transaction = await connection.begin()

            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                autoflush=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                try:
                    yield session
                finally:
                    await session.close()
                    if transaction.is_active:
                        await transaction.rollback()
    finally:
        await close_service_clients(clients)


@pytest.mark.asyncio
async def test_create_session(db):
    repo = SessionRepository(db)

    session = await repo.create_session(
        **TEST_SESSION_DATA
    )

    assert isinstance(session.id, uuid.UUID)
    assert session.user_id == TEST_SESSION_DATA["user_id"]
    assert session.user_role == "broker"
    assert session.source == "danube_host"
    assert session.app_source == "web_app"
    assert session.title == ""


@pytest.mark.asyncio
async def test_get_session_owner(db):
    repo = SessionRepository(db)

    created = await repo.create_session(
        **TEST_SESSION_DATA
    )

    result = await repo.get_session(
        session_id=created.id,
        user_id=TEST_SESSION_DATA["user_id"],
    )

    assert result is not None
    assert result.id == created.id


@pytest.mark.asyncio
async def test_get_session_other_user(db):
    repo = SessionRepository(db)

    created = await repo.create_session(
        **TEST_SESSION_DATA
    )

    result = await repo.get_session(
        session_id=created.id,
        user_id="another-test-user",
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_sessions(db):
    repo = SessionRepository(db)

    created = await repo.create_session(
        **TEST_SESSION_DATA
    )

    sessions = await repo.list_sessions(
        user_id=TEST_SESSION_DATA["user_id"],
    )

    assert any(
        session.id == created.id
        for session in sessions
    )

    assert all(
        session.user_id == TEST_SESSION_DATA["user_id"]
        for session in sessions
    )


@pytest.mark.asyncio
async def test_update_session(db):
    repo = SessionRepository(db)

    created = await repo.create_session(
        **TEST_SESSION_DATA
    )

    updated = await repo.update_session(
        session_id=created.id,
        user_id=TEST_SESSION_DATA["user_id"],
        title="Updated Test Title",
    )

    assert updated is not None
    assert updated.title == "Updated Test Title"


@pytest.mark.asyncio
async def test_delete_session(db):
    repo = SessionRepository(db)

    created = await repo.create_session(
        **TEST_SESSION_DATA
    )

    deleted = await repo.delete_session(
        session_id=created.id,
        user_id=TEST_SESSION_DATA["user_id"],
    )

    assert deleted is True

    result = await repo.get_session(
        session_id=created.id,
        user_id=TEST_SESSION_DATA["user_id"],
    )

    assert result is None


@pytest.mark.asyncio
async def test_rollback(db):
    repo = SessionRepository(db)

    created = await repo.create_session(
        **TEST_SESSION_DATA
    )

    created_id = created.id

    await db.rollback()

    result = await repo.get_session(
        session_id=created_id,
        user_id=TEST_SESSION_DATA["user_id"],
    )

    assert result is None


@pytest.mark.asyncio
async def test_invalid_pagination(db):
    repo = SessionRepository(db)

    with pytest.raises(ValueError):
        await repo.list_sessions(
            user_id=TEST_SESSION_DATA["user_id"],
            limit=0,
        )

    with pytest.raises(ValueError):
        await repo.list_sessions(
            user_id=TEST_SESSION_DATA["user_id"],
            offset=-1,
        )
