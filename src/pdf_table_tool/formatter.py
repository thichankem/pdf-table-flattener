"""Turn an extracted :class:`Grid` into flat bullet lines.

Output shape (test.md):

    - Tên: Nam  |  Tuổi: 25  |  Chức vụ: Dev

Rows whose last column holds a long, multi-paragraph cell are rendered as a
header line plus indented sub-bullets, because squeezing several paragraphs onto
one physical line is unreadable and would still be a bullet list.

Guarantees enforced here:

* no invented column labels ("Cột 1:", "Column 2:") -- see `_is_fake_header`;
* no header repeated as its own value ("Điều kiện: Điều kiện vay vốn");
* no blank lines at all inside a table's bullet block;
* every token of the source grid appears in the output (`_completeness_guard`).
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .grid_extractor import CellLine, Grid, GridCell, Item
from .text_utils import (
    bullet_marker,
    collapse_blank_lines,
    is_bullet_line,
    join_wrapped_lines,
    strip_bullet,
    tokenize,
)

logger = logging.getLogger(__name__)

SEPARATOR = "  |  "
INDENT_UNIT = "  "
LEVEL_MARKERS = ["-", "+", "*"]

_FAKE_HEADER_RE = re.compile(
    r"^(cột|cot|column|col|field|trường|unnamed|no\.?|#)\s*\d*$", re.IGNORECASE
)


@dataclass
class TableStructure:
    """How a table is laid out.

    `header_rows`   how many leading rows label the columns (0 = none).
    `label_column`  whether column 0 labels each row instead.

    A table can have neither (a plain grid of values), either, or both.  Getting
    this wrong is what produces nonsense like pairing every row of a row-header
    table with the first row's sentence.
    """

    header_rows: int = 0
    label_column: bool = False
    source: str = "geometry"


def _is_fake_header(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    return bool(_FAKE_HEADER_RE.match(v))


def cell_to_items(cell: GridCell) -> List[Item]:
    """Parse a cell's visual lines into nested logical bullets.

    Nesting comes from the x-position of the bullet glyphs, not from guessing at
    the glyph itself, so documents that use ``-``/``+``/``•`` in any order work.

    A cell that already carries its items (a .docx paragraph knows its own list
    level) skips the inference entirely -- guessing at synthetic geometry would
    only be able to get it wrong.
    """
    if cell.items is not None:
        return list(cell.items)

    lines = [ln for ln in cell.lines if ln.text.strip()]
    if not lines:
        return []

    bullet_x = sorted({round(ln.x0, 0) for ln in lines if is_bullet_line(ln.text)})
    levels: List[float] = []
    for x in bullet_x:
        if not levels or x - levels[-1] > 6.0:
            levels.append(x)

    def level_of(x: float) -> int:
        best, best_d = 0, float("inf")
        for i, lx in enumerate(levels):
            d = abs(lx - x)
            if d < best_d:
                best, best_d = i, d
        return best

    # A paragraph break needs two independent signals, because either one alone
    # produces wrong splits on real documents:
    #   * a vertical gap clearly larger than this cell's own line spacing --
    #     measured against the *median gap*, not the glyph height, so 1.5-spaced
    #     text does not break on every line;
    #   * the previous line not running to the cell's right margin.  A full line
    #     is by definition mid-sentence, so whatever follows continues it.
    gaps = [
        lines[i + 1].top - lines[i].bottom
        for i in range(len(lines) - 1)
        if lines[i + 1].top >= lines[i].bottom
    ]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
    break_threshold = median_gap * 1.25 + 1.0
    right_margin = max(ln.x1 for ln in lines)
    full_line_x = right_margin - max(6.0, (right_margin - min(ln.x0 for ln in lines)) * 0.06)

    items: List[Item] = []
    buffer: List[str] = []
    current_level = 0
    current_marker = ""
    prev: Optional[CellLine] = None

    def flush() -> None:
        nonlocal buffer
        if buffer:
            text = join_wrapped_lines(buffer).strip()
            if text:
                items.append(
                    Item(level=current_level, text=text, marker=current_marker)
                )
        buffer = []

    for ln in lines:
        starts_bullet = is_bullet_line(ln.text)
        paragraph_break = (
            prev is not None
            and (ln.top - prev.bottom) > break_threshold
            and prev.x1 < full_line_x
        )
        if starts_bullet or (paragraph_break and buffer):
            flush()
            if starts_bullet:
                current_level = level_of(ln.x0)
                current_marker = bullet_marker(ln.text)
                buffer.append(strip_bullet(ln.text))
            else:
                current_marker = ""
                buffer.append(ln.text)
        else:
            buffer.append(ln.text)
        prev = ln

    flush()
    return items


def _is_simple(items: Sequence[Item]) -> bool:
    """A cell is 'simple' when it is a single short bullet-free run of text."""
    return len(items) <= 1 and all(item.level == 0 for item in items)


def _label(header: str, value: str) -> str:
    """``Header: value``, unless the label would be noise or a duplicate."""
    h = (header or "").strip().rstrip(":").strip()
    v = (value or "").strip()
    if not h or _is_fake_header(h):
        return v
    hl, vl = h.lower(), v.lower()
    if hl == vl or vl.startswith(hl):
        return v
    if is_bullet_line(h):
        return v
    return f"{h}: {v}"


MAX_LABEL_CHARS = 60


def _row_cells(matrix_cells, row: int, n_cols: int) -> List[GridCell]:
    return [matrix_cells[(row, c)] for c in range(n_cols) if (row, c) in matrix_cells]


def _row_can_be_header(matrix_cells, grid: Grid, row: int) -> bool:
    """Could row `row` be labelling the columns below it?

    The decisive test is structural, not textual: a header cell may not merge
    columns that the rows below keep apart.  In

        | Điều kiện | one long sentence spanning both columns |
        | Tình huống | Thỏa điều kiện | Không thỏa điều kiện   |

    the first row cannot be a header, because it has nothing to say about the
    two separate columns underneath -- it is a labelled data row, and the labels
    live in column 0.
    """
    for cell in _row_cells(matrix_cells, row, grid.n_cols):
        if cell.col_span <= 1:
            continue
        for lower in range(row + cell.row_span, grid.n_rows):
            covered = [
                matrix_cells[(lower, c)]
                for c in range(cell.col, min(cell.col + cell.col_span, grid.n_cols))
                if (lower, c) in matrix_cells and not matrix_cells[(lower, c)].is_empty
            ]
            if len(covered) > 1:
                return False
    return True


def _header_band_height(matrix_cells, grid: Grid) -> int:
    """How many leading rows form the header, or 0 when there is no header row."""
    if grid.n_rows < 2 or grid.n_cols < 2:
        return 0

    row0 = _row_cells(matrix_cells, 0, grid.n_cols)
    present = [c for c in row0 if not c.is_empty]
    if not present:
        return 0
    # One filled cell cannot be naming three or more columns; in a two-column
    # table a blank label-column header is normal.
    if grid.n_cols >= 3 and len(present) < 2:
        return 0
    if any(is_bullet_line(c.text) or len(c.text) > 150 for c in present):
        return 0
    # A row of pure numbers is data, not a header.
    if all(re.fullmatch(r"[\d.,%/\s-]+", c.text.strip()) for c in present):
        return 0
    if not _row_can_be_header(matrix_cells, grid, 0):
        return 0

    # A header names every column.  When the first row fills fewer cells than
    # the rows beneath it, it is not labelling them -- most often it is a cell
    # continued from the previous page, whose text would otherwise be pasted in
    # front of every row as a bogus label.
    widest_data_row = max(
        (
            len([c for c in _row_cells(matrix_cells, r, grid.n_cols) if not c.is_empty])
            for r in range(1, grid.n_rows)
        ),
        default=0,
    )
    if len(present) < widest_data_row:
        return 0

    # A header can occupy two grid rows: its own text wraps in the narrow
    # columns while the label column keeps one cell spanning the whole band.
    # Row `r` is still header when both hold:
    #   * its cells sit only under row-0 cells that do NOT span the band, i.e.
    #     under headers that had room to wrap;
    #   * none of them is a bare number -- a numeric row is data, which is what
    #     tells a wrapped header apart from a rowspan group ("Nhóm A" over
    #     I / II / III).
    wrappable = {
        c.col for c in row0 if c.row_span == 1 and not c.is_empty
    }
    band_limit = min(max((c.row_span for c in row0), default=1), 3, grid.n_rows - 1)

    band = 1
    for r in range(1, band_limit):
        cells = [c for c in _row_cells(matrix_cells, r, grid.n_cols) if not c.is_empty]
        if cells:
            if any(is_bullet_line(c.text) for c in cells):
                break
            if any(c.col not in wrappable for c in cells):
                break
            if any(re.fullmatch(r"[\d.,%/\s-]+", c.text.strip()) for c in cells):
                break
        # An empty row means the header above already covers it -- either as a
        # blank spanning cell or as a wrapped header the cell normaliser fused.
        band = r + 1
    return band


def _has_label_column(rows: List[List[GridCell]], n_cols: int) -> bool:
    """Does column 0 hold a short label for each row rather than data?"""
    if n_cols < 2 or len(rows) < 2:
        return False

    labels: List[str] = []
    body_lengths: List[int] = []
    for row in rows:
        if not row or row[0].col != 0:
            return False
        text = " ".join(row[0].text.split())
        if not text or len(text) > MAX_LABEL_CHARS or is_bullet_line(text):
            return False
        # A numbering column ("3.7", "1", "a.") indexes rows, it does not name
        # them -- prefixing every value with it reads worse than a plain join.
        if not any(ch.isalpha() for ch in text):
            return False
        if len(row) < 2:
            return False
        labels.append(text.lower())
        body_lengths.extend(len(c.text) for c in row[1:])

    if len(set(labels)) != len(labels) or not body_lengths:
        return False

    # Labels are consistently shorter than what they label.
    return (sum(len(x) for x in labels) / len(labels)) < (
        sum(body_lengths) / len(body_lengths)
    )


def _merge_cells(cells: List[GridCell]) -> GridCell:
    """Fuse vertically stacked cells of one column into a single logical cell."""
    first = cells[0]
    merged_lines: List[CellLine] = []
    for cell in cells:
        merged_lines.extend(cell.lines)
    merged_items: Optional[List[Item]] = None
    if any(c.items is not None for c in cells):
        merged_items = [item for c in cells for item in (c.items or [])]
    return GridCell(
        row=first.row,
        col=first.col,
        row_span=sum(c.row_span for c in cells),
        col_span=first.col_span,
        bbox=(
            min(c.bbox[0] for c in cells),
            min(c.bbox[1] for c in cells),
            max(c.bbox[2] for c in cells),
            max(c.bbox[3] for c in cells),
        ),
        lines=merged_lines,
        items=merged_items,
    )


def _fills_column(cell: GridCell) -> bool:
    """Does this cell's text run all the way to its right edge?

    A full last line means the text was cut off by the column, not by the
    author -- so whatever sits directly below continues the same sentence.
    """
    if not cell.lines:
        return False
    width = cell.bbox[2] - cell.bbox[0]
    if width <= 0:
        return False
    return cell.lines[-1].x1 >= cell.bbox[2] - max(10.0, width * 0.08)


def normalise_sliced_cells(grid: Grid) -> Grid:
    """Rejoin cells that are really one paragraph cut apart by stray rulings.

    Word emits faint interior rules inside a merged cell, so pdfplumber reports
    a single wrapped paragraph as three stacked one-line cells -- and the table
    then looks like three rows with two of them unlabelled.  Cells are fused
    when they sit in the same column, touch vertically, and the boundary between
    them is not a real row: either the upper cell runs to the column's right
    edge, or the rule that separates them is drawn in this column alone.
    """
    def rule_is_local(cell: GridCell, boundary: int) -> bool:
        """Is the rule under `cell` drawn inside this column only?

        A table row is ruled straight across, so every column has an edge on it.
        A rule that no other column shares is not a row boundary at all -- it is
        the box some generators draw around a single cell's wrapped text, which
        otherwise splits one invoice into two rows that repeat every other
        column's value.
        """
        covered = range(cell.col, cell.col + cell.col_span)
        for other in grid.cells:
            if other.col in covered:
                continue
            if other.row + other.row_span - 1 == boundary or other.row == boundary + 1:
                return False
        return True

    def splits_elsewhere(cell: GridCell, boundary: int) -> bool:
        """Does another column start a new record across this row boundary?

        If it does, the boundary is a real table row (a rowspan group, or the
        next numbered item) and the two cells must stay apart.
        """
        covered = range(cell.col, cell.col + cell.col_span)
        for c in range(grid.n_cols):
            if c in covered:
                continue
            ends = any(
                o.col <= c < o.col + o.col_span
                and o.row + o.row_span - 1 == boundary
                and not o.is_empty
                for o in grid.cells
            )
            starts = any(
                o.col <= c < o.col + o.col_span
                and o.row == boundary + 1
                and not o.is_empty
                for o in grid.cells
            )
            if ends and starts:
                return True
        return False

    by_column: Dict[Tuple[int, int], List[GridCell]] = {}
    for cell in grid.cells:
        by_column.setdefault((cell.col, cell.col_span), []).append(cell)

    kept: List[GridCell] = []
    for cells in by_column.values():
        cells.sort(key=lambda c: c.row)
        run: List[GridCell] = []
        for cell in cells:
            if run:
                prev = run[-1]
                boundary = prev.row + prev.row_span - 1
                touching = abs(prev.bbox[3] - cell.bbox[1]) <= 3.0
                if (
                    touching
                    and (_fills_column(prev) or rule_is_local(prev, boundary))
                    and not splits_elsewhere(prev, boundary)
                ):
                    run.append(cell)
                    continue
                kept.append(_merge_cells(run) if len(run) > 1 else run[0])
                run = []
            run.append(cell)
        if run:
            kept.append(_merge_cells(run) if len(run) > 1 else run[0])

    kept.sort(key=lambda c: (c.row, c.col))
    return Grid(n_rows=grid.n_rows, n_cols=grid.n_cols, cells=kept, bbox=grid.bbox)


def _logical_rows(
    grid: Grid, matrix_cells, first_data_row: int
) -> List[List[GridCell]]:
    """Group grid rows into the rows a reader actually sees.

    A boundary between two grid rows is real only when some column has one cell
    ending above it and another starting below it.  A merged cell spanning the
    boundary is not enough on its own: in a rowspan group ("Nhóm A" covering
    I / II / III) the other columns do split, and those are genuine rows.
    """
    def is_real_boundary(above: int) -> bool:
        for c in range(grid.n_cols):
            ends_above = any(
                cell.col <= c < cell.col + cell.col_span
                and cell.row + cell.row_span - 1 == above
                and not cell.is_empty
                for cell in grid.cells
            )
            starts_below = any(
                cell.col <= c < cell.col + cell.col_span
                and cell.row == above + 1
                and not cell.is_empty
                for cell in grid.cells
            )
            if ends_above and starts_below:
                return True
        return False

    groups: List[List[int]] = []
    for r in range(first_data_row, grid.n_rows):
        if groups and not is_real_boundary(r - 1):
            groups[-1].append(r)
        else:
            groups.append([r])

    rows: List[List[GridCell]] = []
    for group in groups:
        lo, hi = group[0], group[-1]
        # A cell is part of every row its rowspan covers, so a value merged down
        # the side of a table ("1,5%" against six years) belongs to each of
        # those rows instead of only the first.
        cells = [
            cell
            for cell in grid.cells
            if not cell.is_empty
            and cell.row >= first_data_row
            and cell.row <= hi
            and cell.row + cell.row_span - 1 >= lo
        ]
        if cells:
            rows.append(sorted(cells, key=lambda c: (c.col, c.row)))
    return rows


def _record_columns(rows: List[List[GridCell]]) -> List[int]:
    """Data columns that each stand for one record in a two-dimensional table.

    Taken from the row that splits into the most cells, so a label row that
    merges the data columns together does not hide the split.
    """
    best: List[int] = []
    for row in rows:
        anchors = sorted({c.col for c in row if c.col > 0})
        if len(anchors) > len(best):
            best = anchors
    return best


def detect_structure(grid: Grid, matrix_cells=None) -> TableStructure:
    """Work out a table's orientation from its geometry."""
    if matrix_cells is None:
        grid = normalise_sliced_cells(grid)
        matrix_cells = {(c.row, c.col): c for c in grid.cells}
    header_rows = _header_band_height(matrix_cells, grid)
    rows = _logical_rows(grid, matrix_cells, header_rows)
    label_column = _has_label_column(rows, grid.n_cols)
    return TableStructure(
        header_rows=header_rows, label_column=label_column, source="geometry"
    )


