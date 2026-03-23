from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_agent.collectors.mock_collector import MockCollector
from news_agent.collectors.reddit_collector import RedditCollector
from news_agent.collectors.rss_collector import RssCollector
from news_agent.collectors.twitter_collector import TwitterCollector
from news_agent.config_loader import NewsAgentConfig, load_config
from news_agent.clustering.embedding_cluster import (
    cluster_by_embedding_similarity,
    singleton_clusters_from_items,
)
from news_agent.filters.dedupe import dedupe_by_fingerprint_and_url
from news_agent.filters.heuristic import heuristic_prefilter
from news_agent.models.item import ContentItem, PipelineStageRecord
from news_agent.normalizers.item_builder import raw_to_content_item
from news_agent.reporting.exporters import (
    default_output_stem,
    export_docx,
    export_markdown,
)
from news_agent.scoring.openai_scorer import score_items_with_openai
from news_agent.settings import Settings, get_settings
from news_agent.storage.db import get_engine, get_session_factory, init_db
from news_agent.storage.repository import RunRepository
from news_agent.summarization.daily_brief import generate_daily_brief

logger = logging.getLogger(__name__)


def _build_collectors(settings: Settings, cfg: NewsAgentConfig, include_mock: bool):
    cols = [RssCollector(f) for f in cfg.rss_feeds]
    cols.append(RedditCollector(settings, list(cfg.reddit_subreddits)))
    cols.append(TwitterCollector(settings, list(cfg.twitter_queries)))
    if include_mock:
        cols.append(MockCollector())
    return cols


def run_daily_pipeline(
    *,
    settings: Settings | None = None,
    config_path: Path | None = None,
    include_mock: bool = False,
    write_reports: bool = True,
    output_dir: Path | None = None,
    simple: bool = False,
) -> dict[str, Any]:
    """
    End-to-end pipeline: fetch → normalize → dedupe → prefilter → score → cluster → brief → export.

    When ``simple`` is True, skip embedding clustering (one cluster per accepted item), skip
    intermediate item snapshots and LLM DB cache for scoring/brief, and avoid DB persistence.
    """
    settings = settings or get_settings()
    cfg_path = config_path or settings.news_agent_config
    cfg = load_config(cfg_path)

    session = None
    repo = None
    run_id = 0
    if not simple:
        engine = get_engine(settings.database_url)
        init_db(engine)
        SessionFactory = get_session_factory(engine)
        session = SessionFactory()
        repo = RunRepository(session)
        run_id = repo.start_run(str(cfg_path))
        session.commit()
    else:
        logger.info("Simple mode: DB persistence disabled for this run.")

    since = datetime.now(timezone.utc) - timedelta(hours=settings.pipeline_since_hours)
    all_items: list[ContentItem] = []

    try:
        for collector in _build_collectors(settings, cfg, include_mock):
            try:
                for raw in collector.collect(since):
                    all_items.append(raw_to_content_item(raw))
            except Exception:
                logger.exception("Collector %s failed", type(collector).__name__)

        if repo is not None and session is not None and not simple:
            repo.save_items_snapshot(run_id, "normalized", all_items)
            session.commit()

        deduped = dedupe_by_fingerprint_and_url(all_items)
        if repo is not None and session is not None and not simple:
            repo.save_items_snapshot(run_id, "deduped", deduped)
            session.commit()

        prefilter_cfg = cfg.prefilter or {}
        to_score: list[ContentItem] = []
        for it in deduped:
            if heuristic_prefilter(it, prefilter_cfg):
                to_score.append(it)
            else:
                it.pipeline_decision = "rejected"
                it.pipeline_decision_detail = "prefilter"
                it.history.append(
                    PipelineStageRecord(
                        stage="classify",
                        action="dropped",
                        reason_codes=["prefilter"],
                        detail=None,
                    )
                )

        score_repo = None if simple else repo
        scored = score_items_with_openai(to_score, settings, cfg, repo=score_repo)
        scored_by_id = {it.id: it for it in scored}
        merged: list[ContentItem] = []
        for it in deduped:
            merged.append(scored_by_id.get(it.id, it))
        if repo is not None and session is not None and not simple:
            repo.save_items_snapshot(run_id, "scored", merged)
            session.commit()

        cluster_pool = [
            it for it in merged if it.pipeline_decision in ("accepted", "overhyped")
        ]
        if simple:
            clusters = singleton_clusters_from_items(cluster_pool)
        else:
            clusters = cluster_by_embedding_similarity(cluster_pool, settings, cfg)
        if repo is not None and session is not None:
            repo.save_clusters(run_id, clusters)
            session.commit()

        items_by_id = {it.id: it for it in merged}

        report_cfg = cfg.report or {}
        brief_repo = None if simple else repo
        brief = generate_daily_brief(
            clusters,
            items_by_id,
            settings,
            repo=brief_repo,
            report_cfg=report_cfg,
        )
        if session is not None:
            session.commit()

        out: dict[str, Any] = {
            "run_id": run_id,
            "brief": brief.model_dump(),
            "stats": {
                "ingested": len(all_items),
                "deduped": len(deduped),
                "scored": len(to_score),
                "clusters": len(clusters),
            },
        }

        if write_reports:
            base = output_dir or settings.output_dir
            run_at = datetime.now(timezone.utc)
            stem = default_output_stem(run_at)
            day_dir = base / f"{run_at:%Y_%m_%d}"
            md_path = day_dir / f"{stem}.md"
            docx_path = day_dir / f"{stem}.docx"
            export_markdown(
                brief,
                md_path,
                clusters=clusters,
                audit_items=merged,
                report_cfg=report_cfg,
            )
            export_docx(brief, docx_path, report_cfg=report_cfg)
            if repo is not None and session is not None:
                repo.save_report_ref(run_id, "markdown", str(md_path.resolve()), None)
                repo.save_report_ref(run_id, "docx", str(docx_path.resolve()), None)
                session.commit()
            out["artifacts"] = {
                "markdown": str(md_path.resolve()),
                "docx": str(docx_path.resolve()),
            }

        if repo is not None and session is not None:
            repo.finish_run(run_id, "ok", None)
            session.commit()
        return out
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        if repo is not None and session is not None:
            repo.finish_run(run_id, "error", str(e))
            session.commit()
        raise
    finally:
        if session is not None:
            session.close()
