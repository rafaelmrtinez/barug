from datetime import datetime
from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException


class ChildImmunizationDomainService:
    
    @staticmethod
    def validate_immunization(immunization, all_immunizations):
        """
        Domain-level validation for immunization order and chronological consistency.
        Ensures:
        - No skipped stages
        - No duplicate stages
        - Date order matches stage order
        """
        same_vaccine_doses = [
            rec for rec in all_immunizations
            if rec["immunization_type_id"] == immunization.p_immunization_type_id
        ]

        existing_stages = sorted([
            int(rec["immunization_stage_given_id"])
            for rec in same_vaccine_doses
            if rec.get("immunization_stage_given_id") is not None
        ])

        existing_dates = sorted([
            rec["date_given"]
            for rec in same_vaccine_doses
            if rec.get("date_given") is not None
        ])

        new_stage = int(immunization.p_immunization_stage_given_id)
        new_date = immunization.p_date_given
        latest_stage = existing_stages[-1] if existing_stages else None
        latest_date = existing_dates[-1] if existing_dates else None

        # --- A. Validate first dose rule ---
        if latest_stage is None and new_stage != 2:
            raise ChildHealthDomainException(
                "Invalid first dose for this vaccine type. Must start with stage 2 (1st dose)."
            )

        # --- B. Prevent duplicates ---
        if new_stage in existing_stages:
            raise ChildHealthDomainException(
                f"Stage {new_stage} already recorded for this vaccine type."
            )

        # --- C. Prevent skipped doses ---
        if latest_stage is not None and new_stage != latest_stage + 1:
            raise ChildHealthDomainException(
                f"Invalid dose sequence. Latest recorded stage is {latest_stage}, "
                f"next allowed stage is {latest_stage + 1}."
            )

        # --- D. Enforce chronological date order ---
        if latest_date and new_date <= latest_date:
            raise ChildHealthDomainException(
                f"Invalid date sequence. New dose date ({new_date}) "
                f"must be after the last recorded dose date ({latest_date})."
            )



# from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException


# class ChildImmunizationDomainService:
    
#     @staticmethod
#     def validate_immunization(immunization, all_immunizations):

#         # 4️⃣ Filter doses for the same vaccine type only
#         same_vaccine_doses = [
#             rec for rec in all_immunizations
#             if rec["immunization_type_id"] == immunization.p_immunization_type_id
#         ]

#         # Extract stage IDs from filtered records
#         existing_stages = sorted([
#             int(rec["immunization_stage_given_id"])
#             for rec in same_vaccine_doses
#             if rec.get("immunization_stage_given_id") is not None
#         ])

#         new_stage = int(immunization.p_immunization_stage_given_id)
#         latest_stage = existing_stages[-1] if existing_stages else None

#         # 5️⃣ Enforce chronological order
#         # Case A: No previous dose → must start with stage 2
#         if latest_stage is None and new_stage != 2:
#             raise ChildHealthDomainException(
#                 f"Invalid first dose for this vaccine type. Must start with stage 2 (1ST DOSE)."
#             )

#         # Case B: Duplicate stage
#         if new_stage in existing_stages:
#             raise ChildHealthDomainException(
#                 f"Stage {new_stage} already recorded for this child and vaccine type "
#                 f"({immunization.p_immunization_type_id})."
#             )

#         # Case C: Skipped dose
#         if latest_stage is not None and new_stage != latest_stage + 1:
#             raise ChildHealthDomainException(
#                 f"Invalid dose sequence. Latest recorded stage is {latest_stage}, "
#                 f"next allowed stage is {latest_stage + 1}."
#             )