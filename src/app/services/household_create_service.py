from typing import Optional, Any, Dict

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.commands.household_commands import HouseholdCommand
from src.infra.exceptions.membership_exception import MembershipException


class HouseholdCreateService:
	"""Service layer for household creation.

	This class performs validation and orchestrates calls to repository/command
	layers. It accepts optional dependencies to allow manual dependency
	injection for easier testing.
	"""

	def __init__(self, household_command: Optional[HouseholdCommand] = None):
		self.cmd = household_command

	def validate_payload(self, payload: Dict[str, Any]) -> None:
		"""Validate required fields are present and not None/empty.

		Raises `HouseholdMembershipException` with a clear message when
		required values are missing.
		"""
		required = [
			'p_house_type_id',
			'p_house_ownership_id',
			'p_city',
			'p_barangay',
			'p_household_num',
			'p_house_num',
			'p_household_head_id',
            'p_longitude',
            'p_latitude',
		]
		missing = [k for k in required if payload.get(k) in (None, '')]
		if missing:
			raise MembershipException(f"Missing required fields: {', '.join(missing)}")

	def create_household(self,
			p_house_type_id: int,
			p_house_ownership_id: int,
			p_city: str,
			p_barangay: str,
			p_sitio_purok: Optional[str],
			p_street: Optional[str],
			p_added_by_id: Optional[int],
			p_household_num: str,
			p_house_num: str,
			p_household_head_id: int,
			p_latitude: Optional[float] = None,
			p_longitude: Optional[float] = None,
		) -> Any:
		"""Validate and delegate to the command layer to persist a household.

		Returns whatever the underlying `HouseholdCommand.insert_household`
		returns. Raises `HouseholdMembershipException` on validation errors to
		keep the API layer consistent.
		"""
		payload = {
			'p_house_type_id': p_house_type_id,
			'p_house_ownership_id': p_house_ownership_id,
			'p_city': p_city,
			'p_barangay': p_barangay,
			'p_sitio_purok': p_sitio_purok,
			'p_street': p_street,
			'p_added_by_id': p_added_by_id,
			'p_household_num': p_household_num,
			'p_house_num': p_house_num,
			'p_household_head_id': p_household_head_id,
			'p_latitude': p_latitude,
			'p_longitude': p_longitude,
		}

		# perform validation (raises HouseholdMembershipException on failure)
		self.validate_payload(payload)

		# Delegate to the command layer; let exceptions propagate (API will map them)
		return self.cmd.insert_household(
			p_house_type_id,
			p_house_ownership_id,
			p_city,
			p_barangay,
			p_sitio_purok,
			p_street,
			p_added_by_id,
			p_household_num,
			p_house_num,
			p_household_head_id,
			p_latitude,
			p_longitude,
		)
