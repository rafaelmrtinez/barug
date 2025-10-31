from abc import ABC, abstractmethod
from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2


class IChildHealthService(ABC):

    @abstractmethod
    def execute_insert_child_immunization(self, immunization: ImmunizationRequestVersion2):
        """Insert immunization for a child visit."""
        raise NotImplementedError()
