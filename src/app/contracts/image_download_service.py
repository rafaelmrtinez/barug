from abc import ABC, abstractmethod
from typing import Tuple


class IImageDownloadService(ABC):
    @abstractmethod
    def zip_lab_images_for_maternal_record(self, mhr_id: int) -> Tuple[str, str]:
        """Return (zip_path_or_bytes, filename) for the given maternal record id."""
        raise NotImplementedError()
