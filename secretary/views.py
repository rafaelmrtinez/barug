# secretary/views.py
from __future__ import annotations
from django.templatetags.static import static

import os
os.environ.setdefault("HTTPX_DISABLE_HTTP2", "1")

import io
import logging
from uuid import uuid4
from datetime import datetime, time as dtime, date
import logging
log = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional
, Optional
from django.urls import reverse

from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.csrf import csrf_protect
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.business_service_contract import (
    IBusinessService,
    IBusinessInfoService,
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository
)
from src.app.contracts.household_service_contract import (
    IHouseholdService,
)
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository,
)

from .forms import (
    StaffFilters,
    BusinessFilters,
    HouseholdFilters
)


from common.supabase_client import supabase
from common.services.storage import upload_to_storage

from secretary.models import Secretary
from .forms import ResidentProfileform, ChooseRole, StaffFilters, Schedule

from common.flash import flash_success, flash_warning, flash_db_error, flash_system_error
from django.db import DatabaseError, OperationalError, IntegrityError
from common.db_errors import _pg_err_tuple

# NEW
from .services.residents import (
    list_residents_minimal,
    get_resident_full_profile,
    build_fullname,
    build_address_line,
)

# ─────────────────────────────
# Constants (mirror clerk style)
# ─────────────────────────────

logger = logging.getLogger(__name__)

ROLE_BHW = 9
ROLE_LUPON = 8
WZ_KEY = "staff_nonres_wizard"

SECRETARY_ROLE = "Barangay Secretary"

# Demo identity (kept as-is)
user_fullname = "lname, fname mname suffix"
user_role = "Barangay Secretary"
user_role_template = user_role.lower().replace(" ", "_")

BUCKET_FINAL = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
BUCKET_STAFF_PROOF = getattr(settings, "SUPABASE_STAFF_PROOF_BUCKET", "staff-proof")

# ─────────────────────────────
# Helpers
# ─────────────────────────────

from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.shortcuts import redirect

def _smart_redirect(request, url_name, *args, **kwargs):
    url = reverse(url_name, args=args, kwargs=kwargs)

    # HTMX: ask the client to redirect
    if request.headers.get("HX-Request") == "true":
        return HttpResponse(status=204, headers={"HX-Redirect": url})

    # AJAX/fetch: return JSON the client can act on
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"redirect": url, "ok": True})

    # Normal form POST: classic 302 works
    return redirect(url)

def _wiz_get(request) -> Dict[str, Any]:
    return request.session.get(WZ_KEY, {}) or {}

def _wiz_set(request, key: str, value: Any) -> None:
    data = _wiz_get(request)
    data[key] = value
    request.session[WZ_KEY] = data
    request.session.modified = True

def _wiz_clear(request) -> None:
    if WZ_KEY in request.session:
        del request.session[WZ_KEY]
        request.session.modified = True

def _parse_hhmm(s: Optional[str]) -> Optional[dtime]:
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%H:%M").time()
    except Exception:
        return None

def _ct_from_name(name: str) -> str:
    n = (name or "").lower()
    if n.endswith(".png"):
        return "image/png"
    return "image/jpeg"

def _label_from_choices(choices, value):
    s = str(value) if value is not None else ""
    for k, v in choices:
        if str(k) == s:
            return v
    return None

def _make_signed_url(bucket: str, path: str, expire_seconds: int = 1800) -> str | None:
    if not path:
        return None
    try:
        res = supabase.storage.from_(bucket).create_signed_url(path, expire_seconds)
        return (res.get("signedURL") or res.get("signed_url")) if isinstance(res, dict) else None
    except Exception:
        return None

def _same_file(a, b) -> bool:
    if not a or not b:
        return False
    try:
        return (getattr(a, "size", None) == getattr(b, "size", None)) and (
            getattr(a, "name", "") == getattr(b, "name", "")
        )
    except Exception:
        return False

# --- image utilities: auto-rotate + compress to JPEG ---
from io import BytesIO

def _pil_autorotate_and_jpeg(file_obj, *, max_w=2200, max_h=2200, quality=85) -> BytesIO:
    try:
        from PIL import Image, ImageOps
        file_obj.seek(0)
        img = Image.open(file_obj)
        img = ImageOps.exif_transpose(img)  # autorotate
        img.thumbnail((max_w, max_h))       # bound size
        buf = BytesIO()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)
        return buf
    except Exception:
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return file_obj  # fallback

