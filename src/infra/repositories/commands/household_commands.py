from typing import Optional

import logging

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.household_update_exception import HouseholdUpdateException
from src.infra.exceptions.membership_exception import MembershipException

logger = logging.getLogger(__name__)


class HouseholdCommand:
    
    def __init__(self, ctx: ConnectionAdapter):
        self._ctx = ctx
        
    def update_fam_info(
        self,
        p_performed_by: int,
        p_family_id: int,
        p_reason: str,
        p_source_of_income: str,
        p_family_mnthly_icnome_id: int,
        p_nhts_status_id: int,
        p_indigent_status_id: int,
        p_household_type_id: int,
        p_household_id: int,
        p_family_head_id: int,
        p_rel_to_hhold_head_id: int
    ) -> Optional[int]:
        """
        Call the database function `update_fam_info` and return its result.
        Args:
            p_performed_by: User ID performing the update
            p_family_id: Family ID to update
            p_reason: Reason for the update
            p_source_of_income: Source of income
            p_family_mnthly_icnome_id: Family monthly income ID
            p_nhts_status_id: NHTS status ID
            p_indigent_status_id: Indigent status ID
            p_household_type_id: Household type ID
            p_household_id: Household ID
            p_family_head_id: Family head ID
            p_rel_to_hhold_head_id: Relationship to household head ID
        Returns:
            The result of the function (e.g., updated family id or status), or None.
        Raises:
            MembershipException if a known membership error occurs.
        """
        sql = "SELECT update_fam_info(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        params = (
            p_performed_by,
            p_family_id,
            p_reason,
            p_source_of_income,
            p_family_mnthly_icnome_id,
            p_nhts_status_id,
            p_indigent_status_id,
            p_household_type_id,
            p_household_id,
            p_family_head_id,
            p_rel_to_hhold_head_id
        )
        try:
            logger.info('Calling update_fam_info with params=%s', params)
            result = None
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                result = self._ctx.execute_query(sql, params)
            logger.info('update_fam_info returned %s', result)
            return result
        except Exception as exc:
            pgcode = getattr(exc, 'pgcode', None)
            if pgcode and HouseholdUpdateException.is_household_update_exception(pgcode):
                raise HouseholdUpdateException(str(exc)) from exc
            try:
                msg = str(exc)
                if any(code in msg for code in HouseholdUpdateException.ERROR_CODES):
                    logger.warning('Raising HouseholdUpdateException for message: %s', msg)
                    raise HouseholdUpdateException(msg) from exc
            except Exception:
                logger.error('Failed to inspect exception message for HouseholdUpdateException mapping.')
                pass
            raise

    # Command to invoke the change_family_head SQL function
    def change_family_head(p_family_id: int, p_new_head_person_id: int, p_performed_by: int, p_reason: str):
        """
        Invokes the change_family_head SQL function to update the family head.
        Args:
            p_family_id (int): The family ID.
            p_new_head_person_id (int): The new head's person ID.
            p_performed_by (int): The user performing the change.
            p_reason (str): Reason for the change.
        Returns:
            The result of the SQL function execution.
        """
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM change_family_head(%s, %s, %s, %s)", [
                p_family_id,
                p_new_head_person_id,
                p_performed_by,
                p_reason
            ])
            result = cursor.fetchone()
        return result

    def update_hhold_info(
        self,
        p_performed_by: int,
        p_household_id: int,
        p_reason: str,
        p_house_type_id: int,
        p_house_ownership_id: int,
        p_city: str,
        p_barangay: str,
        p_street: str,
        p_purok_sitio_name: str,
        p_latitude: float,
        p_longitude: float
    ) -> Optional[int]:
        """
        Call the database function `update_hhold_info` and return its result.
        Args:
            p_performed_by: User ID performing the update
            p_household_id: Household ID to update
            p_reason: Reason for the update
            p_house_type_id: House type ID
            p_house_ownership_id: House ownership ID
            p_city: City name
            p_barangay: Barangay name
            p_street: Street name
            p_purok_sitio_name: Purok/Sitio name
            p_latitude: Latitude
            p_longitude: Longitude
        Returns:
            The result of the function (e.g., updated household id or status), or None.
        Raises:
            MembershipException if a known membership error occurs.
        """
        sql = "SELECT update_hhold_info(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        params = (
            p_performed_by,
            p_household_id,
            p_reason,
            p_house_type_id,
            p_house_ownership_id,
            p_city,
            p_barangay,
            p_street,
            p_purok_sitio_name,
            p_latitude,
            p_longitude
        )
        try:
            logger.info('Calling update_hhold_info with params=%s', params)
            result = None
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                result = self._ctx.execute_query(sql, params)
            logger.info('update_hhold_info returned %s', result)
            return result
        except Exception as exc:
            pgcode = getattr(exc, 'pgcode', None)
            if pgcode and HouseholdUpdateException.is_household_update_exception(pgcode):
                raise HouseholdUpdateException(str(exc)) from exc
            try:
                msg = str(exc)
                if any(code in msg for code in HouseholdUpdateException.ERROR_CODES):
                    logger.warning('Raising HouseholdUpdateException for message: %s', msg)
                    raise HouseholdUpdateException(msg) from exc
            except Exception:
                logger.error('Failed to inspect exception message for HouseholdUpdateException mapping.')
                pass
            raise

    def insert_house_member(
        self,
        p_family_id: int,
        p_added_by_id: int,
        p_existing_person_id: int,
        p_relationship_to_hholdhead_id: int,
        p_relationship_to_family_head_id: int,
    ) -> Optional[int]:
        """
        Call the database stored procedure `insert_house_member` and return
        the created member id (if the procedure returns one).
        """
        sql = (
            "SELECT insert_house_member(%s, %s, %s, %s, %s)"
        )
        params = (
            p_family_id,
            p_added_by_id,
            p_existing_person_id,
            p_relationship_to_hholdhead_id,
            p_relationship_to_family_head_id,
        )
        try:
            logger.info('Calling insert_house_member stored-proc with params=%s', params)
            result = None
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                result = self._ctx.execute_query(sql, params)
            logger.info('insert_house_member returned %s', result)
            return result
        except Exception as exc:
            pgcode = getattr(exc, 'code', None)
            if pgcode and MembershipException.is_membership_exception(pgcode):
                raise MembershipException(str(exc.message)) from exc
            try:
                msg = str(exc)
                if any(code in msg for code in MembershipException.ERROR_CODES):
                    logger.warning('Raising MembershipException for message: %s', msg)
                    raise MembershipException(msg) from exc
            except Exception:
                logger.error('Failed to inspect exception message for MembershipException mapping.')
                pass
            raise
    
    def change_household_head(
        self,
        p_household_id: int,
        p_new_head_person_id: int,
        p_performed_by: int,
        p_reason: str
    ) -> Optional[int]:
        """
        Call the database function `change_household_head` and return its result.
        Args:
            p_household_id: ID of the household to update
            p_new_head_person_id: Person ID of the new household head
            p_performed_by: User ID performing the change
            p_reason: Reason for the change
        Returns:
            The result of the function (e.g., updated household id or status), or None.
        Raises:
            MembershipException if a known membership error occurs.
        """
        sql = "SELECT change_household_head(%s, %s, %s, %s)"
        params = (
            p_household_id,
            p_new_head_person_id,
            p_performed_by,
            p_reason,
        )
        try:
            logger.info('Calling change_household_head with params=%s', params)
            result = None
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                result = self._ctx.execute_query(sql, params)
            logger.info('change_household_head returned %s', result)
            return result
        except Exception as exc:
            pgcode = getattr(exc, 'pgcode', None)
            if pgcode and HouseholdUpdateException.is_household_update_exception(pgcode):
                raise HouseholdUpdateException(str(exc)) from exc
            try:
                msg = str(exc)
                if any(code in msg for code in HouseholdUpdateException.ERROR_CODES):
                    logger.warning('Raising HouseholdUpdateException for message: %s', msg)                    
                    raise HouseholdUpdateException(msg) from exc
            except Exception:
                logger.error('Failed to inspect exception message for HouseholdUpdateException mapping.')
                pass
            raise

    def insert_household(
        self,
        p_house_type_id: int,
        p_house_ownership_id: int,
        p_city: str,
        p_barangay: str,
        p_sitio_purok: str,
        p_street: str,
        p_added_by_id: int,
        p_household_num: str,
        p_house_num: str,
        p_household_head_id: int,
        p_latitude: Optional[float] = None,
        p_longitude: Optional[float] = None,
    ) -> Optional[int]:
        """Call the database stored procedure `insert_household` and return
        the created household id (if the procedure returns one).

        The procedure is expected to accept the parameters listed in the
        method signature in the same order.
        """
        sql = (
            "SELECT insert_household(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
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
            p_latitude if p_latitude is not None else None,
            p_longitude if p_longitude is not None else None,
        )

        # Prefer a scalar return; many adapters provide `execute_scalar`.
        try:
            logger.debug('Calling insert_household stored-proc with params=%s', params)
            result = None
            # use execute_scalar if available on the adapter
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                # fallback to a general query execution (may return rows)
                result = self._ctx.execute_query(sql, params)

            logger.debug('insert_household returned %s', result)
            return result
        except Exception as exc:
            # If the underlying DB error exposes a Postgres error code (pgcode),
            # map known membership error codes to a domain exception so callers
            # (e.g. API views) can return user-friendly responses.
            pgcode = getattr(exc, 'pgcode', None)
            if pgcode and MembershipException.is_membership_exception(pgcode):
                raise MembershipException(str(exc)) from exc

            # Some adapters may wrap the original exception; try to inspect args
            # for a textual code like 'P6035'. Fall back to re-raising the
            # original exception if no mapping applies.
            try:
                # look for known code in exception message
                msg = str(exc)
                if any(code in msg for code in MembershipException.ERROR_CODES):
                    raise MembershipException(msg) from exc
            except Exception:
                pass

            # Unmapped exception: re-raise for caller to handle/log.
            raise

