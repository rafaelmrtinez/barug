from datetime import datetime, date
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
        # Reject entirely empty payloads early
        if immunization is None:
            raise ChildHealthDomainException("Missing immunization payload.")
        if getattr(immunization, 'p_immunization_stage_given_id', None) in (None, '') or getattr(immunization, 'p_date_given', None) in (None, ''):
            raise ChildHealthDomainException("Please provide both immunization stage and date.")

        # Normalize inputs and sanitize basic fields
        try:
            new_stage = int(immunization.p_immunization_stage_given_id)
        except Exception:
            raise ChildHealthDomainException("Invalid stage value.")

        new_date = immunization.p_date_given
        # normalize new_date if string
        if isinstance(new_date, str):
            try:
                new_date = datetime.fromisoformat(new_date).date()
            except Exception:
                raise ChildHealthDomainException("Invalid date format for immunization.")
        elif isinstance(new_date, datetime):
            new_date = new_date.date()

        if not isinstance(new_date, date):
            raise ChildHealthDomainException("Invalid or missing date for immunization.")

        # Prevent future dates
        if new_date > date.today():
            raise ChildHealthDomainException("Immunization date cannot be in the future.")

        # Filter existing records for the same vaccine type
        same_vaccine_doses = [
            rec for rec in (all_immunizations or [])
            if rec.get("immunization_type_id") == immunization.p_immunization_type_id
        ]

        existing_stages = sorted([
            int(rec["immunization_stage_given_id"]) for rec in same_vaccine_doses
            if rec.get("immunization_stage_given_id") is not None
        ])

        existing_dates = sorted([
            (rec["date_given"].date() if isinstance(rec["date_given"], datetime) else rec["date_given"]) 
            for rec in same_vaccine_doses
            if rec.get("date_given") is not None
        ])

        # Also collect all prior immunization dates across all vaccines to ensure global ordering
        all_dates = sorted([
            (rec["date_given"].date() if isinstance(rec.get("date_given"), datetime) else rec.get("date_given"))
            for rec in (all_immunizations or [])
            if rec.get("date_given") is not None
        ])

        latest_stage = existing_stages[-1] if existing_stages else None
        latest_date = existing_dates[-1] if existing_dates else None

        # Vaccine type specific rules
        # Assume vaccine type ids 1 and 2 map to BCG and HEP BV (24-hour vaccines)
        if int(immunization.p_immunization_type_id) in (1, 2):
            # Only the 24-hour dose (stage 1) is allowed and only once
            if new_stage != 1:
                raise ChildHealthDomainException("Only the 24-hour dose is allowed for this vaccine type.")
            if existing_stages:
                raise ChildHealthDomainException("A 24-hour dose for this vaccine type has already been recorded.")
            # Also ensure new_date is not earlier than any other recorded immunization
            if all_dates and new_date < all_dates[-1]:
                raise ChildHealthDomainException("New dose date cannot be before previously recorded immunizations.")
            return True

        # For other vaccine types:
        # Disallow 24-hour stage (stage 1)
        if new_stage == 1:
            raise ChildHealthDomainException("24-hour dose is not allowed for this vaccine type.")

        # First dose must start with stage 2
        if latest_stage is None and new_stage != 2:
            raise ChildHealthDomainException(
                "Invalid first dose for this vaccine type. Must start with stage 2 (1st dose)."
            )

        # Prevent duplicates
        if new_stage in existing_stages:
            raise ChildHealthDomainException(f"Stage {new_stage} already recorded for this vaccine type.")

        # Prevent skipped doses
        if latest_stage is not None and new_stage != latest_stage + 1:
            raise ChildHealthDomainException(
                f"Invalid dose sequence. Latest recorded stage is {latest_stage}, next allowed stage is {latest_stage + 1}."
            )

        # Enforce chronological date order for same vaccine
        if latest_date and new_date <= latest_date:
            raise ChildHealthDomainException(
                f"Invalid date sequence. New dose date ({new_date}) must be after the last recorded dose date ({latest_date})."
            )

        # Ensure new_date is not before any previously recorded immunization dates
        if all_dates and new_date < all_dates[-1]:
            raise ChildHealthDomainException("New dose date cannot be before previously recorded immunizations.")

        return True
