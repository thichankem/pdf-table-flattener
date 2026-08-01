"""Write the flattened bullets back into the PDF.

Design rules that follow directly from test.md:

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

        src = fitz.open(pdf_path)
        out = fitz.open()
        stats = {"spill_pages": 0, "shrunk_tables": 0}

        for page_num in range(len(src)):
            out.insert_pdf(src, from_page=page_num, to_page=page_num)
            if page_num in pages_without_tables or not patches_by_page.get(page_num):
                continue

            page = out[-1]
            patches = sorted(
                patches_by_page[page_num], key=lambda p: p["bbox"][1]
            )
            obstacles = self._page_obstacles(page, [p["bbox"] for p in patches])

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
        limit = page.rect.height - settings.PAGE_BOTTOM_MARGIN

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
            if placed.text.strip():
                writer.append(
                    fitz.Point(x0 + placed.indent, y),
                    placed.text,
                    font=font,
                    fontsize=size,
                )
                charset.update(placed.text)
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
        width = template.rect.width
        height = template.rect.height
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


