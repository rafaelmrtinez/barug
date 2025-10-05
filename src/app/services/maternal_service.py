from src.app.exceptions.person_not_found import PersonNotFoundException
from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.domain.contracts.family_repository import IFamilyRepository
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.domain.contracts.maternal_service import IMaternalService


class MaternalService(IMaternalService):
    
    def __init__(
        self, 
        maternal_repository: IMaternalRepository,
        family_repository: IFamilyRepository
    ):
        self._maternal_repository = maternal_repository
        self._family_repository = family_repository
        
    def execute_child_visit(self, visit_data: ChildVisitRequest, person_id: int):
        record_id = self._maternal_repository.get_child_record_by_person_id(person_id=person_id)
        if not record_id:
            raise PersonNotFoundException(f"No record found!")
        visit_data.p_child_record_id = record_id
        # return self._maternal_repository.insert_child_visit(visit_data)
        return 1

    def execute_insert_child_record(self, child_data: CreateChildRecordRequest) -> int:
        family_id = self._family_repository.get_family_id_by_family_no(child_data.p_family_id)
        child_data.p_family_id = family_id
        return self._maternal_repository.insert_child_record(child_data)