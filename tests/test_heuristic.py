from __future__ import annotations

from datetime import datetime

from news_agent.filters.heuristic import heuristic_prefilter
from news_agent.models.item import ContentItem, EngagementSignals


def test_prefilter_short_text_dropped():
    it = ContentItem(
        id="1",
        source_type="rss",
        source_id="s",
        url="https://example.com",
        title="x",
        body_text="short",
        published_at=datetime.utcnow(),
        engagement=EngagementSignals(),
        normalized_text="short",
        body_fingerprint="fp",
    )
    assert heuristic_prefilter(it, {"min_text_length": 40}) is False


def test_prefilter_passes():
    text = "This is a substantive update about a new model release with benchmarks."
    it = ContentItem(
        id="1",
        source_type="rss",
        source_id="s",
        url="https://example.com",
        title="x",
        body_text=text,
        published_at=datetime.utcnow(),
        engagement=EngagementSignals(),
        normalized_text=text,
        body_fingerprint="fp2",
    )
    assert heuristic_prefilter(it, {"min_text_length": 40}) is True
