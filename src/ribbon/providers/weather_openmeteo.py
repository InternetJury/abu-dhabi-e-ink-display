from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from ribbon.models import WeatherSummary
from ribbon.providers.base import ProviderError, WeatherProvider
from ribbon.settings import SETTINGS


WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    80: "Rain showers",
    95: "Thunderstorm",
}


class OpenMeteoWeatherProvider(WeatherProvider):
    def __init__(self) -> None:
        self.cache_path = SETTINGS.cache_dir / "weather.json"

    @staticmethod
    def _aqi_label(value: int | None) -> str | None:
        if value is None:
            return None
        if value <= 50:
            return "Good"
        if value <= 100:
            return "Moderate"
        if value <= 150:
            return "Unhealthy for Sensitive Groups"
        if value <= 200:
            return "Unhealthy"
        if value <= 300:
            return "Very Unhealthy"
        return "Hazardous"

    def _write_cache(self, weather: WeatherSummary) -> None:
        SETTINGS.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(ZoneInfo(SETTINGS.timezone)).isoformat(),
            "weather": weather.model_dump(mode="json"),
        }
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read_cache(self) -> tuple[datetime | None, WeatherSummary]:
        if not self.cache_path.exists():
            raise ProviderError("No weather cache available")
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"]) if payload.get("fetched_at") else None
        weather_payload = payload.get("weather") or payload
        return fetched_at, WeatherSummary.model_validate(weather_payload)

    def _fresh_cache(self, now: datetime) -> WeatherSummary | None:
        try:
            fetched_at, weather = self._read_cache()
        except ProviderError:
            return None
        if fetched_at is None:
            return None
        age_seconds = (
            now.astimezone(ZoneInfo(SETTINGS.timezone)) - fetched_at.astimezone(ZoneInfo(SETTINGS.timezone))
        ).total_seconds()
        if age_seconds <= SETTINGS.weather_cache_ttl_minutes * 60:
            return weather
        return None

    def fetch(self, now: datetime) -> WeatherSummary:
        cached = self._fresh_cache(now)
        if cached:
            return cached

        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": SETTINGS.weather_latitude,
            "longitude": SETTINGS.weather_longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "daily": "sunrise,sunset,temperature_2m_max,temperature_2m_min",
            "timezone": SETTINGS.timezone,
            "forecast_days": 1,
        }
        try:
            weather_response = httpx.get(weather_url, params=weather_params, timeout=20)
            weather_response.raise_for_status()
            payload = weather_response.json()
        except Exception as exc:
            try:
                _, cached_weather = self._read_cache()
                return cached_weather
            except ProviderError as cache_exc:
                raise ProviderError(f"Open-Meteo request failed: {exc}") from cache_exc

        aqi_index = None
        try:
            aqi_response = httpx.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": SETTINGS.weather_latitude,
                    "longitude": SETTINGS.weather_longitude,
                    "current": "us_aqi,european_aqi",
                    "timezone": SETTINGS.timezone,
                },
                timeout=20,
            )
            aqi_response.raise_for_status()
            aqi_payload = aqi_response.json()
            current_aqi = aqi_payload.get("current", {})
            raw_aqi = current_aqi.get("us_aqi") or current_aqi.get("european_aqi")
            if raw_aqi is not None:
                aqi_index = int(raw_aqi)
        except Exception:
            aqi_index = None

        current = payload.get("current", {})
        daily = payload.get("daily", {})
        timezone = ZoneInfo(SETTINGS.timezone)
        observed_at = datetime.fromisoformat(current["time"]).replace(tzinfo=timezone)
        sunrise = None
        sunset = None
        if daily.get("sunrise"):
            sunrise = datetime.fromisoformat(daily["sunrise"][0]).replace(tzinfo=timezone)
        if daily.get("sunset"):
            sunset = datetime.fromisoformat(daily["sunset"][0]).replace(tzinfo=timezone)

        weather = WeatherSummary(
            location_label=SETTINGS.weather_location_label,
            temperature_c=float(current.get("temperature_2m", 0.0)),
            daily_high_c=float(daily["temperature_2m_max"][0]) if daily.get("temperature_2m_max") else None,
            daily_low_c=float(daily["temperature_2m_min"][0]) if daily.get("temperature_2m_min") else None,
            condition_label=WEATHER_CODES.get(int(current.get("weather_code", -1)), "Unknown"),
            humidity_pct=int(current.get("relative_humidity_2m", 0)),
            aqi_index=aqi_index,
            aqi_label=self._aqi_label(aqi_index),
            sunrise_local=sunrise,
            sunset_local=sunset,
            observed_at=observed_at,
        )
        self._write_cache(weather)
        return weather
