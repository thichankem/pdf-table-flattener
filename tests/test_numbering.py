"""Hierarchical numbering: a table takes its place in the document's outline.

The point of it is chunking for retrieval, so the tests are about the two things
a chunker needs: a line must say which branch it belongs to, and that branch must
be the one the document itself would give it -- a table under "1. Thuật ngữ" is
1.1 and its rows 1.1.1, never a numbering of its own invention.
"""

import fitz
import pytest
from docx import Document
from docx.oxml import parse_xml
from openpyxl import Workbook

from pdf_table_tool.config import settings
from pdf_table_tool.docx_flattener import DocxTableFlattener
from pdf_table_tool.docx_numbering import ListNumbering
from pdf_table_tool.outline import (
    CONTINUED_MARK,
    DocumentOutline,
    TableNumber,
    continues_outline,
    is_contents_line,
    number_table_lines,
    parse_heading,
)
from pdf_table_tool.pipeline import PDFTableFlattenerPipeline
from pdf_table_tool.xlsx_flattener import XlsxTableFlattener


# ------------------------------------------------------------ reading headings
@pytest.mark.parametrize(
    "line, expected",
    [
        ("1. THUẬT NGỮ VÀ ĐỊNH NGHĨA", (1,)),
        ("1.1. Bác sĩ: là người có bằng cấp chuyên môn", (1, 1)),
        ("2.3.2.Điều khoản cung cấp thông tin", (2, 3, 2)),  # no blank after the dot
        ("1.27 Thương tật toàn bộ và vĩnh viễn", (1, 27)),
        ("3) Quyền lợi bảo hiểm", (3,)),
        ("ĐIỀU 5: QUYỀN LỢI BẢO HIỂM", (5,)),
        ("ĐIỀU5:QUYỀN LỢI", (5,)),  # letter-spaced heading, blanks lost
    ],
)
def test_a_numbered_heading_is_read(line, expected):
    assert parse_heading(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "1.000.000 đồng phí bảo hiểm",  # a sum of money, not section 1.000.000
        "3 Bản sao là bản sao y chứng thực",  # a footnote: no punctuation
        "3.5% của Số tiền bảo hiểm",
        "theo quy định tại Điều 5 của Hợp đồng",  # a cross-reference, mid-sentence
        "Điều 8.2 quy định về tạm ứng",  # a reference to a clause, not article 8
        "4/23",  # a page number
        "",
    ],
)
def test_prose_is_not_read_as_a_heading(line):
    assert parse_heading(line) is None


def test_a_contents_entry_is_recognised_by_its_leader_dots():
    assert is_contents_line("2.1. Quyền lợi ....................... 7")
    assert not is_contents_line("2.1. Quyền lợi có thể được bảo hiểm")


def test_an_outline_carries_on_by_one_step():
    assert continues_outline((1, 12), (1, 13))
    assert continues_outline((1, 28), (2,))
    assert continues_outline((2,), (2, 1))
    assert not continues_outline((1, 28), (2, 1))
    assert not continues_outline((1, 12), (1, 20))


# --------------------------------------------------------- allocating a number
def test_a_table_is_numbered_under_the_heading_above_it():
    outline = DocumentOutline()
    outline.enter((1,))
    assert outline.next_table().label == "1.1"
    assert outline.next_table().label == "1.2"


def test_a_table_never_takes_a_number_a_heading_owns():
    """The document has its own 1.1 and 1.2 further down; the table gets 1.3."""
    outline = DocumentOutline()
    outline.load([], known=[(1,), (1, 1), (1, 2)])
    outline.enter((1,))
    assert outline.next_table().label == "1.3"


def test_a_document_without_headings_numbers_its_tables_in_order():
    outline = DocumentOutline()
    assert outline.next_table().label == "1"
    assert outline.next_table().label == "2"


def test_a_deeper_heading_takes_the_table_deeper_with_it():
    outline = DocumentOutline()
    outline.enter((2,))
    outline.enter((2, 3))
    outline.enter((2, 3, 1))
    assert outline.next_table().label == "2.3.1.1"


def test_a_heading_with_no_number_of_its_own_is_counted():
    """Word draws the number of a Heading style, so it is nowhere in the text."""
    outline = DocumentOutline()
    assert outline.enter_level(0) == (1,)
    assert outline.enter_level(1) == (1, 1)
    assert outline.enter_level(1) == (1, 2)
    assert outline.enter_level(0) == (2,)


