from typing import cast

import pytest
from fakes import openmeteo_client
from mecha_api import weather
from mecha_api.agent import AgentDeps, agent
from pydantic_ai import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

pytestmark = pytest.mark.anyio


def _tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


async def test_weather_tool_chain() -> None:
    """The scripted model chains search_locations → get_weather_forecast."""

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = _tool_returns(messages)
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="search_locations", args={"name": "Berlin"})
                ]
            )
        if len(returns) == 1:
            locations = cast(list[weather.Location], returns[0].content)
            best_match = locations[0]
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_weather_forecast",
                        args={
                            "latitude": best_match.latitude,
                            "longitude": best_match.longitude,
                        },
                    )
                ]
            )
        report = cast(weather.WeatherReport, returns[1].content)
        return ModelResponse(
            parts=[
                TextPart(
                    f"Berlin: {report.current.temperature_c}°C, "
                    f"{report.current.conditions}"
                )
            ]
        )

    async with openmeteo_client() as http_client:
        with agent.override(model=FunctionModel(scripted)):
            result = await agent.run(
                "What's the weather in Berlin?",
                deps=AgentDeps(http_client=http_client),
            )

    assert result.output == "Berlin: 20.3°C, mainly clear"


async def test_unknown_location_feeds_retry_back_to_model() -> None:
    """An unmatched location raises ModelRetry; the model sees the hint."""

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        retried = any(
            isinstance(part, RetryPromptPart)
            for message in messages
            for part in message.parts
        )
        if retried:
            return ModelResponse(parts=[TextPart("I couldn't find that place.")])
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name="search_locations", args={"name": "Atlantis"})
            ]
        )

    async with openmeteo_client() as http_client:
        with agent.override(model=FunctionModel(scripted)):
            result = await agent.run(
                "Weather in Atlantis?", deps=AgentDeps(http_client=http_client)
            )

    assert result.output == "I couldn't find that place."
    retry = next(
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    )
    assert "No location matches 'Atlantis'" in str(retry.content)


async def test_out_of_range_forecast_days_is_rejected() -> None:
    """Pydantic validates tool args; bad values become retries, then a fix."""

    def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        retried = any(
            isinstance(part, RetryPromptPart)
            for message in messages
            for part in message.parts
        )
        if not retried:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_weather_forecast",
                        args={"latitude": 52.5, "longitude": 13.4, "forecast_days": 99},
                    )
                ]
            )
        if not _tool_returns(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_weather_forecast",
                        args={"latitude": 52.5, "longitude": 13.4, "forecast_days": 3},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("Fixed it.")])

    async with openmeteo_client() as http_client:
        with agent.override(model=FunctionModel(scripted)):
            result = await agent.run(
                "Forecast?", deps=AgentDeps(http_client=http_client)
            )

    assert result.output == "Fixed it."
