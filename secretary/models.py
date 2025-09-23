from django.db import models, connection

class Secretary(models.Model):
    class Meta:
        managed = False

    @staticmethod
    def search_resident(p_key: str):
        if not p_key:
            return []
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM search_person_by_code_or_name(%s)", [p_key])
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    @staticmethod
    def get_resident_details(person_id: int):
        if not person_id:
            return []
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM get_specific_resident_full_profile(%s)", [person_id])
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
