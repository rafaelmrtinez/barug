from abc import ABC, abstractmethod
from dataclasses import dataclass
from django.core.files.uploadedfile import InMemoryUploadedFile
from typing import Optional


@dataclass
class IDocument(ABC):
    name: str
    created_at: str
    file: Optional[InMemoryUploadedFile] = None