from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
    )

    database_url: str = Field(
        default="sqlite:///./data/news_agent.sqlite3",
        alias="DATABASE_URL",
    )

    reddit_enabled: bool = Field(default=False, alias="REDDIT_ENABLED")
    reddit_client_id: str = Field(default="", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(
        default="ai-news-brief/0.1 (local)",
        alias="REDDIT_USER_AGENT",
    )

    twitter_enabled: bool = Field(default=False, alias="TWITTER_ENABLED")
    twitter_bearer_token: str = Field(default="", alias="TWITTER_BEARER_TOKEN")

    news_agent_config: Path = Field(
        default=Path("config/default.yaml"),
        alias="NEWS_AGENT_CONFIG",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    mock_external_apis: bool = Field(default=False, alias="MOCK_EXTERNAL_APIS")

    pipeline_since_hours: float = Field(default=24.0, alias="PIPELINE_SINCE_HOURS")

    output_dir: Path = Field(default=Path("outputs"), alias="OUTPUT_DIR")


def get_settings() -> Settings:
    return Settings()
