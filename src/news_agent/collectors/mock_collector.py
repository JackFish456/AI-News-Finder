from __future__ import annotations

from datetime import datetime, timedelta, timezone

from news_agent.collectors.base import RawIngest, SourceCollector


class MockCollector(SourceCollector):
    """Deterministic sample items for CI and local testing without network."""

    source_type = "mock"

    def __init__(self, source_id: str = "mock_seed"):
        self._source_id = source_id

    def collect(self, since: datetime) -> list[RawIngest]:
        now = datetime.now(timezone.utc)
        return [
            RawIngest(
                source_type=self.source_type,
                source_id=self._source_id,
                external_id="mock-1",
                url="https://example.com/news/openai-ships-widget",
                title="OpenAI ships new widget API for enterprise",
                body_text="The release includes batching, improved latency, and new safety filters.",
                author="mock_reporter",
                published_at=now - timedelta(hours=2),
                credibility_meta={"outlet_tier": "trade_press"},
                raw_payload={"note": "mock"},
            ),
            RawIngest(
                source_type=self.source_type,
                source_id=self._source_id,
                external_id="mock-2",
                url="https://example.com/hype/agi-soon",
                title="AGI is definitely tomorrow (thread)",
                body_text="🚀🚀🚀 you won't believe this one weird trick for alignment. moon soon.",
                author="hype_bot",
                published_at=now - timedelta(hours=1),
                credibility_meta={},
                raw_payload={"note": "mock_fluff"},
            ),
        ]
