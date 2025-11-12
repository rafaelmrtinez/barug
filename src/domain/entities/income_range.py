from dataclasses import dataclass
from typing import Optional


@dataclass
class IncomeRange:
    income_range_id: Optional[int]
    income_range_amnt: Optional[str]