def _normalise_label(value: str) -> str:
    return " ".join((value or "").split()).strip(" :").lower()


def _restates(detected: Sequence[str], inherited: Sequence[str]) -> bool:
    """Does this page's own header band repeat the headers carried over?

    Word repeats a table's header row on every page it spills onto, but only if
    the author asked it to.  When it does, the band is a real header and must be
    dropped from the data; when it does not, whatever geometry found in row 0 is
    the page's first record.
    """
    found = [_normalise_label(h) for h in detected]
    found = [h for h in found if h]
    carried = {_normalise_label(h) for h in inherited if _normalise_label(h)}
    if not found or not carried:
        return False
    hits = sum(1 for h in found if h in carried)
    return hits * 2 >= len(found)


def _carry_headers(
    detected: List[str],
    first_data_row: int,
    inherited: Sequence[str],
    n_cols: int,
) -> Tuple[List[str], int]:
    """Column labels for a table continued from the previous page.

    A continuation page usually starts straight into data, with the headers left
    behind on the page before.  Row 0 then looks exactly like a header to pure
    geometry -- short cells, one per column, no bullets -- and every row below it
    ends up captioned with the first invoice's own values ("HD-2026-0021: HD-
    2026-0022").  Carrying the real headers across the page break is the only way
    to tell the two apart, so when row 0 does not restate them it is data.
    """
    carried = list(inherited[:n_cols]) + [""] * max(0, n_cols - len(inherited))
    if first_data_row and _restates(detected, inherited):
        return detected, first_data_row
    if first_data_row:
        logger.info(
            "Continuation table: row 0 is data, not a header -- reusing the "
            "headers from the previous page."
        )
    return carried, 0


