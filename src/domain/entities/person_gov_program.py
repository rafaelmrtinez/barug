from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PersonGovProgram:
    person_gov_program_id: Optional[int] = None
    person_id: Optional[int] = None
    gov_mem_prog_id: Optional[int] = None
    is_active: Optional[bool] = True
    date_added: Optional[datetime] = None
    added_by_id: Optional[int] = None
