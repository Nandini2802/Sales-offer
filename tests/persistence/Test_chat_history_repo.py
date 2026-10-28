
"""
Integration tests for ChatHistoryRepository.

Uses the existing Azure PostgreSQL engine from clients.py.

Each test runs inside an outer transaction that is rolled back afterward. The SQLAlchemy session uses a savepoint so session.commit() or session.rollback() cannot commit the outer test transaction.
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
from app.persistence.repositories.chat_history_repo import (
    ChatHistoryRepository,
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
    Provide an isolated database session.

    Uses the existing PostgreSQL URL loaded via Key Vault.
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
    Create a chatbot session for message testing.
    """

    session_repo = SessionRepository(db)

    session = await session_repo.create_session(
        **TEST_SESSION_DATA
    )

    return session


@pytest.mark.asyncio
async def test_add_user_message(db, chat_session):
    repo = ChatHistoryRepository(db)

    message = await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="Tell me about Greenz by Danube",
    )

    assert message is not None
    assert isinstance(message.id, uuid.UUID)
    assert message.session_id == chat_session.id
    assert message.role == "user"
    assert message.content == "Tell me about Greenz by Danube"


@pytest.mark.asyncio
async def test_add_assistant_message(db, chat_session):
    repo = ChatHistoryRepository(db)

    message = await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="assistant",
        content="Greenz is a Danube Properties project.",
    )

    assert message is not None
    assert message.role == "assistant"


@pytest.mark.asyncio
async def test_add_message_other_user(db, chat_session):
    repo = ChatHistoryRepository(db)

    message = await repo.add_message(
        session_id=chat_session.id,
        user_id=OTHER_USER_ID,
        role="user",
        content="Unauthorized message",
    )

    assert message is None


@pytest.mark.asyncio
async def test_invalid_message_role(db, chat_session):
    repo = ChatHistoryRepository(db)

    with pytest.raises(ValueError):
        await repo.add_message(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            role="system",
            content="System message",
        )


@pytest.mark.asyncio
async def test_empty_message_content(db, chat_session):
    repo = ChatHistoryRepository(db)

    with pytest.raises(ValueError):
        await repo.add_message(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            role="user",
            content="   ",
        )


@pytest.mark.asyncio
async def test_get_message_owner(db, chat_session):
    repo = ChatHistoryRepository(db)

    created = await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="What units are available?",
    )

    result = await repo.get_message(
        message_id=created.id,
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
    )

    assert result is not None
    assert result.id == created.id


@pytest.mark.asyncio
async def test_get_message_other_user(db, chat_session):
    repo = ChatHistoryRepository(db)

    created = await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="Show me available units",
    )

    result = await repo.get_message(
        message_id=created.id,
        session_id=chat_session.id,
        user_id=OTHER_USER_ID,
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_nonexistent_message(db, chat_session):
    repo = ChatHistoryRepository(db)

    result = await repo.get_message(
        message_id=uuid.uuid4(),
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_messages(db, chat_session):
    repo = ChatHistoryRepository(db)

    await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="First question",
    )

    await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="assistant",
        content="First answer",
    )

    messages = await repo.list_messages(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
    )

    assert len(messages) == 2
    assert messages[0].content == "First question"
    assert messages[1].content == "First answer"


@pytest.mark.asyncio
async def test_list_messages_other_user(db, chat_session):
    repo = ChatHistoryRepository(db)

    await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="Private conversation",
    )

    messages = await repo.list_messages(
        session_id=chat_session.id,
        user_id=OTHER_USER_ID,
    )

    assert messages == []


@pytest.mark.asyncio
async def test_recent_messages(db, chat_session):
    repo = ChatHistoryRepository(db)

    for index in range(5):
        await repo.add_message(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            role="user",
            content=f"Message {index}",
        )

    messages = await repo.get_recent_messages(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        limit=3,
    )

    assert len(messages) == 3
    assert [message.content for message in messages] == [
        "Message 2",
        "Message 3",
        "Message 4",
    ]


@pytest.mark.asyncio
async def test_count_messages(db, chat_session):
    repo = ChatHistoryRepository(db)

    for index in range(3):
        await repo.add_message(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            role="user",
            content=f"Question {index}",
        )

    count = await repo.count_messages(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
    )

    assert count == 3


@pytest.mark.asyncio
async def test_count_messages_other_user(db, chat_session):
    repo = ChatHistoryRepository(db)

    await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="Private message",
    )

    count = await repo.count_messages(
        session_id=chat_session.id,
        user_id=OTHER_USER_ID,
    )

    assert count == 0


@pytest.mark.asyncio
async def test_invalid_pagination(db, chat_session):
    repo = ChatHistoryRepository(db)

    with pytest.raises(ValueError):
        await repo.list_messages(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            limit=0,
        )

    with pytest.raises(ValueError):
        await repo.list_messages(
            session_id=chat_session.id,
            user_id=TEST_USER_ID,
            offset=-1,
        )


@pytest.mark.asyncio
async def test_session_timestamp_updated(db, chat_session):
    repo = ChatHistoryRepository(db)

    original_updated_at = chat_session.updated_at

    await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="New conversation activity",
    )

    await db.refresh(chat_session)

    assert chat_session.updated_at >= original_updated_at


@pytest.mark.asyncio
async def test_message_transaction_rollback(db, chat_session):
    repo = ChatHistoryRepository(db)

    message = await repo.add_message(
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
        role="user",
        content="Message to roll back",
    )

    message_id = message.id

    await db.rollback()

    result = await repo.get_message(
        message_id=message_id,
        session_id=chat_session.id,
        user_id=TEST_USER_ID,
    )

    assert result is None
