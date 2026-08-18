"""Tests for retrieval/rerank.py: cross-encoder re-ranking."""

import numpy as np

from retrieval import rerank
from retrieval.search import RetrievedChunk


def _fake_chunk(chunk_id: str, text: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        section_name="Item 7",
        page_number=None,
        score=score,
        accession_number="acc-1",
        ticker="NVDA",
        fiscal_year=2025,
    )


class _FakeCrossEncoder:
    def __init__(self, score_by_text: dict[str, float]):
        self.score_by_text = score_by_text

    def predict(self, pairs):
        return np.array([self.score_by_text[text] for _query, text in pairs])


def test_rerank_empty_chunks_returns_empty(monkeypatch):
    assert rerank.rerank("query", []) == []


def test_rerank_reorders_by_cross_encoder_score(monkeypatch):
    chunks = [
        _fake_chunk("c1", "irrelevant passage about the weather", score=0.9),  # high cosine
        _fake_chunk("c2", "the passage that actually answers the question", score=0.7),
    ]
    fake_model = _FakeCrossEncoder(
        {
            "irrelevant passage about the weather": 0.1,
            "the passage that actually answers the question": 8.5,
        }
    )
    monkeypatch.setattr(rerank, "_model", fake_model)

    result = rerank.rerank("query", chunks)

    assert result[0].chunk_id == "c2"
    assert result[0].score == 8.5
    assert result[1].chunk_id == "c1"


def test_rerank_respects_top_k(monkeypatch):
    chunks = [_fake_chunk(f"c{i}", f"text {i}", score=0.5) for i in range(10)]
    fake_model = _FakeCrossEncoder({f"text {i}": float(i) for i in range(10)})
    monkeypatch.setattr(rerank, "_model", fake_model)

    result = rerank.rerank("query", chunks, top_k=3)

    assert len(result) == 3
    assert [c.chunk_id for c in result] == ["c9", "c8", "c7"]


def test_rerank_preserves_other_chunk_fields(monkeypatch):
    chunks = [_fake_chunk("c1", "some text", score=0.5)]
    monkeypatch.setattr(rerank, "_model", _FakeCrossEncoder({"some text": 3.0}))

    result = rerank.rerank("query", chunks)

    assert result[0].section_name == "Item 7"
    assert result[0].accession_number == "acc-1"
    assert result[0].ticker == "NVDA"
