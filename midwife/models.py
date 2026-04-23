from django.db import models, connection
from typing import List, Optional, Dict, Any

class Midwife:
    @staticmethod
    def update_staff_assigned_purok(
        staff_id: int,
        updated_by_staff_id: int,
        purok_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Update staff purok assignments using the database function.
        
        Args:
            staff_id: ID of the staff to update
            updated_by_staff_id: ID of the staff performing the update
            purok_ids: List of purok IDs to assign (None to remove all)
            
        Returns:
            Dict with staff_id, purok_added_count, purok_deactivated_count
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM update_staff_assigned_purok(%s, %s, %s)",
                [staff_id, updated_by_staff_id, purok_ids]
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    'staff_id': result[0],
                    'purok_added_count': result[1],
                    'purok_deactivated_count': result[2]
                }
            return {'staff_id': staff_id, 'purok_added_count': 0, 'purok_deactivated_count': 0}
