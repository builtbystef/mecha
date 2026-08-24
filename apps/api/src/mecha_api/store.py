"""SQLite persistence for conversations and their model-message history.

Each agent run appends one row holding that run's new messages, serialized
with pydantic-ai's `ModelMessagesTypeAdapter`; a conversation's full history
is the concatenation of its runs, ready to pass back as `message_history=`.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    messages TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_by_conversation ON runs(conversation_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Conversation(BaseModel):
    id: str
    title: str
    created_at: datetime


class ConversationStore:
    def __init__(self, path: Path | str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("ConversationStore.connect() was never called")
        return self._db

    async def create_conversation(self, title: str) -> Conversation:
        conversation = Conversation(id=uuid.uuid4().hex, title=title, created_at=_now())
        await self._conn.execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
            (conversation.id, conversation.title, conversation.created_at.isoformat()),
        )
        await self._conn.commit()
        return conversation

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        cursor = await self._conn.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Conversation(id=row[0], title=row[1], created_at=row[2])

    async def list_conversations(self) -> list[Conversation]:
        cursor = await self._conn.execute(
            "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            Conversation(id=row[0], title=row[1], created_at=row[2]) for row in rows
        ]

    async def rename_conversation(self, conversation_id: str, title: str) -> None:
        await self._conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id),
        )
        await self._conn.commit()

    async def delete_conversation(self, conversation_id: str) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def append_run(
        self, conversation_id: str, messages: list[ModelMessage]
    ) -> None:
        payload = ModelMessagesTypeAdapter.dump_json(messages).decode()
        await self._conn.execute(
            "INSERT INTO runs (conversation_id, created_at, messages) VALUES (?, ?, ?)",
            (conversation_id, _now(), payload),
        )
        await self._conn.commit()

    async def load_history(self, conversation_id: str) -> list[ModelMessage]:
        cursor = await self._conn.execute(
            "SELECT messages FROM runs WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        history: list[ModelMessage] = []
        for (payload,) in rows:
            history.extend(ModelMessagesTypeAdapter.validate_json(payload))
        return history
