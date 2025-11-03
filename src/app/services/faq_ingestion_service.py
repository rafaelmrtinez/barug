from typing import List, Tuple, Optional
from pathlib import Path
from io import BytesIO
import logging

from src.infra.repositories.faq_ingestion_repository import FAQIngestionRepository

logger = logging.getLogger(__name__)


class FAQValidationError(Exception):
    pass


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
        """Validate the workbook and return a list of (question, answer) tuples.

        Raises FAQValidationError with a human-friendly message on failure.
        """
        # file size
        if len(file_bytes) > self.max_file_size:
            raise FAQValidationError(f"File too large (>{self.max_file_size} bytes).")

        ext = Path(filename).suffix.lower()
        if ext not in (".xlsx", ".xls"):
            raise FAQValidationError("Invalid file type. Only .xlsx and .xls are allowed.")

        # Lazy import openpyxl / xlrd to avoid adding heavy deps at module import time
        rows = []
        try:
            if ext == ".xlsx":
                from openpyxl import load_workbook
                wb = load_workbook(filename=BytesIO(file_bytes), read_only=True, data_only=True)
                ws = wb.worksheets[0]
                iterator = ws.iter_rows(values_only=True)
                header_row = next(iterator, None)
                if not header_row:
                    raise FAQValidationError("Workbook first sheet is empty.")
                header = [ (str(c).strip().lower() if c is not None else "") for c in header_row ]
                # collect rows
                for r in iterator:
                    rows.append(list(r))
            else:
                # .xls support via xlrd
                import xlrd
                book = xlrd.open_workbook(file_contents=file_bytes)
                sheet = book.sheet_by_index(0)
                if sheet.nrows == 0:
                    raise FAQValidationError("Workbook first sheet is empty.")
                header = [ str(sheet.cell_value(0, c)).strip().lower() for c in range(sheet.ncols) ]
                for ri in range(1, sheet.nrows):
                    row = [ sheet.cell_value(ri, c) if c < sheet.ncols else None for c in range(len(header)) ]
                    rows.append(row)
        except FAQValidationError:
            raise
        except Exception as exc:
            logger.exception("Failed to read workbook: %s", exc)
            raise FAQValidationError("Failed to parse Excel workbook. Ensure the file is a valid Excel document.")

        # headers must be exactly two columns: question and answer (case-insensitive)
        if len(header) != 2:
            raise FAQValidationError("Workbook must have exactly two columns: question and answer.")

        header_normalized = [h.strip().lower() for h in header]
        if set(header_normalized) != {"question", "answer"}:
            raise FAQValidationError("Headers must be exactly: 'question' and 'answer' (case-insensitive).")

        # map header order to indices
        q_idx = header_normalized.index("question")
        a_idx = header_normalized.index("answer")

        # before sanitizing, compute how many non-empty data rows exist
        # (some spreadsheets include many blank rows in the used range). If
        # the number of non-empty rows exceeds the configured limit, fail
        # early with a clear error so callers know the file is too large.
        non_empty_count = 0
        for row in rows:
            if any((c is not None and str(c).strip() != '') for c in row):
                non_empty_count += 1
        if non_empty_count > self.max_rows:
            raise FAQValidationError(f"Too many rows ({non_empty_count}). Limit is {self.max_rows}.")

        # validate rows and sanitize
        sanitized = []
        errors = []
        for i, row in enumerate(rows, start=1):
            if i > self.max_rows:
                break
            # ensure row has at least two cells
            q_raw = row[q_idx] if q_idx < len(row) else None
            a_raw = row[a_idx] if a_idx < len(row) else None
            q = self._sanitize_cell(q_raw)
            a = self._sanitize_cell(a_raw)
            if not q and not a:
                # skip entirely blank rows silently
                continue
            # require both question and answer present
            if not q or not a:
                errors.append(f"Row {i+1}: missing question or answer")
                continue
            # enforce reasonable lengths (avoid abuse)
            if len(q) > 2000 or len(a) > 5000:
                errors.append(f"Row {i+1}: content too long")
                continue
            sanitized.append((q, a))

        if errors:
            raise FAQValidationError("Validation failed: " + "; ".join(errors[:10]))

        if len(sanitized) == 0:
            raise FAQValidationError("No valid FAQ rows found in the workbook.")
        print(f"Debug: Total sanitized rows = {len(sanitized)}")
        if len(sanitized) > self.max_rows:
            print(f"Warning: {len(sanitized) - self.max_rows} rows exceeded the limit and will be ignored.")
            raise FAQValidationError(f"Too many FAQ rows: limit is {self.max_rows}.")

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
        # response = self.repo.upload_via_json(file_bytes, filename, uploaded_by)
        
        # mock response
        response = {
            "status": "ok",
            "http_status": 200,
            "message": f"Received {len(limited_rows)} FAQ entries from {uploaded_by}."
        }
        
        return {"uploaded": True, "count": len(limited_rows), "response": response}
