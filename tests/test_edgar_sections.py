"""Tests for edgar/sections.py: section boundary detection and metadata extraction."""

import pytest

from edgar import sections
from edgar.parser import ParsedFiling


@pytest.mark.parametrize(
    "line,expected_key",
    [
        ("Item 1A. Risk Factors", "1A"),
        ("ITEM 1A: Risk Factors", "1A"),
        ("Item 1A - Risk Factors", "1A"),
        ("item 1a", "1A"),
        ("Item 7A—Quantitative Disclosures", "7A"),
        ("Item 7", "7"),
        ("Item 10", "10"),
    ],
)
def test_item_regex_matches_punctuation_variants(line, expected_key):
    m = sections._ITEM_LINE_RE.match(line)
    assert m is not None
    assert m.group(1).upper() == expected_key


def test_item_regex_rejects_multidigit_overrun():
    m = sections._ITEM_LINE_RE.match("Item 1099 of the code")
    assert m is None or m.group(1).upper() not in sections._CANONICAL_ITEMS_SET


def _build_fixture() -> str:
    toc = "\n".join(
        [
            "TABLE OF CONTENTS",
            "Item 1. Business",
            "Item 1A. Risk Factors",
            "Item 7. Management's Discussion and Analysis",
        ]
    )
    body = "\n".join(
        [
            "Apple Inc.",
            "(Exact name of Registrant as specified in its charter)",
            "For the fiscal year ended September 27, 2025",
            toc,
            "PART I",
            "Item 1. Business",
            "We design, manufacture and market smartphones and other devices.",
            "Item 1A. Risk Factors",
            "Our business is subject to a number of real, substantive risk factors described here.",
            "Item 7. Management's Discussion and Analysis",
            "Revenue increased year over year driven by strong iPhone sales performance.",
            "Report of Independent Registered Public Accounting Firm",
            "Ernst & Young LLP",
            "We have audited the accompanying financial statements.",
        ]
    )
    return body


def test_detect_sections_skips_toc_false_positives():
    text = _build_fixture()
    result = sections.detect_sections(text)
    item_1a = next(s for s in result if s.section_name == "Item 1A")
    assert "substantive risk factors" in item_1a.section_text
    assert "TABLE OF CONTENTS" not in item_1a.section_text


def test_detect_sections_finds_expected_keys():
    result = sections.detect_sections(_build_fixture())
    names = {s.section_name for s in result}
    assert {"Item 1", "Item 1A", "Item 7"} <= names


def test_section_offsets_are_consistent():
    text = _build_fixture()
    result = sections.detect_sections(text)
    assert result == sorted(result, key=lambda s: s.char_start)
    for s in result:
        assert text[s.char_start : s.char_end] == s.section_text
        assert s.char_end - s.char_start == len(s.section_text)
    for a, b in zip(result, result[1:], strict=False):
        assert a.char_end <= b.char_start


def test_detect_sections_empty_text_returns_empty_list():
    assert sections.detect_sections("") == []


def test_extract_metadata_all_fields():
    metadata = sections.extract_metadata(_build_fixture())
    assert metadata.company_name == "Apple Inc."
    assert metadata.fiscal_year_end == "September 27, 2025"
    assert metadata.report_date == "September 27, 2025"
    assert metadata.auditor == "Ernst & Young LLP"


def test_extract_metadata_missing_fields_returns_none():
    metadata = sections.extract_metadata("just some unrelated garbage text")
    assert metadata.company_name is None
    assert metadata.fiscal_year_end is None
    assert metadata.report_date is None
    assert metadata.auditor is None


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sections, "DB_PATH", tmp_path / "edgar.duckdb")


def test_store_sections_persists_to_duckdb(_isolated_db):
    parsed = ParsedFiling(accession_number="0000320193-25-000079", raw_text=_build_fixture())
    result = sections.parse_and_store_sections(parsed)
    assert len(result) >= 3

    import duckdb

    with duckdb.connect(str(sections.DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT section_name FROM filing_sections WHERE accession_number = ?",
            [parsed.accession_number],
        ).fetchall()
    assert {r[0] for r in rows} == {s.section_name for s in result}


def test_store_sections_upsert_on_reparse(_isolated_db):
    accession = "0000320193-25-000079"
    sections.store_sections(
        accession,
        [sections.Section(section_name="Item 1", section_text="old", char_start=0, char_end=3)],
    )
    sections.store_sections(
        accession,
        [
            sections.Section(
                section_name="Item 1", section_text="new text", char_start=0, char_end=8
            )
        ],
    )

    import duckdb

    with duckdb.connect(str(sections.DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT section_text FROM filing_sections WHERE accession_number = ?", [accession]
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "new text"
