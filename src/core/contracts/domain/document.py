from abc import ABC


from typing import Optional
from dataclasses import dataclass


from django.core.files.uploadedfile import InMemoryUploadedFile


@dataclass
class IDocument(ABC):
    name: str
    created_at: str
    file: Optional[InMemoryUploadedFile] = None