from src.domain.services.child_immunization_service import ChildImmunizationDomainService
from src.infra.repositories.child_health_repository import ChildHealthRepository
from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2
from src.app.contracts.child_health_service import IChildHealthService


class ChildHealthService(IChildHealthService):
    
    def __init__(self, ch_repo: ChildHealthRepository):
        self._ch_repo = ch_repo
        
    def execute_insert_child_immunization(self, immunization: ImmunizationRequestVersion2):
        """
        Application service:
        - Ensures a valid child visit exists
        - Validates chronological order (stage + date)
        - Inserts immunization record
        """
        # --- Get all immunizations for this child and visit ---
        all_immunizations = self._ch_repo.fetch_immunization_stages_by_chr_id_and_visit_id(
            chr_id=immunization.p_child_record_id,
        )

        # --- Validate immunization order and date ---
        ChildImmunizationDomainService.validate_immunization(
            immunization=immunization,
            all_immunizations=all_immunizations
        )

        # --- Insert into repository ---
        return self._ch_repo.insert_child_immunizations(immunization=immunization)