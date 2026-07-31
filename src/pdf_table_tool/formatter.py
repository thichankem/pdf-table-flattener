import re
from typing import List
from .extractors.base import TableData
import logging

logger = logging.getLogger(__name__)

class TableFormatter:
    @staticmethod
    def format_to_bullets(table_data: TableData) -> List[str]:
        """
        Formats extracted TableData into clean bullet points.
        Format: - Header1: Value1  |  Header2: Value2
        Ensures compliance with test.md criteria 2 & 3.
        """
        headers = table_data.headers or []
        rows = table_data.rows or []

        # Filter out fake headers like 'Cột 1', 'Column 1', 'Unnamed: 0', etc.
        cleaned_headers = []
        for i, h in enumerate(headers):
            h_str = str(h).strip() if h else ""
            if re.match(r"^(cột|column|stt|no\.?)\s*\d+$", h_str, re.IGNORECASE) or h_str.lower().startswith("unnamed"):
                cleaned_headers.append("")
            else:
                cleaned_headers.append(h_str)

        bullet_lines = []

        # Process each row
        for row in rows:
            pairs = []
            for col_idx, cell in enumerate(row):
                val = str(cell).strip() if cell else ""
                if not val:
                    continue

                # Clean cell text (remove newlines, extra spaces)
                val = re.sub(r"\s+", " ", val)

                # Find corresponding header
                header = cleaned_headers[col_idx] if col_idx < len(cleaned_headers) else ""

                if header and not val.startswith(header):
                    pairs.append(f"{header}: {val}")
                else:
                    pairs.append(val)

            if pairs:
                line_content = "  |  ".join(pairs)
                # Prefix with standard bullet point
                bullet_lines.append(f"- {line_content}")

        # If no headers were separated from rows, or table only had 1 row
        if not bullet_lines and headers:
            # Treat headers as a single row if rows were empty
            clean_headers_vals = [re.sub(r"\s+", " ", h) for h in headers if h and str(h).strip()]
            if clean_headers_vals:
                bullet_lines.append(f"- {'  |  '.join(clean_headers_vals)}")

        return bullet_lines
