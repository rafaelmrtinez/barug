# services/timeline.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, time as dtime, timezone as dt_timezone
from django.db import connection
from django.utils import timezone


# ----------------------------
# time + event helpers
# ----------------------------
def _to_display_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-naive datetime in current TZ for safe template display."""
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return timezone.make_naive(dt, timezone.get_current_timezone())
    return dt

def _to_sort_ts(dt: Optional[datetime]) -> float:
    """UTC epoch seconds for stable sorting; None -> +inf (goes last)."""
    if dt is None:
        return float("inf")
    try:
        if timezone.is_aware(dt):
            return dt.astimezone(dt_timezone.utc).timestamp()
        else:
            aware = timezone.make_aware(dt, timezone.get_current_timezone())
            return aware.astimezone(dt_timezone.utc).timestamp()
    except Exception:
        return float("inf")

def _row_to_event(
    dt: Optional[datetime],
    kind: str,
    title: str,
    subtitle: str = "",
    meta: Optional[Dict[str, Any]] = None,
):
    return {
        "dt": _to_display_naive(dt),  # timezone-naive for template
        "ts": _to_sort_ts(dt),          # numeric sort key from ORIGINAL dt
        "kind": kind,
        "title": title.strip(),
        "subtitle": (subtitle or "").strip(),
        "meta": meta or {},
    }

def _column_exists(table: str, column: str) -> bool:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name=%s AND column_name=%s
            LIMIT 1
        """, [table, column])
        return cur.fetchone() is not None


# ----------------------------
# names / parsing helpers
# ----------------------------
def _staff_name(staff_id: Optional[int]) -> Optional[str]:
    """Resolve staff_id → 'LAST, First M.' (None if unknown)."""
    if not staff_id:
        return None
    with connection.cursor() as cur:
        cur.execute("""
            SELECT p.last_name, p.first_name, p.middle_name, p.suffix
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            WHERE s.staff_id=%s
        """, [staff_id])
        r = cur.fetchone()
    if not r:
        return None
    last, first, mid, suf = [(x or "").strip() for x in r]
    parts: List[str] = []
    if last: parts.append(last.upper())
    if first: parts.append((", " if parts else "") + first.title())
    if mid: parts.append(f" {mid[:1].upper()}.")
    if suf: parts.append(f" {suf.upper()}")
    return "".join(parts).strip() or None

def _parse_local_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    """Build a dt from flexible strings; returns naive in current TZ."""
    if not date_str and not time_str:
        return None
    try:
        d = None
        t = None
        if date_str:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%m-%d-%Y", "%d-%m-%Y"):
                try:
                    d = datetime.strptime(date_str.strip(), fmt).date()
                    break
                except Exception:
                    continue
        if time_str:
            for fmt in ("%H:%M", "%I:%M %p"):
                try:
                    t = datetime.strptime(time_str.strip(), fmt).time()
                    break
                except Exception:
                    continue
        if d is None:
            return None
        if t is None:
            t = dtime.min
        aware = timezone.make_aware(datetime.combine(d, t), timezone.get_current_timezone(), is_dst=None)
        return timezone.make_naive(aware, timezone.get_current_timezone())
    except Exception:
        return None

def _answers_for_submission(submission_id: int) -> Dict[str, str]:
    """Return {field_code_lower: value_text} for a submission (strips JSON quotes)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT LOWER(f.field_code), a.value_json::text
            FROM blotter_kp_answer a
            JOIN kp_field f ON f.field_id = a.field_id
            WHERE a.submission_id=%s
        """, [submission_id])
        rows = cur.fetchall()
    out: Dict[str, str] = {}
    for fld, v in rows:
        s = (v or "").strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        out[fld] = s
    return out

