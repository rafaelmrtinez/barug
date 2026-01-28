# lupon_mem/db.py
from __future__ import annotations
from typing import Any, Iterable, List, Tuple, Optional
from django.db import connection

def q(sql: str, params: Iterable[Any] = ()) -> List[Tuple]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        try:
            return cur.fetchall()
        except Exception:
            return []

def q1(sql: str, params: Iterable[Any] = ()) -> Optional[Tuple]:
    rows = q(sql, params)
    return rows[0] if rows else None

def exec_only(sql: str, params: Iterable[Any] = ()) -> None:
    with connection.cursor() as cur:
        cur.execute(sql, params)

def update_person_photo(person_id: int, photo_url: str, supabase_uid: str) -> bool:
    """Update person photo URL in database"""
    try:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE person SET person_img = %s, supabase_uid = %s WHERE person_id = %s",
                [photo_url, supabase_uid, person_id]
            )
            connection.commit()
        return True
    except Exception:
        return False
