"""
Weather MCP Server - A Model Context Protocol server for fetching weather forecasts.

This module provides a weather forecast service using the Government of Canada
Weather API. It exposes a single tool for getting forecasts by latitude and longitude.
"""

import asyncio
import logging
import sys
import time
from typing import Any, Dict, List

import httpx
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("weather-mcp")

# Constants
GC_API_BASE = "https://weather.gc.ca"
USER_AGENT = "weather-app/1.0"
REQUEST_TIMEOUT = 30.0  # seconds
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds

# Initialize FastMCP server
mcp = FastMCP("weather")


class WeatherAPIError(Exception):
    """Raised when there's an error communicating with the weather API."""

    pass


async def make_gc_request(url: str, retries: int = MAX_RETRIES) -> Dict[str, Any]:
    """Make a request to the GC Weather API with proper error handling and retries.

    Args:
        url: The URL to request
        retries: Number of retries on transient errors

    Returns:
        Parsed JSON response data

    Raises:
        WeatherAPIError: If the request fails after all retries
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}

    attempt = 0
    last_error = None

    while attempt <= retries:
        try:
            logger.info(f"Making request to: {url} (attempt {attempt+1}/{retries+1})")
            start_time = time.time()

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=headers, timeout=REQUEST_TIMEOUT
                )

            duration = time.time() - start_time
            logger.info(f"Request completed in {duration:.2f}s")

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"HTTP error: {status_code} - {e}")

            # Don't retry client errors (except 429 too many requests)
            if 400 <= status_code < 500 and status_code != 429:
                raise WeatherAPIError(f"Client error: {e}") from e

            last_error = e

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(f"Request error: {e}")
            last_error = e

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise WeatherAPIError(f"Unexpected error: {e}") from e

        # If we get here, we need to retry
        attempt += 1
        if attempt <= retries:
            wait_time = RETRY_DELAY * (2 ** (attempt - 1))  # Exponential backoff
            logger.info(f"Retrying in {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)

    # If we've exhausted retries
    raise WeatherAPIError(f"Failed after {retries+1} attempts: {last_error}")


def format_forecast(daily_forecast: List[Dict[str, Any]], max_days: int = 5) -> str:
    """Format the daily forecast data into a readable string.

    Args:
        daily_forecast: List of daily forecast data
        max_days: Maximum number of days to include

    Returns:
        Formatted forecast string
    """
    forecasts = []
    days_added = 0

    for day in daily_forecast:
        # Skip night forecasts and limit to max_days
        if day.get("periodLabel") == "Night" or days_added >= max_days:
            continue

        date = day.get("date", "Unknown date")
        text = day.get("text", "No forecast available")

        forecast = f"""
{date}:
Forecast: {text}
"""
        forecasts.append(forecast)
        days_added += 1

    if not forecasts:
        return "No forecast data available"

    return "\n---\n".join(forecasts)


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location

    Returns:
        A formatted string with the 5-day weather forecast
    """
    # Input validation
    if not isinstance(latitude, (int, float)) or not isinstance(
        longitude, (int, float)
    ):
        return "Error: Latitude and longitude must be numbers"

    if latitude < -90 or latitude > 90:
        return "Error: Latitude must be between -90 and 90 degrees"

    if longitude < -180 or longitude > 180:
        return "Error: Longitude must be between -180 and 180 degrees"

    logger.info(f"get_forecast called with lat={latitude}, lon={longitude}")

    try:
        # Build the forecast URL
        forecast_url = (
            f"{GC_API_BASE}/api/app/en/Location/{latitude},{longitude}?type=city"
        )

        # Get the forecast data
        api_response = await make_gc_request(forecast_url)

        if (
            not api_response
            or not isinstance(api_response, list)
            or len(api_response) == 0
        ):
            logger.error(f"Invalid API response: {api_response}")
            return "Unable to fetch forecast data for this location"

        forecast_data = api_response[0]

        # Get the daily forecast
        daily_forecast = forecast_data.get("dailyFcst", {}).get("daily", [])

        if not daily_forecast:
            logger.warning("No daily forecast data found in response")
            return "No forecast data available for this location"

        # Format and return the forecast
        return format_forecast(daily_forecast)

    except WeatherAPIError as e:
        logger.error(f"Weather API error: {e}")
        return f"Weather API error: {str(e)}"

    except KeyError as e:
        logger.error(f"KeyError while processing forecast data: {e}")
        return f"Unable to process forecast data: missing key {e}"

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return f"Error processing forecast data: {str(e)}"


# Add more tools here as needed
# @mcp.tool()
# async def get_current_conditions(latitude: float, longitude: float) -> str:
#     """Get current weather conditions for a location."""
#     pass


if __name__ == "__main__":
    logger.info("Starting weather MCP server")

    try:
        # Initialize and run the server
        mcp.run(transport="stdio")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
