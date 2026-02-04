# notifications/views.py
from __future__ import annotations
import json
from typing import Optional
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_POST
from .service import NotifierService, NotifyTarget, PERSON, STAFF
from . import repo
from . import kp as kp_notify

svc = NotifierService()

def _json(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body or "{}")
    except Exception:
        return {}

@require_POST
def register_push_device(request: HttpRequest):
    p = _json(request)
    user_type_id = p.get("user_type_id")  # 1=PERSON, 2=STAFF
    token        = p.get("expo_push_token")
    if not (user_type_id and token):
        return JsonResponse({"ok": False, "error": "missing user_type_id or token"}, status=400)

    svc.register_device(
        user_type_id=user_type_id,
        person_id=p.get("person_id"),
        staff_id=p.get("staff_id"),
        platform=p.get("platform"),
        expo_push_token=token,
    )
    return JsonResponse({"ok": True})

@require_POST
def send_test_push(request: HttpRequest):
    p = _json(request)
    target = NotifyTarget(
        user_type_id=p.get("user_type_id", PERSON),
        person_id=p.get("person_id"),
        staff_id=p.get("staff_id"),
    )
    svc.notify_user(
        target=target,
        title=p.get("title", "Test"),
        body=p.get("body", "Hello from Expo Push"),
        deep_link=p.get("deep_link", "/dashboard"),
    )
    return JsonResponse({"ok": True})

@require_POST
def clear_notifications(request: HttpRequest):
    p = _json(request)
    svc.mark_all_read(
        user_type_id=p.get("user_type_id"),
        person_id=p.get("person_id"),
        staff_id=p.get("staff_id"),
    )
    return JsonResponse({"ok": True})

def list_notifications(request: HttpRequest):
    # Secure with session/role in production
    user_type_id = int(request.GET.get("user_type_id"))
    person_id = request.GET.get("person_id")
    staff_id  = request.GET.get("staff_id")
    data = svc.list_notifications(user_type_id=user_type_id, person_id=person_id, staff_id=staff_id)
    return JsonResponse({"ok": True, "data": data})

# === KP entry points you can call from form handlers ===
def notify_kp7_complaint_filed(case_id: int, case_num: str): kp_notify.kp7_complaint_filed(svc, case_id=case_id, case_num=case_num)
def notify_kp8_hearing_scheduled(case_id: int, case_num: str, hearing_date: str, hearing_time: str): kp_notify.kp8_hearing_scheduled(svc, case_id=case_id, case_num=case_num, hearing_date=hearing_date, hearing_time=hearing_time)
def notify_kp9_summon_issued(case_id: int, case_num: str, hearing_date: str, hearing_time: str): kp_notify.kp9_summon_issued(svc, case_id=case_id, case_num=case_num, hearing_date=hearing_date, hearing_time=hearing_time)

# Examples for generic ones:
def notify_kp10_constitution_pangkat(case_id: int, case_num: str): kp_notify.kp10_pangkat_constituted(svc, case_id=case_id, case_num=case_num)
def notify_kp11_mediation_proceedings(case_id: int, case_num: str): kp_notify.kp11_mediation_proceedings(svc, case_id=case_id, case_num=case_num)
def notify_kp12_hearing_conciliation(case_id: int, case_num: str): kp_notify.kp12_conciliation_notice(svc, case_id=case_id, case_num=case_num)
def notify_kp13_subpoena_letter(case_id: int, case_num: str): kp_notify.kp13_subpoena_letter(svc, case_id=case_id, case_num=case_num)
def notify_kp14_agreement_arbitration(case_id: int, case_num: str): kp_notify.kp14_agreement_arbitration(svc, case_id=case_id, case_num=case_num)
def notify_kp15_arbitration_award(case_id: int, case_num: str): kp_notify.kp15_arbitration_award(svc, case_id=case_id, case_num=case_num)
def notify_kp16_amicable_settlement(case_id: int, case_num: str): kp_notify.kp16_amicable_settlement(svc, case_id=case_id, case_num=case_num)
def notify_kp17_repudiation(case_id: int, case_num: str): kp_notify.kp17_repudiation(svc, case_id=case_id, case_num=case_num)
def notify_kp18_hearing_complainant(case_id: int, case_num: str): kp_notify.kp18_hearing_complainant(svc, case_id=case_id, case_num=case_num)
def notify_kp19_hearing_respondent(case_id: int, case_num: str): kp_notify.kp19_hearing_respondent(svc, case_id=case_id, case_num=case_num)
def notify_kp20_certification_file_action(case_id: int, case_num: str): kp_notify.kp20_certification_file_action(svc, case_id=case_id, case_num=case_num)
def notify_kp21_certification_bar_action(case_id: int, case_num: str): kp_notify.kp21_certification_bar_action(svc, case_id=case_id, case_num=case_num)
def notify_kp22_certification_bar_action_respondent(case_id: int, case_num: str): kp_notify.kp22_certification_bar_action_respondent(svc, case_id=case_id, case_num=case_num)
def notify_kp23_execution_settlement(case_id: int, case_num: str): kp_notify.kp23_execution_settlement(svc, case_id=case_id, case_num=case_num)
def notify_kp24_motion_execution(case_id: int, case_num: str): kp_notify.kp24_motion_execution(svc, case_id=case_id, case_num=case_num)
def notify_kp25_satisfaction_judgment(case_id: int, case_num: str): kp_notify.kp25_satisfaction_judgment(svc, case_id=case_id, case_num=case_num)
