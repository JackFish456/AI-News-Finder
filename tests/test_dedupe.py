from __future__ import annotations

from datetime import datetime

from news_agent.filters.dedupe import dedupe_by_fingerprint_and_url
from news_agent.models.item import ContentItem, EngagementSignals


def _item(i: int, url: str, fp: str, source_type: str = "rss") -> ContentItem:
    return ContentItem(
        id=str(i),
        source_type=source_type,
        source_id="test",
        url=url,
        title="t",
        body_text="body",
        published_at=datetime.utcnow(),
        engagement=EngagementSignals(),
        normalized_text="body",
        body_fingerprint=fp,
    )


def test_dedupe_drops_same_url():
    a = _item(1, "https://example.com/x?utm_source=a", "fp1")
    b = _item(2, "https://example.com/x?utm_source=b", "fp2")
    out = dedupe_by_fingerprint_and_url([a, b])
    assert len(out) == 1


def test_dedupe_drops_same_fingerprint():
    a = _item(1, "https://a.com/1", "same")
    b = _item(2, "https://b.com/2", "same")
    out = dedupe_by_fingerprint_and_url([a, b])
    assert len(out) == 1
