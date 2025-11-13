# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime
import os
import uuid

from lupon_mem.services.forms.kp8 import KP8Handler  # reuse its normalization
from lupon_mem.services.forms.kp10 import KP10Handler
from lupon_mem.services.forms.kp11 import KP11Handler
from lupon_mem.services.forms.kp12 import KP12Handler
from django.views.decorators.http import require_POST

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}
LUPON_ROLES_LIST = ["BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"]  # pass to templates

from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET

from lupon_mem.utils.http import json_ok, json_err, flash_success, flash_warning, require_post_view
from lupon_mem.utils.params import post_int, post_bool, post_str
from lupon_mem.services import hearings as svc_hear
from django.views.decorators.csrf import csrf_protect
import logging
log = logging.getLogger(__name__)

from django.shortcuts import render, redirect
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    HttpResponseNotFound,
)
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import connection, transaction
from django.urls import reverse
from django.conf import settings

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.supabase_client import supabase

from lupon_mem.services.form_renderer import render_preview_png, render_final_pdf
from django.core.exceptions import ValidationError
from lupon_mem.constants import KP_FORMS_CATALOG   # static chooser catalog

from django.db.models import Prefetch
from django.views.generic import TemplateView, View
from django.shortcuts import get_object_or_404, redirect
from lupon_mem.models import BlotterKpSubmission, KpFormField, KpField, BlotterKpAnswer
# views.py  — replace the whole helper with this
from django.conf import settings

# lupon_mem/views.py  (add these imports near the top)
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from lupon_mem.services.case_state import close_case, reopen_case
from lupon_mem.services.helpers import (
    ordinal,
    one_val, row, rows,
    get_form_id, submitted_codes, latest_submission_for_codes,
    latest_notice_submitted_at, is_hearing_held, hearings_held, hearing_gate,
    prefill_minimal_for_case, create_and_submit_form_from_prefill,
    list_case_photos, list_mediation_photos,
    get_person_mobile_number,
    slice_until_code,
)

from django.db import DatabaseError



# caching / logging
from django.core.cache import cache
import time, logging
log = logging.getLogger(__name__)

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}




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

    

    

def _latest_notice_submitted_at(case_id: int):
    """Newest submitted_at among KP-8 / KP-12 for this case, or None."""
    with connection.cursor() as cur:
        cur.execute("""
            WITH forms AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code) IN ('KP-8','KP-12')
            )
            SELECT MAX(s.submitted_at)
            FROM blotter_kp_submission s
            WHERE s.blotter_case_id=%s
              AND s.form_id IN (SELECT form_id FROM forms)
              AND UPPER(s.status)='SUBMITTED'
        """, [case_id])
        row = cur.fetchone()
    return row[0] if row else None



def _hearing_gate(case_id: int) -> dict:
    """
    Gate computed entirely from fn_case_mediation_hearings(case_id).
    Returns:
      {
        'hearings_held': int,                 # rows with hearing_held=true or held_at not null
        'hearings_set': int,                  # total rows from the TVF
        'latest_notice_submitted_at': datetime|None,
        'latest_notice_submission_id': int|None,
        'latest_notice_code': str|None,       # 'KP-8' or 'KP-12'
        'latest_notice_outstanding': bool,    # latest row NOT marked held
        'settlement_name': str|None,
        'can_issue_notice': bool,
        'reason': str,
        'limit_reached': bool,                # 3 held already
      }
    """
    rows = []
    with connection.cursor() as cur:
        # 1) Pull per-hearing rows (one per KP-8/12)
        cur.execute("""
            SELECT
              hearing_no, source, notice_sid, notice_created_at,
              hearing_date, hearing_time,
              hearing_held, held_at, held_remarks,
              complainant_attended, respondent_attended,
              settlement_outcome
            FROM fn_case_mediation_hearings(%s)
            ORDER BY notice_created_at ASC NULLS LAST, notice_sid ASC
        """, [case_id])
        rows = cur.fetchall()

        # 2) Settlement text (same as before)
        cur.execute("""
            SELECT COALESCE(ss.settlement_status_name,'PENDING') AS name
            FROM blotter_case bc
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        st = cur.fetchone()
        settlement_name = (st[0] if st else None)

    # Columns (index map from SELECT above)
    IDX = {
        "hearing_no": 0, "source": 1, "notice_sid": 2, "notice_created_at": 3,
        "hearing_date": 4, "hearing_time": 5,
        "hearing_held": 6, "held_at": 7, "held_remarks": 8,
        "compl_att": 9, "resp_att": 10, "settlement_outcome": 11,
    }

    hearings_set = len(rows)
    hearings_held = sum(1 for r in rows if (bool(r[IDX["hearing_held"]]) or r[IDX["held_at"]] is not None))

    # Latest = the last row in our ORDER BY (ASC), or compute max explicitly
    latest_row = rows[-1] if rows else None
    latest_at  = latest_row[IDX["notice_created_at"]] if latest_row else None
    latest_sid = int(latest_row[IDX["notice_sid"]]) if latest_row else None
    latest_code= latest_row[IDX["source"]] if latest_row else None

    # “Outstanding” means the latest hearing isn't marked HELD yet
    latest_outstanding = False
    if latest_row:
        latest_outstanding = not (bool(latest_row[IDX["hearing_held"]]) or latest_row[IDX["held_at"]] is not None)

    # Last held timestamp across all hearings (for info/consistency)
    last_held_at = None
    if rows:
        held_times = [r[IDX["held_at"]] for r in rows if r[IDX["held_at"]] is not None]
        last_held_at = max(held_times) if held_times else None

    # Same gating rules you had
    settlement_up = (settlement_name or '').strip().upper()
    settlement_pending = settlement_up in ('PENDING', 'NOT SETTLED', 'UNSET', 'FOR MEDIATION', 'FOR CONCILIATION')

    limit_reached = hearings_held >= 3
    can_issue = (not limit_reached) and (not latest_outstanding) and settlement_pending

    reason = ""
    if limit_reached:
        reason = "Limit reached: 3 hearings already held (proceed to Arbitration/CFA)."
    elif latest_outstanding:
        reason = "There is a scheduled hearing not yet marked HELD."
    elif not settlement_pending:
        reason = f"Settlement is “{settlement_name}” (set to Pending/Not Settled to schedule another)."

    return {
        "hearings_held": int(hearings_held or 0),
        "hearings_set": int(hearings_set or 0),
        "latest_notice_submitted_at": latest_at,
        "latest_notice_submission_id": latest_sid,
        "latest_notice_code": latest_code,
        "latest_notice_outstanding": bool(latest_outstanding),
        "settlement_name": settlement_name,
        "can_issue_notice": bool(can_issue),
        "reason": reason,
        "limit_reached": bool(limit_reached),
    }




def _fetch_lookups() -> Dict[str, List[Tuple[int, str]]]:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name"
        )
        complaint_titles = cur.fetchall()

        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()

        cur.execute(
            "SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY settlement_status_name"
        )
        settlement_statuses = cur.fetchall()

        cur.execute(
            """
            SELECT b.blotter_report_id, COALESCE(b.incident_subject,'(no subject)') || ' — ' || to_char(b.date_time_reported, 'YYYY-MM-DD HH24:MI')
            FROM blotter_report b
            ORDER BY b.date_time_reported DESC
            LIMIT 200
        """
        )
        reports = cur.fetchall()

    return {
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlement_statuses,
        "reports": reports,
    }


def _to_none_if_blank(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip()
    return s if s else None


