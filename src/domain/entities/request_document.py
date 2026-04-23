from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RequestDocument:
    request_document_id: Optional[int]
    file_path: str
    reason: Optional[str]
    uploaded_date: Optional[datetime]
    linked_id: Optional[int]
    document_type_id: Optional[int]
    link_type_id: Optional[int]
    valid_id_type_id: Optional[int]
