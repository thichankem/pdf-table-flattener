import argparse
import sys
import os
import logging
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows for printing Vietnamese characters
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from src.pdf_table_tool.pipeline import PDFTableFlattenerPipeline

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
        datefmt="%H:%M:%S"
    )

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="PDF Table → Bullet Flattener Tool (v5)")
    parser.add_argument("-i", "--input", required=True, help="Input PDF file path or directory")
    parser.add_argument("-o", "--output", help="Output PDF file path or directory")
    parser.add_argument("--no-ollama", action="store_true", help="Disable Ollama LLM bootstrap check")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input path '{args.input}' does not exist.")
        sys.exit(1)

    pipeline = PDFTableFlattenerPipeline(check_ollama=not args.no_ollama)

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            print(f"Error: File '{args.input}' is not a PDF.")
            sys.exit(1)

        out_path = args.output
        if not out_path:
            out_path = str(input_path.parent / f"{input_path.stem}_flattened.pdf")

        print(f"Processing PDF: {input_path} -> {out_path}")
        summary = pipeline.process(str(input_path), out_path)
        print("\n--- Processing Summary ---")
        for k, v in summary.items():
            print(f"  {k}: {v}")

    elif input_path.is_dir():
        out_dir = Path(args.output) if args.output else input_path / "output_flattened"
        out_dir.mkdir(parents=True, exist_ok=True)

        pdf_files = list(input_path.glob("*.pdf"))
        print(f"Found {len(pdf_files)} PDF file(s) in directory '{input_path}'")

        for pdf_file in pdf_files:
            out_file = out_dir / f"{pdf_file.stem}_flattened.pdf"
            print(f"\nProcessing: {pdf_file.name} -> {out_file.name}")
            try:
                summary = pipeline.process(str(pdf_file), str(out_file))
                print(f"  -> Success: Flattened {summary['total_tables_flattened']} table(s) on {summary['pages_patched_count']} page(s).")
            except Exception as e:
                print(f"  -> Failed: {e}")

if __name__ == "__main__":
    main()
