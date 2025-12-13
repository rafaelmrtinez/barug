from logging import Logger
from src.infra.repositories.commands.household_commands import HouseholdCommand
from src.infra.exceptions.household_update_exception import HouseholdUpdateException
from src.infra.repositories.queries.household_queries import HouseholdQuery

class HouseholdUpdateService:

    def __init__(self, household_cmd: HouseholdCommand, logger: Logger, household_query: HouseholdQuery = None):
        self._household_cmd = household_cmd
        self._logger = logger
        self._household_query = household_query

    def update_family_info(self, payload: dict, added_by_id: int):
        self._logger.info("Updating family info...")
        try:
            # Required keys: performed_by, family_id, reason, source_of_income, family_mnthly_icnome_id, nhts_status_id, indigent_status_id, household_type_id, household_id, family_head_id, rel_to_hhold_head_id
            try:
                performed_by = int(added_by_id)
                family_id = int(payload["family_id"])
                reason = str(payload["reason"]).strip()
                source_of_income = str(payload["source_of_income"]).strip()
                family_mnthly_icnome_id = int(payload["family_mnthly_icnome_id"])
                nhts_status_id = int(payload["nhts_status_id"])
                indigent_status_id = int(payload["indigent_status_id"])
                household_type_id = int(payload["household_type_id"])
                household_id = int(payload["household_id"])
                try:
                    family_head_id = int(payload["family_head_id"])
                except (KeyError, TypeError, ValueError):
                    family_head_id = self._household_query.search_family_unit_by_id(family_id)[0]['family_head_id']
                rel_to_hhold_head_id = int(payload["family_id"])
            except KeyError as e:
                self._logger.error(f"Missing required payload key: {e}")
                raise
            except (TypeError, ValueError) as e:
                self._logger.error(f"Invalid data type in payload: {e}")
                raise

            variables = [
                ('performed_by', performed_by),
                ('family_id', family_id),
                ('reason', reason),
                ('source_of_income', source_of_income),
                ('family_mnthly_icnome_id', family_mnthly_icnome_id),
                ('nhts_status_id', nhts_status_id),
                ('indigent_status_id', indigent_status_id),
                ('household_type_id', household_type_id),
                ('household_id', household_id),
                ('family_head_id', family_head_id),
                ('rel_to_hhold_head_id', rel_to_hhold_head_id)
            ]
            for var_name, var_value in variables:
                if var_value is None or (isinstance(var_value, str) and not var_value):
                    self._logger.error(f"{var_name} cannot be None or empty.")
                    raise ValueError(f"{var_name} cannot be None or empty.")

            result = self._household_cmd.update_fam_info(
                p_performed_by=performed_by,
                p_family_id=family_id,
                p_reason=reason,
                p_source_of_income=source_of_income,
                p_family_mnthly_icnome_id=family_mnthly_icnome_id,
                p_nhts_status_id=nhts_status_id,
                p_indigent_status_id=indigent_status_id,
                p_household_type_id=household_type_id,
                p_household_id=household_id,
                p_family_head_id=family_head_id,
                p_rel_to_hhold_head_id=rel_to_hhold_head_id
            )
            self._logger.info(f"Family info updated, result: {result}")
            return result
        except HouseholdUpdateException as hue:
            self._logger.error(f"HouseholdUpdateException: {hue}")
            raise
        except Exception as exc:
            self._logger.error(f"Unhandled exception in update_family_info: {exc}")
            raise

    def change_family_head(self, payload: dict, added_by_id: int):
        self._logger.info("Changing family head...")
        try:
            # Required keys: family_id, new_head_person_id, performed_by, reason
            try:
                family_id = int(payload["family_id"])
                new_head_person_id = int(payload["new_head_person_id"])
                performed_by = int(added_by_id)
                reason = str(payload["reason"]).strip()
            except KeyError as e:
                self._logger.error(f"Missing required payload key: {e}")
                raise
            except (TypeError, ValueError) as e:
                self._logger.error(f"Invalid data type in payload: {e}")
                raise

            variables = [
                ('family_id', family_id),
                ('new_head_person_id', new_head_person_id),
                ('reason', reason),
                ('performed_by', performed_by)
            ]
            for var_name, var_value in variables:
                if var_value is None or (isinstance(var_value, str) and not var_value):
                    self._logger.error(f"{var_name} cannot be None or empty.")
                    raise ValueError(f"{var_name} cannot be None or empty.")

            result = self._household_cmd.change_family_head(
                p_family_id=family_id,
                p_new_head_person_id=new_head_person_id,
                p_performed_by=performed_by,
                p_reason=reason
            )
            self._logger.info(f"Family head changed, result: {result}")
            return result
        except HouseholdUpdateException as hue:
            self._logger.error(f"HouseholdUpdateException: {hue}")
            raise
        except Exception as exc:
            self._logger.error(f"Unhandled exception in change_family_head: {exc}")
            raise

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
        