from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from time import mktime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser

from ribbon.models import HeadlineItem
from ribbon.providers.base import HeadlineProvider, ProviderError
from ribbon.settings import SETTINGS


LOCAL_TZ = ZoneInfo(SETTINGS.timezone)
CACHE_VERSION = 3


@dataclass(frozen=True)
class FeedProfile:
    url: str
    region: str
    priority: int


@dataclass(frozen=True)
class HeadlineCandidate:
    item: HeadlineItem
    region: str
    priority: int


ALLOWLIST = {
    "reuters": "Reuters",
    "the national": "The National",
    "wam": "WAM",
    "the hindu": "The Hindu",
    "the indian express": "The Indian Express",
    "indian express": "The Indian Express",
}

BLOCKED_SOURCE_FRAGMENTS = (
    "fair observer",
    "msn",
    "ms now",
    "opindia",
    "free press journal",
    "filmibeat",
    "times now",
    "news18",
    "india today",
)

BLOCKED_TITLE_FRAGMENTS = (
    "live updates",
    "horoscope",
    "celebrity",
    "movie",
    "box office",
    "cricket live",
    "photos",
    "photo gallery",
    "viral",
    "trending",
    "opinion:",
)

INDIA_KEYWORDS = (
    "india",
    "indian",
    "new delhi",
    "delhi",
    "mumbai",
    "supreme court",
    "parliament",
    "defence",
)

UAE_KEYWORDS = (
    "uae",
    "abu dhabi",
    "dubai",
    "emirates",
    "gulf",
    "middle east",
    "zayed",
)


