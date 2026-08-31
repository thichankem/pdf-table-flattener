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

Nothing here ever deletes the words of a line.  Words are *added*: a number in
front of a row, and -- on the lines nested far enough under a row -- the few
words of that row which say what the line is about.  A chunker cuts a fixed
number of tokens and knows nothing of indentation, so a line that names its own
record is the only kind that survives being cut away from it; a line still
sitting beside its row has no need to repeat it, and repeating it there is noise
the reader pays for on every line of every table.

The one thing that looks like a deletion is not one: a row that opens with its
own counter ("1", "2") next to the number this tool just gave it has that
counter absorbed into the number rather than printed twice -- and only when the
number ends in exactly that counter, so the digits stay written down.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .formatter import INDENT_UNIT, SEPARATOR, is_index_label, leading_counter
from .grid_extractor import group_words_into_lines
from .text_utils import bullet_marker, is_bullet_line, strip_bullet, tokenize

logger = logging.getLogger(__name__)

Path = Tuple[int, ...]
BBox = Tuple[float, float, float, float]

# How many components a number may have before it stops earning its tokens.
# "1.1.1" is a breadcrumb; "1.1.1.1" repeated down a hundred-row table is the
# same breadcrumb paid for a hundred times over.  Deeper lines are written with
# their indent alone -- no number.
MAX_NUMBER_DEPTH = 3

# Only a table's rows are numbered, and never what nests inside one: a table at
# 1.1 has rows 1.1.1, 1.1.2, and that is where the numbering stops.  What sits
# under a row keeps the marker the source document gave it -- "a)", "b)", a
# dash -- because an invented "1.1.1.1" says nothing the marker did not, and
# costs tokens on every line of every row.
MAX_ROW_DEPTH = 1

# What the retriever reads at once.  A record longer than this is cut in two by
# the chunker no matter how it is written, and only the words repeated on each
# of its lines can tell the second half where it came from.
RAG_CHUNK_TOKENS = 512

# Vietnamese runs at roughly this many model tokens per word, which is what
# turns a word count into the budget above.
TOKENS_PER_WORD = 1.8

# How many characters of its row a nested line repeats.  Enough to name the
# record, short enough that repeating it down a long cell stays affordable.
MAX_CONTEXT_CHARS = 60

# How far a nested line may sit from the last place its record was named before
# it has to name it again.  Half a chunk: two mentions that far apart put one of
# them inside every window the chunker can cut, wherever it happens to cut --
# which is the whole job, done once instead of on every line.  A row shorter than
# this is never cut away from its own heading, so it repeats nothing at all.
CONTEXT_REPEAT_WORDS = int(RAG_CHUNK_TOKENS / 2 / TOKENS_PER_WORD)

# Marks the part of a table that carries on after a page break, so a chunk cut
# from page 2 still says which table it belongs to.
CONTINUED_MARK = "(tiếp theo)"

# How long a line may be and still read as the name of a table.  A name is a
# title, not a paragraph: past this it is prose that happens to end in a colon.
MAX_TITLE_CHARS = 150

# A caption sits directly on top of its table.  Further above than this is the
# paragraph before it, which names the table no more than any other line does.
MAX_TITLE_GAP = 30.0

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
# The document naming a table outright: "Bảng 3: Biểu phí", "Phụ lục 02".
_NAMES_A_TABLE_RE = re.compile(r"^(bảng|biểu|phụ\s*lục|table)\b", re.IGNORECASE)
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


def _strip_leading_number(line: str) -> str:
    """Drop the outline number a line writes down ("2.3.", "ĐIỀU 5:").

    A table's caption already carries the number the table was given, so
    repeating the section's own would read "2.3.1 2.3. Nguyên tắc phân bổ".
    """
    article = _ARTICLE_RE.match(line)
    if article and not article.group(2)[:1].isdigit():
        return article.group(2).strip() or line
    match = _NUMBER_RE.match(line)
    if match:
        rest = match.group(3).lstrip(_OPENING_MARKS)
        if rest and _LETTER_RE.match(rest[0]):
            return match.group(3).strip()
    return line


