from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LlmItemEvaluation(BaseModel):
    """Structured output from post-quality + scoring prompt."""

    decision: Literal["keep", "drop"] = Field(
        description="drop if clearly fluff, spam, duplicate commentary, or non-AI-industry noise"
    )
    decision_rationale: str = ""

    importance_score: int = Field(ge=0, le=100)
    credibility_score: int = Field(ge=0, le=100)
    novelty_score: int = Field(ge=0, le=100)
    substance_score: int = Field(ge=0, le=100)
    hype_penalty: int = Field(ge=0, le=100)
    ai_slop_penalty: int = Field(ge=0, le=100)

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
