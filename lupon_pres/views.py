# lupon_pres/views.py
from __future__ import annotations
from django.shortcuts import render
from authentication.guards import session_login_required, role_required

# Import all view functions from lupon_mem.views
from lupon_mem.views import (
    form_builder,
    add_form_choose_static,
    form_builder_by_code,
    generate_settlement_summary,
    hearing_list,
    case_hearing_list,
    case_hearing_schedule,
    open_kp16_from_hearing,
    open_med_attendance_from_hearing,
    open_mediation_attendance,
    hearing_media_upload,
    mediation_photos_upload,
    mediation_complete,
    conciliation_complete,
    case_summary_pdf,
    mark_hearing_held_dev,
    case_summon_list,
    summon_attendance,
    summon_set_status,
    case_timeline,
    incident_heatmap
)

@session_login_required
@role_required("barangay lupon president")
def dashboard(request):
    """Dashboard for Barangay Lupon President"""
    auth = request.session.get("auth")
    return render(request, "lupon_pres/dashboard.html", {
        "page_path": "Barangay Lupon President/Dashboard",
        "page_title": "Dashboard",
        "auth": auth,
    })


import os
os.environ.setdefault("HTTPX_DISABLE_HTTP2", "1")

import io
import logging
import base64
from io import BytesIO
from datetime import datetime, time as dtime, date
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.templatetags.static import static
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_http_methods

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

# Reuse secretary services for DB/RPCs
from secretary.models import Secretary

# Your forms
from .forms import (
    SearchPerson,
    ResidentProfileform,
    Schedule,
    StaffFilters,
    UpdateInfo,
    UpdateInfo,   # ← if this lives in lupon_pres.forms; otherwise import from secretary.forms
)

# Supabase upload helper you already use elsewhere
from common.supabase_client import supabase
from common.services.storage import upload_to_storage

# Flash helpers
from common.flash import flash_success, flash_warning, flash_db_error, flash_system_error
from django.db import DatabaseError, OperationalError, IntegrityError
from common.db_errors import _pg_err_tuple

logger = logging.getLogger(__name__)


ROLE_LUPON = 8
WZ_KEY = "lpres_nonres_wizard"

# App/role for guard
LUPON_PRES_ROLE = "Barangay Lupon President"
#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Barangay Lupon President'

