from __future__ import annotations

import re
from datetime import datetime

from news_agent.collectors.base import RawIngest
from news_agent.models.item import ContentItem, EngagementSignals, PipelineStageRecord
from news_agent.utils.hashing import sha256_hex


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def raw_to_content_item(raw: RawIngest) -> ContentItem:
    body = strip_html(raw.body_text or "")
    title = (raw.title or "").strip()
    normalized = "\n".join(x for x in [title, body] if x).strip()
    fp = sha256_hex(normalized.lower())[:24]
    key = "|".join(
        [
            raw.source_type,
            raw.source_id,
            raw.external_id or raw.url,
            fp,
        ]
    )
    item_id = sha256_hex(key)[:32]

    eng = EngagementSignals(
        upvotes=raw.engagement.get("upvotes"),
        comment_count=raw.engagement.get("comment_count"),
        retweets=raw.engagement.get("retweets"),
        likes=raw.engagement.get("likes"),
        views=raw.engagement.get("views"),
        score=raw.engagement.get("score"),
        raw={k: v for k, v in raw.engagement.items()},
    )

    return ContentItem(
        id=item_id,
        source_type=raw.source_type,
        source_id=raw.source_id,
        external_id=raw.external_id,
        url=raw.url,
        title=title or None,
        body_text=body,
        author=raw.author,
        published_at=raw.published_at,
        fetched_at=datetime.utcnow(),
        engagement=eng,
        credibility_meta=raw.credibility_meta,
        raw_payload=raw.raw_payload,
        normalized_text=normalized,
        body_fingerprint=fp,
        history=[
            PipelineStageRecord(
                stage="normalize",
                action="kept",
                reason_codes=["normalized"],
                detail="Built ContentItem from RawIngest",
            )
        ],
    )
