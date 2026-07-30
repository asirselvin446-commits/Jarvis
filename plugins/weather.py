"""
J.A.R.V.I.S. Weather Plugin
Fetches current weather and forecasts using the Open-Meteo API (free, no API key).
Falls back to wttr.in for simple weather queries.
"""

import requests
import json
from core.tool_manager import tool


def _geocode(city: str) -> dict | None:
    """Get latitude/longitude for a city using Open-Meteo geocoding."""
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en"},
            timeout=10
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                r = results[0]
                return {
                    "name": r.get("name", city),
                    "country": r.get("country", ""),
                    "lat": r["latitude"],
                    "lon": r["longitude"]
                }
    except Exception:
        pass
    return None


def _weather_code_to_text(code: int) -> str:
    """Convert WMO weather code to human-readable text."""
    codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
        77: "Snow grains",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        85: "Slight snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
    }
    return codes.get(code, f"Weather code {code}")


@tool(
    name="get_weather",
    description="Gets the current weather and 3-day forecast for a city. No API key required.",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "Name of the city (e.g., 'Chennai', 'New York', 'London')."
            }
        },
        "required": ["city"]
    }
)
def get_weather(city: str) -> str:
    # 1. Geocode the city
    location = _geocode(city)
    if not location:
        # Fallback to wttr.in
        try:
            resp = requests.get(f"https://wttr.in/{city}?format=3", timeout=10)
            if resp.status_code == 200:
                return resp.text.strip()
        except Exception:
            pass
        return f"Couldn't find weather data for '{city}'."

    # 2. Fetch weather from Open-Meteo
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location["lat"],
                "longitude": location["lon"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": 3
            },
            timeout=10
        )

        if resp.status_code != 200:
            return f"Weather API error: {resp.status_code}"

        data = resp.json()
        current = data.get("current", {})
        daily = data.get("daily", {})

        # Current conditions
        temp = current.get("temperature_2m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        weather_code = current.get("weather_code", 0)
        condition = _weather_code_to_text(weather_code)

        result = f"Weather in {location['name']}, {location['country']}:\n"
        result += f"  Currently: {condition}, {temp}°C\n"
        result += f"  Humidity: {humidity}% | Wind: {wind} km/h\n"

        # 3-day forecast
        if daily and "time" in daily:
            result += "\n  3-Day Forecast:\n"
            for i in range(min(3, len(daily["time"]))):
                day = daily["time"][i]
                high = daily["temperature_2m_max"][i]
                low = daily["temperature_2m_min"][i]
                code = daily["weather_code"][i]
                result += f"    {day}: {_weather_code_to_text(code)}, {low}°C – {high}°C\n"

        return result.strip()

    except Exception as e:
        return f"Failed to fetch weather: {e}"


@tool(
    name="get_weather_brief",
    description="Gets a one-line weather summary for quick voice response.",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name.",
                "default": "Chennai"
            }
        }
    }
)
def get_weather_brief(city: str = "Chennai") -> str:
    try:
        resp = requests.get(f"https://wttr.in/{city}?format=3", timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass

    # Fallback to full weather
    return get_weather(city)
