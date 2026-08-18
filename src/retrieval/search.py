"""Semantic search over ingested filing chunks, with full citation metadata."""

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from embeddings.encoder import encode_query
from retrieval.ingest import COLLECTION, get_qdrant_client


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    section_name: str
    page_number: int | None
    score: float
    accession_number: str
    ticker: str
    fiscal_year: int | None


def _build_filter(
    ticker: str | None,
    form_type: str | None,
    fiscal_year: int | None,
    section_name: str | None = None,
) -> Filter | None:
    conditions = []
    if ticker:
        conditions.append(FieldCondition(key="ticker", match=MatchValue(value=ticker.upper())))
    if form_type:
        conditions.append(FieldCondition(key="form_type", match=MatchValue(value=form_type)))
    if fiscal_year:
        conditions.append(FieldCondition(key="fiscal_year", match=MatchValue(value=fiscal_year)))
    if section_name:
        conditions.append(FieldCondition(key="section_name", match=MatchValue(value=section_name)))
    return Filter(must=conditions) if conditions else None


def search(
    query: str,
    ticker: str | None = None,
    form_type: str | None = "10-K",
    fiscal_year: int | None = None,
    section_name: str | None = None,
    top_k: int = 5,
    client: QdrantClient | None = None,
) -> list[RetrievedChunk]:
    client = client or get_qdrant_client()
    query_vector = encode_query(query)
    query_filter = _build_filter(ticker, form_type, fiscal_year, section_name)

    response = client.query_points(
        collection_name=COLLECTION,
        query=query_vector.tolist(),
        query_filter=query_filter,
        limit=top_k,
    )

    return [
        RetrievedChunk(
            chunk_id=str(p.id),
            text=p.payload["text"],
            section_name=p.payload["section_name"],
            page_number=p.payload.get("page_number"),
            score=p.score,
            accession_number=p.payload["accession_number"],
            ticker=p.payload["ticker"],
            fiscal_year=p.payload.get("fiscal_year"),
        )
        for p in response.points
    ]
