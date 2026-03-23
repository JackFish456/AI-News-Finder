from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from news_agent.models.scoring import ItemScores


class EngagementSignals(BaseModel):
    """Optional per-platform engagement metrics (normalized where possible)."""

    upvotes: int | None = None
    comment_count: int | None = None
    retweets: int | None = None
    likes: int | None = None
    views: int | None = None
    score: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PipelineStageRecord(BaseModel):
    """Audit trail for why an item was kept, dropped, or down-ranked."""

    stage: str
    action: str  # kept | dropped | flagged | passed
    reason_codes: list[str] = Field(default_factory=list)
    detail: str | None = None


class ContentItem(BaseModel):
    """
    Unified ingest schema for articles, posts, and social items.

    `source_id` identifies the collector configuration (e.g. rss_reuters_tech).
    `external_id` should be stable within the source when available.
    """

    model_config = {"extra": "allow"}

    id: str = Field(description="Deterministic id, typically hash of source+external+url")
    source_type: str  # rss | reddit | twitter | manual | mock
    source_id: str
    external_id: str | None = None
    url: HttpUrl | str
    title: str | None = None
    body_text: str = ""
    author: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    language: str | None = "en"

    engagement: EngagementSignals = Field(default_factory=EngagementSignals)
    credibility_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Publisher tier, outlet name, verified account flags, etc.",
    )
    raw_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Original collector payload for debugging",
    )

    # Pipeline outputs
    normalized_text: str | None = None
    body_fingerprint: str | None = None
    history: list[PipelineStageRecord] = Field(default_factory=list)

    scores: ItemScores | None = None
    pipeline_decision: str | None = None
    pipeline_decision_detail: str | None = None
    cluster_id: str | None = None
