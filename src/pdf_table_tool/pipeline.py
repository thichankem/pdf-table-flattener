"""End-to-end orchestration: detect -> extract -> flatten -> render -> verify."""

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

from .config import settings
from .formatter import TableFormatter, detect_structure, normalise_sliced_cells
from .grid_extractor import build_grid
from .outline import (
    DocumentOutline,
    TableNumber,
    lines_outside_tables,
    number_table_lines,
    scan_pdf_outline,
    title_above,
    unsaid_header_line,
)
from .pdf_patcher import PDFPatcher
from .table_detector import _filter_nested, detect_tables_by_page
from .verifier import VerificationReport, verify

logger = logging.getLogger(__name__)

# .xlsm is the same file format with macros; the macros are irrelevant to us,
# and refusing it would only send the user back to re-save the workbook.
EXCEL_SUFFIXES = (".xlsx", ".xlsm")


def _outermost(tables: List[Any]) -> List[Any]:
    """Drop tables nested inside another table of the same list."""
    if not tables:
        return []
    kept, _children = _filter_nested(tables)
    return kept


class PDFTableFlattenerPipeline:
    """Flattens the tables of a document.

    `process` accepts a .pdf, a .docx or an Excel workbook.  A PDF and a Word
    file are patched in place and keep their own format; a workbook has no such
    form and comes back as Word.  All three are handed to this module's
    formatter, so identical tables produce identical bullets.

    `numbering` puts each table on the document's own outline -- a table under
    "1. Thuật ngữ" becomes 1.1 and its rows 1.1.1, 1.1.2 -- so a RAG chunker can
    cut a long table anywhere and every chunk still says where it came from.
    Turning it off restores the plain "- " bullets.
    """

    def __init__(self, verify_output: bool = True, numbering: bool = True):
        self.formatter = TableFormatter()
        self.patcher = PDFPatcher()
        self.verify_output = verify_output
        self.numbering = numbering
        self._docx = None
        self._xlsx = None

    def process(self, pdf_path: str, output_path: str) -> Dict[str, Any]:
        suffix = pdf_path.lower()
        if suffix.endswith(EXCEL_SUFFIXES):
            # Excel is only ever written back as Word; correcting the extension
            # here means no caller can produce a .xlsx holding a Word document.
            output_path = str(Path(output_path).with_suffix(".docx"))
            return self._xlsx_flattener().process(pdf_path, output_path)
        if suffix.endswith(".docx"):
            return self._docx_flattener().process(pdf_path, output_path)
        return self._process_pdf(pdf_path, output_path)

    def _docx_flattener(self):
        """Word support is loaded on demand, so a PDF-only run never needs it."""
        if self._docx is None:
            from .docx_flattener import DocxTableFlattener

            self._docx = DocxTableFlattener(
                verify_output=self.verify_output, numbering=self.numbering
            )
        return self._docx

    def _xlsx_flattener(self):
        """Excel support is loaded on demand; openpyxl is only needed for it."""
        if self._xlsx is None:
            from .xlsx_flattener import XlsxTableFlattener

            self._xlsx = XlsxTableFlattener(
                verify_output=self.verify_output, numbering=self.numbering
            )
        return self._xlsx

    def _process_pdf(self, pdf_path: str, output_path: str) -> Dict[str, Any]:
        logger.info("Processing %s", pdf_path)

        pages_with_tables, pages_without_tables = detect_tables_by_page(pdf_path)

        patches_by_page: Dict[int, List[Dict[str, Any]]] = {}
        total_tables = 0
        inherited_headers: Optional[List[str]] = None
        all_lines: List[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            # The document's own headings decide where each table sits, so they
            # are read before the first table is formatted -- a heading three
            # pages earlier still names the section this one belongs to.
            outline = DocumentOutline()
            if self.numbering:
                events, known = scan_pdf_outline(
                    pdf,
                    {
                        page: [info.bbox for info in infos]
                        for page, infos in pages_with_tables.items()
                    },
                )
                outline.load(events, known)
            # How many tables each section holds, counted before the first of
            # them is numbered: a section holding just the one *is* that table
            # and keeps its own number rather than opening a level below it.
            # Continuations do not count -- they are the same table, further on.
            tables_in: Dict[Tuple[int, ...], int] = {}
            if self.numbering:
                for page_num in sorted(pages_with_tables):
                    for info in pages_with_tables[page_num]:
                        if info.is_continuation:
                            continue
                        at = outline.section_at(page_num, info.bbox[1])
                        tables_in[at] = tables_in.get(at, 0) + 1
            number: Optional[TableNumber] = None
            title = ""
            # With numbering off there is no caption line for the headers no row
            # repeats to live on, so they get a line of their own -- written
            # once, and not again on each of the eleven pages a long table
            # spills onto.  Keyed by the line itself rather than by the headers
            # it came from: header detection wobbles a little from page to page,
            # and it is the line the reader sees twice that is the complaint.
            headers_written: set = set()

            for page_num in sorted(pages_with_tables):
                page = pdf.pages[page_num]
                page_patches: List[Dict[str, Any]] = []
                # The running text of the page, read once: it is where the name
                # printed above a table is found.
                page_lines = (
                    lines_outside_tables(
                        page, [info.bbox for info in pages_with_tables[page_num]]
                    )
                    if self.numbering
                    else []
                )

                for info in pages_with_tables[page_num]:
                    nested_blocks = self._flatten_nested(page, info)
                    grid = build_grid(
                        page, info.raw_table, nested_blocks=nested_blocks
                    )
                    if grid.n_rows == 0:
                        continue

                    carry = inherited_headers if info.is_continuation else None

                    # Geometry decides the layout.  Normalising first means the
                    # detector's row indices mean the same thing as the grid's.
                    normalised = normalise_sliced_cells(grid)
                    structure = detect_structure(normalised)

                    bullet_lines, headers = self.formatter.format_grid(
                        grid, carry, structure
                    )

                    if not bullet_lines:
                        continue

                    if self.numbering:
                        # A table split by a page break keeps the number it was
                        # given on the page before, its name, and its rows carry
                        # on from where they stopped.
                        continued = bool(info.is_continuation and number is not None)
                        if not continued:
                            outline.advance_to(page_num, info.bbox[1])
                            section = outline.section
                            number = outline.next_table(
                                alone=tables_in.get(section) == 1
                            )
                            title = title_above(page_lines, info.bbox[1])
                            # A table that took the section's own number already
                            # has the heading above it for a name, printed under
                            # that same number; a caption would repeat it.
                            if number.path == section:
                                title = ""
                        bullet_lines = number_table_lines(
                            bullet_lines, number, title, headers, continued=continued
                        )
                    else:
                        header_line = unsaid_header_line(bullet_lines, headers)
                        if header_line and header_line not in headers_written:
                            headers_written.add(header_line)
                            bullet_lines = [header_line] + bullet_lines

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


# The class handles PDF, Word and Excel alike; the old name stays for existing
# callers.
DocumentFlattenerPipeline = PDFTableFlattenerPipeline

SUPPORTED_SUFFIXES = (".pdf", ".docx") + EXCEL_SUFFIXES


def output_suffix_for(input_path: str) -> str:
    """The extension the flattened output of `input_path` will carry.

    A PDF and a Word file are patched in place, so they keep their own format.
    A workbook cannot hold a bullet list, so it comes back as Word -- callers
    that build an output name need to know that before the run starts.
    """
    return ".docx" if input_path.lower().endswith(EXCEL_SUFFIXES) else Path(input_path).suffix


# Marks a result file as the flattened form of its input, so the two never look
# alike in a folder listing.
OUTPUT_NAME_TAG = "_flattened"


def output_stem_for(input_path: str) -> str:
    """The input's name carrying the `_flattened` tag.

    Running the tool on its own output must not stack the tag up, so a name
    that already ends with it is left alone.
    """
    stem = Path(input_path).stem
    return stem if stem.lower().endswith(OUTPUT_NAME_TAG) else stem + OUTPUT_NAME_TAG


def output_name_for(input_path: str) -> str:
    """The full file name -- tagged stem plus extension -- of the output."""
    return output_stem_for(input_path) + output_suffix_for(input_path)
