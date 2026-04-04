# Setup

## Requirements

- Python `3.11+`
- Windows PowerShell commands below assume the current project layout

## Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
```

## Optional Browser Fallback

Install Chromium for the Playwright Darbi recovery path:

```powershell
.\.venv\Scripts\python -m playwright install chromium
```

## Test

```powershell
.\.venv\Scripts\python -m pytest
```

## Render

Fixture renders:

```powershell
.\.venv\Scripts\mobility-ribbon render-fixture weekday_commute_now
.\.venv\Scripts\mobility-ribbon render-fixture weekend_multi_stop
.\.venv\Scripts\mobility-ribbon render-fixture ambient_info
```

Live render:

```powershell
.\.venv\Scripts\mobility-ribbon render-live
```

Demo run:

```powershell
.\.venv\Scripts\mobility-ribbon demo-run --minutes 2 --sleep-seconds 60
```
