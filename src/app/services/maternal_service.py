from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.domain.contracts.family_repository import IFamilyRepository
from src.domain.contracts.maternal_service import IMaternalService
from src.infra.repositories.maternal_repository import MaternalRepository


class MaternalService(IMaternalService):
    
    def __init__(
        self, 
        maternal_repository: MaternalRepository,
        family_repository: IFamilyRepository
    ):
        self._maternal_repository = maternal_repository
        self._family_repository = family_repository

    def insert_child_record(self, child_data: CreateChildRecordRequest) -> int:
        family_id = self._family_repository.get_family_id_by_family_no(child_data.p_family_id)
        child_data.p_family_id = family_id
        return self._maternal_repository.insert_child_record(child_data)