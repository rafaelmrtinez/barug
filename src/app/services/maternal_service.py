from src.app.exceptions.person_not_found import PersonNotFoundException
from src.app.exceptions.prescription_exception import PrescriptionException
from src.app.transfer_objects.request.child_immunization_request import ChildImmunizationRequest
from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.app.transfer_objects.request.init_chilld_immunization_request import InitialChildImmunizationRequest
from src.domain.contracts.family_repository import IFamilyRepository
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.domain.contracts.maternal_service import IMaternalService
from src.domain.services.maternal_immunization_service import MaternalImmunizationService


class MaternalService(IMaternalService):
    
    def __init__(
        self, 
        maternal_repository: IMaternalRepository,
        family_repository: IFamilyRepository
    ):
        self._maternal_repository = maternal_repository
        self._family_repository = family_repository
        
    def execute_child_visit(self, initial_visit_data: ChildVisitRequest, immunization_data: list[InitialChildImmunizationRequest]):
        record_id = self._maternal_repository.get_child_record_by_person_id(person_id=initial_visit_data.p_child_id)

        if not record_id:
            raise PersonNotFoundException(f"No record found!")

        initial_visit_data.p_child_record_id = record_id

        validation_errors = MaternalImmunizationService.validate_immunization_sequence(immunization_data)
        
        if validation_errors:
            raise PrescriptionException(validation_errors)

        actual_immunization = []
        
        for immunization in immunization_data:
            key = (
                "pentavalent" if immunization.name == "penta"
                else "hep bv" if immunization.name == "hepb"
                else immunization.name
            )

            immunization_type_id = self._maternal_repository.get_immunization_type_id_by_type_name(key.upper())

            # Find latest valid date and its stage
            doses = [immunization.d0, immunization.d1, immunization.d2, immunization.d3]
            for stage, dose_date in reversed(list(enumerate(doses, start=1))):
                if dose_date:
                    actual_immunization.append(
                        ChildImmunizationRequest(
                            immunization_type_id=immunization_type_id,
                            date_given=dose_date,
                            immunization_stage_given_id=stage,
                        )
                    )
                    break

        print(actual_immunization)
        initial_visit_data.p_child_immunizations = actual_immunization
        # return self._maternal_repository.insert_child_visit(visit_data)
        return 1

    def execute_insert_child_record(self, child_data: CreateChildRecordRequest) -> int:
        family_id = self._family_repository.get_family_id_by_family_no(child_data.p_family_id)
        child_data.p_family_id = family_id
        return self._maternal_repository.insert_child_record(child_data)