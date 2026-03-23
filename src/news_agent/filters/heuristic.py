from __future__ import annotations

import logging
from typing import Any

from news_agent.models.item import ContentItem, PipelineStageRecord

logger = logging.getLogger(__name__)


def heuristic_prefilter(item: ContentItem, cfg: dict[str, Any]) -> bool:
    """
    Return True if item should continue to LLM scoring.
    Return False if item should be dropped before LLM (saves cost).
    """
    min_len = int(cfg.get("min_text_length", 40))
    max_len = int(cfg.get("max_text_length", 32000))
    text = item.normalized_text or ""
    if len(text) < min_len:
        _record(item, "prefilter", "dropped", ["too_short"], f"len={len(text)}")
        return False
    if len(text) > max_len:
        _record(item, "prefilter", "dropped", ["too_long"], f"len={len(text)}")
        return False

    url = str(item.url)
    for pat in cfg.get("block_url_patterns", []) or []:
        if pat and pat in url:
            _record(item, "prefilter", "dropped", ["blocked_url_pattern"], pat)
            return False

    lowered = text.lower()
    fluff_kw = [k.lower() for k in (cfg.get("fluff_keywords", []) or [])]
    hits = sum(1 for k in fluff_kw if k and k in lowered)
    threshold = int(cfg.get("fluff_keyword_hits_to_reject", 999))
    if hits >= threshold:
        _record(item, "prefilter", "dropped", ["fluff_keywords"], f"hits={hits}")
        return False

    slop = [s.lower() for s in (cfg.get("slop_phrases", []) or [])]
    for phrase in slop:
        if phrase and phrase in lowered:
            _record(item, "prefilter", "flagged", ["slop_phrase"], phrase)
            # Flag but continue — LLM will apply ai_slop_penalty; do not hard-drop.

    _record(item, "prefilter", "passed", ["ok"], None)
    return True


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
