# lupon_mem/services/gates.py
from __future__ import annotations
from typing import Optional, Dict, List
from django.db import connection

def _submitted_codes(case_id: int) -> dict[str, bool]:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT UPPER(f.form_code) AS code, BOOL_OR(UPPER(s.status)='SUBMITTED') AS is_submitted
            FROM blotter_kp_submission s JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s GROUP BY 1
        """, [case_id])
        return {row[0]: bool(row[1]) for row in cur.fetchall()}

def _hearings_held(case_id: int) -> int:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id = %s AND UPPER(t.case_progress_type_name) = 'HEARING HELD'
        """, [case_id])
        return int(cur.fetchone()[0])

def _current_settlement(case_id: int) -> str:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(UPPER(ss.settlement_status_name), 'NOT SETTLED')
            FROM blotter_case bc LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        row = cur.fetchone()
        return row[0] if row else 'NOT SETTLED'

def _latest_notice_submitted_at(case_id: int):
    with connection.cursor() as cur:
        cur.execute("""
            WITH forms AS (SELECT form_id FROM kp_form WHERE UPPER(form_code) IN ('KP-8','KP-12'))
            SELECT MAX(s.submitted_at)
            FROM blotter_kp_submission s
            WHERE s.blotter_case_id=%s AND s.form_id IN (SELECT form_id FROM forms) AND UPPER(s.status)='SUBMITTED'
        """, [case_id])
        row = cur.fetchone()
    return row[0] if row else None

def _is_hearing_held(case_id: int, *, strict: bool = True) -> bool:
    latest_notice_at = _latest_notice_submitted_at(case_id)
    with connection.cursor() as cur:
        if strict and latest_notice_at:
            cur.execute("""
                SELECT 1 FROM case_progress_tracking cpt
                JOIN case_progress_type t ON t.case_progress_type_id=cpt.case_progress_type_id
                WHERE cpt.blotter_case_id=%s
                  AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                  AND cpt.date_processed > %s
                LIMIT 1
            """, [case_id, latest_notice_at])
        else:
            cur.execute("""
                SELECT 1 FROM case_progress_tracking cpt
                JOIN case_progress_type t ON t.case_progress_type_id=cpt.case_progress_type_id
                WHERE cpt.blotter_case_id=%s
                  AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                LIMIT 1
            """, [case_id])
        r = cur.fetchone()
    return bool(r)

def _hearing_gate(case_id: int) -> dict:
    with connection.cursor() as cur:
        cur.execute("""
            WITH f8 AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-8'  LIMIT 1),
                 f12 AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-12' LIMIT 1),
            latest AS (
              SELECT s.submission_id, s.submitted_at
              FROM blotter_kp_submission s
              WHERE s.blotter_case_id=%s
                AND s.form_id IN ((SELECT form_id FROM f8),(SELECT form_id FROM f12))
              ORDER BY (UPPER(s.status)='SUBMITTED') DESC, s.submitted_at DESC NULLS LAST, s.submission_id DESC
              LIMIT 1
            ),
            held AS (
              SELECT COUNT(*)::int AS c, COALESCE(MAX(cpt.date_processed), TIMESTAMP '0001-01-01') AS last_held_at
              FROM case_progress_tracking cpt
              JOIN case_progress_type t ON t.case_progress_type_id=cpt.case_progress_type_id
              WHERE cpt.blotter_case_id=%s
                AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
            ),
            st AS (
              SELECT COALESCE(ss.settlement_status_name,'PENDING') AS name
              FROM blotter_case bc
              LEFT JOIN settlement_status ss ON ss.settlement_status_id=bc.settlement_status_id
              WHERE bc.blotter_case_id=%s
            )
            SELECT
              (SELECT c FROM held),
              (SELECT submitted_at FROM latest),
              (SELECT submission_id FROM latest),
              (SELECT name FROM st),
              (SELECT last_held_at FROM held)
        """, [case_id, case_id, case_id])
        r = cur.fetchone()

    hearings_held, latest_at, latest_sid, settlement_name, last_held_at = r
    latest_outstanding = bool(latest_at and (not last_held_at or last_held_at <= latest_at))
    settlement_up = (settlement_name or '').strip().upper()
    pending = settlement_up in ('PENDING','NOT SETTLED','UNSET','FOR MEDIATION','FOR CONCILIATION')
    limit_reached = (hearings_held or 0) >= 3
    can_issue = (not limit_reached) and (not latest_outstanding) and pending

    if limit_reached:
        reason = "Limit reached: 3 hearings already held (proceed to Arbitration/CFA)."
    elif latest_outstanding:
        reason = "There is an upcoming hearing from the latest KP-8/12 (mark it HELD first)."
    elif not pending:
        reason = f"Settlement is “{settlement_name}” (change to Pending/Not Settled to schedule another)."
    else:
        reason = ""

    return {
        "hearings_held": hearings_held or 0,
        "latest_notice_submitted_at": latest_at,
        "latest_notice_submission_id": latest_sid,
        "latest_notice_outstanding": latest_outstanding,
        "settlement_name": settlement_name,
        "can_issue_notice": bool(can_issue),
        "reason": reason,
        "limit_reached": bool(limit_reached),
    }
