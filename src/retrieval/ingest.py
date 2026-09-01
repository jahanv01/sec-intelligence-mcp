"""Embed filing chunks and upsert them into the Qdrant sec_filings collection."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import QDRANT_API_KEY, QDRANT_URL
from edgar.parser import ParsedFiling
from embeddings.chunker import chunk_filing
from embeddings.encoder import encode_passages

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "edgar.duckdb"
COLLECTION = "sec_filings"
VECTOR_SIZE = 768
BATCH_SIZE = 100

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingested_filings (
    accession_number TEXT PRIMARY KEY,
    chunk_count INTEGER NOT NULL,
    ingested_at TIMESTAMP NOT NULL
)
"""

# Mirrors what's stored in Qdrant's payload, keyed by the same point ID, so BM25 (over this
# table) and dense search (over Qdrant) can be fused by ID via hybrid.py's RRF merge.
_CREATE_CHUNKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filing_chunks (
    chunk_id TEXT PRIMARY KEY,
    accession_number TEXT NOT NULL,
    ticker TEXT NOT NULL,
    form_type TEXT NOT NULL,
    fiscal_year INTEGER,
    section_name TEXT NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    chunk_level TEXT NOT NULL,
    char_start INTEGER
)
"""

# CREATE TABLE IF NOT EXISTS doesn't add columns to an already-existing table (e.g. this
# project's dev DB, populated before char_start existed) -- this migration makes the column
# show up either way. Old rows just read back NULL, same graceful-missing-metadata pattern
# already used for page_number.
_ADD_CHAR_START_COLUMN_SQL = """
ALTER TABLE filing_chunks ADD COLUMN IF NOT EXISTS char_start INTEGER
"""


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def get_ingested_fiscal_years(ticker: str, form_type: str = "10-K") -> list[int]:
    """Fiscal years already ingested for this ticker/form_type, most recent first."""
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        rows = conn.execute(
            """
            SELECT DISTINCT f.filing_date FROM filings f
            JOIN ingested_filings i ON f.accession_number = i.accession_number
            WHERE f.ticker = ? AND f.form_type = ?
            ORDER BY f.filing_date DESC
            """,
            [ticker.upper(), form_type],
        ).fetchall()
    return [int(r[0][:4]) for r in rows]


def get_most_recent_ingested_fiscal_year(ticker: str, form_type: str = "10-K") -> int | None:
    years = get_ingested_fiscal_years(ticker, form_type)
    return years[0] if years else None


def get_full_section_text(
    ticker: str, fiscal_year: int, section_name: str, form_type: str = "10-K"
) -> str | None:
    """The complete text of one 10-K section (e.g. "Item 7") for a specific ticker/year, from
    the section-level chunk chunk_filing() already produces -- avoids re-fetching/re-parsing
    the filing just to get a section's full text."""
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_CHUNKS_TABLE_SQL)
        row = conn.execute(
            """
            SELECT text FROM filing_chunks
            WHERE ticker = ? AND fiscal_year = ? AND form_type = ?
              AND section_name = ? AND chunk_level = 'section'
            LIMIT 1
            """,
            [ticker.upper(), fiscal_year, form_type, section_name],
        ).fetchone()
    return row[0] if row else None


def _ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def _already_ingested(accession_number: str) -> int | None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        row = conn.execute(
            "SELECT chunk_count FROM ingested_filings WHERE accession_number = ?",
            [accession_number],
        ).fetchone()
    return row[0] if row else None


def _mark_ingested(accession_number: str, chunk_count: int) -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.execute(
            """
            INSERT INTO ingested_filings (accession_number, chunk_count, ingested_at)
            VALUES (?, ?, ?)
            ON CONFLICT (accession_number) DO UPDATE SET
                chunk_count = excluded.chunk_count,
                ingested_at = excluded.ingested_at
            """,
            [accession_number, chunk_count, datetime.now(UTC)],
        )


def _point_id(accession_number: str, index: int) -> str:
    # deterministic (not random) so re-running ingestion after a partial failure overwrites
    # the same points instead of creating duplicates. Qdrant point IDs must be an unsigned
    # int or a UUID -- an arbitrary string like "accession:index" is not accepted.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{accession_number}:{index}"))


def ingest_filing(parsed_filing: ParsedFiling, client: QdrantClient | None = None) -> int:
    """Chunk, embed, and upsert a filing into Qdrant. Returns the chunk count.

    Skips re-embedding if this accession number was already ingested.
    """
    label = f"{parsed_filing.ticker} {parsed_filing.form_type} {parsed_filing.fiscal_year}"

    existing = _already_ingested(parsed_filing.accession_number)
    if existing is not None:
        print(f"Skipping {label}: already ingested ({existing} chunks)")
        return existing

    chunks = chunk_filing(parsed_filing)
    total = len(chunks)

    client = client or get_qdrant_client()
    _ensure_collection(client)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_CHUNKS_TABLE_SQL)
        conn.execute(_ADD_CHAR_START_COLUMN_SQL)

        for batch_start in range(0, total, BATCH_SIZE):
            batch = chunks[batch_start : batch_start + BATCH_SIZE]
            ids = [_point_id(c.accession_number, batch_start + i) for i, c in enumerate(batch)]
            vectors = encode_passages([c.text for c in batch])
            points = [
                PointStruct(
                    id=ids[i],
                    vector=vectors[i].tolist(),
                    payload={
                        "ticker": c.ticker,
                        "form_type": c.form_type,
                        "fiscal_year": c.fiscal_year,
                        "section_name": c.section_name,
                        "text": c.text,
                        "page_number": c.page_number,
                        "accession_number": c.accession_number,
                        "chunk_level": c.chunk_level,
                        "char_start": c.char_start,
                    },
                )
                for i, c in enumerate(batch)
            ]
            client.upsert(collection_name=COLLECTION, points=points)

            conn.executemany(
                """
                INSERT INTO filing_chunks
                    (chunk_id, accession_number, ticker, form_type, fiscal_year,
                     section_name, text, page_number, chunk_level, char_start)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (chunk_id) DO NOTHING
                """,
                [
                    (
                        ids[i],
                        c.accession_number,
                        c.ticker,
                        c.form_type,
                        c.fiscal_year,
                        c.section_name,
                        c.text,
                        c.page_number,
                        c.chunk_level,
                        c.char_start,
                    )
                    for i, c in enumerate(batch)
                ],
            )

            done = min(batch_start + BATCH_SIZE, total)
            print(f"Ingesting {label}... {done}/{total} chunks")

    _mark_ingested(parsed_filing.accession_number, total)
    return total
