"""Tests for retrieval/ingest.py: chunking/embedding orchestration and dedup, mocked."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from edgar.parser import ParsedFiling
from retrieval import ingest


def _fixture_filing() -> ParsedFiling:
    body = "\n".join(
        [
            "Item 1. Business",
            "We design, manufacture and market smartphones and other devices.",
            "Item 7. Management's Discussion and Analysis",
            "Revenue increased year over year driven by strong sales performance.",
        ]
    )
    return ParsedFiling(
        accession_number="0000320193-25-000079",
        ticker="AAPL",
        form_type="10-K",
        fiscal_year=2025,
        raw_text=body,
    )


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "DB_PATH", tmp_path / "edgar.duckdb")


@pytest.fixture
def _fake_qdrant(monkeypatch):
    client = MagicMock()
    client.collection_exists.return_value = False
    monkeypatch.setattr(
        ingest, "encode_passages", lambda texts: np.zeros((len(texts), 768), dtype=np.float32)
    )
    return client


def test_ingest_filing_creates_collection_and_upserts(_fake_qdrant):
    count = ingest.ingest_filing(_fixture_filing(), client=_fake_qdrant)
    assert count > 0
    _fake_qdrant.create_collection.assert_called_once()
    assert _fake_qdrant.upsert.called


def test_ingest_filing_skips_already_ingested(_fake_qdrant):
    filing = _fixture_filing()
    first_count = ingest.ingest_filing(filing, client=_fake_qdrant)
    _fake_qdrant.reset_mock()

    second_count = ingest.ingest_filing(filing, client=_fake_qdrant)

    assert second_count == first_count
    _fake_qdrant.upsert.assert_not_called()
    _fake_qdrant.create_collection.assert_not_called()


def test_ingest_filing_does_not_recreate_existing_collection(_fake_qdrant):
    _fake_qdrant.collection_exists.return_value = True
    ingest.ingest_filing(_fixture_filing(), client=_fake_qdrant)
    _fake_qdrant.create_collection.assert_not_called()


def test_point_payload_has_citation_fields(_fake_qdrant):
    ingest.ingest_filing(_fixture_filing(), client=_fake_qdrant)
    points = _fake_qdrant.upsert.call_args.kwargs["points"]
    for p in points:
        for field in (
            "ticker",
            "form_type",
            "fiscal_year",
            "section_name",
            "text",
            "page_number",
            "accession_number",
        ):
            assert field in p.payload
