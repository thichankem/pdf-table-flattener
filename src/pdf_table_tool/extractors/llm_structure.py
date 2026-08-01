"""Optional LLM classifier for a table's layout.

Getting a table's *orientation* wrong is the one mistake geometry alone can
still make: a header row and a labelled first row look identical on paper, and
only meaning tells them apart.  That is exactly the kind of judgement a language
model is good at -- so this is where the model is allowed to help.

What it is deliberately **not** allowed to do: produce text.  It answers with two
numbers describing the layout; every character in the output PDF still comes
from the PDF itself.  A wrong answer can therefore make a table read oddly, but
it can never lose or invent content.
"""

import json
import logging
from typing import List, Optional

import requests

from ..config import settings
from ..formatter import TableStructure

logger = logging.getLogger(__name__)

MAX_CELL_CHARS = 120
MAX_ROWS_SENT = 8

PROMPT = (
    "Bạn phân tích CẤU TRÚC của một bảng trích từ PDF. Không viết lại nội dung.\n"
    "Cho ma trận ô dưới đây, hãy xác định:\n"
    '  "header_rows": số dòng ĐẦU dùng làm tiêu đề cho các CỘT (0 nếu bảng '
    "không có dòng tiêu đề).\n"
    '  "label_column": true nếu CỘT ĐẦU là nhãn cho từng dòng '
    "(ví dụ: Điều kiện / Tình huống / Thứ tự phân bổ phí), false nếu không.\n"
    "Lưu ý: một dòng chỉ là tiêu đề khi nó đặt tên cho TỪNG cột bên dưới. "
    "Nếu dòng đầu là một câu dài trải ngang nhiều cột thì đó là DỮ LIỆU, "
    "không phải tiêu đề.\n"
    'Chỉ trả về JSON: {"header_rows": <int>, "label_column": <bool>}'
)


def _matrix_preview(grid) -> List[List[str]]:
    rows: List[List[str]] = []
    for r in range(min(grid.n_rows, MAX_ROWS_SENT)):
        row: List[str] = []
        for c in range(grid.n_cols):
            cell = next(
                (x for x in grid.cells if x.row == r and x.col == c), None
            )
            if cell is None:
                row.append("")
                continue
            text = " ".join(cell.text.split())[:MAX_CELL_CHARS]
            if cell.col_span > 1:
                text = f"[gộp {cell.col_span} cột] {text}"
            row.append(text)
        rows.append(row)
    return rows


class LLMStructureClassifier:
    """Asks Ollama how a table is laid out; falls back silently when unsure."""

    def __init__(self, url: Optional[str] = None, model: Optional[str] = None):
        self.url = url or settings.OLLAMA_URL
        self.model = model or settings.OLLAMA_MODEL
        self._available: Optional[bool] = None

    def available(self) -> bool:
        if self._available is None:
            try:
                self._available = (
                    requests.get(f"{self.url}/api/tags", timeout=3).status_code == 200
                )
            except requests.RequestException:
                self._available = False
            if not self._available:
                logger.info("Ollama not reachable; using geometric layout analysis.")
        return self._available

    def classify(self, grid, fallback: TableStructure) -> TableStructure:
        if grid.n_rows < 2 or grid.n_cols < 2 or not self.available():
            return fallback
        try:
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": PROMPT
                    + "\n\nMA TRẬN:\n"
                    + json.dumps(_matrix_preview(grid), ensure_ascii=False),
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0},
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = json.loads(response.json().get("response", "{}"))
            header_rows = int(payload["header_rows"])
            label_column = bool(payload["label_column"])
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            logger.warning("LLM layout check skipped: %s", exc)
            return fallback

        if not 0 <= header_rows <= min(2, grid.n_rows - 1):
            logger.warning(
                "LLM proposed header_rows=%s for a %dx%d table; ignoring.",
                header_rows,
                grid.n_rows,
                grid.n_cols,
            )
            return fallback

        if (header_rows, label_column) != (
            fallback.header_rows,
            fallback.label_column,
        ):
            logger.info(
                "LLM layout: header_rows %d->%d, label_column %s->%s",
                fallback.header_rows,
                header_rows,
                fallback.label_column,
                label_column,
            )
        return TableStructure(
            header_rows=header_rows, label_column=label_column, source="llm"
        )
