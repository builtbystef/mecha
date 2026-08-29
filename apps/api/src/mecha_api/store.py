"""Conversation persistence, over SQLAlchemy's async ORM.

Each agent run appends one row with that run's new messages (serialized with
pydantic-ai's `ModelMessagesTypeAdapter`); a conversation's history is all
its runs in order, ready to pass back as `message_history=`.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from mecha_api import tables


# The API-facing shape of a conversation; the ORM row is
# `tables.Conversation`. A docstring here would land in the OpenAPI schema
# and from there in the generated client, so this stays a comment.
class Conversation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    """SQLite defaults a server process wants and doesn't get for free.

    Foreign keys are off per connection unless asked for, so the runs cascade
    would silently not fire; the rollback journal blocks readers for the
    length of a write; and the default busy timeout is zero, which turns any
    contention straight into "database is locked".
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


class ConversationStore:
    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(url)
        if self._engine.dialect.name == "sqlite":
            # Listens on the sync engine underneath: pragmas run on the raw
            # DBAPI connection, which asyncio drivers reach through it too.
            event.listen(self._engine.sync_engine, "connect", _sqlite_pragmas)
        self._session = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def create_conversation(self, title: str) -> Conversation:
        row = tables.Conversation(id=uuid.uuid4().hex, title=title)
        async with self._session.begin() as session:
            session.add(row)
        return Conversation.model_validate(row)

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        async with self._session() as session:
            row = await session.get(tables.Conversation, conversation_id)
            return None if row is None else Conversation.model_validate(row)

    async def list_conversations(self) -> list[Conversation]:
        async with self._session() as session:
            rows = await session.scalars(
                select(tables.Conversation).order_by(
                    tables.Conversation.created_at.desc(), tables.Conversation.id
                )
            )
            return [Conversation.model_validate(row) for row in rows]

    async def rename_conversation(self, conversation_id: str, title: str) -> None:
        async with self._session.begin() as session:
            row = await session.get(tables.Conversation, conversation_id)
            if row is not None:
                row.title = title

    async def delete_conversation(self, conversation_id: str) -> bool:
        async with self._session.begin() as session:
            row = await session.get(tables.Conversation, conversation_id)
            if row is None:
                return False
            await session.delete(row)
            return True

    async def append_run(
        self, conversation_id: str, messages: list[ModelMessage]
    ) -> None:
        payload = ModelMessagesTypeAdapter.dump_json(messages).decode()
        async with self._session.begin() as session:
            session.add(tables.Run(conversation_id=conversation_id, messages=payload))

    async def load_history(self, conversation_id: str) -> list[ModelMessage]:
        async with self._session() as session:
            payloads = await session.scalars(
                select(tables.Run.messages)
                .where(tables.Run.conversation_id == conversation_id)
                .order_by(tables.Run.id)
            )
        history: list[ModelMessage] = []
        for payload in payloads:
            history.extend(ModelMessagesTypeAdapter.validate_json(payload))
        return history
