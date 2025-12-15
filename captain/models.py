import json
import logging
from typing import Optional
from django.db import DatabaseError, transaction
from django.db import connection, models

logger = logging.getLogger(__name__)

try:
    from psycopg2.extras import Json as PGJson  # JSONB adapter (psycopg2)
    _HAS_PGJSON = True
except Exception:
    _HAS_PGJSON = False

class Captain(models.Model):
    class Meta:
        managed = False

    @staticmethod
    def list_requests():
        try:
            with connection.cursor() as cursor:
                cursor.callproc('get_staff_account_req_list', [])
                cols = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            logger.error("Error listing staff account requests: %s", e)
            return []
        

    @staticmethod 
    def get_pending_staff_details(p_staff_acc_req_id): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('get_staff_acc_req_profile', [p_staff_acc_req_id]) 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
        except Exception as e: raise e

    @staticmethod
    def process_staff_account_request_approval(
        p_staff_acc_req_id: int,
        p_approver_id: int,
        p_request_status_id: int,
        p_remarks: str | None = None,
    ) -> str | None:

        try:
            with connection.cursor() as cursor:
                logger.info(
                    "DB > process_staff_account_request_approval(req_id=%s, by=%s, new_status=%s, remarks=%s)",
                    p_staff_acc_req_id, p_approver_id, p_request_status_id, p_remarks
                )

                # Using SELECT … ensures we can reliably fetch the scalar TEXT return value
                cursor.execute(
                    "SELECT process_staff_account_request_approval(%s, %s, %s, %s)",
                    [p_staff_acc_req_id, p_approver_id, p_request_status_id, p_remarks]
                )

                row = cursor.fetchone()
                result_text = row[0] if row else None  # 'REJECTED' or staff_code

                logger.info(
                    "DB OK process_staff_account_request_approval(req_id=%s) result=%s",
                    p_staff_acc_req_id, result_text
                )
                return result_text

        except Exception:
            logger.exception(
                "DB ERROR process_staff_account_request_approval failed (req_id=%s, by=%s, new_status=%s, remarks=%s)",
                p_staff_acc_req_id, p_approver_id, p_request_status_id, p_remarks
            )
            raise

    @staticmethod
    def upsert_staff_credentials_and_log(
        p_staff_id: int,
        p_username: str,
        p_password_plain: str,
        p_sender_staff_id: int,
        p_is_credentials_sent: Optional[bool] = None,
    ) -> bool:
        """
        Calls: upsert_staff_credentials_and_log(
            p_staff_id INT,
            p_username TEXT,
            p_password_plain TEXT,
            p_sender_staff_id INT,
            p_is_credentials_sent BOOLEAN DEFAULT NULL
        ) RETURNS BOOLEAN
        """
        if p_is_credentials_sent is None:
            # Postgres NULL (don't log "sent")
            sent_arg = None
        else:
            # Ensure proper boolean for psycopg2
            sent_arg = bool(p_is_credentials_sent)

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Using SELECT to fetch the boolean result explicitly
                    cursor.execute(
                        """
                        SELECT upsert_staff_credentials_and_log(%s, %s, %s, %s, %s);
                        """,
                        [p_staff_id, p_username, p_password_plain, p_sender_staff_id, sent_arg],
                    )
                    row = cursor.fetchone()
                    return bool(row[0]) if row is not None else False

                    # If you prefer the callproc style (works in many setups):
                    # cursor.callproc(
                    #     'upsert_staff_credentials_and_log',
                    #     [p_staff_id, p_username, p_password_plain, p_sender_staff_id, sent_arg]
                    # )
                    # row = cursor.fetchone()
                    # return bool(row[0]) if row is not None else False

        except DatabaseError as db_err:
            # Re-raise so callers can flash a DB-specific message
            raise db_err
        except Exception as e:
            # Non-DB errors (validation, type issues, etc.)
            raise e