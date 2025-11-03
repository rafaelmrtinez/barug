# notifications/service.py
import requests
from django.db import connection

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def _exec(sql, params=()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        try:
            return cur.fetchall()
        except Exception:
            return []

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
    except Exception:
        pass  # log if you want

def notify_user(*, user_type_id:int, person_id:int|None, staff_id:int|None,
                title:str, body:str, deep_link:str|None=None):
    _exec("""INSERT INTO notification(user_type_id, person_id, staff_id, title, body, deep_link)
             VALUES (%s,%s,%s,%s,%s,%s)""",
          (user_type_id, person_id, staff_id, title, body, deep_link))
    tokens = _get_tokens(user_type_id, person_id, staff_id)
    _send_push(tokens, title, body, {"deep_link": deep_link or ""})
