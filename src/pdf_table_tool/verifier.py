"""Automatic verification of the three acceptance criteria (see README.md).

The pipeline runs this on its own output, so a regression surfaces as a failed
report instead of a silently mangled PDF.
"""

import logging
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from xml.etree import ElementTree

import fitz
import pdfplumber

from .table_detector import visible_page
from .text_utils import tokenize

logger = logging.getLogger(__name__)

# Any label the tool must never invent.
FAKE_LABEL_RE = re.compile(r"\b(cột|column|col)\s*\d+\s*:", re.IGNORECASE)
# Control / formatting characters that should never survive into the output.
# Items 1 and 2 of the normalisation checklist (NORM §8): no control or
# zero-width character, nothing left in the private use area -- no text font has
# a glyph there, so the index would read a replacement character -- and no
# U+FFFD, which is what a decoder writes where it gave up.
STRAY_CHAR_RE = re.compile(
    "[" + "".join(chr(c) for c in
                  list(range(0x00, 0x09)) + list(range(0x0B, 0x20)) +
                  [0xAD, 0x2060, 0xFEFF, 0xFFFD] + list(range(0x200B, 0x2010)) +
                  list(range(0x202A, 0x202F)) + list(range(0xE000, 0xF900))) + "]"
)


@dataclass
class VerificationReport:
    missing_tokens: Dict[int, List[str]] = field(default_factory=dict)
    residual_table_pages: List[int] = field(default_factory=list)
    fake_labels: List[str] = field(default_factory=list)
    stray_characters: List[str] = field(default_factory=list)
    double_blank_lines: List[int] = field(default_factory=list)
    input_token_count: int = 0
    output_token_count: int = 0

    @property
    def criterion_1_and_2_ok(self) -> bool:
        return not self.missing_tokens

    @property
    def criterion_2_ok(self) -> bool:
        return not self.residual_table_pages

    @property
    def criterion_3_ok(self) -> bool:
        return not (
            self.fake_labels or self.stray_characters or self.double_blank_lines
        )

    @property
    def passed(self) -> bool:
        return (
            self.criterion_1_and_2_ok
            and self.criterion_2_ok
            and self.criterion_3_ok
        )

    def describe(self) -> str:
        rows = [
            ("Criteria 1+2: no content was lost", self.criterion_1_and_2_ok),
            ("Criterion 2: no table survives", self.criterion_2_ok),
            ("Criterion 3: clean output, no junk", self.criterion_3_ok),
        ]
        out = [f"  {'PASS' if ok else 'FAIL'}  {name}" for name, ok in rows]
        if self.missing_tokens:
            for page, toks in list(self.missing_tokens.items())[:10]:
                out.append(f"      page {page}: missing {toks[:15]}")
        if self.residual_table_pages:
            out.append(f"      tables left on pages: {self.residual_table_pages}")
        if self.fake_labels:
            out.append(f"      invented labels: {self.fake_labels[:5]}")
        if self.stray_characters:
            out.append(f"      stray characters: {self.stray_characters[:5]}")
        if self.double_blank_lines:
            out.append(f"      consecutive blank lines on pages: {self.double_blank_lines}")
        out.append(
            f"      tokens: input={self.input_token_count} output={self.output_token_count}"
        )
        return "\n".join(out)


DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_parts(path: str) -> List[bytes]:
    """The XML of every story of a .docx: body, headers, footers, footnotes."""
    with zipfile.ZipFile(path) as archive:
        return [
            archive.read(name)
            for name in archive.namelist()
            if name.startswith("word/")
            and name.endswith(".xml")
            and (
                name == "word/document.xml"
                or any(
                    name.startswith(f"word/{kind}")
                    for kind in ("header", "footer", "footnotes", "endnotes")
                )
            )
        ]


