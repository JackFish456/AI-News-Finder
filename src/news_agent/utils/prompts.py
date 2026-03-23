from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path


def prompts_package_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt_text(relative_name: str) -> str:
    """
    Load a versioned prompt file from package `news_agent/prompts/`.
    `relative_name` e.g. 'post_quality_v1.txt'
    """
    base = prompts_package_dir()
    path = base / relative_name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    # Fallback for editable installs where files might be missing
    try:
        ref = resources.files("news_agent.prompts").joinpath(relative_name)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as e:
        raise FileNotFoundError(f"Prompt not found: {relative_name}") from e
