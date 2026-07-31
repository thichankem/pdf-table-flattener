import fitz  # PyMuPDF
from typing import Dict, List, Set, Any, Tuple
from .config import settings
import logging

logger = logging.getLogger(__name__)

class PDFPatcher:
    def __init__(self, font_path: str = None):
        self.font_path = font_path or settings.get_font_path()

    def process_pdf(
        self,
        pdf_path: str,
        output_path: str,
        patches_by_page: Dict[int, List[Dict[str, Any]]],
        pages_without_tables: Set[int]
    ) -> None:
        """
        Processes PDF:
        - Non-table pages: Direct stream copy (100% passthrough).
        - Table pages: Redact table bbox, overlay bullet text, shift lower content if needed.
        """
        src_doc = fitz.open(pdf_path)
        out_doc = fitz.open()

        font_file_path = settings.get_font_path()
        font_name = "UnicodeFont" if font_file_path != "helv" else "helv"

        for page_num in range(len(src_doc)):
            if page_num in pages_without_tables:
                # 100% Direct Byte Passthrough
                out_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
                logger.info(f"Page {page_num + 1}: Direct passthrough (no tables).")
            else:
                # Page containing table
                out_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
                page = out_doc[-1]

                # Register font on page if TrueType font file exists
                if font_name == "UnicodeFont" and font_file_path:
                    try:
                        page.insert_font(fontname=font_name, fontfile=font_file_path)
                    except Exception as fe:
                        logger.warning(f"Font registration warning: {fe}")
                        font_name = "helv"

                page_patches = patches_by_page.get(page_num, [])

                # Process patches from bottom to top to preserve Y coordinates during shift
                sorted_patches = sorted(
                    page_patches,
                    key=lambda p: p["layout"]["original_bbox"][1],
                    reverse=True
                )

                for patch in sorted_patches:
                    bbox = patch["layout"]["original_bbox"]
                    bullet_lines = patch["bullet_lines"]
                    extra_height = patch["layout"]["extra_height"]

                    x0, top, x1, bottom = bbox

                    if extra_height > 0:
                        self._shift_content_below(page, threshold_y=bottom, shift=extra_height, font_name=font_name, font_path=font_file_path)

                    # Redact table area (expand 2.0pt margin to erase outer border lines completely)
                    new_bottom = bottom + extra_height
                    redact_rect = fitz.Rect(max(0, x0 - 2.0), max(0, top - 2.0), x1 + 2.0, new_bottom + 2.0)
                    page.add_redact_annot(redact_rect, fill=(1, 1, 1))
                    page.apply_redactions()

                    # Insert formatted bullet text
                    rect = fitz.Rect(x0, top, x1, new_bottom)

                    # Insert formatted bullet text
                    text = "\n".join(bullet_lines)
                    if text.strip():
                        if font_name == "UnicodeFont":
                            page.insert_textbox(
                                rect,
                                text,
                                fontsize=settings.BULLET_FONT_SIZE,
                                fontname=font_name,
                                fontfile=font_file_path,
                                color=(0, 0, 0)
                            )
                        else:
                            page.insert_textbox(
                                rect,
                                text,
                                fontsize=settings.BULLET_FONT_SIZE,
                                fontname="helv",
                                color=(0, 0, 0)
                            )

                logger.info(f"Page {page_num + 1}: Patched {len(page_patches)} table(s).")

        out_doc.save(output_path)
        src_doc.close()
        out_doc.close()
        logger.info(f"Patched PDF successfully saved to {output_path}")

    def _shift_content_below(self, page: fitz.Page, threshold_y: float, shift: float, font_name: str, font_path: str):
        """
        Shifts text blocks below threshold_y downwards by `shift` points.
        """
        page_dict = page.get_text("dict")
        blocks_to_shift = []

        for b in page_dict.get("blocks", []):
            if b.get("type") == 0:  # Text block
                bbox = b.get("bbox")
                if bbox and bbox[1] >= threshold_y:
                    blocks_to_shift.append(b)

        # Process each block: redact original area and draw at y + shift
        for b in blocks_to_shift:
            b_bbox = fitz.Rect(b["bbox"])
            text_lines = []
            for line in b.get("lines", []):
                line_str = "".join([span.get("text", "") for span in line.get("spans", [])])
                text_lines.append(line_str)

            text_content = "\n".join(text_lines)
            if not text_content.strip():
                continue

            # Redact original position
            page.add_redact_annot(b_bbox, fill=(1, 1, 1))
            page.apply_redactions()

            # Insert at new shifted position
            new_bbox = fitz.Rect(b_bbox.x0, b_bbox.y0 + shift, b_bbox.x1, b_bbox.y1 + shift)
            if font_name == "UnicodeFont":
                page.insert_textbox(new_bbox, text_content, fontsize=9, fontname=font_name, fontfile=font_path)
            else:
                page.insert_textbox(new_bbox, text_content, fontsize=9, fontname="helv")
