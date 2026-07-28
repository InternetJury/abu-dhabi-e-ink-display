# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Fixed

- close each decoded PNG source and processed image so the always-on Pi display client cannot exhaust file descriptors
- terminate on descriptor exhaustion or repeated display-loop failures so `systemd` can restart with a startup clear and full refresh
- resolve and locally cache the Pi IPv4 target on the A6 to avoid intermittent `.local`/mDNS failures in the Windows `SYSTEM` publisher task

## [0.2.0] - 2026-07-26

### Added

- Geekom A6 installation, minute-aligned render/publish loop, and startup task
- publisher watchdog for apparently running but stale render processes
- current-frame-only storage and bounded log retention
- Raspberry Pi `systemd` display client with process locking and rotating logs
- atomic `.tmp` to `current.png` transfer with render-time preservation
- stale, previous-minute, and late-frame rejection before panel initialization
- mandatory full-frame refresh after restart and clean panel sleep on idle/shutdown
- Waveshare 10.85-inch B/W dual-controller adapter with row-safe master/slave buffer splitting
- guarded full-screen panel verification utility and recovery runbook
- private Telegram status and confirmed-shutdown bot with local-only credentials and numeric user-ID allowlisting

### Security

- dedicated A6-to-Pi SSH identity and private known-hosts file
- A6 secrets directory restricted to `SYSTEM` and the installing administrator
- Telegram commands from unauthorized users are ignored without operational responses once the allowlist is configured
- Telegram logs rotate and record bounded rejection counters rather than message bodies

### Changed

- full-frame e-paper refresh is the production default while dual-controller partial refresh remains quarantined
- A6 publisher and Telegram tasks run as `SYSTEM` at startup without requiring interactive login
- deployment documentation now reflects the implemented hardware runtime and remaining target-device acceptance work

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

- Phase 1 is PNG-first and remains independent of hardware.
- Device integration was added in `0.2.0` without changing the locked templates.
