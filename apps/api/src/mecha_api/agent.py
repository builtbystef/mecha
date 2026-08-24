"""The mecha agent: provider-agnostic, tool-calling, dependency-injected.

The agent is defined without a model; the "<provider>:<model>" string from
settings is passed per run (`agent.run(..., model=...)`), which keeps this
module import-safe and lets tests swap in TestModel/FunctionModel via
`agent.override()`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import httpx
from pydantic import Field
from pydantic_ai import Agent, ModelRetry, RunContext

from mecha_api import weather


@dataclass
class AgentDeps:
    """Runtime dependencies injected into every tool call via `ctx.deps`."""

    http_client: httpx.AsyncClient


INSTRUCTIONS = """\
You are mecha, a concise, friendly assistant with live weather data.

When asked about weather, first resolve the place name to coordinates with
`search_locations`, then call `get_weather_forecast`. If several locations
match, pick the most populous unless the user was more specific. Report
temperatures in °C and mention the local date the forecast applies to.
Weather data comes from Open-Meteo (CC-BY 4.0).

Answer non-weather questions normally; use `current_datetime` whenever the
current date or time matters."""

agent: Agent[AgentDeps, str] = Agent(
    deps_type=AgentDeps,
    instructions=INSTRUCTIONS,
    retries=2,
)


@agent.tool
async def search_locations(
    ctx: RunContext[AgentDeps], name: str
) -> list[weather.Location]:
    """Find places matching a name and return their coordinates.

    Args:
        name: City or place name, e.g. "Berlin" or "Podgorica".
    """
    try:
        locations = await weather.search_locations(ctx.deps.http_client, name)
    except weather.OpenMeteoError as exc:
        raise ModelRetry(f"Location search failed: {exc}") from exc
    if not locations:
        raise ModelRetry(
            f"No location matches {name!r}. Try another spelling, the local "
            "name, or a nearby larger city."
        )
    return locations


@agent.tool
async def get_weather_forecast(
    ctx: RunContext[AgentDeps],
    latitude: Annotated[float, Field(ge=-90, le=90)],
    longitude: Annotated[float, Field(ge=-180, le=180)],
    forecast_days: Annotated[int, Field(ge=1, le=16)] = 3,
) -> weather.WeatherReport:
    """Get current conditions and a daily forecast for coordinates.

    Args:
        latitude: WGS84 latitude in decimal degrees.
        longitude: WGS84 longitude in decimal degrees.
        forecast_days: How many days of forecast to return (1-16).
    """
    try:
        return await weather.get_forecast(
            ctx.deps.http_client, latitude, longitude, forecast_days
        )
    except weather.OpenMeteoError as exc:
        raise ModelRetry(f"Forecast request failed: {exc}") from exc


@agent.tool_plain
def current_datetime() -> str:
    """Get the current date and time in UTC, ISO 8601 formatted."""
    return datetime.now(UTC).isoformat(timespec="seconds")
