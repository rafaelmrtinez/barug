from typing import List, Tuple, Optional
from pathlib import Path
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


def parse_workbook(file_bytes: bytes, filename: str, max_file_size: int = 5 * 1024 * 1024) -> Tuple[List[str], List[List[Optional[object]]]]:
    """Parse an Excel workbook (xls/xlsx) and return (header, rows).

    header is a list of header labels (strings). rows is a list of rows where
    each row is a list of cell values (may contain None).
    """
    if not file_bytes:
        raise ParseError("Uploaded file is empty")

    if len(file_bytes) > max_file_size:
        raise ParseError("File too large")

    ext = Path(filename).suffix.lower()
    rows = []
    try:
        if ext == '.xlsx':
            from openpyxl import load_workbook
            wb = load_workbook(filename=BytesIO(file_bytes), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            iterator = ws.iter_rows(values_only=True)
            header_row = next(iterator, None)
            if not header_row:
                raise ParseError("Workbook first sheet is empty")
            header = [ (str(c).strip() if c is not None else '') for c in header_row ]
            for r in iterator:
                rows.append(list(r))
        elif ext == '.xls':
            import xlrd
            book = xlrd.open_workbook(file_contents=file_bytes)
            sheet = book.sheet_by_index(0)
            if sheet.nrows == 0:
                raise ParseError("Workbook first sheet is empty")
            header = [ str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols) ]
            for ri in range(1, sheet.nrows):
                row = [ sheet.cell_value(ri, c) if c < sheet.ncols else None for c in range(len(header)) ]
                rows.append(row)
        else:
            raise ParseError("Invalid file type. Only .xlsx and .xls are allowed")
    except ParseError:
        raise
    except Exception as exc:
        logger.exception('Failed to parse workbook: %s', exc)
        raise ParseError('Failed to parse Excel workbook.')

    return header, rows
