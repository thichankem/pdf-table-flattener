import pytest
import pdfplumber
import fitz
from pathlib import Path
from src.pdf_table_tool.formatter import TableFormatter
from src.pdf_table_tool.extractors.base import TableData
from src.pdf_table_tool.pipeline import PDFTableFlattenerPipeline

TEST_PDF_DIR = Path(__file__).parent.parent / "input test"

def test_formatter_criteria_2_and_3():
    """Verify criteria 2 & 3: bullet format and clean output without fake labels."""
    sample_table = TableData(
        headers=["Tên", "Tuổi", "Chức vụ", "Cột 4"],
        rows=[
            ["Nam", "25", "Dev", "Ghi chú 1"],
            ["Hoa", "23", "Designer", ""],
        ]
    )

    bullets = TableFormatter.format_to_bullets(sample_table)

    assert len(bullets) == 2
    assert bullets[0] == "- Tên: Nam  |  Tuổi: 25  |  Chức vụ: Dev  |  Ghi chú 1"
    # Verify 'Cột 4' fake header filtering: empty cell skipped, value appended clean
    assert bullets[1] == "- Tên: Hoa  |  Tuổi: 23  |  Chức vụ: Designer"

def test_end_to_end_flattening(tmp_path):
    """Run E2E flattening on sample PDF from input test directory."""
    sample_pdfs = list(TEST_PDF_DIR.glob("*.pdf"))
    if not sample_pdfs:
        pytest.skip("No sample PDFs found in input test directory.")

    test_file = sample_pdfs[0]
    out_file = tmp_path / "output_test.pdf"

    pipeline = PDFTableFlattenerPipeline(check_ollama=False)
    summary = pipeline.process(str(test_file), str(out_file))

    assert summary["status"] == "success"
    assert out_file.exists()

    # Criteria 2 Verification: Ensure no explicit grid tables remain in output PDF
    with pdfplumber.open(str(out_file)) as pdf:
        total_remaining_grid_tables = 0
        total_bullet_lines_found = 0

        for page in pdf.pages:
            tables = page.find_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            total_remaining_grid_tables += len(tables)

            text = page.extract_text() or ""
            for line in text.splitlines():
                if line.strip().startswith("- "):
                    total_bullet_lines_found += 1

        assert total_remaining_grid_tables == 0, f"Expected 0 grid tables remaining, found {total_remaining_grid_tables}"
        assert total_bullet_lines_found > 0, "Expected formatted bullet lines in output PDF"
