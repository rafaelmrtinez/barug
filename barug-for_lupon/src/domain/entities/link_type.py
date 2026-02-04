from dataclasses import dataclass
from typing import Optional


@dataclass
class LinkType:
    link_type_id: Optional[int]
    link_type_name: str
