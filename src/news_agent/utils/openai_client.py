from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from news_agent.settings import Settings
from news_agent.storage.repository import RunRepository
from news_agent.utils.hashing import item_cache_key

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OpenAiJsonClient:
    """Chat completions with JSON parsing, retries, and optional DB cache."""

    def __init__(
        self,
        settings: Settings,
        repo: RunRepository | None = None,
        cache_ttl_seconds: int | None = None,
    ):
        self._settings = settings
        self._repo = repo
        self._cache_ttl = cache_ttl_seconds
        self._client: OpenAI | None = None
        if settings.openai_api_key:
            self._client = OpenAI(api_key=settings.openai_api_key)

    @property
    def available(self) -> bool:
        return self._client is not None

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        reraise=True,
    )
    def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        cache_key_parts: dict[str, Any] | None = None,
        cache_namespace: str = "json",
    ) -> T:
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY is not set")

        cache_key = None
        if self._repo and cache_key_parts is not None:
            cache_key = item_cache_key(cache_namespace, {"m": model, **cache_key_parts})
            cached = self._repo.get_llm_cache(cache_key)
            if cached:
                return response_model.model_validate(cached)

        resp = self._client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        parsed = response_model.model_validate(data)

        if self._repo and cache_key:
            self._repo.set_llm_cache(
                cache_key,
                model,
                parsed.model_dump(),
                self._cache_ttl,
            )
        return parsed

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        reraise=True,
    )
    def embed_texts(self, model: str, texts: list[str]) -> list[list[float]]:
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY is not set")
        if not texts:
            return []
        resp = self._client.embeddings.create(model=model, input=texts)
        by_index = {d.index: d.embedding for d in resp.data}
        return [by_index[i] for i in range(len(texts))]
