from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

from news_agent.models.item import ContentItem, PipelineStageRecord

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        q = []
        for part in (p.query or "").split("&"):
            if not part or part.lower().startswith("utm_"):
                continue
            q.append(part)
        new_query = "&".join(sorted(q))
        path = (p.path or "").rstrip("/") or "/"
        return urlunparse((p.scheme, p.netloc.lower(), path, "", new_query, ""))
    except Exception:
        return url


def dedupe_by_fingerprint_and_url(items: list[ContentItem]) -> list[ContentItem]:
    """Keep a single item per normalized URL and per body fingerprint (best-effort)."""
    by_url: dict[str, ContentItem] = {}
    by_fp_map: dict[str, ContentItem] = {}

    def rank(a: ContentItem) -> tuple[int, float]:
        order = {"rss": 3, "reddit": 2, "twitter": 1, "mock": 0, "manual": 4}
        score = 0.0
        if a.engagement.score is not None:
            try:
                score = float(a.engagement.score)
            except (TypeError, ValueError):
                score = 0.0
        return (order.get(a.source_type, 0), score)

    kept: list[ContentItem] = []
    for it in sorted(items, key=lambda x: rank(x), reverse=True):
        nu = _normalize_url(str(it.url))
        fp = it.body_fingerprint or ""
        if nu in by_url:
            _record_dup(it, by_url[nu], "url")
            continue
        if fp and fp in by_fp_map:
            _record_dup(it, by_fp_map[fp], "fingerprint")
            continue
        by_url[nu] = it
        if fp:
            by_fp_map[fp] = it
        _record(it, "dedupe", "passed", ["canonical_selected"], None)
        kept.append(it)
    logger.info("Dedupe: %d -> %d items", len(items), len(kept))
    return kept


def _record(
    item: ContentItem,
    stage: str,
    action: str,
    codes: list[str],
    detail: str | None,
) -> None:
    item.history.append(
        PipelineStageRecord(stage=stage, action=action, reason_codes=codes, detail=detail)
    )


def _record_dup(dup: ContentItem, canonical: ContentItem, kind: str) -> None:
    dup.history.append(
        PipelineStageRecord(
            stage="dedupe",
            action="dropped",
            reason_codes=[f"duplicate_{kind}"],
            detail=f"canonical={canonical.id}",
        )
    )
