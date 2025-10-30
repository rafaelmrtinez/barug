import json
import logging
from django.db import connection, models

logger = logging.getLogger(__name__)

try:
    from psycopg2.extras import Json as PGJson 
    _HAS_PGJSON = True
except Exception:
    _HAS_PGJSON = False

class Admin(models.Model):
    class Meta:
        managed = False

    @staticmethod
    def create_staff_direct(
        p_requested_by_id: int,
        p_person_id: int,
        p_role_id: int | None = None,
        p_supporting_docs: list[str] | None = None,
        p_lupon_sched: list[dict] | None = None,   # [{day:1,time_start:"08:00",time_end:"12:00"}, ...]
        p_bhw_purok_ids: list[int] | None = None,
    ) -> dict:
        """
        Calls create_staff_direct(...) which RETURNS TABLE(out_staff_id INT, out_staff_code TEXT).
        Maps them to {'staff_id': ..., 'staff_code': ...}.
        """
        _docs_for_log  = p_supporting_docs if p_supporting_docs else None
        _sched_for_log = p_lupon_sched if p_lupon_sched else None
        _purok_for_log = p_bhw_purok_ids if p_bhw_purok_ids else None

        try:
            with connection.cursor() as cursor:
                if _HAS_PGJSON:
                    cursor.execute(
                        """
                        SELECT out_staff_id, out_staff_code
                        FROM create_staff_direct(%s,%s,%s,%s,%s,%s);
                        """,
                        [
                            p_requested_by_id,
                            p_person_id,
                            p_role_id,
                            _docs_for_log,
                            PGJson(_sched_for_log) if _sched_for_log is not None else None,
                            _purok_for_log,
                        ],
                    )
                else:
                    cursor.execute(
                        """
                        SELECT out_staff_id, out_staff_code
                        FROM create_staff_direct(
                            %s,%s,%s,
                            %s,            -- supporting_docs TEXT[]
                            %s::jsonb,     -- p_lupon_sched
                            %s::int[]      -- p_bhw_purok_ids
                        );
                        """,
                        [
                            p_requested_by_id,
                            p_person_id,
                            p_role_id,
                            _docs_for_log,
                            json.dumps(_sched_for_log) if _sched_for_log is not None else None,
                            _purok_for_log,
                        ],
                    )

                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("No row returned from create_staff_direct().")

                out_staff_id, out_staff_code = row[0], row[1]
                logger.info(
                    "DB ✓ create_staff_direct → staff_id=%s, staff_code=%s",
                    out_staff_id, out_staff_code
                )
                return {"staff_id": int(out_staff_id), "staff_code": (out_staff_code or "").strip()}

        except Exception:
            logger.exception(
                "DB ✗ create_staff_direct failed (person=%s role=%s proof=%s sched=%s puroks=%s)",
                p_person_id, p_role_id, _docs_for_log, _sched_for_log, _purok_for_log
            )
            raise