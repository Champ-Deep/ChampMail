"""
Backwards-compatibility shim.

All logic now lives in file_parser.py which supports both CSV and XLSX.
This module re-exports the old names so ``from app.utils.csv_parser import ...``
continues to work without changes.
"""

from app.utils.file_parser import (  # noqa: F401
    ProspectFileParser as ProspectCSVParser,
    FileValidationError as CSVValidationError,
)
