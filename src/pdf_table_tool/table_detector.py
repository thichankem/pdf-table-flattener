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

from .borderless import find_borderless_tables

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


def _is_white(colour: Any) -> bool:
    """True for the colour of a blank page, in any of the spaces PDFs use."""
    if colour is None:
        return False
    if isinstance(colour, (int, float)):
        return float(colour) >= 0.999          # DeviceGray
    try:
        values = [float(c) for c in colour]
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False
    if len(values) == 1:
        return values[0] >= 0.999
    if len(values) == 3:
        return all(v >= 0.999 for v in values)  # DeviceRGB
    if len(values) == 4:
        return all(v <= 0.001 for v in values)  # DeviceCMYK
    return False


def _draws_nothing(obj: Dict[str, Any]) -> bool:
    """True for a shape that puts no mark on a white page.

    Some generators lay a white, unstroked rectangle behind every paragraph.
    pdfplumber turns the edges of a shape into rulings whether or not it is ever
    drawn, so such a page of prose arrives as a stack of one-row tables -- and
    the flattener then rewrites running text as bullets.  A shape that is not
    stroked and is filled with nothing but white cannot be part of a table
    because it cannot be seen.  A coloured fill is left alone: a header band
    with no rulings of its own really does mark out a row.

    Whether a rectangle arrives as a ``rect`` or as a closed ``curve`` depends
    on which operator the producer chose, so both are covered.
    """
    if obj.get("object_type") not in ("rect", "curve"):
        return False
    if obj.get("stroke"):
        return False
    return not obj.get("fill") or _is_white(obj.get("non_stroking_color"))


def visible_page(page):
    """`page` without the shapes that draw nothing."""
    try:
        return page.filter(lambda obj: not _draws_nothing(obj))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not filter invisible rectangles: %s", exc)
        return page


def _absorb_rules(page, block) -> Tuple[List[float], List[float]]:
    """Pull partly-ruled tables' own lines into the detected block.

    A "borderless" table often still has a rule under its header, or the
    booktabs look of horizontal rules only.  Those rules belong to the table:
    if the block does not reach them they survive redaction and the output
    still contains something that reads as a table.
    """
    cols = sorted(block.column_edges)
    rows = sorted(block.row_edges)
    width = cols[-1] - cols[0]
    if width <= 0:
        return cols, rows

    horizontals = [
        ln
        for ln in list(page.lines) + [r for r in page.rects if r["height"] <= 2]
        if (ln["x1"] - ln["x0"]) >= width * 0.7
        and rows[0] - 25 <= ln["top"] <= rows[-1] + 25
    ]
    for ln in horizontals:
        cols[0] = min(cols[0], ln["x0"] - 1.0)
        cols[-1] = max(cols[-1], ln["x1"] + 1.0)
        y = (ln["top"] + ln["bottom"]) / 2.0
        if all(abs(y - r) > 2.0 for r in rows):
            rows.append(y)

    rows.sort()
    return cols, rows


def _borderless_candidates(page, ruled: List[Any]) -> List[Any]:
    """Turn whitespace-aligned tables into ordinary pdfplumber Table objects.

    Feeding the detected gutters back as ``explicit`` rulings means the rest of
    the pipeline -- cell geometry, headers, flattening, redaction -- treats a
    borderless table exactly like a ruled one.
    """
    try:
        blocks = find_borderless_tables(page, exclude=[t.bbox for t in ruled])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Borderless detection failed: %s", exc)
        return []

    out: List[Any] = []
    for block in blocks:
        cols, rows = _absorb_rules(page, block)
        settings = {
            "vertical_strategy": "explicit",
            "horizontal_strategy": "explicit",
            "explicit_vertical_lines": cols,
            "explicit_horizontal_lines": rows,
        }
        crop = (
            max(0.0, cols[0]),
            max(0.0, rows[0]),
            min(float(page.width), cols[-1]),
            min(float(page.height), rows[-1]),
        )
        try:
            tables = page.crop(crop, strict=False).find_tables(settings)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Borderless table build failed: %s", exc)
            continue
        for t in tables:
            if (t.bbox[2] - t.bbox[0]) > 20 and (t.bbox[3] - t.bbox[1]) > 15:
                out.append(t)
    return out


def detect_tables_by_page(
    pdf_path: str,
) -> Tuple[Dict[int, List[TableInfo]], Set[int]]:
    """Return (pages that contain tables, pages that contain none)."""
    pages_with_tables: Dict[int, List[TableInfo]] = {}
    pages_without_tables: Set[int] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page = visible_page(page)
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

            candidates.extend(_borderless_candidates(page, candidates))

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


def _column_edges(info: TableInfo, tolerance: float = 4.0) -> List[float]:
    """Distinct vertical rulings of a table, outer borders included."""
    if info.raw_table is None:
        return []
    values = sorted(
        {round(c[0], 1) for c in info.raw_table.cells}
        | {round(c[2], 1) for c in info.raw_table.cells}
    )
    edges: List[float] = []
    for v in values:
        if not edges or v - edges[-1] > tolerance:
            edges.append(v)
    return edges


def _same_column_grid(a: TableInfo, b: TableInfo, tolerance: float = 4.0) -> bool:
    """Do two tables share the same column layout?

    Two unrelated tables can both hug the text margins and both sit at the edge
    of their page, so position alone links tables that have nothing to do with
    each other -- and the second one then inherits the first one's headers.
    Matching interior rulings is what actually identifies one table split across
    a page break.
    """
    edges_a, edges_b = _column_edges(a), _column_edges(b)
    if not edges_a or len(edges_a) != len(edges_b):
        return False
    return all(abs(x - y) <= tolerance for x, y in zip(edges_a, edges_b))


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

        if (
            same_left
            and same_right
            and reaches_bottom
            and starts_at_top
            and _same_column_grid(last, first)
        ):
            first.is_continuation = True
            first.parent_page_num = curr
            logger.info(
                "Page %d table continues page %d table.", nxt + 1, curr + 1
            )
