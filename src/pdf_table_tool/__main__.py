"""``python -m pdf_table_tool`` runs the command-line interface."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
