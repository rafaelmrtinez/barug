from datetime import date
from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException
from src.domain.services.child_immunization_service import ChildImmunizationDomainService
from src.infra.repositories.child_health_repository import ChildHealthRepository
from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2


class ChildHealthService:
    
    def __init__(self, ch_repo: ChildHealthRepository):
        self._ch_repo = ch_repo
        
    def execute_insert_child_immunization(self, immunization: ImmunizationRequestVersion2):
        """
        Application service:
        - Ensures a valid child visit exists
        - Validates chronological order (stage + date)
        - Inserts immunization record
        """
        # --- 1️⃣ Verify latest visit existence ---
        child_visit_id = self._ch_repo.fetch_recent_visit_id_by_chr_id(immunization.p_child_record_id)
        if not child_visit_id:
            raise ValueError("No recent visit found for the given Child Health Record.")

        # --- 2️⃣ Get all immunizations for this child and visit ---
        all_immunizations = self._ch_repo.fetch_immunization_stages_by_chr_id_and_visit_id(
            chr_id=immunization.p_child_record_id,
            visit_id=child_visit_id
        )

        # --- 3️⃣ Bypass validation for 24hr vaccines (BCG, Hep BV) ---
        if immunization.p_immunization_type_id in [1, 2]:
            return self._ch_repo.insert_child_immunizations(immunization=immunization)

        # --- 4️⃣ Validate immunization order and date ---
        ChildImmunizationDomainService.validate_immunization(
            immunization=immunization,
            all_immunizations=all_immunizations
        )

        # --- 5️⃣ Insert into repository ---
        return self._ch_repo.insert_child_immunizations(immunization=immunization)


# from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2
# from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException
# from src.domain.services.child_immunization_service import ChildImmunizationDomainService
# from src.infra.repositories.child_health_repository import ChildHealthRepository


# class ChildHealthService:
    
#     def __init__(self, ch_repo: ChildHealthRepository):
#         self._ch_repo = ch_repo
        
#     def execute_insert_child_immunization(self, immunization: ImmunizationRequestVersion2):
#         """
#         Validate chronological immunization order before inserting a new record.
#         """
#         child_visit_id = self._ch_repo.fetch_recent_visit_id_by_chr_id(immunization.p_child_record_id)
#         if not child_visit_id:
#             raise ValueError("No recent visit found for the given Child Health Record.")
#         all_immunizations = self._ch_repo.fetch_immunization_stages_by_chr_id_and_visit_id(
#             chr_id=immunization.p_child_record_id,
#             visit_id=child_visit_id
#         )
#         if immunization.p_immunization_type_id in [1, 2]:
#             return self._ch_repo.insert_child_immunizations(immunization=immunization)
#         ChildImmunizationDomainService.validate_immunization(
#             immunization=immunization,
#             all_immunizations=all_immunizations
#         )
#         return self._ch_repo.insert_child_immunizations(immunization=immunization)