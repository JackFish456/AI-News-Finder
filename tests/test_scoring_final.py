from __future__ import annotations

from news_agent.models.item import ContentItem, EngagementSignals
from news_agent.models.scoring import ItemScores
from news_agent.scoring.final import compute_final_score, resolve_source_weight


def test_resolve_source_weight_prefers_feed_key():
    it = ContentItem(
        id="1",
        source_type="rss",
        source_id="s",
        url="https://example.com",
        body_text="x",
        published_at=None,
        engagement=EngagementSignals(),
        credibility_meta={"feed_weight_key": "rss_reuters"},
        normalized_text="x",
        body_fingerprint="fp",
    )
    w = resolve_source_weight(
        it,
        {"rss_reuters": 1.1, "rss": 1.0, "default": 0.9},
    )
    assert w == 1.1


def test_compute_final_score_penalizes_hype():
    s = ItemScores(
        importance_score=80,
        credibility_score=80,
        novelty_score=80,
        substance_score=80,
        hype_penalty=80,
        ai_slop_penalty=0,
    )
    base = compute_final_score(s, 1.0)
    low_hype = compute_final_score(
        ItemScores(
            importance_score=80,
            credibility_score=80,
            novelty_score=80,
            substance_score=80,
            hype_penalty=10,
            ai_slop_penalty=0,
        ),
        1.0,
    )
    assert base < low_hype