# utils
def _prep_image_for_upload(file_obj, *, max_w=2200, max_h=2200, default_bg="white"):

    try:
        from PIL import Image, ImageOps
        file_obj.seek(0)
        img = Image.open(file_obj)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_w, max_h))

        has_alpha = (img.mode in ("RGBA", "LA")) or ("transparency" in img.info)

        if has_alpha:
            if img.mode not in ("RGBA", "LA"):
                img = img.convert("RGBA")
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            buf.seek(0)
            return buf, "image/png", "png"
        else:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            buf.seek(0)
            return buf, "image/jpeg", "jpg"
    except Exception:
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return file_obj, getattr(file_obj, "content_type", "application/octet-stream"), "jpg"

# NEW: data-url helpers for preview-only flow (no bucket writes in Step 2)
import base64

def _bytes_to_data_url(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(b).decode('ascii')}"

def _file_to_data_url(fileobj, fallback_mime="image/jpeg") -> str:
    mime = getattr(fileobj, "content_type", None) or fallback_mime
    try:
        fileobj.seek(0)
    except Exception:
        pass
    data = fileobj.read()
    return _bytes_to_data_url(data, mime=mime)
def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

def _to_int_or_none(val) -> Optional[int]:
    try:
        if val in (None, "", "None"):
            return None
        return int(val)
    except Exception:
        return None
    
