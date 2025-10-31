# notifications/service.py
# notifications/service.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Mapping, Any, Iterable, List
from notifications.expo_client import ExpoClient
from notifications import repo

PERSON = 1
STAFF = 2

@dataclass(frozen=True)
class NotifyTarget:
    user_type_id: int
    person_id: Optional[int] = None
    staff_id: Optional[int] = None

class NotifierService:
    def __init__(self, expo: Optional[ExpoClient] = None):
        self.expo = expo or ExpoClient()

    # register
    def register_device(self, *, user_type_id: int, person_id: Optional[int], staff_id: Optional[int],
                        platform: Optional[str], expo_push_token: str) -> None:
        repo.upsert_push_device(
            user_type_id=user_type_id,
            person_id=person_id,
            staff_id=staff_id,
            platform=platform,
            token=expo_push_token
        )

    # main notify
    def notify_user(self, *, target: NotifyTarget, title: str, body: str,
                    deep_link: Optional[str] = None, dedupe_minutes: int = 5) -> bool:
        if repo.recently_sent_exists(
            user_type_id=target.user_type_id,
            person_id=target.person_id,
            staff_id=target.staff_id,
            title=title,
            body=body,
            minutes=dedupe_minutes,
        ):
            return True  # silently skip duplicate

        repo.insert_notification(
            user_type_id=target.user_type_id,
            person_id=target.person_id,
            staff_id=target.staff_id,
            title=title,
            body=body,
            deep_link=deep_link,
        )

        tokens = repo.get_tokens(
            user_type_id=target.user_type_id,
            person_id=target.person_id,
            staff_id=target.staff_id,
        )

        messages = [{
            "to": t,
            "title": title,
            "body": body,
            "data": {"deep_link": deep_link or ""},
        } for t in tokens]

        self.expo.send(messages)
        return True

    # helpers
    def mark_all_read(self, *, user_type_id: int, person_id: Optional[int], staff_id: Optional[int]) -> None:
        repo.mark_all_read(user_type_id=user_type_id, person_id=person_id, staff_id=staff_id)

    def list_notifications(self, *, user_type_id: int, person_id: Optional[int], staff_id: Optional[int], limit:int=50):
        rows = repo.list_latest(user_type_id=user_type_id, person_id=person_id, staff_id=staff_id, limit=limit)
        return [
            {
                "notification_id": r[0],
                "title": r[1],
                "body": r[2],
                "deep_link": r[3],
                "is_read": r[4],
                "created_at": r[5].isoformat(),
            } for r in rows
        ]


# pasttt
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
