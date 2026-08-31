"""Defects that only some PDF producers -- and one PDF library -- put in our way.

Each case here cost a page of a real document, and none of them is visible in
the text a reader sees: an invisible rectangle, a font-position code point, a
content stream MuPDF rewrote incorrectly.  They are grouped together because
they share a shape -- the input looks fine, and the output is wrong.
"""

import fitz
import pdfplumber
import pytest

from pdf_table_tool.config import settings
from pdf_table_tool.pdf_patcher import (
    PDFPatcher,
    _text_rows,
    _undo_doubled_line_moves,
)
from pdf_table_tool.pipeline import PDFTableFlattenerPipeline
from pdf_table_tool.table_detector import _draws_nothing, _is_white, detect_tables_by_page
from pdf_table_tool.text_utils import PUA_RE, normalize_text


def _write(page, items, size=10):
    font = fitz.Font(fontfile=settings.get_font_path())
    writer = fitz.TextWriter(page.rect)
    for x, y, text in items:
        writer.append(fitz.Point(x, y), text, font=font, fontsize=size)
    writer.write_text(page)


# ------------------------------------------- rectangles nobody can see
def test_white_and_unstroked_rectangles_are_not_rulings():
    invisible = {
        "object_type": "rect", "stroke": False, "fill": True,
        "non_stroking_color": (1.0, 1.0, 1.0),
    }
    assert _draws_nothing(invisible)
    assert _draws_nothing(dict(invisible, non_stroking_color=1.0))     # gray
    assert _draws_nothing(dict(invisible, non_stroking_color=(0,) * 4))  # cmyk
    assert _draws_nothing(dict(invisible, fill=False))                 # nothing drawn

    assert not _draws_nothing(dict(invisible, stroke=True))
    assert not _draws_nothing(dict(invisible, non_stroking_color=(1.0, 0.75, 0.0)))
    assert not _draws_nothing(dict(invisible, object_type="line"))


def test_is_white_ignores_a_colour_it_cannot_read():
    assert not _is_white(None)
    assert not _is_white("white")


def test_a_paragraph_on_a_white_background_is_not_a_table(tmp_path):
    """Some producers lay a white box behind every paragraph.

    pdfplumber reads the edges of a rectangle as rulings whether or not it is
    ever drawn, so such a page arrives as a stack of one-row tables -- and the
    flattener would rewrite ordinary prose as bullets.
    """
    src = tmp_path / "backgrounds.pdf"
    doc = fitz.open()
    page = doc.new_page()
    prose = [
        "Trong Quy dinh nay, cac tu ngu duoi day duoc hieu nhu sau:",
        "1. Ngan hang: la Ngan hang Loc Phat Viet Nam.",
        "2. Don vi kinh doanh: la cac Chi nhanh va Phong Giao dich.",
        "3. Ngoai te: la dong tien cua quoc gia hoac vung lanh tho khac.",
    ]
    for i, line in enumerate(prose):
        top = 90 + i * 40
        page.draw_rect(
            fitz.Rect(60, top, 540, top + 40), color=None, fill=(1, 1, 1)
        )
        _write(page, [(64, top + 25, line)])
    doc.save(src)
    doc.close()

    with_tables, without = detect_tables_by_page(str(src))
    assert not with_tables
    assert without == {0}


def test_a_drawn_grid_is_still_found(tmp_path):
    """The counterpart: filtering invisible boxes must not blind the detector."""
    src = tmp_path / "ruled.pdf"
    doc = fitz.open()
    page = doc.new_page()
    for r in range(4):
        for c in range(2):
            _write(page, [(70 + c * 150, 105 + r * 25, "R%dC%d" % (r, c))])
    for r in range(5):
        page.draw_line(fitz.Point(60, 90 + r * 25), fitz.Point(360, 90 + r * 25),
                       width=0.6)
    for c in range(3):
        page.draw_line(fitz.Point(60 + c * 150, 90), fitz.Point(60 + c * 150, 190),
                       width=0.6)
    doc.save(src)
    doc.close()

    with_tables, _without = detect_tables_by_page(str(src))
    assert list(with_tables) == [0]


# ------------------------------------------- symbol fonts and missing glyphs
def test_a_wingdings_list_marker_becomes_a_bullet():
    """Word stores a Wingdings tick as its position in the font, U+F0FC.

    No text font has a glyph there, so drawing it yields .notdef -- a blank box
    that reads back as U+0000 and fails criterion 3.  NORM §1.3 resolves the
    private use area; a glyph opening a line is the marker of a list item and is
    written as the dash the spec asks for.
    """
    tick, dot = chr(0xF0FC), chr(0xF0B7)
    assert normalize_text(tick + " DVKD kiem tra ho so") == "- DVKD kiem tra ho so"
    assert normalize_text(dot + " muc dau tien") == "- muc dau tien"
    assert normalize_text(chr(0xE000) + " abc") == "- abc"


