"""End-to-end orchestration: detect -> extract -> flatten -> render -> verify."""

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

import pdfplumber

from .config import settings
from .formatter import TableFormatter, detect_structure, normalise_sliced_cells
from .grid_extractor import build_grid
from .pdf_patcher import PDFPatcher
from .table_detector import _filter_nested, detect_tables_by_page
from .verifier import VerificationReport, verify

logger = logging.getLogger(__name__)


def _outermost(tables: List[Any]) -> List[Any]:
    """Drop tables nested inside another table of the same list."""
    if not tables:
        return []
    kept, _children = _filter_nested(tables)
    return kept


class PDFTableFlattenerPipeline:
    """Flattens the tables of a document.

    `process` accepts a .pdf or a .docx and writes the same format back out;
    Word files are handed to :mod:`.docx_flattener`, which shares this module's
    formatter so both formats produce the same bullets.
    """

    def __init__(self, use_llm: Optional[bool] = None, verify_output: bool = True):
        self.formatter = TableFormatter()
        self.patcher = PDFPatcher()
        self.verify_output = verify_output
        self.use_llm = settings.USE_LLM if use_llm is None else use_llm
        self._refiner = None
        self._classifier = None
        self._docx = None
        if self.use_llm:
            from .extractors.llm_reconstructor import LLMBulletRefiner
            from .extractors.llm_structure import LLMStructureClassifier

            self._refiner = LLMBulletRefiner()
            self._classifier = LLMStructureClassifier()

    def process(self, pdf_path: str, output_path: str) -> Dict[str, Any]:
        if pdf_path.lower().endswith(".docx"):
            return self._docx_flattener().process(pdf_path, output_path)
        return self._process_pdf(pdf_path, output_path)

    def _docx_flattener(self):
        """Word support is loaded on demand, so a PDF-only run never needs it."""
        if self._docx is None:
            from .docx_flattener import DocxTableFlattener

            self._docx = DocxTableFlattener(
                use_llm=self.use_llm, verify_output=self.verify_output
            )
        return self._docx

    def _process_pdf(self, pdf_path: str, output_path: str) -> Dict[str, Any]:
        logger.info("Processing %s", pdf_path)

        pages_with_tables, pages_without_tables = detect_tables_by_page(pdf_path)

        patches_by_page: Dict[int, List[Dict[str, Any]]] = {}
        total_tables = 0
        inherited_headers: Optional[List[str]] = None
        all_lines: List[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num in sorted(pages_with_tables):
                page = pdf.pages[page_num]
                page_patches: List[Dict[str, Any]] = []

                for info in pages_with_tables[page_num]:
                    nested_blocks = self._flatten_nested(page, info)
                    grid = build_grid(
                        page, info.raw_table, nested_blocks=nested_blocks
                    )
                    if grid.n_rows == 0:
                        continue

                    carry = inherited_headers if info.is_continuation else None

                    # Geometry decides the layout; the LLM may only correct it.
                    # Both see the same normalised grid so their row indices
                    # mean the same thing.
                    normalised = normalise_sliced_cells(grid)
                    structure = detect_structure(normalised)
                    if self._classifier is not None:
                        structure = self._classifier.classify(normalised, structure)

                    bullet_lines, headers = self.formatter.format_grid(
                        grid, carry, structure
                    )

                    if self._refiner is not None:
                        bullet_lines = self._refiner.refine(bullet_lines)

                    if not bullet_lines:
                        continue

                    font_file, font_size = self._match_typography(page, info.bbox)
                    page_patches.append(
                        {
                            "bbox": info.bbox,
                            "bullet_lines": bullet_lines,
                            "font_file": font_file,
                            "font_size": font_size,
                        }
                    )
                    total_tables += 1
                    all_lines.extend(bullet_lines)
                    if any(h.strip() for h in headers):
                        inherited_headers = headers

                if page_patches:
                    patches_by_page[page_num] = page_patches
                else:
                    pages_without_tables.add(page_num)

        render_stats = self.patcher.process_pdf(
            pdf_path=pdf_path,
            output_path=output_path,
            patches_by_page=patches_by_page,
            pages_without_tables=pages_without_tables,
        )

        summary: Dict[str, Any] = {
            "input_file": pdf_path,
            "output_file": output_path,
            "pages_passthrough_count": len(pages_without_tables),
            "pages_patched_count": len(patches_by_page),
            "total_tables_flattened": total_tables,
            "continuation_pages_added": render_stats.get("spill_pages", 0),
            "status": "success",
        }

        if self.verify_output:
            report: VerificationReport = verify(pdf_path, output_path, all_lines)
            summary["verification_passed"] = report.passed
            summary["verification"] = report
            if not report.passed:
                summary["status"] = "verification_failed"
                logger.warning("Verification failed:\n%s", report.describe())
            else:
                logger.info("Verification passed:\n%s", report.describe())

        logger.info("Done: %s", {k: v for k, v in summary.items() if k != "verification"})
        return summary

    # -- helpers ---------------------------------------------------------
    def _flatten_nested(self, page, info) -> List[tuple]:
        """Flatten every table drawn inside a cell of `info`, innermost first.

        Word draws a sub-table (``Nhóm chức danh | HMTC``) with its own rulings,
        so it arrives as a separate table sitting inside a parent cell.  Giving
        it the full treatment here -- headers, labels, bullets -- keeps its
        column pairing, which is lost if its words are merely poured into the
        parent cell.
        """
        blocks: List[tuple] = []
        for child in _outermost(info.dropped_children):
            try:
                child_grid = build_grid(page, child)
                if child_grid.n_rows == 0:
                    continue
                child_lines, _ = self.formatter.format_grid(child_grid)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Nested table flattening failed: %s", exc)
                continue
            if child_lines:
                blocks.append((tuple(child.bbox), child_lines))
        return blocks

    @staticmethod
    def _match_typography(page, bbox) -> tuple:
        """Pick a font face and size close to what the table itself used."""
        x0, top, x1, bottom = bbox
        chars = [
            c
            for c in page.chars
            if x0 - 1 <= c["x0"] <= x1 + 1 and top - 1 <= c["top"] <= bottom + 1
        ]
        if not chars:
            return settings.get_font_path(serif=True), settings.BULLET_FONT_SIZE

        names = Counter((c.get("fontname") or "").lower() for c in chars)
        dominant = names.most_common(1)[0][0]
        serif = not any(k in dominant for k in ("arial", "helvetica", "calibri", "sans"))

        sizes = Counter(round(float(c.get("size") or 0), 1) for c in chars)
        common_size = sizes.most_common(1)[0][0] or settings.BULLET_FONT_SIZE
        size = min(12.0, max(settings.MIN_FONT_SIZE, common_size))
        return settings.get_font_path(serif=serif), size


# The class handles PDF and Word alike; the old name stays for existing callers.
DocumentFlattenerPipeline = PDFTableFlattenerPipeline

SUPPORTED_SUFFIXES = (".pdf", ".docx")
