"""Unit tests for the pieces the three acceptance criteria rest on."""

import fitz

from pdf_table_tool.formatter import (
    TableFormatter,
    _header_for,
    _is_fake_header,
    _label,
    cell_to_items,
)
from pdf_table_tool.grid_extractor import CellLine, Grid, GridCell
from pdf_table_tool.text_layout import fit_plan, wrap_lines
from pdf_table_tool.text_utils import (
    collapse_blank_lines,
    join_wrapped_lines,
    normalize_text,
    tokenize,
)
from pdf_table_tool.config import settings


# --------------------------------------------------------------------- utils
def test_join_wrapped_lines_reunites_word_split_by_column_wrap():
    assert join_wrapped_lines(["Khoả", "n"]) == "Khoản"


def test_join_wrapped_lines_keeps_real_words_separate():
    assert (
        join_wrapped_lines(["Điều kiện vay", "vốn"]) == "Điều kiện vay vốn"
    )
    assert join_wrapped_lines(["các sản", "phẩm xi măng"]) == "các sản phẩm xi măng"


def test_normalize_text_strips_invisible_characters():
    assert normalize_text("a­b‌c d") == "abc d"


def test_collapse_blank_lines_never_leaves_two_in_a_row():
    out = collapse_blank_lines(["", "a", "", "", "b", "", ""])
    assert out == ["a", "", "b"]


# ------------------------------------------------------------------ headers
def test_fake_headers_are_recognised():
    for value in ("Cột 1", "Column 2", "col3", "Unnamed", "#", ""):
        assert _is_fake_header(value)
    for value in ("Khoản", "Điều kiện", "Tỷ lệ %"):
        assert not _is_fake_header(value)


def test_label_drops_redundant_and_fake_labels():
    assert _label("Điều kiện", "Điều kiện vay vốn") == "Điều kiện vay vốn"
    assert _label("Cột 1", "3.1") == "3.1"
    assert _label("Tuổi", "25") == "Tuổi: 25"


def test_header_lookup_follows_the_cells_column_span():
    headers = ["", "Năm dương lịch", "", "", "Phí quản lý", ""]
    cell = GridCell(row=1, col=0, row_span=1, col_span=3, bbox=(0, 0, 1, 1))
    assert _header_for(cell, headers) == "Năm dương lịch"
    cell = GridCell(row=1, col=3, row_span=1, col_span=3, bbox=(0, 0, 1, 1))
    assert _header_for(cell, headers) == "Phí quản lý"


# -------------------------------------------------------------------- cells
def _cell(lines, col=0, row=0, col_span=1, row_span=1):
    return GridCell(
        row=row, col=col, row_span=row_span, col_span=col_span,
        bbox=(0, 0, 400, 400), lines=lines,
    )


def test_cell_items_rejoin_wrapped_lines_of_the_same_bullet():
    """A line that fills the column is mid-sentence; the next line continues it."""
    lines = [
        CellLine("+ Giấy xác nhận thông tin về cư trú do công an xã/phường/thị",
                 x0=10, x1=395, top=0, bottom=10),
        CellLine("trấn xác nhận (ký, đóng dấu). Hoặc:",
                 x0=20, x1=200, top=24, bottom=34),
    ]
    items = cell_to_items(_cell(lines))
    assert len(items) == 1
    assert "xã/phường/thị trấn xác nhận" in items[0].text


def test_cell_items_split_on_a_real_paragraph_break():
    """Normal line spacing sets the baseline; a much larger gap starts a new item."""
    lines = [
        CellLine("- Câu mở đầu chạy hết chiều ngang của ô", x0=10, x1=395, top=0, bottom=10),
        CellLine("và tràn sang dòng thứ hai", x0=10, x1=200, top=12, bottom=22),
        CellLine("Đoạn văn mới hoàn toàn.", x0=10, x1=180, top=60, bottom=70),
        CellLine("nối tiếp đoạn mới", x0=10, x1=170, top=72, bottom=82),
    ]
    items = cell_to_items(_cell(lines))
    assert len(items) == 2
    assert items[0].text.endswith("dòng thứ hai")
    assert items[1].text.startswith("Đoạn văn mới")


def test_cell_items_infer_nesting_from_bullet_indentation():
    lines = [
        CellLine("- Mức 1", x0=10, x1=80, top=0, bottom=10),
        CellLine("+ Mức 2", x0=30, x1=90, top=14, bottom=24),
        CellLine("- Mức 1 nữa", x0=10, x1=95, top=28, bottom=38),
    ]
    items = cell_to_items(_cell(lines))
    assert [i.level for i in items] == [0, 1, 0]
    assert [i.marker for i in items] == ["-", "+", "-"]


