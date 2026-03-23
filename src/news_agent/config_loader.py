from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RssFeedConfig(BaseModel):
    id: str
    url: str
    weight_key: str = "default"


class NewsAgentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_weights: dict[str, float] = Field(default_factory=dict)
    prefilter: dict[str, Any] = Field(default_factory=dict)
    dedupe: dict[str, Any] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(default_factory=dict)
    rss_feeds: list[RssFeedConfig] = Field(default_factory=list)
    reddit_subreddits: list[str] = Field(default_factory=list)
    twitter_queries: list[str] = Field(default_factory=list)


def load_config(path: Path) -> NewsAgentConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return NewsAgentConfig.model_validate(raw)
