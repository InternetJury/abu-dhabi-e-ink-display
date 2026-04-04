from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SavedStop:
    stop_id: str
    title: str


@dataclass(frozen=True)
class ProjectSettings:
    project_name: str
    width: int
    height: int
    timezone: str
    weekday_commute_stop: SavedStop
    weekday_commute_start_hour: int
    weekday_commute_start_minute: int
    weekday_commute_end_hour: int
    weekday_commute_end_minute: int
    walking_buffer_minutes: int
    rotation_minutes: int
    render_interval_seconds: int
    full_refresh_minutes: int
    weather_cache_ttl_minutes: int
    market_cache_ttl_minutes: int
    weekend_stops: tuple[SavedStop, ...]
    weather_latitude: float
    weather_longitude: float
    weather_location_label: str
    headline_feed_urls: tuple[str, ...]
    headline_cache_ttl_minutes: int
    output_dir: Path
    frame_output_dir: Path
    demo_output_dir: Path
    cache_dir: Path
    darbi_map_url: str
    darbi_user_agent: str


ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT_DIR / "output"

SETTINGS = ProjectSettings(
    project_name="abudhabi-mobility-ribbon",
    width=1360,
    height=480,
    timezone="Asia/Dubai",
    weekday_commute_stop=SavedStop(stop_id="00513B", title="Aster Pharmacy"),
    weekday_commute_start_hour=6,
    weekday_commute_start_minute=0,
    weekday_commute_end_hour=8,
    weekday_commute_end_minute=0,
    walking_buffer_minutes=5,
    rotation_minutes=10,
    render_interval_seconds=60,
    full_refresh_minutes=5,
    weather_cache_ttl_minutes=10,
    market_cache_ttl_minutes=15,
    weekend_stops=(
        SavedStop(stop_id="00513B", title="Aster Pharmacy"),
        SavedStop(stop_id="00512A", title="UAE Exchange"),
        SavedStop(stop_id="00303B", title="WTC - To Marina"),
        SavedStop(stop_id="00303A", title="WTC - From Marina"),
    ),
    weather_latitude=24.4539,
    weather_longitude=54.3773,
    weather_location_label="Abu Dhabi",
    headline_feed_urls=(
        "https://news.google.com/rss/search?q=site:thenationalnews.com+(UAE+OR+Abu+Dhabi+OR+Dubai)+when:1d&hl=en-AE&gl=AE&ceid=AE:en",
        "https://news.google.com/rss/search?q=site:reuters.com+(UAE+OR+Abu+Dhabi+OR+Dubai+OR+Gulf+OR+Middle+East)+when:1d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=site:wam.ae+(UAE+OR+Abu+Dhabi)+when:1d&hl=en-AE&gl=AE&ceid=AE:en",
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://indianexpress.com/section/india/feed/",
    ),
    headline_cache_ttl_minutes=60,
    output_dir=OUTPUT_DIR,
    frame_output_dir=OUTPUT_DIR / "frames",
    demo_output_dir=OUTPUT_DIR / "demo_runs",
    cache_dir=OUTPUT_DIR / "cache",
    darbi_map_url="https://darbi.itc.gov.ae/darbweb/map-viewer.html",
    darbi_user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    ),
)
