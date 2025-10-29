import json
import logging
from django.db import connection, models

logger = logging.getLogger(__name__)

try:
    from psycopg2.extras import Json as PGJson 
    _HAS_PGJSON = True
except Exception:
    _HAS_PGJSON = False

class Secretary(models.Model):
    class Meta:
        managed = False

    @staticmethod 
    def search_resident(p_key): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('search_person_by_code_or_name', [p_key]) 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
                
        except Exception as e: raise e


    @staticmethod 
    def search_staff_by_name(p_key): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('search_staff_by_name', [p_key]) 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
                
        except Exception as e: raise e


    @staticmethod
    def filter_staff_by_role_and_account(p_role_id, p_acc_status_id):
        try:
            with connection.cursor() as cursor:
                cursor.callproc(
                    'filter_staff_by_role_and_account',
                    [p_role_id, p_acc_status_id]
                )
                cols = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            raise e


    @staticmethod
    def filter_staff_by_sched_day_and_account(p_day, p_acc_status_id):
        try:
            with connection.cursor() as cursor:
                cursor.callproc(
                    'filter_staff_by_sched_day_and_account',
                    [p_day, p_acc_status_id]
                )
                cols = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            raise e
        
    
    @staticmethod
    def filter_staff_by_purok_and_account(p_purok_sitio_id, p_acc_status_id):
        try:
            with connection.cursor() as cursor:
                cursor.callproc(
                    'filter_staff_by_purok_and_account',
                    [p_purok_sitio_id, p_acc_status_id]
                )
                cols = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            raise e


    @staticmethod 
    def get_resident_details(person_id): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('get_specific_resident_full_profile', [person_id]) 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
        except Exception as e: raise e


    @staticmethod 
    def get_all_staff_info_summary(): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('get_all_staff_info_summary') 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
        except Exception as e: raise e


    @staticmethod 
    def get_staff_profile_display(p_staff_id): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('get_staff_profile_display', [p_staff_id]) 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
        except Exception as e: raise e


    @staticmethod
    def insert_res_staff_account_request(
        p_requested_by_id,
        p_person_id=None,
        p_role_id=None,
        p_supporting_docs=None,
        p_lupon_sched=None,
        p_bhw_purok_ids=None,
    ):

        # Precompute for exception log safety
        _docs_for_log  = p_supporting_docs if p_supporting_docs else None
        _sched_for_log = p_lupon_sched if p_lupon_sched else None
        _purok_for_log = p_bhw_purok_ids if p_bhw_purok_ids else None

        try:
            with connection.cursor() as cursor:
                # Normalize payloads
                sched_payload = None if not p_lupon_sched else p_lupon_sched
                purok_payload = None if not p_bhw_purok_ids else p_bhw_purok_ids
                docs_payload  = None if not p_supporting_docs else p_supporting_docs

                logger.info(
                    "DB ▶ insert_staff_account_request(by=%s, person=%s, role=%s, proof=%s, sched=%s, puroks=%s)",
                    p_requested_by_id, p_person_id, p_role_id, docs_payload, sched_payload, purok_payload
                )

                if _HAS_PGJSON:
                    cursor.execute(
                        """
                        SELECT out_staff_acc_req_id, out_person_id
                        FROM insert_staff_account_request(%s,%s,%s,%s,%s,%s);
                        """,
                        [
                            p_requested_by_id,
                            p_person_id,
                            p_role_id,
                            docs_payload,
                            PGJson(sched_payload) if sched_payload is not None else None,  # JSONB
                            purok_payload, 
                        ],
                    )
                else:
                    cursor.execute(
                        """
                        SELECT out_staff_acc_req_id, out_person_id
                        FROM insert_staff_account_request(
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
                            docs_payload,
                            json.dumps(sched_payload) if sched_payload is not None else None,
                            purok_payload,
                        ],
                    )

                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("No row returned from insert_staff_account_request().")

                staff_req_id, person_id = row[0], row[1]
                logger.info("DB ✓ insert_staff_account_request → staff_req_id=%s, person_id=%s", staff_req_id, person_id)
                return {"staff_acc_req_id": int(staff_req_id), "person_id": int(person_id)}

        except Exception:
            logger.exception(
                "DB ✗ insert_staff_account_request failed (person=%s role=%s proof=%s sched=%s puroks=%s)",
                p_person_id, p_role_id, _docs_for_log, _sched_for_log, _purok_for_log
            )
            raise



    @staticmethod
    def insert_nonres_staff_account_request(
        p_requested_by_id,
        p_person_id=None,
        p_role_id=None,
        p_supporting_docs=None, 
        p_lupon_sched=None,
        p_bhw_purok_ids=None, 
        # used when p_person_id IS NULL
        p_first_name=None,
        p_last_name=None,
        p_middle_name=None,
        p_suffix=None,
        p_birthdate=None,
        p_email=None,
        p_mobile_num=None,

        # FK ids (when p_person_id IS NULL)
        p_sex_id=None,
        p_civil_status_id=None,
        p_nationality_id=None,
        p_religion_id=None,

        # address (when p_person_id IS NULL)
        p_city=None,
        p_barangay=None,
        p_sitio_purok=None,
        p_street=None,

        # documents
        p_valid_id_front=None,
        p_valid_id_back=None,
        p_valid_id_type_id=None,
        p_selfie_path=None,
    ):

        # For error logs (don’t reference locals defined later)
        _docs_for_log  = p_supporting_docs if p_supporting_docs else None
        _sched_for_log = p_lupon_sched if p_lupon_sched else None
        _purok_for_log = p_bhw_purok_ids if p_bhw_purok_ids else None

        try:
            with connection.cursor() as cursor:
                # Normalize -> send NULLs if empty
                sched_payload = None if not p_lupon_sched else p_lupon_sched
                purok_payload = None if not p_bhw_purok_ids else p_bhw_purok_ids
                docs_payload  = None if not p_supporting_docs else p_supporting_docs 

                logger.info(
                    "DB ▶ insert_staff_account_request(by=%s, person=%s, role=%s, proof=%s, sched=%s, puroks=%s)",
                    p_requested_by_id, p_person_id, p_role_id, docs_payload, sched_payload, purok_payload
                )

                if _HAS_PGJSON:
                    # PGJson adapts to JSONB; lists adapt to PG arrays
                    cursor.execute(
                        """
                        SELECT out_staff_acc_req_id, out_person_id
                        FROM insert_staff_account_request(
                            %s,%s,%s,              -- by, person, role
                            %s,                    -- supporting_docs TEXT[]
                            %s,                    -- lupon_sched JSONB
                            %s,                    -- bhw_purok_ids INT[]
                            %s,%s,%s,%s,%s,%s,%s,  -- first/last/middle/suffix/birthdate/email/mobile
                            %s,%s,%s,%s,           -- sex_id, civil_status_id, nationality_id, religion_id
                            %s,%s,%s,%s,           -- city, barangay, sitio_purok, street
                            %s,%s,%s,%s            -- valid_id_front, valid_id_back, valid_id_type_id, selfie_path
                        );
                        """,
                        [
                            p_requested_by_id,
                            p_person_id,
                            p_role_id,
                            docs_payload,
                            PGJson(sched_payload) if sched_payload is not None else None,
                            purok_payload,

                            p_first_name,
                            p_last_name,
                            p_middle_name,
                            p_suffix,
                            p_birthdate,
                            p_email,
                            p_mobile_num,

                            p_sex_id,
                            p_civil_status_id,
                            p_nationality_id,
                            p_religion_id,

                            p_city,
                            p_barangay,
                            p_sitio_purok,
                            p_street,

                            p_valid_id_front,
                            p_valid_id_back,
                            p_valid_id_type_id,
                            p_selfie_path,
                        ],
                    )
                else:
                    # Fallback: cast JSON/ARRAY explicitly via literals
                    import json as _json

                    def _pg_array_int(vals):
                        if not vals:
                            return None
                        return "{" + ",".join(str(int(v)) for v in vals) + "}"

                    def _pg_array_text(vals):
                        if not vals:
                            return None
                        def esc(s):  # basic quote escape for array literal
                            return '"' + str(s).replace('"', r'\"') + '"'
                        return "{" + ",".join(esc(v) for v in vals) + "}"

                    purok_literal = _pg_array_int(purok_payload)
                    docs_literal  = _pg_array_text(docs_payload)
                    sched_text    = _json.dumps(sched_payload) if sched_payload is not None else None

                    cursor.execute(
                        """
                        SELECT out_staff_acc_req_id, out_person_id
                        FROM insert_staff_account_request(
                            %s,%s,%s,              -- by, person, role
                            %s::text[],            -- supporting_docs
                            %s::jsonb,             -- lupon_sched
                            %s::int[],             -- bhw_purok_ids
                            %s,%s,%s,%s,%s,%s,%s,  -- first/last/middle/suffix/birthdate/email/mobile
                            %s,%s,%s,%s,           -- sex_id, civil_status_id, nationality_id, religion_id
                            %s,%s,%s,%s,           -- city, barangay, sitio_purok, street
                            %s,%s,%s,%s            -- valid_id_front, valid_id_back, valid_id_type_id, selfie_path
                        );
                        """,
                        [
                            p_requested_by_id,
                            p_person_id,
                            p_role_id,
                            docs_literal,
                            sched_text,
                            purok_literal,

                            p_first_name,
                            p_last_name,
                            p_middle_name,
                            p_suffix,
                            p_birthdate,
                            p_email,
                            p_mobile_num,

                            p_sex_id,
                            p_civil_status_id,
                            p_nationality_id,
                            p_religion_id,

                            p_city,
                            p_barangay,
                            p_sitio_purok,
                            p_street,

                            p_valid_id_front,
                            p_valid_id_back,
                            p_valid_id_type_id,
                            p_selfie_path,
                        ],
                    )

                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("No row returned from insert_staff_account_request().")

                staff_req_id, person_id = row[0], row[1]
                logger.info(
                    "DB ✓ insert_staff_account_request → staff_req_id=%s, person_id=%s",
                    staff_req_id, person_id
                )
                return {"staff_acc_req_id": int(staff_req_id), "person_id": int(person_id)}

        except Exception:
            logger.exception(
                "DB ✗ insert_staff_account_request failed (person=%s role=%s proof=%s sched=%s puroks=%s)",
                p_person_id, p_role_id, _docs_for_log, _sched_for_log, _purok_for_log
            )
            raise
