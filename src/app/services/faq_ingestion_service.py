from typing import List, Tuple, Optional
from pathlib import Path
from io import BytesIO
import logging

from src.infra.repositories.faq_ingestion_repository import FAQIngestionRepository
from src.infra.repositories.faq_excel_parser import parse_workbook, ParseError
from src.domain.services.faq_validator import validate_and_sanitize_rows, FAQValidationError

logger = logging.getLogger(__name__)


class FAQIngestionService:
    """Service layer that validates and sanitizes an uploaded Excel file
    before delegating the upload to the external function via repository.

    Validation rules (implemented):
      - allowed extensions: .xlsx, .xls
      - maximum file size: default 5 MB (configurable)
      - workbook first sheet must contain exactly two headers: question, answer
      - maximum content rows (excluding header): 500
      - question/answer text are required for each row and are trimmed/sanitized
    """

    DEFAULT_MAX_ROWS = 500
    DEFAULT_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

    def __init__(self, repository: Optional[FAQIngestionRepository] = None,
                 max_rows: int = DEFAULT_MAX_ROWS,
                 max_file_size: int = DEFAULT_MAX_FILE_SIZE):
        self.repo = repository or FAQIngestionRepository()
        self.max_rows = int(max_rows)
        self.max_file_size = int(max_file_size)

    def _sanitize_cell(self, value: Optional[object]) -> str:
        if value is None:
            return ""
        s = str(value).strip()
        # Collapse multiple whitespace to single space
        s = " ".join(s.split())
        return s
    def _validate_and_extract(self, file_bytes: bytes, filename: str) -> List[Tuple[str, str]]:
        """Coordinate infra parsing and domain validation, returning sanitized tuples.

        Raises domain-level FAQValidationError on validation problems.
        """
        try:
            header, rows = parse_workbook(file_bytes, filename, max_file_size=self.max_file_size)
        except ParseError as pe:
            # Convert infra parse errors into domain-facing validation errors
            raise FAQValidationError(str(pe))

        # Delegate header/row validation and sanitization to domain layer
        sanitized = validate_and_sanitize_rows(header, rows, max_rows=self.max_rows)
        return sanitized

    def ingest_and_upload(self, file_obj, filename: str, uploaded_by: str) -> dict:
        """Validate, sanitize and upload the file using the repository.

        file_obj may be bytes or a file-like object. Returns the repository
        response as a dict.
        """
        # guards: ensure parameters are present
        if not filename or not isinstance(filename, str):
            raise FAQValidationError("filename is required")
        if not uploaded_by or not isinstance(uploaded_by, str):
            raise FAQValidationError("uploaded_by is required")

        # read bytes
        if hasattr(file_obj, "read"):
            file_bytes = file_obj.read()
        else:
            file_bytes = file_obj

        if not file_bytes:
            raise FAQValidationError("Uploaded file is empty")

        # run validations (raises FAQValidationError on problems)
        sanitized_rows = self._validate_and_extract(file_bytes, filename)

        # Optionally, further sanitize/limit before upload: here we just ensure
        # each value is trimmed and safe (already done) and do not include more
        # than max_rows.
        limited_rows = sanitized_rows[: self.max_rows]

        # At this point we can either upload the original file (per API
        # contract) or send parsed JSON. The endpoint expects base64 file in
        # JSON; we'll send the original bytes encoded by the repository.
        response = self.repo.upload_via_json(file_bytes, filename, uploaded_by)
        
        # mock response
        # response = {
        #     "status": "ok",
        #     "http_status": 200,
        #     "message": f"Received {len(limited_rows)} FAQ entries from {uploaded_by}."
        # }
        
        return {"uploaded": True, "count": len(limited_rows), "response": response}
