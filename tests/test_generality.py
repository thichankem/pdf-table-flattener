"""Guards against the tool being tuned to one family of documents.

Each case is a structurally different PDF built from scratch: English prose,
whitespace-aligned tables, rotated pages, landscape, sparse grids, and pages
with no tables at all.  They exist so that a change which helps the sample
corpus but breaks everything else fails here.
"""

import fitz
import pdfplumber

from pdf_table_tool.borderless import find_borderless_tables
from pdf_table_tool.config import settings
from pdf_table_tool.pipeline import PDFTableFlattenerPipeline
from pdf_table_tool.table_detector import TABLE_SETTINGS_LINES
from pdf_table_tool.text_utils import tokenize


def _write(page, items, size=10):
    font = fitz.Font(fontfile=settings.get_font_path())
    tw = fitz.TextWriter(page.rect)
    for x, y, text in items:
        tw.append(fitz.Point(x, y), text, font=font, fontsize=size)
    tw.write_text(page)


def _grid(page, x0, y0, col_w, row_h, ncols, nrows):
    for r in range(nrows + 1):
        page.draw_line(fitz.Point(x0, y0 + r * row_h),
                       fitz.Point(x0 + ncols * col_w, y0 + r * row_h), width=0.6)
    for c in range(ncols + 1):
        page.draw_line(fitz.Point(x0 + c * col_w, y0),
                       fitz.Point(x0 + c * col_w, y0 + nrows * row_h), width=0.6)


def _run(tmp_path, name, build):
    src = tmp_path / (name + ".pdf")
    out = tmp_path / (name + "_flat.pdf")
    doc = fitz.open()
    build(doc)
    doc.save(src)
    doc.close()
    summary = PDFTableFlattenerPipeline().process(str(src), str(out))
    return src, out, summary


def _page_text(path, index=0):
    """Extracted page text with the nbsp our fixtures emit folded to a space."""
    with fitz.open(path) as doc:
        return doc[index].get_text().replace(" ", " ")


def _assert_all_criteria(summary):
    report = summary["verification"]
    assert report.passed, report.describe()


# ---------------------------------------------------------------- languages
def test_english_document_flattens_correctly(tmp_path):
    def build(doc):
        p = doc.new_page()
        _write(p, [(60, 70, "Quarterly report. This paragraph must survive untouched.")])
        rows = [["Region", "Revenue", "Growth"], ["North", "1,200", "12%"],
                ["South", "980", "-3%"], ["East", "1,450", "21%"]]
        for r, row in enumerate(rows):
            for c, t in enumerate(row):
                _write(p, [(70 + c * 150, 115 + r * 25, t)])
        _grid(p, 60, 95, 150, 25, 3, 4)
        _write(p, [(60, 240, "Footer prose below the table.")])

    _src, out, summary = _run(tmp_path, "english", build)
    _assert_all_criteria(summary)
    text = _page_text(out)
    assert "Quarterly report." in text
    assert "Footer prose below the table." in text
    assert "- Region: North  |  Revenue: 1,200  |  Growth: 12%" in text
    assert "Growth: -3%" in text


# --------------------------------------------------------------- borderless
def test_whitespace_aligned_table_is_found_and_flattened(tmp_path):
    def build(doc):
        p = doc.new_page()
        _write(p, [(60, 70, "Caption line above the table:")])
        for r, row in enumerate([["Ma", "Ten", "So luong"], ["A1", "But bi", "10"],
                                 ["A2", "Vo ghi", "25"], ["A3", "Thuoc ke", "7"]]):
            for c, t in enumerate(row):
                _write(p, [(70 + c * 140, 100 + r * 20, t)])
        _write(p, [(60, 200, "Prose after the table.")])

    _src, out, summary = _run(tmp_path, "borderless", build)
    _assert_all_criteria(summary)
    assert summary["total_tables_flattened"] == 1
    text = _page_text(out)
    assert "- Ma: A1  |  Ten: But bi  |  So luong: 10" in text
    # The caption is not part of the table and must be left as prose.
    assert "Caption line above the table:" in text
    assert "- Caption line" not in text


def test_prose_is_never_mistaken_for_a_borderless_table(tmp_path):
    src = tmp_path / "prose.pdf"
    doc = fitz.open()
    p = doc.new_page()
    _write(p, [(60, 70 + i * 18,
                "Day la mot doan van binh thuong, dai va lien tuc, dong so %d." % i)
               for i in range(24)])
    doc.save(src)
    doc.close()
    with pdfplumber.open(src) as pdf:
        assert find_borderless_tables(pdf.pages[0]) == []


def test_table_of_contents_is_not_flattened(tmp_path):
    """Leader dots give a contents list a table-like shape; it is not a table."""
    src = tmp_path / "toc.pdf"
    doc = fitz.open()
    p = doc.new_page()
    for i in range(12):
        _write(p, [(60, 80 + i * 20, "%d. Muc luc phan %d %s %d"
                    % (i + 1, i + 1, "." * 40, 10 + i))])
    doc.save(src)
    doc.close()
    with pdfplumber.open(src) as pdf:
        assert find_borderless_tables(pdf.pages[0]) == []


