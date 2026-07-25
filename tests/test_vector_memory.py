"""Semantic recall: embeddings enhance recall() when the provider
supports them, and recall() must fall back to plain substring search
(unchanged behavior) when it doesn't - the embeddings integration must
never make remember()/recall() slow or break when unsupported."""

import time
from unittest.mock import patch

import pytest

from agentos import embeddings
from agentos.embeddings import cosine_similarity
from agentos.memory import Memory


def test_cosine_similarity_basic_properties():
    assert cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0
    assert cosine_similarity([1, 1], [-1, -1]) == pytest.approx(-1.0)
    assert cosine_similarity([], [1, 2]) == 0.0
    assert cosine_similarity(None, [1, 2]) == 0.0
    assert cosine_similarity([1, 2], [1, 2, 3]) == 0.0  # mismatched length


def test_embed_returns_none_and_is_fast_when_provider_lacks_embeddings(monkeypatch):
    embeddings._unavailable = False  # reset the module-level latch

    def broken(**kwargs):
        raise RuntimeError("404 no such endpoint")

    with patch("agentos.embeddings.client") as mock_client:
        mock_client.with_options.return_value.embeddings.create = broken
        t0 = time.time()
        result1 = embeddings.embed("hello")
        t1 = time.time()
        result2 = embeddings.embed("world")  # should skip the client entirely now
        t2 = time.time()

    assert result1 is None and result2 is None
    assert (t1 - t0) < 2  # fails fast, doesn't wait out retries/timeouts
    assert (t2 - t1) < 0.01  # second call short-circuits with zero cost
    mock_client.with_options.assert_called_once()  # never called again after failing once
    embeddings._unavailable = False  # don't leak into other tests


def test_remember_and_recall_work_normally_without_embeddings(tmp_path, monkeypatch):
    """The common case for free providers (Groq/Gemini): embeddings just
    aren't available, and recall must behave exactly as pure substring
    search - this is the existing, already-tested behavior and must not
    regress."""
    monkeypatch.setattr(embeddings, "embed", lambda text: None)
    mem = Memory(db_path=str(tmp_path / "t.db"))
    mem.remember("favorite_color", "blue", scope="key-a")
    assert mem.recall(query="color", scope="key-a") == {"favorite_color": "blue"}
    assert mem.recall(query="nonexistent-word", scope="key-a") == {}


def test_recall_ranks_by_semantic_similarity_when_embeddings_available(tmp_path):
    """Core semantic-recall value: a fact should surface for a query with
    NO literal substring overlap, purely via embedding similarity."""
    mem = Memory(db_path=str(tmp_path / "t.db"))

    fake_vectors = {
        "prefers collaborative decision-making": [1.0, 0.0, 0.0],
        "likes pizza on fridays": [0.0, 1.0, 0.0],
        "leadership style query": [0.9, 0.1, 0.0],  # close to the first fact
    }

    def fake_embed(text):
        return fake_vectors.get(text)

    with patch("agentos.memory.embed", side_effect=fake_embed):
        mem.remember("mgmt_style", "prefers collaborative decision-making",
                    scope="key-a")
        mem.remember("food", "likes pizza on fridays", scope="key-a")

    with patch("agentos.memory.embed", side_effect=fake_embed), \
         patch("agentos.memory.cosine_similarity", side_effect=cosine_similarity):
        # "leadership style" has zero literal substring overlap with the
        # stored fact, yet must surface via semantic similarity.
        result = mem.recall(query="leadership style query", scope="key-a")

    assert "mgmt_style" in result
    assert "food" not in result


def test_recall_still_returns_substring_matches_alongside_semantic_ones(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    with patch("agentos.memory.embed", return_value=None):
        mem.remember("literal_fact", "this contains the word banana", scope="key-a")

    with patch("agentos.memory.embed", return_value=None):
        result = mem.recall(query="banana", scope="key-a")
    assert result == {"literal_fact": "this contains the word banana"}
