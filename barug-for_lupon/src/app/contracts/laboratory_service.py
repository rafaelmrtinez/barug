from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ILaboratoryService(ABC):

    @abstractmethod
    def build_payload(self, paired_tests) -> List[Dict[str, Any]]:
        """Build serializable payload from cleaned paired_tests."""
        raise NotImplementedError()

    @abstractmethod
    def save(self, paired_tests) -> Dict[str, Any]:
        """Persist laboratory paired_tests and return result."""
        raise NotImplementedError()
