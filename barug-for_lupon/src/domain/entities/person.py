from dataclasses import dataclass
from datetime import date
from typing import Optional
from src.domain.value_objects.name import Name
from src.domain.value_objects.contact import Contact


@dataclass
class Person:
    person_id: Optional[int]
    person_code: str
    name: Name
    birthdate: date
    age: float
    email: Optional[str] = None
    mobile_num: Optional[str] = None
    occupation: Optional[str] = None
    is_minor: bool = False
    mnthly_personal_income_id: Optional[int] = None
    sex_id: Optional[int] = None
    address_id: Optional[int] = None
    person_status_id: Optional[int] = None
    residential_status_id: Optional[int] = None
    civil_status_id: Optional[int] = None
    nationality_id: Optional[int] = None
    religion_id: Optional[int] = None
    education_id: Optional[int] = None
    employment_status_id: Optional[int] = None

    @property
    def contact(self) -> Contact:
        return Contact(email=self.email, mobile=self.mobile_num)

    def full_name(self) -> str:
        return self.name.full()

    def is_adult(self) -> bool:
        return not self.is_minor and self.age >= 18
