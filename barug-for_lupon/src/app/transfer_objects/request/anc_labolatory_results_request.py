from datetime import date
from pydantic import BaseModel


class ANCLaboratoryResultsRequest(BaseModel):
    lab_test_id: int | None = None
    result: int | str | float | None = None
    date_tested: date | None = None