from dataclasses import asdict
from src.app.exceptions.person_not_found import PersonNotFoundException
from src.app.exceptions.prescription_exception import PrescriptionException
from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.app.transfer_objects.request.init_chilld_immunization_request import InitialChildImmunizationRequest
from src.app.utility.maternal_service_utility import MaternalServiceUtility
from src.domain.contracts.family_repository import IFamilyRepository
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.app.contracts.maternal_service import IMaternalService
from src.domain.services.maternal_immunization_service import MaternalDomainService
from src.infra.utilities.json_deep_conversion import JSONConverterUtility


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

        validation_errors = MaternalDomainService.validate_immunization_sequence(immunization_data)
        
        if validation_errors:
            raise PrescriptionException(validation_errors)

        actual_immunization = MaternalServiceUtility.handle_immunization_name_mapping(immunization_data, self._maternal_repository)

        initial_visit_data.p_child_immunizations = actual_immunization
        initial_visit_data.p_child_immunizations = JSONConverterUtility.deep_conversion([asdict(i) for i in actual_immunization])
        initial_visit_data.p_bf_checks = JSONConverterUtility.deep_conversion([asdict(i) for i in initial_visit_data.p_bf_checks]) if initial_visit_data.p_bf_checks else None
        initial_visit_data.p_monitoring_logs = JSONConverterUtility.deep_conversion([asdict(initial_visit_data.p_monitoring_logs)])
        initial_visit_data.p_screening = JSONConverterUtility.to_json_object(asdict(initial_visit_data.p_screening))
        initial_visit_data.p_iron_supplements = JSONConverterUtility.to_json_object(asdict(initial_visit_data.p_iron_supplements))
        initial_visit_data.p_vitamin_a = JSONConverterUtility.deep_conversion([asdict(i) for i in initial_visit_data.p_vitamin_a]) if initial_visit_data.p_vitamin_a else None
        
        final_data = initial_visit_data

        return self._maternal_repository.insert_child_visit(final_data)

    def execute_insert_child_record(self, child_data: CreateChildRecordRequest) -> int:
        family_id = self._family_repository.get_family_id_by_family_no(child_data.p_family_id)
        child_data.p_family_id = family_id
        return self._maternal_repository.insert_child_record(child_data)