def _extract_session_dt_from_answers(code: str, sid: int, ans: Dict[str, str]) -> Optional[datetime]:
    """
    Compute scheduled datetime for KP-8/KP-12/KP-9.
    - Uses SQL helper _extract_dt_time_for_submission if available (KP-8/12)
    - Otherwise falls back to common field names
    - KP-9 reconstructs from summon_date + summon_month + summon_year + summon_time
    """
    code_u = (code or "").upper()

    # KP-8 / KP-12: try SQL helper first
    if code_u in ("KP-8", "KP-12"):
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT session_date, session_time FROM _extract_dt_time_for_submission(%s)", [sid])
                row = cur.fetchone()
            if row:
                return _parse_local_dt(row[0] or None, row[1] or None)
        except Exception:
            pass
        # fallbacks seen in your seeds
        d = ans.get("hearing_date") or ans.get("appearance_date")
        t = ans.get("hearing_time") or ans.get("appearance_time")
        return _parse_local_dt(d, t)

    # KP-9: month/day/year in separate fields + time
    if code_u == "KP-9":
        day = (ans.get("summon_date") or "").strip()
        mon = (ans.get("summon_month") or "").strip()
        yr  = (ans.get("summon_year") or "").strip()
        tm  = (ans.get("summon_time") or "").strip()

        month_map = {
            "JANUARY": "01","FEBRUARY":"02","MARCH":"03","APRIL":"04","MAY":"05","JUNE":"06",
            "JULY":"07","AUGUST":"08","SEPTEMBER":"09","OCTOBER":"10","NOVEMBER":"11","DECEMBER":"12"
        }
        if mon and not mon.isdigit():
            mon = month_map.get(mon.upper(), mon)
        if len(day) == 1: day = "0"+day
        if len(mon) == 1: mon = "0"+mon

        date_str = f"{yr}-{mon}-{day}" if (yr and mon and day) else None
        return _parse_local_dt(date_str, tm)

    return None


# ----------------------------
# data fetchers per source
# ----------------------------
def _fetch_header(case_id: int) -> Optional[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              bc.blotter_case_id,
              COALESCE(bc.blotter_case_num, bc.blotter_case_name) AS case_num,
              bc.blotter_case_name,
              bc.date_filed, bc.time_filed,
              bc.blotter_report_id,
              COALESCE(ct.complaint_title_name,'—') AS type_name,
              COALESCE(cn.case_name,'—')           AS nature_name,
              bc.updated_at
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature    cn ON cn.case_nature_id    = bc.case_nature_id
            WHERE bc.blotter_case_id=%s
        """, [case_id])
        row = cur.fetchone()
    if not row:
        return None
    (cid, case_num, case_name, date_filed, time_filed,
     report_id, type_name, nature_name, updated_at) = row
    return {
        "case_id": cid,
        "case_num": case_num,
        "case_name": case_name,
        "date_filed": date_filed,
        "time_filed": time_filed,
        "report_id": report_id,
        "type_name": type_name,
        "nature_name": nature_name,
        "updated_at": updated_at,
    }

def _fetch_report_event(report_id: int) -> List[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT incident_subject, date_time_reported
            FROM blotter_report
            WHERE blotter_report_id=%s
        """, [report_id])
        r = cur.fetchone()
    if not r:
        return []
    subject, dt = r
    return [_row_to_event(dt, "report", "Report filed", subject or "", {"report_id": report_id})]

def _combine_date_time(d: Optional[date], t: Optional[dtime]) -> Optional[datetime]:
    try:
        if d is not None and t is not None:
            return datetime.combine(d, t if isinstance(t, dtime) else dtime.min)
        elif d is not None:
            return datetime.combine(d, dtime.min)
    except Exception:
        return None
    return None

def _fetch_case_opened(header: Dict[str, Any]) -> List[Dict[str, Any]]:
    opened_dt = _combine_date_time(header.get("date_filed"), header.get("time_filed"))
    return [_row_to_event(opened_dt, "case", "Case opened", f"{header['type_name']} — {header['nature_name']}")]

