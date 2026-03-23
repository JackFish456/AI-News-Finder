from __future__ import annotations

import hashlib
import logging
import math
import uuid
from typing import Any

from news_agent.config_loader import NewsAgentConfig
from news_agent.models.cluster import StoryCluster
from news_agent.models.item import ContentItem, PipelineStageRecord
from news_agent.settings import Settings
from news_agent.utils.openai_client import OpenAiJsonClient

logger = logging.getLogger(__name__)

_PSEUDO_DIM = 256


def _pseudo_embedding(text: str) -> list[float]:
    """Deterministic sparse vector so offline runs do not merge unrelated items (stable across processes)."""
    vec = [0.0] * _PSEUDO_DIM
    for tok in text.lower().split():
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big") % _PSEUDO_DIM
        vec[h] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _sort_key_final_score(it: ContentItem) -> float:
    return float(it.scores.final_score if it.scores else 0.0)


def cluster_by_embedding_similarity(
    items: list[ContentItem],
    settings: Settings,
    agent_cfg: NewsAgentConfig,
) -> list[StoryCluster]:
    """
    Greedy clustering using embedding cosine similarity.
    Falls back to single-item clusters if OpenAI is unavailable.
    """
    dedupe_cfg: dict[str, Any] = agent_cfg.dedupe or {}
    merge_threshold = float(dedupe_cfg.get("cluster_merge_threshold", 0.86))
    batch = int(dedupe_cfg.get("max_items_per_batch_embed", 64))

    if not items:
        return []

    client = OpenAiJsonClient(settings, repo=None, cache_ttl_seconds=None)
    texts = [(it.normalized_text or it.body_text or "")[:8000] for it in items]
    embeddings: list[list[float]] = []
    if client.available:
        try:
            for i in range(0, len(texts), batch):
                chunk = texts[i : i + batch]
                embeddings.extend(
                    client.embed_texts(settings.openai_embedding_model, chunk),
                )
        except Exception:
            logger.exception("Embedding API failed; falling back to deterministic pseudo-embeddings")
            embeddings = [_pseudo_embedding(t) for t in texts]
    else:
        logger.warning("OpenAI unavailable — clustering uses pseudo-embeddings (may over/under-merge).")
        embeddings = [_pseudo_embedding(t) for t in texts]

    # Greedy: process highest final_score first as cluster seeds
    order = sorted(range(len(items)), key=lambda idx: _sort_key_final_score(items[idx]), reverse=True)
    clusters: list[list[int]] = []
    centroids: list[list[float]] = []

    for idx in order:
        vec = embeddings[idx]
        placed = False
        for ci, centroid in enumerate(centroids):
            if _cosine(vec, centroid) >= merge_threshold:
                clusters[ci].append(idx)
                # Incremental centroid mean (simple average recompute)
                members = clusters[ci]
                dim = len(vec)
                centroid[:] = [
                    sum(embeddings[j][d] for j in members) / len(members) for d in range(dim)
                ]
                placed = True
                break
        if not placed:
            clusters.append([idx])
            centroids.append(vec[:])

    out: list[StoryCluster] = []
    for member_indices in clusters:
        member_items = [items[i] for i in member_indices]
        member_items.sort(key=_sort_key_final_score, reverse=True)
        canonical = member_items[0]
        cid = uuid.uuid4().hex[:12]
        for it in member_items:
            it.cluster_id = cid
            it.history.append(
                PipelineStageRecord(
                    stage="cluster",
                    action="kept",
                    reason_codes=["clustered"],
                    detail=f"cluster={cid} canonical={canonical.id}",
                )
            )
        urls = []
        for it in member_items:
            u = str(it.url)
            if u not in urls:
                urls.append(u)
        out.append(
            StoryCluster(
                cluster_id=cid,
                canonical_item_id=canonical.id,
                member_item_ids=[it.id for it in member_items],
                supporting_urls=urls,
                headline_hint=canonical.title or (canonical.normalized_text or "")[:120],
                items=member_items,
            )
        )
    logger.info("Clustering: %d items -> %d clusters", len(items), len(out))
    return out


def singleton_clusters_from_items(items: list[ContentItem]) -> list[StoryCluster]:
    """
    One cluster per item (canonical = item), sorted by final_score descending.
    Used for --simple pipeline mode (no embedding merge pass).
    """
    if not items:
        return []
    ordered = sorted(items, key=_sort_key_final_score, reverse=True)
    out: list[StoryCluster] = []
    for it in ordered:
        cid = uuid.uuid4().hex[:12]
        it.cluster_id = cid
        it.history.append(
            PipelineStageRecord(
                stage="cluster",
                action="kept",
                reason_codes=["singleton_simple"],
                detail=f"cluster={cid} canonical={it.id}",
            )
        )
        u = str(it.url)
        out.append(
            StoryCluster(
                cluster_id=cid,
                canonical_item_id=it.id,
                member_item_ids=[it.id],
                supporting_urls=[u] if u else [],
                headline_hint=it.title or (it.normalized_text or "")[:120],
                items=[it],
            )
        )
    logger.info("Singleton clustering (simple mode): %d items -> %d clusters", len(items), len(out))
    return out
