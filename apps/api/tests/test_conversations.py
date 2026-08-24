from fastapi.testclient import TestClient
from mecha_api.agent import agent
from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def test_create_and_list(client: TestClient) -> None:
    created = client.post("/api/conversations", json={"title": "Weather chat"})
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["title"] == "Weather chat"

    listed = client.get("/api/conversations").json()
    assert [c["id"] for c in listed] == [conversation["id"]]


def test_create_without_body_uses_default_title(client: TestClient) -> None:
    conversation = client.post("/api/conversations").json()
    assert conversation["title"] == "New conversation"


def test_first_message_becomes_title(client: TestClient) -> None:
    conversation = client.post("/api/conversations").json()

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("Sunny.")])

    with agent.override(model=FunctionModel(reply)):
        client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"content": "Weather in Berlin?"},
        )

    listed = client.get("/api/conversations").json()
    assert listed[0]["title"] == "Weather in Berlin?"


def test_messages_of_new_conversation_is_empty(client: TestClient) -> None:
    conversation = client.post("/api/conversations").json()
    messages = client.get(f"/api/conversations/{conversation['id']}/messages")
    assert messages.status_code == 200
    assert messages.json() == []


def test_messages_of_unknown_conversation_is_404(client: TestClient) -> None:
    assert client.get("/api/conversations/nope/messages").status_code == 404


def test_delete(client: TestClient) -> None:
    conversation = client.post("/api/conversations").json()
    assert client.delete(f"/api/conversations/{conversation['id']}").status_code == 204
    assert client.get("/api/conversations").json() == []
    assert client.delete(f"/api/conversations/{conversation['id']}").status_code == 404
