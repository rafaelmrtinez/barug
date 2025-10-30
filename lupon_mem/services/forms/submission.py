# lupon_mem/services/forms/submission.py
from __future__ import annotations
from typing import Optional
from django.db import connection


def _create_and_submit_form_from_prefill(case_id: int, form_code: str, prefill: dict[str, object] | None = None) -> Optional[int]:
    """
    Creates a blotter_kp_submission for `form_code`, writes answers using the provided
    `prefill` map keyed by *field_code*, marks SUBMITTED, and returns submission_id.
    Returns None if form_code not active/doesn't exist.
    """
    form_code_up = (form_code or "").strip().upper()
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)=%s AND is_active IS TRUE LIMIT 1", [form_code_up])
        r = cur.fetchone()
        if not r:
            return None
        form_id = int(r[0])

        # create submission (DRAFT)
        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT') RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # gather fields for this form
        cur.execute("""
            SELECT f.field_id, LOWER(f.field_code) AS code
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id=%s
        """, [form_id])
        fields = cur.fetchall()

        # pick values for each field from prefill (skip None/blank to keep PDFs tidy)
        import json as _json
        pmap = (prefill or {})
        for field_id, code in fields:
            code = (code or "").lower()
            if code in pmap:
                val = pmap[code]
            else:
                continue
            if val in (None, "", []):
                continue
            cur.execute("""
                INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                VALUES (%s,%s,%s)
                ON CONFLICT (submission_id, field_id) DO UPDATE SET value_json=EXCLUDED.value_json
            """, [sid, int(field_id), _json.dumps(val)])

        # mark SUBMITTED
        cur.execute("UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s", [sid])

    return sid





def _open_kp16_draft(case_id: int) -> int:
    """
    Create (or reuse) a KP-16 DRAFT with minimal prefill and return submission_id.
    Does NOT submit; just prepares the form so the Lupon can type the settlement statement.
    """
    with connection.cursor() as cur:
        # Reuse most recent KP-16 DRAFT if present
        cur.execute("""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='KP-16'
              AND UPPER(s.status)='DRAFT'
            ORDER BY s.submission_id DESC
            LIMIT 1
        """, [case_id])
        r = cur.fetchone()
        if r:
            return int(r[0])

        # Create new DRAFT
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-16' AND is_active IS TRUE LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise ValidationError("KP-16 is not configured/active.")
        form_id = int(row[0])

        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT') RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # Prefill some friendly defaults (optional)
        pre = _prefill_minimal_for_case(case_id)
        cur.execute("""
            SELECT kff.field_id, LOWER(kf.field_code)
            FROM kp_form_field kff
            JOIN kp_field kf ON kf.field_id = kff.field_id
            WHERE kff.form_id=%s
        """, [form_id])
        import json as _json
        for field_id, code in cur.fetchall():
            v = pre.get((code or "").lower())
            if v in (None, "", []):
                continue
            cur.execute("""
                INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                VALUES (%s,%s,%s)
                ON CONFLICT (submission_id, field_id)
                DO UPDATE SET value_json=EXCLUDED.value_json
            """, [sid, int(field_id), _json.dumps(v)])

        return sid





def _open_med_attendance_draft(case_id: int) -> int:
    """
    Create (or reuse) a MED-ATT-2025 DRAFT and return submission_id.
    Prefills minimally (safe) using _prefill_minimal_for_case.
    """
    # Reuse latest DRAFT if it exists
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
             WHERE s.blotter_case_id=%s
               AND UPPER(f.form_code)='MED-ATT-2025'
               AND UPPER(s.status)='DRAFT'
             ORDER BY s.submission_id DESC
             LIMIT 1
        """, [case_id])
        r = cur.fetchone()
        if r:
            return int(r[0])

        # Resolve form_id for MED-ATT-2025 (must be active)
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)='MED-ATT-2025' AND is_active IS TRUE LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise ValidationError("MED-ATT-2025 is not configured/active.")
        form_id = int(row[0])

        # Create DRAFT
        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT')
            RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # Prefill what we can (best-effort, skip blanks)
        pre = _prefill_minimal_for_case(case_id)
        cur.execute("""
            SELECT kff.field_id, LOWER(kf.field_code)
              FROM kp_form_field kff
              JOIN kp_field kf ON kf.field_id = kff.field_id
             WHERE kff.form_id=%s
        """, [form_id])
        import json as _json
        for field_id, code in cur.fetchall():
            val = pre.get((code or "").lower())
            if val in (None, "", []):
                continue
            cur.execute("""
                INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                VALUES (%s,%s,%s)
                ON CONFLICT (submission_id, field_id)
                DO UPDATE SET value_json=EXCLUDED.value_json
            """, [sid, int(field_id), _json.dumps(val)])

        return sid