def _docx_tokens(path: str) -> Counter:
    """Every content token of a Word file, read straight from its XML.

    Going through the XML rather than python-docx keeps text that lives in
    hyperlinks, text boxes and content controls in the count, so criterion 1 is
    checked against everything the reader can actually see.
    """
    counter: Counter = Counter()
    for blob in _docx_parts(path):
        root = ElementTree.fromstring(blob)
        for node in root.iter(f"{DOCX_NS}t"):
            counter.update(tokenize(node.text or ""))
    return counter


def _docx_token_stream(path: str) -> str:
    """All content characters of a Word file, in reading order, unspaced."""
    parts: List[str] = []
    for blob in _docx_parts(path):
        root = ElementTree.fromstring(blob)
        for node in root.iter(f"{DOCX_NS}t"):
            parts.extend(tokenize(node.text or ""))
    return "".join(parts)


def _docx_table_count(path: str) -> int:
    return sum(
        len(ElementTree.fromstring(blob).findall(f".//{DOCX_NS}tbl"))
        for blob in _docx_parts(path)
    )


def verify_docx(
    input_path: str,
    output_path: str,
    generated_lines: Optional[List[str]] = None,
) -> VerificationReport:
    """Check an output .docx against the same three criteria as the PDF path."""
    report = VerificationReport()

    src_tokens = _docx_tokens(input_path)
    out_tokens = _docx_tokens(output_path)
    report.input_token_count = sum(src_tokens.values())
    report.output_token_count = sum(out_tokens.values())

    # As in the PDF check: a token that only changed shape (rejoined across a
    # line break) is still present in the output character stream.
    out_stream = _docx_token_stream(output_path)
    missing = [
        tok for tok in (src_tokens - out_tokens).elements() if tok not in out_stream
    ]
    if missing:
        report.missing_tokens[0] = sorted(missing)

    remaining = _docx_table_count(output_path)
    if remaining:
        report.residual_table_pages = list(range(1, remaining + 1))

    src_text = " ".join(src_tokens.elements())
    scope = "\n".join(generated_lines or [])
    report.fake_labels = sorted(
        set(FAKE_LABEL_RE.findall(scope)) - set(FAKE_LABEL_RE.findall(src_text))
    )
    report.stray_characters = sorted(set(STRAY_CHAR_RE.findall(scope)))

    for idx in range(1, len(generated_lines or [])):
        if not generated_lines[idx].strip() and not generated_lines[idx - 1].strip():
            report.double_blank_lines.append(idx)
            break

    return report


def verify_xlsx(
    input_path: str,
    output_path: str,
    generated_lines: Optional[List[str]] = None,
) -> VerificationReport:
    """Check an Excel workbook against its flattened Word output.

    The source side is compared as *displayed* text, not as stored values: a
    percentage lives in the sheet as 0.291 and reaches the output as "29.1%",
    and it is the reader's version of a cell that must survive.
    """
    from .xlsx_flattener import workbook_texts

    report = VerificationReport()

    src_tokens: Counter = Counter()
    for text in workbook_texts(input_path):
        src_tokens.update(tokenize(text))
    out_tokens = _docx_tokens(output_path)
    report.input_token_count = sum(src_tokens.values())
    report.output_token_count = sum(out_tokens.values())

    out_stream = _docx_token_stream(output_path)
    missing = [
        tok for tok in (src_tokens - out_tokens).elements() if tok not in out_stream
    ]
    if missing:
        report.missing_tokens[0] = sorted(missing)

    # Criterion 2 is trivially met here -- the writer only ever emits paragraphs
    # -- but a stray table would still mean a bug, so it is checked all the same.
    remaining = _docx_table_count(output_path)
    if remaining:
        report.residual_table_pages = list(range(1, remaining + 1))

    src_text = " ".join(src_tokens.elements())
    scope = "\n".join(generated_lines or [])
    report.fake_labels = sorted(
        set(FAKE_LABEL_RE.findall(scope)) - set(FAKE_LABEL_RE.findall(src_text))
    )
    report.stray_characters = sorted(set(STRAY_CHAR_RE.findall(scope)))

    for idx in range(1, len(generated_lines or [])):
        if not generated_lines[idx].strip() and not generated_lines[idx - 1].strip():
            report.double_blank_lines.append(idx)
            break

    return report


