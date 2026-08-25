"""Database tables.

Alembic autogenerates migrations by diffing `Base.metadata` against the
database, so every schema change starts here. Named `tables` rather than
`models` because "model" already means an LLM in this codebase.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    DateTime,
    Dialect,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is always UTC-aware, on every backend.

    SQLite has no timestamp type and drops the offset, so a value written as
    aware comes back naive and comparisons against `datetime.now(UTC)` raise.
    Normalizing in both directions keeps SQLite and Postgres behaving alike.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: pass an aware one, e.g. now(UTC)")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    # Every `Mapped[datetime]` column gets `UtcDateTime` without repeating it.
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: UtcDateTime}


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(default=_now)

    runs: Mapped[list[Run]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        # Let the database's ON DELETE CASCADE do the work. Without this the
        # ORM loads every run just to delete it, which mid-async is a lazy
        # load on a closed greenlet rather than a slow query.
        passive_deletes=True,
    )


class Run(Base):
    """One completed agent run's new messages, as `ModelMessagesTypeAdapter` JSON.

    A conversation's history is its runs in order.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)
    messages: Mapped[str] = mapped_column(Text)

    conversation: Mapped[Conversation] = relationship(back_populates="runs")
