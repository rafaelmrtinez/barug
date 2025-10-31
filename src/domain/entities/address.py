from dataclasses import dataclass
from typing import Optional
from src.domain.value_objects.coordinates import Coordinates


@dataclass
class Address:
    address_id: Optional[int]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    street: Optional[str] = None
    barangay: Optional[str] = None
    city: Optional[str] = None
    purok_sitio_id: Optional[int] = None

    def coordinates(self) -> Optional[Coordinates]:
        if self.latitude is None or self.longitude is None:
            return None
        return Coordinates(latitude=self.latitude, longitude=self.longitude)
