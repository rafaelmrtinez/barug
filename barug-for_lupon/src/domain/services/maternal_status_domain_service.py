"""Domain-level rules for maternal health record status transitions.

This module should contain pure domain logic (no DB, no HTTP). Keep business
rules here. For now this is permissive — it validates the inputs and can be
extended to enforce real business rules (for example: do not allow moving from
COMPLETE back to INCOMPLETE).
"""
from typing import Optional


class MaternalStatusDomainException(Exception):
    """Domain-level exception for maternal status rules."""
    pass


class MaternalStatusDomainService:
    """Encapsulates domain rules for maternal status transitions.

    All methods are static and contain pure business logic. This class can be
    extended with additional static helpers for other domain checks.
    """

    @staticmethod
    def validate_status_transition(
        existing_status_id: Optional[int],
        new_status_id: int,
        existing_status_name: Optional[str] = None,
    ) -> bool:
        """Validate a proposed status transition.

        - existing_status_id: current status id (may be None)
        - new_status_id: proposed new status id
        - existing_status_name: optional readable name for the current status (used for error messages)

        Returns True if allowed. Raises MaternalStatusDomainException for disallowed transitions.

        This method performs pure domain checks (no DB access). Application code
        that needs DB lookups (for example latest-record checks) should remain
        in the application/service layer.
        """
        # new status must be provided
        if new_status_id is None:
            raise MaternalStatusDomainException("New status id must be provided")

        # Prevent no-op transitions (setting the same status)
        try:
            if existing_status_id is not None and int(existing_status_id) == int(new_status_id):
                name = existing_status_name if existing_status_name else str(new_status_id)
                raise MaternalStatusDomainException(f"Status is already set to {name}")
        except ValueError:
            # fall through to general validation error if conversion fails
            raise MaternalStatusDomainException("Invalid status id")

        # Example rule (commented): prevent changing from COMPLETE (id 2) back to INCOMPLETE (id 3)
        # if existing_status_id == 2 and new_status_id == 3:
        #     raise MaternalStatusDomainException("Cannot change status from COMPLETE back to INCOMPLETE")

        # No other blocking rules for now
        return True