# ------------------------------------------------------------ numbering lines
def test_rows_are_numbered_under_the_table_and_sub_bullets_under_their_row():
    lines = [
        "- Thuật ngữ: Bên mua bảo hiểm  |  Định nghĩa: Tổ chức, cá nhân",
        "- Thuật ngữ: Người được bảo hiểm  |  Định nghĩa:",
        "  - Là người được nhận quyền lợi",
        "  - Phải cư trú tại Việt Nam",
    ]
    out = number_table_lines(
        lines, TableNumber(path=(1, 1)), headers=["Thuật ngữ", "Định nghĩa"]
    )

    assert out == [
        "1.1 Thuật ngữ  |  Định nghĩa",
        "  1.1.1 Thuật ngữ: Bên mua bảo hiểm  |  Định nghĩa: Tổ chức, cá nhân",
        "  1.1.2 Thuật ngữ: Người được bảo hiểm  |  Định nghĩa:",
        "    1.1.2.1 Là người được nhận quyền lợi",
        "    1.1.2.2 Phải cư trú tại Việt Nam",
    ]


def test_a_table_without_headers_gets_no_caption_line():
    out = number_table_lines(["- Nam  |  25", "- Lan  |  30"], TableNumber(path=(1,)))
    assert out == ["1.1 Nam  |  25", "1.2 Lan  |  30"]


def test_a_repeated_header_is_named_once_in_the_caption():
    out = number_table_lines(
        ["- Năm: 1  |  Tỷ lệ: 50%  |  Tỷ lệ: 1,5%"],
        TableNumber(path=(3,)),
        headers=["Năm", "Tỷ lệ", "Tỷ lệ"],
    )
    assert out[0] == "3 Năm  |  Tỷ lệ"


def test_a_continued_table_carries_on_where_it_stopped():
    number = TableNumber(path=(2, 1))
    first = number_table_lines(["- a", "- b"], number, headers=["H"])
    second = number_table_lines(["- c"], number, headers=["H"], continued=True)

    assert first[-1].strip().startswith("2.1.2 ")
    assert second[0] == f"2.1 H {CONTINUED_MARK}"
    assert second[-1].strip().startswith("2.1.3 ")


def test_a_line_too_deep_to_number_keeps_its_glyph():
    lines = ["- a", "  - b", "    + c", "      - d", "        - e"]
    out = number_table_lines(lines, TableNumber(path=(1, 2, 3)))

    assert out[2].strip().startswith("1.2.3.1.1.1 ")  # six components, the limit
    assert out[3].strip() == "- d"
    assert out[4].strip() == "- e"
    # Indentation still tells the reader where the line belongs.
    assert out[4].startswith(" " * 8)


def test_no_word_of_a_line_is_changed_by_numbering():
    lines = ["- Khoản: 3.8  |  Quy định: Giải ngân", "  + Chuyển khoản"]
    out = number_table_lines(lines, TableNumber(path=(4,)), headers=["Khoản"])

    for source, numbered in zip(lines, out[1:]):
        assert source.strip().lstrip("-+* ") in numbered


# ------------------------------------------------ the numbers Word draws itself
_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

