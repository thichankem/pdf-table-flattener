"""Write the flattened bullets back into the PDF.

Design rules that follow directly from the acceptance criteria:

* Pages without tables are byte-copied -- criterion 1 is then trivially true.
* On a table page, only the table rectangle is redacted.  Nothing else on the
  page is re-drawn, re-flowed or re-typeset, so headers, logos, footnotes and
  images survive untouched.
* Text is never clipped.  If the bullets do not fit in the freed rectangle we
  first shrink the font, then use the empty space below the table, and finally
  continue on an appended page.  Silent truncation is what destroyed content in
  the previous version.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import fitz

from .config import settings
from .text_layout import PlacedLine, fit_plan

logger = logging.getLogger(__name__)

LEADING_RATIO = 1.32
BOTTOM_SAFETY = 6.0


class PDFPatcher:
    def __init__(self, font_path: Optional[str] = None):
        self.font_path = font_path or settings.get_font_path()
        # fontfile -> characters actually drawn with it, and the font objects,
        # used to rebuild a correct ToUnicode map before saving.
        self._charsets: Dict[str, set] = {}
        self._fonts: Dict[str, fitz.Font] = {}
        self._font_xrefs: Dict[int, str] = {}
        # fontfile -> characters it could not draw, so each is reported once.
        self._missing_glyphs: Dict[str, set] = {}

    # -- public ----------------------------------------------------------
    def process_pdf(
        self,
        pdf_path: str,
        output_path: str,
        patches_by_page: Dict[int, List[Dict[str, Any]]],
        pages_without_tables: Set[int],
    ) -> Dict[str, Any]:
        # Font xrefs are per-document; carrying them over from a previous file
        # would rewrite an unrelated font's ToUnicode map.
        self._charsets.clear()
        self._fonts.clear()
        self._font_xrefs.clear()
        self._missing_glyphs.clear()

        src = fitz.open(pdf_path)
        out = fitz.open()
        stats = {"spill_pages": 0, "shrunk_tables": 0}

        for page_num in range(len(src)):
            out.insert_pdf(src, from_page=page_num, to_page=page_num)
            if page_num in pages_without_tables or not patches_by_page.get(page_num):
                continue

            page = out[-1]
            patches = [
                dict(p, bbox=_to_page_space(page, p["bbox"]))
                for p in patches_by_page[page_num]
            ]
            patches.sort(key=lambda p: p["bbox"][1])
            # Work on the page as if it were not rotated.  PyMuPDF mixes the two
            # frames -- drawings and redactions are unrotated, TextWriter is
            # validated against the rotated rectangle -- and clearing /Rotate for
            # the duration makes both agree.  It is restored below, so the saved
            # page looks exactly as before.
            rotation = page.rotation
            if rotation:
                page.set_rotation(0)
            obstacles = self._page_obstacles(page, [p["bbox"] for p in patches])
            # Where every line of the page sits before anything is redacted.
            # Redaction must not move a single one of them; see
            # `repair_line_moves`.
            rows = _text_rows(page)

            # Pass 1 -- delete the table's ruling lines.  No fill is painted and
            # no text is touched, so this rectangle may safely cover the border
            # strokes even where they graze a neighbouring block (page headers
            # often sit a fraction of a point above a table's top rule).
            for patch in patches:
                page.add_redact_annot(self._lineart_rect(page, patch["bbox"]))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                text=fitz.PDF_REDACT_TEXT_NONE,
            )
            # Before pass 2, so that pass 2 erases the table where the table is.
            page = repair_line_moves(out, page, rows)

            # Pass 2 -- erase the table's text and paint the area blank.  This
            # rectangle is clamped so it can never overlap content that must
            # survive untouched.
            for patch in patches:
                page.add_redact_annot(
                    self._redaction_rect(page, patch["bbox"], obstacles),
                    fill=(1, 1, 1),
                )
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            page = repair_line_moves(out, page, rows)

            overflow: List[str] = []
            for idx, patch in enumerate(patches):
                lower_limit = self._free_bottom(
                    page, patch["bbox"], obstacles, patches, idx
                )
                remaining, shrunk = self._draw_block(
                    page,
                    patch["bullet_lines"],
                    patch["bbox"],
                    lower_limit,
                    patch.get("font_file"),
                    patch.get("font_size"),
                )
                stats["shrunk_tables"] += int(shrunk)
                if remaining:
                    overflow.extend(remaining)

            if rotation:
                page.set_rotation(rotation)

            if overflow:
                stats["spill_pages"] += self._write_spill_pages(
                    out, src[page_num], overflow, patches
                )

        self._repair_tounicode(out)
        out.save(output_path, garbage=3, deflate=True)
        src.close()
        out.close()
        logger.info("Wrote %s", output_path)
        return stats

    # -- geometry --------------------------------------------------------
    @staticmethod
    def _lineart_rect(
        page: fitz.Page, bbox: Tuple[float, float, float, float]
    ) -> fitz.Rect:
        """Rectangle that fully contains the table *and its own ruling lines*.

        Border strokes usually sit a fraction of a point outside the reported
        table bbox, so a rect stopping at the bbox leaves them behind -- and a
        table whose borders are merely painted over white is still a table in
        the file (criterion 2).
        """
        rect = fitz.Rect(bbox)
        probe = fitz.Rect(rect.x0 - 4.0, rect.y0 - 4.0, rect.x1 + 4.0, rect.y1 + 4.0)
        grown = fitz.Rect(rect)
        for item in page.get_drawings():
            r = fitz.Rect(item["rect"])
            if r.x0 >= probe.x0 and r.y0 >= probe.y0 and r.x1 <= probe.x1 and r.y1 <= probe.y1:
                # Ruling lines are zero-width rects, which `Rect.__or__` treats
                # as empty and ignores -- expand the bounds by hand.
                grown.x0 = min(grown.x0, r.x0)
                grown.y0 = min(grown.y0, r.y0)
                grown.x1 = max(grown.x1, r.x1)
                grown.y1 = max(grown.y1, r.y1)
        return fitz.Rect(
            grown.x0 - 0.6, grown.y0 - 0.6, grown.x1 + 0.6, grown.y1 + 0.6
        )

    def _redaction_rect(
        self,
        page: fitz.Page,
        bbox: Tuple[float, float, float, float],
        obstacles: Sequence[fitz.Rect],
    ) -> fitz.Rect:
        """Area that gets its text removed and is painted blank.

        Same footprint as :meth:`_lineart_rect`, but pulled back off anything
        that must survive untouched.
        """
        rect = fitz.Rect(bbox)
        grown = self._lineart_rect(page, bbox)

        # Never let the grown rect bite into content that must stay untouched.
        for other in obstacles:
            inter = grown & other
            if not inter.is_valid or inter.get_area() <= 0.5:
                continue
            if other.y1 <= rect.y0 + 0.5:          # sits above the table
                grown.y0 = max(grown.y0, other.y1 + 0.2)
            elif other.y0 >= rect.y1 - 0.5:        # sits below the table
                grown.y1 = min(grown.y1, other.y0 - 0.2)
            elif other.x1 <= rect.x0 + 0.5:
                grown.x0 = max(grown.x0, other.x1 + 0.2)
            elif other.x0 >= rect.x1 - 0.5:
                grown.x1 = min(grown.x1, other.x0 - 0.2)
        return grown

    @staticmethod
    def _page_obstacles(
        page: fitz.Page, table_boxes: Sequence[Tuple[float, float, float, float]]
    ) -> List[fitz.Rect]:
        """Everything on the page that the bullets must not overlap."""
        rects: List[fitz.Rect] = []
        info = page.get_text("dict")
        for block in info.get("blocks", []):
            bbox = block.get("bbox")
            if bbox:
                rects.append(fitz.Rect(bbox))
        for item in page.get_drawings():
            rects.append(fitz.Rect(item["rect"]))
        try:
            for img in page.get_image_info():
                rects.append(fitz.Rect(img["bbox"]))
        except Exception:  # pragma: no cover - defensive
            pass

        def inside_table(r: fitz.Rect) -> bool:
            for t in table_boxes:
                tr = fitz.Rect(t)
                inter = r & tr
                if inter.is_valid and inter.get_area() >= r.get_area() * 0.7:
                    return True
            return False

        return [r for r in rects if r.get_area() > 1 and not inside_table(r)]

    def _free_bottom(
        self,
        page: fitz.Page,
        bbox: Tuple[float, float, float, float],
        obstacles: Sequence[fitz.Rect],
        patches: Sequence[Dict[str, Any]],
        idx: int,
    ) -> float:
        """Lowest y the bullets for this table may reach on the current page."""
        x0, _top, x1, bottom = bbox
        limit = _page_box(page).height - settings.PAGE_BOTTOM_MARGIN

        for r in obstacles:
            if r.y0 < bottom - 1:
                continue
            if r.x1 <= x0 + 1 or r.x0 >= x1 - 1:
                continue  # no horizontal overlap
            limit = min(limit, r.y0 - BOTTOM_SAFETY)

        for other in patches[idx + 1 :]:
            limit = min(limit, other["bbox"][1] - BOTTOM_SAFETY)

        return max(bottom, limit)

    # -- drawing ---------------------------------------------------------
    def _draw_block(
        self,
        page: fitz.Page,
        lines: Sequence[str],
        bbox: Tuple[float, float, float, float],
        lower_limit: float,
        font_file: Optional[str],
        font_size: Optional[float],
    ) -> Tuple[List[str], bool]:
        """Draw as many bullet lines as fit; return the ones that did not."""
        if not lines:
            return [], False

        font_file = font_file or self.font_path
        font = fitz.Font(fontfile=font_file)
        # Before the layout, so a substituted character is measured as drawn.
        lines = [self._drawable(line, font, font_file) for line in lines]
        x0, top, x1, _bottom = bbox
        width = max(40.0, x1 - x0)
        height = max(10.0, lower_limit - top)

        base = font_size or settings.BULLET_FONT_SIZE
        sizes = [round(base - step * 0.5, 2) for step in range(0, 9)]
        sizes = [s for s in sizes if s >= settings.MIN_FONT_SIZE] or [
            settings.MIN_FONT_SIZE
        ]

        size, wrapped, n_fit = fit_plan(
            lines, font, width, height, sizes, LEADING_RATIO
        )
        draw_count, leftover = self._split_at_fit(lines, wrapped, n_fit)
        self._write_lines(page, wrapped[:draw_count], font, font_file, size, x0, top)

        if not leftover:
            return [], size < base
        logger.info(
            "Table at %.0f,%.0f overflows page: %d line(s) continue on a new page.",
            x0,
            top,
            len(leftover),
        )
        return leftover, True

    def _drawable(self, line: str, font: fitz.Font, font_file: str) -> str:
        """`line` with every character the render font cannot draw replaced.

        A missing glyph is written as .notdef: a blank box on the page that
        reads back as U+0000, so it fails criterion 3 while looking merely odd.
        A full stop stands in for it -- every text font has one -- and each
        character that needed the substitute is reported once, because a font
        that cannot carry the document is worth knowing about rather than
        silently working around.
        """
        missing = self._missing_glyphs.setdefault(font_file, set())
        out = []
        for char in line:
            if char in " \t" or font.has_glyph(ord(char)):
                out.append(char)
                continue
            if char not in missing:
                missing.add(char)
                logger.warning(
                    "Font %s has no glyph for %r (U+%04X); drawing '.' instead.",
                    Path(font_file).name,
                    char,
                    ord(char),
                )
            out.append(".")
        return "".join(out)

    @staticmethod
    def _split_at_fit(
        logical: Sequence[str], wrapped: Sequence[PlacedLine], n_fit: int
    ) -> Tuple[int, List[str]]:
        """Decide what to draw now and what to carry over.

        Returns ``(physical_lines_to_draw, logical_lines_left)``.  Drawing stops
        at a logical-line boundary so nothing is duplicated across the break and
        nothing is orphaned; the remainder is re-emitted as whole bullets, which
        keeps the continuation page properly indented.
        """
        if n_fit >= len(wrapped):
            return len(wrapped), []

        boundary = n_fit
        source = wrapped[boundary].source
        while boundary > 0 and wrapped[boundary - 1].source == source:
            boundary -= 1

        if boundary == 0:
            # One bullet is taller than the whole area; fall back to breaking it
            # between wrapped fragments rather than losing its tail.
            return n_fit, [line.text for line in wrapped[n_fit:]]

        return boundary, list(logical[wrapped[boundary].source :])

    def _write_lines(
        self,
        page: fitz.Page,
        lines: Sequence[PlacedLine],
        font: fitz.Font,
        font_file: str,
        size: float,
        x0: float,
        top: float,
    ) -> None:
        if not lines:
            return
        writer = fitz.TextWriter(page.rect)
        y = top + size
        charset = self._charsets.setdefault(font_file, set())
        self._fonts.setdefault(font_file, font)
        for placed in lines:
            # The blank line between two records is drawn as a single space.
            # A PDF has no line the reader cannot see: a gap with nothing in it
            # is not extracted as a line at all, and the break that separates
            # one record from the next would be lost to whatever reads the text
            # back -- which, for a document written to be retrieved from, is the
            # reader that matters most.
            text = placed.text if placed.text.strip() else " "
            writer.append(
                fitz.Point(x0 + placed.indent, y),
                text,
                font=font,
                fontsize=size,
            )
            charset.update(text)
            y += size * LEADING_RATIO

        before = {info[0] for info in page.get_fonts()}
        writer.write_text(page, color=(0, 0, 0))
        for info in page.get_fonts():
            if info[0] not in before:
                self._font_xrefs[info[0]] = font_file

    # -- text extraction fidelity ----------------------------------------
    def _repair_tounicode(self, doc: fitz.Document) -> None:
        """Rewrite the ToUnicode CMap of every font this tool embedded.

        MuPDF derives ToUnicode by inverting the font's own cmap, and picks an
        arbitrary alias when several code points share a glyph -- Times maps
        both U+0020/U+00A0 to the space glyph and U+002D/U+00AD to the hyphen.
        The result is output that *looks* right but yields soft hyphens and
        non-breaking spaces when copied, which criterion 3 forbids.  Since we
        know exactly which characters we drew, we can emit an exact map.
        """
        for xref, font_file in self._font_xrefs.items():
            font = self._fonts.get(font_file)
            charset = self._charsets.get(font_file)
            if not font or not charset:
                continue
            try:
                key_type, value = doc.xref_get_key(xref, "ToUnicode")
                if key_type != "xref":
                    continue
                stream_xref = int(value.split()[0])
                doc.update_stream(
                    stream_xref, _build_tounicode(font, charset), compress=True
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Could not repair ToUnicode for xref %s: %s", xref, exc)

    # -- spill -----------------------------------------------------------
    def _write_spill_pages(
        self,
        out: fitz.Document,
        template: fitz.Page,
        lines: List[str],
        patches: Sequence[Dict[str, Any]],
    ) -> int:
        box = _page_box(template)
        width = box.width
        height = box.height
        left = min(p["bbox"][0] for p in patches)
        right = max(p["bbox"][2] for p in patches)
        font_file = patches[0].get("font_file") or self.font_path
        base = patches[0].get("font_size") or settings.BULLET_FONT_SIZE
        font = fitz.Font(fontfile=font_file)

        top = settings.PAGE_TOP_MARGIN
        avail_h = height - settings.PAGE_TOP_MARGIN - settings.PAGE_BOTTOM_MARGIN
        avail_w = max(60.0, right - left)

        sizes = [base] if base >= settings.MIN_FONT_SIZE else [settings.MIN_FONT_SIZE]
        pages_added = 0
        remaining = list(lines)
        while remaining:
            page = out.new_page(width=width, height=height)
            pages_added += 1
            size, wrapped, n_fit = fit_plan(
                remaining, font, avail_w, avail_h, sizes, LEADING_RATIO
            )
            n_fit = max(1, n_fit)
            draw_count, leftover = self._split_at_fit(remaining, wrapped, n_fit)
            self._write_lines(
                page, wrapped[:draw_count], font, font_file, size, left, top
            )
            if leftover == remaining:  # pragma: no cover - would loop forever
                logger.error("Cannot place %d line(s); stopping.", len(leftover))
                break
            remaining = leftover
        logger.info("Added %d continuation page(s) for overflowing bullets.", pages_added)
        return pages_added


# -- MuPDF's doubled line moves ------------------------------------------
#
# `apply_redactions` re-writes every content stream of the page through MuPDF's
# content filter.  MuPDF 1.29 (PyMuPDF 1.28) turns a text object placed by a
# translation-only `Tm` into `tx ty TD T*`.  `TD` also *sets the leading* to
# -ty, so the `T*` that follows moves the line down by that same amount a second
# time: every line of the page ends up twice as far from the origin as it
# should.  The page then no longer matches the table rectangles measured before
# the call -- the tool erases whatever drifted into them and leaves the table
# text behind, one row lower.
#
# Only the pages of some producers are affected (a `Tm` carrying a scale is
# written back as `Tm`), so the repair is applied only where the damage is
# actually observed, and it is checked afterwards.  MuPDF's writer never emits
# `TL`, and emits `T*` for no other reason, so the pair unambiguously means the
# `Td` it should have written.
_DOUBLED_LINE_MOVE = re.compile(rb"TD[\s]+T\*")
# An operator is preceded by whitespace; `/TD` is a name, and `xTD` is not `TD`.
_PDF_WHITESPACE = b" \t\r\n\f\x00"
# A line that has to move this far to be considered moved rather than rounded.
_MOVED_TOLERANCE = 1.0


def _undo_doubled_line_moves(stream: bytes) -> Tuple[bytes, int]:
    """Rewrite each `TD T*` of a content stream as the `Td` it stands for.

    String literals are copied through untouched: `(TD T*)` is text a page may
    legitimately draw, and only operators outside a string are operators.
    """
    out = bytearray()
    fixed = 0
    i, n = 0, len(stream)
    while i < n:
        char = stream[i]
        if char == 0x28:  # "(" -- a literal string, copied verbatim
            depth = 0
            while i < n:
                char = stream[i]
                if char == 0x5C:  # a backslash escapes the next byte
                    out += stream[i : i + 2]
                    i += 2
                    continue
                depth += (char == 0x28) - (char == 0x29)
                out.append(char)
                i += 1
                if depth == 0:
                    break
            continue
        match = (
            _DOUBLED_LINE_MOVE.match(stream, i)
            if i and stream[i - 1] in _PDF_WHITESPACE
            else None
        )
        if match:
            # Padded to the same length, so nothing else in the stream shifts.
            out += b"Td".ljust(match.end() - i)
            i = match.end()
            fixed += 1
            continue
        out.append(char)
        i += 1
    return bytes(out), fixed


def _text_rows(page: fitz.Page) -> List[float]:
    """The y of every text line on the page -- a fingerprint of its layout."""
    rows = set()
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type"):
            continue
        for line in block.get("lines", []):
            rows.add(round(line["bbox"][1], 1))
    return sorted(rows)


def _lines_off_their_row(page: fitz.Page, rows: Sequence[float]) -> int:
    """How many text lines of `page` sit at no y they occupied in `rows`.

    Redaction deletes text; it never moves any, so a single line that no longer
    matches one of the rows recorded beforehand means the page was rewritten
    wrongly.
    """
    return sum(
        1
        for row in _text_rows(page)
        if not any(abs(row - was) <= _MOVED_TOLERANCE for was in rows)
    )


def _form_xobjects(doc: fitz.Document, xref: int) -> List[int]:
    """The xrefs the /XObject resources of `xref` point at."""
    try:
        kind, value = doc.xref_get_key(xref, "Resources/XObject")
    except Exception:  # pragma: no cover - defensive
        return []
    if kind == "xref":
        value = doc.xref_object(int(value.split()[0]))
    elif kind != "dict":
        return []
    return [int(num) for num in re.findall(r"(\d+)\s+0\s+R", value)]


def _content_streams(doc: fitz.Document, page: fitz.Page) -> List[int]:
    """Every stream the page draws from: its own contents and its forms."""
    xrefs = list(page.get_contents())
    seen: Set[int] = set()
    stack = _form_xobjects(doc, page.xref)
    while stack:
        xref = stack.pop()
        if xref in seen:
            continue
        seen.add(xref)
        try:
            if doc.xref_get_key(xref, "Subtype")[1] != "/Form":
                continue
        except Exception:  # pragma: no cover - defensive
            continue
        xrefs.append(xref)
        stack.extend(_form_xobjects(doc, xref))
    return xrefs


def repair_line_moves(
    doc: fitz.Document, page: fitz.Page, rows: Sequence[float]
) -> fitz.Page:
    """Put the page's text back on `rows` if `apply_redactions` moved it.

    Returns the page to keep working with -- rewriting a stream invalidates the
    one that was passed in.
    """
    if not rows or not _lines_off_their_row(page, rows):
        return page

    fixed = 0
    for xref in _content_streams(doc, page):
        try:
            stream = doc.xref_stream(xref)
        except Exception:  # pragma: no cover - defensive
            continue
        repaired, count = _undo_doubled_line_moves(stream)
        if count:
            doc.update_stream(xref, repaired, compress=True)
            fixed += count
    if not fixed:
        logger.warning(
            "Text on page %d moved during redaction and does not carry the "
            "known defect; the page is left as MuPDF wrote it.",
            page.number + 1,
        )
        return page

    page = doc.reload_page(page)
    left = _lines_off_their_row(page, rows)
    if left:
        logger.warning(
            "Page %d: %d line(s) still off their original row after repairing "
            "%d line move(s).",
            page.number + 1,
            left,
            fixed,
        )
    else:
        logger.info(
            "Page %d: repaired %d line move(s) doubled by MuPDF.",
            page.number + 1,
            fixed,
        )
    return page


def _to_page_space(
    page: fitz.Page, bbox: Tuple[float, float, float, float]
) -> Tuple[float, float, float, float]:
    """Convert a pdfplumber bbox into the coordinates PyMuPDF edits in.

    On a page carrying /Rotate, pdfplumber reports what the reader sees while
    PyMuPDF's drawings, text and redactions all live in the unrotated page --
    so a table on such a page would be measured in one place and erased in
    another.  Everything downstream works in unrotated space.
    """
    if not page.rotation:
        return tuple(bbox)
    rect = fitz.Rect(bbox) * page.derotation_matrix
    rect.normalize()
    return (rect.x0, rect.y0, rect.x1, rect.y1)


def _page_box(page: fitz.Page) -> fitz.Rect:
    """The page rectangle in unrotated coordinates."""
    if not page.rotation:
        return page.rect
    rect = fitz.Rect(page.rect) * page.derotation_matrix
    rect.normalize()
    return rect


def _build_tounicode(font: fitz.Font, charset: Sequence[str]) -> bytes:
    """Build an Identity-H ToUnicode CMap covering exactly `charset`."""
    entries = []
    for ch in sorted(set(charset)):
        gid = font.has_glyph(ord(ch))
        if gid:
            entries.append((gid, ord(ch)))
    entries.sort()

    chunks = []
    for start in range(0, len(entries), 100):
        block = entries[start : start + 100]
        body = "\n".join(f"<{gid:04X}> <{uni:04X}>" for gid, uni in block)
        chunks.append(f"{len(block)} beginbfchar\n{body}\nendbfchar")

    cmap = (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\n"
        "begincmap\n"
        "/CIDSystemInfo <</Registry(Adobe)/Ordering(UCS)/Supplement 0>> def\n"
        "/CMapName /Adobe-Identity-UCS def\n"
        "/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        + "\n".join(chunks)
        + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
    )
    return cmap.encode("latin-1")


