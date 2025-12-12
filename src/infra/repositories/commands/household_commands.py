from typing import Optional

import logging

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.membership_exception import MembershipException

logger = logging.getLogger(__name__)


class HouseholdCommand:

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
            logger.debug('Calling insert_house_member stored-proc with params=%s', params)
            result = None
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                result = self._ctx.execute_query(sql, params)
            logger.debug('insert_house_member returned %s', result)
            return result
        except Exception as exc:
            pgcode = getattr(exc, 'code', None)
            if pgcode and MembershipException.is_membership_exception(pgcode):
                raise MembershipException(str(exc.message)) from exc
            try:
                msg = str(exc)
                if any(code in msg for code in MembershipException.ERROR_CODES):
                    raise MembershipException(msg) from exc
            except Exception:
                pass
            raise

    def __init__(self, ctx: ConnectionAdapter):
        self._ctx = ctx

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

