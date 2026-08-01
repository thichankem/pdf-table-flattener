"""Detection of tables that are aligned by whitespace instead of ruled lines.

pdfplumber's own ``text`` strategy treats every line of the page as a table row,
so switching it on turns ordinary prose into nonsense tables and destroys the
"leave non-table content alone" guarantee.  This module looks for the one thing
a borderless table has and running text does not: a **column gutter** -- a
vertical band of whitespace that survives unbroken across a run of consecutive
lines.

Everything here is deliberately conservative.  A missed borderless table leaves
the page untouched, which is safe; a false positive would shred a paragraph.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .text_utils import is_bullet_line

#: Leader dots ("Chapter one .......... 12") give a table of contents the same
#: shape as a two-column table: aligned left text, a clean gutter, a right-hand
#: number.  They are a universal typographic convention, and a contents list is
#: not a table -- flattening one would rewrite ordinary front matter.
LEADER_RE = re.compile(r"[.·‧]{4,}")
MAX_LEADER_RATIO = 0.3

logger = logging.getLogger(__name__)

BBox = Tuple[float, float, float, float]

MIN_ROWS = 3
MIN_GUTTER_WIDTH = 7.0
MIN_COLUMN_WIDTH = 12.0
#: Share of a run's lines that must reach into every detected column.  A
#: bulleted list also has a gutter (after the bullet glyph) but its wrapped
#: lines leave the first column empty, so it fails this test.
MIN_FULL_ROW_RATIO = 0.7
#: How far apart two lines may sit and still belong to the same run.
MAX_LINE_GAP_FACTOR = 2.2


@dataclass
class BorderlessTable:
    bbox: BBox
    column_edges: List[float]
    row_edges: List[float]

    @property
    def n_cols(self) -> int:
        return max(0, len(self.column_edges) - 1)


def _lines_from_words(words: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    heights = [w["bottom"] - w["top"] for w in ordered if w["bottom"] > w["top"]]
    median_h = sorted(heights)[len(heights) // 2] if heights else 10.0
    tol = max(2.0, median_h * 0.6)

    lines: List[List[Dict[str, Any]]] = [[ordered[0]]]
    for w in ordered[1:]:
        if abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    return lines


def _gutters(lines: Sequence[List[Dict[str, Any]]]) -> List[Tuple[float, float]]:
    """Vertical whitespace bands shared by *every* line in the run."""
    x0 = min(w["x0"] for line in lines for w in line)
    x1 = max(w["x1"] for line in lines for w in line)
    if x1 - x0 <= 0:
        return []

    step = 1.0
    n_bins = int((x1 - x0) / step) + 1
    occupied = [False] * n_bins

    for line in lines:
        for w in line:
            lo = max(0, int((w["x0"] - x0) / step))
            hi = min(n_bins - 1, int((w["x1"] - x0) / step))
            for i in range(lo, hi + 1):
                occupied[i] = True

    bands: List[Tuple[float, float]] = []
    start: Optional[int] = None
    for i, taken in enumerate(occupied):
        if not taken and start is None:
            start = i
        elif taken and start is not None:
            bands.append((x0 + start * step, x0 + i * step))
            start = None
    if start is not None:
        bands.append((x0 + start * step, x1))

    # Interior bands only, and only ones wide enough to be a real gutter.
    return [
        (a, b)
        for a, b in bands
        if b - a >= MIN_GUTTER_WIDTH and a > x0 + MIN_COLUMN_WIDTH and b < x1 - MIN_COLUMN_WIDTH
    ]


def _column_edges(lines: Sequence[List[Dict[str, Any]]]) -> List[float]:
    gutters = _gutters(lines)
    if not gutters:
        return []
    x0 = min(w["x0"] for line in lines for w in line)
    x1 = max(w["x1"] for line in lines for w in line)
    edges = [x0 - 1.0]
    edges.extend((a + b) / 2.0 for a, b in gutters)
    edges.append(x1 + 1.0)
    return edges


def _cells_per_line(
    line: Sequence[Dict[str, Any]], edges: Sequence[float]
) -> int:
    filled = set()
    for w in line:
        centre = (w["x0"] + w["x1"]) / 2.0
        for c in range(len(edges) - 1):
            if edges[c] <= centre < edges[c + 1]:
                filled.add(c)
                break
    return len(filled)


def _runs(lines: List[List[Dict[str, Any]]]) -> List[List[List[Dict[str, Any]]]]:
    """Split lines into blocks separated by unusually large vertical gaps."""
    if not lines:
        return []
    gaps = []
    for i in range(len(lines) - 1):
        top_next = min(w["top"] for w in lines[i + 1])
        bottom = max(w["bottom"] for w in lines[i])
        gaps.append(max(0.0, top_next - bottom))
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
    limit = median_gap * MAX_LINE_GAP_FACTOR + 4.0

    runs = [[lines[0]]]
    for i in range(1, len(lines)):
        if gaps[i - 1] > limit:
            runs.append([lines[i]])
        else:
            runs[-1].append(lines[i])
    return runs


def _full_row_ratio(
    run: Sequence[List[Dict[str, Any]]], edges: Sequence[float]
) -> float:
    n_cols = len(edges) - 1
    if n_cols < 1 or not run:
        return 0.0
    full = sum(1 for line in run if _cells_per_line(line, edges) >= n_cols)
    return full / len(run)


def _accept(run: Sequence[List[Dict[str, Any]]], edges: Sequence[float]) -> bool:
    n_cols = len(edges) - 1
    if n_cols < 2 or len(run) < MIN_ROWS:
        return False
    texts = [" ".join(w["text"] for w in line) for line in run]
    # A list ("- item", "+ item") has a gutter after its glyph but is not a table.
    if all(is_bullet_line(t) for t in texts):
        return False
    if sum(bool(LEADER_RE.search(t)) for t in texts) > len(texts) * MAX_LEADER_RATIO:
        return False
    return _full_row_ratio(run, edges) >= MIN_FULL_ROW_RATIO


def find_borderless_tables(
    page, exclude: Sequence[BBox] = ()
) -> List[BorderlessTable]:
    """Locate whitespace-aligned tables on `page`, skipping `exclude` regions."""
    try:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Word extraction failed: %s", exc)
        return []

    def outside(w: Dict[str, Any]) -> bool:
        cx, cy = (w["x0"] + w["x1"]) / 2.0, (w["top"] + w["bottom"]) / 2.0
        return not any(
            b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in exclude
        )

    lines = _lines_from_words([w for w in words if outside(w)])

    found: List[BorderlessTable] = []
    for block in _runs(lines):
        run, edges = _best_variant(block)
        if not run:
            continue

        row_edges = _row_edges(run)
        found.append(
            BorderlessTable(
                bbox=(
                    edges[0],
                    row_edges[0],
                    edges[-1],
                    row_edges[-1],
                ),
                column_edges=list(edges),
                row_edges=row_edges,
            )
        )
    if found:
        logger.info("Found %d borderless table(s).", len(found))
    return found


MAX_TRIM = 2


def _best_variant(
    block: List[List[Dict[str, Any]]],
) -> Tuple[List[List[Dict[str, Any]]], List[float]]:
    """Pick the sub-run that reads best as a table.

    A caption sitting directly above the table belongs to the same vertical run
    and, because it stretches across the gutters, it hides the very columns we
    are looking for.  Trying a few leading/trailing trims and keeping whichever
    yields the most columns leaves such lines outside the table, where they are
    passed through as ordinary prose.
    """
    best: Tuple[List[List[Dict[str, Any]]], List[float]] = ([], [])
    best_score = (0, 0.0, 0)
    for head in range(MAX_TRIM + 1):
        for tail in range(MAX_TRIM + 1):
            run = block[head : len(block) - tail] if tail else block[head:]
            if len(run) < MIN_ROWS:
                continue
            edges = _column_edges(run)
            if not edges or not _accept(run, edges):
                continue
            # Most columns first, then the cleanest fit, and only then size --
            # otherwise a caption that half-fits is kept just for being an
            # extra row.
            score = (
                len(edges) - 1,
                round(_full_row_ratio(run, edges), 3),
                len(run),
            )
            if score > best_score:
                best_score, best = score, (run, edges)
    return best


def _row_edges(run: Sequence[List[Dict[str, Any]]]) -> List[float]:
    edges = [min(w["top"] for w in run[0]) - 1.0]
    for i in range(len(run) - 1):
        bottom = max(w["bottom"] for w in run[i])
        top_next = min(w["top"] for w in run[i + 1])
        edges.append((bottom + top_next) / 2.0)
    edges.append(max(w["bottom"] for w in run[-1]) + 1.0)
    return edges
