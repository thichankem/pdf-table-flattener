"""Table discovery.

Two rules matter for correctness:

1. Nested tables are dropped.  Word (and most PDF generators) draw a bullet list
   inside a cell using its own ruling lines, so pdfplumber reports it as a second
   table living *inside* the real one.  Extracting the inner one loses the outer
   table's text entirely — this was the single biggest source of content loss.
2. A table bbox is never grown.  Expanding it upwards to "catch" a continuation
   header eats page headers, logos and footnotes, which criterion 1 forbids.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

import pdfplumber

logger = logging.getLogger(__name__)

BBox = Tuple[float, float, float, float]


@dataclass
class TableInfo:
    page_num: int
    bbox: BBox
    raw_table: Any = None
    dropped_children: List[Any] = field(default_factory=list)
    is_continuation: bool = False
    parent_page_num: int = -1


def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection_area(a: BBox, b: BBox) -> float:
    x0 = max(a[0], b[0])
    top = max(a[1], b[1])
    x1 = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if x1 <= x0 or bottom <= top:
        return 0.0
    return (x1 - x0) * (bottom - top)


def _filter_nested(tables: List[Any]) -> Tuple[List[Any], Dict[int, List[Any]]]:
    """Keep only outermost tables; report which children each kept table absorbed."""
    ordered = sorted(tables, key=lambda t: _area(t.bbox), reverse=True)
    kept: List[Any] = []
    children: Dict[int, List[Any]] = {}
    for t in ordered:
        covered_by = None
        for idx, k in enumerate(kept):
            own = _area(t.bbox)
            if own <= 0:
                covered_by = idx
                break
            if _intersection_area(t.bbox, k.bbox) / own >= 0.80:
                covered_by = idx
                break
        if covered_by is None:
            kept.append(t)
            children[len(kept) - 1] = []
        else:
            children[covered_by].append(t)
            logger.debug(
                "Dropped nested table %s (inside %s)", t.bbox, kept[covered_by].bbox
            )
    return kept, children


TABLE_SETTINGS_LINES = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 3,
}


def detect_tables_by_page(
    pdf_path: str,
) -> Tuple[Dict[int, List[TableInfo]], Set[int]]:
    """Return (pages that contain tables, pages that contain none)."""
    pages_with_tables: Dict[int, List[TableInfo]] = {}
    pages_without_tables: Set[int] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            try:
                found = page.find_tables(TABLE_SETTINGS_LINES)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("find_tables failed on page %d: %s", page_num + 1, exc)
                found = []

            candidates = [
                t
                for t in found
                if (t.bbox[2] - t.bbox[0]) > 20 and (t.bbox[3] - t.bbox[1]) > 15
            ]

            if not candidates:
                pages_without_tables.add(page_num)
                continue

            kept, children = _filter_nested(candidates)
            infos = [
                TableInfo(
                    page_num=page_num,
                    bbox=tuple(t.bbox),
                    raw_table=t,
                    dropped_children=children.get(i, []),
                )
                for i, t in enumerate(kept)
            ]
            infos.sort(key=lambda ti: (ti.bbox[1], ti.bbox[0]))
            pages_with_tables[page_num] = infos

        _link_multipage_tables(pdf, pages_with_tables)

    logger.info(
        "Detected tables on %d page(s); %d page(s) pass through untouched.",
        len(pages_with_tables),
        len(pages_without_tables),
    )
    return pages_with_tables, pages_without_tables


def _link_multipage_tables(
    pdf: pdfplumber.PDF, pages_with_tables: Dict[int, List[TableInfo]]
) -> None:
    """Flag the first table of page N+1 as a continuation of page N's last table.

    This only sets metadata (used to inherit column headers).  It never modifies
    a bounding box.
    """
    sorted_pages = sorted(pages_with_tables)
    for i in range(len(sorted_pages) - 1):
        curr, nxt = sorted_pages[i], sorted_pages[i + 1]
        if nxt != curr + 1:
            continue
        curr_tables, next_tables = pages_with_tables[curr], pages_with_tables[nxt]
        if not curr_tables or not next_tables:
            continue

        last = max(curr_tables, key=lambda t: t.bbox[3])
        first = min(next_tables, key=lambda t: t.bbox[1])

        curr_h = float(pdf.pages[curr].height)
        next_h = float(pdf.pages[nxt].height)

        same_left = abs(last.bbox[0] - first.bbox[0]) <= 12.0
        same_right = abs(last.bbox[2] - first.bbox[2]) <= 12.0
        reaches_bottom = last.bbox[3] > curr_h * 0.60
        starts_at_top = first.bbox[1] < next_h * 0.25

        if same_left and same_right and reaches_bottom and starts_at_top:
            first.is_continuation = True
            first.parent_page_num = curr
            logger.info(
                "Page %d table continues page %d table.", nxt + 1, curr + 1
            )
