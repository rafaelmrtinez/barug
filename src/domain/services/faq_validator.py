from typing import List, Tuple, Optional


class FAQValidationError(Exception):
    """Domain-level validation error for FAQ rows."""
    pass


def _sanitize_cell(value: Optional[object]) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = " ".join(s.split())
    return s


class FAQValidator:
    """Class-based validator for FAQ header/rows.

    Usage:
        validator = FAQValidator(max_rows=500)
        sanitized = validator.validate(header, rows)
    """

    def __init__(self, max_rows: int = 500):
        self.max_rows = int(max_rows)

    def validate(self, header: List[str], rows: List[List[Optional[object]]]) -> List[Tuple[str, str]]:
        """Validate header and rows and return sanitized tuples.

        Raises FAQValidationError on any validation problem.
        """
        if not header or len(header) != 2:
            raise FAQValidationError("Workbook must have exactly two columns: question and answer.")

        header_normalized = [h.strip().lower() for h in header]
        if set(header_normalized) != {"question", "answer"}:
            raise FAQValidationError("Headers must be exactly: 'question' and 'answer' (case-insensitive).")

        q_idx = header_normalized.index("question")
        a_idx = header_normalized.index("answer")

        # Count non-empty data rows first
        non_empty_count = 0
        for row in rows:
            if any((c is not None and str(c).strip() != '') for c in row):
                non_empty_count += 1
        if non_empty_count > self.max_rows:
            raise FAQValidationError(f"Too many rows ({non_empty_count}). Limit is {self.max_rows}.")

        sanitized = []
        errors = []
        for i, row in enumerate(rows, start=1):
            q_raw = row[q_idx] if q_idx < len(row) else None
            a_raw = row[a_idx] if a_idx < len(row) else None
            q = _sanitize_cell(q_raw)
            a = _sanitize_cell(a_raw)
            if not q and not a:
                continue
            if not q or not a:
                errors.append(f"Row {i+1}: missing question or answer")
                continue
            if len(q) > 2000 or len(a) > 5000:
                errors.append(f"Row {i+1}: content too long")
                continue
            sanitized.append((q, a))

        if errors:
            raise FAQValidationError("Validation failed: " + "; ".join(errors[:10]))

        if len(sanitized) == 0:
            raise FAQValidationError("No valid FAQ rows found in the workbook.")

        return sanitized


def validate_and_sanitize_rows(header: List[str], rows: List[List[Optional[object]]], max_rows: int = 500) -> List[Tuple[str, str]]:
    """Backward-compatible function wrapper around FAQValidator.

    This preserves the previous module-level API while internally using the
    class-based implementation.
    """
    validator = FAQValidator(max_rows=max_rows)
    return validator.validate(header, rows)
