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