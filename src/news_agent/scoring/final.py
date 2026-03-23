from __future__ import annotations

from news_agent.models.item import ContentItem
from news_agent.models.scoring import ItemScores


def resolve_source_weight(item: ContentItem, source_weights: dict[str, float]) -> float:
    meta = item.credibility_meta or {}
    key = meta.get("feed_weight_key")
    if isinstance(key, str) and key in source_weights:
        return float(source_weights[key])
    if item.source_type in source_weights:
        return float(source_weights[item.source_type])
    return float(source_weights.get("default", 1.0))


def compute_final_score(
    scores: ItemScores,
    source_weight: float,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Combine dimensions into a single ranking score.

    Default weights emphasize substance and importance; penalties subtract in 0–30 range.
    """
    w = weights or {
        "importance": 0.25,
        "credibility": 0.2,
        "novelty": 0.2,
        "substance": 0.35,
    }
    base = (
        w["importance"] * scores.importance_score
        + w["credibility"] * scores.credibility_score
        + w["novelty"] * scores.novelty_score
        + w["substance"] * scores.substance_score
    )
    # Penalties are 0–100; map to a reduction of up to ~30 points each (capped)
    hype = min(30.0, scores.hype_penalty * 0.25)
    slop = min(35.0, scores.ai_slop_penalty * 0.35)
    raw = max(0.0, base - hype - slop)
    return round(raw * source_weight, 4)
