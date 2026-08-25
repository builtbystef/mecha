from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from mecha_api import migrate
from mecha_api.store import ConversationStore
from mecha_api.tables import Base, Run
from pydantic_ai import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from sqlalchemy import Connection, func, select
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.anyio


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[ConversationStore]:
    store = ConversationStore(f"sqlite+aiosqlite:///{tmp_path / 'store.db'}")
    await migrate.upgrade_to_head(store.engine)
    yield store
    await store.close()


def _turn(prompt: str, reply: str) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ModelResponse(parts=[TextPart(content=reply)]),
    ]


async def test_created_at_comes_back_utc_aware(store: ConversationStore) -> None:
    conversation = await store.create_conversation("Hi")

    reloaded = await store.get_conversation(conversation.id)

    assert reloaded is not None
    assert reloaded.created_at.utcoffset() is not None
    assert reloaded.created_at == conversation.created_at


async def test_deleting_a_conversation_deletes_its_runs(
    store: ConversationStore,
) -> None:
    conversation = await store.create_conversation("Hi")
    await store.append_run(conversation.id, _turn("one", "two"))

    assert await store.delete_conversation(conversation.id) is True

    # Cascades only because the connect hook turns SQLite foreign keys on.
    async with store.engine.connect() as connection:
        remaining = await connection.scalar(select(func.count()).select_from(Run))
    assert remaining == 0


async def test_history_round_trips(store: ConversationStore) -> None:
    conversation = await store.create_conversation("Hi")
    await store.append_run(conversation.id, _turn("one", "1"))
    await store.append_run(conversation.id, _turn("two", "2"))

    history = await store.load_history(conversation.id)

    assert [type(message).__name__ for message in history] == [
        "ModelRequest",
        "ModelResponse",
        "ModelRequest",
        "ModelResponse",
    ]


async def test_deleting_an_unknown_conversation_reports_false(
    store: ConversationStore,
) -> None:
    assert await store.delete_conversation("nope") is False


async def test_migrations_leave_no_drift_from_tables(tmp_path: Path) -> None:
    """`alembic upgrade head` must produce exactly what `tables.py` declares.

    The database equivalent of CI's `contract` job: editing a table without
    generating the migration fails here rather than in production.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'drift.db'}")
    await migrate.upgrade_to_head(engine)

    def _diff(connection: Connection) -> list[Any]:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)

    async with engine.connect() as connection:
        differences = await connection.run_sync(_diff)
    await engine.dispose()

    assert differences == []
