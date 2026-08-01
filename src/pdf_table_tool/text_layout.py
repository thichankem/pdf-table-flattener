"""Metric-accurate text wrapping for the PDF renderer.

``Page.insert_textbox`` silently refuses (or clips) when text overflows its
rectangle -- that is how whole paragraphs disappeared from the old output.  We
wrap and place lines ourselves so the caller always knows exactly how many lines
were drawn and what is left over.
"""

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import fitz


@dataclass
class PlacedLine:
    text: str
    indent: float
    source: int = 0
    """Index of the logical line this fragment came from.

    The renderer needs it to know exactly where to resume when only part of the
    text fits, so nothing can fall off the end unnoticed.
    """


def _hanging_indent(line: str) -> Tuple[float, str]:
    """Width (in characters) of the bullet prefix, so wraps align under the text."""
    stripped = line.lstrip(" ")
    lead = len(line) - len(stripped)
    marker_len = 0
    if len(stripped) > 1 and stripped[0] in "-+*" and stripped[1] == " ":
        marker_len = 2
    return lead + marker_len, stripped


def wrap_lines(
    lines: Sequence[str],
    font: fitz.Font,
    font_size: float,
    width: float,
    space_width_chars: float = 1.0,
) -> List[PlacedLine]:
    """Wrap logical lines to `width`, preserving indentation and hanging indents."""
    char_w = font.text_length("0", font_size) or (font_size * 0.5)
    out: List[PlacedLine] = []

    for source_idx, logical in enumerate(lines):
        if not logical.strip():
            out.append(PlacedLine("", 0.0, source_idx))
            continue

        prefix_chars, body_with_marker = _hanging_indent(logical)
        lead_spaces = len(logical) - len(logical.lstrip(" "))
        first_indent = lead_spaces * char_w * space_width_chars
        cont_indent = prefix_chars * char_w * space_width_chars
        content = logical.strip()

        words = content.split(" ")
        current = ""
        indent = first_indent
        avail = max(char_w * 4, width - indent)

        for word in words:
            candidate = word if not current else current + " " + word
            if font.text_length(candidate, font_size) <= avail or not current:
                current = candidate
                # A single word longer than the line must still be broken.
                while font.text_length(current, font_size) > avail and len(current) > 1:
                    cut = _fit_prefix(current, font, font_size, avail)
                    if cut <= 0 or cut >= len(current):
                        break
                    out.append(PlacedLine(current[:cut], indent, source_idx))
                    current = current[cut:]
                    indent = cont_indent
                    avail = max(char_w * 4, width - indent)
            else:
                out.append(PlacedLine(current, indent, source_idx))
                indent = cont_indent
                avail = max(char_w * 4, width - indent)
                current = word
        if current:
            out.append(PlacedLine(current, indent, source_idx))

    return out


def _fit_prefix(text: str, font: fitz.Font, size: float, avail: float) -> int:
    lo, hi = 1, len(text)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if font.text_length(text[:mid], size) <= avail:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def fit_plan(
    lines: Sequence[str],
    font: fitz.Font,
    width: float,
    height: float,
    sizes: Sequence[float],
    leading_ratio: float,
) -> Tuple[float, List[PlacedLine], int]:
    """Pick the largest font size whose wrapped text fits `height`.

    Returns ``(size, wrapped_lines, n_lines_that_fit)``.  When even the smallest
    size overflows, the caller is expected to spill the remainder elsewhere --
    `n_lines_that_fit` is then smaller than ``len(wrapped_lines)``.
    """
    for size in sizes:
        wrapped = wrap_lines(lines, font, size, width)
        needed = len(wrapped) * size * leading_ratio
        if needed <= height:
            return size, wrapped, len(wrapped)
    size = sizes[-1]
    wrapped = wrap_lines(lines, font, size, width)
    fits = max(0, int(height // (size * leading_ratio)))
    return size, wrapped, fits
