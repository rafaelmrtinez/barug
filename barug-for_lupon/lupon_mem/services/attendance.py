# lupon_mem/services/attendance.py
from __future__ import annotations
from typing import Optional
from django.db import connection




def _maybe_upsert_hearing_attendance(
    case_id: int,
    source_code: str,        # 'KP-8' or 'KP-12'
    notice_sid: int,         # submission_id of the notice
    compl_attended: bool,
    resp_attended: bool,
    settlement: str | None,
    remarks: str | None,
) -> None:
    with connection.cursor() as cur:
        # ensure cache table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hearing_attendance (
              blotter_case_id      int      NOT NULL,
              source_code          text     NOT NULL,  -- 'KP-8' / 'KP-12'
              notice_submission_id int      NOT NULL,
              held_at              timestamptz DEFAULT NOW(),
              complainant_attended boolean,
              respondent_attended  boolean,
              settlement_outcome   text,
              remarks              text
            );
        """)

        # try UPDATE first
        cur.execute("""
            UPDATE hearing_attendance
               SET held_at = NOW(),
                   complainant_attended = %s,
                   respondent_attended  = %s,
                   settlement_outcome   = NULLIF(%s,''),
                   remarks              = NULLIF(%s,'')
             WHERE blotter_case_id = %s
               AND source_code = %s
               AND notice_submission_id = %s
        """, [
            compl_attended, resp_attended,
            (settlement or ""), (remarks or ""),
            case_id, source_code, notice_sid
        ])

        # if no existing row, INSERT
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO hearing_attendance
                  (blotter_case_id, source_code, notice_submission_id,
                   held_at, complainant_attended, respondent_attended,
                   settlement_outcome, remarks)
                VALUES (%s,%s,%s, NOW(), %s,%s, NULLIF(%s,''), NULLIF(%s,''))
            """, [
                case_id, source_code, notice_sid,
                compl_attended, resp_attended,
                (settlement or ""), (remarks or "")
            ])






def _has_med_att_for_notice(case_id: int, notice_submission_id: int) -> bool:
    """
    True if there's a SUBMITTED MED-ATT-2025 that references this hearing notice
    via a field_code 'notice_sid' = notice_submission_id (int or string).
    """
    with connection.cursor() as cur:
        cur.execute("""
            WITH f_att AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code)='MED-ATT-2025' LIMIT 1
            ),
            fld AS (
              SELECT kf.field_id
              FROM kp_form_field kff
              JOIN kp_field kf ON kf.field_id=kff.field_id
              WHERE kff.form_id=(SELECT form_id FROM f_att)
                AND LOWER(kf.field_code)='notice_sid'
              LIMIT 1
            )
            SELECT 1
            FROM blotter_kp_submission s
            JOIN blotter_kp_answer a
              ON a.submission_id=s.submission_id
            WHERE s.blotter_case_id=%s
              AND s.form_id=(SELECT form_id FROM f_att)
              AND UPPER(s.status)='SUBMITTED'
              AND a.field_id=(SELECT field_id FROM fld)
              AND (a.value_json::text = %s OR a.value_json::text = to_jsonb(%s)::text)
            LIMIT 1
        """, [case_id, str(notice_submission_id), int(notice_submission_id)])
        return cur.fetchone() is not None







def _mark_hearing_held(case_id: int, notice_submission_id: int, outcome: str | None = None) -> bool:
    """
    Marks the hearing (derived from KP-8/KP-12 submission_id) as HELD.
    outcome can be 'SETTLED' or 'NOT SETTLED' (optional).
    Returns True on success.
    """
    try:
        with connection.cursor() as cur:
            # This mirrors your existing dev flow; adjust SQL to your schema if needed.
            # 1) Mark hearing held for this notice_submission_id
            cur.execute("""
                UPDATE blotter_hearing
                   SET held = TRUE, held_at = NOW()
                 WHERE blotter_case_id = %s
                   AND notice_submission_id = %s
            """, [case_id, notice_submission_id])

            # 2) Optionally set the outcome on the case if provided
            if outcome and outcome.upper() == 'SETTLED':
                cur.execute("""
                    UPDATE blotter_case
                       SET settlement_status_id = (SELECT settlement_status_id
                                                     FROM settlement_status
                                                    WHERE UPPER(settlement_status_name)='SETTLED'
                                                    LIMIT 1)
                     WHERE blotter_case_id = %s
                """, [case_id])

        print(f"[auto-held] Marked hearing HELD for case_id={case_id} sid={notice_submission_id} outcome={outcome}")
        return True
    except Exception as e:
        print(f"[auto-held][ERROR] case_id={case_id} sid={notice_submission_id}: {e}")
        return False








def _count_med_att_case(case_id: int) -> int:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='MED-ATT-2025'
              AND UPPER(s.status)='SUBMITTED'
        """, [case_id])
        return int(cur.fetchone()[0] or 0)



def _list_med_att_case(case_id: int) -> list[int]:
    """Return submission_ids of submitted MED-ATT-2025 (oldest→newest)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='MED-ATT-2025'
              AND UPPER(s.status)='SUBMITTED'
            ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
        """, [case_id])
        return [int(r[0]) for r in cur.fetchall()]








def _has_mediation_attendance(case_id: int) -> bool:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='MED-ATT-2025'
              AND UPPER(s.status)='SUBMITTED'
            LIMIT 1
        """, [case_id])
        return cur.fetchone() is not None





