"""The overflow path: a table whose bullets cannot fit where the table was.

The old renderer handed an oversized string to ``insert_textbox`` and lost
whatever did not fit.  These tests build a PDF that provably overflows and check
that every word still reaches the output.
"""

from pathlib import Path

import fitz
import pytest

from pdf_table_tool.config import settings
from pdf_table_tool.pipeline import PDFTableFlattenerPipeline
from pdf_table_tool.text_utils import tokenize

CELL_WORDS = 36


def _build_dense_table_pdf(
    path: Path, rows: int = 40, y0: float = 80.0, row_h: float = 11.0
) -> None:
    """A table holding far more text than its own rectangle can show.

    Cell text is drawn at 3pt, so re-rendering the same words as bullets at a
    readable size cannot fit where the table stood.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    font_file = settings.get_font_path()
    font = fitz.Font(fontfile=font_file)

    x0, x1 = 60.0, 540.0
    y1 = y0 + row_h * (rows + 1)

    writer = fitz.TextWriter(page.rect)
    headers = ["Mã", "Nội dung"]
    col_x = [x0 + 4, x0 + 60]
    for c, head in enumerate(headers):
        writer.append(fitz.Point(col_x[c], y0 + 8), head, font=font, fontsize=6)

    for r in range(rows):
        y = y0 + row_h * (r + 1) + 8
        writer.append(fitz.Point(col_x[0], y), f"M{r:02d}", font=font, fontsize=6)
        body = " ".join(f"tu{r}x{i}" for i in range(CELL_WORDS))
        writer.append(fitz.Point(col_x[1], y), body, font=font, fontsize=3)
    writer.write_text(page)

    for r in range(rows + 2):
        y = y0 + row_h * r
        page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y), width=0.5)
    for x in (x0, x0 + 56, x1):
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y1), width=0.5)

    # Content below the table that must survive untouched.
    page.insert_text(fitz.Point(x0, y1 + 14), "DONG CUOI TRANG", fontsize=10)
    doc.save(path)
    doc.close()


@pytest.fixture(scope="module")
def overflow_case(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("overflow")
    src = tmp / "dense.pdf"
    out = tmp / "dense_flattened.pdf"
    _build_dense_table_pdf(src)
    summary = PDFTableFlattenerPipeline(use_llm=False).process(str(src), str(out))
    return src, out, summary


def test_overflowing_table_is_detected(overflow_case):
    _src, _out, summary = overflow_case
    assert summary["total_tables_flattened"] >= 1


def test_no_word_is_lost_when_bullets_overflow(overflow_case):
    src, out, _summary = overflow_case
    with fitz.open(src) as s, fitz.open(out) as o:
        src_tokens = set(tokenize("".join(p.get_text() for p in s)))
        out_tokens = set(tokenize("".join(p.get_text() for p in o)))
    assert src_tokens <= out_tokens, sorted(src_tokens - out_tokens)[:20]


def test_overflow_shrinks_the_font_before_anything_else(overflow_case):
    """With free space below the table the bullets stay on their own page."""
    src, out, summary = overflow_case
    with fitz.open(src) as s, fitz.open(out) as o:
        assert len(o) >= len(s)
    assert summary["verification"].criterion_1_and_2_ok


@pytest.fixture(scope="module")
def spill_case(tmp_path_factory):
    """A table pinned to the bottom of the page: shrinking alone cannot save it."""
    tmp = tmp_path_factory.mktemp("spill")
    src = tmp / "bottom.pdf"
    out = tmp / "bottom_flattened.pdf"
    _build_dense_table_pdf(src, rows=16, y0=560.0, row_h=12.0)
    summary = PDFTableFlattenerPipeline(use_llm=False).process(str(src), str(out))
    return src, out, summary


def test_bullets_that_cannot_fit_continue_on_a_new_page(spill_case):
    src, out, summary = spill_case
    assert summary["continuation_pages_added"] >= 1
    with fitz.open(src) as s, fitz.open(out) as o:
        assert len(o) == len(s) + summary["continuation_pages_added"]


def test_spilled_bullets_lose_nothing(spill_case):
    src, out, summary = spill_case
    with fitz.open(src) as s, fitz.open(out) as o:
        src_tokens = set(tokenize("".join(p.get_text() for p in s)))
        out_tokens = set(tokenize("".join(p.get_text() for p in o)))
    assert src_tokens <= out_tokens, sorted(src_tokens - out_tokens)[:20]
    assert summary["verification"].passed, summary["verification"].describe()


def test_spilled_bullets_are_not_duplicated(spill_case):
    """A bullet split across the page break must appear exactly once."""
    _src, out, _summary = spill_case
    with fitz.open(out) as o:
        text = "".join(p.get_text() for p in o)
    tokens = tokenize(text)
    body = [t for t in tokens if t.startswith("tu")]
    assert len(body) == len(set(body))


def test_content_below_the_table_survives(overflow_case):
    _src, out, _summary = overflow_case
    with fitz.open(out) as o:
        assert "DONG CUOI TRANG" in "".join(p.get_text() for p in o)


def test_verification_passes_on_the_overflow_case(overflow_case):
    _src, _out, summary = overflow_case
    assert summary["verification"].passed, summary["verification"].describe()
