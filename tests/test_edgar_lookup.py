"""Tests for edgar/lookup.py: DuckDB caching behavior for ticker -> CIK lookups."""

from types import SimpleNamespace

import pytest

from edgar import lookup

FAKE_TICKERS_RESPONSE = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(lookup, "DB_PATH", tmp_path / "edgar.duckdb")


@pytest.fixture
def _mock_http_get(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: FAKE_TICKERS_RESPONSE,
        )

    monkeypatch.setattr(lookup.httpx, "get", fake_get)
    return calls


def test_get_cik_returns_zero_padded_cik(_mock_http_get):
    assert lookup.get_cik("NVDA") == "0001045810"


def test_get_company_name(_mock_http_get):
    assert lookup.get_company_name("AAPL") == "Apple Inc."


def test_second_call_does_not_hit_network(_mock_http_get):
    lookup.get_cik("NVDA")
    lookup.get_cik("NVDA")
    assert len(_mock_http_get) == 1, "expected exactly one network call across two lookups"


def test_unknown_ticker_raises(_mock_http_get):
    with pytest.raises(ValueError, match="Unknown ticker"):
        lookup.get_cik("NOTAREALTICKER")


def test_lookup_is_case_insensitive(_mock_http_get):
    assert lookup.get_cik("nvda") == "0001045810"
