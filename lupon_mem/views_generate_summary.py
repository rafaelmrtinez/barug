# lupon_mem/views_generate_summary.py
from django.shortcuts import redirect
from django.contrib import messages
from django.db import connection, transaction
from django.http import HttpRequest
from authentication.guards import session_login_required, role_required
from lupon_mem.utils.logging import blotter_log_event
import logging

log = logging.getLogger(__name__)
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def generate_settlement_summary(request: HttpRequest, case_id: int):
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    
    if not staff_id:
        messages.error(request, "Cannot determine current staff user.")
        return redirect("lupon_mem:case_detail", case_id=case_id)
    
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT bc.settlement_status_id, ss.settlement_status_name, bc.blotter_case_num, bc.blotter_case_name
                FROM blotter_case bc
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                WHERE bc.blotter_case_id = %s
            """, [case_id])
            
            case_row = cur.fetchone()
            if not case_row:
                messages.error(request, "Case not found.")
                return redirect("lupon_mem:case_detail", case_id=case_id)
            
            settlement_status_name = (case_row[1] or "").upper()
            case_num, case_name = case_row[2], case_row[3]
            
            if "SETTLED" not in settlement_status_name:
                messages.warning(request, "Case must be marked as SETTLED before generating settlement summary.")
                return redirect("lupon_mem:case_detail", case_id=case_id)
            
            cur.execute("""
                SELECT COUNT(*) FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-8' AND s.submitted_at IS NOT NULL
            """, [case_id])
            
            mediation_count = cur.fetchone()[0]
            if mediation_count == 0:
                messages.warning(request, "No mediation hearings found. Please add KP-8 forms first.")
                return redirect("lupon_mem:case_detail", case_id=case_id)
            
            form_code_map = {1: "MED1-SETTLED", 2: "MED2-SETTLED", 3: "MED3-SETTLED"}
            effective_count = min(mediation_count, 3)
            target_form_code = form_code_map.get(effective_count)
            
            cur.execute("""
                SELECT s.submission_id FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = %s LIMIT 1
            """, [case_id, target_form_code])
            
            if cur.fetchone():
                messages.info(request, f"Settlement summary for {effective_count}{_ordinal_suffix(effective_count)} mediation already exists.")
                return redirect("lupon_mem:case_detail", case_id=case_id)
            
            cur.execute("SELECT form_id, form_name FROM kp_form WHERE UPPER(form_code) = %s AND is_active = TRUE LIMIT 1", [target_form_code])
            form_row = cur.fetchone()
            if not form_row:
                messages.error(request, f"Form template {target_form_code} not found in system.")
                return redirect("lupon_mem:case_detail", case_id=case_id)
            
            form_id, form_name = form_row
            
            with transaction.atomic():
                cur.execute("""
                    INSERT INTO blotter_kp_submission (blotter_case_id, form_id, status, submitted_at)
                    VALUES (%s, %s, 'SUBMITTED', NOW()) RETURNING submission_id
                """, [case_id, form_id])
                submission_id = cur.fetchone()[0]
                
                _prefill_settlement_summary(cur, submission_id, case_id, form_id)
                
                staff_name = _get_staff_name(cur, staff_id)
                blotter_log_event(
                    action="AUTO_GENERATE_FORM", table_affected="blotter_kp_submission",
                    record_affected_id=submission_id,
                    details=f"{staff_name or f'Staff ID {staff_id}'} auto-generated {form_name} for Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'}",
                    performer_staff_id=staff_id
                )
            
            messages.success(request, f"Successfully generated {form_name}!")
            return redirect("lupon_mem:kp_submission_edit", pk=submission_id)
            
    except Exception as e:
        log.exception("Failed to generate settlement summary")
        messages.error(request, f"Failed to generate settlement summary: {str(e)}")
        return redirect("lupon_mem:case_detail", case_id=case_id)


def _ordinal_suffix(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _get_staff_name(cur, staff_id: int) -> str:
    if not staff_id:
        return None
    cur.execute("""
        SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, '')))
        FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s
    """, [staff_id])
    row = cur.fetchone()
    return row[0] if row else None


def _prefill_settlement_summary(cur, submission_id: int, case_id: int, form_id: int):
    from datetime import date
    
    cur.execute("""
        SELECT bc.blotter_case_num, bc.date_filed, ct.complaint_title_name, cn.case_name
        FROM blotter_case bc
        LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
        LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
        WHERE bc.blotter_case_id = %s
    """, [case_id])
    
    case_row = cur.fetchone()
    if not case_row:
        return
    
    case_num, date_filed, complaint_title, case_nature = case_row
    
    cur.execute("""
        SELECT TRIM(CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix))
        FROM complainant_case cc JOIN person p ON p.person_id = cc.person_id
        WHERE cc.blotter_case_id = %s ORDER BY p.last_name, p.first_name
    """, [case_id])
    complainants = ", ".join([row[0] for row in cur.fetchall()])
    
    cur.execute("""
        SELECT TRIM(CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix))
        FROM respondent_case rc JOIN person p ON p.person_id = rc.person_id
        WHERE rc.blotter_case_id = %s ORDER BY p.last_name, p.first_name
    """, [case_id])
    respondents = ", ".join([row[0] for row in cur.fetchall()])
    
    cur.execute("""
        SELECT a.value_json FROM blotter_kp_submission s
        JOIN kp_form kf ON kf.form_id = s.form_id
        JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
        JOIN kp_field f ON f.field_id = a.field_id
        WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-8'
          AND LOWER(f.field_code) = 'hearing_date'
          AND s.submitted_at IS NOT NULL
        ORDER BY s.submission_id LIMIT 3
    """, [case_id])
    notice_dates = [row[0].strip('"') for row in cur.fetchall() if row[0]]
    
    cur.execute("""
        SELECT a.value_json FROM blotter_kp_submission s
        JOIN kp_form kf ON kf.form_id = s.form_id
        JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
        JOIN kp_field f ON f.field_id = a.field_id
        WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-9'
          AND LOWER(f.field_code) = 'summon_date'
          AND s.submitted_at IS NOT NULL
        ORDER BY s.submission_id LIMIT 3
    """, [case_id])
    summon_dates = [row[0].strip('"') for row in cur.fetchall() if row[0]]
    
    cur.execute("""
        SELECT a.value_json FROM blotter_kp_submission s
        JOIN kp_form kf ON kf.form_id = s.form_id
        JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
        JOIN kp_field f ON f.field_id = a.field_id
        WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-16'
          AND LOWER(f.field_code) IN ('date_signed', 'settlement_date', 'date_settled')
          AND s.submitted_at IS NOT NULL
        ORDER BY s.submission_id DESC LIMIT 1
    """, [case_id])
    settlement_row = cur.fetchone()
    settlement_date = settlement_row[0].strip('"') if settlement_row and settlement_row[0] else None
    
    cur.execute("SELECT kff.field_id, f.field_code FROM kp_form_field kff JOIN kp_field f ON f.field_id = kff.field_id WHERE kff.form_id = %s", [form_id])
    fields = {row[1].lower(): row[0] for row in cur.fetchall()}
    
    values_to_insert = []
    field_map = {
        "case_num": case_num,
        "dt_filed": date_filed.isoformat() if date_filed else None,
        "complainant_name": complainants,
        "respondent_name": respondents,
        "complaint_title": complaint_title or "",
        "case_nature": case_nature or "",
        "first_notice_dt": notice_dates[0] if len(notice_dates) > 0 else None,
        "second_notice_dt": notice_dates[1] if len(notice_dates) > 1 else None,
        "third_notice_dt": notice_dates[2] if len(notice_dates) > 2 else None,
        "first_summon_dt": summon_dates[0] if len(summon_dates) > 0 else None,
        "second_summon_dt": summon_dates[1] if len(summon_dates) > 1 else None,
        "third_summon_dt": summon_dates[2] if len(summon_dates) > 2 else None,
        "first_conf_dt": notice_dates[0] if len(notice_dates) > 0 else None,
        "settlement_dt": settlement_date,
    }
    
    for field_code, value in field_map.items():
        if field_code in fields and value:
            values_to_insert.append((submission_id, fields[field_code], value))
    
    if values_to_insert:
        from psycopg2.extras import execute_values
        execute_values(cur, """
            INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
            VALUES %s ON CONFLICT (submission_id, field_id) DO UPDATE SET value_json = EXCLUDED.value_json
        """, [(sid, fid, f'"{val}"') for sid, fid, val in values_to_insert])
