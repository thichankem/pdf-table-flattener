"""Shared text normalisation helpers.

Everything here is deliberately conservative: the pipeline guarantees that no
word from the source PDF is ever dropped, so these helpers only ever *join* or
*clean* whitespace, never remove visible characters.
"""

import re
import unicodedata
from typing import List

# Bullet glyphs that may introduce a list item inside a table cell.
BULLET_PREFIX_RE = re.compile(r"^\s*([-‐-―•●○▪·+*o])\s+")

# Characters that carry no visible content but pollute extracted text.
_INVISIBLE_CODEPOINTS = (
    list(range(0x00, 0x09)) + list(range(0x0B, 0x20)) +
    [0x2060, 0xFEFF] + list(range(0x200B, 0x2010)) +
    list(range(0x202A, 0x202F))
)
INVISIBLE_RE = re.compile(
    "[" + "".join(chr(c) for c in _INVISIBLE_CODEPOINTS) + "]"
)

# Every unicode space variant that should behave like a plain blank.
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


def normalize_text(value: str) -> str:
    """NFC-normalise, strip invisible characters, unify whitespace inside each line."""
    if not value:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    # A soft hyphen is usually invisible, but a PDF that draws one means it as a
    # hyphen -- deleting it would silently drop a visible character.
    text = text.replace("­", "-")
    text = INVISIBLE_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [SPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


def is_bullet_line(line: str) -> bool:
    return bool(BULLET_PREFIX_RE.match(line))


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