_NUMBERING_XML = f"""<w:numbering {_W}>
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/></w:lvl>
    <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2">
    <w:abstractNumId w:val="0"/>
    <w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>
  </w:num>
  <w:num w:numId="3"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""


def _numbered_paragraph(num_id, ilvl=0):
    return parse_xml(
        f'<w:p {_W}><w:pPr><w:numPr>'
        f'<w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/>'
        f"</w:numPr></w:pPr></w:p>"
    )


def _lists():
    return ListNumbering(parse_xml(_NUMBERING_XML))


def test_word_list_counters_are_replayed():
    numbering = _lists()
    seen = [numbering.advance(_numbered_paragraph(1)) for _ in range(3)]
    assert seen == [(1,), (2,), (3,)]


def test_a_deeper_level_restarts_under_each_parent():
    numbering = _lists()
    numbering.advance(_numbered_paragraph(1))
    assert numbering.advance(_numbered_paragraph(1, ilvl=1)) == (1, 1)
    assert numbering.advance(_numbered_paragraph(1, ilvl=1)) == (1, 2)
    assert numbering.advance(_numbered_paragraph(1)) == (2,)
    assert numbering.advance(_numbered_paragraph(1, ilvl=1)) == (2, 1)


def test_a_bulleted_list_names_no_section():
    assert _lists().advance(_numbered_paragraph(3)) is None


def test_a_restarted_list_starts_from_one_again():
    """An appendix that numbers itself 1., 2., 3. again is a new `w:num`."""
    numbering = _lists()
    for _ in range(4):
        numbering.advance(_numbered_paragraph(1))
    assert numbering.advance(_numbered_paragraph(2)) == (1,)


def test_an_unnumbered_paragraph_is_not_counted():
    assert _lists().advance(parse_xml(f"<w:p {_W}/>")) is None


# -------------------------------------------------------------- the Word path
def _docx_with(tmp_path, build, numbering=True):
    doc = Document()
    build(doc)
    src = tmp_path / "src.docx"
    out = tmp_path / "out.docx"
    doc.save(src)
    DocxTableFlattener(verify_output=False, numbering=numbering).process(
        str(src), str(out)
    )
    return [p.text for p in Document(str(out)).paragraphs if p.text.strip()]


def _grid_table(doc, rows):
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.cell(r, c).text = text
    return table


def test_word_table_is_numbered_under_the_numbered_paragraph_above_it(tmp_path):
    def build(doc):
        doc.add_paragraph("1. Thuật ngữ")
        _grid_table(doc, [["Tên", "Tuổi"], ["Nam", "25"], ["Lan", "30"]])

    texts = _docx_with(tmp_path, build)

    assert texts == [
        "1. Thuật ngữ",
        "1.1 Tên  |  Tuổi",
        "1.1.1 Tên: Nam  |  Tuổi: 25",
        "1.1.2 Tên: Lan  |  Tuổi: 30",
    ]


def test_the_number_word_draws_decides_where_the_table_sits(tmp_path):
    """The section number is nowhere in the text -- Word paints it from a list.

    This is the common shape of an official document: the author ticked
    "numbered list", so the paragraph that reads "2. Chính sách ưu đãi" on
    screen reaches us as "Chính sách ưu đãi".
    """
    def build(doc):
        doc.add_paragraph("Đối tượng áp dụng", style="List Number")
        doc.add_paragraph("Chính sách ưu đãi", style="List Number")
        _grid_table(doc, [["Hạng", "Ưu đãi"], ["Gold", "0,10"]])

    texts = _docx_with(tmp_path, build)

    assert texts[-2:] == ["2.1 Hạng  |  Ưu đãi", "2.1.1 Hạng: Gold  |  Ưu đãi: 0,10"]


def test_a_numbered_paragraph_inside_a_table_still_counts(tmp_path):
    """Word counts it, so the section after the table must not be one short."""
    def build(doc):
        doc.add_paragraph("Mục một", style="List Number")
        table = doc.add_table(rows=1, cols=1)
        table.style = "Table Grid"
        table.cell(0, 0).paragraphs[0].text = "Mục hai nằm trong bảng"
        table.cell(0, 0).paragraphs[0].style = "List Number"
        doc.add_paragraph("Mục ba", style="List Number")
        _grid_table(doc, [["Hạng", "Ưu đãi"], ["Gold", "0,10"]])

    texts = _docx_with(tmp_path, build)

    assert any(t.startswith("3.1 Hạng") for t in texts), texts


def test_word_heading_styles_number_themselves(tmp_path):
    def build(doc):
        doc.add_heading("Quy định chung", level=1)
        doc.add_heading("Biểu phí", level=2)
        _grid_table(doc, [["Tuổi", "Phí"], ["30", "1.000"]])

    texts = _docx_with(tmp_path, build)

    assert texts[-2:] == ["1.1.1 Tuổi  |  Phí", "1.1.1.1 Tuổi: 30  |  Phí: 1.000"]


def test_a_second_table_in_the_same_section_gets_the_next_number(tmp_path):
    def build(doc):
        doc.add_paragraph("2. Quyền lợi")
        _grid_table(doc, [["A", "B"], ["1", "2"]])
        doc.add_paragraph("Đoạn văn giữa hai bảng.")
        _grid_table(doc, [["C", "D"], ["3", "4"]])

    texts = _docx_with(tmp_path, build)

    assert "2.1 A  |  B" in texts
    assert "2.2 C  |  D" in texts


def test_numbering_loses_nothing_of_a_word_document(tmp_path):
    """Numbering only ever puts a number in front of a line."""
    doc = Document()
    doc.add_paragraph("1. Thuật ngữ")
    _grid_table(doc, [["Khoản", "Quy định"], ["3.8", "Giải ngân"]])
    doc.add_paragraph("Đoạn văn giữa hai bảng.")
    _grid_table(doc, [["Mã", "Tên"], ["A1", "Bút bi"]])
    src = tmp_path / "src.docx"
    out = tmp_path / "out.docx"
    doc.save(src)

    summary = DocxTableFlattener().process(str(src), str(out))

    assert summary["total_tables_flattened"] == 2
    assert summary["verification"].passed, summary["verification"].describe()


def test_turning_numbering_off_restores_the_plain_bullets(tmp_path):
    def build(doc):
        doc.add_paragraph("1. Thuật ngữ")
        _grid_table(doc, [["Tên", "Tuổi"], ["Nam", "25"]])

    assert _docx_with(tmp_path, build, numbering=False) == [
        "1. Thuật ngữ",
        "- Tên: Nam  |  Tuổi: 25",
    ]


def test_a_nested_table_stays_part_of_its_parent_row(tmp_path):
    """A sub-table is content of a cell, not a section of the document."""
    def build(doc):
        doc.add_paragraph("1. Hạn mức")
        table = _grid_table(doc, [["Điều kiện", "Nội dung"], ["Hạn mức", ""]])
        nested = table.cell(1, 1).add_table(rows=2, cols=2)
        nested.style = "Table Grid"
        for r, row in enumerate([["Chức danh", "HMTC"], ["Giám đốc", "500"]]):
            for c, text in enumerate(row):
                nested.cell(r, c).text = text

    texts = _docx_with(tmp_path, build)

    assert texts[1].startswith("1.1 ")
    assert any("Chức danh: Giám đốc  |  HMTC: 500" in t for t in texts)
    # The sub-table did not take a number of its own from the outline.
    assert not any(t.startswith("1.2 ") for t in texts)


# ------------------------------------------------------------- the Excel path
def _xlsx_paragraphs(tmp_path, build, numbering=True):
    workbook = Workbook()
    build(workbook)
    src = tmp_path / "book.xlsx"
    out = tmp_path / "book.docx"
    workbook.save(src)
    XlsxTableFlattener(verify_output=False, numbering=numbering).process(
        str(src), str(out)
    )
    return [p.text for p in Document(str(out)).paragraphs if p.text.strip()]


def test_each_sheet_of_a_workbook_becomes_a_numbered_section(tmp_path):
    def build(workbook):
        first = workbook.active
        first.title = "Một"
        first.append(["Tên", "Tuổi"])
        first.append(["Nam", 25])
        second = workbook.create_sheet("Hai")
        second.append(["Mã", "Giá"])
        second.append(["X1", 10])

    assert _xlsx_paragraphs(tmp_path, build) == [
        "1. Một",
        "1.1 Tên  |  Tuổi",
        "1.1.1 Tên: Nam  |  Tuổi: 25",
        "2. Hai",
        "2.1 Mã  |  Giá",
        "2.1.1 Mã: X1  |  Giá: 10",
    ]


def test_a_single_sheet_numbers_its_tables_from_the_top(tmp_path):
    def build(workbook):
        sheet = workbook.active
        sheet.append(["Tên", "Tuổi"])
        sheet.append(["Nam", 25])
        sheet.append([])
        sheet.append(["Mã", "Giá"])
        sheet.append(["X1", 10])

    assert _xlsx_paragraphs(tmp_path, build) == [
        "1 Tên  |  Tuổi",
        "1.1 Tên: Nam  |  Tuổi: 25",
        "2 Mã  |  Giá",
        "2.1 Mã: X1  |  Giá: 10",
    ]


# --------------------------------------------------------------- the PDF path
def _write(page, items, size=10):
    font = fitz.Font(fontfile=settings.get_font_path())
    writer = fitz.TextWriter(page.rect)
    for x, y, text in items:
        writer.append(fitz.Point(x, y), text, font=font, fontsize=size)
    writer.write_text(page)


def _grid(page, x0, y0, col_w, row_h, ncols, nrows):
    for r in range(nrows + 1):
        page.draw_line(
            fitz.Point(x0, y0 + r * row_h),
            fitz.Point(x0 + ncols * col_w, y0 + r * row_h),
            width=0.6,
        )
    for c in range(ncols + 1):
        page.draw_line(
            fitz.Point(x0 + c * col_w, y0),
            fitz.Point(x0 + c * col_w, y0 + nrows * row_h),
            width=0.6,
        )


def test_a_pdf_table_is_numbered_under_the_heading_printed_above_it(tmp_path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "out.pdf"
    doc = fitz.open()
    page = doc.new_page()
    _write(page, [(60, 70, "2. Quy dinh chung")])
    _write(page, [(60, 92, "2.1. Bieu phi bao hiem")])
    rows = [["Tuoi", "Phi"], ["30", "1.000"], ["40", "2.000"]]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            _write(page, [(70 + c * 150, 130 + r * 25, text)])
    _grid(page, 60, 110, 150, 25, 2, 3)
    doc.save(src)
    doc.close()

    summary = PDFTableFlattenerPipeline().process(str(src), str(out))
    assert summary["verification"].passed, summary["verification"].describe()

    with fitz.open(out) as flat:
        text = flat[0].get_text()

    assert "2.1.1 Tuoi  |  Phi" in text
    assert "2.1.1.1 Tuoi: 30  |  Phi: 1.000" in text
    assert "2.1.1.2 Tuoi: 40  |  Phi: 2.000" in text
    # The document's own headings are passthrough content and stay as they were.
    assert "2. Quy dinh chung" in text
    assert "2.1. Bieu phi bao hiem" in text
