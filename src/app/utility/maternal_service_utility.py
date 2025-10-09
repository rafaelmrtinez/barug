from src.app.transfer_objects.request.child_immunization_request import ChildImmunizationRequest
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.domain.services.maternal_immunization_service import MaternalDomainService


class MaternalServiceUtility:
    
    @staticmethod
    def handle_immunization_name_mapping(immunization_data, repo: IMaternalRepository) -> list:
        
        actual_immunization = []
        
        for immunization in immunization_data:
            result = MaternalDomainService.determine_latest_immunization(immunization)
            if result:
                key, date_given, stage = result
                immunization_type_id = repo.fetch_immunization_type_id_by_type_name(key)
                actual_immunization.append(
                    ChildImmunizationRequest(
                        immunization_type_id=immunization_type_id,
                        date_given=date_given,
                        immunization_stage_given_id=stage
                    )
                )
        return actual_immunization