from django.db import connection, models
import logging

logger = logging.getLogger(__name__)

class Authentication(models.Model):
    class Meta:
        managed = False

    @staticmethod
    def get_staff_profile_by_id(staff_id):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM get_staff_profile_display_by_id(%s)", [staff_id])
                cols = [col[0] for col in cursor.description]
                row = cursor.fetchone()
                if row:
                    return dict(zip(cols, row))
                return None
        except Exception:
            raise
    
    @staticmethod
    def set_staff_photo(staff_id, staff_img_path):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_staff_photo(%s, %s)", [staff_id, staff_img_path])
                return cursor.fetchone()[0]
        except Exception:
            raise
    
    @staticmethod
    def check_staff_current_password(staff_id, current_password):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT check_staff_current_password(%s, %s)", [staff_id, current_password])
                return cursor.fetchone()[0]
        except Exception:
            raise
    
    @staticmethod
    def change_staff_password(staff_id, new_password, retyped_password):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT change_staff_password(%s, %s, %s)", [staff_id, new_password, retyped_password])
                return cursor.fetchone()[0]
        except Exception:
            raise
    
    @staticmethod
    def update_person_info(editor_staff_id, person_id, reason, **kwargs):
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT update_person_info(
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, [
                    editor_staff_id, person_id, reason,
                    kwargs.get('first_name'), kwargs.get('middle_name'), kwargs.get('last_name'),
                    kwargs.get('suffix'), kwargs.get('birthdate'), kwargs.get('sex_id'),
                    kwargs.get('civil_status_id'), kwargs.get('nationality_id'), kwargs.get('religion_id'),
                    kwargs.get('email'), kwargs.get('mobile_num'), kwargs.get('occupation'),
                    kwargs.get('mnthly_personal_income_id'), kwargs.get('residential_status_id'),
                    kwargs.get('education_id'), kwargs.get('employment_status_id'), kwargs.get('is_student'),
                    kwargs.get('gov_mem_prog_ids'), kwargs.get('city'), kwargs.get('barangay'),
                    kwargs.get('sitio_purok'), kwargs.get('street'), kwargs.get('province')
                ])
                return cursor.fetchone()[0]
        except Exception as e:
            raise e
    
    @staticmethod
    def update_personal_information(staff_id, updated_by_staff_id, **kwargs):
        """Update personal information using the same approach as staff_dets"""
        try:
            # Extract only the fields that should be passed to update_person_info
            person_fields = {
                'first_name': kwargs.get('first_name'),
                'middle_name': kwargs.get('middle_name'), 
                'last_name': kwargs.get('last_name'),
                'suffix': kwargs.get('suffix'),
                'birthdate': kwargs.get('birthdate'),
                'sex_id': kwargs.get('sex_id'),
                'civil_status_id': kwargs.get('civil_status_id'),
                'nationality_id': kwargs.get('nationality_id'),
                'religion_id': kwargs.get('religion_id'),
                'email': kwargs.get('email'),
                'mobile_num': kwargs.get('mobile_number'),
                'occupation': kwargs.get('occupation'),
                'mnthly_personal_income_id': kwargs.get('monthly_income_id'),
                'residential_status_id': kwargs.get('residential_status_id'),
                'education_id': kwargs.get('education_id'),
                'employment_status_id': kwargs.get('employment_status_id'),
                'is_student': kwargs.get('is_student'),
                'gov_mem_prog_ids': kwargs.get('gov_mem_prog_ids'),
                'city': kwargs.get('city'),
                'barangay': kwargs.get('barangay'),
                'sitio_purok': kwargs.get('sitio_purok'),
                'street': kwargs.get('street'),
                'province': kwargs.get('province')
            }
            
            # Get person_id from staff_id
            with connection.cursor() as cursor:
                cursor.execute("SELECT person_id FROM staff WHERE staff_id = %s", [staff_id])
                row = cursor.fetchone()
                if not row:
                    raise ValueError("Staff not found")
                person_id = row[0]
            
            # Call update_person_info with filtered fields
            reason = kwargs.get('reason', 'Personal information update')
            # Special handling for gov_mem_prog_ids - include even if empty list
            filtered_fields = {k: v for k, v in person_fields.items() if v is not None or k == 'gov_mem_prog_ids'}
            result = Authentication.update_person_info(
                editor_staff_id=updated_by_staff_id,
                person_id=person_id,
                reason=reason,
                **filtered_fields
            )
            
            logger.info("Personal information update result: %s", result)
            return result
            
        except Exception as e:
            logger.error("Failed to update personal information: %s", str(e), exc_info=True)
            raise e
    
    @staticmethod
    def change_person_email(editor_staff_id, person_id, new_email, reason):
        """Change person's email address"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT change_person_email(%s, %s, %s, %s)", 
                             [editor_staff_id, person_id, new_email, reason])
                return cursor.fetchone()[0]
        except Exception:
            raise
    
    @staticmethod
    def change_staff_username(editor_staff_id, staff_id, new_username, reason):
        """Change staff's username"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT change_staff_username(%s, %s, %s, %s)", 
                             [editor_staff_id, staff_id, new_username, reason])
                return cursor.fetchone()[0]
        except Exception:
            raise
    
    @staticmethod
    def _to_int_or_none(val):
        """Helper function to convert value to int or None"""
        try:
            if val in (None, "", "None"):
                return None
            return int(val)
        except (ValueError, TypeError):
            return None