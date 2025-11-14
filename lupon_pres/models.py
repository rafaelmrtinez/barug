from django.db import models, connection
import json
import logging

logger = logging.getLogger(__name__)

class LuponPres:
    @staticmethod
    def update_staff_assigned_sched(staff_id, updated_by_staff_id, schedules_json):
        """
        Update staff assigned schedule using the database function.
        
        Args:
            staff_id: ID of the staff member
            updated_by_staff_id: ID of the staff member making the update
            schedules_json: List of schedule dictionaries with day, time_start, time_end
        
        Returns:
            Dict with staff_id, sched_added_count, sched_removed_count
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM update_staff_assigned_sched(%s, %s, %s)",
                    [staff_id, updated_by_staff_id, json.dumps(schedules_json) if schedules_json else None]
                )
                result = cursor.fetchone()
                
                if result:
                    return {
                        'staff_id': result[0],
                        'sched_added_count': result[1],
                        'sched_removed_count': result[2]
                    }
                return None
                
        except Exception as e:
            logger.exception("Error updating staff schedule: %s", e)
            raise
# lupon_pres/models.py
from django.db import models

# Create your models here.

# Note: lupon_pres uses the same database models as lupon_mem
# The models are defined in the shared database schema and accessed
# through raw SQL queries in the services layer.

# Key models that would be used (defined elsewhere in the system):
# - BlotterCase
# - BlotterKpSubmission  
# - KpForm
# - KpField
# - BlotterKpAnswer
# - CaseProgressTracking
# - CaseProgressType
# - SettlementStatus
# - CaseState
# - Person
# - Staff

class BlotterKpSubmission(models.Model):
    """Proxy model for blotter_kp_submission table"""
    class Meta:
        managed = False
        db_table = 'blotter_kp_submission'

class KpFormField(models.Model):
    """Proxy model for kp_form_field table"""
    class Meta:
        managed = False
        db_table = 'kp_form_field'

class KpField(models.Model):
    """Proxy model for kp_field table"""
    class Meta:
        managed = False
        db_table = 'kp_field'

class BlotterKpAnswer(models.Model):
    """Proxy model for blotter_kp_answer table"""
    class Meta:
        managed = False
        db_table = 'blotter_kp_answer'
