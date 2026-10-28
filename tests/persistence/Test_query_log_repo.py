
"""
Integration tests for QueryLogRepository.

Uses the existing Azure PostgreSQL connection
through create_service_clients().

All writes are enclosed in a test transaction
and rolled back after each test.
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

from app.persistence.repositories.query_log_repo import (
    QueryLogRepository,
)


TEST_SESSION_DATA = {
    "user_id": "005J9000000HpVQIA0",
    "user_role": "broker",
    "source": "danube_host",
    "app_source": "web_app",
    "title": "",
}

TEST_USER_ID = TEST_SESSION_DATA["user_id"]
OTHER_USER_ID = "unauthorized-test-user"


@pytest_asyncio.fixture
async def db():
    """
    Reuse the existing PostgreSQL engine configuration.

    Keep all test changes inside a transaction
    that is rolled back during cleanup.
    """

    clients = await create_service_clients()

    try:
        async with clients.postgres.connect() as connection:
            transaction = await connection.begin()

            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    autoflush=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            finally:
                if transaction.is_active:
                    await transaction.rollback()

    finally:
        await close_service_clients(clients)


@pytest_asyncio.fixture
async def chat_session(db):
    """
    Create a temporary chatbot session.
    """

    session_repo = SessionRepository(db)

    return await session_repo.create_session(
        **TEST_SESSION_DATA
    )


@pytest.mark.asyncio
async def test_create_query_log(db, chat_session):
    repo = QueryLogRepository(db)

    log = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Tell me about Greenz by Danube",
        intent="marketing",
        status="success",
        latency_ms=1250,
    )

    assert log is not None
    assert isinstance(log.id, uuid.UUID)
    assert log.session_id == chat_session.id
    assert log.user_id == TEST_USER_ID
    assert log.query_text == (
        "Tell me about Greenz by Danube"
    )
    assert log.intent == "marketing"
    assert log.status == "success"
    assert log.latency_ms == 1250


@pytest.mark.asyncio
async def test_create_failed_query_log(db, chat_session):
    repo = QueryLogRepository(db)

    log = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Show available units",
        intent="inventory",
        status="failed",
        latency_ms=500,
    )

    assert log is not None
    assert log.status == "failed"
    assert log.intent == "inventory"


@pytest.mark.asyncio
async def test_default_query_log_values(db, chat_session):
    repo = QueryLogRepository(db)

    log = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Hello",
    )

    assert log is not None
    assert log.status == "pending"
    assert log.intent is None
    assert log.latency_ms is None


@pytest.mark.asyncio
async def test_create_log_other_user(db, chat_session):
    repo = QueryLogRepository(db)

    log = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=OTHER_USER_ID,
        query_text="Unauthorized query",
    )

    assert log is None


@pytest.mark.asyncio
async def test_create_log_invalid_session(db):
    repo = QueryLogRepository(db)

    log = await repo.create_query_log(
        session_id=uuid.uuid4(),
        user_id=TEST_USER_ID,
        query_text="Invalid session query",
    )

    assert log is None


@pytest.mark.asyncio
async def test_get_query_log_owner(db, chat_session):
    repo = QueryLogRepository(db)

    created = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="What is the payment plan?",
        intent="marketing",
        status="success",
    )

    result = await repo.get_query_log(
        log_id=created.id,
        user_id=TEST_USER_ID,
    )

    assert result is not None
    assert result.id == created.id


@pytest.mark.asyncio
async def test_get_query_log_other_user(db, chat_session):
    repo = QueryLogRepository(db)

    created = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Private query",
    )

    result = await repo.get_query_log(
        log_id=created.id,
        user_id=OTHER_USER_ID,
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_nonexistent_log(db):
    repo = QueryLogRepository(db)

    result = await repo.get_query_log(
        log_id=uuid.uuid4(),
        user_id=TEST_USER_ID,
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_query_logs(db, chat_session):
    repo = QueryLogRepository(db)

    created_ids = set()

    for index in range(3):
        log = await repo.create_query_log(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            query_text=f"Query {index}",
            status="success",
        )

        created_ids.add(log.id)

    logs = await repo.list_query_logs(
        user_id=TEST_USER_ID,
        session_id=chat_session.id,
    )

    assert len(logs) == 3
    assert {log.id for log in logs} == created_ids


@pytest.mark.asyncio
async def test_list_query_logs_other_user(
    db,
    chat_session,
):
    repo = QueryLogRepository(db)

    await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Private query",
    )

    logs = await repo.list_query_logs(
        user_id=OTHER_USER_ID,
        session_id=chat_session.id,
    )

    assert logs == []


@pytest.mark.asyncio
async def test_list_query_logs_session_filter(
    db,
    chat_session,
):
    repo = QueryLogRepository(db)
    session_repo = SessionRepository(db)

    second_session = await session_repo.create_session(
        **TEST_SESSION_DATA
    )

    first_log = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="First session query",
    )

    await repo.create_query_log(
        session_id=second_session.id,
        user_id=TEST_USER_ID,
        query_text="Second session query",
    )

    logs = await repo.list_query_logs(
        user_id=TEST_USER_ID,
        session_id=chat_session.id,
    )

    assert len(logs) == 1
    assert logs[0].id == first_log.id


@pytest.mark.asyncio
async def test_count_query_logs(db, chat_session):
    repo = QueryLogRepository(db)

    for index in range(3):
        await repo.create_query_log(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            query_text=f"Query {index}",
        )

    count = await repo.count_query_logs(
        user_id=TEST_USER_ID,
        session_id=chat_session.id,
    )

    assert count == 3


@pytest.mark.asyncio
async def test_count_query_logs_other_user(
    db,
    chat_session,
):
    repo = QueryLogRepository(db)

    await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Private query",
    )

    count = await repo.count_query_logs(
        user_id=OTHER_USER_ID,
        session_id=chat_session.id,
    )

    assert count == 0


@pytest.mark.asyncio
async def test_empty_query_text(db, chat_session):
    repo = QueryLogRepository(db)

    with pytest.raises(ValueError):
        await repo.create_query_log(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            query_text="   ",
        )


@pytest.mark.asyncio
async def test_negative_latency(db, chat_session):
    repo = QueryLogRepository(db)

    with pytest.raises(ValueError):
        await repo.create_query_log(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            query_text="Test query",
            latency_ms=-100,
        )


@pytest.mark.asyncio
async def test_invalid_status(db, chat_session):
    repo = QueryLogRepository(db)

    with pytest.raises(ValueError):
        await repo.create_query_log(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            query_text="Test query",
            status="",
        )


@pytest.mark.asyncio
async def test_invalid_pagination(db):
    repo = QueryLogRepository(db)

    with pytest.raises(ValueError):
        await repo.list_query_logs(
            user_id=TEST_USER_ID,
            limit=0,
        )

    with pytest.raises(ValueError):
        await repo.list_query_logs(
            user_id=TEST_USER_ID,
            limit=101,
        )

    with pytest.raises(ValueError):
        await repo.list_query_logs(
            user_id=TEST_USER_ID,
            offset=-1,
        )


@pytest.mark.asyncio
async def test_query_log_rollback(db, chat_session):
    repo = QueryLogRepository(db)

    # Commit the test session's savepoint.
    # The outer test transaction remains uncommitted.
    await db.commit()

    log = await repo.create_query_log(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        query_text="Rollback test query",
    )

    log_id = log.id

    await db.rollback()

    result = await repo.get_query_log(
        log_id=log_id,
        user_id=TEST_USER_ID,
    )

    assert result is None
