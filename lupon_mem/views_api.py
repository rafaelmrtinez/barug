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
from .models import BlotterKpSubmission, KpFormField, KpField, BlotterKpAnswer
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
from lupon_mem.services.all_helpers import *


# caching / logging
from django.core.cache import cache
import time, logging
log = logging.getLogger(__name__)

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}



@session_login_required
@role_required(*LUPON_ROLES)
def submission_pdf(request: HttpRequest, submission_id: int):
    try:
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        return HttpResponse(str(e), status=400)
    except Exception:
        return HttpResponse("Failed to generate PDF.", status=500)

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    resp["X-Frame-Options"] = "SAMEORIGIN"
    return resp

# --- preview image (PNG) ---
@session_login_required
@role_required(*LUPON_ROLES)
def preview_image(request: HttpRequest):
    form_id = int(request.GET["form_id"])
    submission_id = request.GET.get("submission_id")
    answers_json = request.GET.get("answers")
    img_bytes = render_preview_png(
        form_id=form_id, submission_id=submission_id, answers_json=answers_json
    )
    return HttpResponse(img_bytes, content_type="image/png")




@role_required(*LUPON_ROLES)
@session_login_required
def save_answers(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    data = request.POST
    case_id = int(data["case_id"])
    form_id = int(data["form_id"])
    submission_id = data.get("submission_id")

    import json as _json
    payload = _json.loads(data["answers"])  # {field_id: value}

    with transaction.atomic():
        with connection.cursor() as cur:
            if submission_id:
                sid = int(submission_id)
            else:
                cur.execute(
                    """
                  INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
                  VALUES (%s,%s,'DRAFT') RETURNING submission_id
                """,
                    [case_id, form_id],
                )
                sid = cur.fetchone()[0]

            for field_id, value in payload.items():
                cur.execute(
                    """
                  INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                  VALUES (%s,%s,%s)
                  ON CONFLICT (submission_id, field_id)
                  DO UPDATE SET value_json=EXCLUDED.value_json
                """,
                    [sid, int(field_id), _json.dumps(value)],
                )

    return JsonResponse({"ok": True, "submission_id": sid})



# --- AJAX: submit & generate PDF ---
@role_required(*LUPON_ROLES)
@session_login_required
def submit_form(request: HttpRequest):
    """
    Save any posted answers, render PDF, upload, mark submitted, then allow the
    form-specific handler to persist its auto-computed answers via a universal hook.

    Extras retained:
      • KP-23: record 'who filed' meta (party/person) via function.
      • KP-16: set case status SETTLED, optional MED summary generation, auto-mark hearing HELD.
    """
    import json as _json
    import json
    from datetime import datetime as _dt
    from django.db import transaction
    from django.urls import reverse
    from django.http import JsonResponse
    from django.conf import settings
    from django.contrib import messages
    from zoneinfo import ZoneInfo

    log = logging.getLogger(__name__)

    # ---------- Parse body ----------
    try:
        data = _json.loads(request.body.decode())
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    try:
        submission_id = int(data["submission_id"])
        case_id       = int(data["case_id"])
    except Exception:
        return JsonResponse({"ok": False, "error": "Missing or invalid submission_id/case_id."}, status=400)

    # ---------- Persist latest posted answers (generic for ALL forms) ----------
    answers_payload = data.get("answers")
    if isinstance(answers_payload, dict) and answers_payload:
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    for field_id_str, value in answers_payload.items():
                        cur.execute("""
                            INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (submission_id, field_id)
                            DO UPDATE SET value_json = EXCLUDED.value_json
                        """, [submission_id, int(field_id_str), _json.dumps(value)])
        except Exception:
            log.exception("submit_form upsert answers failed (submission_id=%s)", submission_id)
            return JsonResponse({"ok": False, "error": "Failed to save answers before rendering."}, status=500)

    # ---------- Ensure processed_by audit fields are present ----------
    try:
        auth = request.session.get("auth") or {}
        staff_id_raw = auth.get("staff_id")
        if staff_id_raw:
            staff_id = int(staff_id_raw)
            with transaction.atomic():
                with connection.cursor() as cur:
                    # Fetch staff display info
                    cur.execute("""
                        SELECT
                          TRIM(
                              COALESCE(p.first_name,'') || ' ' ||
                              COALESCE(p.middle_name,'') || ' ' ||
                              COALESCE(p.last_name,'')  || ' ' ||
                              COALESCE(p.suffix,'')
                          ) AS full_name,
                          COALESCE(r.role_name,'') AS role_name
                        FROM staff s
                        JOIN person p ON p.person_id = s.person_id
                        LEFT JOIN rolee r ON r.role_id = s.role_id
                        WHERE s.staff_id = %s
                        LIMIT 1
                    """, [staff_id])
                    row = cur.fetchone() or ("", "")
                    full_name = (row[0] or "").strip()
                    role_name = (row[1] or "").strip()

                    tz_name = getattr(settings, "TIME_ZONE", None)
                    try:
                        now = _dt.now(ZoneInfo(tz_name)) if tz_name else _dt.now()
                    except Exception:
                        now = _dt.now()
                    values_map = {
                        "processed_by_staff_id": str(staff_id),
                        "processed_by_staff_name": full_name,
                        "processed_by_staff": full_name,  # alias support
                        "processed_by_staff_position": role_name,
                        "processed_on_date": now.date().isoformat(),
                        "processed_on_time": now.strftime("%I:%M %p").lstrip("0").lower(),
                    }

                    cur.execute(
                        "SELECT field_code, field_id FROM kp_field WHERE field_code IN %s",
                        [tuple(values_map.keys())]
                    )
                    code_to_id = {fc: fid for fc, fid in cur.fetchall()}

                    import json as _json
                    for code, val in values_map.items():
                        fid = code_to_id.get(code)
                        if not fid:
                            continue
                        cur.execute(
                            """
                            INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (submission_id, field_id)
                            DO UPDATE SET value_json = EXCLUDED.value_json
                            """,
                            [submission_id, int(fid), _json.dumps(val)]
                        )
    except Exception:
        log.exception("submit_form failed to persist processed_by answers (submission_id=%s)", submission_id)
        # Non-fatal; continue

    # ---------- Render PDF ----------
    try:
        from lupon_mem.services.form_renderer import render_final_pdf
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception:
        log.exception("submit_form render_final_pdf failed")
        return JsonResponse({"ok": False, "error": "Failed to generate PDF."}, status=500)

    # ---------- Upload to Supabase (best-effort) ----------
    bucket = getattr(settings, "SUPABASE_BUCKET", "documents")
    path = f"blotter/{case_id}/{filename}"
    storage_url = None
    try:
        supabase.storage.from_(bucket).upload(path, pdf_bytes,
                                              {"contentType": "application/pdf", "upsert": "true"})
        try:
            pub = supabase.storage.from_(bucket).get_public_url(path)
            storage_url = pub.get("publicUrl") if isinstance(pub, dict) else (pub if isinstance(pub, str) else None)
        except Exception:
            storage_url = None
        if not storage_url:
            try:
                signed = supabase.storage.from_(bucket).create_signed_url(path, 60 * 60 * 24 * 7)
                storage_url = (signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")) \
                              if isinstance(signed, dict) else None
            except Exception:
                storage_url = None
    except Exception:
        storage_url = None

    # ---------- Mark SUBMITTED ----------
    try:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE blotter_kp_submission "
                "SET status='SUBMITTED', submitted_at=now() "
                "WHERE submission_id=%s",
                [submission_id]
            )
    except Exception:
        log.exception("submit_form failed to mark SUBMITTED (submission_id=%s)", submission_id)
        return JsonResponse({"ok": False, "error": "Failed to finalize submission."}, status=500)

    # ---------- Determine form_code + form_id ----------
    row_fc = None
    form_id_of_submission = None
    form_code = None
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT UPPER(kf.form_code), s.form_id
                  FROM blotter_kp_submission s
                  JOIN kp_form kf ON kf.form_id = s.form_id
                 WHERE s.submission_id=%s
            """, [submission_id])
            row_fc = cur.fetchone()
            if row_fc:
                form_code = str(row_fc[0])
                form_id_of_submission = int(row_fc[1])
    except Exception:
        log.exception("submit_form failed to lookup form_code (submission_id=%s)", submission_id)

    # ---------- Universal: let the specific handler persist its computed answers ----------
    try:
        if form_code and form_id_of_submission:
            from lupon_mem.services.forms import get_handler
            handler = get_handler(form_code)
            out_map = {}
            try:
                out_map = handler.build_name_value_map(form_id_of_submission, submission_id) or {}
            except Exception:
                from lupon_mem.services.form_shared import answers_to_names_strict
                out_map = answers_to_names_strict(form_id_of_submission, submission_id)

            if hasattr(handler, "persist_computed"):
                handler.persist_computed(
                    form_id=form_id_of_submission,
                    submission_id=submission_id,
                    case_id=case_id,
                    out_map=out_map,
                )
    except Exception:
        log.exception("persist_computed hook failed (submission_id=%s)", submission_id)

    # ---------- KP-23: record who filed (party/person) ----------
    try:
        if form_code and form_code.upper() == "KP-23":
            meta = data.get("meta") or {}
            party_raw  = (data.get("filed_by_party") or meta.get("filed_by_party") or "").strip().upper()
            person_raw = (data.get("filed_by_person_id") or meta.get("filed_by_person_id"))

            if party_raw not in ("COMPLAINANT", "RESPONDENT"):
                return JsonResponse({"ok": False,
                                     "error": "For KP-23, 'filed_by_party' must be COMPLAINANT or RESPONDENT."},
                                    status=400)
            try:
                party_person_id = int(person_raw)
            except Exception:
                return JsonResponse({"ok": False,
                                     "error": "For KP-23, 'filed_by_person_id' must be a valid person_id integer."},
                                    status=400)

            staff_id = (request.session.get("auth") or {}).get("staff_id")

            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT insert_kp23_filer_meta(%s,%s,%s,%s)",
                        [submission_id, party_raw, party_person_id, staff_id]
                    )
            except Exception as e:
                msg = str(e)
                if "P6310" in msg:
                    return JsonResponse({"ok": False, "error": "Submission is not KP-23."}, status=400)
                if "P6311" in msg:
                    return JsonResponse({"ok": False, "error": "Submission not found or case mismatch."}, status=400)
                if "P6312" in msg:
                    return JsonResponse({"ok": False, "error": "Invalid party type for KP-23."}, status=400)
                if "P6313" in msg:
                    return JsonResponse({"ok": False, "error": "Selected person is not on that side for this case."}, status=400)
                if "P6314" in msg:
                    return JsonResponse({"ok": False, "error": "Filer meta already exists for this submission."}, status=400)
                log.exception("submit_form KP-23 meta insert failed (submission_id=%s)", submission_id)
                return JsonResponse({"ok": False, "error": "Failed to record KP-23 filer."}, status=500)

            try:
                filed_by_text = f"{party_raw.title()} — person_id #{party_person_id}"
                if form_id_of_submission:
                    with connection.cursor() as cur:
                        cur.execute("""
                            SELECT f.field_id
                              FROM kp_form_field kff
                              JOIN kp_field f ON f.field_id = kff.field_id
                             WHERE kff.form_id = %s AND LOWER(f.field_code) = 'kp23_filed_by'
                             LIMIT 1
                        """, [int(form_id_of_submission)])
                        row = cur.fetchone()
                    if row:
                        fb_field_id = int(row[0])
                        with transaction.atomic():
                            with connection.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (submission_id, field_id)
                                    DO UPDATE SET value_json = EXCLUDED.value_json
                                """, [submission_id, fb_field_id, json.dumps(filed_by_text)])
            except Exception:
                log.warning("submit_form KP-23: failed to persist kp23_filed_by display text", exc_info=True)
    except Exception:
        log.exception("submit_form KP-23 filer block error (submission_id=%s)", submission_id)
        return JsonResponse({"ok": False, "error": "KP-23 filer recording failed unexpectedly."}, status=500)

    # ---------- KP-16: set case SETTLED on submit ----------
    extra_files = []
    try:
        if form_code and form_code.upper() == "KP-16":
            staff_id = (request.session.get("auth") or {}).get("staff_id")
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Settled via KP-16', staff_id])
            messages.success(request, "Settlement finalized (KP-16 submitted).")
    except Exception:
        log.exception("Failed to set case SETTLED on KP-16 submit")

    # ---------- KP-16: optional MEDx settled summary (feature-flag) ----------
    try:
        if form_code and form_code.upper() == "KP-16" and getattr(settings, "LUPON_AUTOGEN_MEDX", False):
            from lupon_mem.services.med_settled import _autogen_settled_summary
            extra_files = _autogen_settled_summary(case_id=case_id, kp16_submission_id=submission_id) or []
    except Exception as e:
        print("[MED-SETTLED][DEBUG] auto generation failed:", e)

    # ---------- KP-16: auto-mark hearing as HELD when triggered from hearing page ----------
    try:
        if form_code and form_code.upper() == "KP-16":
            sid = request.session.get("auto_mark_hearing_after_kp16_sid")
            sid_case = request.session.get("auto_mark_hearing_case_id")
            if sid and sid_case and int(sid_case) == int(case_id):
                try:
                    with connection.cursor() as cur:
                        cur.execute("""
                            UPDATE blotter_hearing
                               SET held = TRUE,
                                   held_at = NOW()
                             WHERE blotter_case_id = %s
                               AND notice_submission_id = %s
                        """, [case_id, int(sid)])
                    messages.success(request, "Hearing automatically marked as HELD.")
                    print(f"[auto-held] case_id={case_id} notice_sid={sid} (via KP-16)")
                except Exception as e:
                    log.exception("Auto-mark hearing HELD failed (case_id=%s, sid=%s)", case_id, sid)
                    messages.warning(request, "Settlement saved, but auto-marking the hearing as HELD failed. Please mark it manually.")
                request.session.pop("auto_mark_hearing_after_kp16_sid", None)
                request.session.pop("auto_mark_hearing_case_id", None)
                request.session.modified = True
    except Exception as e:
        log.exception("submit_form post-KP16 auto-held hook error: %s", e)

    # ---------- Local download url (always works) ----------
    local_download = request.build_absolute_uri(reverse("lupon_mem:submission_pdf", args=[submission_id]))

    return JsonResponse({
        "ok": True,
        "file": filename,
        "download_url": local_download,
        "storage_url": storage_url,
        "extra_files": extra_files,
    })

