# Contributing

Thanks for your interest in improving the Abu Dhabi E-Ink Display project.

## Ground Rules

- Treat the current three templates as locked unless a new design phase explicitly reopens them.
- Keep the project PNG-first unless a new hardware phase is being worked intentionally.
- Prefer changes that preserve test coverage and deterministic rendering.

## Local Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m pytest
```

Optional browser fallback setup:

```powershell
.\.venv\Scripts\python -m playwright install chromium
```

## Common Checks

- run `python -m pytest`
- re-render the canonical fixture boards when changing renderer behavior
- do not commit cache output or transient demo-run folders

## Design / Artifact Policy

- keep only curated final preview PNGs in `output/frames`
- keep only the approved Stitch export set in `design/stitch_exports`
- do not reintroduce intermediate or obsolete render artifacts into the public repo

## Pull Requests

- explain whether the change affects:
  - provider behavior
  - scheduler behavior
  - renderer layout
  - public documentation
- call out any render-regression baseline changes explicitly