def table_title(text: str, heading: bool = False) -> str:
    """The name this line gives the table printed below it, or "" for none.

    A table is named by the document itself, in one of three ways: a heading
    right above it ("2.3. Nguyên tắc xác định đơn vị quản lý"), a lead-in that
    ends in a colon ("Chức danh lãnh đạo và phân hạng tương ứng như bảng sau:"),
    or a caption that says so outright ("Bảng 3: Biểu phí").  `heading` is what
    the source knows and the words cannot say -- a Word heading style, a number
    Word drew itself.

    Ordinary prose names nothing and gets nothing back: a full sentence is about
    the table, not its name, and a table the document never named is better off
    with no caption at all than with one invented for it.
    """
    line = " ".join((text or "").split())
    if not line or is_contents_line(line):
        return ""
    line = _strip_leading_number(line)
    names_a_table = bool(_NAMES_A_TABLE_RE.match(line))
    if not (heading or names_a_table or line.endswith(":")):
        return ""
    # A heading does not end in a full stop; a sentence does.  "Bảng 3: Biểu
    # phí." is still a caption, so only the other two are held to it.
    if line.endswith(".") and not names_a_table:
        return ""
    line = line.rstrip(":").strip()
    return line if line and len(line) <= MAX_TITLE_CHARS else ""


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
    at 1.1.15 instead of starting again at 1.1.1.  `context` survives it too --
    it is the name of the last row written, which the first line of the next page
    needs in order to say which record it continues.
    """

    path: Path
    rows: int = 0
    context: str = ""

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

    def section_at(self, page: int, top: float) -> Path:
        """The section this point of the document falls in, without moving on.

        :meth:`advance_to` answers the same question but only ever forwards, and
        counting how many tables a section holds has to be done before the first
        of them is numbered -- hence a reading that leaves the cursor alone.
        """
        section: Path = ()
        for event in self._events:
            if (event.page, event.top) >= (page, top):
                break
            section = event.path
        return section

    def advance_to(self, page: int, top: float) -> None:
        """Enter every heading that sits before this point in the document."""
        while self._cursor < len(self._events):
            event = self._events[self._cursor]
            if (event.page, event.top) >= (page, top):
                break
            self.enter(event.path)
            self._cursor += 1

    # -- handing out numbers ---------------------------------------------
    def has_children(self, section: Path) -> bool:
        """Does the document number anything of its own under `section`?"""
        return bool(self._taken.get(tuple(section)))

    def next_table(
        self, section: Optional[Path] = None, alone: bool = False
    ) -> TableNumber:
        """The number for the next table of `section` (the current one by default).

        A caller that worked out where its tables sit in a pass of its own --
        the Word path does, because it has to resolve Word's own list counters
        first -- passes the section in rather than relying on the cursor.

        `alone` says this is the only table the section holds.  Such a section
        *is* its table, so the table keeps the section's own number instead of
        opening a level beneath it: under "3.5. Quy định sản phẩm tiết kiệm
        thường" the rows are 3.5.1, 3.5.2, rather than a "3.5.1" that repeats
        the heading word for word and pushes every row down to 3.5.1.1.

        A section that numbers children of its own is left alone even then --
        its rows would be handed numbers that real headings further down own.
        """
        parent = self._section if section is None else tuple(section)
        if alone and parent and not self.has_children(parent):
            return TableNumber(path=parent)
        taken = self._taken.setdefault(parent, set())
        index = 1
        while index in taken:
            index += 1
        taken.add(index)
        return TableNumber(path=parent + (index,))


# ---------------------------------------------------------------------------
# rewriting a table's bullets as a numbered branch
# ---------------------------------------------------------------------------
def _header_line(headers: Optional[Sequence[str]]) -> str:
    """Every column header, each written once."""
    seen: List[str] = []
    for header in headers or ():
        text = " ".join((header or "").split())
        if text and text not in seen:
            seen.append(text)
    return SEPARATOR.join(seen)


def _unsaid_headers(lines: Sequence[str], headers: Optional[Sequence[str]]) -> str:
    """The column headers, when the rows below do not already name them.

    A list of headers is not a name -- it is the top row read aloud -- so it is
    never what a table is captioned with.  It is still the only place some
    headers are ever written: a column whose cells are all empty, and a table
    pivoted around its side labels, name their columns nowhere else, and
    dropping the line would drop those words out of the document.

    Returns "" when every header is already said by the rows themselves, which
    is the ordinary case -- each cell is rendered as "Header: value".

    The row counter's header ("STT") is the everyday case of a header no row
    says: it is deliberately never printed in front of a number, so this line is
    the one place in the document it survives.
    """
    if not headers:
        return ""
    body = "\n".join(lines)
    seen: List[str] = []
    for header in headers:
        text = " ".join((header or "").split())
        if text and text not in seen and text.rstrip(":").strip() not in body:
            seen.append(text)
    return SEPARATOR.join(seen)


def unsaid_header_line(
    lines: Sequence[str], headers: Optional[Sequence[str]]
) -> str:
    """The one line that keeps the headers no row repeats, or "" when there are none.

    Numbering writes those headers on the table's caption line, and that is the
    only place some of them are ever written -- the row counter's "STT" above
    all, which is deliberately never printed in front of a number.  With
    numbering turned off there is no caption line, so without this the word
    would simply vanish from the document and criterion 1 would fail.

    Returned as a line rather than written straight in, because the caller is
    the only one that knows whether the same line has already been written for
    an earlier page of the same table -- and the line, not the headers it was
    built from, is what must not appear twice.
    """
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return ""
    unsaid = _unsaid_headers(body, headers)
    if not unsaid:
        return ""
    return "- " + (_header_line(headers) or unsaid)


def keep_unsaid_headers(
    lines: Sequence[str], headers: Optional[Sequence[str]]
) -> List[str]:
    """`lines` with that header line in front, for a table that is not paged."""
    line = unsaid_header_line(lines, headers)
    return [line] + list(lines) if line else list(lines)


def _shorten(text: str, limit: int = MAX_CONTEXT_CHARS) -> str:
    """`text` in one line, cut at a word boundary once it passes `limit`."""
    words = " ".join((text or "").split())
    if len(words) <= limit:
        return words
    cut = words[:limit].rsplit(" ", 1)[0] or words[:limit]
    # A cut lands wherever the character count runs out, which is often just
    # after a separator ("... định cư/").  The mark joined two things and now
    # dangles in front of nothing, so it goes.
    return cut.rstrip(" ,;:/-–—") or cut


def _counts_itself(headers: Optional[Sequence[str]]) -> bool:
    """Does this table number its own rows in a column of its own ("STT")?"""
    return any(is_index_label(h) for h in headers or ())


def _bare_text(line: str) -> str:
    """A body line without its indent and without its bullet glyph."""
    stripped = line.lstrip(" ")
    return strip_bullet(stripped) if is_bullet_line(stripped) else stripped


def _row_level(line: str) -> int:
    return (len(line) - len(line.lstrip(" "))) // max(1, len(INDENT_UNIT))


def _opens_a_group(body: Sequence[str], index: int) -> bool:
    """Is the counter-less row at `index` a divider between groups of rows?

    A table that counts its own rows still puts uncounted rows between them --
    "I. Người cư trú là tổ chức...", spanning the full width, dividing the rows
    that follow from the rows above.  It is told from the tail of a row that a
    page break cut by what comes after it: a divider is followed by a count
    starting over at 1, a cut-off tail by the count carrying on.

    Getting this right is what keeps our numbering level with the document's own,
    which is what lets the counter be absorbed at all: a divider counted as a row
    puts every row after it one out of step.
    """
    for line in body[index + 1:]:
        if _row_level(line) != 0:
            continue
        counter = leading_counter(_bare_text(line))
        if counter is not None:
            return counter == 1
    return False


def _absorb_row_index(text: str, row: int) -> str:
    """`text` without the leading counter that the row's own number now states.

    A row of a table with an "STT" column reads "1  |  Nguồn thu: ...", and it
    has just been handed the number 1.4.1 -- so the line would open "1.4.1 1",
    which indexes the row twice and says nothing the second time.

    The segment is dropped only when the number ends in exactly that counter, so
    the digits are not lost: they are the last component of the row's number.  A
    counter that disagrees with our count (a table whose rows are numbered 8, 9,
    10 on a continuation page) is the document's own reference and stays.
    """
    parts = text.split(SEPARATOR)
    if len(parts) < 2 or leading_counter(text) != row:
        return text
    rest = SEPARATOR.join(parts[1:]).lstrip()
    return rest or text


def row_context(row: str) -> str:
    """The few words of a row that say which record it is.

    A row reads "1  |  Mục đích: Chuyển tiền học phí  |  Hồ sơ:", and what names
    it is "Chuyển tiền học phí" -- not the "1", which counts rows rather than
    naming one, and not the "Hồ sơ:" that only announces the column its list
    fills.  The label in front of a value is dropped as well: the value is what
    a reader searches for, and the label is repeated on the row itself anyway.
    """
    for part in row.split(SEPARATOR):
        segment = " ".join(part.split())
        if not segment or segment.endswith(":"):
            continue
        _, sep, value = segment.partition(": ")
        if sep and value.strip():
            segment = value.strip()
        if not _LETTER_RE.search(segment):
            # "1", "3.8": an index, not a name.
            continue
        return _shorten(segment)
    return ""


def number_table_lines(
    lines: Sequence[str],
    number: TableNumber,
    title: str = "",
    headers: Optional[Sequence[str]] = None,
    continued: bool = False,
) -> List[str]:
    """Rewrite one table's bullet lines as a numbered branch of the document.

    The table itself is `number` (say 1.1) and its rows become 1.1.1, 1.1.2 --
    one level, and no more.  A row that already counts itself in its first column
    does not get counted twice: that counter is absorbed into the number (see
    :func:`_absorb_row_index`).  Keeping the two counts in step is what makes
    that possible, so in a table with a counter column a line that carries no
    counter is read as the rest of the row above rather than as a row of its own
    -- which is what it is, every time: the tail of a cell a page break cut.

    What nests inside a row is not numbered at all: it keeps the marker the
    source wrote it with ("a)", "b)", a dash).  Once it has drifted
    `CONTEXT_REPEAT_WORDS` words away from the last mention of its record, it
    also gains, in front of its own words, the few words of its row that say
    which record that is -- because a chunker cuts a fixed number of tokens and
    reads neither indent nor bullet, so a line cut away from its row keeps its
    context only by carrying it.  Nearer than that the row is in the same chunk
    and says it already, and a second copy is noise.

    Rows are separated by a blank line, which is where a chunker prefers to cut
    -- so a record is cut whole rather than through the middle of a sentence.

    The caption line carries the table's own number however deep the table sits,
    because it is the one line that says which branch everything below belongs
    to.  `title` is the name the document gave the table (see
    :func:`table_title`); the column headers no row repeats are added to it, as
    the only place those words are written down.

    `number` is advanced as rows are consumed, so calling this again for the
    continuation of the same table on the next page carries on where it stopped.
    """
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return list(lines)

    out: List[str] = []
    name = " ".join((title or "").split())
    # The headers no row repeats are written here and nowhere else -- the row
    # counter's "STT" above all, which is never printed in front of a number.
    # Once, though: the page this table started on wrote them, and a header row
    # printed again on each of the eleven pages it spills onto is noise.  What a
    # chunk cut from page eleven needs is the branch it sits in, and every row
    # on it carries that itself, in the number it opens with.
    unsaid = "" if continued else _unsaid_headers(body, headers)
    if unsaid and not name:
        # "1.3 STT" on its own names nothing.  Standing with the headers beside
        # it, the line reads as what it is -- the top row of the table.
        unsaid = _header_line(headers) or unsaid
    caption = name or unsaid
    # A table continued overleaf keeps its rows at the depth they had on the
    # page before, caption line or no caption line.
    shift = 1 if (caption or continued) else 0
    if caption:
        head = f"{number.label} {caption}"
        if continued:
            head = f"{head} {CONTINUED_MARK}"
        if name and unsaid:
            head = f"{head}{SEPARATOR}{unsaid}"
        out.append(head)

    counts_itself = _counts_itself(headers)
    row = number.rows
    # The name of the last row written, which on a continuation page is on the
    # page before -- so a line nested at the top of this one is already a chunk
    # away from its row and has to name it.
    context = number.context
    words = 0
    since = CONTEXT_REPEAT_WORDS
    warned = False
    unnumbered = False
    for index, line in enumerate(body):
        stripped = line.lstrip(" ")
        raw_level = _row_level(line)
        bare = _bare_text(line)

        # A table that counts its own rows has said, by leaving the count out,
        # that this line is not one of them.  It is one of two other things, and
        # what follows it says which -- see :func:`_opens_a_group`.
        divider = False
        if raw_level == 0 and counts_itself and leading_counter(bare) is None:
            if _opens_a_group(body, index):
                divider = True
            elif row > 0:
                # The rest of the row above, cut apart by a page break or by a
                # stray ruling.  Numbering it would invent a record the document
                # does not have.
                raw_level = MAX_ROW_DEPTH
                unnumbered = True

        if raw_level == 0:
            level = 0
        elif row == number.rows and not unnumbered:
            # Nothing can nest inside a row that was never written: a block
            # opening on an indented line starts its first record there.
            level = 0
        else:
            level = min(raw_level, MAX_ROW_DEPTH)
        indent = INDENT_UNIT * (level + shift)

        if level == 0:
            text = bare
            if out:
                # The blank line between two records is what a chunker cuts on.
                out.append("")
            if divider:
                # A divider is not a record and takes no number of its own; the
                # rows it divides keep the count the document gave them.
                out.append(f"{indent}{text}")
                unnumbered = True
            else:
                row += 1
                path = number.path + (row,)
                if len(path) <= MAX_NUMBER_DEPTH:
                    # The number states the row's index, so the row need not.
                    text = _absorb_row_index(text, row)
                    out.append(f"{indent}{'.'.join(str(p) for p in path)} {text}")
                else:
                    # Past the limit a number costs more than it says; the caption
                    # above already names the branch this row sits in.  Nothing
                    # states the row's index here, so its own counter stays.
                    out.append(f"{indent}{text}")
            # A row with nothing but numbers in it is named by its table.
            context = row_context(text) or _shorten(name)
            words = len(tokenize(text))
            # The row line names the record; the distance starts from there.
            since = words
        else:
            marker = bullet_marker(stripped)
            lead = f"{marker} " if marker else ""
            said = ""
            if context and since >= CONTEXT_REPEAT_WORDS:
                said = f"{context}{SEPARATOR}"
                since = 0
            out.append(f"{indent}{lead}{said}{bare}")
            spent = len(tokenize(bare))
            words += spent
            since += spent

        if not warned and words * TOKENS_PER_WORD > RAG_CHUNK_TOKENS:
            logger.info(
                "Row %s is longer than one %d-token chunk: a retriever will cut "
                "it in two, and only the words each line repeats will say where "
                "the second half came from.",
                ".".join(str(p) for p in number.path + (row,)),
                RAG_CHUNK_TOKENS,
            )
            warned = True

    number.rows = row
    number.context = context
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


def lines_outside_tables(page, boxes: Sequence[BBox] = ()) -> List[Any]:
    """The page's own text lines -- everything that is not inside a table."""
    try:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Reading the text of a page failed: %s", exc)
        return []
    return group_words_into_lines([w for w in words if _outside(w, boxes)])


