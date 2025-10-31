from dataclasses import dataclass
from typing import Optional, List
from src.domain.entities.maternal_health_record import MaternalHealthRecord
from src.domain.entities.person import Person


@dataclass
class MaternalAggregate:
    record: MaternalHealthRecord
    person: Optional[Person] = None
    anc_visits: Optional[List[dict]] = None

    def age_group(self) -> Optional[str]:
        if not self.person:
            return None
        age = int(self.person.age)
        if age < 18:
            return 'Under 18'
        if age <= 24:
            return '18-24'
        if age <= 34:
            return '25-34'
        return '35+'
