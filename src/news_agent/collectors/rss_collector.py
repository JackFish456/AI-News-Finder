from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from news_agent.collectors.base import RawIngest, SourceCollector
from news_agent.config_loader import RssFeedConfig

logger = logging.getLogger(__name__)


def _parse_dt(entry: Any) -> datetime | None:
    """Parse entry time as timezone-aware UTC (naive strings assumed UTC)."""
    if getattr(entry, "published_parsed", None):
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    if getattr(entry, "published", None):
        try:
            dt = parsedate_to_datetime(entry.published)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass
    return None


def _ensure_utc(since: datetime) -> datetime:
    if since.tzinfo is None:
        return since.replace(tzinfo=timezone.utc)
    return since.astimezone(timezone.utc)


class RssCollector(SourceCollector):
    source_type = "rss"

    def __init__(self, feed: RssFeedConfig, timeout: float = 20.0):
        self._feed = feed
        self._timeout = timeout

    def collect(self, since: datetime) -> list[RawIngest]:
        since_utc = _ensure_utc(since)
        out: list[RawIngest] = []
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                resp = client.get(
                    self._feed.url,
                    headers={"User-Agent": "ai-news-brief/0.1 (+https://example.local)"},
                )
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
        except httpx.HTTPError as e:
            logger.warning("RSS fetch failed %s: %s", self._feed.id, e)
            return out

        for entry in getattr(parsed, "entries", []) or []:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue
            published = _parse_dt(entry)
            if published is not None and published < since_utc:
                continue
            title = entry.get("title")
            summary = entry.get("summary") or entry.get("description") or ""
            author = None
            if entry.get("author"):
                author = entry.get("author")
            elif entry.get("authors"):
                author = entry["authors"][0].get("name")

            ext_id = entry.get("id") or link
            out.append(
                RawIngest(
                    source_type=self.source_type,
                    source_id=self._feed.id,
                    external_id=str(ext_id),
                    url=str(link),
                    title=title,
                    body_text=summary,
                    author=author,
                    published_at=published,
                    credibility_meta={"feed_weight_key": self._feed.weight_key},
                    raw_payload=dict(entry),
                )
            )
        logger.info("RSS %s: %d items since %s", self._feed.id, len(out), since_utc.isoformat())
        return out