# --- lightweight staff suggest for officer picker (KP-9 offcr_name) ---
@session_login_required
@role_required(*LUPON_ROLES)
def staff_suggest(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'') || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee  r ON r.role_id = s.role_id
            WHERE (r.role_name IN ('BARANGAY LUPON MEMBER','BARANGAY LUPON PRESIDENT'))
              AND (
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || p.last_name) ILIKE %s
              )
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like],
        )
        rows = cur.fetchall()

    return JsonResponse({"results": [{"id": r[0], "name": r[1].strip()} for r in rows]})


@session_login_required
@role_required(*LUPON_ROLES)
def staff_suggest_all(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'') || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee  r ON r.role_id = s.role_id
            WHERE r.role_name IN (
                'BARANGAY LUPON MEMBER',
                'BARANGAY LUPON PRESIDENT',
                'BARANGAY SECRETARY',
                'BARANGAY CAPTAIN'
            )
              AND (
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || p.last_name) ILIKE %s
              )
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like],
        )
        rows = cur.fetchall()

    return JsonResponse({"results": [{"id": r[0], "name": r[1].strip()} for r in rows]})


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def resident_lookup(request: HttpRequest):
    """
    A nice standalone page (or embeddable view) to search residents and pick one.
    Supports ?target=INPUT_ID — if provided and the page is opened from a parent form,
    clicking "Use this person" will attempt to fill that INPUT_ID in the opener window.
    """
    target_input = (request.GET.get("target") or "").strip() or None
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    return render(request, "lupon_mem/resident_lookup.html", {
        "target_input": target_input,
        'page_path': f'{user_role} / Resident Lookup',
        'page_title': 'Resident Lookup'
    })


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_GET
def resident_quick_search(request: HttpRequest):
    """
    GET /lupon_mem/resident/quick-search/?q=term
    Returns top residents for the autocomplete (id, name, purok, address).
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"ok": True, "results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              p.person_id AS id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,''))    AS name,
              coalesce(ps.purok_sitio_name,'') AS purok,
              trim(concat_ws(', ',
                    NULLIF(a.street,''),
                    NULLIF(ps.purok_sitio_name,''),
                    NULLIF(a.barangay,''),
                    NULLIF(a.city,'')
              )) AS address
            FROM person p
            LEFT JOIN addresss a   ON a.address_id = p.address_id
            LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
            WHERE
                 p.first_name ILIKE %s
              OR p.last_name  ILIKE %s
              OR (p.first_name || ' ' || coalesce(p.middle_name,'') || ' ' || p.last_name) ILIKE %s
              OR a.street ILIKE %s
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like, like],
        )
        rows = cur.fetchall()

    results = [
        {"id": r[0], "name": (r[1] or "").strip(), "purok": (r[2] or "").strip(), "address": (r[3] or "").strip()}
        for r in rows
    ]
    return JsonResponse({"ok": True, "results": results})




@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_GET
def person_lookup(request: HttpRequest):
    """
    GET /lupon_mem/person/lookup/?person_id=123
    -> { ok: true, person: { id, name } }
    """
    pid = (request.GET.get("person_id") or "").strip()
    if not pid.isdigit():
        return JsonResponse({"ok": False, "error": "Invalid person_id."}, status=400)

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              p.person_id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,'')) AS name
            FROM person p
            WHERE p.person_id=%s
            """,
            [int(pid)],
        )
        row = cur.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "Not found."}, status=404)

    return JsonResponse({"ok": True, "person": {"id": row[0], "name": (row[1] or "").strip()}})
