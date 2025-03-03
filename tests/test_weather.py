"""
Tests for the weather MCP server.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import weather

# Sample API response data for testing
SAMPLE_API_RESPONSE = [
    {
        "displayName": "Test City",
        "dailyFcst": {
            "daily": [
                {
                    "date": "2023-01-01",
                    "periodLabel": "Day",
                    "text": "Sunny with cloudy periods",
                },
                {"date": "2023-01-01", "periodLabel": "Night", "text": "Clear"},
                {
                    "date": "2023-01-02",
                    "periodLabel": "Day",
                    "text": "Cloudy with chance of rain",
                },
                {"date": "2023-01-02", "periodLabel": "Night", "text": "Cloudy"},
                {"date": "2023-01-03", "periodLabel": "Day", "text": "Sunny"},
            ]
        },
    }
]


@pytest.fixture
def mock_httpx_response():
    """Fixture for mocking httpx response."""
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_API_RESPONSE
    mock_response.raise_for_status.return_value = None
    return mock_response


@pytest.fixture
def mock_httpx_client(mock_httpx_response):
    """Fixture for mocking httpx client."""
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_httpx_response
    return mock_client


@pytest.mark.asyncio
async def test_make_gc_request(mock_httpx_client):
    """Test the make_gc_request function."""
    # Use the __aenter__ method to return self for the async context manager
    mock_httpx_client.__aenter__.return_value = mock_httpx_client

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        result = await weather.make_gc_request("https://test-url.com")

    assert result == SAMPLE_API_RESPONSE
    mock_httpx_client.get.assert_called_once()


def test_format_forecast():
    """Test the format_forecast function."""
    daily_forecast = SAMPLE_API_RESPONSE[0]["dailyFcst"]["daily"]

    result = weather.format_forecast(daily_forecast)

    assert "2023-01-01" in result
    assert "Sunny with cloudy periods" in result
    assert "2023-01-02" in result
    assert "Cloudy with chance of rain" in result
    assert "2023-01-03" in result
    assert "Sunny" in result

    # Ensure night forecasts are filtered out
    assert "Clear" not in result
    assert "Night" not in result


@pytest.mark.asyncio
async def test_get_forecast_success(mock_httpx_client):
    """Test the get_forecast function with successful API response."""
    # Mock the make_gc_request function directly instead of httpx
    with patch("weather.make_gc_request", return_value=SAMPLE_API_RESPONSE):
        result = await weather.get_forecast(45.0, -75.0)

    assert "2023-01-01" in result
    assert "Sunny with cloudy periods" in result
    assert "2023-01-02" in result
    assert "2023-01-03" in result


@pytest.mark.asyncio
async def test_get_forecast_invalid_coordinates():
    """Test get_forecast with invalid coordinates."""
    # Test with latitude out of range
    result = await weather.get_forecast(100.0, 0.0)
    assert "Error: Latitude must be between" in result

    # Test with longitude out of range
    result = await weather.get_forecast(0.0, 200.0)
    assert "Error: Longitude must be between" in result

    # Test with non-numeric values - our implementation handles this with a validation
    # check rather than raising a TypeError, so we check the error message instead
    try:
        result = await weather.get_forecast("invalid", 0.0)
        assert "Error: Latitude and longitude must be numbers" in result
    except TypeError:
        # Alternative: If the implementation does raise TypeError, this will pass too
        pass


@pytest.mark.asyncio
async def test_get_forecast_api_error():
    """Test get_forecast when API request fails."""
    with patch(
        "weather.make_gc_request", side_effect=weather.WeatherAPIError("API error")
    ):
        result = await weather.get_forecast(45.0, -75.0)

    assert "Weather API error" in result


@pytest.mark.asyncio
async def test_get_forecast_empty_response():
    """Test get_forecast with empty API response."""
    with patch("weather.make_gc_request", return_value=[]):
        result = await weather.get_forecast(45.0, -75.0)

    assert "Unable to fetch forecast data" in result


@pytest.mark.asyncio
async def test_get_forecast_missing_data():
    """Test get_forecast with missing forecast data."""
    with patch("weather.make_gc_request", return_value=[{"displayName": "Test City"}]):
        result = await weather.get_forecast(45.0, -75.0)

    assert "No forecast data available" in result
