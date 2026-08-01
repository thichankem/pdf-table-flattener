"""Unit tests for the pieces the three acceptance criteria rest on."""

import fitz

from pdf_table_tool.formatter import (
    TableFormatter,
    _record_columns,
    detect_structure,
    normalise_sliced_cells,
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
    assert normalize_text("a​b‌c d") == "abc d"


def test_normalize_text_keeps_a_drawn_soft_hyphen_as_a_hyphen():
    """A PDF that draws U+00AD means a hyphen; deleting it would lose a glyph."""
    assert normalize_text("­3%") == "-3%"


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


# -------------------------------------------------------------- structure
def _line(text, x0, x1, top, bottom):
    return CellLine(text, x0=x0, x1=x1, top=top, bottom=bottom)


def _row_header_grid():
    """The layout from the LPBank fee table:

        | Điều kiện          | one sentence spanning both columns |
        | Tình huống         | Thỏa điều kiện | Không thỏa điều kiện |
        | Thứ tự phân bổ phí | Đóng cho A     | Đóng cho B           |
    """
    cells = [
        GridCell(0, 0, 1, 1, (0, 0, 100, 30), [_line("Điều kiện", 2, 60, 5, 15)]),
        GridCell(0, 1, 1, 2, (100, 0, 400, 30),
                 [_line("Khoản phí đóng vào có thể đủ để duy trì hiệu lực của Hợp "
                        "đồng bảo hiểm", 102, 398, 5, 15)]),
        GridCell(1, 0, 1, 1, (0, 30, 100, 50), [_line("Tình huống", 2, 62, 34, 44)]),
        GridCell(1, 1, 1, 1, (100, 30, 250, 50),
                 [_line("Thỏa điều kiện", 102, 190, 34, 44)]),
        GridCell(1, 2, 1, 1, (250, 30, 400, 50),
                 [_line("Không thỏa điều kiện", 252, 370, 34, 44)]),
        GridCell(2, 0, 1, 1, (0, 50, 100, 70),
                 [_line("Thứ tự phân bổ phí", 2, 90, 54, 64)]),
        GridCell(2, 1, 1, 1, (100, 50, 250, 70),
                 [_line("Đóng cho Phí bảo hiểm định kỳ", 102, 240, 54, 64)]),
        GridCell(2, 2, 1, 1, (250, 50, 400, 70),
                 [_line("Đóng cho Phí bảo hiểm cơ bản", 252, 390, 54, 64)]),
    ]
    return Grid(n_rows=3, n_cols=3, cells=cells, bbox=(0, 0, 400, 70))


def test_row_header_table_is_not_mistaken_for_a_column_header():
    """Row 0 merges the columns that row 1 keeps apart, so it cannot be a header."""
    structure = detect_structure(_row_header_grid())
    assert structure.header_rows == 0
    assert structure.label_column is True


def test_two_dimensional_table_is_pivoted_into_one_bullet_per_case():
    """Each data column is one case and carries every label down column 0."""
    lines, _ = TableFormatter().format_grid(_row_header_grid())
    assert len(lines) == 2
    assert lines[0] == (
        "- Điều kiện: Khoản phí đóng vào có thể đủ để duy trì hiệu lực của "
        "Hợp đồng bảo hiểm"
        "  |  Tình huống: Thỏa điều kiện"
        "  |  Thứ tự phân bổ phí: Đóng cho Phí bảo hiểm định kỳ"
    )
    assert lines[1] == (
        "- Điều kiện: Khoản phí đóng vào có thể đủ để duy trì hiệu lực của "
        "Hợp đồng bảo hiểm"
        "  |  Tình huống: Không thỏa điều kiện"
        "  |  Thứ tự phân bổ phí: Đóng cho Phí bảo hiểm cơ bản"
    )


def test_single_data_column_is_never_pivoted():
    """Pivoting needs at least two data columns; otherwise read row by row."""
    rows = [
        [
            GridCell(0, 0, 1, 1, (0, 0, 100, 20), [_line("Tên", 2, 30, 5, 15)]),
            GridCell(0, 1, 1, 1, (100, 0, 400, 20), [_line("Nguyễn Văn A", 102, 200, 5, 15)]),
        ],
        [
            GridCell(1, 0, 1, 1, (0, 20, 100, 40), [_line("Chức vụ", 2, 60, 25, 35)]),
            GridCell(1, 1, 1, 1, (100, 20, 400, 40), [_line("Chuyên viên", 102, 190, 25, 35)]),
        ],
    ]
    assert _record_columns(rows) == [1]


def test_vertically_merged_value_repeats_on_every_row_it_covers():
    """A cell merged down the side applies to each of those rows."""
    cells = [
        GridCell(0, 0, 1, 1, (0, 0, 100, 20), [_line("Năm", 2, 40, 5, 15)]),
        GridCell(0, 1, 1, 1, (100, 0, 250, 20), [_line("Cơ bản", 102, 160, 5, 15)]),
        GridCell(0, 2, 1, 1, (250, 0, 400, 20), [_line("Đóng thêm", 252, 330, 5, 15)]),
        GridCell(1, 0, 1, 1, (0, 20, 100, 40), [_line("1", 2, 12, 25, 35)]),
        GridCell(1, 1, 1, 1, (100, 20, 250, 40), [_line("50%", 102, 140, 25, 35)]),
        GridCell(1, 2, 3, 1, (250, 20, 400, 80), [_line("1,5%", 252, 300, 45, 55)]),
        GridCell(2, 0, 1, 1, (0, 40, 100, 60), [_line("2", 2, 12, 45, 55)]),
        GridCell(2, 1, 1, 1, (100, 40, 250, 60), [_line("30%", 102, 140, 45, 55)]),
        GridCell(3, 0, 1, 1, (0, 60, 100, 80), [_line("3", 2, 12, 65, 75)]),
        GridCell(3, 1, 1, 1, (100, 60, 250, 80), [_line("20%", 102, 140, 65, 75)]),
    ]
    grid = Grid(n_rows=4, n_cols=3, cells=cells, bbox=(0, 0, 400, 80))
    lines, _ = TableFormatter().format_grid(grid)
    assert lines == [
        "- Năm: 1  |  Cơ bản: 50%  |  Đóng thêm: 1,5%",
        "- Năm: 2  |  Cơ bản: 30%  |  Đóng thêm: 1,5%",
        "- Năm: 3  |  Cơ bản: 20%  |  Đóng thêm: 1,5%",
    ]


def test_paragraph_sliced_by_stray_rulings_is_rejoined():
    """Three stacked one-line cells in one column are one paragraph."""
    cells = [
        GridCell(0, 0, 3, 1, (0, 0, 80, 60), [_line("Điều kiện", 2, 50, 20, 30)]),
        GridCell(0, 1, 1, 1, (80, 0, 400, 20),
                 [_line("Khoản phí đóng vào có thể đủ để duy trì", 82, 398, 5, 15)]),
        GridCell(1, 1, 1, 1, (80, 20, 400, 40),
                 [_line("hiệu lực của Hợp đồng bảo hiểm đến hết", 82, 398, 25, 35)]),
        GridCell(2, 1, 1, 1, (80, 40, 400, 60),
                 [_line("ngày liền trước Ngày đến hạn.", 82, 250, 45, 55)]),
    ]
    grid = Grid(n_rows=3, n_cols=2, cells=cells, bbox=(0, 0, 400, 60))
    fused = normalise_sliced_cells(grid)
    assert len(fused.cells) == 2
    lines, _ = TableFormatter().format_grid(grid)
    assert len(lines) == 1
    assert lines[0].startswith("- Điều kiện")
    # The three slices read as one sentence again, in order.
    assert "duy trì hiệu lực của Hợp đồng bảo hiểm đến hết ngày liền trước" in lines[0]
    assert lines[0].endswith("Ngày đến hạn.")


def test_rowspan_group_keeps_its_separate_rows():
    """"Nhóm A" spanning three rows must not swallow them into one bullet."""
    cells = [
        GridCell(0, 0, 1, 1, (0, 0, 80, 20), [_line("Nhóm", 2, 40, 5, 15)]),
        GridCell(0, 1, 1, 1, (80, 0, 200, 20), [_line("Hạng", 82, 120, 5, 15)]),
        GridCell(0, 2, 1, 1, (200, 0, 400, 20), [_line("HMTC", 202, 250, 5, 15)]),
        GridCell(1, 0, 3, 1, (0, 20, 80, 80), [_line("Nhóm A", 2, 50, 40, 50)]),
        GridCell(1, 1, 1, 1, (80, 20, 200, 40), [_line("I", 82, 90, 25, 35)]),
        GridCell(1, 2, 1, 1, (200, 20, 400, 40), [_line("1.000", 202, 250, 25, 35)]),
        GridCell(2, 1, 1, 1, (80, 40, 200, 60), [_line("II", 82, 92, 45, 55)]),
        GridCell(2, 2, 1, 1, (200, 40, 400, 60), [_line("700", 202, 240, 45, 55)]),
        GridCell(3, 1, 1, 1, (80, 60, 200, 80), [_line("III", 82, 95, 65, 75)]),
        GridCell(3, 2, 1, 1, (200, 60, 400, 80), [_line("200", 202, 240, 65, 75)]),
    ]
    grid = Grid(n_rows=4, n_cols=3, cells=cells, bbox=(0, 0, 400, 80))
    assert len(normalise_sliced_cells(grid).cells) == len(cells)
    lines, _ = TableFormatter().format_grid(grid)
    assert len(lines) == 3
    assert "1.000" in lines[0] and "700" in lines[1] and "200" in lines[2]


def test_column_header_table_is_still_detected():
    grid = Grid(
        n_rows=2, n_cols=2,
        cells=[
            GridCell(0, 0, 1, 1, (0, 0, 100, 20), [_line("Khoản", 2, 40, 5, 15)]),
            GridCell(0, 1, 1, 1, (100, 0, 400, 20), [_line("Quy định", 102, 160, 5, 15)]),
            GridCell(1, 0, 1, 1, (0, 20, 100, 40), [_line("3.1", 2, 20, 25, 35)]),
            GridCell(1, 1, 1, 1, (100, 20, 400, 40), [_line("Nội dung", 102, 170, 25, 35)]),
        ],
        bbox=(0, 0, 400, 40),
    )
    structure = detect_structure(grid)
    assert structure.header_rows == 1
    lines, _ = TableFormatter().format_grid(grid)
    assert lines == ["- Khoản: 3.1  |  Quy định: Nội dung"]


def test_continuation_cell_at_top_of_page_is_not_a_header():
    """A cell carried over from the previous page fills one column, not a row."""
    cells = [
        GridCell(0, 0, 1, 1, (0, 0, 80, 20), []),
        GridCell(0, 1, 1, 1, (80, 0, 200, 20), []),
        GridCell(0, 2, 1, 1, (200, 0, 400, 20),
                 [_line("năm/lần ĐVKD thực hiện đánh giá lại hạn mức.", 202, 390, 5, 15)]),
        GridCell(1, 0, 1, 1, (0, 20, 80, 40), [_line("3.8", 2, 25, 25, 35)]),
        GridCell(1, 1, 1, 1, (80, 20, 200, 40), [_line("Giải ngân", 82, 140, 25, 35)]),
        GridCell(1, 2, 1, 1, (200, 20, 400, 40), [_line("Chuyển khoản", 202, 280, 25, 35)]),
        GridCell(2, 0, 1, 1, (0, 40, 80, 60), [_line("3.9", 2, 25, 45, 55)]),
        GridCell(2, 1, 1, 1, (80, 40, 200, 60), [_line("Trả nợ", 82, 130, 45, 55)]),
        GridCell(2, 2, 1, 1, (200, 40, 400, 60), [_line("Hàng tháng", 202, 270, 45, 55)]),
    ]
    grid = Grid(n_rows=3, n_cols=3, cells=cells, bbox=(0, 0, 400, 60))
    assert detect_structure(grid).header_rows == 0
    lines, _ = TableFormatter().format_grid(grid)
    # The carried-over sentence must not be glued in front of the real rows.
    assert sum("năm/lần" in line for line in lines) == 1
    assert lines[-1] == "- 3.9  |  Trả nợ  |  Hàng tháng"


def test_header_of_a_multi_part_cell_is_kept_on_the_caption_line():
    cells = [
        GridCell(0, 0, 1, 1, (0, 0, 80, 20), [_line("Khoản", 2, 45, 5, 15)]),
        GridCell(0, 1, 1, 1, (80, 0, 400, 20),
                 [_line("Nội dung chi tiết", 82, 190, 5, 15)]),
        GridCell(1, 0, 1, 1, (0, 20, 80, 60), [_line("3.1", 2, 25, 25, 35)]),
        GridCell(1, 1, 1, 1, (80, 20, 400, 60), [
            _line("- Điểm thứ nhất.", 82, 200, 25, 35),
            _line("- Điểm thứ hai.", 82, 195, 40, 50),
        ]),
    ]
    grid = Grid(n_rows=2, n_cols=2, cells=cells, bbox=(0, 0, 400, 60))
    lines, _ = TableFormatter().format_grid(grid)
    assert lines[0] == "- Khoản: 3.1  |  Nội dung chi tiết:"
    assert lines[1:] == ["  - Điểm thứ nhất.", "  - Điểm thứ hai."]
