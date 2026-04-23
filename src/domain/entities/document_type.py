from dataclasses import dataclass
from typing import Optional


@dataclass
class DocumentType:
    document_type_id: Optional[int]
    document_type_name: str
    valid_id_type_id: Optional[int] = None