class RSSHeadlineProvider(HeadlineProvider):
    def __init__(self, feed_urls: tuple[str, ...] | None = None) -> None:
        urls = feed_urls or SETTINGS.headline_feed_urls
        self.feed_profiles = self._build_profiles(urls)
        self.cache_path = SETTINGS.cache_dir / "headlines.json"

    @staticmethod
    def _build_profiles(urls: tuple[str, ...]) -> tuple[FeedProfile, ...]:
        profiles: list[FeedProfile] = []
        for url in urls:
            lower = url.lower()
            if "thehindu.com" in lower or "indianexpress.com" in lower:
                region = "india"
                priority = 2
            elif "thenationalnews.com" in lower or "wam.ae" in lower:
                region = "uae"
                priority = 0
            elif "reuters.com" in lower:
                region = "uae"
                priority = 1
            else:
                region = "global"
                priority = 3
            profiles.append(FeedProfile(url=url, region=region, priority=priority))
        return tuple(profiles)

    def _write_cache(self, headlines: list[HeadlineItem]) -> None:
        SETTINGS.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "fetched_at": datetime.now(LOCAL_TZ).isoformat(),
            "items": [item.model_dump(mode="json") for item in headlines],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read_cache(self) -> tuple[datetime | None, list[HeadlineItem]]:
        if not self.cache_path.exists():
            raise ProviderError("No headline cache available")
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            raise ProviderError("Legacy headline cache no longer supported")
        if payload.get("version") != CACHE_VERSION:
            raise ProviderError("Outdated headline cache version")
        fetched_at = None
        if payload.get("fetched_at"):
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
        return fetched_at, [HeadlineItem.model_validate(item) for item in payload.get("items", [])]

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join((value or "").strip().split()).lower()

    @classmethod
    def _canonical_source_name(cls, source_name: str, link: str) -> str | None:
        source_norm = cls._normalize_text(source_name)
        link_norm = cls._normalize_text(urlparse(link).netloc)
        for fragment, canonical in ALLOWLIST.items():
            if fragment in source_norm or fragment in link_norm:
                return canonical
        return None

    @classmethod
    def _clean_title(cls, title: str, source_name: str) -> str:
        cleaned = " ".join((title or "").strip().split())
        suffix = f" - {source_name}"
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
        return cleaned

    @classmethod
    def _is_clickbait(cls, title: str) -> bool:
        title_norm = cls._normalize_text(title)
        return any(fragment in title_norm for fragment in BLOCKED_TITLE_FRAGMENTS)

    @classmethod
    def _is_blocked_source(cls, source_name: str) -> bool:
        source_norm = cls._normalize_text(source_name)
        return any(fragment in source_norm for fragment in BLOCKED_SOURCE_FRAGMENTS)

    @classmethod
    def _infer_region(cls, profile_region: str, title: str) -> str:
        title_norm = cls._normalize_text(title)
        if any(keyword in title_norm for keyword in INDIA_KEYWORDS):
            return "india"
        if any(keyword in title_norm for keyword in UAE_KEYWORDS):
            return "uae"
        return profile_region

    @staticmethod
    def _published_at(entry) -> datetime | None:
        if getattr(entry, "published_parsed", None):
            return datetime.fromtimestamp(mktime(entry.published_parsed), tz=LOCAL_TZ)
        if getattr(entry, "updated_parsed", None):
            return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=LOCAL_TZ)
        return None

    def _fresh_cache(self) -> list[HeadlineItem] | None:
        try:
            fetched_at, headlines = self._read_cache()
        except ProviderError:
            return None
        if fetched_at is None:
            return None
        age_seconds = (datetime.now(LOCAL_TZ) - fetched_at.astimezone(LOCAL_TZ)).total_seconds()
        if age_seconds <= SETTINGS.headline_cache_ttl_minutes * 60:
            return headlines
        return None

    def _collect_candidates(self) -> list[HeadlineCandidate]:
        candidates: list[HeadlineCandidate] = []
        seen: set[str] = set()

        for profile in self.feed_profiles:
            parsed = feedparser.parse(profile.url)
            if getattr(parsed, "bozo", 0):
                continue
            for entry in parsed.entries[:30]:
                link = entry.get("link", "").strip()
                raw_source = (entry.get("source", {}) or {}).get("title") or parsed.feed.get("title", "Feed")
                canonical_source = self._canonical_source_name(raw_source, link)
                if canonical_source is None or self._is_blocked_source(canonical_source):
                    continue

                title = self._clean_title(entry.get("title", ""), canonical_source)
                if not title or self._is_clickbait(title):
                    continue

                key = self._normalize_text(title)
                if key in seen:
                    continue
                seen.add(key)

                published_at = self._published_at(entry)
                item = HeadlineItem(
                    title=title,
                    source_name=canonical_source,
                    url=link,
                    published_at=published_at,
                )
                candidates.append(
                    HeadlineCandidate(
                        item=item,
                        region=self._infer_region(profile.region, title),
                        priority=profile.priority,
                    )
                )
        return candidates

    @classmethod
    def _candidate_score(cls, candidate: HeadlineCandidate) -> tuple[int, int, float]:
        source_rank = {
            "Reuters": 0,
            "The National": 1,
            "WAM": 2,
            "The Hindu": 3,
            "The Indian Express": 4,
        }.get(candidate.item.source_name, 9)
        published = candidate.item.published_at.timestamp() if candidate.item.published_at else 0.0
        return (candidate.priority, source_rank, -published)

    @classmethod
    def _select_headlines(cls, candidates: list[HeadlineCandidate], limit: int) -> list[HeadlineItem]:
        ranked = sorted(candidates, key=cls._candidate_score)
        selected: list[HeadlineCandidate] = []
        used_titles: set[str] = set()

        india_candidates = [candidate for candidate in ranked if candidate.region == "india"]
        if india_candidates:
            selected.append(india_candidates[0])
            used_titles.add(cls._normalize_text(india_candidates[0].item.title))

        uae_candidates = [candidate for candidate in ranked if candidate.region == "uae"]
        for candidate in uae_candidates:
            if len(selected) >= limit:
                break
            title_key = cls._normalize_text(candidate.item.title)
            if title_key in used_titles:
                continue
            selected.append(candidate)
            used_titles.add(title_key)

        for candidate in ranked:
            if len(selected) >= limit:
                break
            title_key = cls._normalize_text(candidate.item.title)
            if title_key in used_titles:
                continue
            selected.append(candidate)
            used_titles.add(title_key)

        ordered = sorted(
            selected[:limit],
            key=lambda candidate: candidate.item.published_at or datetime.min.replace(tzinfo=LOCAL_TZ),
            reverse=True,
        )
        india_index = next((index for index, candidate in enumerate(ordered) if candidate.region == "india"), None)
        protected_index = min(4, max(0, limit - 1))
        if india_index is not None and india_index > protected_index:
            india_candidate = ordered.pop(india_index)
            ordered.insert(protected_index, india_candidate)
        return [candidate.item for candidate in ordered]

    def fetch(self, limit: int = 6) -> list[HeadlineItem]:
        cached = self._fresh_cache()
        if cached:
            return cached[:limit]

        candidates = self._collect_candidates()
        if not candidates:
            try:
                _, cached_items = self._read_cache()
                return cached_items[:limit]
            except ProviderError as exc:
                raise ProviderError("No curated headlines available from any configured feed") from exc

        headlines = self._select_headlines(candidates, max(limit, 6))
        self._write_cache(headlines)
        return headlines[:limit]
