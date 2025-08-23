from dataclasses import dataclass

@dataclass(frozen=True)
class IncomeSource:
    source: str