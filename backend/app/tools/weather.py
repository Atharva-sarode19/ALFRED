"""weather: current conditions and forecast from Open-Meteo (no API key)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, PermissionLevel, ToolResult

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "light freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "light freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


class Units(str, Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class WeatherInput(BaseModel):
    location: str = Field(..., min_length=1, max_length=100, description="City or place, e.g. 'Pune, India'.")
    forecast_days: int = Field(default=0, ge=0, le=7, description="0 for current conditions only, else days of forecast.")
    units: Units = Field(default=Units.METRIC, description="metric (C, km/h) or imperial (F, mph).")


class WeatherLookupError(RuntimeError):
    pass


def describe(code: Any) -> str:
    return WMO_CODES.get(int(code), "unknown conditions") if code is not None else "unknown conditions"


class WeatherTool(BaseTool):
    name = "weather"
    description = "Get the current weather and an optional multi-day forecast for a place."
    permission_level = PermissionLevel.LOW
    input_model = WeatherInput

    def __init__(self, client: Any | None = None):
        # `client` is any object with `async get(url, params=...)` (httpx.AsyncClient); injectable for tests.
        self._client = client

    async def _get_json(self, client: Any, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def execute(self, arguments: WeatherInput) -> ToolResult:
        try:
            if self._client is not None:
                data = await self._lookup(self._client, arguments)
            else:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    data = await self._lookup(client, arguments)
        except WeatherLookupError as exc:
            return ToolResult.fail(str(exc))
        except Exception:  # noqa: BLE001 - network/HTTP errors must not leak details
            return ToolResult.fail("The weather service is unavailable right now.")
        return ToolResult.ok(data)

    async def _lookup(self, client: Any, args: WeatherInput) -> dict[str, Any]:
        place = await self._geocode(client, args.location)

        imperial = args.units == Units.IMPERIAL
        params: dict[str, Any] = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
        if imperial:
            params.update(temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch")
        if args.forecast_days:
            params["daily"] = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            params["forecast_days"] = args.forecast_days

        raw = await self._get_json(client, FORECAST_URL, params)
        cur = raw.get("current") or {}
        units = raw.get("current_units") or {}
        result: dict[str, Any] = {
            "location": ", ".join(p for p in (place.get("name"), place.get("admin1"), place.get("country")) if p),
            "timezone": raw.get("timezone"),
            "current": {
                "conditions": describe(cur.get("weather_code")),
                "temperature": cur.get("temperature_2m"),
                "feels_like": cur.get("apparent_temperature"),
                "humidity_percent": cur.get("relative_humidity_2m"),
                "wind_speed": cur.get("wind_speed_10m"),
                "precipitation": cur.get("precipitation"),
                "units": {
                    "temperature": units.get("temperature_2m", "F" if imperial else "C"),
                    "wind_speed": units.get("wind_speed_10m", "mph" if imperial else "km/h"),
                },
                "observed_at": cur.get("time"),
            },
        }
        daily = raw.get("daily")
        if args.forecast_days and daily:
            result["forecast"] = [
                {
                    "date": day,
                    "conditions": describe(daily["weather_code"][i]),
                    "high": daily["temperature_2m_max"][i],
                    "low": daily["temperature_2m_min"][i],
                    "precipitation_probability_percent": daily["precipitation_probability_max"][i],
                }
                for i, day in enumerate(daily.get("time", []))
            ]
        return result

    async def _geocode(self, client: Any, location: str) -> dict[str, Any]:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        name, hints = parts[0], [h.lower() for h in parts[1:]]
        data = await self._get_json(client, GEOCODE_URL, {"name": name, "count": 5, "language": "en", "format": "json"})
        results = data.get("results") or []
        if not results:
            raise WeatherLookupError(f"I couldn't find a place called '{location}'.")
        if hints:
            for candidate in results:
                labels = [str(candidate.get(k, "")).lower() for k in ("country", "admin1", "country_code")]
                if any(h in labels for h in hints):
                    return candidate
        return results[0]
