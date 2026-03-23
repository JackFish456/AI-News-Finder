from __future__ import annotations

import logging
from typing import Any

from news_agent.config_loader import NewsAgentConfig
from news_agent.models.item import ContentItem, PipelineStageRecord
from news_agent.models.scoring import ItemScores
from news_agent.scoring.final import compute_final_score, resolve_source_weight
from news_agent.scoring.llm_models import LlmItemEvaluation
from news_agent.settings import Settings
from news_agent.storage.repository import RunRepository
from news_agent.utils.openai_client import OpenAiJsonClient
from news_agent.utils.prompts import load_prompt_text

logger = logging.getLogger(__name__)

PROMPT_VERSION = "post_quality_v1.txt+ai_slop_signals_v1.txt"


def _build_system_prompt() -> str:
    main = load_prompt_text("post_quality_v1.txt")
    slop = load_prompt_text("ai_slop_signals_v1.txt")
    return main.strip() + "\n\n---\n\n" + slop.strip()


def _item_user_payload(item: ContentItem) -> str:
    return (
        f"source_type: {item.source_type}\n"
        f"source_id: {item.source_id}\n"
        f"url: {item.url}\n"
        f"title: {item.title or ''}\n"
        f"author: {item.author or ''}\n"
        f"published_at: {item.published_at.isoformat() if item.published_at else ''}\n"
        f"text:\n{item.normalized_text or item.body_text}\n"
    )


def score_items_with_openai(
    items: list[ContentItem],
    settings: Settings,
    agent_cfg: NewsAgentConfig,
    repo: RunRepository | None = None,
) -> list[ContentItem]:
    scoring_cfg: dict[str, Any] = agent_cfg.scoring or {}
    ttl = int(scoring_cfg.get("cache_ttl_seconds", 86400))
    client = OpenAiJsonClient(settings, repo=repo, cache_ttl_seconds=ttl)
    if not client.available:
        logger.warning("OpenAI unavailable — assigning neutral scores for pipeline continuity.")
        return [_fallback_scores(it, agent_cfg) for it in items]

    system = _build_system_prompt()
    model = settings.openai_model
    min_sub = int(scoring_cfg.get("min_substance_score", 35))
    min_cred = int(scoring_cfg.get("min_credibility_score", 25))
    max_hype = int(scoring_cfg.get("max_hype_penalty_before_hard_reject", 85))
    max_slop = int(scoring_cfg.get("max_ai_slop_penalty_before_hard_reject", 85))
    min_final = float(scoring_cfg.get("min_final_score", 40))

    for item in items:
        try:
            ev = client.complete_json(
                model=model,
                system=system,
                user=_item_user_payload(item),
                response_model=LlmItemEvaluation,
                cache_key_parts={"item_id": item.id, "pv": PROMPT_VERSION},
                cache_namespace="item_eval",
            )
        except Exception as e:
            logger.exception("Scoring failed for %s: %s", item.id, e)
            item = _fallback_scores(item, agent_cfg)
            continue

        scores = ItemScores(
            importance_score=ev.importance_score,
            credibility_score=ev.credibility_score,
            novelty_score=ev.novelty_score,
            substance_score=ev.substance_score,
            hype_penalty=ev.hype_penalty,
            ai_slop_penalty=ev.ai_slop_penalty,
            importance_rationale=ev.importance_rationale,
            credibility_rationale=ev.credibility_rationale,
            novelty_rationale=ev.novelty_rationale,
            substance_rationale=ev.substance_rationale,
            hype_rationale=ev.hype_rationale,
            ai_slop_rationale=ev.ai_slop_rationale,
            primary_category=ev.primary_category,
            llm_model=model,
            prompt_version=PROMPT_VERSION,
        )
        sw = resolve_source_weight(item, agent_cfg.source_weights or {})
        scores.final_score = compute_final_score(scores, sw)

        item.scores = scores
        item.pipeline_decision = _decision_from_eval(
            ev,
            scores,
            min_sub,
            min_cred,
            max_hype,
            max_slop,
            min_final,
        )
        item.pipeline_decision_detail = ev.decision_rationale
        item.history.append(
            PipelineStageRecord(
                stage="score",
                action="dropped" if item.pipeline_decision == "rejected" else "kept",
                reason_codes=[item.pipeline_decision or "unknown"],
                detail=f"final_score={scores.final_score}",
            )
        )
    return items


def _decision_from_eval(
    ev: LlmItemEvaluation,
    scores: ItemScores,
    min_sub: int,
    min_cred: int,
    max_hype: int,
    max_slop: int,
    min_final: float,
) -> str:
    if ev.decision == "drop":
        return "rejected"
    if scores.substance_score < min_sub:
        return "rejected"
    if scores.credibility_score < min_cred:
        return "rejected"
    if scores.hype_penalty >= max_hype:
        return "rejected"
    if scores.ai_slop_penalty >= max_slop:
        return "rejected"
    if scores.final_score < min_final:
        return "rejected"
    if scores.hype_penalty >= 55:
        return "overhyped"
    return "accepted"


def _fallback_scores(item: ContentItem, agent_cfg: NewsAgentConfig) -> ContentItem:
    scores = ItemScores(
        importance_score=50,
        credibility_score=50,
        novelty_score=50,
        substance_score=50,
        hype_penalty=20,
        ai_slop_penalty=20,
        importance_rationale="fallback",
        credibility_rationale="fallback",
        novelty_rationale="fallback",
        substance_rationale="fallback",
        hype_rationale="fallback",
        ai_slop_rationale="fallback",
        primary_category="other",
        llm_model=None,
        prompt_version="fallback",
    )
    sw = resolve_source_weight(item, agent_cfg.source_weights or {})
    scores.final_score = compute_final_score(scores, sw)
    item.scores = scores
    item.pipeline_decision = "accepted"
    item.pipeline_decision_detail = "OpenAI key missing — neutral fallback for dev/test"
    item.history.append(
        PipelineStageRecord(
            stage="score",
            action="kept",
            reason_codes=["fallback_no_llm"],
            detail="neutral scores",
        )
    )
    return item
