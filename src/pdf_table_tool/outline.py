"""Where a flattened table sits in the document's own numbering.

A RAG chunker cuts a long bullet list wherever the chunk gets too big, and a
chunk that starts halfway down a twelve-page table carries nothing that says
what it is about.  Numbering every line with the branch it belongs to fixes
that: each line keeps a breadcrumb back to the document's own outline, and a
long table stays one addressable branch instead of an anonymous run of dashes.

The numbers are not invented from nothing.  The document already numbers itself
-- "ĐIỀU 1", "1.1.", "1.27." -- so a table sitting under "1. Thuật ngữ" is
numbered 1.1 and its rows 1.1.1, rather than restarting at 1.  Two halves live
here:

* reading that outline (:func:`parse_heading`, :func:`scan_pdf_outline`);
* handing each table its number and rewriting its bullets
  (:class:`DocumentOutline`, :func:`number_table_lines`).

Nothing here ever deletes or rewrites the words of a line: a number is only ever
put in front of one, in place of its bullet glyph.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .formatter import INDENT_UNIT, SEPARATOR
from .grid_extractor import group_words_into_lines
from .text_utils import is_bullet_line, strip_bullet

logger = logging.getLogger(__name__)

Path = Tuple[int, ...]
BBox = Tuple[float, float, float, float]

# How many components a number may have before it stops helping.  "1.27.1.4.2"
# is still a useful breadcrumb; anything deeper is noise, and those lines keep
# their bullet glyph instead.
MAX_NUMBER_DEPTH = 6

# Marks the part of a table that carries on after a page break, so a chunk cut
# from page 2 still says which table it belongs to.
CONTINUED_MARK = "(tiếp theo)"

# A heading number: "3.", "3.1", "1.27.".  Components after the first may not
# start with a zero, which is what keeps "1.000.000 đồng" from reading as
# heading 1.000.000.  The blank after the number is optional once it has been
# punctuated, because real documents run the two together ("2.3.2.Điều khoản
# cung cấp thông tin") and that heading has to be found like any other.
_NUMBER_RE = re.compile(r"^(\d{1,3}(?:\.[1-9]\d?)*)(?:([.)])\s*|\s+)(.*)$")
# Vietnamese legal documents number their sections "ĐIỀU 5:" and their clauses
# "5.1." -- the two form one outline, so the article heading is read as its top
# level.  The colon is what tells a heading from a cross-reference in prose
# ("... quy định tại Điều 5 của Hợp đồng").  The spaces are optional because a
# bold, letter-spaced heading reaches us as "ĐIỀU5:" -- the glyphs sit so close
# together that the word splitter finds no gap between them.
_ARTICLE_RE = re.compile(r"^điều\s*(\d{1,3})\s*[:.\-–—]\s*(.*)$", re.IGNORECASE)
# Dot leaders: the line belongs to a table of contents, not to the body.
_LEADER_RE = re.compile(r"\.{4,}")
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_OPENING_MARKS = "\"'“‘([«"


def parse_heading(text: str) -> Optional[Path]:
    """The outline number a line states, or None when it states none.

    Only a number the document wrote down itself is returned.  Prose that
    happens to open with a figure ("2.1 triệu đồng là mức phí") is rejected by
    demanding that what follows the number reads as a title.
    """
    line = " ".join((text or "").split())
    if not line:
        return None

    article = _ARTICLE_RE.match(line)
    # "Điều 8.2 quy định..." is a reference to a clause, not the heading of
    # article 8: what follows the separator is a number, not a title.
    if article and not article.group(2)[:1].isdigit():
        return (int(article.group(1)),)

    match = _NUMBER_RE.match(line)
    if not match:
        return None
    parts = tuple(int(p) for p in match.group(1).split("."))
    if parts[0] == 0 or len(parts) > 4:
        return None
    # A single number only heads a section when it is punctuated as one ("3.").
    # A bare "3 Bản sao là bản sao y chứng thực..." is a footnote, and reading
    # it as a heading would move every table after it into section 3.
    if len(parts) == 1 and not match.group(2):
        return None

    head = match.group(3).lstrip(_OPENING_MARKS)
    if not head or not _LETTER_RE.match(head[0]):
        return None
    return parts


def is_contents_line(text: str) -> bool:
    """Is this line an entry in a table of contents rather than a heading?

    Its number is real -- worth reserving so a table never gets handed it -- but
    the section itself starts pages later, so reading it as "we are now inside
    8.5" would misfile every table on page 2.
    """
    return bool(_LEADER_RE.search(text or ""))


def continues_outline(last: Path, path: Path) -> bool:
    """Does `path` carry on from `last` the way an outline does?

    The first child of the current section, or the next number at any level
    above it.  This is what lets a heading be recognised when it follows a
    justified paragraph whose last line runs to the margin -- geometry says
    nothing there, but "1.13" straight after "1.12" is unmistakable.
    """
    if not last:
        return len(path) == 1 or path[-1] == 1
    if len(path) == len(last) + 1 and path[:-1] == last and path[-1] == 1:
        return True
    depth = len(path)
    if depth <= len(last) and path[:-1] == last[: depth - 1]:
        return path[-1] == last[depth - 1] + 1
    return False


# ---------------------------------------------------------------------------
# the number a table gets
# ---------------------------------------------------------------------------
@dataclass
class TableNumber:
    """The branch one table occupies, and how far down it we have got.

    `rows` survives a page break: a table continued on the next page carries on
    at 1.1.15 instead of starting again at 1.1.1.
    """

    path: Path
    rows: int = 0

    @property
    def label(self) -> str:
        return ".".join(str(p) for p in self.path)


@dataclass
class OutlineEvent:
    """A heading found in the source, with the position it was found at."""

    page: int
    top: float
    path: Path


class DocumentOutline:
    """The document's numbering, and the numbers handed out to its tables.

    Two things are tracked: which section we are currently inside (so a table
    lands under the right parent), and which child numbers are already taken (so
    a table is never handed a number a real heading also uses).
    """

    def __init__(self):
        self._section: Path = ()
        self._taken: Dict[Path, Set[int]] = {}
        self._entered: Dict[Path, int] = {}
        self._events: List[OutlineEvent] = []
        self._cursor = 0

    # -- reading the document -------------------------------------------
    def reserve(self, path: Path) -> None:
        """Record a number the document itself uses, at every level of it."""
        for depth in range(len(path)):
            self._taken.setdefault(tuple(path[:depth]), set()).add(path[depth])

    def enter(self, path: Path) -> None:
        """A heading was reached: everything after it belongs to that section."""
        if not path:
            return
        self.reserve(path)
        self._entered[tuple(path[:-1])] = path[-1]
        self._section = tuple(path)

    def enter_level(self, level: int) -> Path:
        """A heading whose number the document does not spell out.

        Word's Heading styles (and a workbook's sheets) state a *level* and let
        the word processor draw the number, so it is nowhere in the text.  The
        number is counted here instead, which is exactly what Word does.
        """
        parent = self._section[:level]
        while len(parent) < level:
            parent = parent + (1,)
        index = self._entered.get(parent, 0) + 1
        taken = self._taken.setdefault(parent, set())
        while index in taken:
            index += 1
        path = parent + (index,)
        self.enter(path)
        return path

    def leave(self) -> None:
        """Step outside every section -- used for stories with no outline."""
        self._section = ()

    @property
    def section(self) -> Path:
        return self._section

    # -- walking a pre-scanned outline -----------------------------------
    def load(self, events: Sequence[OutlineEvent], known: Iterable[Path] = ()) -> None:
        """Take in headings found ahead of time.

        `known` holds every number the document mentions anywhere, including its
        table of contents.  Reserving them all up front is what guarantees a
        table is never numbered 1.1 in a document that has its own 1.1 further
        down.
        """
        for path in known:
            self.reserve(path)
        self._events = sorted(events, key=lambda e: (e.page, e.top))
        self._cursor = 0

    def advance_to(self, page: int, top: float) -> None:
        """Enter every heading that sits before this point in the document."""
        while self._cursor < len(self._events):
            event = self._events[self._cursor]
            if (event.page, event.top) >= (page, top):
                break
            self.enter(event.path)
            self._cursor += 1

    # -- handing out numbers ---------------------------------------------
    def next_table(self, section: Optional[Path] = None) -> TableNumber:
        """The number for the next table of `section` (the current one by default).

        A caller that worked out where its tables sit in a pass of its own --
        the Word path does, because it has to resolve Word's own list counters
        first -- passes the section in rather than relying on the cursor.
        """
        parent = self._section if section is None else tuple(section)
        taken = self._taken.setdefault(parent, set())
        index = 1
        while index in taken:
            index += 1
        taken.add(index)
        return TableNumber(path=parent + (index,))


# ---------------------------------------------------------------------------
# rewriting a table's bullets as a numbered branch
# ---------------------------------------------------------------------------
def _caption(headers: Optional[Sequence[str]]) -> str:
    """The table's own title line, built from its column headers.

    Repeated labels (one merged header covering three columns) are collapsed:
    the caption names the columns once.
    """
    if not headers:
        return ""
    seen: List[str] = []
    for header in headers:
        text = " ".join((header or "").split())
        if text and text not in seen:
            seen.append(text)
    return SEPARATOR.join(seen)


def number_table_lines(
    lines: Sequence[str],
    number: TableNumber,
    headers: Optional[Sequence[str]] = None,
    continued: bool = False,
) -> List[str]:
    """Rewrite one table's bullet lines as a numbered branch of the document.

    The table itself is `number` (say 1.1); its rows become 1.1.1, 1.1.2 and
    whatever nests inside a row goes one level deeper again.  Each line keeps
    its own words and its nesting -- the number replaces the bullet glyph, and
    the indent moves with it, so number and indent always agree.

    `number` is advanced as rows are consumed, so calling this again for the
    continuation of the same table on the next page carries on where it stopped.
    """
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return list(lines)

    out: List[str] = []
    caption = _caption(headers)
    shift = 0
    if caption:
        head = f"{number.label} {caption}"
        out.append(f"{head} {CONTINUED_MARK}" if continued else head)
        shift = 1

    # Level 0 counts rows and must survive a page break; deeper levels restart
    # inside every row.
    counters: List[int] = [number.rows]
    for line in body:
        stripped = line.lstrip(" ")
        level = (len(line) - len(stripped)) // max(1, len(INDENT_UNIT))
        # A line may only go one level deeper than the line above it: a number
        # cannot have a parent that was never written down.  A source indent
        # that skips a level is pulled back to the first free one.
        level = max(0, min(level, len(counters)))

        if level == len(counters):
            counters.append(0)
        else:
            del counters[level + 1 :]
        counters[level] += 1
        for depth in range(level):
            # A line that starts indented has no parent of its own; give it one
            # rather than emitting a "1.1.0.1".
            counters[depth] = max(1, counters[depth])

        path = number.path + tuple(counters[: level + 1])
        text = strip_bullet(stripped) if is_bullet_line(stripped) else stripped
        indent = INDENT_UNIT * (level + shift)
        if len(path) <= MAX_NUMBER_DEPTH:
            out.append(f"{indent}{'.'.join(str(p) for p in path)} {text}")
        else:
            # Too deep to read as a number; the glyph says more than "1.2.3.4.5.6.1".
            out.append(f"{indent}{stripped}")

    number.rows = counters[0]
    return out


# ---------------------------------------------------------------------------
# reading a PDF's outline
# ---------------------------------------------------------------------------
def _outside(word: Dict[str, Any], boxes: Sequence[BBox]) -> bool:
    """Is this word part of the running text rather than of a table?"""
    cx = (word["x0"] + word["x1"]) / 2.0
    cy = (word["top"] + word["bottom"]) / 2.0
    for x0, top, x1, bottom in boxes:
        if x0 - 1 <= cx <= x1 + 1 and top - 1 <= cy <= bottom + 1:
            return False
    return True


def _median(values: List[float]) -> float:
    return sorted(values)[len(values) // 2] if values else 0.0


def scan_pdf_outline(
    pdf, table_boxes: Optional[Dict[int, Sequence[BBox]]] = None
) -> Tuple[List[OutlineEvent], List[Path]]:
    """Find the numbered headings of a PDF, in reading order.

    Returns ``(headings, every number the document mentions)``.  A line counts
    as a heading when it states a number *and* either starts a new paragraph --
    the line above it stops short of the margin, or there is extra space above
    it -- or carries the outline on from the previous heading.  Either signal
    alone misses real headings in justified text; together they are what tells
    "1.13. Ngày đến hạn đóng phí" apart from a sentence that opens with a
    figure.
    """
    events: List[OutlineEvent] = []
    known: List[Path] = []
    last: Path = ()
    boxes_by_page = table_boxes or {}

    for page_num, page in enumerate(pdf.pages):
        boxes = boxes_by_page.get(page_num) or ()
        try:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Outline scan failed on page %d: %s", page_num + 1, exc)
            continue
        lines = group_words_into_lines([w for w in words if _outside(w, boxes)])
        if not lines:
            continue

        left = min(ln.x0 for ln in lines)
        right = max(ln.x1 for ln in lines)
        full_line = right - max(8.0, (right - left) * 0.04)
        gap = _median(
            [
                lines[i + 1].top - lines[i].bottom
                for i in range(len(lines) - 1)
                if lines[i + 1].top >= lines[i].bottom
            ]
        )

        previous = None
        for line in lines:
            path = parse_heading(line.text)
            if path is None:
                previous = line
                continue
            if is_contents_line(line.text):
                # Its number is real even though its position is not.
                known.append(path)
                previous = line
                continue

            starts_paragraph = (
                previous is None
                or previous.x1 < full_line
                or (line.top - previous.bottom) > gap * 1.6 + 1.0
            )
            if starts_paragraph or continues_outline(last, path):
                events.append(OutlineEvent(page=page_num, top=line.top, path=path))
                known.append(path)
                last = path
            previous = line

    logger.info("Outline: %d heading(s) found in the document text.", len(events))
    return events, known
