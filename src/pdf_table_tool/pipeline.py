import os
from typing import Dict, List, Any
from .table_detector import detect_tables_by_page
from .router import TableRouter
from .formatter import TableFormatter
from .layout_planner import LayoutPlanner
from .pdf_patcher import PDFPatcher
from .ollama_bootstrap import ensure_ollama_running
import logging

logger = logging.getLogger(__name__)

class PDFTableFlattenerPipeline:
    def __init__(self, check_ollama: bool = True):
        self.check_ollama = check_ollama
        self.router = TableRouter()
        self.formatter = TableFormatter()
        self.planner = LayoutPlanner()
        self.patcher = PDFPatcher()

    def process(self, pdf_path: str, output_path: str) -> Dict[str, Any]:
        """
        Main end-to-end pipeline execution.
        """
        logger.info(f"Starting processing for file: {pdf_path}")
        if self.check_ollama:
            is_ollama_ok, msg = ensure_ollama_running()
            logger.info(f"Ollama status: {msg}")

        # Step 1: Detect tables & classify pages
        pages_with_tables, pages_without_tables = detect_tables_by_page(pdf_path)

        patches_by_page: Dict[int, List[Dict[str, Any]]] = {}
        total_tables_processed = 0

        # Step 2: Route, extract, format & plan layout for pages with tables
        for page_num, tables in pages_with_tables.items():
            page_patches = []
            for t_info in tables:
                bbox = t_info.bbox
                # Route & Extract table data
                table_data = self.router.route_and_extract(pdf_path, page_num, bbox)

                # Format table data to clean bullets
                bullet_lines = self.formatter.format_to_bullets(table_data)

                # Plan layout
                layout_info = self.planner.plan_layout(bbox, bullet_lines)

                page_patches.append({
                    "table_data": table_data,
                    "bullet_lines": bullet_lines,
                    "layout": layout_info,
                    "original_bbox": bbox
                })
                total_tables_processed += 1

            patches_by_page[page_num] = page_patches

        # Step 3: Patch PDF
        self.patcher.process_pdf(
            pdf_path=pdf_path,
            output_path=output_path,
            patches_by_page=patches_by_page,
            pages_without_tables=pages_without_tables
        )

        summary = {
            "input_file": pdf_path,
            "output_file": output_path,
            "pages_passthrough_count": len(pages_without_tables),
            "pages_patched_count": len(pages_with_tables),
            "total_tables_flattened": total_tables_processed,
            "status": "success"
        }
        logger.info(f"Processing complete: {summary}")
        return summary
