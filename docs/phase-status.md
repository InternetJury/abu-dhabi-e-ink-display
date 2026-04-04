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

## Phase 2: Optional

Phase 2 is only needed if you want to move from a polished PNG-first project to an operational device deployment.

Candidate Phase 2 work:

- hardware / panel driver integration
- partial/full refresh orchestration for the target e-ink panel
- Raspberry Pi runtime service or daemon packaging
- settings externalization and deployment configuration
- stronger observability and operational hardening
- packaging/distribution instructions for target hardware

## Backend Assessment

No immediate backend change is required for the current public release.

Possible future backend improvements:

- more durable persistence for last-good boards
- richer provider health telemetry
- additional source resilience and fallback ranking
- environment/config driven settings instead of code constants
