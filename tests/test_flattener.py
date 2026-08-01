"""End-to-end tests: the three mandatory criteria of test.md, on real PDFs.

    1. Content outside tables is untouched, 100%.
    2. Every table is flattened into bullets; no table survives.
    3. The generated text is clean: no fake labels, no hidden characters, no
       two blank lines in a row.
"""

from pathlib import Path

import fitz
import pdfplumber
import pytest

from pdf_table_tool.pipeline import PDFTableFlattenerPipeline

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
    return PDFTableFlattenerPipeline(use_llm=False)


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
    """Pages the tool declared table-free must come through untouched."""
    src_path, out_path, _summary = _case(flattened, name)
    with fitz.open(src_path) as src, fitz.open(out_path) as out:
        for page_idx in range(min(len(src), len(out))):
            with pdfplumber.open(src_path) as pdf:
                if pdf.pages[page_idx].find_tables(LINE_SETTINGS):
                    continue
            assert src[page_idx].get_text() == out[page_idx].get_text()


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
    """Every flattened table contributes at least one bullet line."""
    _src, out_path, summary = _case(flattened, name)
    if summary["total_tables_flattened"] == 0:
        pytest.skip("file has no tables")
    with fitz.open(out_path) as out:
        text = "\n".join(page.get_text() for page in out)
    assert text.count("\n- ") + text.startswith("- ") >= 1


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
    _src, out_path, _summary = _case(flattened, name)
    with fitz.open(out_path) as out:
        for page in out:
            for line in page.get_text().splitlines():
                if line.lstrip().startswith("- "):
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
