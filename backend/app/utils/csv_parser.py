"""
CSV parser utility for prospect list uploads.
Validates and parses CSV files with comprehensive error handling.
"""

import csv
import io
import re
from typing import Dict, List, Tuple
from fastapi import UploadFile
import hashlib


class CSVValidationError(Exception):
    """Custom exception for CSV validation errors."""
    pass


class ProspectCSVParser:
    """Parser for prospect CSV files with validation."""

    # Required headers
    REQUIRED_HEADERS = ["email"]

    # Optional headers
    OPTIONAL_HEADERS = [
        "first_name",
        "last_name",
        "company_name",
        "company_domain",
        "title",
        "phone",
        "linkedin_url",
        "industry",
        "company_size"
    ]

    # Allowed headers (required + optional)
    ALLOWED_HEADERS = REQUIRED_HEADERS + OPTIONAL_HEADERS

    # Size limits
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_ROWS = 100000  # Maximum prospects per file

    # Email validation regex
    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    @staticmethod
    def _validate_email(email: str) -> bool:
        """Validate email format."""
        if not email or not isinstance(email, str):
            return False
        return bool(ProspectCSVParser.EMAIL_REGEX.match(email.strip()))

    @staticmethod
    def _clean_value(value: str) -> str:
        """Clean and trim CSV value."""
        if not value:
            return ""
        return value.strip()

    @staticmethod
    async def validate_file(file: UploadFile) -> Dict:
        """
        Validate CSV file before processing.

        Args:
            file: UploadFile from FastAPI

        Returns:
            Dict with validation results: {valid: bool, errors: List[str], warnings: List[str]}

        Raises:
            CSVValidationError: If file is invalid
        """
        errors = []
        warnings = []

        # Check file extension
        if not file.filename or not file.filename.lower().endswith('.csv'):
            errors.append("File must have .csv extension")

        # Check content type (may not be reliable)
        if file.content_type and file.content_type not in ["text/csv", "application/csv", "application/vnd.ms-excel"]:
            warnings.append(f"Unexpected content type: {file.content_type}")

        # Read file to check size and magic bytes
        content = await file.read()
        file_size = len(content)

        if file_size == 0:
            errors.append("File is empty")

        if file_size > ProspectCSVParser.MAX_FILE_SIZE:
            errors.append(f"File size ({file_size} bytes) exceeds maximum allowed ({ProspectCSVParser.MAX_FILE_SIZE} bytes)")

        # Check magic bytes (CSV doesn't have strict magic bytes, but check for text)
        if content[:100]:
            try:
                content[:100].decode('utf-8')
            except UnicodeDecodeError:
                errors.append("File does not appear to be a valid text file")

        # Reset file pointer for further processing
        await file.seek(0)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "file_size": file_size
        }

    @staticmethod
    async def parse_and_validate(
        file: UploadFile,
        validate_only: bool = False
    ) -> Tuple[List[Dict], Dict]:
        """
        Parse CSV file and validate prospect data.

        Args:
            file: UploadFile from FastAPI
            validate_only: If True, only validate structure without full parsing

        Returns:
            Tuple of (prospects_list, validation_report)

        Raises:
            CSVValidationError: If file validation fails
        """
        # First validate file
        validation = await ProspectCSVParser.validate_file(file)
        if not validation["valid"]:
            raise CSVValidationError("; ".join(validation["errors"]))

        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8-sig')  # Handle BOM

        # Parse CSV
        csv_file = io.StringIO(content_str)
        reader = csv.DictReader(csv_file)

        # Get headers
        if not reader.fieldnames:
            raise CSVValidationError("CSV file has no headers")

        headers = [h.strip().lower() for h in reader.fieldnames]

        # Validate headers
        if "email" not in headers:
            raise CSVValidationError("CSV must have 'email' column")

        # Check for unknown headers
        unknown_headers = [h for h in headers if h not in ProspectCSVParser.ALLOWED_HEADERS]
        if unknown_headers:
            raise CSVValidationError(f"Unknown headers: {', '.join(unknown_headers)}")

        # Parse rows
        prospects = []
        errors = []
        warnings = []
        duplicate_emails = set()
        seen_emails = set()
        row_num = 1

        for row in reader:
            row_num += 1

            # Normalize keys to lowercase
            row_normalized = {k.strip().lower(): v for k, v in row.items() if k}

            # Get email (required)
            email = ProspectCSVParser._clean_value(row_normalized.get("email", ""))

            if not email:
                errors.append(f"Row {row_num}: Missing email")
                continue

            if not ProspectCSVParser._validate_email(email):
                errors.append(f"Row {row_num}: Invalid email format: {email}")
                continue

            # Check for duplicates within file
            if email.lower() in seen_emails:
                duplicate_emails.add(email.lower())
                warnings.append(f"Row {row_num}: Duplicate email: {email}")
                continue

            seen_emails.add(email.lower())

            # Build prospect dict
            prospect = {
                "email": email.lower(),
                "first_name": ProspectCSVParser._clean_value(row_normalized.get("first_name", "")),
                "last_name": ProspectCSVParser._clean_value(row_normalized.get("last_name", "")),
                "company_name": ProspectCSVParser._clean_value(row_normalized.get("company_name", "")),
                "company_domain": ProspectCSVParser._clean_value(row_normalized.get("company_domain", "")),
                "title": ProspectCSVParser._clean_value(row_normalized.get("title", "")),
                "phone": ProspectCSVParser._clean_value(row_normalized.get("phone", "")),
                "linkedin_url": ProspectCSVParser._clean_value(row_normalized.get("linkedin_url", "")),
                "industry": ProspectCSVParser._clean_value(row_normalized.get("industry", "")),
                "company_size": ProspectCSVParser._clean_value(row_normalized.get("company_size", "")),
            }

            # Validate optional fields
            if prospect["linkedin_url"] and not prospect["linkedin_url"].startswith("http"):
                warnings.append(f"Row {row_num}: LinkedIn URL should start with http: {prospect['linkedin_url']}")

            prospects.append(prospect)

            # Stop if too many rows
            if len(prospects) > ProspectCSVParser.MAX_ROWS:
                errors.append(f"File exceeds maximum {ProspectCSVParser.MAX_ROWS} rows")
                break

            # Stop if validate_only and we have enough for validation
            if validate_only and row_num > 100:
                break

        # Build validation report
        report = {
            "total_rows": row_num - 1,
            "valid_prospects": len(prospects),
            "errors": errors,
            "warnings": warnings,
            "duplicate_emails": list(duplicate_emails),
            "headers_found": headers,
            "is_valid": len(errors) == 0
        }

        # If there were critical errors, raise
        if errors and not validate_only:
            error_summary = f"{len(errors)} validation errors found"
            if len(errors) <= 5:
                error_summary += ": " + "; ".join(errors[:5])
            else:
                error_summary += f": {errors[0]} (and {len(errors) - 1} more)"
            raise CSVValidationError(error_summary)

        return prospects, report

    @staticmethod
    def compute_file_hash(content: bytes) -> str:
        """
        Compute SHA256 hash of file content for deduplication.

        Args:
            content: File content as bytes

        Returns:
            SHA256 hash as hex string
        """
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    async def deduplicate_prospects(prospects: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """
        Deduplicate prospects by email.

        Args:
            prospects: List of prospect dicts

        Returns:
            Tuple of (unique_prospects, duplicate_emails)
        """
        seen = {}
        unique = []
        duplicates = []

        for prospect in prospects:
            email = prospect["email"].lower()
            if email not in seen:
                seen[email] = True
                unique.append(prospect)
            else:
                duplicates.append(email)

        return unique, duplicates
