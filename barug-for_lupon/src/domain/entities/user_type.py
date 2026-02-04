from dataclasses import dataclass
from typing import Optional


@dataclass
class UserType:
    user_type_id: Optional[int]
    user_type_name: str
