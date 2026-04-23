# lupon_mem/services/hearings_window.py
from typing import Optional, Dict, Any
from django.db import connection

def get_hearing_window(case_id: int) -> Optional[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM fn_case_hearing_window(%s)", [case_id])
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.cursor.description] if hasattr(cur, "cursor") else [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        # Normalize keys your template reads:
        return {
            "can_set_mediation":      bool(data.get("can_set_mediation")),
            "can_set_conciliation":   bool(data.get("can_set_conciliation")),
            "window_end_date_text":   data.get("window_end_date_text"),
            "window_end_time_text":   data.get("window_end_time_text"),
            "days_left":              int(data.get("days_left") or 0),
            "mediation_hearings_set": int(data.get("mediation_hearings_set") or 0),
            "mediation_hearings_held":int(data.get("mediation_hearings_held") or 0),
        }
