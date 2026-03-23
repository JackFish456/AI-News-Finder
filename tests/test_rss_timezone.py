from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from news_agent.collectors.rss_collector import _parse_dt


def test_parse_published_parsed_as_utc_aware() -> None:
    entry = SimpleNamespace(published_parsed=(2024, 6, 15, 14, 30, 0, 0, 0, 0))
    dt = _parse_dt(entry)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt == datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "published,expect_hour",
    [
        ("Mon, 15 Jun 2024 14:30:00 GMT", 14),
        ("Mon, 15 Jun 2024 10:30:00 -0400", 14),
    ],
)
def test_parse_published_string_normalizes_to_utc(published: str, expect_hour: int) -> None:
    entry = SimpleNamespace(published_parsed=None, published=published)
    dt = _parse_dt(entry)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.hour == expect_hour
