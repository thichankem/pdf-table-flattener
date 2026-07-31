from typing import Tuple, List, Dict, Any
from .config import settings
import logging

logger = logging.getLogger(__name__)

class LayoutPlanner:
    def plan_layout(
        self,
        bbox: Tuple[float, float, float, float],
        bullet_lines: List[str],
        font_size: float = None,
        line_height: float = None
    ) -> Dict[str, Any]:
        """
        Calculates space required for bullet lines versus original table bbox.
        """
        x0, top, x1, bottom = bbox
        original_height = bottom - top
        f_size = font_size or settings.BULLET_FONT_SIZE
        l_height = line_height or settings.BULLET_LINE_HEIGHT

        # Estimate line wrapping if text width > bbox width
        bbox_width = max(100.0, x1 - x0)
        total_rendered_lines = 0

        for line in bullet_lines:
            # Approx char width is font_size * 0.5
            est_chars_per_line = max(20, int(bbox_width / (f_size * 0.5)))
            line_len = len(line)
            wrapped_count = max(1, (line_len + est_chars_per_line - 1) // est_chars_per_line)
            total_rendered_lines += wrapped_count

        needed_height = total_rendered_lines * l_height + 6.0  # 6pt padding

        if needed_height <= original_height:
            return {
                "original_bbox": bbox,
                "needed_height": needed_height,
                "extra_height": 0.0,
                "fits": True,
            }

        extra_height = needed_height - original_height
        logger.info(f"Bullet content overflows bbox by {extra_height:.1f}pt. Shifting content below.")
        return {
            "original_bbox": bbox,
            "needed_height": needed_height,
            "extra_height": extra_height,
            "fits": False,
        }
