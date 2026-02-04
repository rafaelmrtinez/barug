# notifications/repo.py
from __future__ import annotations
from typing import Any, Iterable, List, Tuple, Optional
from django.db import connection

def _exec(sql: str, params: Iterable[Any] = ()) -> List[Tuple]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        try:
            return cur.fetchall()
        except Exception:
            return []

def upsert_push_device(*, user_type_id: int, person_id: Optional[int], staff_id: Optional[int],
                       platform: Optional[str], token: str) -> None:
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

def get_tokens(*, user_type_id: int, person_id: Optional[int], staff_id: Optional[int]) -> List[str]:
    rows = _exec("""
      SELECT expo_push_token
        FROM push_device
       WHERE user_type_id=%s
         AND COALESCE(person_id,0)=COALESCE(%s,0)
         AND COALESCE(staff_id,0)=COALESCE(%s,0)
    """, (user_type_id, person_id, staff_id))
    return [r[0] for r in rows]

def recently_sent_exists(*, user_type_id: int, person_id: Optional[int], staff_id: Optional[int],
                         title: str, body: str, minutes: int = 5) -> bool:
    rows = _exec("""
        SELECT 1 FROM notification 
         WHERE user_type_id=%s AND COALESCE(person_id,0)=COALESCE(%s,0) 
           AND COALESCE(staff_id,0)=COALESCE(%s,0)
           AND title=%s AND body=%s 
           AND created_at > now() - (interval '%s minutes')
         LIMIT 1
    """, (user_type_id, person_id, staff_id, title, body, minutes))
    return bool(rows)

def insert_notification(*, user_type_id: int, person_id: Optional[int], staff_id: Optional[int],
                        title: str, body: str, deep_link: Optional[str]) -> None:
    _exec("""INSERT INTO notification(user_type_id, person_id, staff_id, title, body, deep_link)
             VALUES (%s,%s,%s,%s,%s,%s)""",
          (user_type_id, person_id, staff_id, title, body, deep_link))

def mark_all_read(*, user_type_id: int, person_id: Optional[int], staff_id: Optional[int]) -> None:
    _exec("""
      UPDATE notification
         SET is_read = TRUE
       WHERE user_type_id=%s
         AND COALESCE(person_id,0)=COALESCE(%s,0)
         AND COALESCE(staff_id,0)=COALESCE(%s,0)
         AND is_read=FALSE
    """, (user_type_id, person_id, staff_id))

def list_latest(*, user_type_id: int, person_id: Optional[int], staff_id: Optional[int], limit: int = 50):
    return _exec("""
      SELECT notification_id, title, body, deep_link, is_read, created_at
        FROM notification
       WHERE user_type_id=%s
         AND COALESCE(person_id,0)=COALESCE(%s,0)
         AND COALESCE(staff_id,0)=COALESCE(%s,0)
       ORDER BY created_at DESC
       LIMIT %s
    """, (user_type_id, person_id, staff_id, limit))

def case_party_person_ids(case_id: int):
    return _exec("""
        SELECT 'complainant' as role, cc.person_id 
          FROM complainant_case cc WHERE cc.blotter_case_id = %s
        UNION ALL
        SELECT 'respondent' as role, rc.person_id 
          FROM respondent_case rc WHERE rc.blotter_case_id = %s
    """, (case_id, case_id))

def lupon_staff_ids():
    return _exec("""
        SELECT s.staff_id
          FROM staff s 
          JOIN rolee r ON r.role_id = s.role_id 
         WHERE r.role_name IN ('LUPON MEMBER', 'BARANGAY CAPTAIN')
    """)
