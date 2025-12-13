from logging import Logger
from src.infra.repositories.commands.household_commands import HouseholdCommand
from src.infra.exceptions.household_update_exception import HouseholdUpdateException

class HouseholdUpdateService:

    def __init__(self, household_cmd: HouseholdCommand, logger: Logger):
        self._household_cmd = household_cmd
        self._logger = logger

    def update_household_info(self, payload: dict, added_by_id: int):
        self._logger.info("Updating household info...")
        try:
            # Required keys: performed_by, household_id, reason, house_type_id, house_ownership_id, city, barangay, street, purok_sitio_name, latitude, longitude
            try:
                performed_by = int(added_by_id)
                household_id = int(payload["household_id"])
                reason = str(payload["reason"]).strip()
                house_type_id = int(payload["house_type_id"])
                house_ownership_id = int(payload["house_ownership_id"])
                city = str(payload["city"]).strip()
                barangay = str(payload["barangay"]).strip()
                street = str(payload["street"]).strip()
                purok_sitio_name = str(payload["purok_sitio_name"]).strip()
                latitude = float(payload["latitude"])
                longitude = float(payload["longitude"])
            except KeyError as e:
                self._logger.error(f"Missing required payload key: {e}")
                raise
            except (TypeError, ValueError) as e:
                self._logger.error(f"Invalid data type in payload: {e}")
                raise

            variables = [
                ('performed_by', performed_by),
                ('household_id', household_id),
                ('reason', reason),
                ('house_type_id', house_type_id),
                ('house_ownership_id', house_ownership_id),
                ('city', city),
                ('barangay', barangay),
                ('street', street),
                ('purok_sitio_name', purok_sitio_name),
                ('latitude', latitude),
                ('longitude', longitude)
            ]
            for var_name, var_value in variables:
                if var_value is None or (isinstance(var_value, str) and not var_value):
                    self._logger.error(f"{var_name} cannot be None or empty.")
                    raise ValueError(f"{var_name} cannot be None or empty.")

            result = self._household_cmd.update_hhold_info(
                p_performed_by=performed_by,
                p_household_id=household_id,
                p_reason=reason,
                p_house_type_id=house_type_id,
                p_house_ownership_id=house_ownership_id,
                p_city=city,
                p_barangay=barangay,
                p_street=street,
                p_purok_sitio_name=purok_sitio_name,
                p_latitude=latitude,
                p_longitude=longitude
            )
            self._logger.info(f"Household info updated, result: {result}")
            return result
        except HouseholdUpdateException as hue:
            self._logger.error(f"HouseholdUpdateException: {hue}")
            raise
        except Exception as exc:
            self._logger.error(f"Unhandled exception in update_household_info: {exc}")
            raise
        
    def update_household_head(self, payload: dict, added_by_id: int):
        self._logger.info("Updating household head...")
        try:
            # Required keys: household_id, new_head_person_id, performed_by, reason
            try:
                household_id = int(payload["household_id"])
                new_head_person_id = int(payload["new_head_id"])
                performed_by = int(added_by_id)
                reason = str(payload["reason"]).strip()
            except KeyError as e:
                self._logger.error(f"Missing required payload key: {e}")
                raise
            except (TypeError, ValueError) as e:
                self._logger.error(f"Invalid data type in payload: {e}")
                raise

            # None check
            variables = [
                ('household_id', household_id),
                ('new_head_person_id', new_head_person_id),
                ('reason', reason),
                ('performed_by', performed_by)
            ]
            for var_name, var_value in variables:
                if var_value is None or (isinstance(var_value, str) and not var_value):
                    self._logger.error(f"{var_name} cannot be None or empty.")
                    raise ValueError(f"{var_name} cannot be None or empty.")

            result = self._household_cmd.change_household_head(
                p_household_id=household_id,
                p_new_head_person_id=new_head_person_id,
                p_performed_by=performed_by,
                p_reason=reason
            )
            self._logger.info(f"Household head updated, result: {result}")
            return result
        except HouseholdUpdateException as hue:
            self._logger.error(f"HouseholdUpdateException: {hue}")
            raise
        except Exception as exc:
            self._logger.error(f"Unhandled exception in update_household_head: {exc}")
            raise
        