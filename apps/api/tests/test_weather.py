import httpx
import pytest
from fakes import openmeteo_client
from mecha_api import weather

pytestmark = pytest.mark.anyio


async def test_search_locations_parses_results() -> None:
    async with openmeteo_client() as client:
        locations = await weather.search_locations(client, "Berlin")

    assert len(locations) == 2
    assert locations[0].name == "Berlin"
    assert locations[0].country == "Germany"
    assert locations[0].population == 3426354
    # The API omits empty fields; the model must tolerate their absence.
    assert locations[1].country is None
    assert locations[1].population is None


async def test_search_locations_without_results_key() -> None:
    async with openmeteo_client() as client:
        assert await weather.search_locations(client, "Atlantis") == []


async def test_get_forecast() -> None:
    async with openmeteo_client() as client:
        report = await weather.get_forecast(client, 52.52, 13.41)

    assert report.timezone == "Europe/Berlin"
    assert report.current.temperature_c == 20.3
    assert report.current.conditions == "mainly clear"
    assert len(report.daily) == 3
    assert report.daily[0].temperature_max_c == 20.6
    assert report.daily[2].conditions == "slight rain"


async def test_api_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": True, "reason": "Latitude must be in range"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(weather.OpenMeteoError, match="Latitude must be in range"):
            await weather.get_forecast(client, 999.0, 13.41)


def test_describe_unknown_weather_code() -> None:
    assert weather.describe_weather_code(1234) == "unknown conditions (WMO code 1234)"
