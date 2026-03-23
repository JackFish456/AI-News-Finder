from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawIngest(BaseModel):
    """Collector-native row before normalization into ContentItem."""

    source_type: str
    source_id: str
    external_id: str | None = None
    url: str
    title: str | None = None
    body_text: str = ""
    author: str | None = None
    published_at: datetime | None = None
    engagement: dict[str, Any] = Field(default_factory=dict)
    credibility_meta: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class SourceCollector(ABC):
    source_type: str = "abstract"

    @abstractmethod
    def collect(self, since: datetime) -> list[RawIngest]:
        raise NotImplementedError
