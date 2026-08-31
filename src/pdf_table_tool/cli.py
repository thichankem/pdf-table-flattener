import argparse
import logging
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows so document names in any script print
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from .pipeline import (
    SUPPORTED_SUFFIXES,
    PDFTableFlattenerPipeline,
    output_name_for,
)

OUTPUT_DIR_NAME = "output_flattened"


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
    )


def _report(summary: dict) -> bool:
    print(f"  tables flattened   : {summary['total_tables_flattened']}")
    if "sheets_read_count" in summary:
        print(f"  sheets read        : {summary['sheets_read_count']}")
    if "pages_passthrough_count" in summary:
        print(f"  pages copied as-is : {summary['pages_passthrough_count']}")
    if summary.get("continuation_pages_added"):
        print(f"  pages appended     : {summary['continuation_pages_added']}")
    if summary.get("uncached_formulas"):
        print(
            "  WARNING: this workbook holds formulas Excel never evaluated. "
            "Those cells are empty in the source file, so they are empty in the\n"
            "           output too. Open the workbook in Excel and save it again "
            "to store the computed values."
        )
    report = summary.get("verification")
    if report is not None:
        print(report.describe())
    return summary.get("verification_passed", True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flatten every table in a PDF, Word or Excel document into "
        "bullet points. PDF and Word keep their own format; Excel comes back as Word."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="A PDF/DOCX/XLSX file, or a directory"
    )
    parser.add_argument("-o", "--output", help="Output file or directory")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip the self-check against the three acceptance criteria",
    )
    parser.add_argument(
        "--no-numbering",
        action="store_true",
        help="Do not number bullets after the document outline (1.1, 1.1.1); "
        "emit plain '-' bullets instead",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: '{args.input}' does not exist.")
        return 1

    pipeline = PDFTableFlattenerPipeline(
        verify_output=not args.no_verify, numbering=not args.no_numbering
    )

    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            print(f"Error: '{args.input}' is not a PDF, DOCX or XLSX file.")
            return 1
        # The output keeps the input's name with `_flattened` appended, and
        # without -o it lands in its own folder.  The extension changes only for
        # Excel, which comes back as Word.
        out_path = Path(args.output) if args.output else (
            input_path.parent / OUTPUT_DIR_NAME / output_name_for(str(input_path))
        )
        if out_path.resolve() == input_path.resolve():
            print("Error: the output file is the input file.")
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Processing: {input_path.name} -> {out_path}")
        return 0 if _report(pipeline.process(str(input_path), str(out_path))) else 2

    out_dir = Path(args.output) if args.output else input_path / OUTPUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        f
        for f in input_path.iterdir()
        if f.is_file()
        and f.suffix.lower() in SUPPORTED_SUFFIXES
        and not f.name.startswith("~$")
    )
    print(f"Found {len(files)} PDF/DOCX/XLSX file(s) in '{input_path}'")

    failures = 0
    for src_file in files:
        out_file = out_dir / output_name_for(str(src_file))
        print(f"\n{src_file.name}")
        try:
            if not _report(pipeline.process(str(src_file), str(out_file))):
                failures += 1
        except Exception as exc:
            failures += 1
            print(f"  ERROR: {exc}")
    return 0 if failures == 0 else 2
