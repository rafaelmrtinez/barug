
import logging
from src.infra.repositories.commands.household_commands import HouseholdCommand
from src.infra.repositories.queries.household_queries import HouseholdQuery
from src.infra.exceptions.membership_exception import MembershipException


class HouseholdMembershipService:

    def __init__(
        self,
        household_command: HouseholdCommand | None = None,
        household_query: HouseholdQuery | None = None):
        self._household_command = household_command
        self._household_query = household_query
        self._logger = logging.getLogger(self.__class__.__name__)


    def add_household_members(
        self,
        members_payload: list[dict],
        added_by_id: int
    ) -> list:
        """
        Insert multiple household members by calling insert_house_member for each record in the payload.
        Each dict in members_payload should have keys:
            - p_family_id
            - p_added_by_id
            - p_existing_person_id
            - p_relationship_to_hholdhead_id
            - p_relationship_to_family_head_id
        Returns a list of results (inserted IDs or None). If an error occurs, returns a dict with 'error' and 'index'.
        """
        self._logger.info(f"Starting add_household_members: {len(members_payload)} members, added_by_id={added_by_id}")
        results = []
        try:
            for idx, member in enumerate(members_payload):
                person_name = member.get('person_name', 'Unknown')
                person_id = member.get('p_existing_person_id')
                family_num = member.get('p_family_id')  # Actually a family_num
                self._logger.debug(f"Adding member {idx}: {person_name} (person_id={person_id}, family_num={family_num})")

                # Resolve family_id from family_num
                family_unit_result = self._household_query.search_family_unit_by_num(family_num)
                if not family_unit_result or not isinstance(family_unit_result, list) or not family_unit_result[0].get('family_id'):
                    error_msg = f"{person_name} - Family unit not found for family_num {family_num}."
                    self._logger.warning(error_msg)
                    results.append({'error': error_msg, 'index': idx})
                    continue
                family_id = family_unit_result[0]['family_id']
                household_id = family_unit_result[0].get('household_id')

                # Domain Rule 1: Prevent duplicate membership
                if self._household_query.is_person_already_house_member(person_id):
                    error_msg = f"{person_name} - This person is already a member of a household."
                    self._logger.warning(error_msg)
                    results.append({'error': error_msg, 'index': idx})
                    continue

                # Domain Rule 2: Only allow insertion if household and family unit are active
                if not household_id:
                    error_msg = f"{person_name} - Household ID not found for family_num {family_num}."
                    self._logger.warning(error_msg)
                    results.append({'error': error_msg, 'index': idx})
                    continue
                if not self._household_query.is_household_active(household_id):
                    error_msg = f"{person_name} - Household is not active."
                    self._logger.warning(error_msg)
                    results.append({'error': error_msg, 'index': idx})
                    continue
                if not self._household_query.is_family_unit_active(family_id):
                    error_msg = f"{person_name} - Family unit is not active."
                    self._logger.warning(error_msg)
                    results.append({'error': error_msg, 'index': idx})
                    continue

                try:
                    result = self._household_command.insert_house_member(
                        p_family_id=family_id,
                        p_added_by_id=added_by_id,
                        p_existing_person_id=member['p_existing_person_id'],
                        p_relationship_to_hholdhead_id=member['p_relationship_to_hholdhead_id'],
                        p_relationship_to_family_head_id=member['p_relationship_to_family_head_id'],
                    )
                    results.append(result)
                    self._logger.info(f"Successfully added member: {person_name} (person_id={person_id})")
                except MembershipException as me:
                    error_msg = f"{person_name} - {me.message}"
                    self._logger.warning(f"MembershipException for {person_name} (person_id={person_id}): {me}")
                    results.append({'error': error_msg, 'index': idx})
                except Exception as e:
                    error_msg = f"{person_name} - {str(e)}"
                    self._logger.error(f"Exception for {person_name} (person_id={person_id}): {e}")
                    results.append({'error': error_msg, 'index': idx})
        except Exception as exc:
            self._logger.exception(f"Batch error in add_household_members: {exc}")
            # If the whole batch fails unexpectedly, return a single error
            return [{'error': f"Batch error - {str(exc)}", 'index': 'batch'}]
        return results
