from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from news_agent.collectors.base import RawIngest, SourceCollector
from news_agent.settings import Settings

logger = logging.getLogger(__name__)

TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterCollector(SourceCollector):
    """
    Recent search for the last ~7 days (Twitter API limitation).

    TODO: Requires TWITTER_BEARER_TOKEN with Elevated/Pro access for most production use.
    Paid tiers apply — stub returns empty when disabled.
    """

    source_type = "twitter"

    def __init__(self, settings: Settings, queries: list[str]):
        self._settings = settings
        self._queries = queries

    def collect(self, since: datetime) -> list[RawIngest]:
        if not self._settings.twitter_enabled or self._settings.mock_external_apis:
            logger.info("Twitter collector skipped (disabled or mock mode).")
            return []

        token = self._settings.twitter_bearer_token
        if not token:
            logger.warning("Twitter enabled but TWITTER_BEARER_TOKEN missing.")
            return []

        # Twitter recent search does not support arbitrary 24h lower bound in one call
        # without pagination; we filter client-side.
        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        since_utc = since_utc.astimezone(timezone.utc)
        start_time = since_utc
        headers = {"Authorization": f"Bearer {token}"}
        out: list[RawIngest] = []
        with httpx.Client(timeout=30.0, headers=headers) as client:
            for q in self._queries:
                try:
                    r = client.get(
                        TWITTER_SEARCH_URL,
                        params={
                            "query": q,
                            "max_results": 50,
                            "tweet.fields": "created_at,author_id,public_metrics,text",
                            "start_time": start_time.isoformat().replace("+00:00", "Z"),
                        },
                    )
                    r.raise_for_status()
                    payload = r.json()
                except httpx.HTTPError as e:
                    logger.warning("Twitter query failed (%s): %s", q[:40], e)
                    continue
                for tw in payload.get("data", []) or []:
                    created_raw = tw.get("created_at")
                    if not created_raw:
                        continue
                    created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    else:
                        created = created.astimezone(timezone.utc)
                    if created < since_utc:
                        continue
                    metrics = tw.get("public_metrics") or {}
                    tid = tw.get("id")
                    out.append(
                        RawIngest(
                            source_type=self.source_type,
                            source_id="twitter_search",
                            external_id=str(tid),
                            url=f"https://twitter.com/i/web/status/{tid}",
                            title=None,
                            body_text=tw.get("text") or "",
                            author=str(tw.get("author_id")),
                            published_at=created,
                            engagement={
                                "retweets": metrics.get("retweet_count"),
                                "likes": metrics.get("like_count"),
                                "comment_count": metrics.get("reply_count"),
                            },
                            raw_payload=tw,
                        )
                    )
        logger.info("Twitter: collected %d tweets", len(out))
        return out