def _fetch_forms(case_id: int) -> List[Dict[str, Any]]:
    """
    Submissions:
      - Normal forms: event at submitted_at (kind='form')
      - KP-8: kind='hearing', dt from answers (hearing/appearance fields or SQL helper)
      - KP-12: kind='conciliation', dt from answers
      - KP-9: kind='status' (summons issued/scheduled), dt reconstructed from parts
      - Always attach 'by' from submitted_by_id when available
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id, kf.form_code, kf.form_name, s.status, s.submitted_at, s.submitted_by_id
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id=%s
            ORDER BY COALESCE(s.submitted_at, '4712-01-01'::timestamptz), s.submission_id
        """, [case_id])
        rows = cur.fetchall()

    out: List[Dict[str, Any]] = []
    for sid, code, name, status, submitted_at, submitted_by_id in rows:
        code_u = (code or "").upper()
        ans = _answers_for_submission(sid)
        by = _staff_name(submitted_by_id)
        meta: Dict[str, Any] = {"submission_id": sid, "status": status}
        if by: meta["by"] = by

        # Defaults
        event_dt = submitted_at
        event_kind = "form"
        title = "Form submitted"
        subtitle = f"{code} — {name}"

        # Special handling
        if code_u in ("KP-8", "KP-12", "KP-9"):
            maybe_dt = _extract_session_dt_from_answers(code_u, sid, ans)
            if maybe_dt:
                event_dt = maybe_dt
            if code_u == "KP-8":
                event_kind, title = "hearing", "Mediation hearing scheduled"
            elif code_u == "KP-12":
                event_kind, title = "conciliation", "Conciliation hearing scheduled"
            elif code_u == "KP-9":
                event_kind, title = "status", "Summons issued / schedule set"

        # Drafts go to end
        if str(status).upper() == "SUBMITTED":
            out.append(_row_to_event(event_dt, event_kind, title, subtitle, meta))
        else:
            out.append(_row_to_event(None, "form", "Draft saved", f"{code} — {name}", meta))
    return out

def _fetch_schedule_timeline(case_id: int) -> List[Dict[str, Any]]:
    """
    Fetch schedule timeline events from get_Schedule_timeline function.
    Returns events showing schedule changes (SET, RESCHEDULE, CANCEL).
    """
    with connection.cursor() as cur:
        try:
            cur.execute("SELECT * FROM get_Schedule_timeline(%s) ORDER BY event_seq ASC", [case_id])
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall() if cols else []
        except Exception as e:
            print(f"[timeline] Error fetching schedule timeline: {e}")
            return []
    
    out: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(zip(cols, row))
        event_kind = (data.get('event_kind') or '').upper()
        source = data.get('source') or ''
        notice_sid = data.get('notice_sid')
        old_schedule = data.get('old_schedule') or ''
        new_schedule = data.get('new_schedule') or ''
        event_at = data.get('event_at')
        staff_name = data.get('staff_name')
        log_message = data.get('log_message')
        event_seq = data.get('event_seq', 0)
        
        # Skip entries with empty schedules (incomplete reschedule records)
        if event_kind == 'RESCHEDULE' and not new_schedule and not old_schedule:
            continue
        
        # Build title based on event kind
        if event_kind == 'SET':
            title = f"Hearing scheduled ({source})" if source else "Hearing scheduled"
        elif event_kind == 'RESCHEDULE':
            title = f"Hearing rescheduled ({source})" if source else "Hearing rescheduled"
        elif event_kind == 'CANCEL':
            title = f"Hearing cancelled ({source})" if source else "Hearing cancelled"
        else:
            title = "Schedule event"
        
        # Use log_message if available, otherwise build subtitle
        if log_message:
            subtitle = log_message
        elif new_schedule:
            if old_schedule and event_kind == 'RESCHEDULE':
                subtitle = f"Changed from {old_schedule} to {new_schedule}"
            else:
                subtitle = f"Scheduled for: {new_schedule}"
        else:
            subtitle = ""
        
        meta = {
            "notice_sid": notice_sid,
            "source": source,
            "event_kind": event_kind,
            "old_schedule": old_schedule,
            "new_schedule": new_schedule,
            "event_seq": event_seq,
        }
        if staff_name:
            meta["by"] = staff_name
        
        out.append(_row_to_event(event_at, "hearing", title, subtitle, meta))
    
    return out

