from __future__ import annotations

from news_agent.clustering import embedding_cluster as ec


def test_pseudo_embedding_is_deterministic_across_calls() -> None:
    text = "openai releases batch api for enterprise customers"
    a = ec._pseudo_embedding(text)
    b = ec._pseudo_embedding(text)
    assert a == b
    assert len(a) == ec._PSEUDO_DIM


def test_pseudo_embedding_differs_for_different_text() -> None:
    u = ec._pseudo_embedding("alpha beta gamma")
    v = ec._pseudo_embedding("alpha beta delta")
    assert u != v
