from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ribbon.models import BusDepartureItem
from ribbon.providers.base import BusProvider, ProviderError
from ribbon.settings import SETTINGS, SavedStop


DARBI_TZ = ZoneInfo(SETTINGS.timezone)
MMJPV5_URL_PREFIX = (
    "https://darbi.itc.gov.ae/dotservices/proxyAPI/proxy.ashx?"
    "https://darbi.itc.gov.ae/dotservices/api/MMJPv5/BusStopDepartureBoard?"
)


@dataclass
class DarbiFetchStatus:
    stop_id: str
    source: str = "unavailable"
    internal_stop_id: str | None = None
    resolved_stop_name: str | None = None
    fetched_at: datetime | None = None
    cached_at: datetime | None = None
    used_cache: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def note(self) -> str | None:
        if self.used_cache and self.cached_at is not None:
            return (
                f"Using cached Darbi departures from "
                f"{self.cached_at.astimezone(DARBI_TZ).strftime('%H:%M')}"
            )
        return None


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _parse_datetime(value: Any, now: datetime) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=DARBI_TZ)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=DARBI_TZ)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.endswith("Z"):
            stripped = stripped.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(stripped)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=DARBI_TZ)
            return parsed.astimezone(DARBI_TZ)
        except ValueError:
            pass
        if ":" in stripped and len(stripped) <= 5:
            hours, minutes = stripped.split(":")
            parsed = now.replace(hour=int(hours), minute=int(minutes), second=0, microsecond=0)
            if parsed < now - timedelta(hours=6):
                parsed += timedelta(days=1)
            return parsed
    return None


