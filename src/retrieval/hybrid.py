"""Hybrid retrieval: BM25 (term-heavy queries) + dense semantic search, merged via
Reciprocal Rank Fusion (RRF).

Her thesis found BM25 outperforms dense retrieval on term-heavy financial queries (specific
accounting terms, exact figures) while dense retrieval wins on narrative queries. Rather than
picking one, RRF blends both rankings so a chunk that ranks well in *either* system surfaces,
without needing to normalize/compare BM25 and cosine scores directly (which aren't on the
same scale).
"""

import re

import duckdb
from rank_bm25 import BM25Okapi

from retrieval.ingest import DB_PATH
from retrieval.search import RetrievedChunk
from retrieval.search import search as _semantic_search

RRF_K = 60
CANDIDATE_POOL_SIZE = 20  # candidates pulled from each system before fusion


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _fetch_corpus(
    ticker: str, form_type: str | None, fiscal_year: int | None
) -> list[tuple[str, str, str, int | None, str, int | None]]:
    """Returns (chunk_id, text, section_name, page_number, accession_number, fiscal_year)."""
    sql = (
        "SELECT chunk_id, text, section_name, page_number, accession_number, fiscal_year "
        "FROM filing_chunks WHERE ticker = ?"
    )
    params: list = [ticker.upper()]
    if form_type:
        sql += " AND form_type = ?"
        params.append(form_type)
    if fiscal_year:
        sql += " AND fiscal_year = ?"
        params.append(fiscal_year)

    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS filing_chunks ("
            "chunk_id TEXT PRIMARY KEY, accession_number TEXT, ticker TEXT, form_type TEXT, "
            "fiscal_year INTEGER, section_name TEXT, text TEXT, page_number INTEGER, "
            "chunk_level TEXT)"
        )
        return conn.execute(sql, params).fetchall()


def _bm25_ranking(query: str, corpus: list[tuple]) -> list[str]:
    """Returns chunk_ids ranked best-first by BM25 score."""
    if not corpus:
        return []
    tokenized_docs = [_tokenize(row[1]) for row in corpus]
    bm25 = BM25Okapi(tokenized_docs)
    scores = bm25.get_scores(_tokenize(query))
    ranked_indices = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
    return [corpus[i][0] for i in ranked_indices[:CANDIDATE_POOL_SIZE]]


def _rrf_fuse(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """RRF: score(d) = sum(1 / (k + rank_i(d))) across each ranking d appears in (1-indexed
    rank). Returns chunk_ids ordered best-first."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)


def hybrid_search(
    query: str,
    ticker: str,
    form_type: str | None = "10-K",
    fiscal_year: int | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    corpus = _fetch_corpus(ticker, form_type, fiscal_year)
    corpus_by_id = {row[0]: row for row in corpus}

    bm25_ranking = _bm25_ranking(query, corpus)
    semantic_results = _semantic_search(
        query,
        ticker=ticker,
        form_type=form_type,
        fiscal_year=fiscal_year,
        top_k=CANDIDATE_POOL_SIZE,
    )
    semantic_by_id = {r.chunk_id: r for r in semantic_results}
    semantic_ranking = [r.chunk_id for r in semantic_results]

    fused_ids = _rrf_fuse([bm25_ranking, semantic_ranking])[:top_k]

    results = []
    for chunk_id in fused_ids:
        if chunk_id in semantic_by_id:
            results.append(semantic_by_id[chunk_id])
        elif chunk_id in corpus_by_id:
            _, text, section_name, page_number, accession_number, fy = corpus_by_id[chunk_id]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=text,
                    section_name=section_name,
                    page_number=page_number,
                    score=0.0,  # BM25-only match: no cosine score to report
                    accession_number=accession_number,
                    ticker=ticker.upper(),
                    fiscal_year=fy,
                )
            )
    return results