def test_a_symbol_glyph_inside_a_sentence_is_read_by_its_position():
    """NORM §1.3: U+F020-U+F07E keeps the ASCII position of what it replaced.

    Punctuation and digits are read back from it; a letter position is not --
    there sits the Greek alphabet or an ornament, and spelling one out in Latin
    would put a word in the document that nobody wrote.
    """
    assert normalize_text("gia tri" + chr(0xF03D) + "100") == "gia tri=100"   # "="
    assert normalize_text("a" + chr(0xF061) + "b") == "a b"                   # "a"
    assert normalize_text("buoc" + chr(0xF0D8) + "buoc") == "buoc->buoc"      # arrow
    # Nothing may be left behind in the private use area (checklist §8.1).
    assert not PUA_RE.search(normalize_text("x" + chr(0xF8FF) + "y"))


def test_the_renderer_never_draws_a_glyph_the_font_does_not_have():
    patcher = PDFPatcher()
    font = fitz.Font(fontfile=settings.get_font_path())
    assert patcher._drawable("Hạn mức 15.000 USD", font, "x.ttf") == (
        "Hạn mức 15.000 USD"
    )
    # No font carries the private use area, so nothing here can be drawn.
    assert patcher._drawable("a" + chr(0xE000) + "b", font, "x.ttf") == "a.b"


def test_a_symbol_marker_survives_the_whole_pipeline_as_a_bullet(tmp_path):
    src = tmp_path / "wingdings.pdf"
    out = tmp_path / "wingdings_flat.pdf"
    doc = fitz.open()
    page = doc.new_page()
    rows = [["Buoc", "Noi dung"],
            ["1", chr(0xF0FC) + " Kiem tra ho so"],
            ["2", chr(0xF0FC) + " Phe duyet giao dich"]]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            _write(page, [(70 + c * 120, 105 + r * 25, text)])
    for r in range(4):
        page.draw_line(fitz.Point(60, 90 + r * 25), fitz.Point(300, 90 + r * 25),
                       width=0.6)
    for c in range(3):
        page.draw_line(fitz.Point(60 + c * 120, 90), fitz.Point(60 + c * 120, 165),
                       width=0.6)
    doc.save(src)
    doc.close()

    summary = PDFTableFlattenerPipeline(numbering=False).process(str(src), str(out))
    assert summary["verification"].passed, summary["verification"].describe()
    with fitz.open(out) as result:
        text = result[0].get_text()
    assert "\x00" not in text
    assert "Kiem tra ho so" in text


# ------------------------------------------- MuPDF's doubled line moves
def test_a_td_followed_by_tstar_is_rewritten_as_a_plain_td():
    """`TD` sets the leading to -ty, so the `T*` after it moves the line twice."""
    stream, fixed = _undo_doubled_line_moves(b"BT 40 -200 TD T* (Hi)Tj ET")
    assert fixed == 1
    assert stream == b"BT 40 -200 Td    (Hi)Tj ET"
    assert len(stream) == len(b"BT 40 -200 TD T* (Hi)Tj ET")


def test_the_line_move_repair_leaves_a_correct_stream_alone():
    for stream in (b"BT 40 -200 Td (Hi)Tj ET", b"BT 40 -200 TD (Hi)Tj ET"):
        assert _undo_doubled_line_moves(stream) == (stream, 0)


def test_the_line_move_repair_never_edits_a_string_a_page_draws():
    stream = b"BT 10 20 Td (see TD T* below)Tj (a\\)TD T*)Tj ET"
    assert _undo_doubled_line_moves(stream) == (stream, 0)


def test_a_name_ending_in_td_is_not_an_operator():
    stream = b"BT /F1TD T* 12 Tf ET"
    assert _undo_doubled_line_moves(stream) == (stream, 0)


def test_redaction_leaves_every_line_of_a_page_where_it_was(tmp_path):
    """The end-to-end invariant the repair exists to keep.

    Redaction deletes text; it must never move any.  When MuPDF rewrites the
    page wrongly the table lands somewhere other than the rectangle measured for
    it, so the tool erases whichever prose drifted in and leaves the table.
    """
    src = tmp_path / "prose_and_table.pdf"
    out = tmp_path / "prose_and_table_flat.pdf"
    doc = fitz.open()
    page = doc.new_page()
    _write(page, [(60, 70, "TIEU DE PHAI CON NGUYEN VEN")])
    rows = [["Dieu kien", "Han muc"], ["Uu tien", "15.000 USD"], ["Con lai", "10.000 USD"]]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            _write(page, [(70 + c * 150, 125 + r * 25, text)])
    for r in range(4):
        page.draw_line(fitz.Point(60, 110 + r * 25), fitz.Point(360, 110 + r * 25),
                       width=0.6)
    for c in range(3):
        page.draw_line(fitz.Point(60 + c * 150, 110), fitz.Point(60 + c * 150, 185),
                       width=0.6)
    _write(page, [(60, 260, "Doan van ban ben duoi cung phai con nguyen ven.")])
    doc.save(src)
    doc.close()

    summary = PDFTableFlattenerPipeline(numbering=False).process(str(src), str(out))
    assert summary["verification"].passed, summary["verification"].describe()

    with fitz.open(out) as result:
        text = result[0].get_text()
        rows_after = _text_rows(result[0])
    assert "TIEU DE PHAI CON NGUYEN VEN" in text
    assert "Doan van ban ben duoi cung phai con nguyen ven." in text
    # The two paragraphs are still on the rows they started on.
    with fitz.open(src) as original:
        rows_before = _text_rows(original[0])
    for y in (rows_before[0], rows_before[-1]):
        assert any(abs(y - r) <= 1.0 for r in rows_after)
