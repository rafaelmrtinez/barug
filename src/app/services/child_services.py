from src.app.contracts.child_services import IChildService
from src.app.transfer_objects.response.child_basic_info_response import BasicInformationResponse
from src.infra.contracts.child_repository import IChildRepository


class ChildService(IChildService):
    
    def __init__(self, child_repository: IChildRepository) -> None:
        self.child_repository = child_repository

    def execute_get_child_basic_info(self, id: int) -> BasicInformationResponse:
        return self.child_repository.get_child_basic_info_by_person_id(id)