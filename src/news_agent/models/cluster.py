from __future__ import annotations

from pydantic import BaseModel, Field

from news_agent.models.item import ContentItem


class StoryCluster(BaseModel):
    """Grouped coverage of one underlying story from multiple items."""

    cluster_id: str
    canonical_item_id: str
    member_item_ids: list[str] = Field(default_factory=list)
    supporting_urls: list[str] = Field(default_factory=list)
    headline_hint: str | None = None
    centroid_embedding_id: str | None = None

    # Populated after summarization
    summary: str | None = None
    why_it_matters: str | None = None
    impact_estimate: str | None = None
    confidence_note: str | None = None

    # Optional hydrated items for reporting (not always persisted)
    items: list[ContentItem] = Field(default_factory=list, exclude=True)
