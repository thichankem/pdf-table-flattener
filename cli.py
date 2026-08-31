"""Command-line entry point:  python cli.py -i <file-or-folder>

The implementation lives in :mod:`pdf_table_tool.cli`, so an installed copy of
the package exposes the very same interface as ``pdf-flattener`` or
``python -m pdf_table_tool``.  This shim only makes ``src/`` importable for a
plain checkout that was never pip-installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pdf_table_tool.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
