# notifications/views.py
import json, requests
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_POST
from django.db import connection

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def _exec(sql, params=()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        try:
            return cur.fetchall()
        except:
            return []

@require_POST
def register_push_device(request: HttpRequest):
    payload = json.loads(request.body or "{}")
    user_type_id = payload.get("user_type_id")  # 1=PERSON, 2=STAFF
    person_id    = payload.get("person_id")
    staff_id     = payload.get("staff_id")
    platform     = payload.get("platform")
    token        = payload.get("expo_push_token")

    if not (user_type_id and token):
        return JsonResponse({"ok": False, "error": "missing user_type_id or token"}, status=400)

    _exec("""
      INSERT INTO push_device (user_type_id, person_id, staff_id, platform, expo_push_token, last_seen)
      VALUES (%s, %s, %s, %s, %s, now())
      ON CONFLICT (expo_push_token)
      DO UPDATE SET last_seen = EXCLUDED.last_seen,
                    user_type_id = EXCLUDED.user_type_id,
                    person_id = EXCLUDED.person_id,
                    staff_id = EXCLUDED.staff_id,
                    platform = EXCLUDED.platform
    """, (user_type_id, person_id, staff_id, platform, token))

    return JsonResponse({"ok": True})

def _get_tokens(user_type_id, person_id, staff_id):
    rows = _exec("""
      SELECT expo_push_token
        FROM push_device
       WHERE user_type_id=%s
         AND COALESCE(person_id,0)=COALESCE(%s,0)
         AND COALESCE(staff_id,0)=COALESCE(%s,0)
    """, (user_type_id, person_id, staff_id))
    return [r[0] for r in rows]

def _send_push(tokens, title, body, data=None):
    if not tokens:
        return
    msgs = [{"to": t, "title": title, "body": body, "data": data or {}} for t in tokens]
    try:
        requests.post(EXPO_PUSH_URL, json=msgs, timeout=10)
    except Exception as e:
        # optional: log error
        pass

def notify_user(*, user_type_id:int, person_id:int|None, staff_id:int|None,
                title:str, body:str, deep_link:str|None=None):
    # Check for duplicate within last 5 minutes
    existing = _exec("""
        SELECT 1 FROM notification 
        WHERE user_type_id=%s AND COALESCE(person_id,0)=COALESCE(%s,0) 
        AND COALESCE(staff_id,0)=COALESCE(%s,0) AND title=%s AND body=%s 
        AND created_at > now() - interval '5 minutes' LIMIT 1
    """, (user_type_id, person_id, staff_id, title, body))
    
    if existing:
        return  # Skip duplicate
    
    # 1) store it (powers in-app list + badges)
    _exec("""INSERT INTO notification(user_type_id, person_id, staff_id, title, body, deep_link)
             VALUES (%s,%s,%s,%s,%s,%s)""",
          (user_type_id, person_id, staff_id, title, body, deep_link))
    # 2) push to devices (best-effort)
    tokens = _get_tokens(user_type_id, person_id, staff_id)
    _send_push(tokens, title, body, {"deep_link": deep_link or ""})

@require_POST
def send_test_push(request: HttpRequest):
    payload = json.loads(request.body or "{}")
    notify_user(
        user_type_id=payload.get("user_type_id", 1),
        person_id=payload.get("person_id"),
        staff_id=payload.get("staff_id"),
        title=payload.get("title", "Test"),
        body=payload.get("body", "Hello from Expo Push"),
        deep_link=payload.get("deep_link", "/dashboard")
    )
    return JsonResponse({"ok": True})

@require_POST
def clear_notifications(request: HttpRequest):
    payload = json.loads(request.body or "{}")
    user_type_id = payload.get("user_type_id")
    person_id    = payload.get("person_id")
    staff_id     = payload.get("staff_id")
    _exec("""
      UPDATE notification
         SET is_read = TRUE
       WHERE user_type_id=%s
         AND COALESCE(person_id,0)=COALESCE(%s,0)
         AND COALESCE(staff_id,0)=COALESCE(%s,0)
         AND is_read=FALSE
    """, (user_type_id, person_id, staff_id))
    return JsonResponse({"ok": True})

def list_notifications(request: HttpRequest):
    # quick GET for testing; in production secure this (session/role)
    user_type_id = int(request.GET.get("user_type_id"))
    person_id    = request.GET.get("person_id")
    staff_id     = request.GET.get("staff_id")
    rows = _exec("""
      SELECT notification_id, title, body, deep_link, is_read, created_at
        FROM notification
       WHERE user_type_id=%s
         AND COALESCE(person_id,0)=COALESCE(%s,0)
         AND COALESCE(staff_id,0)=COALESCE(%s,0)
       ORDER BY created_at DESC
       LIMIT 50
    """, (user_type_id, person_id, staff_id))
    data = [
      {"notification_id": r[0], "title": r[1], "body": r[2], "deep_link": r[3],
       "is_read": r[4], "created_at": r[5].isoformat()}
      for r in rows
    ]
    return JsonResponse({"ok": True, "data": data})

# KP Form notification helpers
def notify_kp7_complaint_filed(case_id, case_num):
    """Notify complainant and respondent about new complaint (KP-7)"""
    print(f"[KP7 NOTIFICATION] Starting notifications for case_id={case_id}, case_num={case_num}")
    parties = _exec("""
        SELECT 'complainant' as role, cc.person_id 
        FROM complainant_case cc WHERE cc.blotter_case_id = %s
        UNION ALL
        SELECT 'respondent' as role, rc.person_id 
        FROM respondent_case rc WHERE rc.blotter_case_id = %s
    """, (case_id, case_id))
    
    print(f"[KP7 NOTIFICATION] Found {len(parties)} parties: {parties}")
    
    for role, person_id in parties:
        if role == 'complainant':
            print(f"[KP7 NOTIFICATION] Sending to COMPLAINANT person_id={person_id}: 'Your complaint has been filed'")
            notify_user(
                user_type_id=1, person_id=person_id, staff_id=None,
                title="Complaint Filed",
                body=f"Your complaint has been filed as Case #{case_num}",
                deep_link=f"/resident/cases/{case_id}"
            )
        else:  # respondent
            print(f"[KP7 NOTIFICATION] Sending to RESPONDENT person_id={person_id}: 'A complaint has been filed against you'")
            notify_user(
                user_type_id=1, person_id=person_id, staff_id=None,
                title="New Case Filed Against You",
                body=f"A complaint has been filed against you - Case #{case_num}",
                deep_link=f"/resident/cases/{case_id}"
            )

def notify_kp8_hearing_scheduled(case_id, case_num, hearing_date, hearing_time):
    """Notify complainant about hearing scheduled (KP-8)"""
    print(f"[KP8 NOTIFICATION] Starting notifications for case_id={case_id}, case_num={case_num}, date={hearing_date}, time={hearing_time}")
    complainants = _exec("""
        SELECT cc.person_id FROM complainant_case cc WHERE cc.blotter_case_id = %s
    """, (case_id,))
    
    print(f"[KP8 NOTIFICATION] Found {len(complainants)} complainants: {complainants}")
    
    for (person_id,) in complainants:
        print(f"[KP8 NOTIFICATION] Sending to COMPLAINANT person_id={person_id}: 'Hearing scheduled'")
        notify_user(
            user_type_id=1, person_id=person_id, staff_id=None,
            title=f"Hearing Scheduled — Case {case_num}",
            body=f"Hearing scheduled for {hearing_date} at {hearing_time}",
            deep_link=f"/resident/cases/{case_id}"
        )
    
    # Notify Lupon members about new KP-8 submission
    lupon_members = _exec("""
        SELECT s.staff_id FROM staff s 
        JOIN rolee r ON r.role_id = s.role_id 
        WHERE r.role_name IN ('LUPON MEMBER', 'BARANGAY CAPTAIN')
    """)
    
    print(f"[KP8 NOTIFICATION] Found {len(lupon_members)} lupon members: {lupon_members}")
    
    for (staff_id,) in lupon_members:
        print(f"[KP8 NOTIFICATION] Sending to LUPON MEMBER staff_id={staff_id}: 'New KP-8 submission'")
        notify_user(
            user_type_id=2, person_id=None, staff_id=staff_id,
            title="New KP-8 Submission",
            body=f"NOTICE OF HEARING has been submitted for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/"
        )

def notify_kp9_summon_issued(case_id, case_num, hearing_date, hearing_time):
    """Notify respondent about summon (KP-9)"""
    print(f"[KP9 NOTIFICATION] Starting notifications for case_id={case_id}, case_num={case_num}, date={hearing_date}, time={hearing_time}")
    respondents = _exec("""
        SELECT rc.person_id FROM respondent_case rc WHERE rc.blotter_case_id = %s
    """, (case_id,))
    
    print(f"[KP9 NOTIFICATION] Found {len(respondents)} respondents: {respondents}")
    
    for (person_id,) in respondents:
        print(f"[KP9 NOTIFICATION] Sending to RESPONDENT person_id={person_id}: 'Notice of Hearing'")
        notify_user(
            user_type_id=1, person_id=person_id, staff_id=None,
            title=f"Notice of Hearing — Case {case_num}",
            body=f"You are required to appear {hearing_date} at {hearing_time} for your mediation hearing. (Case {case_num})",
            deep_link=f"/resident/cases/{case_id}"
        )

def notify_kp_form_submitted(kp_num, case_id, case_num, title, body_template):
    """Generic notification for KP form submissions"""
    print(f"[KP{kp_num} NOTIFICATION] Starting notifications for case_id={case_id}, case_num={case_num}")
    
    # Notify both parties
    parties = _exec("""
        SELECT 'complainant' as role, cc.person_id FROM complainant_case cc WHERE cc.blotter_case_id = %s
        UNION ALL
        SELECT 'respondent' as role, rc.person_id FROM respondent_case rc WHERE rc.blotter_case_id = %s
    """, (case_id, case_id))
    
    print(f"[KP{kp_num} NOTIFICATION] Found {len(parties)} parties: {parties}")
    
    for role, person_id in parties:
        body = body_template.format(case_num=case_num, role=role)
        print(f"[KP{kp_num} NOTIFICATION] Sending to {role.upper()} person_id={person_id}: '{title}'")
        notify_user(
            user_type_id=1, person_id=person_id, staff_id=None,
            title=f"{title} — Case {case_num}",
            body=body,
            deep_link=f"/resident/cases/{case_id}"
        )
    
    # Notify Lupon members
    lupon_members = _exec("""
        SELECT s.staff_id FROM staff s 
        JOIN rolee r ON r.role_id = s.role_id 
        WHERE r.role_name IN ('LUPON MEMBER', 'BARANGAY CAPTAIN')
    """)
    
    for (staff_id,) in lupon_members:
        print(f"[KP{kp_num} NOTIFICATION] Sending to LUPON MEMBER staff_id={staff_id}: 'New KP-{kp_num} submission'")
        notify_user(
            user_type_id=2, person_id=None, staff_id=staff_id,
            title=f"New KP-{kp_num} Submission",
            body=f"KP-{kp_num} form has been submitted for Case #{case_num}",
            deep_link=f"/lupon_mem/case/{case_id}/"
        )

# Specific KP form notifications
def notify_kp10_constitution_pangkat(case_id, case_num):
    notify_kp_form_submitted(10, case_id, case_num, "Pangkat Constitution", "Pangkat has been constituted for Case #{case_num}")

def notify_kp11_mediation_proceedings(case_id, case_num):
    notify_kp_form_submitted(11, case_id, case_num, "Mediation Proceedings", "Mediation proceedings have started for Case #{case_num}")

def notify_kp12_hearing_conciliation(case_id, case_num):
    notify_kp_form_submitted(12, case_id, case_num, "Notice of Hearing (Conciliation)", "Notice of hearing for conciliation proceedings has been issued for Case #{case_num}")

# Updated notification functions based on actual KP form names
def notify_kp13_subpoena_letter(case_id, case_num):
    notify_kp_form_submitted(13, case_id, case_num, "Subpoena Letter", "Subpoena letter has been issued for Case #{case_num}")

def notify_kp14_agreement_arbitration(case_id, case_num):
    notify_kp_form_submitted(14, case_id, case_num, "Agreement for Arbitration", "Agreement for arbitration has been filed for Case #{case_num}")

def notify_kp15_arbitration_award(case_id, case_num):
    notify_kp_form_submitted(15, case_id, case_num, "Arbitration Award", "Arbitration award has been issued for Case #{case_num}")

def notify_kp16_amicable_settlement(case_id, case_num):
    notify_kp_form_submitted(16, case_id, case_num, "Amicable Settlement", "Amicable settlement has been reached for Case #{case_num}")

def notify_kp17_repudiation(case_id, case_num):
    notify_kp_form_submitted(17, case_id, case_num, "Repudiation", "Repudiation has been filed for Case #{case_num}")

def notify_kp18_hearing_complainant(case_id, case_num):
    notify_kp_form_submitted(18, case_id, case_num, "Notice of Hearing for Complainant", "Notice of hearing has been issued for Case #{case_num}")

def notify_kp19_hearing_respondent(case_id, case_num):
    notify_kp_form_submitted(19, case_id, case_num, "Notice of Hearing for Respondent", "Notice of hearing has been issued for Case #{case_num}")

def notify_kp20_certification_file_action(case_id, case_num):
    notify_kp_form_submitted(20, case_id, case_num, "Certification to File Action", "Certification to file action has been issued for Case #{case_num}")

def notify_kp20a_certification_pangkat(case_id, case_num):
    notify_kp_form_submitted("20A", case_id, case_num, "Certification from Pangkat Secretary", "Certification to file action from Pangkat Secretary for Case #{case_num}")

def notify_kp20b_certification_general(case_id, case_num):
    notify_kp_form_submitted("20B", case_id, case_num, "Certification to File Action", "General certification to file action for Case #{case_num}")

def notify_kp21_certification_bar_action(case_id, case_num):
    notify_kp_form_submitted(21, case_id, case_num, "Certification to Bar Action", "Certification to bar action has been issued for Case #{case_num}")

def notify_kp22_certification_bar_counterclaim(case_id, case_num):
    notify_kp_form_submitted(22, case_id, case_num, "Certification to Bar Counterclaim", "Certification to bar counterclaim has been issued for Case #{case_num}")

def notify_kp23_motion_execution(case_id, case_num):
    notify_kp_form_submitted(23, case_id, case_num, "Motion for Execution", "Motion for execution has been filed for Case #{case_num}")

def notify_kp24_hearing_execution(case_id, case_num):
    notify_kp_form_submitted(24, case_id, case_num, "Notice of Hearing (Re: Motion for Execution)", "Notice of hearing for motion for execution has been issued for Case #{case_num}")

def notify_kp25_notice_execution(case_id, case_num):
    notify_kp_form_submitted(25, case_id, case_num, "Notice of Execution", "Notice of execution has been issued for Case #{case_num}")

def notify_kp26_monthly_transmittal(case_id, case_num):
    notify_kp_form_submitted(26, case_id, case_num, "Monthly Transmittal", "Monthly transmittal of final reports has been submitted for Case #{case_num}")

# Additional forms
def notify_acknowledgement_receipt(case_id, case_num):
    notify_kp_form_submitted("ACK", case_id, case_num, "Acknowledgement Receipt", "Acknowledgement receipt has been issued for Case #{case_num}")

def notify_case_folder_summary(case_id, case_num):
    notify_kp_form_submitted("FOLDER", case_id, case_num, "Case Folder Summary", "Case folder summary has been updated for Case #{case_num}")

def notify_invitation_letter(case_id, case_num):
    notify_kp_form_submitted("INVITE", case_id, case_num, "Invitation Letter", "Invitation letter has been sent for Case #{case_num}")

def notify_kp9_officers_return(case_id, case_num):
    notify_kp_form_submitted("9-P2", case_id, case_num, "Officer's Return", "Officer's return has been filed for summon in Case #{case_num}")
