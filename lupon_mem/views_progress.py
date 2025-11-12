# lupon_mem/views_progress.py
from __future__ import annotations
from typing import Any, Dict
from django.http import HttpRequest
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from lupon_mem.services import flow_progress as FP
from lupon_mem.utils.http import json_ok, json_err

@require_http_methods(["GET", "POST"])
@csrf_protect
def flow_progress_api(request: HttpRequest, case_id: int):
    if request.method == "GET":
        data = FP.get_progress(case_id) or {
            "case_id": case_id,
            "current_step": "start",
            "hearing_no": 1,
            "hearing_attempt": 1,
            "reached_steps": [],
            "updated_at": None,
            "updated_by_id": None,
            "history": [],
        }
        return json_ok(data)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            import json
            payload: Dict[str, Any] = json.loads(request.body.decode("utf-8") or "{}")
        else:
            payload = request.POST.dict()

        step             = (payload.get("step") or "start").strip()
        hearing_no       = int(payload.get("hearing_no") or 1)
        hearing_attempt  = int(payload.get("hearing_attempt") or 1)
        append_history   = str(payload.get("append_history") or "true").lower() != "false"

        auth = request.session.get("auth") or {}
        staff_id = auth.get("staff_id")

        FP.save_progress(
            case_id=case_id,
            step=step,
            hearing_no=hearing_no,
            hearing_attempt=hearing_attempt,
            staff_id=staff_id,
            append_history=append_history,
        )
        # Return the fresh state with updated timestamps
        return json_ok(FP.get_progress(case_id))
    except Exception as e:
        return json_err(str(e))
