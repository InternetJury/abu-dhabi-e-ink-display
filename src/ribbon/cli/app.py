from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from ribbon.derive.builder import build_live_snapshot
from ribbon.fixtures import load_fixture_snapshot, list_fixture_names
from ribbon.models import ModeName
from ribbon.providers import (
    ChainedBusProvider,
    DarbiBusProvider,
    DarbiPlaywrightBusProvider,
    FixtureBusProvider,
    FixtureHeadlineProvider,
    FixtureMarketProvider,
    FixtureWeatherProvider,
    CompositeMarketProvider,
    OpenMeteoWeatherProvider,
    RSSHeadlineProvider,
)
from ribbon.render import RibbonRenderer
from ribbon.scheduler import compute_refresh_hint, select_mode, snapshot_signature
from ribbon.settings import SETTINGS, SavedStop


app = typer.Typer(no_args_is_help=True)


def _now() -> datetime:
    return datetime.now(ZoneInfo(SETTINGS.timezone))


def _output_path(name: str) -> Path:
    SETTINGS.frame_output_dir.mkdir(parents=True, exist_ok=True)
    return SETTINGS.frame_output_dir / name


@app.command("list-fixtures")
def list_fixtures() -> None:
    for name in list_fixture_names():
        typer.echo(name)


@app.command("render-fixture")
def render_fixture(
    fixture_name: str = typer.Argument(...),
    output: Path | None = typer.Option(None),
    weekend_center_stop_names: bool = typer.Option(True),
) -> None:
    snapshot = load_fixture_snapshot(fixture_name)
    default_name = f"{fixture_name}.png"
    path = output or _output_path(default_name)
    renderer = RibbonRenderer(center_weekend_stop_names=weekend_center_stop_names)
    renderer.render_to_path(snapshot, path)
    typer.echo(str(path))


@app.command("probe-provider")
def probe_provider(
    stop_id: str = typer.Option("00513B"),
    stop_title: str = typer.Option("Aster Pharmacy"),
    use_playwright_fallback: bool = typer.Option(False),
) -> None:
    bus_provider = DarbiBusProvider()
    if use_playwright_fallback:
        bus_provider = ChainedBusProvider(DarbiBusProvider(), DarbiPlaywrightBusProvider())
    departures = bus_provider.fetch_stop(SavedStop(stop_id, stop_title), _now())
    typer.echo(json.dumps([item.model_dump(mode="json") for item in departures[:6]], indent=2))


@app.command("render-live")
def render_live(
    mode: ModeName | None = typer.Option(None, help="Optional explicit mode override. Defaults to scheduler selection."),
    output: Path | None = typer.Option(None),
    use_playwright_fallback: bool = typer.Option(False),
) -> None:
    now = _now()
    active_mode = mode or select_mode(now)
    bus_provider = DarbiBusProvider()
    if use_playwright_fallback:
        bus_provider = ChainedBusProvider(DarbiBusProvider(), DarbiPlaywrightBusProvider())
    snapshot = build_live_snapshot(
        mode=active_mode,
        now=now,
        refresh_hint=compute_refresh_hint(now, active_mode, previous_mode=active_mode),
        bus_provider=bus_provider,
        weather_provider=OpenMeteoWeatherProvider(),
        headline_provider=RSSHeadlineProvider(),
        market_provider=CompositeMarketProvider(),
    )
    path = output or _output_path(f"live-{active_mode.value}.png")
    RibbonRenderer().render_to_path(snapshot, path)
    typer.echo(str(path))


@app.command("render-fixture-live-shape")
def render_fixture_live_shape(
    fixture_name: str = typer.Argument(...),
    output: Path | None = typer.Option(None),
) -> None:
    now = _now()
    base_snapshot = load_fixture_snapshot(fixture_name)
    snapshot = build_live_snapshot(
        mode=base_snapshot.mode,
        now=now,
        refresh_hint=base_snapshot.refresh_hint,
        bus_provider=FixtureBusProvider(fixture_name),
        weather_provider=FixtureWeatherProvider(fixture_name),
        headline_provider=FixtureHeadlineProvider(fixture_name),
        market_provider=FixtureMarketProvider(fixture_name),
    )
    current_signature = snapshot_signature(snapshot)
    snapshot = snapshot.model_copy(
        update={
            "refresh_hint": compute_refresh_hint(
                now,
                snapshot.mode,
                previous_mode=snapshot.mode,
                previous_signature=current_signature,
                current_signature=current_signature,
            )
        }
    )
    path = output or _output_path(f"{fixture_name}-live-shape.png")
    RibbonRenderer().render_to_path(snapshot, path)
    typer.echo(str(path))


@app.command("demo-run")
def demo_run(
    minutes: int = typer.Option(2, min=1),
    sleep_seconds: int = typer.Option(60, min=0),
    use_playwright_fallback: bool = typer.Option(False),
) -> None:
    start = _now()
    output_dir = SETTINGS.demo_output_dir / start.strftime("%Y%m%d-%H%M")
    output_dir.mkdir(parents=True, exist_ok=True)

    bus_provider = DarbiBusProvider()
    if use_playwright_fallback:
        bus_provider = ChainedBusProvider(DarbiBusProvider(), DarbiPlaywrightBusProvider())
    weather_provider = OpenMeteoWeatherProvider()
    headline_provider = RSSHeadlineProvider()
    market_provider = CompositeMarketProvider()
    renderer = RibbonRenderer(center_weekend_stop_names=True)
    modes = [
        ModeName.WEEKDAY_COMMUTE_NOW,
        ModeName.WEEKEND_MULTI_STOP,
        ModeName.AMBIENT_INFO,
    ]

    for minute_index in range(minutes):
        now = _now()
        for mode in modes:
            snapshot = build_live_snapshot(
                mode=mode,
                now=now,
                refresh_hint=compute_refresh_hint(now, mode, previous_mode=mode),
                bus_provider=bus_provider,
                weather_provider=weather_provider,
                headline_provider=headline_provider,
                market_provider=market_provider,
            )
            path = output_dir / f"minute-{minute_index:02d}-{mode.value}.png"
            renderer.render_to_path(snapshot, path)
            typer.echo(str(path))
        if minute_index < minutes - 1 and sleep_seconds:
            time.sleep(sleep_seconds)

    typer.echo(str(output_dir))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