class TableFormatter:
    """Renders a :class:`Grid` (plus optionally inherited headers) to bullets."""

    def format_grid(
        self,
        grid: Grid,
        inherited_headers: Optional[List[str]] = None,
        structure: Optional[TableStructure] = None,
    ) -> Tuple[List[str], List[str]]:
        """Return ``(bullet_lines, headers_for_next_page)``.

        `structure` overrides the geometric layout analysis, which is how a
        format that states its own header rows (Word, Excel) gets to win.
        """
        original = grid
        grid = normalise_sliced_cells(grid)
        matrix_cells = {(c.row, c.col): c for c in grid.cells}
        if structure is None:
            structure = detect_structure(grid, matrix_cells)

        headers, first_data_row = self._resolve_headers(
            grid, matrix_cells, structure.header_rows
        )
        if inherited_headers and any(h.strip() for h in inherited_headers):
            headers, first_data_row = _carry_headers(
                headers, first_data_row, inherited_headers, grid.n_cols
            )

        label_column = structure.label_column and not any(
            h.strip() for h in headers[1:]
        )

        rows = _logical_rows(grid, matrix_cells, first_data_row)

        lines: List[str] = []
        record_cols = _record_columns(rows) if label_column else []
        if len(record_cols) >= 2:
            # Two-dimensional table: the labels run down the side and each data
            # column is one record.  Reading it row by row would scatter a
            # single case across several bullets, so pivot instead.
            lines = self._render_pivoted(rows, record_cols)
        else:
            for row_cells in rows:
                lines.extend(self._render_row(row_cells, headers, label_column))

        if not lines and any(h.strip() for h in headers):
            lines.append("- " + SEPARATOR.join(h for h in headers if h.strip()))

        # Guard against the *original* grid so a bug in cell normalisation can
        # never make text disappear.
        lines = _completeness_guard(original, lines, first_data_row, headers)
        return collapse_blank_lines(lines), headers

    # -- headers ---------------------------------------------------------
    def _resolve_headers(
        self, grid: Grid, matrix_cells, header_rows: int
    ) -> Tuple[List[str], int]:
        """Merge the header band into one label per column."""
        headers = ["" for _ in range(grid.n_cols)]
        band = max(0, min(header_rows, grid.n_rows - 1))
        if band == 0:
            return headers, 0

        for c in range(grid.n_cols):
            parts: List[str] = []
            for r in range(band):
                cell = matrix_cells.get((r, c))
                if cell is None or cell.is_empty:
                    continue
                parts.extend(ln.text for ln in cell.lines)
            if not parts:
                continue
            merged = join_wrapped_lines(parts)
            headers[c] = "" if _is_fake_header(merged) else merged

        # Horizontally merged header cells label every column they cover.
        for c in range(grid.n_cols):
            cell = matrix_cells.get((0, c))
            if cell is not None and cell.col_span > 1 and headers[c]:
                for extra in range(1, cell.col_span):
                    if c + extra < grid.n_cols and not headers[c + extra]:
                        headers[c + extra] = headers[c]

        return headers, band

    # -- pivoted (two-dimensional) tables ---------------------------------
    def _render_pivoted(
        self, rows: List[List[GridCell]], record_cols: List[int]
    ) -> List[str]:
        """One bullet per data column, captioned by the labels down column 0.

            | Điều kiện          | applies to both columns          |
            | Tình huống         | Thỏa điều kiện | Không thỏa      |
            | Thứ tự phân bổ phí | Đóng cho A     | Đóng cho B      |

        becomes one bullet for "Thỏa điều kiện" and one for "Không thỏa", each
        carrying every label -- which is how the table reads on the page.
        """
        out: List[str] = []
        for col in record_cols:
            parts: List[str] = []
            trailing: List[str] = []
            for row in rows:
                # Go through cell_to_items so a label wrapped across lines
                # ("Thứ tự" / "phân bổ phí") is rejoined with its space.
                label = ""
                if row[0].col == 0:
                    label_items = cell_to_items(row[0])
                    if label_items:
                        label = label_items[0].text.rstrip(":").strip()
                cell = next(
                    (
                        c
                        for c in row
                        if c.col > 0 and c.col <= col < c.col + max(1, c.col_span)
                    ),
                    None,
                )
                if cell is None:
                    continue
                items = cell_to_items(cell)
                if not items:
                    continue
                if _is_simple(items):
                    parts.append(_label(label, items[0].text))
                else:
                    parts.append(f"{label}:" if label else "")
                    for item in items:
                        level = 1 + item.level
                        marker = _normalize_marker(item.marker) or LEVEL_MARKERS[
                            min(level, len(LEVEL_MARKERS) - 1)
                        ]
                        trailing.append(f"{INDENT_UNIT * level}{marker} {item.text}")
            parts = [p for p in parts if p]
            if parts:
                out.append("- " + SEPARATOR.join(parts))
            out.extend(trailing)
        return out

    # -- rows ------------------------------------------------------------
    def _render_row(
        self,
        row_cells: List[GridCell],
        headers: List[str],
        label_column: bool = False,
    ) -> List[str]:
        parsed = [(cell, cell_to_items(cell)) for cell in row_cells]
        parsed = [(cell, items) for cell, items in parsed if items]
        if not parsed:
            return []

        row_label = ""
        if label_column and parsed and parsed[0][0].col == 0:
            first_cell, first_items = parsed[0]
            if _is_simple(first_items):
                row_label = first_items[0].text.rstrip(":").strip()
                parsed = parsed[1:]
                if not parsed:
                    return [f"- {row_label}"]

        # Cells to the left of the first multi-part cell caption the row; from
        # there on, every cell is a value in its own right and keeps its own
        # place, so a neighbour's single line is never hoisted into the caption.
        first_complex = next(
            (i for i, (_c, items) in enumerate(parsed) if not _is_simple(items)),
            len(parsed),
        )
        simple = parsed[:first_complex]
        complex_cells = parsed[first_complex:]

        out: List[str] = []
        head_parts = [
            _label(_header_for(cell, headers), items[0].text)
            for cell, items in simple
        ]
        head_parts = [p for p in head_parts if p]

        if row_label and head_parts:
            head_parts[0] = f"{row_label}: {head_parts[0]}"

        if not complex_cells:
            if head_parts:
                out.append("- " + SEPARATOR.join(head_parts))
            return out

        # A multi-part cell still has a column header, and it has to appear
        # somewhere -- announce it on the caption line rather than losing it.
        captions = []
        for cell, _items in complex_cells:
            header = _header_for(cell, headers).rstrip(":").strip()
            if header and not _is_fake_header(header) and header not in captions:
                captions.append(header)
        if head_parts and captions:
            head_parts.append(f"{captions[0]}:" if len(captions) == 1
                              else SEPARATOR.join(f"{c}:" for c in captions))

        if head_parts:
            out.append("- " + SEPARATOR.join(head_parts))
        elif row_label:
            out.append(f"- {row_label}:")

        for cell, items in complex_cells:
            header = _header_for(cell, headers)
            base_indent = 1 if (head_parts or row_label) else 0
            if not head_parts and not row_label and header and not _is_fake_header(header):
                out.append(f"- {header.rstrip(':').strip()}:")
                base_indent = 1
            for item in items:
                level = base_indent + item.level
                marker = _normalize_marker(item.marker) or LEVEL_MARKERS[
                    min(level, len(LEVEL_MARKERS) - 1)
                ]
                out.append(f"{INDENT_UNIT * level}{marker} {item.text}")
        return out


