from __future__ import annotations

from news_agent.models.cluster import StoryCluster
from news_agent.models.item import ContentItem, EngagementSignals
from news_agent.models.scoring import ItemScores
from news_agent.summarization.daily_brief import (
    BriefEntry,
    DailyBriefReport,
    apply_source_diversity_cap,
)


def _item(iid: str, source_id: str, score: float) -> ContentItem:
    sc = ItemScores(
        importance_score=50,
        credibility_score=50,
        novelty_score=50,
        substance_score=50,
        hype_penalty=10,
        ai_slop_penalty=10,
        importance_rationale="x",
        credibility_rationale="x",
        novelty_rationale="x",
        substance_rationale="x",
        hype_rationale="x",
        ai_slop_rationale="x",
        primary_category="other",
        llm_model=None,
        prompt_version="t",
        final_score=score,
    )
    return ContentItem(
        id=iid,
        source_type="rss",
        source_id=source_id,
        url=f"https://example.com/{iid}",
        title=f"Title {iid}",
        body_text="body",
        engagement=EngagementSignals(),
        normalized_text="body " + iid,
        body_fingerprint="fp" + iid,
        scores=sc,
    )


def test_diversity_cap_backfills_other_sources() -> None:
    a = _item("a", "feed_a", 90.0)
    b = _item("b", "feed_a", 80.0)
    c = _item("c", "feed_b", 70.0)
    items_by_id = {x.id: x for x in (a, b, c)}
    clusters = [
        StoryCluster(
            cluster_id="c1",
            canonical_item_id="a",
            member_item_ids=["a"],
            supporting_urls=["https://example.com/a"],
            headline_hint="A",
            items=[a],
        ),
        StoryCluster(
            cluster_id="c2",
            canonical_item_id="b",
            member_item_ids=["b"],
            supporting_urls=["https://example.com/b"],
            headline_hint="B",
            items=[b],
        ),
        StoryCluster(
            cluster_id="c3",
            canonical_item_id="c",
            member_item_ids=["c"],
            supporting_urls=["https://example.com/c"],
            headline_hint="C",
            items=[c],
        ),
    ]
    brief = DailyBriefReport(
        top_stories=[
            BriefEntry(
                headline="HA",
                why_it_matters="",
                summary="",
                related_cluster_ids=["c1"],
            ),
            BriefEntry(
                headline="HB",
                why_it_matters="",
                summary="",
                related_cluster_ids=["c2"],
            ),
        ]
    )
    # Model ranked two items from feed_a first; cap=1 keeps the first only, then backfills feed_b
    report_cfg = {"top_stories": 2, "max_top_stories_per_source_id": 1}
    out = apply_source_diversity_cap(brief, clusters, items_by_id, report_cfg)
    assert len(out.top_stories) == 2
    assert out.top_stories[0].headline == "HA"
    assert out.top_stories[1].headline == "Title c"
    assert out.top_stories[1].related_cluster_ids == ["c3"]


def test_diversity_cap_maps_entry_without_related_cluster_ids_via_link() -> None:
    a = _item("a", "feed_a", 90.0)
    b = _item("b", "feed_b", 85.0)
    items_by_id = {x.id: x for x in (a, b)}
    clusters = [
        StoryCluster(
            cluster_id="c1",
            canonical_item_id="a",
            member_item_ids=["a"],
            supporting_urls=["https://example.com/a"],
            headline_hint="A",
            items=[a],
        ),
        StoryCluster(
            cluster_id="c2",
            canonical_item_id="b",
            member_item_ids=["b"],
            supporting_urls=["https://example.com/b"],
            headline_hint="B",
            items=[b],
        ),
    ]
    brief = DailyBriefReport(
        top_stories=[
            # Missing related_cluster_ids, but link matches feed_a canonical URL
            BriefEntry(
                headline="A story",
                why_it_matters="",
                summary="",
                supporting_links=["https://example.com/a"],
                related_cluster_ids=[],
            ),
            BriefEntry(
                headline="A story follow-up",
                why_it_matters="",
                summary="",
                supporting_links=["https://example.com/a?ref=tracking"],
                related_cluster_ids=[],
            ),
        ]
    )
    report_cfg = {"top_stories": 2, "max_top_stories_per_source_id": 1}
    out = apply_source_diversity_cap(brief, clusters, items_by_id, report_cfg)
    assert len(out.top_stories) == 2
    # Second item from same source should be capped and replaced via backfill from feed_b.
    assert out.top_stories[1].headline == "Title b"
    assert out.top_stories[1].related_cluster_ids == ["c2"]
