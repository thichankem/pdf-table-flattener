from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from pydantic import BaseModel, Field

class TableData(BaseModel):
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    confidence: float = 1.0
    notes: Optional[str] = None

class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, pdf_path: str, page_num: int, bbox: Tuple[float, float, float, float]) -> TableData:
        """Extract table data from specified page and bounding box."""
        pass