def _fetch_progress(case_id: int) -> List[Dict[str, Any]]:
    """
    case_progress_tracking + case_progress_type classification.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              cpt.progress_tracking_id,
              cpt.date_processed,
              cpt.remarks,
              cpt.processed_by_id,
              UPPER(pt.case_progress_type_name)
            FROM case_progress_tracking cpt
            JOIN case_progress_type pt ON pt.case_progress_type_id=cpt.case_progress_type_id
            WHERE cpt.blotter_case_id=%s
            ORDER BY cpt.date_processed ASC, cpt.progress_tracking_id ASC
        """, [case_id])
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for pid, when, remarks, by_id, tname in rows:
        by = _staff_name(by_id)
        meta = {"progress_id": pid}
        if by: meta["by"] = by
        subtitle = (remarks or "").strip()
        kind = "progress"
        title = tname.title()
        
        # Handle reschedule formatting
        if "RESCHEDULED" in tname or "RESCHEDULE" in tname:
            kind, title = "hearing", "Hearing rescheduled"
            # Parse and reformat subtitle for consistency
            if subtitle:
                # Check if it already has the "from X to Y" format
                if "rescheduled from" in subtitle.lower():
                    # Already formatted correctly, just ensure single "Reason:"
                    if subtitle.count("Reason:") > 1:
                        # Remove duplicate "Reason:" prefix
                        parts = subtitle.split("\n", 1)
                        if len(parts) > 1 and parts[1].startswith("Reason: Reason:"):
                            subtitle = parts[0] + "\n" + parts[1].replace("Reason: Reason:", "Reason:", 1)
                else:
                    # Just a reason provided, no schedule info
                    subtitle = f"Reason: {subtitle}"
            else:
                subtitle = "Reason: Rescheduled"
        elif "SCHEDULED HEARING" in tname:
            kind, title = "hearing", "Hearing scheduled"
        elif "HEARING HELD" in tname:
            kind, title = "hearing", "Hearing held"
        elif "CONCILIATION SCHEDULED" in tname:
            kind, title = "conciliation", "Conciliation scheduled"
        elif "CONCILIATION HELD" in tname:
            kind, title = "conciliation", "Conciliation held"
        elif "SETTLEMENT REACHED" in tname:
            kind, title = "status", "Settlement reached"
        elif "CERTIFICATION ISSUED" in tname:
            kind, title = "status", "Certification issued"
        elif "AWARD ISSUED" in tname:
            kind, title = "status", "Arbitration award issued"
        elif tname == "CLOSED":
            kind, title = "state", "Case closed"
        elif tname == "INTAKE":
            kind, title = "progress", "Intake"
        out.append(_row_to_event(when, kind, title, subtitle, meta))
    return out


def _pick_ts_col(table: str, candidates: List[str]) -> str:
    """Return the first existing timestamp-like column; else 'NULL'."""
    for c in candidates:
        if _column_exists(table, c):
            return c
    return "NULL"

