from dataclasses import dataclass
from typing import Optional


@dataclass
class GovernmentMembershipProgram:
    gov_mem_prog_id: Optional[int]
    gov_mem_prog_name: str