def _page_metrics(lines: Sequence[Any]) -> Tuple[float, float]:
    """``(where the right margin is, the usual gap between two lines)``."""
    if not lines:
        return 0.0, 0.0
    left = min(ln.x0 for ln in lines)
    right = max(ln.x1 for ln in lines)
    gap = _median(
        [
            lines[i + 1].top - lines[i].bottom
            for i in range(len(lines) - 1)
            if lines[i + 1].top >= lines[i].bottom
        ]
    )
    return right - max(8.0, (right - left) * 0.04), gap


def _starts_paragraph(line, previous, full_line: float, gap: float) -> bool:
    """Does this line begin a paragraph, or carry the one above it on?

    Two signals, because a page gives no others: the line above stops short of
    the right margin, or there is more space above this line than between two
    lines of the same paragraph.
    """
    return (
        previous is None
        or previous.x1 < full_line
        or (line.top - previous.bottom) > gap * 1.6 + 1.0
    )


def title_above(lines: Sequence[Any], top: float) -> str:
    """The name the text printed directly above `top` gives the table there.

    Only what rests on the table is asked -- a caption is written right above
    what it captions -- and it is read whole: a page wraps a sentence over
    several lines, and the last line of one ("... chi trả như dưới đây:") is a
    fragment of a name, not a name.  A numbered heading is one line by
    construction and is taken as it stands.
    """
    above = sorted((ln for ln in lines if ln.bottom <= top + 1.0), key=lambda ln: ln.top)
    if not above or top - above[-1].bottom > MAX_TITLE_GAP:
        return ""

    nearest = above[-1]
    if parse_heading(nearest.text) is not None:
        return table_title(nearest.text, heading=True)

    full_line, gap = _page_metrics(lines)
    parts = [nearest]
    for line in reversed(above[:-1]):
        if _starts_paragraph(parts[0], line, full_line, gap):
            break
        parts.insert(0, line)
    return table_title(" ".join(ln.text for ln in parts))


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

        full_line, gap = _page_metrics(lines)

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

            if _starts_paragraph(line, previous, full_line, gap) or continues_outline(
                last, path
            ):
                events.append(OutlineEvent(page=page_num, top=line.top, path=path))
                known.append(path)
                last = path
            previous = line

    logger.info("Outline: %d heading(s) found in the document text.", len(events))
    return events, known
