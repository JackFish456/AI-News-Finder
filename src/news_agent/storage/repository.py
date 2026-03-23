from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from news_agent.models.cluster import StoryCluster
from news_agent.models.item import ContentItem
from news_agent.storage.orm import ClusterRow, ItemRow, LlmCacheRow, PipelineRunRow, ReportArtifactRow


class RunRepository:
    def __init__(self, session: Session):
        self._s = session

    def start_run(self, config_path: str) -> int:
        row = PipelineRunRow(config_path=config_path, status="running")
        self._s.add(row)
        self._s.flush()
        return row.id

    def finish_run(self, run_id: int, status: str, error: str | None = None) -> None:
        row = self._s.get(PipelineRunRow, run_id)
        if row:
            row.status = status
            row.finished_at = datetime.utcnow()
            row.error_message = error

    def save_items_snapshot(self, run_id: int, stage: str, items: list[ContentItem]) -> None:
        self._s.execute(delete(ItemRow).where(ItemRow.run_id == run_id, ItemRow.stage == stage))
        for it in items:
            self._s.add(
                ItemRow(
                    run_id=run_id,
                    stage=stage,
                    item_id=it.id,
                    payload_json=it.model_dump_json(),
                )
            )

    def save_clusters(self, run_id: int, clusters: list[StoryCluster]) -> None:
        self._s.execute(delete(ClusterRow).where(ClusterRow.run_id == run_id))
        for c in clusters:
            self._s.add(
                ClusterRow(
                    run_id=run_id,
                    cluster_id=c.cluster_id,
                    payload_json=c.model_dump_json(exclude={"items"}),
                )
            )

    def get_llm_cache(self, cache_key: str) -> dict[str, Any] | None:
        row = self._s.get(LlmCacheRow, cache_key)
        if not row:
            return None
        if row.expires_at and row.expires_at < datetime.utcnow():
            self._s.delete(row)
            return None
        return json.loads(row.response_json)

    def set_llm_cache(
        self,
        cache_key: str,
        model: str,
        payload: dict[str, Any],
        ttl_seconds: int | None,
    ) -> None:
        expires = None
        if ttl_seconds:
            expires = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        row = self._s.get(LlmCacheRow, cache_key)
        body = json.dumps(payload)
        if row:
            row.response_json = body
            row.model = model
            row.expires_at = expires
        else:
            self._s.add(
                LlmCacheRow(
                    cache_key=cache_key,
                    model=model,
                    response_json=body,
                    expires_at=expires,
                )
            )

    def save_report_ref(self, run_id: int, report_format: str, path: str, quality: float | None) -> None:
        self._s.add(
            ReportArtifactRow(
                run_id=run_id,
                format=report_format,
                path=path,
                quality_score=quality,
            )
        )
