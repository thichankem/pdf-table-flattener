from typing import Tuple
from .extractors.base import TableData
from .extractors.rule_extractor import RuleExtractor
from .extractors.llm_vision_extractor import LLMVisionExtractor
from .ollama_bootstrap import check_ollama_available
import logging

logger = logging.getLogger(__name__)

class TableRouter:
    def __init__(self):
        self.rule_extractor = RuleExtractor()
        self.vision_extractor = LLMVisionExtractor()

    def route_and_extract(self, pdf_path: str, page_num: int, bbox: Tuple[float, float, float, float]) -> TableData:
        # Step 1: Run Rule-based extractor
        rule_data = self.rule_extractor.extract(pdf_path, page_num, bbox)

        if rule_data.confidence >= 0.7 and (rule_data.headers or rule_data.rows):
            logger.info(f"Page {page_num}: Using RuleExtractor (confidence: {rule_data.confidence})")
            return rule_data

        # Step 2: Fallback to LLM Vision Extractor if Ollama available
        if check_ollama_available():
            logger.info(f"Page {page_num}: RuleExtractor confidence low ({rule_data.confidence}). Fallback to LLMVisionExtractor.")
            vision_data = self.vision_extractor.extract(pdf_path, page_num, bbox)
            if vision_data.headers or vision_data.rows:
                return vision_data

        logger.info(f"Page {page_num}: Returning best available extraction data.")
        return rule_data
