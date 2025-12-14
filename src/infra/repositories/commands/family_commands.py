from src.infra.database.connection_adapter import ConnectionAdapter

import logging
from typing import Optional
from src.infra.exceptions.membership_exception import MembershipException

logger = logging.getLogger(__name__)

class FamilyCommands:

    def __init__(self, ctx: ConnectionAdapter):
        self._ctx = ctx

    def insert_family_unit(
        self,
        p_household_id: int,
        p_added_by_id: int,
        p_family_num: str,
        p_ufc_num: str,
        p_source_of_income: str,
        p_family_mnthly_icnome_id: int,
        p_nhts_status_id: int,
        p_indigent_status_id: int,
        p_household_type_id: int,
        p_family_head_id: int,
        p_rel_to_hhold_head_id: int,
    ) -> Optional[int]:
        """Call the database stored procedure `insert_family_unit` and return
        the created family unit id (if the procedure returns one).

        The procedure is expected to accept the parameters listed in the
        method signature in the same order.
        """
        sql = (
            "SELECT insert_family_unit(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
            p_household_id,
            p_added_by_id,
            p_family_num,
            p_ufc_num,
            p_source_of_income,
            p_family_mnthly_icnome_id,
            p_nhts_status_id,
            p_indigent_status_id,
            p_household_type_id,
            p_family_head_id,
            p_rel_to_hhold_head_id,
        )

        try:
            logger.debug('Calling insert_family_unit stored-proc with params=%s', params)
            result = None
            if hasattr(self._ctx, 'execute_scalar'):
                result = self._ctx.execute_scalar(sql, params)
            else:
                result = self._ctx.execute_query(sql, params)
            logger.debug('insert_family_unit returned %s', result)
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
        
    