from dataclasses import dataclass
from typing import Optional


@dataclass
class PurokSitio:
    purok_sitio_id: Optional[int]
    purok_sitio_code: str
    purok_sitio_name: str
