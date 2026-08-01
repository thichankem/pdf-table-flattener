"""Optional LLM polish for the generated bullets.

The deterministic pipeline is already lossless, so the model is given a strictly
limited job: tidy wording and labels.  Its answer is accepted **only** if it
contains exactly the tokens of the input -- otherwise the deterministic bullets
are kept.  Enabling the LLM can therefore improve readability but can never
cause the content loss this tool exists to avoid.
"""

import json
import logging
from collections import Counter
from typing import List, Optional

import requests

from ..config import settings
from ..text_utils import collapse_blank_lines, tokenize

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là biên tập viên văn bản tiếng Việt. Bạn nhận một danh sách gạch đầu "
    "dòng đã được làm phẳng từ một bảng PDF.\n"
    "NHIỆM VỤ: chỉ chỉnh lại dấu câu, khoảng trắng và nhãn cột cho dễ đọc.\n"
    "TUYỆT ĐỐI KHÔNG: thêm nội dung mới, bỏ bớt bất kỳ từ nào, tóm tắt, dịch, "
    "hoặc đổi thứ tự các dòng.\n"
    "Giữ nguyên số dòng và mức thụt đầu dòng.\n"
    'Trả về JSON thuần: {"lines": ["- ...", "  - ..."]}'
)


class LLMBulletRefiner:
    """Ollama-backed cosmetic refiner with a hard no-loss guard."""

    def __init__(self, url: Optional[str] = None, model: Optional[str] = None):
        self.url = url or settings.OLLAMA_URL
        self.model = model or settings.OLLAMA_MODEL

    def available(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=3).status_code == 200
        except requests.RequestException:
            return False

    def refine(self, lines: List[str]) -> List[str]:
        if not lines or not self.available():
            return lines
        try:
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": SYSTEM_PROMPT
                    + "\n\nDANH SÁCH:\n"
                    + json.dumps(lines, ensure_ascii=False),
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0},
                },
                timeout=90,
            )
            response.raise_for_status()
            payload = json.loads(response.json().get("response", "{}"))
            candidate = [str(x) for x in payload.get("lines", [])]
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning("LLM refine skipped: %s", exc)
            return lines

        if not candidate:
            return lines

        before = Counter(tokenize("\n".join(lines)))
        after = Counter(tokenize("\n".join(candidate)))
        if before - after:
            logger.warning(
                "LLM output dropped %d token(s); keeping deterministic bullets.",
                sum((before - after).values()),
            )
            return lines
        if after - before:
            logger.warning("LLM output invented tokens; keeping deterministic bullets.")
            return lines

        return collapse_blank_lines(candidate)
