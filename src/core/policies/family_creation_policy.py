from src.core.context.family_eligibility_context import FamilyEligibilityContext
from src.core.entities.resident import Resident
from src.core.enums.relationship import Relationships
from src.core.exceptions.policy_exception import PolicyException
from src.core.policies.resident_eligibility_policy import ResidentEligibilityPolicy


class FamilyCreationPolicy:
    def __init__(self, resident: Resident, ctx: FamilyEligibilityContext):
        self.resident = resident
        self.ctx = ctx

    def check_eligibility(self) -> None:

        ResidentEligibilityPolicy(resident=self.resident).check_eligibility(
            has_existing_household=self.ctx.has_existing_household)

        if not self.ctx.household_number:
            raise PolicyException("Household number does not exist.")

        if self.ctx.household_head_relationship not in Relationships.relationship_list():
            raise PolicyException("Invalid household head relationship.")

        if self.ctx.pending_requests > 0:
            raise PolicyException("There is already a pending family creation request for this resident.")