def _fetch_payments_and_or(case_id: int, report_id: Optional[int]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    # ——— Case payments ———
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bcp.blotter_case_payment_id, bcp.date_of_payment, bcp.amount, ps.payment_status_name,
                   bcp.receipt_num, bcp.payee_id
            FROM blotter_case_payment bcp
            JOIN payment_status ps ON ps.payment_status_id = bcp.payment_status_id
            WHERE bcp.blotter_case_id=%s
            ORDER BY bcp.date_of_payment ASC, bcp.blotter_case_payment_id ASC
        """, [case_id])
        rows = cur.fetchall()
    for pid, paid_at, amount, pstatus, receipt, payee_staff_id in rows:
        meta = {
            "case_payment_id": pid,
            "amount": float(amount) if amount is not None else None,
            "status": pstatus,
            "receipt": receipt or "",
        }
        by = _staff_name(payee_staff_id)
        if by: meta["by"] = by
        subtitle = f"₱{amount:.2f} • Status: {pstatus}" if amount is not None else f"Status: {pstatus}"
        if receipt: subtitle += f" • OR: {receipt}"
        events.append(_row_to_event(paid_at, "payment", "Case payment", subtitle, meta))

    # ——— Official Receipt linked to CASE ———
    if _column_exists("official_receipt", "blotter_case_id"):
        ts_col = _pick_ts_col(
            "official_receipt",
            candidates=[
                "created_at", "issued_at", "date_issued", "issued_on",
                "or_date", "date_created", "datetime_created", "date"
            ],
        )
        ts_sql = f"({ts_col})::timestamptz" if ts_col != "NULL" else "NULL::timestamptz"
        with connection.cursor() as cur:
            cur.execute(f"""
                SELECT or_number, amount_paid, issued_by_staff_id, {ts_sql} AS ts
                FROM official_receipt
                WHERE blotter_case_id=%s
                ORDER BY ts ASC NULLS LAST, or_number ASC
            """, [case_id])
            rows = cur.fetchall()
        for or_no, amt, staff_id, ts in rows:
            meta = {"or_number": or_no, "amount": float(amt) if amt is not None else None}
            by = _staff_name(staff_id)
            if by: meta["by"] = by
            subtitle = f"₱{amt:.2f}" if amt is not None else ""
            events.append(_row_to_event(ts, "or", f"Official Receipt {or_no}", subtitle, meta))

    # ——— Report payments ———
    if report_id:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT brp.blotter_report_payment_id, brp.date_of_payment, brp.amount, ps.payment_status_name,
                       brp.receipt_num, brp.payee_id
                FROM blotter_report_payment brp
                JOIN payment_status ps ON ps.payment_status_id = brp.payment_status_id
                WHERE brp.blotter_report_id=%s
                ORDER BY brp.date_of_payment ASC, brp.blotter_report_payment_id ASC
            """, [report_id])
            rows = cur.fetchall()
        for pid, paid_at, amount, pstatus, receipt, payee_staff_id in rows:
            meta = {
                "report_payment_id": pid,
                "amount": float(amount) if amount is not None else None,
                "status": pstatus,
                "receipt": receipt or "",
            }
            by = _staff_name(payee_staff_id)
            if by: meta["by"] = by
            subtitle = f"₱{amount:.2f} • Status: {pstatus}" if amount is not None else f"Status: {pstatus}"
            if receipt: subtitle += f" • OR: {receipt}"
            events.append(_row_to_event(paid_at, "payment", "Report payment", subtitle, meta))

        # ——— Official Receipt linked to REPORT ———
        if _column_exists("official_receipt", "blotter_report_id"):
            ts_col = _pick_ts_col(
                "official_receipt",
                candidates=[
                    "created_at", "issued_at", "date_issued", "issued_on",
                    "or_date", "date_created", "datetime_created", "date"
                ],
            )
            ts_sql = f"({ts_col})::timestamptz" if ts_col != "NULL" else "NULL::timestamptz"
            with connection.cursor() as cur:
                cur.execute(f"""
                    SELECT or_number, amount_paid, issued_by_staff_id, {ts_sql} AS ts
                    FROM official_receipt
                    WHERE blotter_report_id=%s
                    ORDER BY ts ASC NULLS LAST, or_number ASC
                """, [report_id])
                rows = cur.fetchall()
            for or_no, amt, staff_id, ts in rows:
                meta = {"or_number": or_no, "amount": float(amt) if amt is not None else None}
                by = _staff_name(staff_id)
                if by: meta["by"] = by
                subtitle = f"₱{amt:.2f}" if amt is not None else ""
                events.append(_row_to_event(ts, "or", f"Official Receipt {or_no}", subtitle, meta))

    return events


def _fetch_status_history(case_id: int) -> List[Dict[str, Any]]:
    if not _column_exists("blotter_case_status_history", "blotter_case_id"):
        return []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_status_history_id, status_kind, status_value_id, remarks, changed_at, changed_by_id
            FROM blotter_case_status_history
            WHERE blotter_case_id=%s
            ORDER BY changed_at ASC, case_status_history_id ASC
        """, [case_id])
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for hid, kind, value_id, remarks, when, by_id in rows:
        by = _staff_name(by_id)
        meta = {"history_id": hid, "kind": kind}
        if by: meta["by"] = by
        title = "Status changed"
        if kind:
            title = f"{kind.title()} updated"
        out.append(_row_to_event(when, "status", title, (remarks or "").strip(), meta))
    return out

def _fetch_media(case_id: int) -> List[Dict[str, Any]]:
    if not _column_exists("case_hearing_media", "blotter_case_id"):
        return []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_hearing_media_id, uploaded_at, media_kind, caption, submission_id, uploaded_by_id
            FROM case_hearing_media
            WHERE blotter_case_id=%s AND COALESCE(is_deleted, FALSE)=FALSE
            ORDER BY uploaded_at ASC, case_hearing_media_id ASC
        """, [case_id])
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for mid, when, mkind, caption, sub_id, by_id in rows:
        meta = {"media_id": mid, "kind": mkind, "submission_id": sub_id}
        by = _staff_name(by_id)
        if by: meta["by"] = by
        subtitle = mkind.title()
        if caption: subtitle += f" — {caption}"
        out.append(_row_to_event(when, "media", "Hearing media uploaded", subtitle, meta))
    return out

