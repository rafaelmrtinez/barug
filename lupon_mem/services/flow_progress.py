# lupon_mem/services/flow_progress.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from django.db import connection

def _fetchone_dict(cur) -> Optional[Dict[str, Any]]:
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))

def _fetchall_dict(cur) -> List[Dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in rows]

def get_progress(case_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns current progress + last 20 history rows.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_id, current_step, hearing_no, hearing_attempt,
                   reached_steps, updated_at, updated_by_id
            FROM lupon_flow_progress
            WHERE case_id = %s
        """, [case_id])
        prog = _fetchone_dict(cur)

        cur.execute("""
            SELECT id, case_id, step, hearing_no, hearing_attempt,
                   updated_at, updated_by_id
            FROM lupon_flow_progress_history
            WHERE case_id = %s
            ORDER BY updated_at DESC
            LIMIT 20
        """, [case_id])
        hist = _fetchall_dict(cur)

    if not prog:
        return None

    prog["history"] = hist
    return prog

def save_progress(
    case_id: int,
    step: str,
    hearing_no: int,
    hearing_attempt: int,
    staff_id: Optional[int],
    append_history: bool = True,
) -> None:
    """
    Upsert current row (updates updated_at) and optionally append to history.
    Also merges step into reached_steps if new.
    """
    with connection.cursor() as cur:
        # 1) Upsert main record
        cur.execute("""
            INSERT INTO lupon_flow_progress (
              case_id, current_step, hearing_no, hearing_attempt, reached_steps, updated_at, updated_by_id
            )
            VALUES (
              %s, %s, %s, %s, to_jsonb(ARRAY[%s])::jsonb, now(), %s
            )
            ON CONFLICT (case_id) DO UPDATE SET
              current_step    = EXCLUDED.current_step,
              hearing_no      = EXCLUDED.hearing_no,
              hearing_attempt = EXCLUDED.hearing_attempt,
              -- merge step into reached_steps if not already present
              reached_steps   = CASE
                                  WHEN lupon_flow_progress.reached_steps ? %s
                                  THEN lupon_flow_progress.reached_steps
                                  ELSE lupon_flow_progress.reached_steps || to_jsonb(ARRAY[%s])::jsonb
                                END,
              updated_at      = now(),
              updated_by_id   = EXCLUDED.updated_by_id
        """, [case_id, step, hearing_no, hearing_attempt, step, staff_id, step, step])

        # 2) Append history (one row per save)
        if append_history:
            cur.execute("""
                INSERT INTO lupon_flow_progress_history (
                  case_id, step, hearing_no, hearing_attempt, updated_at, updated_by_id
                )
                VALUES (%s, %s, %s, %s, now(), %s)
            """, [case_id, step, hearing_no, hearing_attempt, staff_id])
