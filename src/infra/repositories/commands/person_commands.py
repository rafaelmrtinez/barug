from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.person_exceptions import PersonException

import logging

from src.infra.exceptions.query_exec_exception import QueryExecutionException

logger = logging.getLogger(__name__)

class PersonCommand:
    
    def __init__(self, conn: ConnectionAdapter):
        self._conn = conn

    def confirm_residency(
        self,
        p_person_id: int,
        p_performed_by: int,
        p_rel_to_hholdhead_id: int,
        p_rel_to_family_head_id: int,
        p_reason: str
    ) -> dict:
        """
        Confirms residency for a person.
        
        Args:
            p_person_id: The ID of the person whose residency is being confirmed
            p_performed_by: The ID of the staff performing the confirmation
            p_rel_to_hholdhead_id: Relationship to household head ID
            p_rel_to_family_head_id: Relationship to family head ID
            p_reason: Reason for confirming residency
            
        Returns:
            dict: Result from the SQL function
            
        Raises:
            PersonException: If the operation fails
        """
        try:
            logger.info(f"Confirming residency for person_id={p_person_id} by staff_id={p_performed_by}")
            
            result = self._conn.execute_query(
                sql="SELECT * FROM confirm_residency(%s, %s, %s, %s, %s);",
                params=(
                    p_person_id,
                    p_performed_by,
                    p_rel_to_hholdhead_id,
                    p_rel_to_family_head_id,
                    p_reason
                )
            )
            
            logger.info(f"Residency confirmed successfully for person_id={p_person_id}")
            return result
            
        except QueryExecutionException as exc:
            logger.error(f"Failed to confirm residency for person_id={p_person_id}: {exc}")
            pgcode = getattr(exc, 'code', None)
            if pgcode and PersonException.is_person_exception(pgcode):
                raise PersonException(exc.message) from exc
            try:
                msg = str(exc)
                if any(code in msg for code in PersonException.ERROR_CODES):
                    logger.warning('Raising PersonException for message: %s', msg)
                    raise PersonException(msg) from exc
            except Exception:
                logger.error('Failed to inspect exception message for PersonException mapping.')
                pass
            logger.error('Error in confirm_residency: %s', exc)
            raise