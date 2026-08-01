import argparse
import logging
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows for printing Vietnamese characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.pdf_table_tool.pipeline import SUPPORTED_SUFFIXES, PDFTableFlattenerPipeline

OUTPUT_DIR_NAME = "output_flattened"


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
    )


def _report(summary: dict) -> bool:
    print(f"  bảng đã làm phẳng : {summary['total_tables_flattened']}")
    if "pages_passthrough_count" in summary:
        print(f"  trang giữ nguyên  : {summary['pages_passthrough_count']}")
    if summary.get("continuation_pages_added"):
        print(f"  trang bổ sung     : {summary['continuation_pages_added']}")
    report = summary.get("verification")
    if report is not None:
        print(report.describe())
    return summary.get("verification_passed", True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Làm phẳng mọi bảng trong PDF hoặc Word thành gạch đầu dòng."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="File PDF/DOCX hoặc thư mục"
    )
    parser.add_argument("-o", "--output", help="File hoặc thư mục đầu ra")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Dùng LLM (Ollama) để đoán cấu trúc bảng (dòng tiêu đề / cột nhãn) "
        "và tinh chỉnh câu chữ. LLM không sinh nội dung: câu trả lời bị bỏ nếu "
        "sai định dạng, làm mất hoặc thêm bất kỳ từ nào.",
    )
    parser.add_argument(
        "--no-verify", action="store_true", help="Bỏ qua bước tự kiểm tra 3 tiêu chí"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Lỗi: không tìm thấy '{args.input}'.")
        return 1

    pipeline = PDFTableFlattenerPipeline(
        use_llm=args.llm, verify_output=not args.no_verify
    )

    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            print(f"Lỗi: '{args.input}' không phải file PDF hoặc DOCX.")
            return 1
        # The output keeps the input's name, so without -o it has to land in its
        # own folder -- writing next to the input would overwrite it.
        out_path = Path(args.output) if args.output else (
            input_path.parent / OUTPUT_DIR_NAME / input_path.name
        )
        if out_path.resolve() == input_path.resolve():
            print("Lỗi: file đầu ra trùng với file đầu vào.")
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Đang xử lý: {input_path.name} -> {out_path}")
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
    print(f"Tìm thấy {len(files)} file PDF/DOCX trong '{input_path}'")

    failures = 0
    for src_file in files:
        out_file = out_dir / src_file.name
        print(f"\n{src_file.name}")
        try:
            if not _report(pipeline.process(str(src_file), str(out_file))):
                failures += 1
        except Exception as exc:
            failures += 1
            print(f"  LỖI: {exc}")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
