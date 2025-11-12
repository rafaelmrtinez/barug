from django.db import connection, models

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
        except Exception as e:
            raise e
    
    @staticmethod
    def set_staff_photo(staff_id, staff_img_path):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_staff_photo(%s, %s)", [staff_id, staff_img_path])
                return cursor.fetchone()[0]
        except Exception as e:
            raise e
    
    @staticmethod
    def check_staff_current_password(staff_id, current_password):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT check_staff_current_password(%s, %s)", [staff_id, current_password])
                return cursor.fetchone()[0]
        except Exception as e:
            raise e
    
    @staticmethod
    def change_staff_password(staff_id, new_password, retyped_password):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT change_staff_password(%s, %s, %s)", [staff_id, new_password, retyped_password])
                return cursor.fetchone()[0]
        except Exception as e:
            raise e