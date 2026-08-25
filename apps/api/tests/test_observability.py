"""Instrumentation is wired up: a chat turn produces a usable trace.

`capfire` swaps the global exporter for an in-memory one, so these assert on
the spans the app would have sent rather than on any backend.
"""

from collections.abc import AsyncIterator
from typing import Any

import logfire
import pytest
from fastapi.testclient import TestClient
from logfire.testing import CaptureLogfire
from mecha_api.agent import agent
from pydantic_ai import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)


def _send(client: TestClient, model: FunctionModel, content: str) -> str:
    conversation_id = client.post("/api/conversations").json()["id"]
    with agent.override(model=model):
        client.post(
            f"/api/conversations/{conversation_id}/messages", json={"content": content}
        )
    return conversation_id


def _spans(capfire: CaptureLogfire) -> list[dict[str, Any]]:
    return capfire.exporter.exported_spans_as_dict()


def _replies(*chunks: str) -> FunctionModel:
    async def stream_fn(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    return FunctionModel(stream_function=stream_fn)


def test_chat_turn_span_carries_conversation_id(
    client: TestClient, capfire: CaptureLogfire
) -> None:
    conversation_id = _send(client, _replies("hi"), "Hello")

    turns = [s for s in _spans(capfire) if s["name"] == "chat turn"]
    assert len(turns) == 1
    assert turns[0]["attributes"]["conversation_id"] == conversation_id


def test_chat_turn_span_records_usage(
    client: TestClient, capfire: CaptureLogfire
) -> None:
    _send(client, _replies("hi"), "Hello")

    (turn,) = [s for s in _spans(capfire) if s["name"] == "chat turn"]
    assert turn["attributes"]["requests"] == 1
    assert turn["attributes"]["output_tokens"] > 0


def test_agent_and_tool_spans_nest_under_the_turn(
    client: TestClient, capfire: CaptureLogfire
) -> None:
    async def call_tool_then_answer(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        already_ran = any(
            isinstance(part, ToolReturnPart)
            for message in messages
            for part in message.parts
        )
        if already_ran:
            yield "Done."
        else:
            yield {0: DeltaToolCall(name="current_datetime", json_args="{}")}

    _send(client, FunctionModel(stream_function=call_tool_then_answer), "What time?")

    names = [s["name"] for s in _spans(capfire)]
    # pydantic-ai's own spans, reachable because `configure()` ran.
    assert "invoke_agent agent" in names
    assert "execute_tool current_datetime" in names
    assert "chat turn" in names


def test_failed_run_marks_the_turn_span_as_an_error(
    client: TestClient, capfire: CaptureLogfire
) -> None:
    async def explode(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        raise RuntimeError("provider is down")
        yield ""  # pragma: no cover - makes this an async generator

    _send(client, FunctionModel(stream_function=explode), "Hello")

    (turn,) = [s for s in _spans(capfire) if s["name"] == "chat turn"]
    # 17 is OTel's number for the "error" level.
    assert turn["attributes"]["logfire.level_num"] == 17


def test_health_is_not_traced(client: TestClient, capfire: CaptureLogfire) -> None:
    client.get("/api/health")

    assert not [s for s in _spans(capfire) if "health" in s["name"]]


def test_requests_are_traced(client: TestClient, capfire: CaptureLogfire) -> None:
    client.get("/api/conversations")

    (span,) = [s for s in _spans(capfire) if s["name"] == "GET /api/conversations"]
    assert span["attributes"]["fastapi.route.operation_id"] == "listConversations"


@pytest.mark.parametrize("include_content", [True, False])
def test_trace_content_controls_prompts_on_spans(
    client: TestClient, capfire: CaptureLogfire, include_content: bool
) -> None:
    # `configure()` applies this once at import; re-apply it here and restore
    # the default afterwards.
    logfire.instrument_pydantic_ai(include_content=include_content)
    try:
        _send(client, _replies("hi"), "my secret question")
    finally:
        logfire.instrument_pydantic_ai(include_content=True)

    model_spans = [
        s for s in _spans(capfire) if "gen_ai.input.messages" in s["attributes"]
    ]
    prompts = str([s["attributes"]["gen_ai.input.messages"] for s in model_spans])
    assert ("my secret question" in prompts) is include_content
