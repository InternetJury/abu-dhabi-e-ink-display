from datetime import datetime
from zoneinfo import ZoneInfo

from ribbon.models import HeadlineItem
from ribbon.providers.headlines_rss import HeadlineCandidate, RSSHeadlineProvider


TZ = ZoneInfo("Asia/Dubai")


def test_headline_selection_guarantees_one_india_story_when_available():
    candidates = [
        HeadlineCandidate(
            item=HeadlineItem(
                title="UAE cabinet approves new industrial plan",
                source_name="Reuters",
                url="https://www.reuters.com/world/middle-east",
                published_at=datetime(2026, 4, 4, 20, 0, tzinfo=TZ),
            ),
            region="uae",
            priority=0,
        ),
        HeadlineCandidate(
            item=HeadlineItem(
                title="India parliament passes emergency fiscal relief package",
                source_name="The Hindu",
                url="https://www.thehindu.com/news/national/",
                published_at=datetime(2026, 4, 4, 19, 0, tzinfo=TZ),
            ),
            region="india",
            priority=2,
        ),
        HeadlineCandidate(
            item=HeadlineItem(
                title="Abu Dhabi launches new logistics corridor",
                source_name="The National",
                url="https://www.thenationalnews.com/uae/",
                published_at=datetime(2026, 4, 4, 18, 30, tzinfo=TZ),
            ),
            region="uae",
            priority=0,
        ),
    ]

    selected = RSSHeadlineProvider._select_headlines(candidates, limit=3)
    titles = [item.title for item in selected]
    assert any("India parliament" in title for title in titles)


def test_headline_source_filter_blocks_low_quality_and_non_allowlisted_sources():
    assert RSSHeadlineProvider._canonical_source_name("Reuters World News", "https://www.reuters.com/world") == "Reuters"
    assert RSSHeadlineProvider._canonical_source_name("NDTV", "https://www.ndtv.com") is None
    assert RSSHeadlineProvider._is_blocked_source("MSN") is True
    assert RSSHeadlineProvider._is_clickbait("Celebrity live updates and viral photos") is True
