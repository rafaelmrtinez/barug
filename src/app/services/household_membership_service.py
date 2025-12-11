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
        results = []
        try:
            for idx, member in enumerate(members_payload):
                try:
                    result = self._household_command.insert_house_member(
                        p_family_id=member['p_family_id'],
                        p_added_by_id=added_by_id,
                        p_existing_person_id=member['p_existing_person_id'],
                        p_relationship_to_hholdhead_id=member['p_relationship_to_hholdhead_id'],
                        p_relationship_to_family_head_id=member['p_relationship_to_family_head_id'],
                    )
                    results.append(result)
                except MembershipException as me:
                    results.append({'membership_error': str(me), 'index': idx})
                except Exception as e:
                    results.append({'error': str(e), 'index': idx})
        except Exception as exc:
            # If the whole batch fails unexpectedly, return a single error
            return [{'error': str(exc), 'index': 'batch'}]
        return results
