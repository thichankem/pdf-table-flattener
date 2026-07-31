from typing import Dict, List, Set, Tuple, Any
import pdfplumber
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class TableInfo:
    def __init__(self, page_num: int, bbox: Tuple[float, float, float, float], raw_table: Any = None):
        self.page_num = page_num
        self.bbox = bbox  # (x0, top, x1, bottom)
        self.raw_table = raw_table

def detect_tables_by_page(pdf_path: str) -> Tuple[Dict[int, List[TableInfo]], Set[int]]:
    """
    Detect tables page-by-page in PDF.
    Returns:
        pages_with_tables: Dict[page_num -> List[TableInfo]]
        pages_without_tables: Set[page_num]
    """
    pages_with_tables: Dict[int, List[TableInfo]] = {}
    pages_without_tables: Set[int] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # Attempt pdfplumber table extraction settings
            table_objs = page.find_tables()
            valid_tables = []

            for t in table_objs:
                x0, top, x1, bottom = t.bbox
                # Filtering out tiny or invalid boxes
                width = x1 - x0
                height = bottom - top
                if width > 20 and height > 15:
                    valid_tables.append(TableInfo(page_num=page_num, bbox=t.bbox, raw_table=t))

            if valid_tables:
                merged_tables = merge_table_infos(page_num, valid_tables)
                pages_with_tables[page_num] = merged_tables
            else:
                pages_without_tables.add(page_num)

    logger.info(
        f"Table Detection complete: {len(pages_with_tables)} pages with tables, "
        f"{len(pages_without_tables)} pages without tables (passthrough)."
    )
    return pages_with_tables, pages_without_tables

def merge_table_infos(page_num: int, tables: List[TableInfo], margin: float = 10.0) -> List[TableInfo]:
    """Merge table bboxes on the same page that overlap or lie within `margin` distance."""
    if not tables:
        return []

    boxes = [t.bbox for t in tables]
    merged_boxes = []

    for box in sorted(boxes, key=lambda b: (b[1], b[0])):
        if not merged_boxes:
            merged_boxes.append(box)
        else:
            prev = merged_boxes[-1]
            # Check overlap or close proximity
            if (box[1] <= prev[3] + margin) and (box[0] <= prev[2] + margin) and (box[2] >= prev[0] - margin):
                # Merge
                new_box = (
                    min(prev[0], box[0]),
                    min(prev[1], box[1]),
                    max(prev[2], box[2]),
                    max(prev[3], box[3])
                )
                merged_boxes[-1] = new_box
            else:
                merged_boxes.append(box)

    return [TableInfo(page_num=page_num, bbox=b) for b in merged_boxes]
