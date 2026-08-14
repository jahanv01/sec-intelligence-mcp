"""Chunk filing text into section-level and paragraph-level pieces for embedding.

Two levels, per the design: one coarse chunk per detected section (for broad queries like
"what are Apple's main risks") and many finer paragraph-level chunks within each section
(for specific-fact queries). Paragraph chunks target ~512 tokens with ~50-token overlap so a
fact split across a chunk boundary is still findable in the neighboring chunk.

Paragraph chunks are built by greedily packing whole lines (parser.py already emits one line
per original HTML block) up to the token target, rather than slicing raw token windows. This
keeps char_start always exact -- slicing by token windows would require decoding partial BPE
tokens back to text, which is not guaranteed to round-trip cleanly across multi-byte Unicode
characters (tiktoken's own docs recommend errors="replace" for exactly this reason).
"""

import tiktoken
from pydantic import BaseModel

from edgar.parser import ParsedFiling
from edgar.sections import detect_sections

PARAGRAPH_CHUNK_TOKENS = 450
PARAGRAPH_CHUNK_OVERLAP_TOKENS = 50

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


class Chunk(BaseModel):
    text: str
    ticker: str
    form_type: str
    fiscal_year: int | None
    section_name: str
    accession_number: str
    char_start: int
    chunk_level: str  # "section" or "paragraph"
    page_number: int | None = None  # not tracked for HTML filings (the common case)


def _line_starts(text: str, lines: list[str]) -> list[int]:
    starts = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1  # +1 for the '\n' split() consumes
    return starts


def _paragraph_windows(section_text: str) -> list[tuple[str, int]]:
    """Returns (chunk_text, char_start) pairs via greedy line-packing to ~512 tokens
    with ~50-token overlap carried into the next window."""
    lines = section_text.split("\n")
    starts = _line_starts(section_text, lines)
    token_counts = [len(_TOKENIZER.encode(line)) for line in lines]

    windows: list[tuple[str, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        cur_lines: list[str] = []
        cur_tokens = 0
        j = i
        while j < n:
            if cur_tokens + token_counts[j] > PARAGRAPH_CHUNK_TOKENS and cur_lines:
                break
            cur_lines.append(lines[j])
            cur_tokens += token_counts[j]
            j += 1

        end_line = j - 1
        chunk_text = "\n".join(cur_lines)
        windows.append((chunk_text, starts[i]))

        if j >= n:
            break

        overlap_tokens = 0
        k = end_line
        while k > i and overlap_tokens < PARAGRAPH_CHUNK_OVERLAP_TOKENS:
            overlap_tokens += token_counts[k]
            k -= 1
        i = max(k + 1, i + 1)  # always make forward progress

    return windows


def _make_chunk(
    text: str, char_start: int, section_name: str, level: str, parsed_filing: ParsedFiling
) -> Chunk:
    return Chunk(
        text=text,
        ticker=parsed_filing.ticker,
        form_type=parsed_filing.form_type,
        fiscal_year=parsed_filing.fiscal_year,
        section_name=section_name,
        accession_number=parsed_filing.accession_number,
        char_start=char_start,
        chunk_level=level,
    )


def chunk_filing(parsed_filing: ParsedFiling) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in detect_sections(parsed_filing.raw_text):
        chunks.append(
            _make_chunk(
                section.section_text,
                section.char_start,
                section.section_name,
                "section",
                parsed_filing,
            )
        )
        for text, offset_in_section in _paragraph_windows(section.section_text):
            if not text.strip():
                continue
            chunks.append(
                _make_chunk(
                    text,
                    section.char_start + offset_in_section,
                    section.section_name,
                    "paragraph",
                    parsed_filing,
                )
            )
    return chunks
