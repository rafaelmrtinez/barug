from dataclasses import dataclass
from typing import Optional
from src.domain.entities.person import Person
from src.domain.entities.address import Address


@dataclass
class PersonAggregate:
    person: Person
    address: Optional[Address] = None

    def full_profile(self) -> dict:
        return {
            'person_id': self.person.person_id,
            'full_name': self.person.full_name(),
            'email': self.person.email,
            'mobile': self.person.mobile_num,
            'address': {
                'street': self.address.street if self.address else None,
                'barangay': self.address.barangay if self.address else None,
                'city': self.address.city if self.address else None,
            } if self.address else None,
        }