LUPON_PRES_ROLE = "Barangay Lupon President"
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def staff_selection(request):
    return render(request, "members/staff_selection.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
    })


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_GET
def resident_suggest(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    try:
        rows = Secretary.search_resident(q) or []
        out: List[Dict[str, Any]] = []
        for r in rows[:8]:
            full_name = (r.get("person_name") or "").strip()
            code = r.get("person_code") or ""
            addr_parts = [
                (r.get("street") or "").strip(),
                (r.get("purok_sitio_name") or r.get("purok") or r.get("purok_sitio") or "").strip(),
                (r.get("barangay") or "").strip(),
                (r.get("city") or "").strip(),
            ]
            subtitle = ", ".join([p for p in addr_parts if p])
            out.append({
                "id": r.get("person_id"),
                "code": code,
                "title": full_name,
                "subtitle": subtitle,
            })
        return JsonResponse({"results": out})
    except Exception:
        logger.exception("resident_suggest failed")
        return JsonResponse({"results": [], "error": "Search failed"}, status=500)


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:

    pid = (request.POST.get("pid") or "").strip()
    # role_str = (request.POST.get("role") or "").strip()
    role_id = ROLE_LUPON

    proof_url = (request.POST.get("proof") or "").strip() or None
    proof_file = request.FILES.get("proof_file") if hasattr(request, "FILES") else None

    # Collect Lupon schedules (base + dynamic)
    schedules: List[Dict[str, Any]] = []

    def _push_sched(d_s, ts_s, te_s):
        if not d_s or not ts_s or not te_s:
            return
        if not str(d_s).isdigit():
            return
        d = int(d_s)
        ts = _parse_hhmm(ts_s)
        te = _parse_hhmm(te_s)
        if d < 1 or d > 7 or not ts or not te or not (te > ts):
            return
        schedules.append({"day": d, "time_start": ts_s, "time_end": te_s})

    _push_sched(request.POST.get("day"), request.POST.get("time_start"), request.POST.get("time_end"))
    for d, s, e in zip(
        request.POST.getlist("day[]"),
        request.POST.getlist("time_start[]"),
        request.POST.getlist("time_end[]"),
    ):
        _push_sched(d, s, e)

    # Staff id from session
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    # fallback demo

    # Handle POST
    if request.method == "POST" and pid:
        # basic completeness gate
        if not (pid or role_id or proof_file or proof_url or request.POST.get("day") or request.POST.getlist("day[]")):
            flash_warning(request, "Please select a resident and fill out the form before submitting.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not staff_id:
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not role_id:
            flash_warning(request, "Please choose a staff role.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # For Lupon role: require ≥1 schedule and 1 per day
        if role_id == ROLE_LUPON:
            if len(schedules) < 1:
                flash_warning(request, "Lupon Member must have at least one schedule.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)
            _days = [s["day"] for s in schedules]
            if len(_days) != len(set(_days)):
                flash_warning(request, "Duplicate day selections in schedule are not allowed.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not (proof_file or proof_url):
            flash_warning(request, "Please attach a proof of employment.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # Upload proof (optional)
        uploaded_proof_url = None
        # 1) Lookup resident basic for key
        try:
            rows_for_key = Secretary.get_resident_details(int(pid)) or []
            res_for_key = rows_for_key[0] if rows_for_key else {}
        except (DatabaseError, OperationalError, IntegrityError) as e:
            flash_db_error(request, e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "Resident details lookup failed.", exc=e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        def _personal_like(rd: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "last_name":  rd.get("last_name") or "",
                "first_name": rd.get("first_name") or "",
                "middle_name": rd.get("middle_name") or "",
                "birthdate":  rd.get("birthdate") or "",
                "mobile_num": rd.get("mobile_num") or "",
            }

        def _key_from_personal(personal: dict) -> str:
            """LFM + mmddyyyy + last8 mobile"""
            import re as _re
            last  = (personal.get("last_name")   or "").strip()
            first = (personal.get("first_name")  or "").strip()
            mid   = (personal.get("middle_name") or "").strip()
            initials = (last[:1] + first[:1] + mid[:1]).lower()
            b = personal.get("birthdate")
            b_dt: date | None = None
            if isinstance(b, date):
                b_dt = b
            elif isinstance(b, str) and b:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        b_dt = datetime.strptime(b, fmt).date()
                        break
                    except Exception:
                        pass
            b_str = b_dt.strftime("%m%d%Y") if b_dt else ""
            mobile_raw = (personal.get("mobile_num") or "").strip()
            mobile_digits = _re.sub(r"\D+", "", mobile_raw)
            last8 = mobile_digits[-8:] if mobile_digits else ""
            return f"{initials}{b_str}{last8}-staff-app"

        try:
            personal_like = _personal_like(res_for_key)
            final_base = f"staff_acc_req_proof/{_key_from_personal(personal_like)}"
        except Exception:
            final_base = f"staff_acc_req_proof/{pid}"

        BUCKET_FOR_PROOF = BUCKET_STAFF_PROOF

        if proof_file:
            try:
                buf, mime, ext = _prep_image_for_upload(proof_file)
                res_up = _upload_to_storage_retry(
                    buf,
                    path=f"{final_base}/staff-app-proof.{ext}",
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,
                )
                uploaded_proof_url = res_up.get("public_url") or res_up.get("signed_url")
            except (DatabaseError, OperationalError, IntegrityError) as e:
                flash_db_error(request, e)
                return redirect(request.META.get("HTTP_REFERER") or request.path)
            except Exception as e:
                flash_system_error(request, "Proof upload failed.", exc=e)
                return redirect(request.META.get("HTTP_REFERER") or request.path)
        elif proof_url:
            # Accept data-URL or external URL
            import re
            m = re.match(r"^data:(.+?);base64,(.+)$", proof_url)
            if m:
                _mime_hint, b64 = m.groups()
                raw = io.BytesIO(base64.b64decode(b64))
                buf, mime, ext = _prep_image_for_upload(raw)
                res_up = _upload_to_storage_retry(
                    buf,
                    path=f"{final_base}/staff-app-proof.{ext}",
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,
                )
                uploaded_proof_url = res_up.get("public_url") or res_up.get("signed_url")
            else:
                uploaded_proof_url = proof_url

        # Create staff account request (NO purok ids passed)
        try:
            result = Secretary.insert_res_staff_account_request(
                p_requested_by_id=staff_id,
                p_person_id=int(pid),
                p_role_id=role_id,
                p_supporting_docs=([uploaded_proof_url] if uploaded_proof_url else None),
                p_lupon_sched=(schedules if schedules else None),
                p_bhw_purok_ids=None,  # ← explicitly no purok assignment
            )
            _ = result.get("staff_acc_req_id")
            flash_success(request, "Staff account request created.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except (DatabaseError, OperationalError, IntegrityError) as e:
            logger.exception("DB ✗ insert_staff_account_request failed")
            flash_db_error(request, e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "System ✗ insert_staff_account_request failed.", exc=e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)

    # GET (and also POST fall-through -> render page with details)
    residents: List[Dict[str, Any]] = []
    res_details: Optional[Dict[str, Any]] = None
    doc_images: List[Dict[str, str]] = []

    res_search = (request.POST.get("residentSearch") or "").strip()
    res_id = (request.POST.get("person_id") or "").strip()

    try:
        if res_search:
            residents = Secretary.search_resident(res_search) or []
        if res_id:
            rows = Secretary.get_resident_details(int(res_id)) or []
            res_details = rows[0] if rows else None

        if res_details:
            def _val(d, *keys):
                for k in keys:
                    v = d.get(k)
                    if v:
                        return v
                return None

            front_val  = _val(res_details, "valid_id_front_files", "valid_id_front_url", "valid_id_front_path")
            back_val   = _val(res_details, "valid_id_back_files",  "valid_id_back_url",  "valid_id_back_path")
            selfie_val = _val(res_details, "selfie_with_id",       "selfie_url",         "selfie_with_id_path")

            PERSON_BUCKET = BUCKET_FINAL

            def _push(label: str, value: str | None):
                if not value:
                    return
                val = str(value).strip()
                if val.startswith("http://") or val.startswith("https://"):
                    doc_images.append({"label": label, "src": val, "alt": label})
                    return
                signed = _make_signed_url(PERSON_BUCKET, val, expire_seconds=1800)
                if signed:
                    doc_images.append({"label": label, "src": signed, "alt": label})

            _push("Front of ID", front_val)
            _push("Back of ID",  back_val)
            _push("Selfie w/ ID", selfie_val)

    except (DatabaseError, OperationalError, IntegrityError) as e:
        flash_db_error(request, e)
    except Exception as e:
        flash_system_error(request, "Error loading resident details.", exc=e)

    role_form = UpdateInfo()
    sched_form = Schedule()
    proof_form = ResidentProfileform()
    return render(request, "members/staff_selection_resident.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "residents": residents,
        "res_details": res_details,
        "staff_id": staff_id,
        "role_form": role_form,
        "sched_form": sched_form,
        "proof_form": proof_form,
        "doc_images": doc_images,
        "placeholder_img": static("images/brgy-sto-nino.png"),
    })



@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform(request.POST or None)
    # Make file/id fields optional in step 1
    for f in (
        "res_code", "username", "temp_pass", "res_status", "reg_method",
        "reg_date", "acc_status", "added_by", "home_address",
        "type_of_id", "front_id", "back_id", "res_img", "proof",
    ):
        if f in form.fields:
            form.fields[f].required = False

    if request.method == "POST":
        if form.is_valid():
            cd = form.cleaned_data
            def _label(field, val):
                return _label_from_choices(form.fields[field].choices, val)
            _wiz_set(request, "personal", {
                "first_name":  cd.get("first_name") or "",
                "last_name":   cd.get("last_name") or "",
                "middle_name": cd.get("middle_name") or "",
                "suffix":      (cd.get("suffix") or "").strip() or None,
                "birthdate":   (cd.get("dob").isoformat() if cd.get("dob") else None),
                "email":       cd.get("email") or "",
                "mobile_num":  cd.get("mob_num") or "",
                "sex_id":          int(cd["sex"]) if str(cd.get("sex") or "").isdigit() else None,
                "civil_status_id": int(cd["civil_status"]) if str(cd["civil_status"]).isdigit() else None,
                "nationality_id":  int(cd["nationality"]) if str(cd["nationality"]).isdigit() else None,
                "religion_id":     int(cd["religion"]) if str(cd["religion"]).isdigit() else None,
                "sex_label":          _label("sex", cd.get("sex")),
                "civil_status_label": _label("civil_status", cd.get("civil_status")),
                "nationality_label":  _label("nationality", cd.get("nationality")),
                "religion_label":     _label("religion", cd.get("religion")),
                "city":      cd.get("city") or "",
                "barangay":  cd.get("barangay") or "",
                "sitio_purok": cd.get("purok_sitio") or "",
                "street":    cd.get("street") or "",
            })
            flash_success(request, "Personal information saved successfully.")
            return redirect("lupon_pres:staff_selection_non-resident_docs")
        else:
            flash_warning(request, "Please correct the errors below.")

    return render(request, "members/staff_selection_nonresident.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "form": form,
        "redirect": "lupon_pres:staff_selection_non-resident_docs",
    })


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres_docs(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform(request.POST or None, request.FILES or None)
    for f in ("last_name","first_name","middle_name","suffix","sex","dob",
              "civil_status","nationality","religion","email","mob_num",
              "street","purok_sitio","barangay","city"):
        if f in form.fields:
            form.fields[f].required = False

    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}

    if request.method == "GET":
        if not personal:
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("lupon_pres:staff_selection_non-resident")

    if request.method == "POST":
        valid_id_type_raw = (request.POST.get("type_of_id") or "").strip()
        valid_id_type_id = int(valid_id_type_raw) if valid_id_type_raw.isdigit() else None
        valid_id_type_label = _label_from_choices(ResidentProfileform().fields["type_of_id"].choices, valid_id_type_raw)

        if not valid_id_type_id:
            flash_warning(request, "Please choose the Valid ID Type.")
            return redirect(request.path)

        # files
        front_in  = request.FILES.get("front_id")
        back_in   = request.FILES.get("back_id")
        selfie_in = request.FILES.get("res_img")
        proof_in  = request.FILES.get("proof")

        if not (front_in and back_in and selfie_in):
            flash_warning(request, "Front ID, Back ID, and Selfie with ID are required.")
            return redirect(request.path)

        if _same_file(front_in, back_in):
            flash_warning(request, "Front and Back photos appear to be the same file.")
            return redirect(request.path)

        # autorotate/compress for preview only
        try:
            front_buf  = _pil_autorotate_and_jpeg(front_in)
            back_buf   = _pil_autorotate_and_jpeg(back_in)
            selfie_buf = _pil_autorotate_and_jpeg(selfie_in)
            proof_buf  = _pil_autorotate_and_jpeg(proof_in) if proof_in else None
        except Exception:
            try: front_in.seek(0); back_in.seek(0); selfie_in.seek(0)
            except Exception: pass
            if proof_in:
                try: proof_in.seek(0)
                except Exception: pass
            front_buf, back_buf, selfie_buf, proof_buf = front_in, back_in, selfie_in, proof_in

        # store base64 previews in session
        def _readall(fobj):
            try: fobj.seek(0)
            except Exception: pass
            return fobj.read()

        b_front  = _readall(front_buf)
        b_back   = _readall(back_buf)
        b_selfie = _readall(selfie_buf)
        b_proof  = _readall(proof_buf) if proof_buf is not None else None

        docs_payload = {
            "valid_id_type_id": valid_id_type_id,
            "valid_id_type_label": valid_id_type_label,
            "front_preview": _bytes_to_data_url(b_front,  "image/jpeg"),
            "back_preview":  _bytes_to_data_url(b_back,   "image/jpeg"),
            "selfie_preview":_bytes_to_data_url(b_selfie, "image/jpeg"),
            "proof_preview": _bytes_to_data_url(b_proof,  "image/jpeg") if b_proof is not None else None,
            "front_b64": base64.b64encode(b_front).decode("ascii"),
            "back_b64": base64.b64encode(b_back).decode("ascii"),
            "selfie_b64": base64.b64encode(b_selfie).decode("ascii"),
            "proof_b64": base64.b64encode(b_proof).decode("ascii") if b_proof is not None else None,
        }
        _wiz_set(request, "docs", docs_payload)

        flash_success(request, "Documents loaded for preview. Please review and choose role.")
        return redirect("lupon_pres:staff_selection_non-resident_role_review")

    return render(request, "members/supporting_docs.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "form": form,
    })


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres_role_review(request: HttpRequest) -> HttpResponse:
    role_form = UpdateInfo(request.POST or None)
    sched_form = Schedule(request.POST or None)

    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}
    docs = wiz.get("docs") or {}

    if request.method == "GET":
        if not personal:
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("lupon_pres:staff_selection_non-resident")
        if not docs:
            flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
            return redirect("lupon_pres:staff_selection_non-resident_docs")

        return render(request, "members/schedule.html", {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Account Verification",
            "page_title": "Account Verification",
            "user_role_template": user_role_template,
            "role_form": role_form,
            "sched_form": sched_form,
            "personal": personal,
            "docs": docs,
        })


    role_id = ROLE_LUPON

    schedules: List[Dict[str, Any]] = []

    def _push(d_s, ts_s, te_s):
        if not d_s or not ts_s or not te_s:
            return
        if not str(d_s).isdigit():
            return
        d = int(d_s)
        ts = _parse_hhmm(ts_s)
        te = _parse_hhmm(te_s)
        if d < 1 or d > 7 or not ts or not te or not (te > ts):
            return
        schedules.append({"day": d, "time_start": ts_s, "time_end": te_s})

    _push(request.POST.get("day"), request.POST.get("time_start"), request.POST.get("time_end"))
    for d, s, e in zip(
        request.POST.getlist("day[]"),
        request.POST.getlist("time_start[]"),
        request.POST.getlist("time_end[]"),
    ):
        _push(d, s, e)

    if not role_id:
        flash_warning(request, "Please choose a staff role.")
        return redirect(request.path)

    # If Lupon role, require ≥1 schedule & unique days
    if role_id == ROLE_LUPON:
        if len(schedules) < 1:
            flash_warning(request, "Lupon Member must have at least one schedule.")
            return redirect(request.path)
        _days = [s["day"] for s in schedules]
        if len(_days) != len(set(_days)):
            flash_warning(request, "Duplicate day selections in schedule are not allowed.")
            return redirect(request.path)

    if not personal:
        flash_warning(request, "Personal information is missing. Please go back to Step 1.")
        return redirect("lupon_pres:staff_selection_non-resident")

    if not docs:
        flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
        return redirect("lupon_pres:staff_selection_non-resident_docs")

    # session staff id
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    
    if not staff_id:
        flash_warning(request, "Your session is missing staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or request.path)

    # Decode base64 & upload final images
    front_b64 = docs.get("front_b64")
    back_b64  = docs.get("back_b64")
    selfie_b64= docs.get("selfie_b64")
    proof_b64 = docs.get("proof_b64")
    valid_id_type_id = docs.get("valid_id_type_id")

    if not (front_b64 and back_b64 and selfie_b64):
        flash_warning(request, "Supporting documents are incomplete. Please re-upload.")
        return redirect("lupon_pres:staff_selection_non-resident_docs")

    def _key_from_personal(personal: dict) -> str:
        import re as _re
        last  = (personal.get("last_name")   or "").strip()
        first = (personal.get("first_name")  or "").strip()
        mid   = (personal.get("middle_name") or "").strip()
        initials = (last[:1] + first[:1] + mid[:1]).lower()
        b = personal.get("birthdate")
        b_dt: date | None = None
        if isinstance(b, date):
            b_dt = b
        elif isinstance(b, str) and b:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    b_dt = datetime.strptime(b, fmt).date()
                    break
                except Exception:
                    pass
        b_str = b_dt.strftime("%m%d%Y") if b_dt else ""
        mobile_raw = (personal.get("mobile_num") or "").strip()
        mobile_digits = _re.sub(r"\D+", "", mobile_raw)
        last8 = mobile_digits[-8:] if mobile_digits else ""
        return f"{initials}{b_str}{last8}-staff-app"

    final_base = f"person/{_key_from_personal(personal)}"
    proof_final_base = f"staff_acc_req_proof/{_key_from_personal(personal)}"

    try:
        b_front  = base64.b64decode(front_b64)
        b_back   = base64.b64decode(back_b64)
        b_selfie = base64.b64decode(selfie_b64)
        b_proof  = base64.b64decode(proof_b64) if proof_b64 else None
    except Exception as e:
        flash_system_error(request, "Images could not be decoded from session.", exc=e)
        return redirect("lupon_pres:staff_selection_non-resident_docs")

    try:
        f_buf, f_mime, f_ext = _prep_image_for_upload(io.BytesIO(b_front))
        b_buf, b_mime, b_ext = _prep_image_for_upload(io.BytesIO(b_back))
        s_buf, s_mime, s_ext = _prep_image_for_upload(io.BytesIO(b_selfie))

        up_front = _upload_to_storage_retry(
            f_buf, path=f"{final_base}/front.{f_ext}", bucket=BUCKET_FINAL, content_type=f_mime, make_public=True
        )
        up_back = _upload_to_storage_retry(
            b_buf, path=f"{final_base}/back.{b_ext}", bucket=BUCKET_FINAL, content_type=b_mime, make_public=True
        )
        up_selfie = _upload_to_storage_retry(
            s_buf, path=f"{final_base}/selfie.{s_ext}", bucket=BUCKET_FINAL, content_type=s_mime, make_public=True
        )

        up_proof = None
        if b_proof is not None:
            p_buf, p_mime, p_ext = _prep_image_for_upload(io.BytesIO(b_proof))
            up_proof = _upload_to_storage_retry(
                p_buf,
                path=f"{proof_final_base}/staff-app-proof.{p_ext}",
                bucket=BUCKET_STAFF_PROOF,
                content_type=p_mime,
                make_public=True,
            )
    except Exception as e:
        flash_system_error(request, "Final upload failed.", exc=e)
        return redirect(request.path)

    front_url = up_front.get("public_url") or up_front.get("signed_url")
    back_url  = up_back.get("public_url") or up_back.get("signed_url")
    self_url  = up_selfie.get("public_url") or up_selfie.get("signed_url")
    proof_url = up_proof.get("public_url") or up_proof.get("signed_url") if up_proof else None

    # Insert non-resident staff account request (NO purok)
    try:
        _req_id = Secretary.insert_nonres_staff_account_request(
            p_requested_by_id=staff_id,
            p_person_id=None,
            p_role_id=role_id,
            p_supporting_docs=([proof_url] if proof_url else None),
            p_lupon_sched=schedules if schedules else None,
            p_bhw_purok_ids=None,  # ← ensure none
            p_first_name=personal.get("first_name"),
            p_last_name=personal.get("last_name"),
            p_middle_name=(personal.get("middle_name") or "").strip() or None,
            p_suffix=(personal.get("suffix") or "").strip() or None,
            p_birthdate=personal.get("birthdate"),
            p_email=personal.get("email"),
            p_mobile_num=personal.get("mobile_num"),
            p_sex_id=personal.get("sex_id"),
            p_civil_status_id=personal.get("civil_status_id"),
            p_nationality_id=personal.get("nationality_id"),
            p_religion_id=personal.get("religion_id"),
            p_city=personal.get("city"),
            p_barangay=personal.get("barangay"),
            p_sitio_purok=personal.get("sitio_purok"),
            p_street=personal.get("street"),
            p_valid_id_front=front_url,
            p_valid_id_back=back_url,
            p_valid_id_type_id=valid_id_type_id,
            p_selfie_path=self_url,
        )
    except (DatabaseError, OperationalError, IntegrityError) as e:
        pgcode, _primary = _pg_err_tuple(e)
        if pgcode == "P5007":
            # Example special-case
            flash_warning(request, "This person is already registered. Please use the Resident flow.")
            return redirect("lupon_pres:staff_selection_resident")
        flash_db_error(request, e)
        return redirect(request.path)
    except Exception as e:
        flash_system_error(request, "Failed to create staff account request.", exc=e)
        return redirect(request.path)

    # Clean heavy previews
    try:
        if "docs" in wiz:
            for k in ("front_b64","back_b64","selfie_b64","proof_b64","front_preview","back_preview","selfie_preview","proof_preview"):
                wiz["docs"].pop(k, None)
            _wiz_set(request, "docs", wiz["docs"])
    except Exception:
        pass

    flash_success(request, "Staff account request created.")
    _wiz_clear(request)
    return redirect("lupon_pres:staff_selection")


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
def members_list(request: HttpRequest) -> HttpResponse:
    try:
        all_rows = Secretary.get_all_staff_info_summary() or []
        # Keep only Lupon Members
        rows = [
            r for r in all_rows
            if str(r.get("role_id")) == "8"
            or (str(r.get("role_name") or "").strip().upper() == "BARANGAY LUPON MEMBER")
        ]
    except Exception as e:
        logger.exception("Failed to load staff summaries: %s", e)
        rows = []

    from django.core.paginator import Paginator
    try:
        per_page = int(request.GET.get("per_page") or 10)
        if per_page <= 0:
            per_page = 10
    except ValueError:
        per_page = 10

    try:
        page_number = int(request.GET.get("page") or 1)
    except ValueError:
        page_number = 1

    form = StaffFilters()
    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(page_number)

    auth = request.session.get("auth") or {}
    _user_fullname = auth.get("full_name") or user_fullname
    _user_role = auth.get("role_name") or user_role
    _user_role_template = (_user_role or "").lower().replace(" ", "_")

    return render(request, "members/members_list.html", {
        "user_fullname": _user_fullname,
        "user_role": _user_role,
        "page_path": f"{_user_role} / Staff List",
        "page_title": "Staff List",
        "user_role_template": _user_role_template,
        "form": form,
        "page_obj": page_obj,
        "total_count": paginator.count,
        "per_page": per_page,
    })



@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_GET
def staff_search_api(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    try:
        if q:
            results = Secretary.search_staff_by_name(q)[:50]
        else:
            results = Secretary.get_all_staff_info_summary()
        return JsonResponse({"results": results})
    except Exception as e:
        logger.exception("staff_search_api error: %s", e)
        return JsonResponse({"results": [], "error": "Search failed"}, status=500)


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@require_GET
def staff_filter_api(request: HttpRequest):
    # role_raw = (request.GET.get("role_id") or "").strip()
    day_raw  = (request.GET.get("day_id") or "").strip()
    acc_raw  = (request.GET.get("account_status_id") or "").strip()
    # role_id = int(role_raw) if role_raw.isdigit() else None
    day_id  = int(day_raw)  if day_raw.isdigit()  else None
    acc_id  = int(acc_raw)  if acc_raw.isdigit()  else None
    try:
        if day_id is None and acc_id is None:
            rows = Secretary.get_all_staff_info_summary()
        else:
            rows = Secretary.filter_staff_by_sched_day_and_account(day_id, acc_id)
        return JsonResponse({"results": rows})
    except Exception as e:
        logger.exception("staff_filter_api error: %s", e)
        return JsonResponse({"results": [], "error": "Filter failed"}, status=500)


@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
def member_dets(request: HttpRequest, staff_code: str) -> HttpResponse:

    try:
        rows = Secretary.get_staff_profile_display(staff_code) if staff_code else []
    except Exception:
        logger.exception("get_staff_profile_display failed for staff_code=%s", staff_code)
        rows = []

    p = rows[0] if rows else None
    placeholder = static("images/brgy-sto-nino.png")
    def _img(v): return (v or "").strip() or placeholder

    doc_slides = []
    if p:
        doc_slides = [
            {"src": _img(p.get("valid_id_front_img_path")), "label": "Front of ID"},
            {"src": _img(p.get("valid_id_back_img_path")),  "label": "Back of ID"},
            {"src": _img(p.get("selfie_img_path")),         "label": "Selfie w/ ID"},
        ]

    ctx = {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Details : {staff_code}",
        "page_title": f"Staff Details : {staff_code}",
        "user_role_template": user_role_template,
        "profile": p,
        "doc_slides": doc_slides,
    }

    form = UpdateInfo()
    return render(request, "members/member_dets.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Details : {staff_code}",
        "page_title": f"Staff Details : {staff_code}",
        "user_role_template": user_role_template,
        "form": form,
        "profile": p,
        "doc_slides": doc_slides,
    })
