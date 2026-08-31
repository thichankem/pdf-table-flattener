<h1 align="center">PDF Table Flattener</h1>

<p align="center">
  Turn every table in a <b>PDF</b>, <b>Word</b> or <b>Excel</b> document into flat,
  self-describing bullet lines — and leave everything else on the page untouched.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey">
  <img alt="No AI" src="https://img.shields.io/badge/AI-none%2C%20fully%20deterministic-orange">
</p>

---

## Why

Retrieval-augmented generation chokes on tables. A chunker slices a document into
fixed-size windows; a table cut in half loses its header row, and every cell in the
second half becomes an orphan number with no idea what it measures. Layout-aware
parsers help, but they still hand the index a grid — and a grid does not survive
being turned into a flat token stream.

This tool removes the problem at the source. Each table row is rewritten as one
line that repeats its own column headers, so the line still means something after
it has been separated from everything around it:

**Before** — a table on page 4:

| Tier | Balance | Rate |
|------|---------|------|
| 1    | under 100M | 3.1% |
| 2    | 100M – 500M | 3.6% |

**After** — the same page, table replaced in place:

```text
10.1.1 Tier: 1  |  Balance: under 100M  |  Rate: 3.1%
10.1.2 Tier: 2  |  Balance: 100M - 500M  |  Rate: 3.6%
```

The `10.1.x` prefix is the document's *own* outline — the table sits under
section 10.1 — so a chunk that starts in the middle of a twelve-page table still
carries a breadcrumb back to where it came from.

Everything that is not a table — headings, paragraphs, logos, footnotes, images,
page numbers — is byte-identical to the input.

## Features

- **Three formats, one output shape.** PDF, Word (`.docx`) and Excel
  (`.xlsx`/`.xlsm`) all feed the same formatter, so identical tables produce
  identical bullets.
- **Format preserved.** A PDF comes back as a PDF and a Word file as a Word file,
  patched in place. Only the table rectangle is redacted and redrawn — the rest of
  the page is never re-typeset. (Excel has no page layout to preserve, so a
  workbook comes back as Word.)
- **Nothing is dropped.** Extraction is geometry-driven: every word inside a table
  is assigned to exactly one cell, and a word that falls between cells is attached
  to the nearest one rather than discarded.
- **Borderless tables too.** Tables aligned by whitespace instead of ruled lines
  are found by looking for column gutters that survive across consecutive lines —
  without mistaking ordinary prose for a table.
- **Outline numbering for RAG.** Bullets inherit the document's heading hierarchy
  (`1.1`, `1.1.1`) so each line is independently addressable. Switchable off.
- **Self-verifying.** Every run checks its own output against three acceptance
  criteria and reports pass/fail per document.
- **No AI, no network, no API keys.** Pure deterministic parsing. The same input
  always produces the same output, and nothing leaves the machine.
- **Runs anywhere.** GUI with drag-and-drop, a CLI, or an importable library, on
  Windows, macOS and Linux.

## The acceptance contract

Every run is graded against three rules. They are the whole specification of the
tool, and `pdf_table_tool/verifier.py` enforces them automatically on its own
output:

| # | Criterion | Checked by |
|---|-----------|-----------|
| 1 | **Non-table content is untouched.** Text, headings, images and diagrams outside a table survive exactly as they were. | Token-level diff between input and output |
| 2 | **Every table is flattened.** No table structure remains anywhere in the result, and no cell text is lost. | Table re-detection on the output |
| 3 | **The output is clean.** No stray or invisible characters, no invented column labels (`Column 1:`, `Field 2:`), never more than one blank line in a row. | Pattern scan of the rendered text |

A failing criterion is reported per file and sets a non-zero exit code; it does
not silently produce a mangled document.

## Install

### For end users — no Python required

Download or clone the project, then double-click the launcher for your system:

| OS | Launcher |
|----|----------|
| Windows | `START_Windows.bat` |
| macOS | `START_macOS.command` |
| Linux | `START_Linux.sh` |

The first run creates a private `.venv`, installs the dependencies and downloads
the bundled Noto fonts; it needs an Internet connection and happens exactly once.
If the machine has no suitable Python at all, the launcher fetches a private
Python 3.12 for the app rather than touching the system installation. Later runs
open the GUI immediately and work offline.

On Windows, `python create_desktop_shortcut.py` adds a desktop shortcut. On Linux
the launcher installs an application-menu entry by itself.

### For developers

```bash
git clone https://github.com/thichankem/pdf-table-flattener.git
cd pdf-table-flattener
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[gui,dev]"
```

Requires Python 3.10+. Runtime dependencies are PyMuPDF, pdfplumber, python-docx
and openpyxl; `tkinterdnd2` is optional and only adds drag-and-drop to the GUI.

## Usage

### GUI

```bash
python launch_gui.py
```

Drop files or a folder onto the window, tick or untick outline numbering, press
**Flatten Tables**. Results land in `output_flattened/` next to the app (or in
your Documents folder if the app itself lives somewhere read-only).

### Command line

```bash
# one file -> output_flattened/<name>_flattened.pdf
python cli.py -i report.pdf

# a whole folder, to a folder of your choice
python cli.py -i ./documents -o ./flattened

# plain "-" bullets instead of outline numbering
python cli.py -i report.docx --no-numbering

# skip the self-check (faster on large batches)
python cli.py -i report.pdf --no-verify
```

After `pip install`, the same interface is available as `pdf-flattener` or
`python -m pdf_table_tool`. Exit codes: `0` success, `1` bad input, `2` a file
failed or failed verification.

### As a library

