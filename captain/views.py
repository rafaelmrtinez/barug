from __future__ import annotations
from django.templatetags.static import static

import os
os.environ.setdefault("HTTPX_DISABLE_HTTP2", "1")

import io
import logging
from uuid import uuid4  # (kept only if you actually use later; safe to remove otherwise)
from datetime import datetime, time as dtime, date
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_http_methods

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

from common.supabase_client import supabase
from common.services.storage import upload_to_storage

from captain.models import Captain
from .forms import (SearchPerson, ResidentProfileform, ChooseRole, StaffFilters, Schedule,)

from common.flash import flash_success, flash_warning, flash_db_error, flash_system_error
from django.db import DatabaseError, OperationalError, IntegrityError
from common.db_errors import _pg_err_tuple
from django.core.paginator import Paginator


logger = logging.getLogger(__name__)

ROLE_BHW = 9
ROLE_LUPON = 8
WZ_KEY = "staff_nonres_wizard"

# Demo identity (kept as-is)
user_fullname = "lname, fname mname suffix"
user_role = "Barangay Captain"
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
    """
    Load an uploaded image, auto-rotate using EXIF, bound to max size, and re-encode as JPEG.
    Returns a BytesIO ready for upload_to_storage.
    If Pillow is missing or anything fails, falls back to the original stream.
    """
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
    """
    Returns: (buf, mime, ext)
      - If the image has transparency -> keep PNG  (image/png, .png)
      - Else -> JPEG with autorotate + bounding   (image/jpeg, .jpg)
    """
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

# === Non-resident flow helpers ===
import re
from datetime import datetime as _dt

def _key_from_personal(personal: dict) -> str:
    """
    temp + L-initial + F-initial + M-initial + mmddyyyy + last 8 digits of mobile
    e.g., 'nonres-lfm09212003XXXXXXXX-staff-app'
    """
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
@role_required(user_role)
@nocache
@require_GET
# Create your views here.
def staff_selection(request):
    return render(request, "staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

@session_login_required
@role_required(user_role)
@nocache
@require_GET
def resident_suggest(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    try:
        rows = Captain.search_resident(q) or []
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
@role_required(user_role)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_resident(request):

    pid = (request.POST.get("pid") or "").strip()
    role_str = (request.POST.get("role") or "").strip()
    role_id = int(role_str) if role_str.isdigit() else None

    proof_url = (request.POST.get("proof") or "").strip() or None
    proof_file = request.FILES.get("proof_file") if hasattr(request, "FILES") else None

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id") or 6

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

        # ===========================
        # Upload PROOF to bucket (if any)
        # ===========================
        BUCKET_FOR_PROOF = BUCKET_STAFF_PROOF

        try:
            rows_for_key = Captain.get_resident_details(int(pid)) or []
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

        # ===========================
        # Create staff request in DB
        # ===========================
        try:
            result = Captain.insert_res_staff_account_request(
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
            residents = Captain.search_resident(res_search) or []
        if res_id:
            rows = Captain.get_resident_details(int(res_id)) or []
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

@session_login_required
@role_required(user_role)
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
@role_required(user_role)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres_docs(request: HttpRequest) -> HttpResponse:
    """
    PREVIEW-ONLY (no bucket writes here)
    """
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

def staff_selection_nonres_role_review(request):
    role_form = ChooseRole()
    sched_form = Schedule()
    return render(request, "role.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'role_form': role_form,
        'sched_form': sched_form,
    })

def staff_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "staff_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Staff Lits',
        'page_title': 'Staff List',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

def staff_dets(request, staff_id):
    return render(request, "person/staff_dets.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Staff Details : {staff_id}',
        'page_title' : f'Staff Details : {staff_id}',
        'user_role_template' : user_role_template,
    })