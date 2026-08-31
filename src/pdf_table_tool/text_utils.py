"""Shared text normalisation helpers.

Everything here is deliberately conservative: the pipeline guarantees that no
word from the source PDF is ever dropped, so these helpers only ever *join*,
*clean* or *transliterate*, never remove a character a reader can see.

:func:`normalize_text` implements section 1 of the text-normalisation spec
(NORM) of the RAG index this tool feeds.  The order of its steps is
part of that spec and is not free to change.
"""

import re
import unicodedata
from typing import List, Match, Tuple

# Bullet glyphs that may introduce a list item inside a table cell.  Only "-",
# "·", "+", "*" and "o" survive normalisation; the rest are listed because this
# regex is also read against text that has not been through it yet.
BULLET_PREFIX_RE = re.compile(r"^\s*([-‐-―•●○▪·+*o])\s+")

# NORM §1.1.  Characters that carry no visible content but pollute extracted
# text.  The soft hyphen is one of them: Word writes it where a line *may* be
# broken, and by the time a wrapped line has been rejoined that break is gone,
# so keeping it would leave a hyphen in the middle of a word nobody ever saw.
_INVISIBLE_CODEPOINTS = (
    list(range(0x00, 0x09)) + list(range(0x0B, 0x20)) +
    [0x00AD, 0x2060, 0xFEFF] + list(range(0x200B, 0x2010)) +
    list(range(0x202A, 0x202F))
)
INVISIBLE_RE = re.compile(
    "[" + "".join(chr(c) for c in _INVISIBLE_CODEPOINTS) + "]"
)

# NORM §1.3.  A Wingdings or Symbol run stores each glyph as its position in
# the font, offset into the private use area, so the code point says nothing
# about the character -- U+F0FC is a tick only because the run is set in
# Wingdings.  A text font has no glyph there at all, and drawing one yields
# .notdef, which reads back as U+0000.
PUA_RE = re.compile("[%s-%s]" % (chr(0xE000), chr(0xF8FF)))

# The few of them whose meaning is known whatever the ASCII position underneath
# says: the two list markers Word writes by default, and its two arrows.
_PUA_EXCEPTIONS = {0xF0B7: "-", 0xF0A7: "-", 0xF0D8: "->", 0xF0E0: "->"}

# A private-use glyph opening a line is the marker of a list item -- that is the
# one thing every symbol font in these documents is used for.  It is written as
# a dash rather than put through the rules below, which would drop a tick
# (U+F0FC lands on "u") and leave the item with no marker at all.
_PUA_MARKER_RE = re.compile(
    "^([ \t]*)[%s-%s]+(?=[ \t])" % (chr(0xE000), chr(0xF8FF)), re.MULTILINE
)

# NORM §1.4.  Symbols written as the words or the ASCII the index expects.
# An embedded text font carries none of these glyphs, so leaving them alone
# costs the character twice over: the renderer draws a full stop in its place,
# and the index reads a sentence with a hole in it.
_SYMBOL_MAP = {
    "∑": " Tổng ", "∏": " Tích ", "√": " căn ", "∞": " vô cùng ",
    "≤": "<=", "≥": ">=", "≠": "!=", "≈": "~=", "±": "+/-",
    "×": "x", "÷": "/", "∗": "*", "→": "->", "⇒": "=>",
}
_SYMBOL_MAP.update({dash: "-" for dash in "‐‑‒–—−―"})
_SYMBOL_MAP.update({quote: '"' for quote in "“”„«»″"})
_SYMBOL_MAP.update({quote: "'" for quote in "‘’‚′"})
_SYMBOL_MAP.update({bullet: "-" for bullet in "•▪●◦○"})
_SYMBOL_RE = re.compile("[" + re.escape("".join(_SYMBOL_MAP)) + "]")

# NORM §1.5.  Every unicode space variant that should behave like a blank.
_SPACE_CODEPOINTS = (
    [0x09, 0x20, 0xA0, 0x1680, 0x202F, 0x205F, 0x3000] +
    list(range(0x2000, 0x200B))
)
SPACE_RE = re.compile(
    "[" + "".join(chr(c) for c in _SPACE_CODEPOINTS) + "]+"
)

# Vietnamese single-letter words. Anything else that is one bare latin letter at
# the start of a wrapped line is a fragment of the word ending the line above.
_STANDALONE_ONE_CHAR = {"à", "ừ", "ở", "ô", "ê", "y", "ý",
                        "a", "e", "u", "o", "i"}

