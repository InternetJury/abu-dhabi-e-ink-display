# Architecture

## Overview

The project renders a monochrome Abu Dhabi mobility ribbon as a PNG sized exactly `1360x480`. The pipeline is:

1. providers fetch bus, weather, AQI, headline, and market data
2. the builder normalizes that into a `RibbonSnapshot`
3. the scheduler chooses the active mode and refresh hint
4. the renderer turns the snapshot into a locked PNG layout
5. optional preview transforms create review-only comparison boards

## Main Subsystems

### Providers

- `DarbiBusProvider`
  - primary live source using Darbi MMJPv5 stop search
  - exact stop-code filtering
  - structured RCA logging and last-good cache fallback
- `DarbiPlaywrightBusProvider`
  - browser/XHR recovery path
- `OpenMeteoWeatherProvider`
  - current weather, AQI, sunrise, sunset, daily high/low
- `RSSHeadlineProvider`
  - curated UAE-first headlines with one India slot when available
- `CompositeMarketProvider`
  - NIFTY + S&P 500 compact market summary

### Derivation

`build_live_snapshot()` assembles the current mode-specific ribbon snapshot and carries degraded notes when upstream providers fail.

### Scheduler

The scheduler is time-zone aware (`Asia/Dubai`) and currently uses a 60-second render cadence with:

- weekday commute window
- weekend one-minute alternation between multi-stop mode and ambient mode
- ambient mode outside the commute priority window

Provider caches are intentionally independent of the screen cadence: weather/AQI refreshes every 10 minutes, markets every 15 minutes, and curated headlines every 30 minutes. Each minute render uses the newest available cached data and preserves last-good values when an upstream source is temporarily unavailable.

### Renderer

The renderer is a Pillow-based locked-layout system with vendored fonts and Material Symbols. It follows approved Stitch exports and treats them as source-of-truth design references, not loose inspiration.

### Preview Layer

`preview.py` provides transient review-only transforms, such as the all-delay comparison render, without mutating canonical fixtures or live provider behavior.

## Output Policy

The public repo includes only:

- canonical final preview PNGs
- selected live preview PNGs
- review-only comparison previews
- curated approved Stitch export artifacts

Cache output and transient demo runs remain out of the public repo.
