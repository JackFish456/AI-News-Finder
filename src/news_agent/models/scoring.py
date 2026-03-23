from __future__ import annotations

from pydantic import BaseModel, Field


class ItemScores(BaseModel):
    """Explainable scoring output from the LLM + derived final score."""

    importance_score: int = Field(ge=0, le=100)
    credibility_score: int = Field(ge=0, le=100)
    novelty_score: int = Field(ge=0, le=100)
    substance_score: int = Field(ge=0, le=100)
    hype_penalty: int = Field(ge=0, le=100, description="Higher = more hype / less substance")
    ai_slop_penalty: int = Field(ge=0, le=100, description="Higher = more likely spam/slop")

    importance_rationale: str = ""
    credibility_rationale: str = ""
    novelty_rationale: str = ""
    substance_rationale: str = ""
    hype_rationale: str = ""
    ai_slop_rationale: str = ""

    primary_category: str = Field(
        default="other",
        description="research | product | policy | industry | social | other",
    )

    final_score: float = Field(
        default=0.0,
        description="Weighted combination after penalties and source weight",
    )
    llm_model: str | None = None
    prompt_version: str | None = None