# ----------------------------------------------------------------- flatten
def _grid(rows, n_cols):
    cells = []
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            lines = (
                [CellLine(text, x0=10, x1=100, top=r * 20, bottom=r * 20 + 10)]
                if text
                else []
            )
            cells.append(_cell(lines, col=c, row=r))
    return Grid(n_rows=len(rows), n_cols=n_cols, cells=cells, bbox=(0, 0, 400, 400))


def test_flatten_produces_the_bullet_shape_from_test_md():
    grid = _grid(
        [["Tên", "Tuổi", "Chức vụ"], ["Nam", "25", "Dev"]], n_cols=3
    )
    lines, headers = TableFormatter().format_grid(grid)
    assert lines == ["- Tên: Nam  |  Tuổi: 25  |  Chức vụ: Dev"]
    assert headers == ["Tên", "Tuổi", "Chức vụ"]


def test_flatten_never_invents_a_column_label():
    grid = _grid([["Cột 1", "Cột 2"], ["Nam", "25"]], n_cols=2)
    lines, _ = TableFormatter().format_grid(grid)
    assert lines == ["- Nam  |  25"]


def test_flatten_emits_no_blank_lines():
    grid = _grid(
        [["A", "B"], ["", ""], ["1", "2"], ["", ""], ["3", "4"]], n_cols=2
    )
    lines, _ = TableFormatter().format_grid(grid)
    assert all(line.strip() for line in lines)


def test_completeness_guard_recovers_text_the_renderer_would_drop():
    """Even a cell the row renderer ignores must still reach the output."""
    grid = _grid([["A", "B"], ["giá trị một", "giá trị hai"]], n_cols=2)
    lines, _ = TableFormatter().format_grid(grid)
    produced = set(tokenize("\n".join(lines)))
    for cell in grid.cells:
        assert set(tokenize(cell.text)) <= produced


def test_headers_spanning_two_rows_are_merged():
    """A header that wraps shows up as two grid rows joined by a spanning cell."""
    cells = [
        GridCell(0, 0, row_span=2, col_span=1, bbox=(0, 0, 10, 20), lines=[]),
        GridCell(0, 1, 1, 1, (10, 0, 100, 10),
                 [CellLine("Tuổi của Người được bảo hiểm", 12, 98, 0, 9)]),
        GridCell(1, 1, 1, 1, (10, 10, 100, 20),
                 [CellLine("chính (tuổi)", 12, 60, 11, 19)]),
        GridCell(2, 0, 1, 2, (0, 20, 100, 30), [CellLine("0", 2, 8, 21, 29)]),
    ]
    grid = Grid(n_rows=3, n_cols=2, cells=cells, bbox=(0, 0, 100, 30))
    lines, headers = TableFormatter().format_grid(grid)
    assert headers[1] == "Tuổi của Người được bảo hiểm chính (tuổi)"
    assert lines == ["- Tuổi của Người được bảo hiểm chính (tuổi): 0"]


# ------------------------------------------------------------------ layout
def test_wrap_lines_keeps_every_word():
    font = fitz.Font(fontfile=settings.get_font_path())
    source = ["- " + " ".join(f"từ{i}" for i in range(60))]
    wrapped = wrap_lines(source, font, 9.0, 200.0)
    assert len(wrapped) > 1
    assert tokenize(" ".join(w.text for w in wrapped)) == tokenize(source[0])


def test_wrap_lines_indents_continuations_under_the_bullet_text():
    font = fitz.Font(fontfile=settings.get_font_path())
    wrapped = wrap_lines(["- " + "dài " * 40], font, 9.0, 120.0)
    assert wrapped[0].indent == 0.0
    assert wrapped[1].indent > 0.0


def test_fit_plan_reports_overflow_instead_of_silently_clipping():
    font = fitz.Font(fontfile=settings.get_font_path())
    lines = [f"- dòng số {i} với khá nhiều chữ ở đây" for i in range(200)]
    size, wrapped, n_fit = fit_plan(lines, font, 300.0, 60.0, [9.0, 8.0, 7.0], 1.32)
    assert n_fit < len(wrapped)      # overflow detected, not hidden
    assert size == 7.0               # smallest size was tried first
