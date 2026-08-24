"""Chat API: conversation CRUD plus the SSE streaming endpoint.

The streaming endpoint speaks a small SSE vocabulary the web app parses:

    event: text-delta   data: {"delta": "..."}
    event: tool-call    data: {"tool": "..."}
    event: tool-result  data: {"tool": "..."}
    event: done         data: {"conversationId": "..."}
    event: error        data: {"message": "..."}
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import (
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UsageLimits,
    UserPromptPart,
)

from mecha_api.agent import AgentDeps, agent
from mecha_api.config import Settings
from mecha_api.store import Conversation, ConversationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

DEFAULT_TITLE = "New conversation"

# Caps a single run (not the conversation) to stop runaway tool-call loops.
USAGE_LIMITS = UsageLimits(request_limit=8, tool_calls_limit=12)


def _store(request: Request) -> ConversationStore:
    return request.app.state.store


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _agent_deps(request: Request) -> AgentDeps:
    return AgentDeps(http_client=request.app.state.http_client)


StoreDep = Annotated[ConversationStore, Depends(_store)]
SettingsDep = Annotated[Settings, Depends(_settings)]
AgentDepsDep = Annotated[AgentDeps, Depends(_agent_deps)]


class ConversationCreate(BaseModel):
    title: str = Field(default=DEFAULT_TITLE, min_length=1, max_length=120)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


def to_chat_messages(history: list[ModelMessage]) -> list[ChatMessage]:
    """Turn model-message history into displayable user/assistant turns."""
    messages: list[ChatMessage] = []
    for message in history:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    messages.append(ChatMessage(role="user", content=part.content))
        elif isinstance(message, ModelResponse):
            text = "".join(
                part.content for part in message.parts if isinstance(part, TextPart)
            )
            if text:
                messages.append(ChatMessage(role="assistant", content=text))
    return messages


async def _require_conversation(
    store: ConversationStore, conversation_id: str
) -> Conversation:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.get("/conversations", operation_id="listConversations")
async def list_conversations(store: StoreDep) -> list[Conversation]:
    return await store.list_conversations()


@router.post("/conversations", operation_id="createConversation", status_code=201)
async def create_conversation(
    store: StoreDep, body: ConversationCreate | None = None
) -> Conversation:
    return await store.create_conversation((body or ConversationCreate()).title)


@router.delete(
    "/conversations/{conversation_id}",
    operation_id="deleteConversation",
    status_code=204,
)
async def delete_conversation(conversation_id: str, store: StoreDep) -> None:
    if not await store.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")


@router.get(
    "/conversations/{conversation_id}/messages",
    operation_id="listMessages",
)
async def list_messages(conversation_id: str, store: StoreDep) -> list[ChatMessage]:
    await _require_conversation(store, conversation_id)
    return to_chat_messages(await store.load_history(conversation_id))


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_agent_run(
    prompt: str,
    history: list[ModelMessage],
    deps: AgentDeps,
    model: str,
    store: ConversationStore,
    conversation_id: str,
) -> AsyncIterator[str]:
    new_messages: list[ModelMessage] | None = None
    try:
        async with agent.run_stream_events(
            prompt,
            deps=deps,
            model=model,
            message_history=history,
            usage_limits=USAGE_LIMITS,
        ) as events:
            async for event in events:
                if isinstance(event, PartStartEvent):
                    # A text part may start with content already in it.
                    if isinstance(event.part, TextPart) and event.part.content:
                        yield _sse("text-delta", {"delta": event.part.content})
                elif isinstance(event, PartDeltaEvent):
                    if (
                        isinstance(event.delta, TextPartDelta)
                        and event.delta.content_delta
                    ):
                        yield _sse("text-delta", {"delta": event.delta.content_delta})
                elif isinstance(event, FunctionToolCallEvent):
                    yield _sse("tool-call", {"tool": event.part.tool_name})
                elif isinstance(event, FunctionToolResultEvent):
                    yield _sse("tool-result", {"tool": event.part.tool_name})
                elif isinstance(event, AgentRunResultEvent):
                    new_messages = event.result.new_messages()
    except Exception:
        logger.exception("agent run failed (conversation %s)", conversation_id)
        yield _sse("error", {"message": "Agent run failed; see server logs."})
        return
    # Persist only completed runs, so a failed run can be retried cleanly.
    if new_messages is not None:
        await store.append_run(conversation_id, new_messages)
    yield _sse("done", {"conversationId": conversation_id})


@router.post(
    "/conversations/{conversation_id}/messages",
    operation_id="sendMessage",
    # Streams SSE, so the web app reads the body with fetch, not the
    # generated client.
    response_class=StreamingResponse,
)
async def send_message(
    conversation_id: str,
    body: MessageIn,
    store: StoreDep,
    settings: SettingsDep,
    deps: AgentDepsDep,
) -> StreamingResponse:
    conversation = await _require_conversation(store, conversation_id)
    history = await store.load_history(conversation_id)
    if not history and conversation.title == DEFAULT_TITLE:
        await store.rename_conversation(conversation_id, body.content[:80])
    return StreamingResponse(
        _stream_agent_run(
            body.content, history, deps, settings.model, store, conversation_id
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
