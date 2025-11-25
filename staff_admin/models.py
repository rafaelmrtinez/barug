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
        p_lupon_sched: list[dict] | None = None,
        p_bhw_purok_ids: list[int] | None = None,
    ) -> dict:
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
                            %s,
                            %s::jsonb,
                            %s::int[]
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
                return {"staff_id": int(out_staff_id), "staff_code": (out_staff_code or "").strip()}

        except Exception:
            raise

    @staticmethod
    def update_staff_information(
        staff_id: int,
        updated_by_staff_id: int,
        role_id: int,
        acc_status_id: int,
        username: str = None,
        password: str = None,
        email: str = None,
        purok_ids: list[int] = None,
        schedules_json: list[dict] = None
    ) -> dict:
        with connection.cursor() as cursor:
            schedules_jsonb = None
            if schedules_json:
                schedules_jsonb = json.dumps(schedules_json)
            
            cursor.execute("""
                SELECT * FROM update_staff_information(
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
            """, [
                staff_id,
                updated_by_staff_id,
                role_id,
                acc_status_id,
                username,
                password,
                email,
                purok_ids,
                schedules_jsonb
            ])
            
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
            
            return {}

    @staticmethod
    def insert_person_and_staff(
        p_added_by_id: int,
        p_role_id: int,
        p_supporting_docs: list[str] | None = None,
        p_first_name: str = None,
        p_last_name: str = None,
        p_birthdate: str = None,
        p_email: str = None,
        p_mobile_num: str = None,
        p_sex_id: int = None,
        p_civil_status_id: int = None,
        p_nationality_id: int = None,
        p_religion_id: int = None,
        p_city: str = None,
        p_barangay: str = None,
        p_sitio_purok: str = None,
        p_street: str = None,
        p_valid_id_front: str = None,
        p_valid_id_back: str = None,
        p_valid_id_type_id: int = None,
        p_selfie_path: str = None,
        p_lupon_sched: list[dict] | None = None,
        p_bhw_purok_ids: list[int] | None = None,
        p_middle_name: str = None,
        p_suffix: str = None,
    ) -> dict:
        try:
            with connection.cursor() as cursor:
                if _HAS_PGJSON:
                    cursor.execute(
                        """
                        SELECT out_staff_id, out_person_id
                        FROM insert_person_and_staff(
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                        );
                        """,
                        [
                            p_added_by_id, p_role_id, p_supporting_docs,
                            p_first_name, p_last_name, p_birthdate, p_email, p_mobile_num,
                            p_sex_id, p_civil_status_id, p_nationality_id, p_religion_id,
                            p_city, p_barangay, p_sitio_purok, p_street,
                            p_valid_id_front, p_valid_id_back, p_valid_id_type_id, p_selfie_path,
                            PGJson(p_lupon_sched) if p_lupon_sched else None,
                            p_bhw_purok_ids, p_middle_name, p_suffix
                        ],
                    )
                else:
                    cursor.execute(
                        """
                        SELECT out_staff_id, out_person_id
                        FROM insert_person_and_staff(
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s
                        );
                        """,
                        [
                            p_added_by_id, p_role_id, p_supporting_docs,
                            p_first_name, p_last_name, p_birthdate, p_email, p_mobile_num,
                            p_sex_id, p_civil_status_id, p_nationality_id, p_religion_id,
                            p_city, p_barangay, p_sitio_purok, p_street,
                            p_valid_id_front, p_valid_id_back, p_valid_id_type_id, p_selfie_path,
                            json.dumps(p_lupon_sched) if p_lupon_sched else None,
                            p_bhw_purok_ids, p_middle_name, p_suffix
                        ],
                    )

                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("No row returned from insert_person_and_staff().")

                out_staff_id, out_person_id = row[0], row[1]
                return {"staff_id": int(out_staff_id), "person_id": int(out_person_id)}

        except Exception:
            raise

    @staticmethod
    def get_login_logs_with_status():
        """Get login logs with status using the database function"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    login_log_id, login_time, logout_time, active_status,
                    session_duration, user_id, user_type_id, user_type_name,
                    staff_id, staff_code, role_id, role_name, user_name, ip_add
                FROM get_login_logs_with_status()
            """)
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results

    @staticmethod
    def get_login_logs_grouped_by_staff():
        """Get login logs grouped by staff using the database function"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    staff_id, staff_code, user_name, role_id, role_name,
                    total_sessions, active_sessions, last_login_time,
                    last_logout_time, total_session_duration
                FROM get_login_logs_grouped_by_staff()
            """)
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results

    @staticmethod
    def get_login_logs_with_status_for_staff(staff_id: int):
        """Get all login logs for a specific staff member"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    login_log_id, login_time, logout_time, active_status,
                    session_duration, user_id, user_type_id, user_type_name,
                    staff_id, staff_code, role_id, role_name, user_name, ip_add,
                    total_sessions, active_sessions, total_session_duration
                FROM get_login_logs_with_status_for_staff(%s)
            """, [staff_id])
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results

    @staticmethod
    def get_common_logs_with_names():
        """Get operational logs with names using the database function"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    common_log_id, record_affected_id, details, date_time,
                    table_affected, action, field_changed, old_value, new_value,
                    performer_id, performer_name, user_type_id, user_type_name,
                    subsystem_id, subsystem_name
                FROM get_common_logs_with_names()
            """)
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results

    @staticmethod
    def get_common_log_detail(common_log_id: int):
        """Get detailed information for a specific operational log entry"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    common_log_id, record_affected_id, details, date_time,
                    table_affected, action, field_changed, old_value, new_value,
                    reason, performer_id, performer_name, performer_person_code, performer_staff_code,
                    user_type_id, user_type_name, subsystem_id, subsystem_name
                FROM get_common_log_detail(%s)
            """, [common_log_id])
            
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            if row:
                return dict(zip(columns, row))
            return None