"""Lossless, geometry-driven table extraction.

``pdfplumber.Table.extract()`` re-runs its own cell detection and happily drops
text that falls between detected cells (and picks the wrong table entirely when
tables are nested).  This module instead takes the *cell rectangles* pdfplumber
already found and assigns every single word inside the table bbox to exactly one
cell.  A word can never be dropped: if it is inside no cell rectangle it is
attached to the geometrically nearest one.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
import logging

from .text_utils import normalize_text

logger = logging.getLogger(__name__)

BBox = Tuple[float, float, float, float]

EDGE_TOLERANCE = 3.0


@dataclass
class CellLine:
    """One visual line of text inside a cell, with the geometry needed to infer
    list nesting and paragraph breaks."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class Item:
    """One logical bullet inside a cell."""

    level: int
    text: str
    marker: str = ""


@dataclass
class GridCell:
    row: int
    col: int
    row_span: int
    col_span: int
    bbox: BBox
    lines: List[CellLine] = field(default_factory=list)
    # Pre-parsed bullets, for a source that already knows its own paragraph
    # structure (a .docx cell states it explicitly).  When None -- the PDF case
    # -- the items are inferred from the geometry of `lines`.
    items: Optional[List[Item]] = None

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class Grid:
    """A normalised table: `n_rows` x `n_cols` of anchored cells."""

    n_rows: int
    n_cols: int
    cells: List[GridCell] = field(default_factory=list)
    bbox: BBox = (0.0, 0.0, 0.0, 0.0)

    def as_matrix(self) -> List[List[str]]:
        """Row-major text matrix; spanned positions repeat as empty strings."""
        matrix = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for cell in self.cells:
            if 0 <= cell.row < self.n_rows and 0 <= cell.col < self.n_cols:
                matrix[cell.row][cell.col] = cell.text
        return matrix

    def row_cells(self, row_idx: int) -> List[GridCell]:
        return sorted(
            [c for c in self.cells if c.row == row_idx], key=lambda c: c.col
        )

    def all_text(self) -> str:
        return "\n".join(c.text for c in self.cells if c.text.strip())


