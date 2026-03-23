from __future__ import annotations

from pathlib import Path

import pytest

from news_agent.jobs.daily_pipeline import run_daily_pipeline
from news_agent.settings import Settings


@pytest.fixture
def smoke_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db = (tmp_path / "smoke.sqlite3").resolve()
    out = (tmp_path / "outputs").resolve()
    cfg = Path(__file__).resolve().parent / "fixtures" / "smoke_config.yaml"
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.setenv("NEWS_AGENT_CONFIG", str(cfg))
    return Settings()


def test_daily_pipeline_smoke_mock_simple_writes_markdown(
    smoke_settings: Settings,
    tmp_path: Path,
) -> None:
    out = run_daily_pipeline(
        settings=smoke_settings,
        include_mock=True,
        write_reports=True,
        output_dir=tmp_path / "run_out",
        simple=True,
    )

    assert out.get("run_id") is not None
    stats = out["stats"]
    assert stats["ingested"] >= 1
    assert stats["deduped"] >= 1
    assert stats["clusters"] >= 1

    brief = out["brief"]
    assert brief["top_stories"], "expected non-empty top_stories from mock data"

    artifacts = out.get("artifacts") or {}
    md_path = Path(artifacts["markdown"])
    assert md_path.is_file()
    text = md_path.read_text(encoding="utf-8")
    assert "# AI News Brief" in text