def _header_for(cell: GridCell, headers: List[str]) -> str:
    """Header covering a data cell.

    Header cells and data cells rarely line up one-to-one: a header can sit in
    one normalised column while the data below it spans three, because the two
    rows have different vertical rulings.  Scanning the cell's whole column span
    finds the label that actually sits above it.
    """
    for col in range(cell.col, cell.col + max(1, cell.col_span)):
        if 0 <= col < len(headers) and headers[col].strip():
            return headers[col]
    return ""


def _normalize_marker(marker: str) -> str:
    """Keep the glyph the source document used, mapped to an ASCII equivalent."""
    if not marker:
        return ""
    if marker in "-+*":
        return marker
    return "-" if marker not in "o" else "+"


def _completeness_guard(
    grid: Grid, lines: List[str], first_data_row: int, headers: List[str]
) -> List[str]:
    """Never lose a word: append anything the renderer failed to emit.

    This is the deterministic backstop behind criterion 2 -- if a future change
    to the row renderer silently swallows a cell, the text still reaches the
    output instead of vanishing.
    """
    produced = Counter(tokenize("\n".join(lines)))
    expected = Counter()
    header_tokens = Counter()
    for cell in grid.cells:
        if cell.row < first_data_row:
            # Header text also has to reach the output -- usually as the label
            # on each row, but it must never simply disappear.  Placeholder
            # headers ("Cột 1") are the one thing we do drop on purpose.
            merged = join_wrapped_lines([ln.text for ln in cell.lines])
            if not _is_fake_header(merged):
                header_tokens.update(tokenize(merged))
            continue
        expected.update(tokenize(cell.text))
    for tok, n in header_tokens.items():
        expected[tok] = max(expected.get(tok, 0), n)

    # A token the source split across a line break ("t" + "ử") is rejoined by
    # the formatter, so it is still present -- just as part of a longer token.
    produced_stream = "".join(tokenize("\n".join(lines)))
    missing = Counter(
        {
            tok: n
            for tok, n in (expected - produced).items()
            if tok not in produced_stream
        }
    )
    if not missing:
        return lines

    recovered: List[str] = []
    for cell in grid.cells:
        if cell.is_empty:
            continue
        cell_tokens = Counter(tokenize(cell.text))
        if not (missing & cell_tokens):
            continue
        for item in cell_to_items(cell):
            if Counter(tokenize(item.text)) & missing:
                recovered.append(f"- {item.text}")
                missing -= Counter(tokenize(item.text))

    if recovered:
        logger.warning(
            "Completeness guard recovered %d bullet(s) the renderer dropped.",
            len(recovered),
        )
        lines = lines + recovered
    if missing:
        logger.error("Unrecoverable tokens after guard: %s", list(missing)[:20])
    return lines