def _cluster_edges(values: Sequence[float], tolerance: float = EDGE_TOLERANCE) -> List[float]:
    """Collapse near-identical coordinates into a sorted list of grid lines."""
    if not values:
        return []
    ordered = sorted(values)
    clusters: List[List[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - clusters[-1][-1] <= tolerance:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def _index_of(edges: List[float], value: float, tolerance: float = EDGE_TOLERANCE) -> int:
    """Index of the edge closest to `value` (never out of range)."""
    best, best_d = 0, float("inf")
    for i, e in enumerate(edges):
        d = abs(e - value)
        if d < best_d:
            best, best_d = i, d
    return best


def _belongs_to(word: Dict[str, Any], bbox: BBox) -> bool:
    """Is this word part of the table?

    Requiring full containment loses words that overhang a cell border by a
    fraction of a point -- and those are exactly the words redaction wipes off
    the page, so they would vanish from the document.  A word counts as the
    table's when most of it, or its centre, sits inside.
    """
    x0, top, x1, bottom = bbox
    wx0, wtop, wx1, wbottom = word["x0"], word["top"], word["x1"], word["bottom"]

    cx, cy = (wx0 + wx1) / 2.0, (wtop + wbottom) / 2.0
    if x0 - 1 <= cx <= x1 + 1 and top - 1 <= cy <= bottom + 1:
        return True

    overlap_w = min(wx1, x1) - max(wx0, x0)
    overlap_h = min(wbottom, bottom) - max(wtop, top)
    if overlap_w <= 0 or overlap_h <= 0:
        return False
    word_area = max(1e-6, (wx1 - wx0) * (wbottom - wtop))
    return (overlap_w * overlap_h) / word_area >= 0.30


def _rect_distance(bbox: BBox, x: float, y: float) -> float:
    x0, top, x1, bottom = bbox
    dx = max(x0 - x, 0.0, x - x1)
    dy = max(top - y, 0.0, y - bottom)
    return (dx * dx + dy * dy) ** 0.5


def _join_words(group: List[Dict[str, Any]]) -> str:
    """Concatenate a line's words, inserting a space only where one was drawn.

    A glyph set in a different font -- the minus of "-3%", a bracket, a currency
    symbol -- is reported as its own word even though it touches its neighbour.
    Joining everything with a blank would turn "-3%" into "- 3%", which then
    reads as a bullet and loses the sign.
    """
    if not group:
        return ""
    widths = [
        (w["x1"] - w["x0"]) / max(1, len(w["text"]))
        for w in group
        if w["x1"] > w["x0"] and w["text"]
    ]
    char_w = sorted(widths)[len(widths) // 2] if widths else 5.0
    threshold = char_w * 0.35

    parts = [group[0]["text"]]
    for prev, w in zip(group, group[1:]):
        if w["x0"] - prev["x1"] > threshold:
            parts.append(" ")
        parts.append(w["text"])
    return "".join(parts)


def group_words_into_lines(words: List[Dict[str, Any]]) -> List[CellLine]:
    """Cluster words by baseline, then read left-to-right.

    Used for a cell's own words and, by :mod:`.outline`, for the running text
    around a table -- both need the same "what is one visual line" rule.
    """
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    heights = [w["bottom"] - w["top"] for w in ordered if w["bottom"] > w["top"]]
    median_h = sorted(heights)[len(heights) // 2] if heights else 10.0
    tolerance = max(2.0, median_h * 0.6)

    groups: List[List[Dict[str, Any]]] = [[ordered[0]]]
    for w in ordered[1:]:
        if abs(w["top"] - groups[-1][0]["top"]) <= tolerance:
            groups[-1].append(w)
        else:
            groups.append([w])

    lines: List[CellLine] = []
    for group in groups:
        group.sort(key=lambda w: w["x0"])
        text = normalize_text(_join_words(group))
        if not text:
            continue
        lines.append(
            CellLine(
                text=text,
                x0=min(w["x0"] for w in group),
                x1=max(w["x1"] for w in group),
                top=min(w["top"] for w in group),
                bottom=max(w["bottom"] for w in group),
            )
        )
    return lines


def build_grid(
    page,
    table,
    extra_words: Optional[List[Dict[str, Any]]] = None,
    nested_blocks: Optional[List[Tuple[BBox, List[str]]]] = None,
) -> Grid:
    """Build a :class:`Grid` from a pdfplumber page and one of its Table objects.

    `extra_words` lets a caller feed in words that were otherwise discarded,
    guaranteeing they still land somewhere.

    `nested_blocks` carries tables drawn *inside* a cell, already flattened to
    bullet lines.  Their words are taken out of the word stream and the finished
    bullets are spliced back in at the same place, so a sub-table keeps its own
    column pairing instead of collapsing into a run of loose words.
    """
    raw_cells = [c for c in (table.cells or []) if c]
    if not raw_cells:
        return Grid(n_rows=0, n_cols=0, cells=[], bbox=tuple(table.bbox))

    col_edges = _cluster_edges([c[0] for c in raw_cells] + [c[2] for c in raw_cells])
    row_edges = _cluster_edges([c[1] for c in raw_cells] + [c[3] for c in raw_cells])

    n_cols = max(1, len(col_edges) - 1)
    n_rows = max(1, len(row_edges) - 1)

    grid_cells: List[GridCell] = []
    seen: set = set()
    for (x0, top, x1, bottom) in raw_cells:
        c0 = _index_of(col_edges, x0)
        c1 = _index_of(col_edges, x1)
        r0 = _index_of(row_edges, top)
        r1 = _index_of(row_edges, bottom)
        col_span = max(1, c1 - c0)
        row_span = max(1, r1 - r0)
        key = (r0, c0)
        if key in seen:
            continue
        seen.add(key)
        grid_cells.append(
            GridCell(
                row=min(r0, n_rows - 1),
                col=min(c0, n_cols - 1),
                row_span=row_span,
                col_span=col_span,
                bbox=(x0, top, x1, bottom),
            )
        )

    # ---- assign every word inside the table to exactly one cell ----------
    tx0, ttop, tx1, tbottom = table.bbox
    words = page.extract_words(
        keep_blank_chars=False,
        use_text_flow=False,
        extra_attrs=["size"],
    )
    inside = [w for w in words if _belongs_to(w, (tx0, ttop, tx1, tbottom))]
    for nested_bbox, _lines in nested_blocks or []:
        inside = [w for w in inside if not _belongs_to(w, nested_bbox)]
    if extra_words:
        known = {(round(w["x0"], 2), round(w["top"], 2), w["text"]) for w in inside}
        for w in extra_words:
            if (round(w["x0"], 2), round(w["top"], 2), w["text"]) not in known:
                inside.append(w)

    buckets: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(len(grid_cells))}
    for w in inside:
        cx = (w["x0"] + w["x1"]) / 2.0
        cy = (w["top"] + w["bottom"]) / 2.0
        target = None
        for idx, cell in enumerate(grid_cells):
            bx0, btop, bx1, bbottom = cell.bbox
            if bx0 - 0.5 <= cx <= bx1 + 0.5 and btop - 0.5 <= cy <= bbottom + 0.5:
                target = idx
                break
        if target is None:
            # Never drop a word: attach it to the nearest cell rectangle.
            target = min(
                range(len(grid_cells)),
                key=lambda i: _rect_distance(grid_cells[i].bbox, cx, cy),
            )
        buckets[target].append(w)

    for idx, cell in enumerate(grid_cells):
        cell.lines = group_words_into_lines(buckets[idx])

    for nested_bbox, nested_lines in nested_blocks or []:
        _splice_nested_block(grid_cells, nested_bbox, nested_lines)

    grid_cells.sort(key=lambda c: (c.row, c.col))
    return Grid(n_rows=n_rows, n_cols=n_cols, cells=grid_cells, bbox=tuple(table.bbox))


def _splice_nested_block(
    cells: List[GridCell], bbox: BBox, lines: List[str]
) -> None:
    """Insert a sub-table's finished bullets into the cell that contains it.

    They enter as ordinary cell lines placed at the sub-table's own position, so
    everything downstream -- ordering, indent level, wrapping -- treats them
    like any other bullet the cell already had.
    """
    if not lines or not cells:
        return

    x0, top, x1, bottom = bbox
    cx, cy = (x0 + x1) / 2.0, (top + bottom) / 2.0
    target = min(cells, key=lambda c: _rect_distance(c.bbox, cx, cy))

    height = max(1.0, bottom - top)
    step = height / max(1, len(lines))
    for i, text in enumerate(lines):
        line_top = top + i * step
        target.lines.append(
            CellLine(
                # Already normalised by the formatter; re-normalising here would
                # collapse the "  |  " column separator down to a single space.
                text=text,
                x0=x0,
                # Sub-table bullets are self-contained: never let the paragraph
                # joiner glue the next line of the parent cell onto them.
                x1=x0 + 1.0,
                top=line_top,
                bottom=line_top + step * 0.9,
            )
        )
    target.lines.sort(key=lambda ln: ln.top)


def words_in_bbox(page, bbox: BBox) -> List[Dict[str, Any]]:
    return [
        w
        for w in page.extract_words(keep_blank_chars=False, use_text_flow=False)
        if _belongs_to(w, bbox)
    ]
