from __future__ import annotations

from news_agent.models.cluster import StoryCluster
from news_agent.models.item import ContentItem, EngagementSignals
from news_agent.models.scoring import ItemScores
from news_agent.settings import Settings
from news_agent.summarization import daily_brief as daily_brief_mod


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


def test_generate_daily_brief_falls_back_when_openai_call_fails(monkeypatch) -> None:
    class _FailingClient:
        def __init__(self, *_args, **_kwargs):
            pass

        @property
        def available(self) -> bool:
            return True

        def complete_json(self, **_kwargs):
            raise RuntimeError("simulated OpenAI failure")

    monkeypatch.setattr(daily_brief_mod, "OpenAiJsonClient", _FailingClient)

    it = _item("a", "feed_a", 90.0)
    clusters = [
        StoryCluster(
            cluster_id="c1",
            canonical_item_id=it.id,
            member_item_ids=[it.id],
            supporting_urls=[str(it.url)],
            headline_hint=it.title,
            items=[it],
        )
    ]
    items_by_id = {it.id: it}
    settings = Settings()

    out = daily_brief_mod.generate_daily_brief(
        clusters=clusters,
        items_by_id=items_by_id,
        settings=settings,
        repo=None,
        report_cfg={"top_stories": 3, "max_top_stories_per_source_id": 2},
    )

    assert out.top_stories
    assert out.top_stories[0].headline == "Title a"
