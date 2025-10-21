# lupon_mem/services/people.py
from __future__ import annotations
from typing import Optional
from django.db import connection


def _get_person_mobile_number(person_id: int) -> str | None:
    """
    Returns a raw contact number (best effort) for a person.
    send_sms() will normalize it to 63XXXXXXXXXX.
    """
    try:
        with connection.cursor() as cur:
            # ✅ include more common column names
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='person'
                  AND column_name IN (
                    'mobile_number','mobile','mobile_no','mobile_num',
                    'phone','contact_no','contact_number','contact',
                    'cellphone','cell_no','cellphone_no'
                  )
            """)
            cols = [r[0] for r in cur.fetchall()]

            if cols:
                selects = " , ".join([f"NULLIF({c},'') AS {c}" for c in cols])
                cur.execute(f"SELECT {selects} FROM person WHERE person_id=%s", [person_id])
                row = cur.fetchone()
                if row:
                    for val in row:
                        if isinstance(val, str) and val.strip():
                            return val.strip()

            # Optional: separate contact table (ignore if missing)
            try:
                cur.execute("""
                    SELECT NULLIF(c.contact_value,'')
                    FROM person_contact c
                    WHERE c.person_id=%s
                      AND LOWER(c.contact_type) IN ('mobile','phone','cell','cellphone')
                    ORDER BY c.person_contact_id DESC
                    LIMIT 1
                """, [person_id])
                r2 = cur.fetchone()
                if r2 and r2[0]:
                    return r2[0].strip()
            except Exception:
                pass
    except Exception:
        return None
    return None

    
