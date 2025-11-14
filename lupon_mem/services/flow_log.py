# lupon_mem/services/flow_log.py
from __future__ import annotations
from typing import Any, Dict, Optional
from django.db import connection
import json

def log_event(
    *,
    case_id: int,
    action: str,               # 'FORM_ATTACHED' | 'FORM_UPDATED' | 'FORM_DETACHED'
    form_code: Optional[str] = None,
    submission_id: Optional[int] = None,
    actor_staff_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a structured event to lupon_flow_log via SQL function."""
    payload = json.dumps(details or {}, ensure_ascii=False)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT public.log_flow_event(%s,%s,%s,%s,%s,%s::jsonb)",
            [case_id, action, form_code, submission_id, actor_staff_id, payload],
        )
