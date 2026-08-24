from collections.abc import AsyncIterator

from fakes import parse_sse
from fastapi.testclient import TestClient
from mecha_api.agent import agent
from pydantic_ai import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)


def _streams_text(*chunks: str) -> FunctionModel:
    """A model that streams the given text chunks as its reply."""

    async def stream_fn(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    return FunctionModel(stream_function=stream_fn)


def _create_conversation(client: TestClient) -> str:
    return client.post("/api/conversations").json()["id"]


def test_stream_text_reply(client: TestClient) -> None:
    conversation_id = _create_conversation(client)
    with agent.override(model=_streams_text("Hello from ", "the fake model!")):
        response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "Hi there"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    deltas = [data["delta"] for name, data in events if name == "text-delta"]
    assert "".join(deltas) == "Hello from the fake model!"
    assert len(deltas) > 1  # streamed, not one blob
    assert events[-1] == ("done", {"conversationId": conversation_id})


def test_history_persists_across_runs(client: TestClient) -> None:
    conversation_id = _create_conversation(client)

    async def count_history(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        yield f"history={len(messages)}"

    url = f"/api/conversations/{conversation_id}/messages"
    with agent.override(model=FunctionModel(stream_function=count_history)):
        client.post(url, json={"content": "one"})
        response = client.post(url, json={"content": "two"})

    # Run 2 sees run 1's request + response, plus its own request.
    events = parse_sse(response.text)
    text = "".join(data["delta"] for name, data in events if name == "text-delta")
    assert text == "history=3"

    messages = client.get(url).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0] == {"role": "user", "content": "one"}
    assert messages[3] == {"role": "assistant", "content": "history=3"}


def test_stream_tool_events(client: TestClient) -> None:
    conversation_id = _create_conversation(client)

    async def call_tool_then_answer(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        tool_already_ran = any(
            isinstance(part, ToolReturnPart)
            for message in messages
            for part in message.parts
        )
        if tool_already_ran:
            yield "Done."
        else:
            yield {0: DeltaToolCall(name="current_datetime", json_args="{}")}

    with agent.override(model=FunctionModel(stream_function=call_tool_then_answer)):
        response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "What time is it?"},
        )

    names = [name for name, _ in parse_sse(response.text)]
    assert "tool-call" in names
    assert "tool-result" in names
    assert names[-1] == "done"


def test_message_to_unknown_conversation_is_404(client: TestClient) -> None:
    with agent.override(model=_streams_text("x")):
        response = client.post(
            "/api/conversations/nope/messages", json={"content": "hi"}
        )
    assert response.status_code == 404


def test_empty_message_is_rejected(client: TestClient) -> None:
    conversation_id = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": ""}
    )
    assert response.status_code == 422
