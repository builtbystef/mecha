"""Typed client for the free Open-Meteo APIs (https://open-meteo.com).

No API key required. Data is CC-BY 4.0 (attribute Open-Meteo) and the free
tier is for non-commercial use, rate-limited to ~10k requests/day.
"""

from typing import Any

import httpx
from pydantic import BaseModel

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_WEATHER_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class OpenMeteoError(Exception):
    """Open-Meteo rejected the request (its errors are `{error, reason}`)."""


class Location(BaseModel):
    # The geocoding API omits empty fields, so most fields are optional.
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None
    timezone: str | None = None
    population: int | None = None


class CurrentConditions(BaseModel):
    time: str
    temperature_c: float
    feels_like_c: float
    relative_humidity_pct: int
    precipitation_mm: float
    wind_speed_kmh: float
    conditions: str


class DailyForecast(BaseModel):
    date: str
    temperature_max_c: float
    temperature_min_c: float
    precipitation_probability_pct: int | None
    conditions: str


class WeatherReport(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    current: CurrentConditions
    daily: list[DailyForecast]


def describe_weather_code(code: int) -> str:
    return WMO_WEATHER_CODES.get(code, f"unknown conditions (WMO code {code})")


async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = await client.get(url, params=params)
    if response.is_client_error:
        body = response.json()
        if isinstance(body, dict) and body.get("error"):
            raise OpenMeteoError(str(body.get("reason", "bad request")))
    response.raise_for_status()
    data = response.json()
    assert isinstance(data, dict)
    return data


async def search_locations(
    client: httpx.AsyncClient, name: str, count: int = 5
) -> list[Location]:
    """Match a place name to candidate locations, best match first."""
    data = await _get_json(
        client,
        GEOCODING_URL,
        {"name": name, "count": count, "language": "en", "format": "json"},
    )
    # No matches means no `results` key at all, not an empty list.
    return [Location.model_validate(raw) for raw in data.get("results", [])]


async def get_forecast(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    forecast_days: int = 3,
) -> WeatherReport:
    """Fetch current conditions plus a daily forecast for coordinates."""
    data = await _get_json(
        client,
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,weather_code"
            ),
            "timezone": "auto",
            "forecast_days": forecast_days,
        },
    )
    current = data["current"]
    daily = data["daily"]
    return WeatherReport(
        latitude=data["latitude"],
        longitude=data["longitude"],
        timezone=data["timezone"],
        current=CurrentConditions(
            time=current["time"],
            temperature_c=current["temperature_2m"],
            feels_like_c=current["apparent_temperature"],
            relative_humidity_pct=current["relative_humidity_2m"],
            precipitation_mm=current["precipitation"],
            wind_speed_kmh=current["wind_speed_10m"],
            conditions=describe_weather_code(current["weather_code"]),
        ),
        daily=[
            DailyForecast(
                date=date,
                temperature_max_c=t_max,
                temperature_min_c=t_min,
                precipitation_probability_pct=rain_prob,
                conditions=describe_weather_code(code),
            )
            for date, t_max, t_min, rain_prob, code in zip(
                daily["time"],
                daily["temperature_2m_max"],
                daily["temperature_2m_min"],
                daily["precipitation_probability_max"],
                daily["weather_code"],
                strict=True,
            )
        ],
    )
