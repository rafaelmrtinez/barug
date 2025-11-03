from dataclasses import dataclass
from typing import Optional


@dataclass
class EducationalAttainment:
    education_id: Optional[int]
    educ_level: str