def dashboard(request):
    return render(request, "secretary_dashboard.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'user_role_template' : user_role_template,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_selection(request: HttpRequest) -> HttpResponse:
    return render(request, "staff/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
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
    except Exception as e:
        # For AJAX we still return JSON; logging kept
        logger.exception("resident_suggest failed")
        return JsonResponse({"results": [], "error": "Oops! Our system is having an issue for now. Please try again later."}, status=500)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:
    pid = (request.POST.get("pid") or "").strip()
    role_str = (request.POST.get("role") or "").strip()
    role_id = int(role_str) if role_str.isdigit() else None

    proof_url = (request.POST.get("proof") or "").strip() or None
    proof_file = request.FILES.get("proof_file") if hasattr(request, "FILES") else None

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    # --- Collect BHW puroks: base + extra rows
    purok_ids: List[int] = []
    base_purok = (request.POST.get("purok_sitio") or "").strip()
    if base_purok.isdigit():
        purok_ids.append(int(base_purok))
    for x in request.POST.getlist("purok_sitio_ids[]"):
        x = (x or "").strip()
        if x.isdigit():
            purok_ids.append(int(x))
    purok_ids = sorted(set(purok_ids))

    # --- Collect Lupon schedules
    schedules: List[Dict[str, Any]] = []

    def _push_sched(d_s, ts_s, te_s):
        if not d_s or not ts_s or not te_s: return
        if not str(d_s).isdigit(): return
        d = int(d_s)
        ts = _parse_hhmm(ts_s); te = _parse_hhmm(te_s)
        if d < 1 or d > 7 or not ts or not te or not (te > ts): return
        schedules.append({"day": d, "time_start": ts_s, "time_end": te_s})

    _push_sched(request.POST.get("day"), request.POST.get("time_start"), request.POST.get("time_end"))
    for d, s, e in zip(request.POST.getlist("day[]"),
                       request.POST.getlist("time_start[]"),
                       request.POST.getlist("time_end[]")):
        _push_sched(d, s, e)

    if request.method == "POST":
        logger.debug("POST ▶ pid=%s role_id=%s staff_id=%s purok_ids=%s schedules=%s proof_url=%s file=%s",
                     pid, role_id, staff_id, purok_ids, schedules, bool(proof_url), bool(proof_file))

    if request.method == "POST" and pid:
        if not (pid or role_id or proof_file or proof_url or base_purok
                or request.POST.getlist("purok_sitio_ids[]")
                or request.POST.get("day") or request.POST.getlist("day[]")):
            flash_warning(request, "Please select a resident and fill out the form before submitting.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not staff_id:
            logger.error("Validation ✗ Missing staff_id")
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not role_id:
            logger.error("Validation ✗ No role selected")
            flash_warning(request, "Please choose a staff role.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_BHW and len(purok_ids) < 1:
            logger.error("Validation ✗ BHW requires ≥1 purok")
            flash_warning(request, "BHW must be assigned to at least one Purok/Sitio.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_LUPON and len(schedules) < 1:
            logger.error("Validation ✗ Lupon requires ≥1 schedule")
            flash_warning(request, "Lupon Member must have at least one schedule.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_BHW:
            _raw_purok_ids: List[int] = []
            if base_purok.isdigit():
                _raw_purok_ids.append(int(base_purok))
            for x in request.POST.getlist("purok_sitio_ids[]"):
                x = (x or "").strip()
                if x.isdigit():
                    _raw_purok_ids.append(int(x))
            if len(_raw_purok_ids) != len(set(_raw_purok_ids)):
                logger.error("Validation ✗ Duplicate Purok/Sitio selections are not allowed: %s", _raw_purok_ids)
                flash_warning(request, "Duplicate Purok/Sitio selections are not allowed.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_LUPON and schedules:
            _days = [s["day"] for s in schedules]
            if len(_days) != len(set(_days)):
                logger.error("Validation ✗ Duplicate day selections in schedule are not allowed: %s", _days)
                flash_warning(request, "Duplicate day selections in schedule are not allowed.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not (proof_file or proof_url):
            flash_warning(request, "Please attach a proof of employment.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        BUCKET_FOR_PROOF = BUCKET_STAFF_PROOF

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

        try:
            personal_like = _personal_like(res_for_key)
            final_base = f"staff_acc_req_proof/{_key_from_personal(personal_like)}"
        except Exception:
            final_base = f"staff_acc_req_proof/{pid}"

        uploaded_proof_url = None
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
            import re, base64
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

        try:
            result = Secretary.insert_res_staff_account_request(
                p_requested_by_id=staff_id,
                p_person_id=int(pid),
                p_role_id=role_id,
                p_supporting_docs=([uploaded_proof_url] if uploaded_proof_url else None),
                p_lupon_sched=(schedules if schedules else None),
                p_bhw_purok_ids=(purok_ids if purok_ids else None),
            )
            staff_req_id = result["staff_acc_req_id"]
            flash_success(request, "Staff account request created.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        except (DatabaseError, OperationalError, IntegrityError) as e:
            logger.exception("DB ✗ insert_staff_account_request failed")
            flash_db_error(request, e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "System ✗ insert_staff_account_request failed.", exc=e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)

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

            logger.debug("doc_images_count=%s keys=%s", len(doc_images), list(res_details.keys()))

    except (DatabaseError, OperationalError, IntegrityError) as e:
        flash_db_error(request, e)
    except Exception as e:
        flash_system_error(request, "Error loading resident details.", exc=e)

    role_form = ChooseRole()
    sched_form = Schedule()
    proof_form = ResidentProfileform()
    return render(request, "staff/staff_selection_resident.html", {
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

    

# === Non-resident flow helpers ===
import re
from datetime import datetime as _dt

def _key_from_personal(personal: dict) -> str:

    last  = (personal.get("last_name")   or "").strip()
    first = (personal.get("first_name")  or "").strip()
    mid   = (personal.get("middle_name") or "").strip()

    initials = (last[:1] + first[:1] + mid[:1]).lower()

    # birthdate → mmddyyyy
    b = personal.get("birthdate")
    b_dt: date | None = None
    if isinstance(b, date):
        b_dt = b
    elif isinstance(b, str) and b:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                b_dt = _dt.strptime(b, fmt).date()
                break
            except Exception:
                pass
    b_str = b_dt.strftime("%m%d%Y") if b_dt else ""

    # mobile → keep digits only, take last 8
    mobile_raw = (personal.get("mobile_num") or "").strip()
    mobile_digits = re.sub(r"\D+", "", mobile_raw)
    last8 = mobile_digits[-8:] if mobile_digits else ""

    return f"{initials}{b_str}{last8}-staff-app"

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform(request.POST or None)
    for f in ("type_of_id", "front_id", "back_id", "res_img", "proof"):
        if f in form.fields:
            form.fields[f].required = False

    if request.method == "POST":
        if form.is_valid():
            cd = form.cleaned_data
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
                "sex_label":          _label_from_choices(form.fields["sex"].choices, cd.get("sex")),
                "civil_status_label": _label_from_choices(form.fields["civil_status"].choices, cd.get("civil_status")),
                "nationality_label":  _label_from_choices(form.fields["nationality"].choices, cd.get("nationality")),
                "religion_label":     _label_from_choices(form.fields["religion"].choices, cd.get("religion")),
                "city":      cd.get("city") or "",
                "barangay":  cd.get("barangay") or "",
                "sitio_purok": cd.get("purok_sitio") or "",
                "street":    cd.get("street") or "",
            })
            flash_success(request, "Personal information saved successfully.")
            logger.info("Step1 ✓ personal info saved to wizard")
            return redirect("secretary:staff_selection_non-resident_docs")
        else:
            # Keep same logic: show validation message; do not expose internals
            logger.error("Validation ✗ Form errors: %s", form.errors.as_json())
            flash_warning(request, "Please correct the errors below.")
            # fall-through to re-render with form errors

    return render(request, "staff/staff_selection_nonresident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form': form,
        'redirect': 'secretary:staff_selection_non-resident_docs',
    })

@session_login_required
@role_required(SECRETARY_ROLE)
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
            logger.error("Wizard ✗ Missing personal info in session")
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("secretary:staff_selection_non-resident")

    if request.method == "POST":
        valid_id_type_raw = (request.POST.get("type_of_id") or "").strip()
        valid_id_type_id = int(valid_id_type_raw) if valid_id_type_raw.isdigit() else None
        valid_id_type_label = _label_from_choices(ResidentProfileform().fields["type_of_id"].choices, valid_id_type_raw)

        if not valid_id_type_id:
            flash_warning(request, "Please choose the Valid ID Type.")
            return redirect(request.path)

        # 1) Gather files
        front_in  = request.FILES.get("front_id")
        back_in   = request.FILES.get("back_id")
        selfie_in = request.FILES.get("res_img")
        proof_in  = request.FILES.get("proof")

        if not (front_in and back_in and selfie_in):
            flash_warning(request, "Front ID, Back ID, and Selfie with ID are required.")
            logger.error("Step2 ✗ Missing files: front=%s back=%s selfie=%s", bool(front_in), bool(back_in), bool(selfie_in))
            return redirect(request.path)

        if _same_file(front_in, back_in):
            flash_warning(request, "Front and Back photos appear to be the same file. Please upload the actual back side of the ID.")
            logger.error("Step2 ✗ Front and Back are identical (name/size).")
            return redirect(request.path)

        # 2) Preprocess (autorotate/compress to JPEG)
        try:
            front_buf  = _pil_autorotate_and_jpeg(front_in)
            back_buf   = _pil_autorotate_and_jpeg(back_in)
            selfie_buf = _pil_autorotate_and_jpeg(selfie_in)
            proof_buf  = _pil_autorotate_and_jpeg(proof_in) if proof_in else None
        except Exception as e:
            logger.warning("Step2 ⚠ image preprocess failed; using originals: %s", e)
            try: front_in.seek(0); back_in.seek(0); selfie_in.seek(0)
            except Exception: pass
            if proof_in:
                try: proof_in.seek(0)
                except Exception: pass
            front_buf, back_buf, selfie_buf, proof_buf = front_in, back_in, selfie_in, proof_in

        # 3) Build previews + store base64 (no uploads here)
        try:
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
                # previews
                "front_preview": _bytes_to_data_url(b_front,  "image/jpeg"),
                "back_preview":  _bytes_to_data_url(b_back,   "image/jpeg"),
                "selfie_preview":_bytes_to_data_url(b_selfie, "image/jpeg"),
                "proof_preview": _bytes_to_data_url(b_proof,  "image/jpeg") if b_proof is not None else None,
                # raw b64
                "front_b64": base64.b64encode(b_front).decode("ascii"),
                "back_b64": base64.b64encode(b_back).decode("ascii"),
                "selfie_b64": base64.b64encode(b_selfie).decode("ascii"),
                "proof_b64": base64.b64encode(b_proof).decode("ascii") if b_proof is not None else None,
            }
            _wiz_set(request, "docs", docs_payload)
        except Exception as e:
            logger.error("Step2 ✗ Preview preparation failed: %s", e)
            flash_system_error(request, "Could not prepare previews.", exc=e)
            return redirect(request.path)

        flash_success(request, "Documents loaded for preview. Please review and choose role.")
        logger.info("Step2 ✓ Preview-only complete (no uploads).")
        return redirect("secretary:staff_selection_non-resident_role_review")

    # GET
    return render(request, "staff/supporting_docs.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "form": form,
    })

import time as _time

def _upload_to_storage_retry(
    data,
    *,
    path: str,
    bucket: str,
    content_type: str = "application/octet-stream",
    make_public: bool = False,
    upsert: bool = True,
    reset_metadata: bool = True,
    max_retries: int = 3,
    base_sleep: float = 0.6,
):
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return upload_to_storage(
                data,
                path=path,
                bucket=bucket,
                upsert=upsert,
                make_public=make_public,
                reset_metadata=reset_metadata,
                content_type=content_type,
            )
        except Exception as e:
            msg = str(e)
            transient = (
                "ReadError" in msg or
                "TransportError" in msg or
                "A non-blocking socket operation could not be completed immediately" in msg or
                "WinError 10035" in msg
            )
            if attempt < max_retries and transient:
                sleep_s = base_sleep * (2 ** attempt)
                logger.warning("Upload transient error (%s). Retrying in %.2fs [%d/%d]…", msg, sleep_s, attempt + 1, max_retries)
                _time.sleep(sleep_s)
                continue
            last_err = e
            break
    raise last_err

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres_role_review(request: HttpRequest) -> HttpResponse:

    role_form = ChooseRole(request.POST or None)
    sched_form = Schedule(request.POST or None)

    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}
    docs = wiz.get("docs") or {}

    if request.method == "GET":
        if not personal:
            logger.error("Wizard ✗ Missing personal info in session")
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("secretary:staff_selection_non-resident")
        if not docs:
            logger.error("Wizard ✗ Missing docs info in session")
            flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
            return redirect("secretary:staff_selection_non-resident_docs")

        return render(
            request,
            "staff/role.html",
            {
                "user_fullname": user_fullname,
                "user_role": user_role,
                "page_path": f"{user_role} / Account Verification",
                "page_title": "Account Verification",
                "user_role_template": user_role_template,
                "role_form": role_form,
                "sched_form": sched_form,
                "personal": personal,
                "docs": docs,
            },
        )

    role_str = (request.POST.get("role") or "").strip()
    role_id = int(role_str) if role_str.isdigit() else None

    purok_ids: List[int] = []
    base_purok = (request.POST.get("purok_sitio") or "").strip()
    if base_purok.isdigit():
        purok_ids.append(int(base_purok))
    for x in request.POST.getlist("purok_sitio_ids[]"):
        x = (x or "").strip()
        if x.isdigit():
            purok_ids.append(int(x))

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

    if role_id == ROLE_BHW:
        if len(purok_ids) < 1:
            flash_warning(request, "Barangay Health Worker must be assigned to at least one Purok/Sitio.")
            return redirect(request.path)
        if len(purok_ids) != len(set(purok_ids)):
            flash_warning(request, "Duplicate Purok/Sitio selections are not allowed.")
            return redirect(request.path)

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
        return redirect("secretary:staff_selection_non-resident")

    if not docs:
        flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
        return redirect("secretary:staff_selection_non-resident_docs")

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    if not staff_id:
        logger.error("Validation ✗ Missing staff_id")
        flash_warning(request, "Your session is missing staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or request.path)

    # decode from session (front_b64/back_b64/selfie_b64), upload now
    front_b64 = docs.get("front_b64")
    back_b64  = docs.get("back_b64")
    selfie_b64= docs.get("selfie_b64")
    proof_b64 = docs.get("proof_b64")
    valid_id_type_id = docs.get("valid_id_type_id")

    if not (front_b64 and back_b64 and selfie_b64):
        logger.error("Step3 ✗ Missing base64 docs: %s", list(docs.keys()))
        flash_warning(request, "Supporting documents are incomplete. Please re-upload.")
        return redirect("secretary:staff_selection_non-resident_docs")

    final_base = f"person/{_key_from_personal(personal)}"
    proof_final_base = f"staff_acc_req_proof/{_key_from_personal(personal)}"

    try:
        b_front  = base64.b64decode(front_b64)
        b_back   = base64.b64decode(back_b64)
        b_selfie = base64.b64decode(selfie_b64)
        b_proof  = base64.b64decode(proof_b64) if proof_b64 else None
    except Exception as e:
        logger.error("Step3 ✗ Base64 decode failed: %s", e)
        flash_system_error(request, "Images could not be decoded from session.", exc=e)
        return redirect("secretary:staff_selection_non-resident_docs")

    try:
        f_buf, f_mime, f_ext = _prep_image_for_upload(io.BytesIO(b_front))
        b_buf, b_mime, b_ext = _prep_image_for_upload(io.BytesIO(b_back))
        s_buf, s_mime, s_ext = _prep_image_for_upload(io.BytesIO(b_selfie))

        up_front = _upload_to_storage_retry(
            f_buf,
            path=f"{final_base}/front.{f_ext}",
            bucket=BUCKET_FINAL,
            content_type=f_mime,
            make_public=True,
        )
        up_back = _upload_to_storage_retry(
            b_buf,
            path=f"{final_base}/back.{b_ext}",
            bucket=BUCKET_FINAL,
            content_type=b_mime,
            make_public=True,
        )
        up_selfie = _upload_to_storage_retry(
            s_buf,
            path=f"{final_base}/selfie.{s_ext}",
            bucket=BUCKET_FINAL,
            content_type=s_mime,
            make_public=True,
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
        logger.error("Step3 ✗ Upload failed: %s", e)
        flash_system_error(request, "Final upload failed.", exc=e)
        return redirect(request.path)

    front_url = up_front.get("public_url") or up_front.get("signed_url")
    back_url  = up_back.get("public_url") or up_back.get("signed_url")
    self_url  = up_selfie.get("public_url") or up_selfie.get("signed_url")
    proof_url = up_proof.get("public_url") or up_proof.get("signed_url") if up_proof else None

    try:
        req_id = Secretary.insert_nonres_staff_account_request(
            p_requested_by_id=staff_id,
            p_person_id=None,
            p_role_id=role_id,
            p_supporting_docs=([proof_url] if proof_url else None),
            p_lupon_sched=schedules if schedules else None,
            p_bhw_purok_ids=sorted(set(purok_ids)) if purok_ids else None,
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
        logger.exception("DB ✗ insert_nonres_staff_account_request failed")
        pgcode, primary = _pg_err_tuple(e)

        if pgcode == "P5007":
            from django.contrib import messages
            messages.warning(
                request,
                "This person is already registered. Redirected you to the staff account request for this person."
            )
            return _smart_redirect(request, "secretary:staff_selection_resident")

        flash_db_error(request, e)
        return redirect(request.path)
    except Exception as e:
        logger.exception("System ✗ insert_nonres_staff_account_request failed")
        flash_system_error(request, "Failed to create staff account request.", exc=e)
        return redirect(request.path)

    # Clean heavy base64 previews from session after success
    try:
        if "docs" in wiz:
            for k in ("front_b64","back_b64","selfie_b64","proof_b64","front_preview","back_preview","selfie_preview","proof_preview"):
                wiz["docs"].pop(k, None)
            _wiz_set(request, "docs", wiz["docs"])
    except Exception:
        pass

    logger.info(
        "Step3 ✓ staff_request created: req_id=%s role_id=%s purok_ids=%s schedules_count=%s",
        req_id, role_id, purok_ids, len(schedules)
    )
    flash_success(request, f"Staff account request created.")
    
    _wiz_clear(request)
    return redirect("secretary:staff_selection")


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_list(request):

    try:
        rows = Secretary.get_all_staff_info_summary() or []
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

    # Session/user display info
    auth = request.session.get("auth") or {}
    _user_fullname = auth.get("full_name") or user_fullname
    _user_role = auth.get("role_name") or user_role
    _user_role_template = (_user_role or "").lower().replace(" ", "_")

    return render(request, "staff/staff_list.html", {
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
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def staff_search_api(request):
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
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def staff_filter_api(request):
    role_raw = (request.GET.get("role_id") or "").strip()
    acc_raw  = (request.GET.get("account_status_id") or "").strip()

    role_id = int(role_raw) if role_raw.isdigit() else None
    acc_id  = int(acc_raw)  if acc_raw.isdigit()  else None

    try:
        if role_id is None and acc_id is None:
            rows = Secretary.get_all_staff_info_summary()
        else:
            rows = Secretary.filter_staff_by_role_and_account(role_id, acc_id)
        return JsonResponse({"results": rows})
    except Exception as e:
        logger.exception("staff_filter_api error: %s", e)
        return JsonResponse({"results": [], "error": "Filter failed"}, status=500)



@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_dets(request, staff_code: str):
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
    return render(request, "staff/staff_dets.html", ctx)

 

 # ─────────────────────────────────────────────────────────────
# NEW: Residents list (minimal) + view profile (RPC-backed)
# ─────────────────────────────────────────────────────────────

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def residents_list(request: HttpRequest) -> HttpResponse:
    """Minimal residents table: Name | Address | Actions"""
    q = (request.GET.get("q") or "").strip()
    page = int(request.GET.get("page") or 1)
    page_size = 15

    try:
        rows, total = list_residents_minimal(search=q, page=page, page_size=page_size)
    except Exception as e:
        messages.error(request, f"Failed to load residents: {e}")
        rows, total = [], 0

    paginator = Paginator(range(total), page_size)  # fake range to drive page controls
    page_obj = paginator.get_page(page)

    return render(request, "secretary/residents_list.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Residents',
        'page_title': 'Residents',
        'user_role_template': user_role_template,
        'rows': rows,
        'q': q,
        'page_obj': page_obj,
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def resident_profile(request: HttpRequest, person_id: int) -> HttpResponse:
    """Uses RPC get_specific_resident_full_profile for details."""
    try:
        profile = get_resident_full_profile(person_id)
        if not profile:
            messages.error(request, "Resident not found.")
            return redirect("secretary:residents_list")
    except Exception as e:
        messages.error(request, f"Failed to open profile: {e}")
        return redirect("secretary:residents_list")

    return render(request, "secretary/resident_profile.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Residents / Profile',
        'page_title': 'Resident Profile',
        'user_role_template': user_role_template,
        'profile': profile,
    })

# -------------------------------
# RESIDENT
# -------------------------------

def resident_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "resident/resident_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Resident List',
        'page_title': 'Resident List',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

def resident_map_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "resident/resident_map_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Resident Map',
        'page_title': 'Resident Map',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })



# -------------------------------
# HOUSEHOLD
# -------------------------------
@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def household_list(
    request: HttpRequest,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponseRedirect | HttpResponseRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = HouseholdFilters(request.GET or None)

    search = request.GET.get("search")
    house_type = _to_int_or_none(request.GET.get("house_type"))
    house_ownership = _to_int_or_none(request.GET.get("house_ownership"))

    rows = household_service.execute(
        search=search,
        house_type=house_type,
        ownership_type=house_ownership,
    )

    paginator = Paginator(rows,10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or house_type is not None or house_ownership is not None) and not form.is_valid():
        form = HouseholdFilters()

    return render(request, "household/household_list.html", {
        'page_path': f'{user_role} / Household List',
        'page_title': 'Household List',
        'page_obj': page_obj,
        'form': form,
        'filters' : {
            'search' : search,
            'house_type' : house_type,
            'house_ownership':  house_ownership,
        },
        "search_url": "secretary:ajax_household_search",
    })

@session_login_required
@role_required(SECRETARY_ROLE)   # change if needed
@nocache
@inject
def ajax_household_search(
    request: HttpRequest,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponse:
    """
    Returns partial HTML for live search.
    Accepts:
      q -> search
      house_type, house_ownership
      tpl -> 'cards' (default) or 'rows'
    """
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")

    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    if tpl_key == "rows":
        template_name = "household/_household_list.html"   # table rows partial
        ctx_key = "rows"
    elif tpl_key == "cards":
        template_name = "household/_households.html"       # cards partial (map list)
        ctx_key = "cards"
    else:
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q")
    house_type = _to_int_or_none(request.GET.get("house_type"))
    house_ownership = _to_int_or_none(request.GET.get("house_ownership"))

    rows = household_service.execute(
        search=q,
        house_type=house_type,
        ownership_type=house_ownership,
    )[:50]

    html = render_to_string(
        template_name,
        {ctx_key: rows},
        request=request,
    )
    return HttpResponse(html)

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def household_map_list(
    request: HttpRequest,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = HouseholdFilters(request.GET or None)

    search = request.GET.get("search")
    house_type = _to_int_or_none(request.GET.get("house_type"))
    house_ownership = _to_int_or_none(request.GET.get("house_ownership"))

    rows = household_service.execute(
        search=search,
        house_type=house_type,
        ownership_type=house_ownership,
    )

    paginator = Paginator(rows,10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or house_type is not None or house_ownership is not None) and not form.is_valid():
        form = HouseholdFilters()

    return render(request, "household/household_map_list.html", {
        'page_path': f'{user_role} / Household Map',
        'page_title': 'Household Map',
        'page_obj': page_obj,
        'form': form,
        'filters' : {
            'search' : search,
            'house_type' : house_type,
            'house_ownership':  house_ownership,
        },
        "pins_url": reverse("secretary:api_household_pins"),
        'search_url': 'secretary:ajax_household_search',
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def api_household_pins(
    request: HttpRequest,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
):
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    pins = household_repo.fetch_household_pins(
        search=(request.GET.get("search") or None),
        house_type=_to_int_or_none(request.GET.get("house_type")),
        ownership_type=_to_int_or_none(request.GET.get("house_ownership")),
    )
    return JsonResponse(pins, safe=False)

# -------------------------------
# BUSINESS
# -------------------------------

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def business_list(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = BusinessFilters(request.GET or None)

    search = request.GET.get("search")
    b_category = _to_int_or_none(request.GET.get("b_category"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search= search,
        b_category= b_category,
        ownership_type= ownership_type,
        status= status,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_category is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(request, "business/business_list.html", {
        'page_path': f'{user_role} / Business Records',
        'page_title': 'Business Records',
        'form' : form,
        'page_obj' : page_obj,
        'filters' : {
            'search' : search,
            'b_category' : b_category,
            'ownership_type' :ownership_type,
            'status' : status,
        },
        'url_name' : 'secretary:business_information',
        'search_url': 'secretary:ajax_business_search',
        'is_clerk': (user_role == 'Barangay Clerk'),
    })

AJAX_BUSINESS_PARTIALS = {
    # key      -> template path
    "cards": "business/_businesses.html",         # your map list cards
    "rows":  "business/_business_list.html",      # table rows for list page
}

@session_login_required
@role_required(SECRETARY_ROLE)
@require_GET
@inject
def ajax_business_search(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    # only allow XHR (optional, but nice)
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR required")
    
    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    template_name = AJAX_BUSINESS_PARTIALS.get(tpl_key)
    if not template_name:
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    b_category = request.GET.get("b_category")
    ownership_type = request.GET.get("ownership_type")
    status = request.GET.get("status")

    # def to_int_or_none(v):
    #     try:
    #         return int(v) if v not in (None, "",) else None
    #     except ValueError:
    #         return None

    rows = business_service.execute(
        search=q,
        b_category=_to_int_or_none(b_category),
        ownership_type=_to_int_or_none(ownership_type),
        status=_to_int_or_none(status),
    )[:50]

    base_ctx = {
        "url_name": "secretary:business_information",
    }

    context = {**base_ctx, ("rows" if tpl_key == "rows" else "cards"): rows}
    html = render_to_string(template_name, context, request=request)
    return HttpResponse(html)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def business_information(
    request, 
    b_id: int,
    business_info: IBusinessInfoService = Provide[
        AppContainer.owner_business_service]) -> HttpResponse:
    user_role = _auth_role_name(request)
    
    person_id = request.GET.get("owner")
    person_id = int(person_id) if person_id and str(person_id).isdigit() else None

    dto = (
        business_info.execute(person_id=person_id, business_id=b_id)
        if person_id is not None
        else business_info.execute_by_business_id(b_id)  # see helper below
    )

    def _compose_owner_full_name(data: dict) -> str | None:
        last   = (data.get("last_name") or "").strip()
        first  = (data.get("first_name") or "").strip()
        middle = (data.get("middle_name") or "").strip()
        suffix = (data.get("suffix") or "").strip()

        parts = []
        if last:
            parts.append(last.upper())                   # LAST
        if first:
            parts.append((", " if parts else "") + first.title())  # , First
        if middle:
            parts.append(" " + middle[:1].upper() + ".")           #  M.
        if suffix:
            parts.append(" " + suffix.upper())                     #  JR / III, etc.
        return "".join(parts) or None
    
    def _compose_full_address_from_owner(data: dict) -> str | None:
        street      = (data.get("street") or "").strip()
        sitio_purok = (data.get("sitio_purok") or "").strip()
        barangay    = (data.get("barangay") or "").strip()
        city        = (data.get("city") or "").strip()

        # Order strictly: STREET, PUROK/SITIO, BARANGAY, CITY
        parts = [p for p in [street, sitio_purok, barangay, city] if p]
        return ", ".join(parts) if parts else None

    owner = dict(dto.owner or {})
    owner["owner_full_name"] = _compose_owner_full_name(owner)
    owner["full_address"]    = _compose_full_address_from_owner(owner)

    operating_days = (dto.business.get("operating_days") or "").strip()  # e.g., "Mon, Tue, Wed"
    days = [d.strip() for d in operating_days.split(",")] if operating_days else []
    operating_days_start_name = days[0] if days else None
    operating_days_end_name = days[-1] if days else None

    formatted_id = f"{int(b_id):06d}"

    return render(
        request,
        "business/business_information.html",
        {
            "page_path": f"{user_role} / Business Records / Business Details : {formatted_id}",
            "page_title": f"Business Details : {formatted_id}",
            "owner": owner,
            "business": dto.business,
            "business_files": (dto.business_proof or {}).get("files") or [],
            "operating_days_start_name": operating_days_start_name,
            "operating_days_end_name": operating_days_end_name,
        },
    )

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def business_map_list(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = BusinessFilters(request.GET or None)

    search = request.GET.get("search")
    b_category = _to_int_or_none(request.GET.get("b_category"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search=search,
        b_category=b_category,
        ownership_type=ownership_type,
        status=status,
    )

    paginator = Paginator(rows, 5)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_category is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(
        request,
        "business/business_map_list.html",
        {
            'page_path': f"{user_role} / Business Map",
            'page_title': "Business Map",
            'form': form,
            'page_obj' : page_obj,
            'filters' : {
                'search' : search,
                'b_category' : b_category,
                'ownership_type' :ownership_type,
                'status' : status,
            },
            "pins_url": reverse("secretary:api_business_pins"),
            'search_url': 'secretary:ajax_business_search',
        }
    )

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def api_business_pins(
    request: HttpRequest,
    business_repo: IBusinessRepository = Provide[AppContainer.infra.business],
):
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    pins = business_repo.fetch_business_pins(
        search=(request.GET.get("search") or None),
        b_category=_to_int_or_none(request.GET.get("b_category")),
        ownership_type=_to_int_or_none(request.GET.get("ownership_type")),
        status=_to_int_or_none(request.GET.get("status")),
    )
    return JsonResponse(pins, safe=False)

