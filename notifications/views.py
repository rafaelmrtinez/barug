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
