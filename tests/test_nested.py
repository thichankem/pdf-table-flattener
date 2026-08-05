"""Tables drawn inside a cell keep their own column pairing.

Word renders a sub-table (``Nhóm chức danh | HMTC``) with its own ruling lines,
so it arrives as a separate table living inside a parent cell.  Pouring its
words into the parent turns ``I | 1.000`` into a loose ``I 1.000`` and loses
which value belongs to which column -- these tests pin the fix.
"""

from pathlib import Path

import fitz
import pdfplumber
import pytest

from pdf_table_tool.config import settings
from pdf_table_tool.formatter import TableFormatter
from pdf_table_tool.grid_extractor import build_grid
from pdf_table_tool.pipeline import PDFTableFlattenerPipeline
from pdf_table_tool.table_detector import TABLE_SETTINGS_LINES, detect_tables_by_page
from pdf_table_tool.text_utils import tokenize

ROOT = Path(__file__).resolve().parent.parent


def _build_nested_pdf(path: Path) -> None:
    """Outer 2-column table whose right cell holds a small 2-column sub-table."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    font = fitz.Font(fontfile=settings.get_font_path())

    writer = fitz.TextWriter(page.rect)
    for point, text in [
        ((70, 100), "STT"), ((170, 100), "Noi dung"),
        ((70, 130), "3.5"), ((170, 130), "Han muc thau chi"),
    ]:
        writer.append(fitz.Point(*point), text, font=font, fontsize=10)

    inner_rows = [("Nhom chuc danh", "HMTC"), ("I", "1.000"), ("II", "700"), ("III", "200")]
    for i, (a, b) in enumerate(inner_rows):
        y = 175 + i * 25
        writer.append(fitz.Point(230, y), a, font=font, fontsize=10)
        writer.append(fitz.Point(400, y), b, font=font, fontsize=10)
    writer.write_text(page)

    # Outer table rulings.
    for y in (85, 115, 290):
        page.draw_line(fitz.Point(60, y), fitz.Point(540, y), width=0.6)
    for x in (60, 160, 540):
        page.draw_line(fitz.Point(x, 85), fitz.Point(x, 290), width=0.6)

    # Inner table rulings, entirely inside the right-hand cell.
    for i in range(5):
        y = 160 + i * 25
        page.draw_line(fitz.Point(220, y), fitz.Point(520, y), width=0.6)
    for x in (220, 390, 520):
        page.draw_line(fitz.Point(x, 160), fitz.Point(x, 260), width=0.6)

    doc.save(path)
    doc.close()


@pytest.fixture(scope="module")
def nested_case(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("nested")
    src = tmp / "nested.pdf"
    out = tmp / "nested_flattened.pdf"
    _build_nested_pdf(src)
    summary = PDFTableFlattenerPipeline().process(str(src), str(out))
    return src, out, summary


def test_inner_table_is_detected_as_a_child(nested_case):
    src, _out, _summary = nested_case
    pages, _ = detect_tables_by_page(str(src))
    infos = pages[0]
    assert len(infos) == 1, "the inner table must not be flattened as a peer"
    assert infos[0].dropped_children, "the inner table must be recorded as a child"


def test_inner_table_keeps_its_column_pairing(nested_case):
    src, _out, _summary = nested_case
    pages, _ = detect_tables_by_page(str(src))
    info = pages[0][0]
    pipeline = PDFTableFlattenerPipeline(verify_output=False)
    with pdfplumber.open(src) as pdf:
        page = pdf.pages[0]
        blocks = pipeline._flatten_nested(page, info)
        assert blocks, "the child table produced no bullets"
        _bbox, child_lines = blocks[0]
        assert child_lines == [
            "- Nhom chuc danh: I  |  HMTC: 1.000",
            "- Nhom chuc danh: II  |  HMTC: 700",
            "- Nhom chuc danh: III  |  HMTC: 200",
        ]


def test_inner_bullets_are_spliced_into_the_parent_cell(nested_case):
    src, _out, _summary = nested_case
    pages, _ = detect_tables_by_page(str(src))
    info = pages[0][0]
    pipeline = PDFTableFlattenerPipeline(verify_output=False)
    with pdfplumber.open(src) as pdf:
        page = pdf.pages[0]
        blocks = pipeline._flatten_nested(page, info)
        grid = build_grid(page, info.raw_table, nested_blocks=blocks)
        lines, _ = TableFormatter().format_grid(grid)
    joined = "\n".join(lines)
    assert "Nhom chuc danh: I  |  HMTC: 1.000" in joined
    # The loose, unpaired form must be gone.
    assert "I 1.000" not in joined


def test_nested_case_loses_nothing_and_leaves_no_table(nested_case):
    src, out, summary = nested_case
    with fitz.open(src) as s, fitz.open(out) as o:
        assert set(tokenize("".join(p.get_text() for p in s))) <= set(
            tokenize("".join(p.get_text() for p in o))
        )
    assert summary["verification"].passed, summary["verification"].describe()


def test_no_table_survives_in_the_nested_case(nested_case):
    _src, out, _summary = nested_case
    with pdfplumber.open(out) as pdf:
        for page in pdf.pages:
            for table in page.find_tables(TABLE_SETTINGS_LINES):
                assert (table.bbox[2] - table.bbox[0]) <= 20 or (
                    table.bbox[3] - table.bbox[1]
                ) <= 15