# ---------- Resident Lookup UI (optional standalone page) ----------



# --- lightweight person suggest for subpoena_to / subpoena_witness (KP-13) ---
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def person_suggest(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT p.person_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'')  || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM person p
            WHERE
                 p.first_name ILIKE %s
              OR p.last_name  ILIKE %s
              OR (p.first_name || ' ' || coalesce(p.middle_name,'') || ' ' || p.last_name) ILIKE %s
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like],
        )
        rows = cur.fetchall()

    return JsonResponse({"results": [{"id": r[0], "name": (r[1] or "").strip()} for r in rows]})



@session_login_required
@role_required(*LUPON_ROLES)
@require_GET
def staff_lookup(request: HttpRequest):
    """
    JSON lookup for a single staff member.
    Input:  GET ?staff_id=123
    Output: { ok: true, result: { id, person_id, name, role, mobile } }
    """
    sid_raw = (request.GET.get("staff_id") or "").strip()
    if not sid_raw.isdigit():
        return JsonResponse({"ok": False, "error": "Invalid staff_id."}, status=400)

    staff_id = int(sid_raw)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              s.staff_id,
              p.person_id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,''))    AS name,
              coalesce(r.role_name,'')       AS role
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            LEFT JOIN rolee r ON r.role_id = s.role_id
            WHERE s.staff_id=%s
            LIMIT 1
        """, [staff_id])
        row = cur.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "Staff not found."}, status=404)

    _staff_id, person_id, name, role = row
    from lupon_mem.services.helpers import get_person_mobile_number
    mobile = get_person_mobile_number(person_id) or ""

    return JsonResponse({
        "ok": True,
        "result": {
            "id": _staff_id,
            "person_id": person_id,
            "name": (name or "").strip(),
            "role": (role or "").strip(),
            "mobile": mobile.strip()
        }
    })


@session_login_required
@role_required(*LUPON_ROLES)
@require_GET
def kp16_date_api(request: HttpRequest, case_id: int):
    """
    API endpoint to fetch KP-16 date for repudiation window.
    Returns: { ok: true, date: "October 29, 2025" } or { ok: false, error: "..." }
    """
    from lupon_mem.services.fields_util import get_this_case_kp16_date_filed
    
    try:
        date_str = get_this_case_kp16_date_filed(case_id)
        if date_str:
            return JsonResponse({"ok": True, "date": date_str})
        else:
            return JsonResponse({"ok": False, "error": "KP-16 date not found"})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@session_login_required
@role_required(*LUPON_ROLES)
@require_GET
def kp7_details_api(request: HttpRequest, case_id: int):
    """
    API endpoint to fetch KP-7 complaint details and solutions sought.
    Returns: { complaint_details: "...", solutions_seeked: "..." }
    """
    from lupon_mem.services.fields_util import get_latest_form_fields, get_field_text
    
    try:
        rows = get_latest_form_fields(case_id, 'KP-7')
        complaint_details = get_field_text(rows, 'complaint_details') or ''
        solutions_seeked = get_field_text(rows, 'solutions_seeked') or ''
        
        return JsonResponse({
            "complaint_details": complaint_details,
            "solutions_seeked": solutions_seeked
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@session_login_required
@role_required(*LUPON_ROLES)
@require_GET
def upcoming_hearings_api(request: HttpRequest, case_id: int):
    """
    API endpoint to check for upcoming hearings not yet held.
    Returns: { count: number_of_upcoming_hearings }
    """
    try:
        with connection.cursor() as cur:
            # Use fn_case_mediation_hearings function like the existing code
            cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = [dict(zip(cols, r)) for r in cur.fetchall()] if cols else []
            
            count = 0
            for row in rows:
                hearing_held = row.get('hearing_held', True)  # Default to True if missing
                
                # Count hearings that are not held yet
                if not hearing_held:
                    count += 1
        
        return JsonResponse({"count": count})
    except Exception as e:
        import logging
        logging.error(f"upcoming_hearings_api error: {e}")
        return JsonResponse({"error": str(e)}, status=500)