def _fetch_state_changes(case_id: int) -> List[Dict[str, Any]]:
    """Fetch case state and settlement status changes from case_state_history table."""
    if not _column_exists("case_state_history", "blotter_case_id"):
        return []
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                changed_at,
                transition_kind,
                old_state,
                new_state,
                remarks,
                changed_by_id,
                changed_by_name
            FROM case_state_history
            WHERE blotter_case_id = %s
            ORDER BY changed_at ASC
        """, [case_id])
        rows = cur.fetchall()
    
    out: List[Dict[str, Any]] = []
    for when, trans_kind, old_state, new_state, remarks, by_id, by_name in rows:
        # Determine the event kind based on transition_kind
        if 'STATE' in (trans_kind or '').upper():
            kind = "state"
            title = f"Case state changed: {old_state or 'N/A'} → {new_state}"
        elif 'SETTLEMENT' in (trans_kind or '').upper():
            kind = "settlement"
            title = f"Settlement status changed: {old_state or 'N/A'} → {new_state}"
        else:
            kind = "status"
            title = f"Status changed: {old_state or 'N/A'} → {new_state}"
        
        meta = {
            "transition_kind": trans_kind,
            "old_state": old_state,
            "new_state": new_state,
        }
        
        # Use provided name or resolve from staff_id
        by = by_name or _staff_name(by_id)
        if by:
            meta["by"] = by
        
        subtitle = remarks or ""
        out.append(_row_to_event(when, kind, title, subtitle, meta))
    
    return out


# ----------------------------
# main builder
# ----------------------------
def get_case_timeline(case_id: int) -> Dict[str, Any]:
    header = _fetch_header(case_id)
    if not header:
        return {"header": None, "events": [], "groups": []}

    events: List[Dict[str, Any]] = []

    # report (pre-case)
    if header["report_id"]:
        events += _fetch_report_event(header["report_id"])

    # case opened
    events += _fetch_case_opened(header)

    # forms (with actor & special handling for KP-8/KP-12/KP-9)
    events += _fetch_forms(case_id)
    
    # schedule timeline (from get_Schedule_timeline function)
    events += _fetch_schedule_timeline(case_id)

    # progress (hearing/conciliation/intake/settlement etc.)
    events += _fetch_progress(case_id)

    # payments + ORs (case + report)
    events += _fetch_payments_and_or(case_id, header["report_id"])

    # status history (append-only)
    events += _fetch_status_history(case_id)

    # photos/docs attached to hearings
    events += _fetch_media(case_id)
    
    # state and settlement changes
    events += _fetch_state_changes(case_id)

    # sort chronologically
    def _stable_key(e: Dict[str, Any]) -> Tuple[float, int]:
        meta = e.get("meta", {}) or {}
        any_id = (
            meta.get("progress_id")
            or meta.get("submission_id")
            or meta.get("case_payment_id")
            or meta.get("report_payment_id")
            or meta.get("history_id")
            or meta.get("media_id")
            or meta.get("event_seq")
            or 0
        )
        return (e["ts"], int(any_id) if isinstance(any_id, int) else 0)

    events.sort(key=_stable_key, reverse=True)

    # group by calendar day (YYYY-MM-DD) for the template
    groups: List[Dict[str, Any]] = []
    current_key: Optional[str] = None
    for ev in events:
        if ev["dt"] is not None:
            day_obj = ev["dt"].date()
            day_key = day_obj.isoformat()
        else:
            day_obj = None
            day_key = "—"

        if day_key != current_key:
            groups.append({"day": day_obj, "items": []})
            current_key = day_key

        groups[-1]["items"].append(ev)
        
    return {
        "header": {
            "case_id": header["case_id"],
            "case_num": header["case_num"],
            "case_name": header["case_name"],
            "type_name": header["type_name"],
            "nature_name": header["nature_name"],
        },
        "events": events,   # flat list
        "groups": groups,   # per-day groups for the improved template
    }
