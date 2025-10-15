from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, time as dtime
from django.db import connection
from django.utils import timezone

def _to_display_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Return a timezone-naive datetime in the current timezone for display in templates.
    """
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return timezone.make_naive(dt, timezone.get_current_timezone())
    return dt  # already naive

def _to_sort_ts(dt: Optional[datetime]) -> float:
    """
    Return a numeric timestamp (UTC seconds) for sorting. None -> +inf so it goes last.
    Handles both naive and aware datetimes safely.
    """
    if dt is None:
        return float("inf")
    try:
        if timezone.is_aware(dt):
            aware = dt
        else:
            aware = timezone.make_aware(dt, timezone.get_current_timezone(), is_dst=None)
        return aware.astimezone(timezone.utc).timestamp()
    except Exception:
        return float("inf")

def _row_to_event(
    dt: Optional[datetime],
    kind: str,
    title: str,
    subtitle: str = "",
    meta: Dict[str, Any] | None = None
):
    disp = _to_display_naive(dt)
    return {
        "dt": disp,                        # safe for template (always naive or None)
        "ts": _to_sort_ts(dt),             # numeric sort key (always a float)
        "kind": kind,                      # "report" | "case" | "form"
        "title": title.strip(),
        "subtitle": (subtitle or "").strip(),
        "meta": meta or {},
    }

def get_case_timeline(case_id: int) -> Dict[str, Any]:
    """
    Build a case timeline from existing tables:
      - blotter_report -> 'Report filed' (if linked)
      - blotter_case   -> 'Case opened'
      - blotter_kp_submission + kp_form -> 'Form {code} submitted' (or Draft saved)
    """
    # --- header ---
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                bc.blotter_case_id,
                COALESCE(bc.blotter_case_num, bc.blotter_case_name) AS case_num,
                bc.blotter_case_name,
                bc.date_filed, bc.time_filed,
                bc.blotter_report_id,
                COALESCE(ct.complaint_title_name,'—') AS type_name,
                COALESCE(cn.case_name,'—')           AS nature_name
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature    cn ON cn.case_nature_id    = bc.case_nature_id
            WHERE bc.blotter_case_id=%s
        """, [case_id])
        hdr = cur.fetchone()
        if not hdr:
            return {"header": None, "events": []}

        (cid, case_num, case_name, date_filed, time_filed,
         report_id, type_name, nature_name) = hdr

    events: List[Dict[str, Any]] = []

    # Report (if any)
    if report_id:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT incident_subject, date_time_reported
                FROM blotter_report
                WHERE blotter_report_id=%s
            """, [report_id])
            rpt = cur.fetchone()
            if rpt:
                subject, dt_reported = rpt
                events.append(_row_to_event(
                    dt_reported,
                    "report",
                    "Report filed",
                    subject or ""
                ))

    # Case opened (combine date+time; if time missing, use midnight)
    opened_dt: Optional[datetime] = None
    try:
        if date_filed is not None and time_filed is not None:
            opened_dt = datetime.combine(
                date_filed,
                time_filed if isinstance(time_filed, dtime) else dtime.min
            )
        elif date_filed is not None:
            opened_dt = datetime.combine(date_filed, dtime.min)
    except Exception:
        opened_dt = None

    events.append(_row_to_event(
        opened_dt,
        "case",
        "Case opened",
        f"{type_name} — {nature_name}"
    ))

    # Forms (submissions)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                s.submission_id,
                kf.form_code,
                kf.form_name,
                s.status,
                s.submitted_at
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id=%s
            ORDER BY COALESCE(s.submitted_at, '4712-01-01'::timestamp) ASC, s.submission_id ASC
        """, [case_id])
        for sid, code, name, status, submitted_at in cur.fetchall():
            title = f"{code} — {name}"
            if status == "SUBMITTED":
                events.append(_row_to_event(
                    submitted_at,
                    "form",
                    "Form submitted",
                    title,
                    {"submission_id": sid, "status": status}
                ))
            else:
                # drafts have no submitted_at — put them at the end
                events.append(_row_to_event(
                    None,
                    "form",
                    "Draft saved",
                    title,
                    {"submission_id": sid, "status": status}
                ))

    # Sort by numeric timestamp (None -> +inf goes last), then by submission_id for stability
    events.sort(key=lambda e: (e["ts"], e.get("meta", {}).get("submission_id", 0)))

    header = {
        "case_id": cid,
        "case_num": case_num,
        "case_name": case_name,
        "type_name": type_name,
        "nature_name": nature_name,
    }
    return {"header": header, "events": events}
