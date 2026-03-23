from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from news_agent.collectors.base import RawIngest, SourceCollector
from news_agent.settings import Settings

logger = logging.getLogger(__name__)

REDDIT_OAUTH = "https://www.reddit.com/api/v1/access_token"
REDDIT_OAUTH_API = "https://oauth.reddit.com"


class RedditCollector(SourceCollector):
    """
    Fetches new posts from configured subreddits.

    Requires REDDIT_ENABLED=true and client credentials (application-only OAuth).
    TODO: Add user OAuth if you need higher rate limits or private subs.
    """

    source_type = "reddit"

    def __init__(self, settings: Settings, subreddits: list[str]):
        self._settings = settings
        self._subs = subreddits

    def _token(self) -> str | None:
        if not self._settings.reddit_enabled:
            return None
        cid = self._settings.reddit_client_id
        csec = self._settings.reddit_client_secret
        if not cid or not csec:
            logger.warning(
                "Reddit enabled but REDDIT_CLIENT_ID/SECRET missing; skipping Reddit ingest."
            )
            return None
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                REDDIT_OAUTH,
                data={"grant_type": "client_credentials"},
                auth=(cid, csec),
                headers={"User-Agent": self._settings.reddit_user_agent},
            )
            r.raise_for_status()
            return r.json().get("access_token")

    def collect(self, since: datetime) -> list[RawIngest]:
        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        if not self._settings.reddit_enabled or self._settings.mock_external_apis:
            logger.info("Reddit collector skipped (disabled or mock mode).")
            return []

        token = self._token()
        if not token:
            return []

        out: list[RawIngest] = []
        headers = {
            "Authorization": f"bearer {token}",
            "User-Agent": self._settings.reddit_user_agent,
        }
        with httpx.Client(timeout=30.0, headers=headers, base_url=REDDIT_OAUTH_API) as client:
            for sub in self._subs:
                try:
                    r = client.get(f"/r/{sub}/new", params={"limit": 50})
                    r.raise_for_status()
                    data = r.json()
                except httpx.HTTPError as e:
                    logger.warning("Reddit /r/%s failed: %s", sub, e)
                    continue
                for child in data.get("data", {}).get("children", []) or []:
                    post: dict[str, Any] = child.get("data") or {}
                    created = datetime.fromtimestamp(
                        float(post.get("created_utc", 0)),
                        tz=timezone.utc,
                    )
                    if created < since_utc:
                        continue
                    permalink = post.get("permalink")
                    url = post.get("url_overridden_by_dest") or post.get("url")
                    if permalink and not str(url).startswith("http"):
                        url = "https://www.reddit.com" + str(permalink)
                    title = post.get("title") or ""
                    body = post.get("selftext") or ""
                    out.append(
                        RawIngest(
                            source_type=self.source_type,
                            source_id=f"reddit_{sub}",
                            external_id=post.get("name") or post.get("id"),
                            url=str(url or permalink or f"https://reddit.com/r/{sub}"),
                            title=title,
                            body_text=body or title,
                            author=post.get("author"),
                            published_at=created,
                            engagement={
                                "upvotes": post.get("ups"),
                                "score": post.get("score"),
                                "comment_count": post.get("num_comments"),
                            },
                            credibility_meta={"subreddit": sub},
                            raw_payload=post,
                        )
                    )
        logger.info("Reddit: collected %d posts", len(out))
        return out
