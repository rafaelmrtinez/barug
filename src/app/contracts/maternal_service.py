from abc import ABC, abstractmethod
from typing import Any
from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.app.transfer_objects.request.init_chilld_immunization_request import InitialChildImmunizationRequest


class IMaternalService(ABC):

    @abstractmethod
    def execute_child_visit(self, initial_visit_data: ChildVisitRequest, immunization_data: list[InitialChildImmunizationRequest]):
        raise NotImplementedError()

    @abstractmethod
    def execute_insert_child_record(self, child_data: CreateChildRecordRequest) -> int:
        raise NotImplementedError()
