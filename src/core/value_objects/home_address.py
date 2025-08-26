from dataclasses import dataclass
import re
from typing import Optional

from src.core.exceptions.domain_exceptions import DomainException
from src.core.enums.sitio import Sitio


@dataclass(frozen=True)
class HomeAddress:
    street: str
    sitio: str
    barangay: str
    city: str
    house_number: Optional[str] = None

    def __post_init__(self):
        self.__house_number_validity()
        self.__street_validity()
        self.__sitio_validity()
        self.__barangay_validity()
        self.__city_validity()

    def __city_validity(self):
        if not self.city:
            raise DomainException('City is required.')

        if self.city.lower() != 'cebu city' and self.city.lower() != 'cebu':
            raise DomainException('City must be Cebu City.')

    def __barangay_validity(self):
        if not self.barangay:
            raise DomainException('Barangay is required.')

        allowed_formats = [
            'señor santo niño', 'señor santo nino', 'senor santo nino',
            'señor santo nino', 'sr santo niño', 'sr santo nino', 'sr. sto. niño', 'sr. santo nino'
        ]
        if self.barangay.lower() not in allowed_formats:
            raise DomainException("Barangay is invalid. Please check input.")

    def __sitio_validity(self):

        if not self.sitio:

            alpha_num = r'^[a-zA-Z0-9]+$'
            if not re.match(alpha_num, self.sitio):
                raise DomainException("Sitio must be alphanumeric.")
            return

        if self.sitio not in Sitio.list_sitios():
            raise DomainException("Invalid sitio.")

    def __street_validity(self):
        if not self.street:
            raise DomainException("Street is required.")

        if len(self.street) < 2 or len(self.street) > 100:
            raise DomainException(
                "Street must be between 2 and 100 characters.")

    def __house_number_validity(self):
        if not self.house_number:
            return

        house_number_pattern = r'^[a-zA-Z0-9\s\-\/]+$'
        if not re.match(house_number_pattern, self.house_number):
            raise DomainException(
                "Invalid house number format. Must be numeric format.")