_VOWELS = set(
    "aàáảãạăằắẳẵặâầấẩẫậ"
    "eèéẻẽẹêềếểễệ"
    "iìíỉĩị"
    "oòóỏõọôồốổỗộơờớởỡợ"
    "uùúủũụưừứửữự"
    "yỳýỷỹỵ"
)


def _from_private_use(match: Match) -> str:
    """One private-use glyph, written as what the font actually drew (NORM §1.3).

    U+F020-U+F07E keeps the ASCII position of the character it replaced, so the
    code point can be read back -- but only for punctuation and digits.  The
    letter positions hold the Greek alphabet or a Wingdings ornament, and writing
    those out in Latin would put a word in the document that nobody wrote.
    """
    code = ord(match.group(0))
    if code in _PUA_EXCEPTIONS:
        return _PUA_EXCEPTIONS[code]
    if 0xF020 <= code <= 0xF07E:
        ascii_char = chr(code - 0xF000)
        return " " if ascii_char.isalpha() else ascii_char
    return " "


def normalize_text(value: str) -> str:
    """The five steps of NORM §1, in the order the spec states them.

    Invisible characters go first, NFKC folds the compatibility forms (a formula
    set in Equation Editor reaches us as "𝐌𝐢" and has to read as "Mi"), the
    private use area is resolved to what was drawn, symbols are written as their
    ASCII or their Vietnamese, and whitespace is unified last.

    Vietnamese tone marks, letter case, punctuation and "Đ/đ" are all left
    exactly as they were: this normalisation exists so the index can tokenise
    the text, not so anything can be matched against it.
    """
    if not value:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = INVISIBLE_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    text = _PUA_MARKER_RE.sub(r"\1-", text)
    text = PUA_RE.sub(_from_private_use, text)
    text = _SYMBOL_RE.sub(lambda m: _SYMBOL_MAP[m.group(0)], text)
    lines = [SPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


# An index the document wrote at the head of a line itself: "a)", "b.", "1)",
# "(a)", "6.1".  The punctuation is what makes it one -- a bare number opening a
# sentence ("03 tháng trước thời gian chuyển tiền") counts something, it does
# not index a list, and a line that starts with one still wants its bullet.
#
# A multi-level number needs no punctuation after it: "6.1" is already an index
# and nothing else, so a row opening with one must not be dashed as well ("-
# 6.1  |  Mục đích").  Components after the first are held to one or two digits
# that do not start with a zero, which is what keeps the "1.500.000" of an
# amount from reading as section 1.500.000 -- the same rule `outline` applies to
# the headings it reads out of the running text.
LINE_INDEX_RE = re.compile(
    r"^(?:\(\s*[0-9a-zA-Z]{1,3}\s*\)"
    r"|[0-9]{1,3}(?:\.[1-9][0-9]?)+\s*[.)]?"
    r"|[0-9]{1,3}\s*[.)]"
    r"|[a-zA-Z]\s*[.)])(?=\s|$)"
)

# The same marker, found inside a run of text rather than at the head of one.
_INLINE_INDEX_RE = re.compile(r"(?:^|(?<=[\s(]))([0-9a-zA-Z])\)(?=\s)")

# What an item marker follows when it opens one: the end of the sentence before
# it, or the colon of the line that introduces the list.
_SENTENCE_END = ".:;!?"


def _marker_candidates(text: str) -> List[Tuple[int, str]]:
    """Every ``x)`` in `text` that could be an item marker, and where it sits.

    A ``)`` that closes a bracket someone opened is not a marker, however much
    it looks like one: "(Bản gốc/Bản sao y)" ends in "y)" and indexes nothing.
    Tracking the depth is what tells the two apart -- with one exception, the
    bracket that wraps the marker itself and nothing else, "(1)".
    """
    depth_at: List[int] = []
    depth = 0
    for char in text:
        depth_at.append(depth)
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1

    found: List[Tuple[int, str]] = []
    for match in _INLINE_INDEX_RE.finditer(text):
        at = match.start(1)
        bracketed = at > 0 and text[at - 1] == "(" and depth_at[at - 1] == 0
        if depth_at[at] == 0 or bracketed:
            found.append((at, match.group(1)))
    return found


def _opens_a_sentence(text: str, at: int) -> bool:
    """Does the marker at `at` start a new sentence rather than sit inside one?

    "… quy định của LPBank từng thời kỳ. b) Quy định về giải tỏa …" opens one;
    the "a)" of a cross-reference ("theo điểm a) khoản 2") does not, and a
    reference is not an item however much the two look alike.
    """
    before = text[:at].rstrip()
    return not before or before[-1] in _SENTENCE_END


def is_bullet_line(line: str) -> bool:
    return bool(BULLET_PREFIX_RE.match(line))


def starts_with_index(line: str) -> bool:
    """Does this line already open with an index the document wrote itself?"""
    return bool(LINE_INDEX_RE.match((line or "").lstrip()))


def split_inline_items(text: str) -> List[str]:
    """Split a run of text at the item markers the document buried inside it.

    A table cell routinely holds a whole list in one paragraph -- "a) Sao kê …
    b) Hồ sơ … c) Lưu ý:" -- because the cell wrapped it rather than the author
    breaking it.  Read back as one line it is three items pretending to be a
    sentence: unreadable, and a chunker cutting it has no boundary to cut on.

    A marker has to earn the split twice over, because a wrong one breaks a
    sentence in half.  It must be a real marker and not a closing bracket (see
    :func:`_marker_candidates`), and then be one of:

    * a run that **ascends by one** -- "a) … b) … c)".  Two are enough, so a
      cell carrying a list on from the page before splits as well;
    * a lone marker that **opens a sentence** -- "… từng thời kỳ. b) Quy định
      …", where there is no sibling in this cell to ascend from.

    A marker that is neither is left alone: "theo điểm a) khoản 2" is a
    cross-reference, and cutting the sentence there would be a worse fault than
    the run-on it was meant to fix.
    """
    if not text:
        return []
    found = _marker_candidates(text)

    run: List[int] = []
    for start in range(len(found)):
        chain = [start]
        for nxt in range(start + 1, len(found)):
            here, there = found[chain[-1]][1], found[nxt][1]
            if here.isdigit() == there.isdigit() and ord(there) == ord(here) + 1:
                chain.append(nxt)
        if len(chain) > len(run):
            run = chain
    markers = set(run) if len(run) > 1 else set()
    markers |= {
        i for i, (at, _c) in enumerate(found) if _opens_a_sentence(text, at)
    }
    cuts = sorted(found[i][0] for i in markers)
    if not any(at > 0 for at in cuts):
        return [text]

    pieces: List[str] = []
    cut = 0
    for position in cuts:
        if position > cut:
            pieces.append(text[cut:position].strip())
            cut = position
    pieces.append(text[cut:].strip())
    return [p for p in pieces if p] or [text]


def bullet_marker(line: str) -> str:
    m = BULLET_PREFIX_RE.match(line)
    return m.group(1) if m else ""


def strip_bullet(line: str) -> str:
    return BULLET_PREFIX_RE.sub("", line, count=1).strip()


def _is_word_fragment(token: str) -> bool:
    """True when `token` cannot stand alone and therefore continues the previous line.

    Word processors wrap narrow table columns mid-word (``Khoả`` / ``n``).  Such a
    fragment is one or two lowercase letters that do not form a Vietnamese word
    on their own.
    """
    if not token or len(token) > 2:
        return False
    if not token.isalpha() or not token.islower():
        return False
    if token in _STANDALONE_ONE_CHAR:
        return False
    if len(token) == 1:
        return True
    # Two letters: a consonant cluster ("ng", "nh", "tr") is never a word.
    return not any(ch in _VOWELS for ch in token)


def join_wrapped_lines(lines: List[str]) -> str:
    """Rejoin visually wrapped lines of one paragraph back into a single string."""
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        first_token = line.split(" ", 1)[0]
        if _is_word_fragment(first_token) and out[-1].isalpha():
            out += line
        else:
            out += " " + line
    return out


def collapse_blank_lines(lines: List[str]) -> List[str]:
    """Drop leading/trailing blanks and never allow two blank lines in a row."""
    result: List[str] = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped.strip():
            if not result or not result[-1].strip():
                continue
            result.append("")
        else:
            result.append(stripped)
    while result and not result[-1].strip():
        result.pop()
    return result


def tokenize(text: str) -> List[str]:
    """Content tokens used for the loss-verification invariant."""
    text = unicodedata.normalize("NFC", text or "").lower()
    return re.findall(r"[^\W_]+", text, flags=re.UNICODE)
