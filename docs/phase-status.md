# Phase Status

## Phase 1: Complete

Phase 1 is complete for the intended product surface.

Completed:

- final locked templates for all three modes
- PNG-first renderer
- live Darbi integration with fallback strategy
- weather, AQI, headlines, and market context
- scheduler and preview flows
- tests and curated preview outputs
- Stitch handoff documentation

Not required before public release:

- backend redesign
- schema redesign
- additional template work

## Phase 2: Device Runtime Implemented

The device-runtime implementation is now present without changing the locked templates.

Implemented:

- Geekom A6 minute-aligned render/publish loop
- atomic SSH/SCP transfer with a dedicated local key
- publisher watchdog and bounded frame/log retention
- Raspberry Pi `systemd` display client
- Waveshare 10.85-inch B/W dual-controller adapter
- stale/off-minute frame rejection before hardware initialization
- mandatory full refresh after service restart
- safe panel sleep after idle or service shutdown
- private Telegram status and confirmed-shutdown control

Current deployment acceptance status:

- Pi display service and both panel halves have been verified with clean full-frame output
- minute-aligned weekend/ambient alternation has been verified using the production publisher script
- installation of the hardened publisher/watchdog and Telegram tasks on the target A6 is still pending remote SSH access
- final A6-to-Pi shutdown, cold-boot recovery, and multi-minute soak must be repeated after that target installation

Optional future improvements:

- qualify dual-controller partial refresh separately; production currently uses full-frame refresh for reliability
- broader telemetry and alerting
- packaged installers/releases for additional target devices
- fully externalized application settings

## Backend Assessment

No immediate backend change is required for the current public release.

Possible future backend improvements:

- more durable persistence for last-good boards
- richer provider health telemetry
- additional source resilience and fallback ranking
- environment/config driven settings instead of code constants