def _normalize_stop_code(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip().upper()


def _clean_destination(value: str) -> str:
    normalized = " ".join(str(value or "").replace("<", " / ").split())
    return normalized or "Unknown destination"


def _build_marker(item: dict[str, Any], delay_minutes: int | None) -> str | None:
    banner_info = item.get("bannerInfo") or []
    if isinstance(banner_info, list):
        banner_text = " | ".join(
            " ".join(
                str(message)
                for message in (
                    banner.get("message"),
                    banner.get("title"),
                    banner.get("description"),
                )
                if message
            ).strip()
            for banner in banner_info
            if isinstance(banner, dict)
        ).strip()
        if banner_text:
            return banner_text

    if item.get("isCancelled"):
        return "Cancelled"

    status_text = _pick(item, "marker", "status", "remark", "realtimeStatus")
    if status_text:
        text = str(status_text).strip()
        if text:
            return text

    if isinstance(delay_minutes, int) and delay_minutes > 2:
        return f"Delay +{delay_minutes}m"
    return None


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("Departures", "departures", "data", "items", "Services", "results", "Result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _extract_items(value)
                if nested:
                    return nested
    return []


def filter_departures_for_stop(raw_items: list[dict[str, Any]], stop_id: str) -> list[dict[str, Any]]:
    requested = _normalize_stop_code(stop_id)
    exact_matches = []
    for item in raw_items:
        stop_payload = item.get("Stop", {}) if isinstance(item.get("Stop"), dict) else {}
        raw_stop_id = _normalize_stop_code(
            _pick(
                stop_payload,
                "StopID",
                "stopId",
                "DisplayId",
                "displayID",
                "DisplayID",
            )
        )
        if not raw_stop_id and "platform" in stop_payload and _pick(stop_payload, "Id"):
            raw_stop_id = _normalize_stop_code(stop_payload.get("Id"))
        if raw_stop_id == requested:
            exact_matches.append(item)
    return exact_matches or raw_items


def normalize_darbi_departures(
    raw_items: list[dict[str, Any]],
    stop: SavedStop,
    now: datetime,
    *,
    source: str,
) -> list[BusDepartureItem]:
    normalized: list[BusDepartureItem] = []
    for item in raw_items:
        line_payload = item.get("Line", {}) if isinstance(item.get("Line"), dict) else {}
        route_number = str(
            _pick(
                item,
                "route_number",
                "line",
                "PublishedLineName",
                "lineNo",
                "serviceNo",
                "route",
            )
            or _pick(line_payload, "Number", "LineNo", "line")
            or "?"
        )
        destination = _clean_destination(
            str(
                _pick(
                    item,
                    "destination",
                    "direction",
                    "DestinationName",
                    "Destination",
                    "aimed_destination_name",
                    "headsign",
                )
                or _pick(line_payload, "Destination", "Name")
                or "Unknown destination"
            )
        )
        scheduled_at = _parse_datetime(
            _pick(item, "scheduled_at", "scheduled_iso", "scheduledTime", "AimedDepartureTime", "time", "Time"),
            now,
        )
        expected_at = _parse_datetime(
            _pick(
                item,
                "expected_at",
                "expected_iso",
                "ExpectedDepartureTime",
                "ExpectedDepartureDateTime",
                "expectedTime",
                "Realtime",
            ),
            now,
        )
        if expected_at is None:
            expected_at = scheduled_at

        due_minutes = _pick(item, "due_minutes", "dueInMinutes", "DueMinutes", "due", "Remaining")
        if due_minutes is None and expected_at is not None:
            due_minutes = max(int((expected_at - now).total_seconds() // 60), 0)
        if isinstance(due_minutes, str) and due_minutes.lstrip("-").isdigit():
            due_minutes = int(due_minutes)
        if isinstance(due_minutes, float):
            due_minutes = int(due_minutes)

        delay_minutes = _pick(item, "delay_minutes", "delay", "delayMinutes", "delayTime")
        if delay_minutes is None and scheduled_at and expected_at:
            delay_minutes = int((expected_at - scheduled_at).total_seconds() // 60)
        if isinstance(delay_minutes, str) and delay_minutes.lstrip("-").isdigit():
            delay_minutes = int(delay_minutes)
        if isinstance(delay_minutes, float):
            delay_minutes = int(delay_minutes)

        is_live = bool(_pick(item, "is_live", "isRealtime", "realtime", "live", "IsRealtime"))
        marker = _build_marker(item, delay_minutes if isinstance(delay_minutes, int) else None)

        normalized.append(
            BusDepartureItem(
                stop_id=stop.stop_id,
                stop_title=stop.title,
                route_number=route_number,
                destination=destination,
                scheduled_at=scheduled_at,
                expected_at=expected_at,
                due_minutes=due_minutes if isinstance(due_minutes, int) else None,
                is_live=is_live,
                delay_minutes=delay_minutes if isinstance(delay_minutes, int) else None,
                marker=marker,
                source=source,
            )
        )
    return sorted(
        normalized,
        key=lambda item: item.expected_at or item.scheduled_at or now + timedelta(days=1),
    )


class DarbiBusProvider(BusProvider):
    def __init__(self, timeout_seconds: int = 20, use_browser_fallback: bool = True) -> None:
        self.timeout_seconds = timeout_seconds
        self.use_browser_fallback = use_browser_fallback
        self.cache_path = SETTINGS.cache_dir / "bus_departures.json"
        self.rca_log_path = SETTINGS.cache_dir / "darbi_rca.jsonl"
        self._last_status: dict[str, DarbiFetchStatus] = {}

    def get_last_status(self, stop_id: str) -> DarbiFetchStatus | None:
        return self._last_status.get(stop_id)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": SETTINGS.darbi_user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": SETTINGS.darbi_map_url,
            "Origin": "https://darbi.itc.gov.ae",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _query_url(self, text: str, info: str | None = None) -> str:
        query = httpx.QueryParams(
            {
                "text": text,
                "direct": "true",
                "info": info or "",
                "limit": 0,
                "language": "en",
            }
        )
        return f"{MMJPV5_URL_PREFIX}&{query}"

    def _read_cache_payload(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _read_cached_departures(
        self,
        stop: SavedStop,
    ) -> tuple[list[BusDepartureItem], datetime | None, str | None, str | None]:
        payload = self._read_cache_payload().get(stop.stop_id)
        if not isinstance(payload, dict):
            return [], None, None, None
        items = [BusDepartureItem.model_validate(item) for item in payload.get("items", [])]
        fetched_at = None
        if payload.get("fetched_at"):
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
        return items, fetched_at, payload.get("internal_stop_id"), payload.get("stop_name")

    def _write_cache(
        self,
        stop: SavedStop,
        departures: list[BusDepartureItem],
        fetched_at: datetime,
        *,
        internal_stop_id: str | None,
        stop_name: str | None,
    ) -> None:
        SETTINGS.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = self._read_cache_payload()
        payload[stop.stop_id] = {
            "fetched_at": fetched_at.isoformat(),
            "internal_stop_id": internal_stop_id,
            "stop_name": stop_name,
            "items": [item.model_dump(mode="json") for item in departures],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _append_rca_log(self, status: DarbiFetchStatus) -> None:
        SETTINGS.cache_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "stop_id": status.stop_id,
            "source": status.source,
            "internal_stop_id": status.internal_stop_id,
            "resolved_stop_name": status.resolved_stop_name,
            "fetched_at": status.fetched_at.isoformat() if status.fetched_at else None,
            "cached_at": status.cached_at.isoformat() if status.cached_at else None,
            "used_cache": status.used_cache,
            "attempts": status.attempts,
        }
        with self.rca_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _attempt(
        self,
        status: DarbiFetchStatus,
        *,
        stage: str,
        url: str,
        response_status: int | None = None,
        message: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"stage": stage, "url": url}
        if response_status is not None:
            payload["status"] = response_status
        if message:
            payload["message"] = message
        status.attempts.append(payload)

    def _fetch_mmjpv5_payload(self, text: str, info: str | None = None) -> tuple[str, dict[str, Any]]:
        url = self._query_url(text, info)
        response = httpx.get(url, headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError(f"Darbi MMJPv5 returned non-object payload for {text}")
        return url, payload

    def _fetch_browser_departures(self, stop: SavedStop, now: datetime) -> list[BusDepartureItem]:
        from ribbon.providers.bus_playwright import DarbiPlaywrightBusProvider

        provider = DarbiPlaywrightBusProvider(timeout_seconds=self.timeout_seconds)
        return provider.fetch_stop(stop, now)

    def fetch_stop(self, stop: SavedStop, now: datetime) -> list[BusDepartureItem]:
        status = DarbiFetchStatus(stop_id=stop.stop_id)
        cached_items, cached_at, cached_internal_id, cached_stop_name = self._read_cached_departures(stop)

        try:
            url, payload = self._fetch_mmjpv5_payload(stop.stop_id)
            raw_items = filter_departures_for_stop(_extract_items(payload), stop.stop_id)
            normalized = normalize_darbi_departures(raw_items, stop, now, source="darbi-mmjpv5")
            if normalized:
                sample_stop = raw_items[0].get("Stop", {}) if raw_items else {}
                status.source = "darbi-mmjpv5-stop-code"
                status.internal_stop_id = str(_pick(sample_stop, "Id") or cached_internal_id or "")
                status.internal_stop_id = status.internal_stop_id or None
                status.resolved_stop_name = str(_pick(sample_stop, "Name") or cached_stop_name or "") or None
                status.fetched_at = now
                self._last_status[stop.stop_id] = status
                self._append_rca_log(status)
                self._write_cache(
                    stop,
                    normalized,
                    now,
                    internal_stop_id=status.internal_stop_id,
                    stop_name=status.resolved_stop_name,
                )
                return normalized
            self._attempt(status, stage="direct-no-matching-departures", url=url, response_status=200)
        except Exception as exc:
            message = str(exc)
            response_status = getattr(getattr(exc, "response", None), "status_code", None)
            self._attempt(
                status,
                stage="direct-stop-code-failed",
                url=self._query_url(stop.stop_id),
                response_status=response_status,
                message=message,
            )

        if cached_internal_id:
            try:
                url, payload = self._fetch_mmjpv5_payload(cached_internal_id)
                raw_items = filter_departures_for_stop(_extract_items(payload), stop.stop_id)
                normalized = normalize_darbi_departures(raw_items, stop, now, source="darbi-mmjpv5-internal")
                if normalized:
                    sample_stop = raw_items[0].get("Stop", {}) if raw_items else {}
                    status.source = "darbi-mmjpv5-internal-id"
                    status.internal_stop_id = cached_internal_id
                    status.resolved_stop_name = str(_pick(sample_stop, "Name") or cached_stop_name or "") or None
                    status.fetched_at = now
                    self._last_status[stop.stop_id] = status
                    self._append_rca_log(status)
                    self._write_cache(
                        stop,
                        normalized,
                        now,
                        internal_stop_id=status.internal_stop_id,
                        stop_name=status.resolved_stop_name,
                    )
                    return normalized
                self._attempt(status, stage="internal-id-no-matching-departures", url=url, response_status=200)
            except Exception as exc:
                self._attempt(
                    status,
                    stage="internal-id-failed",
                    url=self._query_url(cached_internal_id),
                    response_status=getattr(getattr(exc, "response", None), "status_code", None),
                    message=str(exc),
                )

        if self.use_browser_fallback:
            try:
                normalized = self._fetch_browser_departures(stop, now)
                if normalized:
                    status.source = "darbi-browser-xhr"
                    status.fetched_at = now
                    self._last_status[stop.stop_id] = status
                    self._append_rca_log(status)
                    self._write_cache(
                        stop,
                        normalized,
                        now,
                        internal_stop_id=cached_internal_id,
                        stop_name=cached_stop_name,
                    )
                    return normalized
            except Exception as exc:
                self._attempt(
                    status,
                    stage="browser-fallback-failed",
                    url=SETTINGS.darbi_map_url,
                    message=str(exc),
                )

        if cached_items:
            status.source = "darbi-cache"
            status.used_cache = True
            status.cached_at = cached_at
            status.internal_stop_id = cached_internal_id
            status.resolved_stop_name = cached_stop_name
            self._last_status[stop.stop_id] = status
            self._append_rca_log(status)
            return cached_items

        self._last_status[stop.stop_id] = status
        self._append_rca_log(status)
        raise ProviderError(f"Darbi live feed unavailable for {stop.stop_id}")
