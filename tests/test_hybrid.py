"""Tests for retrieval/hybrid.py: BM25 ranking, RRF fusion, and hybrid_search."""

import duckdb
import pytest

from retrieval import hybrid
from retrieval.search import RetrievedChunk


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid, "DB_PATH", tmp_path / "edgar.duckdb")


def _seed_chunks(rows):
    with duckdb.connect(str(hybrid.DB_PATH)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS filing_chunks ("
            "chunk_id TEXT PRIMARY KEY, accession_number TEXT, ticker TEXT, form_type TEXT, "
            "fiscal_year INTEGER, section_name TEXT, text TEXT, page_number INTEGER, "
            "chunk_level TEXT)"
        )
        conn.executemany(
            "INSERT INTO filing_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r["chunk_id"],
                    "acc-1",
                    "NVDA",
                    "10-K",
                    2025,
                    r.get("section_name", "Item 7"),
                    r["text"],
                    None,
                    "paragraph",
                )
                for r in rows
            ],
        )


def test_rrf_fuse_combines_rankings():
    ranking_a = ["x", "y", "z"]
    ranking_b = ["x", "z", "y"]
    fused = hybrid._rrf_fuse([ranking_a, ranking_b])
    # x ranks 1st in both rankings -> unambiguously highest combined score
    assert fused[0] == "x"
    assert set(fused) == {"x", "y", "z"}


def test_rrf_fuse_empty_rankings_returns_empty():
    assert hybrid._rrf_fuse([[], []]) == []


def test_bm25_ranking_finds_exact_term_match():
    _seed_chunks(
        [
            {"chunk_id": "c1", "text": "Deferred revenue increased due to subscription growth."},
            {"chunk_id": "c2", "text": "The weather was mild across our retail locations."},
            {"chunk_id": "c3", "text": "Revenue grew due to strong iPhone sales performance."},
        ]
    )
    corpus = hybrid._fetch_corpus("NVDA", "10-K", None)
    ranking = hybrid._bm25_ranking("deferred revenue", corpus)
    assert ranking[0] == "c1"


def test_hybrid_search_merges_bm25_and_semantic(monkeypatch):
    _seed_chunks(
        [
            {"chunk_id": "c1", "text": "Deferred revenue was $13.7 billion as of fiscal year end."},
            {"chunk_id": "c2", "text": "Our growth strategy focuses on long-term customer value."},
        ]
    )

    def fake_semantic_search(query, **kwargs):
        return [
            RetrievedChunk(
                chunk_id="c2",
                text="Our growth strategy focuses on long-term customer value.",
                section_name="Item 7",
                page_number=None,
                score=0.82,
                accession_number="acc-1",
                ticker="NVDA",
                fiscal_year=2025,
            )
        ]

    monkeypatch.setattr(hybrid, "_semantic_search", fake_semantic_search)

    results = hybrid.hybrid_search("deferred revenue", "NVDA", top_k=5)
    result_ids = {r.chunk_id for r in results}
    # both the BM25-only match (c1) and the semantic-only match (c2) should surface
    assert "c1" in result_ids
    assert "c2" in result_ids


def test_hybrid_search_respects_top_k(monkeypatch):
    _seed_chunks([{"chunk_id": f"c{i}", "text": f"revenue figure number {i}"} for i in range(10)])
    monkeypatch.setattr(hybrid, "_semantic_search", lambda query, **kwargs: [])

    results = hybrid.hybrid_search("revenue", "NVDA", top_k=3)
    assert len(results) == 3