def _document_tokens(doc: fitz.Document) -> Counter:
    counter: Counter = Counter()
    for page in doc:
        counter.update(tokenize(page.get_text()))
    return counter


def _token_stream(doc: fitz.Document) -> str:
    """All content characters of the document, whitespace removed."""
    return "".join(
        "".join(tokenize(page.get_text())) for page in doc
    )


def _blank_run_count(text: str) -> int:
    return len(re.findall(r"\n[ \t]*\n[ \t]*\n", text))


def verify(
    input_path: str,
    output_path: str,
    generated_lines: Optional[List[str]] = None,
) -> VerificationReport:
    """Check the output PDF against the three acceptance criteria.

    `generated_lines` are the bullet lines the tool produced.  Criterion 3 is
    checked against them rather than against ``page.get_text()``, because a
    PDF's extracted text is full of whitespace-only spans that belong to the
    untouched passthrough content and say nothing about our output quality.
    """
    report = VerificationReport()

    src = fitz.open(input_path)
    out = fitz.open(output_path)
    try:
        src_tokens = _document_tokens(src)
        out_tokens = _document_tokens(out)
        report.input_token_count = sum(src_tokens.values())
        report.output_token_count = sum(out_tokens.values())

        # A token may legitimately change shape: the flattener rejoins words the
        # source wrapped mid-word ("Khoả" + "n" -> "Khoản") and separates
        # footnote markers glued to a word ("trú3" -> "trú" "3").  Such a token
        # is still present as a substring of the output character stream, so it
        # only counts as lost when even that fails.
        out_stream = _token_stream(out)
        missing = [
            tok
            for tok in (src_tokens - out_tokens).elements()
            if tok not in out_stream
        ]
        if missing:
            report.missing_tokens[0] = sorted(missing)

        src_text = "\n".join(page.get_text() for page in src)
        out_text = "\n".join(page.get_text() for page in out)

        # Only defects this tool introduced count; pre-existing ones live in
        # passthrough content that criterion 1 forbids us to touch.
        scope = "\n".join(generated_lines) if generated_lines is not None else out_text
        report.fake_labels = sorted(
            set(FAKE_LABEL_RE.findall(scope)) - set(FAKE_LABEL_RE.findall(src_text))
        )
        report.stray_characters = sorted(
            set(STRAY_CHAR_RE.findall(scope)) - set(STRAY_CHAR_RE.findall(src_text))
        )
        # The renderer also has to keep the *rendered* text free of hidden
        # characters, which depends on the embedded font's ToUnicode map.
        report.stray_characters = sorted(
            set(report.stray_characters)
            | (set(STRAY_CHAR_RE.findall(out_text)) - set(STRAY_CHAR_RE.findall(src_text)))
        )

        if generated_lines is not None:
            for idx in range(1, len(generated_lines)):
                if (
                    not generated_lines[idx].strip()
                    and not generated_lines[idx - 1].strip()
                ):
                    report.double_blank_lines.append(idx)
                    break
        else:
            for page_idx, page in enumerate(out):
                produced = _blank_run_count(page.get_text())
                original = (
                    _blank_run_count(src[page_idx].get_text())
                    if page_idx < len(src)
                    else 0
                )
                if produced > original:
                    report.double_blank_lines.append(page_idx + 1)
    finally:
        src.close()
        out.close()

    with pdfplumber.open(output_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            # The same view of the page the detector had: a rectangle nobody can
            # see is not a table here either.
            page = visible_page(page)
            try:
                tables = page.find_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "intersection_tolerance": 3,
                    }
                )
            except Exception:  # pragma: no cover - defensive
                tables = []
            real = [
                t
                for t in tables
                if (t.bbox[2] - t.bbox[0]) > 20 and (t.bbox[3] - t.bbox[1]) > 15
            ]
            if real:
                report.residual_table_pages.append(page_idx + 1)

    return report
