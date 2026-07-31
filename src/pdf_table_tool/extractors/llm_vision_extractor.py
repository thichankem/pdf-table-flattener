import fitz  # PyMuPDF
import base64
import io
import json
import requests
from typing import Tuple
from PIL import Image
from .base import BaseExtractor, TableData
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class LLMVisionExtractor(BaseExtractor):
    def extract(self, pdf_path: str, page_num: int, bbox: Tuple[float, float, float, float]) -> TableData:
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num]
            rect = fitz.Rect(bbox)

            # Render page crop at 2.0 zoom for crisp vision resolution
            pix = page.get_pixmap(clip=rect, dpi=200)
            img_bytes = pix.tobytes("png")
            base64_img = base64.b64encode(img_bytes).decode("utf-8")

            prompt = (
                "You are an expert OCR table parser. Extract all tabular data from this image.\n"
                "Return ONLY a raw JSON object with key 'headers' (list of header strings) "
                "and key 'rows' (list of lists of string cell values). Do not include markdown code block quotes.\n"
                "Example format: {\"headers\": [\"Tên\", \"Tuổi\"], \"rows\": [[\"Nam\", \"25\"], [\"Hoa\", \"23\"]]}"
            )

            payload = {
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "images": [base64_img],
                "stream": False,
                "format": "json"
            }

            res = requests.post(
                f"{settings.OLLAMA_URL}/api/generate",
                json=payload,
                timeout=45
            )

            if res.status_code == 200:
                response_json = res.json()
                raw_response = response_json.get("response", "").strip()

                # Clean markdown blocks if any
                if raw_response.startswith("```"):
                    raw_response = raw_response.split("```")[1]
                    if raw_response.startswith("json"):
                        raw_response = raw_response[4:]

                parsed = json.loads(raw_response)
                headers = parsed.get("headers", [])
                rows = parsed.get("rows", [])

                return TableData(
                    headers=headers,
                    rows=rows,
                    confidence=0.9,
                    notes="LLM Vision extracted successfully"
                )

        except Exception as e:
            logger.warning(f"LLMVisionExtractor error on page {page_num}: {e}")

        return TableData(headers=[], rows=[], confidence=0.0, notes="LLM vision failed")
