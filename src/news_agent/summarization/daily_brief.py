from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from news_agent.models.cluster import StoryCluster
from news_agent.models.item import ContentItem
from news_agent.settings import Settings
from news_agent.storage.repository import RunRepository
from news_agent.utils.openai_client import OpenAiJsonClient
from news_agent.utils.prompts import load_prompt_text

logger = logging.getLogger(__name__)

PROMPT_VERSION = "daily_brief_v1.txt#summary-2-4-v1"


class BriefEntry(BaseModel):
    headline: str
    why_it_matters: str
    summary: str = Field(
        description="2–4 complete sentences; key facts plus light context, not one short line.",
    )
    supporting_links: list[str] = Field(default_factory=list)
    credibility_note: str = ""
    estimated_impact: str = ""
    related_cluster_ids: list[str] = Field(default_factory=list)


class DailyBriefReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    top_stories: list[BriefEntry] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


def _clusters_payload(clusters: list[StoryCluster], items_by_id: dict[str, ContentItem]) -> str:
    rows: list[dict[str, Any]] = []
    for c in sorted(clusters, key=lambda x: _cluster_score(x, items_by_id), reverse=True)[:25]:
        canon = items_by_id.get(c.canonical_item_id)
        text = ""
        if canon:
            text = (canon.normalized_text or canon.body_text or "")[:4000]
        rows.append(
            {
                "cluster_id": c.cluster_id,
                "canonical_title": canon.title if canon else c.headline_hint,
                "canonical_url": str(canon.url) if canon else "",
                "supporting_urls": c.supporting_urls,
                "text_excerpt": text,
                "scores": canon.scores.model_dump() if canon and canon.scores else {},
                "category": canon.scores.primary_category if canon and canon.scores else "other",
                "pipeline_decision": canon.pipeline_decision if canon else "",
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _cluster_score(c: StoryCluster, items_by_id: dict[str, ContentItem]) -> float:
    canon = items_by_id.get(c.canonical_item_id)
    if canon and canon.scores:
        return float(canon.scores.final_score)
    return 0.0


def _report_limits_instruction(report_cfg: dict[str, Any]) -> str:
    min_top, top = _story_bounds(report_cfg)
    return (
        "\n\nOutput limits (strict — do not exceed):\n"
        f"- top_stories: at least {min_top} items when available\n"
        f"- top_stories: at most {top} items, ranked most important first\n"
    )


def _story_bounds(report_cfg: dict[str, Any]) -> tuple[int, int]:
    try:
        top = int(report_cfg.get("top_stories", 7))
    except (TypeError, ValueError):
        top = 7
    top = max(1, top)

    try:
        min_top = int(report_cfg.get("min_top_stories", 1))
    except (TypeError, ValueError):
        min_top = 1
    min_top = max(1, min(min_top, top))
    return (min_top, top)


def apply_report_limits(brief: DailyBriefReport, report_cfg: dict[str, Any]) -> DailyBriefReport:
    """Trim section sizes after LLM output so readers are not overwhelmed."""
    _, top = _story_bounds(report_cfg)
    return brief.model_copy(
        update={
            "top_stories": brief.top_stories[:top],
        }
    )


def _canonical_source_id(cluster: StoryCluster, items_by_id: dict[str, ContentItem]) -> str:
    canon = items_by_id.get(cluster.canonical_item_id)
    return canon.source_id if canon else "unknown"


def _source_bucket_for_entry(
    entry: BriefEntry,
    clusters_by_id: dict[str, StoryCluster],
    items_by_id: dict[str, ContentItem],
    canonical_url_to_cluster_id: dict[str, str],
    headline_to_cluster_id: dict[str, str],
) -> tuple[str | None, str | None]:
    """
    Return (canonical_source_id, cluster_id) for diversity cap.
    If the entry cannot be mapped, returns (None, None) and no cap is applied for that row.
    """
    for cid in entry.related_cluster_ids or []:
        c = clusters_by_id.get(cid)
        if c:
            return (_canonical_source_id(c, items_by_id), cid)

    # Fallback 1: map from supporting link URL to known canonical URLs.
    for raw_url in entry.supporting_links or []:
        key = _normalize_url_key(raw_url)
        if not key:
            continue
        cid = canonical_url_to_cluster_id.get(key)
        if not cid:
            continue
        c = clusters_by_id.get(cid)
        if c:
            return (_canonical_source_id(c, items_by_id), cid)

    # Fallback 2: headline exact match to canonical title.
    headline_key = (entry.headline or "").strip().lower()
    if headline_key:
        cid = headline_to_cluster_id.get(headline_key)
        if cid:
            c = clusters_by_id.get(cid)
            if c:
                return (_canonical_source_id(c, items_by_id), cid)

    return (None, None)


def _normalize_url_key(raw_url: str | None) -> str:
    if not raw_url:
        return ""
    try:
        p = urlparse(str(raw_url).strip())
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (p.path or "").rstrip("/")
        return f"{host}{path}"
    except Exception:
        return str(raw_url).strip().lower()


def _backfill_brief_entry(cluster: StoryCluster, items_by_id: dict[str, ContentItem]) -> BriefEntry:
    canon = items_by_id.get(cluster.canonical_item_id)
    summary_text = ""
    if canon and (canon.normalized_text or canon.body_text):
        summary_text = (canon.normalized_text or canon.body_text or "")[:400]
    return BriefEntry(
        headline=canon.title if canon else (cluster.headline_hint or "Story"),
        why_it_matters="Included to diversify sources in the digest.",
        summary=summary_text,
        supporting_links=cluster.supporting_urls[:5],
        credibility_note="",
        estimated_impact="",
        related_cluster_ids=[cluster.cluster_id],
    )


def apply_source_diversity_cap(
    brief: DailyBriefReport,
    clusters: list[StoryCluster],
    items_by_id: dict[str, ContentItem],
    report_cfg: dict[str, Any],
) -> DailyBriefReport:
    """
    Enforce max stories per ``source_id`` (canonical item per cluster) after the model output.
    Preserves model ordering for kept rows; backfills remaining digest slots from other clusters
    by cluster score when possible.
    """
    raw_cap = report_cfg.get("max_top_stories_per_source_id", 2)
    try:
        per_source_cap = int(raw_cap) if raw_cap is not None else 2
    except (TypeError, ValueError):
        per_source_cap = 2
    if per_source_cap <= 0:
        return brief

    min_lim, top_lim = _story_bounds(report_cfg)
    clusters_by_id = {c.cluster_id: c for c in clusters}
    canonical_url_to_cluster_id: dict[str, str] = {}
    headline_to_cluster_id: dict[str, str] = {}
    for c in clusters:
        canon = items_by_id.get(c.canonical_item_id)
        if canon:
            canon_key = _normalize_url_key(str(canon.url))
            if canon_key:
                canonical_url_to_cluster_id.setdefault(canon_key, c.cluster_id)
            title_key = (canon.title or "").strip().lower()
            if title_key:
                headline_to_cluster_id.setdefault(title_key, c.cluster_id)

    counts: dict[str, int] = defaultdict(int)
    used_cluster_ids: set[str] = set()
    selected: list[BriefEntry] = []

    for entry in brief.top_stories:
        if len(selected) >= top_lim:
            break
        bucket, matched_cid = _source_bucket_for_entry(
            entry,
            clusters_by_id,
            items_by_id,
            canonical_url_to_cluster_id,
            headline_to_cluster_id,
        )
        if bucket is not None and counts[bucket] >= per_source_cap:
            continue
        selected.append(entry)
        if bucket is not None:
            counts[bucket] += 1
        if matched_cid:
            used_cluster_ids.add(matched_cid)

    cluster_rank = sorted(
        clusters,
        key=lambda c: _cluster_score(c, items_by_id),
        reverse=True,
    )
    for c in cluster_rank:
        if len(selected) >= top_lim:
            break
        if c.cluster_id in used_cluster_ids:
            continue
        bucket = _canonical_source_id(c, items_by_id)
        if counts[bucket] >= per_source_cap:
            continue
        selected.append(_backfill_brief_entry(c, items_by_id))
        used_cluster_ids.add(c.cluster_id)
        counts[bucket] += 1

    # Ensure a minimum digest size when enough clusters exist. If diversity caps
    # are too restrictive, relax the cap only for the final few slots.
    for c in cluster_rank:
        if len(selected) >= min_lim:
            break
        if c.cluster_id in used_cluster_ids:
            continue
        selected.append(_backfill_brief_entry(c, items_by_id))
        used_cluster_ids.add(c.cluster_id)

    return brief.model_copy(update={"top_stories": selected})


def generate_daily_brief(
    clusters: list[StoryCluster],
    items_by_id: dict[str, ContentItem],
    settings: Settings,
    repo: RunRepository | None = None,
    report_cfg: dict[str, Any] | None = None,
) -> DailyBriefReport:
    report_cfg = report_cfg or {}
    _, top_lim = _story_bounds(report_cfg)

    client = OpenAiJsonClient(settings, repo=repo, cache_ttl_seconds=3600)
    user = (
        "Clusters JSON:\n"
        + _clusters_payload(clusters, items_by_id)
        + _report_limits_instruction(report_cfg)
    )
    system = load_prompt_text("daily_brief_v1.txt")
    if not client.available:
        logger.warning("OpenAI unavailable — returning template brief.")
        report = apply_report_limits(_stub_brief(clusters, items_by_id, report_cfg), report_cfg)
        return apply_source_diversity_cap(report, clusters, items_by_id, report_cfg)

    model = settings.openai_model
    try:
        report = client.complete_json(
            model=model,
            system=system.strip(),
            user=user,
            response_model=DailyBriefReport,
            cache_key_parts={
                "pv": PROMPT_VERSION,
                "clusters": len(clusters),
                "top": top_lim,
            },
            cache_namespace="daily_brief",
        )
    except Exception:
        logger.exception("Daily brief generation failed; falling back to stub brief.")
        report = _stub_brief(clusters, items_by_id, report_cfg)

    # Never trust model-provided clocks for audit trails
    report.generated_at = datetime.now(timezone.utc).isoformat()
    report = apply_report_limits(report, report_cfg)
    return apply_source_diversity_cap(report, clusters, items_by_id, report_cfg)


def _stub_brief(
    clusters: list[StoryCluster],
    items_by_id: dict[str, ContentItem],
    report_cfg: dict[str, Any],
) -> DailyBriefReport:
    _, top_n = _story_bounds(report_cfg)
    top: list[BriefEntry] = []
    for c in clusters[:top_n]:
        canon = items_by_id.get(c.canonical_item_id)
        top.append(
            BriefEntry(
                headline=canon.title if canon else (c.headline_hint or "Story"),
                why_it_matters="Stub mode without OpenAI.",
                summary=(canon.normalized_text if canon else "")[:400] if canon else "",
                supporting_links=c.supporting_urls[:5],
                credibility_note="Unverified in stub mode",
                estimated_impact="Unknown",
                related_cluster_ids=[c.cluster_id],
            )
        )
    return DailyBriefReport(top_stories=top)
