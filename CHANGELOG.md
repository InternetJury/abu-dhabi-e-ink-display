# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-04-05

Initial public release.

### Added

- greenfield Python project for a `1360x480` monochrome mobility ribbon
- three locked product modes:
  - `weekday_commute_now`
  - `weekend_multi_stop`
  - `ambient_info`
- normalized models for departures, weather, headlines, markets, and ribbon snapshots
- scheduler with 60-second render cadence and mode rotation rules
- Darbi live provider with MMJPv5 direct fetch, browser/XHR recovery path, and last-good fallback
- Open-Meteo weather and AQI provider
- curated RSS headline pipeline with UAE-first ranking and an India guaranteed slot
- NIFTY and S&P 500 market provider integration
- locked PNG renderer adapted from approved Google Stitch exports
- review-only uniform delay preview generation
- fixture corpus and regression tests

### Documentation

- public README with setup, commands, status, and preview images
- architecture notes
- phase-status / backend-status summary
- Darbi RCA documentation
- curated Stitch handoff and design notes

### Notes

- Phase 1 is PNG-first only.
- Hardware integration and device runtime are intentionally deferred to a later phase.
