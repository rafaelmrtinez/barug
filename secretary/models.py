from django.db import models, connection

class Secretary(models.Model):
    class Meta:
        managed = False

    # @staticmethod
    # def search_resident(p_key: str):
    #     if not p_key:
    #         return []
    #     with connection.cursor() as cursor:
    #         cursor.proc("search_person_by_code_or_name", [p_key])
    #         cols = [c[0] for c in cursor.description]
    #         return [dict(zip(cols, row)) for row in cursor.fetchall()]

    @staticmethod 
    def search_resident(p_key): 
        try: 
            with connection.cursor() as cursor: 
                cursor.callproc('search_person_by_code_or_name', [p_key]) 
                cols = [col[0] for col in cursor.description] 
                rows = cursor.fetchall() 
                return [dict(zip(cols, row)) for row in rows] 
        except Exception as e: raise e

    # @staticmethod
    # def get_resident_details(person_id: int):
    #     if not person_id:
    #         return []
    #     with connection.cursor() as cursor:
    #         cursor.proc("get_specific_resident_full_profile", [person_id])
    #         cols = [c[0] for c in cursor.description]
    #         return [dict(zip(cols, row)) for row in cursor.fetchall()]

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
    def insert_staff_account_request(
        p_requested_by_id,
        p_person_id=None,
        p_role_id=None,

        # used when p_person_id IS NULL
        # p_first_name=None,
        # p_last_name=None,
        # p_middle_name=None,
        # p_suffix=None,
        # p_birthdate=None,
        # p_email=None,
        # p_mobile_num=None,

        # # FK ids (when p_person_id IS NULL)
        # p_sex_id=None,
        # p_civil_status_id=None,
        # p_nationality_id=None,
        # p_religion_id=None,

        # # address (when p_person_id IS NULL)
        # p_city=None,
        # p_barangay=None,
        # p_sitio_purok=None,
        # p_street=None,

        # # documents
        # p_valid_id_front=None,
        # p_valid_id_back=None,
        # p_valid_id_type_id=None,
        # p_selfie_path=None,
        # p_supporting_docs=None,   # Python list[str] -> PG TEXT[]
    ):
        """
        Wraps: insert_staff_account_request(...) RETURNS INT
        Returns: staff_acc_req_id (int)
        """
        try:
            with connection.cursor() as cursor:
                cursor.callproc('insert_staff_account_request', [
                    p_requested_by_id,
                    p_person_id,
                    p_role_id,

                    # p_first_name,
                    # p_last_name,
                    # p_middle_name,
                    # p_suffix,
                    # p_birthdate,
                    # p_email,
                    # p_mobile_num,

                    # p_sex_id,
                    # p_civil_status_id,
                    # p_nationality_id,
                    # p_religion_id,

                    # p_city,
                    # p_barangay,
                    # p_sitio_purok,
                    # p_street,

                    # p_valid_id_front,
                    # p_valid_id_back,
                    # p_valid_id_type_id,
                    # p_selfie_path,
                    # p_supporting_docs,   # psycopg2 adapts list -> TEXT[]
                ])
                row = cursor.fetchone()   # function returns a single INT
                return int(row[0]) if row and row[0] is not None else None
        except Exception as e:
            raise e



    @staticmethod
    def insert_nonres_staff_account_request(
        p_requested_by_id,
        p_person_id=None,
        p_role_id=None,

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
        p_supporting_docs=None,   # Python list[str] -> PG TEXT[]
    ):
        """
        Wraps: insert_staff_account_request(...) RETURNS INT
        Returns: staff_acc_req_id (int)
        """
        try:
            with connection.cursor() as cursor:
                cursor.callproc('insert_staff_account_request', [
                    p_requested_by_id,
                    p_person_id,
                    p_role_id,

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
                    p_supporting_docs,   # psycopg2 adapts list -> TEXT[]
                ])
                row = cursor.fetchone()   # function returns a single INT
                return int(row[0]) if row and row[0] is not None else None
        except Exception as e:
            raise e

