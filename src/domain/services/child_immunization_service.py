from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException


class ChildImmunizationDomainService:
    
    @staticmethod
    def validate_immunization(immunization, all_immunizations):

        # 4️⃣ Filter doses for the same vaccine type only
        same_vaccine_doses = [
            rec for rec in all_immunizations
            if rec["immunization_type_id"] == immunization.p_immunization_type_id
        ]

        # Extract stage IDs from filtered records
        existing_stages = sorted([
            int(rec["immunization_stage_given_id"])
            for rec in same_vaccine_doses
            if rec.get("immunization_stage_given_id") is not None
        ])

        new_stage = int(immunization.p_immunization_stage_given_id)
        latest_stage = existing_stages[-1] if existing_stages else None

        # 5️⃣ Enforce chronological order
        # Case A: No previous dose → must start with stage 2
        if latest_stage is None and new_stage != 2:
            raise ChildHealthDomainException(
                f"Invalid first dose for this vaccine type. Must start with stage 2 (1ST DOSE)."
            )

        # Case B: Duplicate stage
        if new_stage in existing_stages:
            raise ChildHealthDomainException(
                f"Stage {new_stage} already recorded for this child and vaccine type "
                f"({immunization.p_immunization_type_id})."
            )

        # Case C: Skipped dose
        if latest_stage is not None and new_stage != latest_stage + 1:
            raise ChildHealthDomainException(
                f"Invalid dose sequence. Latest recorded stage is {latest_stage}, "
                f"next allowed stage is {latest_stage + 1}."
            )