def test_bulleted_list_is_not_flattened(tmp_path):
    """A list has a gutter after its glyph but is not a table."""
    src = tmp_path / "list.pdf"
    doc = fitz.open()
    p = doc.new_page()
    for i in range(8):
        _write(p, [(60, 80 + i * 20, "-"),
                   (80, 80 + i * 20, "Muc thu %d trong danh sach" % i)])
    doc.save(src)
    doc.close()
    with pdfplumber.open(src) as pdf:
        assert find_borderless_tables(pdf.pages[0]) == []


# ------------------------------------------------------------ page geometry
def test_landscape_page(tmp_path):
    def build(doc):
        p = doc.new_page(width=842, height=595)
        _write(p, [(60, 60, "Landscape page.")])
        for r, row in enumerate([["C1", "C2", "C3"], ["a", "b", "c"]]):
            for c, t in enumerate(row):
                _write(p, [(70 + c * 145, 100 + r * 25, t)])
        _grid(p, 60, 80, 145, 25, 3, 2)

    _src, _out, summary = _run(tmp_path, "landscape", build)
    _assert_all_criteria(summary)
    assert summary["total_tables_flattened"] == 1


def test_rotated_page(tmp_path):
    """pdfplumber reports rotated coordinates, PyMuPDF edits unrotated ones."""
    def build(doc):
        p = doc.new_page()
        _write(p, [(60, 70, "Rotated page.")])
        for r, row in enumerate([["Col A", "Col B"], ["1", "2"]]):
            for c, t in enumerate(row):
                _write(p, [(70 + c * 160, 105 + r * 25, t)])
        _grid(p, 60, 90, 160, 25, 2, 2)
        p.set_rotation(90)

    _src, out, summary = _run(tmp_path, "rotated", build)
    _assert_all_criteria(summary)
    with fitz.open(out) as doc:
        assert doc[0].rotation == 90, "page rotation must be preserved"
    with pdfplumber.open(out) as pdf:
        for table in pdf.pages[0].find_tables(TABLE_SETTINGS_LINES):
            assert (table.bbox[2] - table.bbox[0]) <= 20 or (
                table.bbox[3] - table.bbox[1]) <= 15


def test_document_without_tables_is_untouched(tmp_path):
    def build(doc):
        p = doc.new_page()
        _write(p, [(60, 70 + i * 18, "Dong van ban thu %d." % i) for i in range(20)])

    src, out, summary = _run(tmp_path, "notables", build)
    _assert_all_criteria(summary)
    assert summary["total_tables_flattened"] == 0
    with fitz.open(src) as a, fitz.open(out) as b:
        assert a[0].get_text() == b[0].get_text()


def test_two_tables_side_by_side(tmp_path):
    def build(doc):
        p = doc.new_page()
        for bx in (60, 320):
            for r, row in enumerate([["H1", "H2"], ["x", "y"], ["z", "w"]]):
                for c, t in enumerate(row):
                    _write(p, [(bx + 10 + c * 100, 105 + r * 25, t)])
            _grid(p, bx, 90, 100, 25, 2, 3)

    _src, _out, summary = _run(tmp_path, "sidebyside", build)
    _assert_all_criteria(summary)
    assert summary["total_tables_flattened"] == 2


def test_image_inside_a_cell_does_not_break_the_page(tmp_path):
    def build(doc):
        p = doc.new_page()
        _write(p, [(60, 70, "Table with an image in a cell.")])
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40))
        pix.set_rect(pix.irect, (200, 30, 30))
        _write(p, [(70, 105, "Anh"), (220, 105, "Mo ta"), (220, 145, "Hinh vuong")])
        p.insert_image(fitz.Rect(70, 120, 105, 155), pixmap=pix)
        _grid(p, 60, 90, 150, 40, 2, 2)

    _src, _out, summary = _run(tmp_path, "imagecell", build)
    _assert_all_criteria(summary)


def test_many_columns(tmp_path):
    def build(doc):
        p = doc.new_page()
        for r in range(4):
            for c in range(9):
                _write(p, [(64 + c * 55, 105 + r * 22,
                            ("H%d" % c) if r == 0 else "%d" % (r * 9 + c))], size=7)
        _grid(p, 60, 90, 55, 22, 9, 4)

    _src, out, summary = _run(tmp_path, "widetable", build)
    _assert_all_criteria(summary)
    assert "H0: 9" in _page_text(out)


def test_sparse_table_keeps_every_value(tmp_path):
    def build(doc):
        p = doc.new_page()
        _write(p, [(70, 105, "A"), (370, 155, "B")])
        _grid(p, 60, 90, 150, 25, 3, 4)

    src, out, summary = _run(tmp_path, "sparse", build)
    _assert_all_criteria(summary)
    with fitz.open(src) as a, fitz.open(out) as b:
        assert set(tokenize("".join(p.get_text() for p in a))) <= set(
            tokenize("".join(p.get_text() for p in b))
        )
