from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from typing import Optional


@dataclass
class IDocument(ABC):
    name: str
    raw_file: Optional[BytesIO] = None 
    created_at: str