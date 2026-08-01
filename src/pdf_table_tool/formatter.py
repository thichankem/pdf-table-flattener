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
from typing import List, Optional, Sequence, Tuple

from .grid_extractor import CellLine, Grid, GridCell
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
class Item:
    """One logical bullet inside a cell."""

    level: int
    text: str
    marker: str = ""


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
    """
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
    if any(is_bullet_line(c.text) for c in present):
        return 0
    # A row of pure numbers is data, not a header.
    if all(re.fullmatch(r"[\d.,%/\s-]+", c.text.strip()) for c in present):
        return 0
    if not _row_can_be_header(matrix_cells, grid, 0):
        return 0

    # A header that wraps onto a second line shows up as extra grid rows, while
    # the untouched columns keep one cell spanning the whole band.  That
    # row-span is the reliable signal for how tall the header is.
    band = max((c.row_span for c in row0), default=1)
    band = max(1, min(band, grid.n_rows - 1))

    for r in range(1, band):
        for cell in _row_cells(matrix_cells, r, grid.n_cols):
            if not cell.is_empty and is_bullet_line(cell.text):
                return r
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
    )


def _logical_rows(
    grid: Grid, matrix_cells, first_data_row: int
) -> List[List[GridCell]]:
    """Group grid rows into the rows a reader actually sees.

    Word writes a long paragraph inside a merged cell as several one-line cells,
    so pdfplumber reports three "rows" where the document shows one.  A grid row
    continues the previous one when a cell from another column spans across the
    boundary *and* both rows put all their text in the same single column -- if
    two columns are populated the boundary separates genuine records (a rowspan
    group like "Nhóm A: I / II / III") and must be kept.
    """
    def spans_boundary(above: int, below: int) -> bool:
        return any(
            cell.row <= above and below < cell.row + cell.row_span
            for cell in grid.cells
        )

    merged: List[List[GridCell]] = []
    last_raw_row = -1
    for r in range(first_data_row, grid.n_rows):
        row = [
            matrix_cells[(r, c)]
            for c in range(grid.n_cols)
            if (r, c) in matrix_cells and not matrix_cells[(r, c)].is_empty
        ]
        if not row:
            continue

        if merged and len(row) == 1 and spans_boundary(last_raw_row, r):
            target = next(
                (c for c in merged[-1] if c.col == row[0].col), None
            )
            if target is not None:
                merged[-1] = [
                    _merge_cells([c, row[0]]) if c is target else c
                    for c in merged[-1]
                ]
                last_raw_row = r
                continue

        merged.append(row)
        last_raw_row = r
    return merged


def detect_structure(grid: Grid, matrix_cells=None) -> TableStructure:
    """Work out a table's orientation from its geometry."""
    if matrix_cells is None:
        matrix_cells = {(c.row, c.col): c for c in grid.cells}
    header_rows = _header_band_height(matrix_cells, grid)
    rows = _logical_rows(grid, matrix_cells, header_rows)
    label_column = _has_label_column(rows, grid.n_cols)
    return TableStructure(
        header_rows=header_rows, label_column=label_column, source="geometry"
    )


class TableFormatter:
    """Renders a :class:`Grid` (plus optionally inherited headers) to bullets."""

    def format_grid(
        self,
        grid: Grid,
        inherited_headers: Optional[List[str]] = None,
        structure: Optional[TableStructure] = None,
    ) -> Tuple[List[str], List[str]]:
        """Return ``(bullet_lines, headers_for_next_page)``.

        `structure` overrides the geometric layout analysis -- that is the hook
        the optional LLM classifier plugs into.
        """
        matrix_cells = {(c.row, c.col): c for c in grid.cells}
        if structure is None:
            structure = detect_structure(grid, matrix_cells)

        headers, first_data_row = self._resolve_headers(
            grid, matrix_cells, structure.header_rows
        )
        if not any(h.strip() for h in headers) and inherited_headers:
            headers = list(inherited_headers)

        label_column = structure.label_column and not any(
            h.strip() for h in headers[1:]
        )

        lines: List[str] = []
        for row_cells in _logical_rows(grid, matrix_cells, first_data_row):
            lines.extend(self._render_row(row_cells, headers, label_column))

        if not lines and any(h.strip() for h in headers):
            lines.append("- " + SEPARATOR.join(h for h in headers if h.strip()))

        lines = _completeness_guard(grid, lines, first_data_row, headers)
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
