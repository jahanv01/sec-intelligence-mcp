"""Tests for edgar/parser.py: HTML/PDF text extraction and DuckDB storage."""

from types import SimpleNamespace

import pytest

from edgar import parser
from edgar.filings import Filing

FAKE_FILING = Filing(
    cik="0000320193",
    ticker="AAPL",
    form_type="10-K",
    filing_date="2025-10-31",
    accession_number="0000320193-25-000079",
    primary_doc_url="https://www.sec.gov/Archives/edgar/data/320193/x/aapl-20250927.htm",
)

FAKE_HTML = b"""
<html><head><style>body{color:red}</style><script>alert(1)</script></head>
<body>
  <h1>Apple Inc.</h1>
  <p>Item 1. Business</p>
  <p>We design, manufacture and market smartphones.</p>
</body></html>
"""


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "DB_PATH", tmp_path / "edgar.duckdb")


def test_extract_html_text_strips_tags_and_script_style():
    text = parser.extract_html_text(FAKE_HTML)
    assert "Apple Inc." in text
    assert "smartphones" in text
    assert "alert(1)" not in text
    assert "color:red" not in text
    assert "<h1>" not in text


def test_fetch_and_parse_filing_html(monkeypatch):
    monkeypatch.setattr(
        parser.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            content=FAKE_HTML, raise_for_status=lambda: None
        ),
    )
    result = parser.fetch_and_parse_filing(FAKE_FILING)
    assert result.accession_number == FAKE_FILING.accession_number
    assert "smartphones" in result.raw_text
    assert result.page_count is None


def test_fetch_and_parse_filing_persists_to_duckdb(monkeypatch):
    monkeypatch.setattr(
        parser.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            content=FAKE_HTML, raise_for_status=lambda: None
        ),
    )
    parser.fetch_and_parse_filing(FAKE_FILING)

    import duckdb

    with duckdb.connect(str(parser.DB_PATH)) as conn:
        row = conn.execute(
            "SELECT accession_number, raw_text FROM filing_content WHERE accession_number = ?",
            [FAKE_FILING.accession_number],
        ).fetchone()
    assert row is not None
    assert "smartphones" in row[1]


def test_pdf_extraction_uses_pdfplumber(monkeypatch):
    pdf_filing = FAKE_FILING.model_copy(update={"primary_doc_url": "https://example.com/doc.pdf"})

    fake_page_1 = SimpleNamespace(extract_text=lambda: "page one text")
    fake_page_2 = SimpleNamespace(extract_text=lambda: "page two text")

    class FakePDF:
        pages = [fake_page_1, fake_page_2]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    import pdfplumber

    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: FakePDF())
    monkeypatch.setattr(
        parser.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            content=b"%PDF-fake", raise_for_status=lambda: None
        ),
    )

    result = parser.fetch_and_parse_filing(pdf_filing)
    assert result.page_count == 2
    assert "page one text" in result.raw_text
    assert "page two text" in result.raw_text
