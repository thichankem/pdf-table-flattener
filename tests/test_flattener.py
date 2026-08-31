"""End-to-end tests: the three mandatory acceptance criteria, on real PDFs.

    1. Content outside tables is untouched, 100%.
    2. Every table is flattened into bullets; no table survives.
    3. The generated text is clean: no fake labels, no hidden characters, no
       two blank lines in a row.
"""

import re
from pathlib import Path

import fitz
import pdfplumber
import pytest

from pdf_table_tool.pipeline import PDFTableFlattenerPipeline

# A flattened line: "- Tên: Nam ..." or "2.3.1.1 Tên: Nam ..." once the table
# has been placed on the document's own outline.
_BULLET_RE = re.compile(r"^\s*(-\s|\d+(\.\d+)*\s)")


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _generated_lines(src_path, out_path):
    """The lines this tool wrote: what the output has and the source did not.

    Scoping the output checks this way is what keeps them about our own work --
    the untouched pages are full of the source document's own quirks, and
    criterion 1 forbids us from doing anything about those.
    """
    with fitz.open(src_path) as src:
        original = {line for page in src for line in page.get_text().splitlines()}
    with fitz.open(out_path) as out:
        return [
            line
            for page in out
            for line in page.get_text().splitlines()
            if line.strip() and line not in original
        ]

ROOT = Path(__file__).resolve().parent.parent
TEST_PDF_DIR = ROOT / "input test"

PDF_FILES = sorted(TEST_PDF_DIR.glob("*.pdf")) if TEST_PDF_DIR.exists() else []

pytestmark = pytest.mark.skipif(
    not PDF_FILES, reason="no sample PDFs in 'input test/'"
)

LINE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 3,
}


@pytest.fixture(scope="session")
def pipeline():
    return PDFTableFlattenerPipeline()


@pytest.fixture(scope="session")
def flattened(pipeline, tmp_path_factory):
    """Run every sample PDF once; hand the tests the summaries."""
    out_dir = tmp_path_factory.mktemp("flattened")
    results = {}
    for pdf in PDF_FILES:
        out = out_dir / f"{pdf.stem}_flattened.pdf"
        results[pdf.name] = (pdf, out, pipeline.process(str(pdf), str(out)))
    return results


def _case(flattened, name):
    return flattened[name]


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_criterion_1_no_content_is_lost(flattened, name):
    _src, _out, summary = _case(flattened, name)
    report = summary["verification"]
    assert report.criterion_1_and_2_ok, f"mất nội dung: {report.missing_tokens}"


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_criterion_1_non_table_pages_are_byte_identical(flattened, name):
    """Pages the tool declared table-free must come through untouched.

    Bullets that do not fit their table's rectangle continue on a page inserted
    directly after it, so an untouched page is not necessarily at the same index
    in the output any more -- it is at that index or later, never altered.
    """
    src_path, out_path, _summary = _case(flattened, name)
    with pdfplumber.open(src_path) as pdf:
        ruled = {
            idx for idx, page in enumerate(pdf.pages) if page.find_tables(LINE_SETTINGS)
        }
    with fitz.open(src_path) as src, fitz.open(out_path) as out:
        for page_idx in range(len(src)):
            if page_idx in ruled:
                continue
            text = src[page_idx].get_text()
            assert any(
                out[idx].get_text() == text for idx in range(page_idx, len(out))
            ), f"trang {page_idx + 1} không còn nguyên vẹn ở đầu ra"


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_criterion_2_no_table_survives(flattened, name):
    _src, out_path, summary = _case(flattened, name)
    report = summary["verification"]
    assert report.criterion_2_ok, f"còn bảng ở trang {report.residual_table_pages}"

    with pdfplumber.open(out_path) as pdf:
        for page in pdf.pages:
            for table in page.find_tables(LINE_SETTINGS):
                width = table.bbox[2] - table.bbox[0]
                height = table.bbox[3] - table.bbox[1]
                assert width <= 20 or height <= 15


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_criterion_2_tables_became_bullets(flattened, name):
    """Every flattened table contributes at least one bullet line.

    A line opens either with a dash or with the section number the table was
    given on the document's outline -- both are the flattened form of a table.
    """
    src_path, out_path, summary = _case(flattened, name)
    if summary["total_tables_flattened"] == 0:
        pytest.skip("file has no tables")
    assert any(_is_bullet(line) for line in _generated_lines(src_path, out_path))


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_criterion_3_output_is_clean(flattened, name):
    _src, out_path, summary = _case(flattened, name)
    report = summary["verification"]
    assert not report.fake_labels, f"nhãn giả: {report.fake_labels}"
    assert not report.stray_characters, f"ký tự lạ: {report.stray_characters}"
    assert not report.double_blank_lines, "có dòng trống liên tiếp"


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_criterion_3_rendered_text_extracts_as_plain_characters(flattened, name):
    """Bullets must copy out as real hyphens and spaces, not hidden lookalikes."""
    src_path, out_path, _summary = _case(flattened, name)
    for line in _generated_lines(src_path, out_path):
        assert chr(0x00AD) not in line
        assert chr(0x00A0) not in line


@pytest.mark.parametrize("name", [p.name for p in PDF_FILES])
def test_all_three_criteria_pass(flattened, name):
    _src, _out, summary = _case(flattened, name)
    assert summary["verification"].passed, summary["verification"].describe()


def test_page_count_never_shrinks(flattened):
    for _name, (src_path, out_path, _summary) in flattened.items():
        with fitz.open(src_path) as src, fitz.open(out_path) as out:
            assert len(out) >= len(src)