```python
from pdf_table_tool.pipeline import PDFTableFlattenerPipeline

pipeline = PDFTableFlattenerPipeline(numbering=True, verify_output=True)
summary = pipeline.process("report.pdf", "report_flattened.pdf")

print(summary["total_tables_flattened"], summary["verification_passed"])
```

`process()` accepts `.pdf`, `.docx`, `.xlsx` and `.xlsm`. Excel input is always
written back as `.docx` — the extension is corrected for you, so no caller can
produce a `.xlsx` that secretly holds a Word document.

## How it works

```
                 ┌───────────┐
   .pdf ────────►│  detect   │  ruled tables (pdfplumber) + borderless tables
                 │  tables   │  (column-gutter analysis); nested tables dropped
                 └─────┬─────┘
                       │
                 ┌─────▼─────┐
   .docx ───────►│  extract  │  every word assigned to exactly one cell;
   (states its   │   grid    │  spans read from w:gridSpan / w:vMerge
    own layout)  └─────┬─────┘
                       │
                 ┌─────▼─────┐
   .xlsx ───────►│  format   │  header inference, rowspan groups, list
   (already a    │  bullets  │  markers, number/percent formatting
    grid)        └─────┬─────┘
                       │
                 ┌─────▼─────┐
                 │  number   │  place each row on the document's outline
                 │ (outline) │  (1.1 -> 1.1.1, 1.1.2, ...)
                 └─────┬─────┘
                       │
                 ┌─────▼─────┐
                 │  render   │  redact only the table rectangle and draw the
                 │  in place │  bullets there; overflow continues on a new page
                 └─────┬─────┘
                       │
                 ┌─────▼─────┐
                 │  verify   │  the three acceptance criteria, on the result
                 └───────────┘
```

Three details are worth calling out, because they are where naive
implementations lose text:

**Nested tables are dropped, not extracted.** Word and most PDF generators draw a
bullet list inside a cell using its own ruling lines, which the detector reports as
a second table living inside the real one. Flattening the inner table first would
lose the outer table's text entirely.

**Extraction never re-runs cell detection.** `pdfplumber.Table.extract()` re-derives
its own cells and drops text that lands between them. This project takes the cell
rectangles that were already found and assigns every word to one of them.

**Text is wrapped by measured metrics, not by the PDF library.**
`Page.insert_textbox` silently clips text that does not fit, which is how whole
paragraphs vanish. Lines are wrapped and placed here, so the renderer always knows
how many lines it drew and what is left over — the remainder continues on an
appended page instead of disappearing.

Text normalisation (NORM §1) runs over everything: soft hyphens and zero-width
characters removed, Symbol/Wingdings private-use glyphs resolved back to the
characters they draw, mathematical alphanumerics folded to ASCII, `≥ ≠ ± …`
spelt out, and every Unicode space variant collapsed to a plain blank.

## Project layout

```
pdf-table-flattener/
├── cli.py                       # command-line entry point (thin shim)
├── gui.py, launch_gui.py        # Tkinter GUI and its launcher
├── START_Windows.bat            # zero-setup launchers, one per OS
├── START_macOS.command
├── START_Linux.sh
├── src/pdf_table_tool/
│   ├── pipeline.py              # orchestration: detect → extract → flatten → render → verify
│   ├── table_detector.py        # table discovery; drops nested tables
│   ├── borderless.py            # whitespace-aligned tables via column gutters
│   ├── grid_extractor.py        # lossless, geometry-driven cell assignment
│   ├── formatter.py             # the shared heart: Grid → bullet lines
│   ├── outline.py               # document outline; hierarchical numbering for RAG
│   ├── pdf_patcher.py           # redact the table rect, draw bullets in place
│   ├── text_layout.py           # metric-accurate wrapping, no silent clipping
│   ├── text_utils.py            # text normalisation (NORM §1)
│   ├── docx_flattener.py        # Word path, in place
│   ├── docx_numbering.py        # the numbers Word draws but never writes down
│   ├── xlsx_flattener.py        # Excel path, out as Word
│   ├── verifier.py              # the three acceptance criteria
│   ├── config.py                # fonts and typography
│   └── platform_support.py      # the few genuine OS differences
├── tests/                       # 190+ unit and end-to-end tests
└── tools/
    ├── bootstrap.py             # first-run setup shared by all three launchers
    ├── posix_launch.sh          # shared macOS/Linux launcher body
    └── build_zip.py             # build the distributable archive
```

## Development

```bash
pytest                     # full suite
pytest tests/test_units.py # one module
```

The end-to-end tests in `tests/test_flattener.py` run against real documents and
skip themselves when none are present. To enable them, drop a few PDFs into an
`input test/` folder at the repository root; that folder is git-ignored, so private
documents stay private.

To build a self-contained archive for someone who will never open a terminal:

```bash
python tools/build_zip.py
```

This produces `dist/PDF-Table-Flattener-<version>.zip`. Unzipped anywhere on any
of the three systems, its `START_*` launcher does the rest — including preserving
the executable bit, without which macOS refuses to run the launcher at all.

## Limitations

- **Scanned PDFs are not supported.** There is no OCR; a table that exists only as
  pixels is invisible to the detector and passes through untouched.
- **Excel becomes Word.** A bullet list is not a grid, so there is no meaningful
  way to write the result back into a spreadsheet.
- **Unevaluated Excel formulas come out empty.** A formula whose result was never
  cached by Excel is empty in the source file too. Open the workbook in Excel and
  save it again to store the computed values.
- **Very complex nested layouts** — a table whose cells hold further tables several
  levels deep — flatten to the outermost table only.

## License

MIT. See [LICENSE](LICENSE).
