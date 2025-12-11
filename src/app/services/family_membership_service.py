from src.infra.repositories.commands.family_commands import FamilyCommands
from src.infra.repositories.queries.household_queries import HouseholdQuery
from src.infra.exceptions.membership_exception import MembershipException
import logging


class FamilyMembershipService:
    _logger = logging.getLogger("FamilyMembershipService")

    def __init__(self, family_commands: FamilyCommands | None, household_query: HouseholdQuery | None):
        self._family_commands = family_commands
        self._household_query = household_query
        self._logger.debug("FamilyMembershipService initialized.")

    def create_family_unit(
        self,
        household_num: str,
        added_by_id: int,
        family_num: str,
        ufc_num: str,
        source_of_income: str,
        family_mnthly_icnome_id: int,
        nhts_status_id: int,
        indigent_status_id: int,
        household_type_id: int,
        family_head_id: int,
        rel_to_hhold_head_id: int,
    ):
        """
        Public method to create a family unit using FamilyCommands.
        Accepts household_num, queries household_id, and validates all inputs.
        Returns the result of the insert_family_unit call.
        Raises MembershipException on error.
        """
        self._logger.info(f"Attempting to create family unit for household_num='{household_num}' and family_num='{family_num}'")
        try:
            if not self._family_commands:
                self._logger.error("FamilyCommands dependency not provided.")
                raise MembershipException("Internal error: FamilyCommands dependency not provided.")
            if not self._household_query:
                self._logger.error("HouseholdQuery dependency not provided.")
                raise MembershipException("Internal error: HouseholdQuery dependency not provided.")

            # Validate household_num
            if not household_num or not isinstance(household_num, str) or not household_num.strip():
                self._logger.warning("Invalid household number provided.")
                raise MembershipException("Please provide a valid household number.")
            household = self._household_query.search_households_by_num(household_num)
            if not household or len(household) == 0:
                self._logger.info(f"No household found for number '{household_num}'.")
                raise MembershipException(f"No household found for number '{household_num}'. Please check and try again.")
            if len(household) > 1:
                self._logger.warning(f"Multiple households found for number '{household_num}'.")
                raise MembershipException(f"Multiple households found for number '{household_num}'. Please contact support.")
            household_id = household[0]["household_id"] if isinstance(household[0], dict) else household[0].household_id

            # Validate added_by_id
            if not isinstance(added_by_id, int) or added_by_id <= 0:
                self._logger.warning("Invalid added_by_id provided.")
                raise MembershipException("Please provide a valid staff/user ID for 'added by'.")

            # Validate family_num
            if not family_num or not isinstance(family_num, str) or not family_num.strip():
                self._logger.warning("Invalid family number provided.")
                raise MembershipException("Please provide a valid family number.")

            # Validate ufc_num
            if not ufc_num or not isinstance(ufc_num, str) or not ufc_num.strip():
                self._logger.warning("Invalid UFC number provided.")
                raise MembershipException("Please provide a valid UFC number.")

            # Validate source_of_income
            if not source_of_income or not isinstance(source_of_income, str) or not source_of_income.strip():
                self._logger.warning("Invalid source_of_income provided.")
                raise MembershipException("Please provide a valid source of income.")

            # Validate family_mnthly_icnome_id
            if not isinstance(family_mnthly_icnome_id, int) or family_mnthly_icnome_id <= 0:
                self._logger.warning("Invalid family_mnthly_icnome_id provided.")
                raise MembershipException("Please select a valid monthly income range.")

            # Validate nhts_status_id
            if not isinstance(nhts_status_id, int) or nhts_status_id <= 0:
                self._logger.warning("Invalid nhts_status_id provided.")
                raise MembershipException("Please select a valid NHTS status.")

            # Validate indigent_status_id
            if not isinstance(indigent_status_id, int) or indigent_status_id <= 0:
                self._logger.warning("Invalid indigent_status_id provided.")
                raise MembershipException("Please select a valid indigent status.")

            # Validate household_type_id
            if not isinstance(household_type_id, int) or household_type_id <= 0:
                self._logger.warning("Invalid household_type_id provided.")
                raise MembershipException("Please select a valid household type.")

            # Validate family_head_id
            if not isinstance(family_head_id, int) or family_head_id <= 0:
                self._logger.warning("Invalid family_head_id provided.")
                raise MembershipException("Please select a valid family head.")

            # Validate rel_to_hhold_head_id
            if not isinstance(rel_to_hhold_head_id, int) or rel_to_hhold_head_id <= 0:
                self._logger.warning("Invalid rel_to_hhold_head_id provided.")
                raise MembershipException("Please select a valid relationship to household head.")

            self._logger.info(f"All validations passed for household_num='{household_num}', family_num='{family_num}'. Proceeding to create family unit.")
            result = self._family_commands.insert_family_unit(
                household_id,
                added_by_id,
                family_num,
                ufc_num,
                source_of_income,
                family_mnthly_icnome_id,
                nhts_status_id,
                indigent_status_id,
                household_type_id,
                family_head_id,
                rel_to_hhold_head_id,
            )
            self._logger.info(f"Family unit created successfully for household_num='{household_num}', family_num='{family_num}'.")
            return result
        except MembershipException as e:
            self._logger.error(f"MembershipException: {str(e)}")
            raise
        except Exception as e:
            self._logger.exception("Unexpected error during family unit creation.")
            raise MembershipException("An unexpected error occurred. Please try again or contact support.")
        
    