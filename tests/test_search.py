"""Tests for retrieval/search.py: query filtering and citation metadata mapping."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from retrieval import search


@pytest.fixture(autouse=True)
def _fake_encode_query(monkeypatch):
    monkeypatch.setattr(search, "encode_query", lambda q: np.zeros(768, dtype=np.float32))


def _fake_point(score: float, **payload_overrides) -> SimpleNamespace:
    payload = {
        "text": "Data center revenue grew significantly.",
        "section_name": "Item 7",
        "page_number": None,
        "accession_number": "0001045810-25-000023",
        "ticker": "NVDA",
        "fiscal_year": 2025,
        **payload_overrides,
    }
    return SimpleNamespace(id="fake-chunk-id", payload=payload, score=score)


def test_search_maps_points_to_retrieved_chunks():
    client = MagicMock()
    client.query_points.return_value = SimpleNamespace(points=[_fake_point(0.87)])

    results = search.search("data center revenue growth", ticker="NVDA", client=client)

    assert len(results) == 1
    chunk = results[0]
    assert chunk.text == "Data center revenue grew significantly."
    assert chunk.section_name == "Item 7"
    assert chunk.score == 0.87
    assert chunk.accession_number == "0001045810-25-000023"
    assert chunk.ticker == "NVDA"
    assert chunk.fiscal_year == 2025


def test_search_builds_filter_for_ticker_form_type_and_year():
    client = MagicMock()
    client.query_points.return_value = SimpleNamespace(points=[])

    search.search("revenue", ticker="nvda", form_type="10-K", fiscal_year=2025, client=client)

    call_kwargs = client.query_points.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    field_values = {c.key: c.match.value for c in query_filter.must}
    assert field_values == {"ticker": "NVDA", "form_type": "10-K", "fiscal_year": 2025}


def test_search_can_filter_by_section_name():
    client = MagicMock()
    client.query_points.return_value = SimpleNamespace(points=[])

    search.search("risk factors", ticker="NVDA", section_name="Item 1A", client=client)

    query_filter = client.query_points.call_args.kwargs["query_filter"]
    field_values = {c.key: c.match.value for c in query_filter.must}
    assert field_values["section_name"] == "Item 1A"


def test_search_with_no_filters_passes_none():
    client = MagicMock()
    client.query_points.return_value = SimpleNamespace(points=[])

    search.search("revenue", ticker=None, form_type=None, fiscal_year=None, client=client)

    assert client.query_points.call_args.kwargs["query_filter"] is None


def test_search_respects_top_k():
    client = MagicMock()
    client.query_points.return_value = SimpleNamespace(points=[])

    search.search("revenue", top_k=3, client=client)

    assert client.query_points.call_args.kwargs["limit"] == 3
