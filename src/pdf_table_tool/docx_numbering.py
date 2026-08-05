"""The numbers Word draws for itself.

A Word document usually does not write its section numbers into the text.  The
author ticks "numbered list", Word keeps a counter in ``numbering.xml`` and
paints "4." in front of the paragraph at display time -- so the paragraph that
reads "4. Chính sách ưu đãi" on screen reaches us as "Chính sách ưu đãi".

Without this module the outline has nothing to go on for such a document and
falls back to counting heading ranks, which invents a level the reader never
sees (1.4 where the document shows 4).  It matters beyond tidiness: these
documents are routinely handed over as PDF as well, and the PDF path reads the
number straight off the page.  Both formats have to produce the same number for
the same document.

Only decimal numbering is reported.  A bulleted list has no number, and a
lettered one ("a)", "i)") does not name a section on its own -- in both cases
the paragraph is left out of the outline instead of guessing.
"""

import logging
from typing import Dict, Optional, Set, Tuple

from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

Path = Tuple[int, ...]

# Formats that produce a section number.  Everything else -- bullets, letters,
# roman numerals -- numbers an item, not a section.
_DECIMAL_FORMATS = {"decimal", "decimalZero"}

MAX_LEVELS = 9


def _val(element, tag: str, default=None):
    if element is None:
        return default
    child = element.find(qn(tag))
    if child is None:
        return default
    value = child.get(qn("w:val"))
    return default if value is None else value


def _int_val(element, tag: str, default: int) -> int:
    try:
        return int(_val(element, tag, default))
    except (TypeError, ValueError):
        return default


class ListNumbering:
    """Replays Word's list counters over the paragraphs of a document.

    `advance` has to be called for **every** numbered paragraph in reading
    order, including the ones inside tables: they all move the same counters,
    and skipping them would leave every later section one number short.
    """

    def __init__(self, numbering_element=None):
        # abstractNumId -> ilvl -> (start, format)
        self._levels: Dict[str, Dict[int, Tuple[int, str]]] = {}
        # numId -> (abstractNumId, ilvl -> startOverride)
        self._lists: Dict[str, Tuple[str, Dict[int, int]]] = {}
        self._counts: Dict[Tuple[str, int], int] = {}
        self._overridden: Set[str] = set()

        if numbering_element is None:
            return
        for abstract in numbering_element.findall(qn("w:abstractNum")):
            abstract_id = abstract.get(qn("w:abstractNumId"))
            if abstract_id is None:
                continue
            levels: Dict[int, Tuple[int, str]] = {}
            for level in abstract.findall(qn("w:lvl")):
                try:
                    ilvl = int(level.get(qn("w:ilvl")))
                except (TypeError, ValueError):
                    continue
                levels[ilvl] = (
                    _int_val(level, "w:start", 1),
                    _val(level, "w:numFmt", "decimal"),
                )
            self._levels[abstract_id] = levels

        for num in numbering_element.findall(qn("w:num")):
            num_id = num.get(qn("w:numId"))
            abstract_id = _val(num, "w:abstractNumId")
            if num_id is None or abstract_id is None:
                continue
            overrides: Dict[int, int] = {}
            for override in num.findall(qn("w:lvlOverride")):
                try:
                    ilvl = int(override.get(qn("w:ilvl")))
                except (TypeError, ValueError):
                    continue
                start = override.find(qn("w:startOverride"))
                if start is not None:
                    try:
                        overrides[ilvl] = int(start.get(qn("w:val")))
                    except (TypeError, ValueError):
                        continue
            self._lists[num_id] = (abstract_id, overrides)

    # -- reading a paragraph ---------------------------------------------
    @staticmethod
    def reference(p_pr) -> Optional[Tuple[Optional[str], Optional[int]]]:
        """What one ``w:pPr`` block says about its numbering.

        Either half may be missing: a paragraph often states only the level and
        leaves the list to its style ("List Number", "Heading 1"), which is why
        this is read from a paragraph *and* from a style definition.
        """
        if p_pr is None:
            return None
        num_pr = p_pr.find(qn("w:numPr"))
        if num_pr is None:
            return None
        num_id = _val(num_pr, "w:numId")
        ilvl = _val(num_pr, "w:ilvl")
        return num_id, (None if ilvl is None else _int_val(num_pr, "w:ilvl", 0))

    def advance(
        self, p, style_reference: Optional[Tuple[str, int]] = None
    ) -> Optional[Path]:
        """Count this paragraph in, and return the number Word shows for it.

        `style_reference` is the numbering its paragraph style carries, which is
        where a document using the built-in list and heading styles keeps it.

        None when the paragraph is not numbered, when its list is not decimal
        all the way up, or when the list is not one this document defines.
        """
        direct = self.reference(p.find(qn("w:pPr")))
        if direct is None and style_reference is None:
            return None
        num_id, ilvl = direct if direct is not None else (None, None)
        if num_id is None and style_reference is not None:
            num_id = style_reference[0]
            if ilvl is None:
                ilvl = style_reference[1]
        if num_id in (None, "0"):  # 0 is Word's way of removing the numbering
            return None
        ilvl = 0 if ilvl is None else ilvl
        entry = self._lists.get(num_id)
        if entry is None:
            return None
        abstract_id, overrides = entry
        levels = self._levels.get(abstract_id)
        if levels is None:
            return None

        if num_id not in self._overridden:
            # A restarted list is a fresh `w:num` pointing at the same
            # definition; the override is what says where it starts again.
            self._overridden.add(num_id)
            for level, start in overrides.items():
                self._counts[(abstract_id, level)] = start - 1

        ilvl = max(0, min(ilvl, MAX_LEVELS - 1))
        self._counts[(abstract_id, ilvl)] = (
            self._counts.get((abstract_id, ilvl), self._start(levels, ilvl) - 1) + 1
        )
        # A level restarts every time one above it moves on.
        for deeper in range(ilvl + 1, MAX_LEVELS):
            self._counts.pop((abstract_id, deeper), None)

        if any(
            self._format(levels, level) not in _DECIMAL_FORMATS
            for level in range(ilvl + 1)
        ):
            return None
        return tuple(
            self._counts.get((abstract_id, level), self._start(levels, level))
            for level in range(ilvl + 1)
        )

    @staticmethod
    def _start(levels: Dict[int, Tuple[int, str]], ilvl: int) -> int:
        return levels.get(ilvl, (1, "decimal"))[0]

    @staticmethod
    def _format(levels: Dict[int, Tuple[int, str]], ilvl: int) -> str:
        return levels.get(ilvl, (1, "decimal"))[1]


def numbering_of(document) -> ListNumbering:
    """The list definitions of a document, or an empty set when it has none.

    A document that never numbered anything has no ``numbering.xml`` at all,
    and python-docx reports that in more than one way depending on version --
    hence the wide net.
    """
    try:
        element = document.part.numbering_part.element
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Document has no numbering definitions: %s", exc)
        return ListNumbering()
    return ListNumbering(element)
