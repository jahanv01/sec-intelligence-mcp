"""Tests for embeddings/chunker.py: section + paragraph level chunking."""

from edgar.parser import ParsedFiling
from embeddings.chunker import chunk_filing

_LONG_LINE = (
    "The Company continues to invest heavily in research and development across its "
    "product lines, focusing on innovation, supply chain resilience, and customer "
    "experience improvements that management believes will drive long-term growth. "
)


def _long_section_text(n_lines: int = 40) -> str:
    return "\n".join(f"{_LONG_LINE}(paragraph {i})" for i in range(n_lines))


def _build_fixture() -> str:
    return "\n".join(
        [
            "Item 1. Business",
            "We design, manufacture and market smartphones and other devices.",
            "Item 1A. Risk Factors",
            _long_section_text(),
            "Item 7. Management's Discussion and Analysis",
            "Revenue increased year over year driven by strong sales performance.",
        ]
    )


def _fixture_filing() -> ParsedFiling:
    return ParsedFiling(
        accession_number="0000320193-25-000079",
        ticker="AAPL",
        form_type="10-K",
        fiscal_year=2025,
        raw_text=_build_fixture(),
    )


def test_every_chunk_has_complete_metadata():
    chunks = chunk_filing(_fixture_filing())
    assert chunks
    for c in chunks:
        assert c.ticker == "AAPL"
        assert c.form_type == "10-K"
        assert c.fiscal_year == 2025
        assert c.section_name
        assert c.accession_number == "0000320193-25-000079"
        assert c.char_start >= 0
        assert c.chunk_level in ("section", "paragraph")
        assert c.text.strip()


def test_one_section_level_chunk_per_section():
    chunks = chunk_filing(_fixture_filing())
    section_level = [c for c in chunks if c.chunk_level == "section"]
    assert {c.section_name for c in section_level} == {"Item 1", "Item 1A", "Item 7"}


def test_large_section_produces_multiple_paragraph_chunks_with_overlap():
    chunks = chunk_filing(_fixture_filing())
    para_chunks = [
        c for c in chunks if c.chunk_level == "paragraph" and c.section_name == "Item 1A"
    ]
    assert len(para_chunks) > 1, "a long section should split into multiple paragraph chunks"

    # consecutive paragraph chunks should overlap: the second chunk should start before
    # the first chunk ends (in the original raw_text)
    raw_text = _fixture_filing().raw_text
    first, second = para_chunks[0], para_chunks[1]
    first_end = first.char_start + len(first.text)
    assert second.char_start < first_end
    assert raw_text[second.char_start : second.char_start + 20] in first.text


def test_char_start_indexes_correctly_into_raw_text():
    filing = _fixture_filing()
    chunks = chunk_filing(filing)
    for c in chunks:
        if c.chunk_level == "paragraph":
            assert filing.raw_text[c.char_start :].startswith(c.text.split("\n")[0][:30])


def test_small_section_produces_single_paragraph_chunk():
    chunks = chunk_filing(_fixture_filing())
    item1_paras = [c for c in chunks if c.chunk_level == "paragraph" and c.section_name == "Item 1"]
    assert len(item1_paras) == 1
