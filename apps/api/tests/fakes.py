"""Canned Open-Meteo payloads (captured from the live API) + test helpers."""

import json

import httpx

GEOCODE_BERLIN = {
    "results": [
        {
            "id": 2950159,
            "name": "Berlin",
            "latitude": 52.52437,
            "longitude": 13.41053,
            "elevation": 74.0,
            "feature_code": "PPLC",
            "country_code": "DE",
            "timezone": "Europe/Berlin",
            "population": 3426354,
            "country": "Germany",
            "admin1": "State of Berlin",
        },
        # The geocoding API omits empty fields entirely; this mirrors a small
        # place with no country/admin1/population in the payload.
        {
            "id": 5083330,
            "name": "Berlin",
            "latitude": 44.46867,
            "longitude": -71.18508,
            "feature_code": "PPL",
            "country_code": "US",
            "timezone": "America/New_York",
        },
    ],
    "generationtime_ms": 0.55,
}

GEOCODE_NO_RESULTS = {"generationtime_ms": 0.4}

FORECAST_BERLIN = {
    "latitude": 52.52,
    "longitude": 13.419998,
    "generationtime_ms": 0.436,
    "utc_offset_seconds": 7200,
    "timezone": "Europe/Berlin",
    "timezone_abbreviation": "GMT+2",
    "elevation": 38.0,
    "current_units": {
        "time": "iso8601",
        "interval": "seconds",
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "apparent_temperature": "°C",
        "precipitation": "mm",
        "weather_code": "wmo code",
        "wind_speed_10m": "km/h",
    },
    "current": {
        "time": "2026-08-24T18:30",
        "interval": 900,
        "temperature_2m": 20.3,
        "relative_humidity_2m": 52,
        "apparent_temperature": 19.4,
        "precipitation": 0.0,
        "weather_code": 1,
        "wind_speed_10m": 6.6,
    },
    "daily_units": {
        "time": "iso8601",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_probability_max": "%",
        "weather_code": "wmo code",
    },
    "daily": {
        "time": ["2026-08-24", "2026-08-25", "2026-08-26"],
        "temperature_2m_max": [20.6, 24.1, 23.6],
        "temperature_2m_min": [11.4, 13.5, 14.3],
        "precipitation_probability_max": [0, 0, 10],
        "weather_code": [3, 3, 61],
    },
}


def openmeteo_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "geocoding-api.open-meteo.com":
        name = request.url.params.get("name", "")
        if name.lower().startswith("berlin"):
            return httpx.Response(200, json=GEOCODE_BERLIN)
        return httpx.Response(200, json=GEOCODE_NO_RESULTS)
    if request.url.host == "api.open-meteo.com":
        return httpx.Response(200, json=FORECAST_BERLIN)
    raise AssertionError(f"unexpected request in test: {request.url}")


def openmeteo_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(openmeteo_handler))


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs."""
    events: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        name = ""
        data: dict = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        events.append((name, data))
    return events
