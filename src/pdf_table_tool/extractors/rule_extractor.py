import pdfplumber
from typing import Tuple, List
from .base import BaseExtractor, TableData
import logging

logger = logging.getLogger(__name__)

class RuleExtractor(BaseExtractor):
    def extract(self, pdf_path: str, page_num: int, bbox: Tuple[float, float, float, float]) -> TableData:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_num]
                # Crop to table bounding box with slight margin
                cropped = page.crop(bbox)
                extracted_table = cropped.extract_table({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                })

                if not extracted_table:
                    # Fallback strategy using text layout
                    extracted_table = cropped.extract_table({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                    })

                if not extracted_table or len(extracted_table) == 0:
                    return TableData(headers=[], rows=[], confidence=0.0, notes="No grid extracted")

                # Clean cell text
                cleaned_rows = []
                for row in extracted_table:
                    cleaned_row = []
                    for cell in row:
                        val = cell.strip() if cell else ""
                        # Replace newlines inside cells with space
                        val = " ".join(val.split())
                        cleaned_row.append(val)
                    if any(cleaned_row):
                        cleaned_rows.append(cleaned_row)

                if not cleaned_rows:
                    return TableData(headers=[], rows=[], confidence=0.0, notes="All cells empty")

                headers = cleaned_rows[0]
                data_rows = cleaned_rows[1:] if len(cleaned_rows) > 1 else []

                # Assess confidence
                non_empty_cells = sum(1 for r in cleaned_rows for c in r if c)
                total_cells = sum(len(r) for r in cleaned_rows)
                cell_fill_rate = non_empty_cells / total_cells if total_cells > 0 else 0

                confidence = 0.85 if cell_fill_rate > 0.5 else 0.4

                return TableData(
                    headers=headers,
                    rows=data_rows,
                    confidence=confidence,
                    notes=f"Rule-based extracted {len(cleaned_rows)} rows"
                )
        except Exception as e:
            logger.error(f"RuleExtractor failed on page {page_num}: {e}")
            return TableData(headers=[], rows=[], confidence=0.0, notes=str(e))
