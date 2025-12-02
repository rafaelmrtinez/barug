from __future__ import annotations

# Standard library
import base64
import io
import logging
import re
import secrets
import string
from datetime import date, datetime, time as dtime
from typing import Any, Dict, List, Optional

# Third-party / external apps
import secretary

# Django
from django.conf import settings
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, OperationalError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_GET, require_http_methods
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer

# Local apps / project modules
from .forms import (
    ChooseRole,
    DAY_CHOICES,
    ResidentProfileform,
    Schedule,
    SearchPerson,
    StaffAccountRequestFilters,
    StaffFilters,
    StaffUpdateForm,
    UpdateInfo,
)
from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from captain.models import Captain
from common.flash import flash_db_error, flash_success, flash_system_error, flash_warning
from common.send_email import send_email
from common.email_validator import verify_email_deliverable_abstract
from common.services.storage import upload_to_storage
from common.supabase_client import supabase
from secretary.models import Secretary
from staff_admin.models import Admin

logger = logging.getLogger(__name__)

ADMIN_ROLE = "Admin"
REQUEST_STATUS_APPROVED = 30
REQUEST_STATUS_REJECTED = 4
WAITING_FOR_ADMIN = 30

ROLE_BHW = 9
ROLE_LUPON = 8
WZ_KEY = "admin_staff_nonres_wizard"

CAPTAIN_ROLE = "Barangay Captain"

BUCKET_FINAL = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
BUCKET_STAFF_PROOF = getattr(settings, "SUPABASE_STAFF_PROOF_BUCKET", "staff-proof")

def get_user_info(request):
    """Get user info from session - call this in each view"""
    auth = request.session.get('auth', {})
    first_name = (auth.get('first_name', '') or '').strip().title()
    middle_name = (auth.get('middle_name', '') or '').strip().title()
    last_name = (auth.get('last_name', '') or '').strip().title()
    suffix = (auth.get('suffix', '') or '').strip().upper()
    
    # Format: "Last Name, First Name Middle Initial Suffix"
    name_parts = [first_name]
    if middle_name:
        name_parts.append(middle_name[0] + '.')  # Middle initial with period
    if suffix:
        name_parts.append(suffix)
    
    user_fullname = f"{last_name}, {' '.join(name_parts)}"
    user_role = auth.get('role_name', 'Staff').title()
    user_role_template = user_role.lower().replace(' ', '_')
    
    return user_fullname, user_role, user_role_template

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

def _to_int_or_none(val) -> Optional[int]:
    try:
        if val in (None, "", "None"):
            return None
        return int(val)
    except Exception:
        return None

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@inject
def dashboard(
    request: HttpRequest,
    admin_dashboard_service=Provide[AppContainer.admin_dashboard_service],
):
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    person_id = auth.get('person_id')

    kpis = {
        "doc_requests": 0,
        "doc_requests_delta": 0,
        "residents_total": 0,
        "ongoing_cases": 0,
        "open_cases": 0,
        "residents_total": 0,
        "household_total": 0,
        "families_total": 0,
        "women_vaccinated": 0,
        "children_vaccinated": 0,
    }

    dashboard_json = None
    announcements = []

    try:
        payload = admin_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json")
    except Exception as exc:
        print("Error fetching admin dashboard KPIs:", exc)
    
    if person_id:
        try:
            from authentication.announcement_views import get_user_announcements
            announcements = get_user_announcements(person_id)
        except Exception as exc:
            print(f"Error fetching announcements for person {person_id}:", exc)

    return render(request, "staff_admin/dashboard.html", {
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'kpis': kpis,
        'dashboard_json': dashboard_json,
        'today': datetime.now().strftime("%B %d, %Y"),
        'announcements': announcements,
    })

def _smart_redirect(request, url_name, *args, **kwargs):
    from django.urls import reverse
    url = reverse(url_name, args=args, kwargs=kwargs)
    if request.headers.get("HX-Request") == "true":
        return HttpResponse(status=204, headers={"HX-Redirect": url})
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"redirect": url, "ok": True})
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

def _prep_image_for_upload(file_obj, *, max_w=2200, max_h=2200, default_bg="white"):
    from io import BytesIO
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

def _bytes_to_data_url(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(b).decode('ascii')}"

def _same_file(a, b) -> bool:
    if not a or not b:
        return False
    try:
        return (getattr(a, "size", None) == getattr(b, "size", None)) and (
            getattr(a, "name", "") == getattr(b, "name", "")
        )
    except Exception:
        return False

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
                "ReadError" in msg
                or "TransportError" in msg
                or "A non-blocking socket operation could not be completed immediately" in msg
                or "WinError 10035" in msg
            )
            if attempt < max_retries and transient:
                sleep_s = base_sleep * (2 ** attempt)
                logger.warning("Upload transient error (%s). Retrying in %.2fs [%d/%d]…", msg, sleep_s, attempt + 1, max_retries)
                _time.sleep(sleep_s)
                continue
            last_err = e
            break
    raise last_err

def _rand_password(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def _initials_from_name(first: str, middle: Optional[str], last: str, suffix: Optional[str]) -> str:
    def fch(s: Optional[str]) -> str:
        s = (s or "").strip()
        return s[0] if s else ""
    def clean_suffix(s: Optional[str]) -> str:
        s = (s or "").strip()
        s = re.sub(r"[^\w]+", "", s)
        return s
    parts = [fch(first), fch(middle), fch(last), clean_suffix(suffix)]
    return "".join(p for p in parts if p).lower()

def _get_staff_by_id(staff_id: int) -> dict | None:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   s.staff_code,
                   p.first_name,
                   p.middle_name,
                   p.last_name,
                   p.suffix,
                   p.email
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            WHERE s.staff_id = %s
            """,
            [staff_id],
        )
        row = cur.fetchone()
    if not row:
        return None
    keys = ["staff_id", "staff_code", "first_name", "middle_name", "last_name", "suffix", "email"]
    return dict(zip(keys, row))

# ── Page: landing ─────────────────────────────────────────────────────────────
@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_selection(request):
    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/staff/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

# ── Resident flow (Admin) ────────────────────────────────────────────────────

@session_login_required
@role_required(ADMIN_ROLE)
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
        logger.exception("resident_suggest failed")
        return JsonResponse({"results": [], "error": "Oops! Our system is having an issue for now. Please try again later."}, status=500)

# === Non-resident flow helpers ===
from datetime import datetime as _dt

def _key_from_personal(personal: dict) -> str:
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
                b_dt = _dt.strptime(b, fmt).date()
                break
            except Exception:
                pass
    b_str = b_dt.strftime("%m%d%Y") if b_dt else ""
    mobile_raw = (personal.get("mobile_num") or "").strip()
    mobile_digits = re.sub(r"\D+", "", mobile_raw)
    last8 = mobile_digits[-8:] if mobile_digits else ""
    return f"{initials}{b_str}{last8}-staff-app"

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:
    pid = (request.POST.get("pid") or "").strip()
    role_str = (request.POST.get("role") or "").strip()
    role_id = int(role_str) if role_str.isdigit() else None

    # ▼▼▼ CHANGED: accept uploads from either `proof` (template field) or `proof_file` (legacy)
    proof_file = None  # CHANGED
    if hasattr(request, "FILES"):  # CHANGED
        proof_file = (request.FILES.get("proof") or  # CHANGED
                      request.FILES.get("proof_file") or  # CHANGED
                      None)  # CHANGED

    # Keep reading any textual proof value (data: URL or plain URL)
    proof_url = (request.POST.get("proof") or "").strip() or None  # CHANGED

    # ▼▼▼ CHANGED: ignore bare filenames like 'sheet.jpg' or 'C:\fakepath\file.jpg'
    if proof_url and not (proof_url.startswith("http://") or proof_url.startswith("https://") or proof_url.startswith("data:")):  # CHANGED
        logger.warning("Ignoring non-URL, non-data proof value: %r", proof_url)  # CHANGED
        proof_url = None  # CHANGED
    # ▲▲▲ END CHANGED

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    # --- Collect BHW puroks
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

    # POST: Create Staff flow
    if request.method == "POST" and pid:
        if not (pid or role_id or proof_file or proof_url or base_purok
                or request.POST.getlist("purok_sitio_ids[]")
                or request.POST.get("day") or request.POST.getlist("day[]")):
            flash_warning(request, "Please select a resident and fill out the form before submitting.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not staff_id:
            logger.error("Validation error: Missing staff_id")
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not role_id:
            logger.error("Validation error: No role selected")
            flash_warning(request, "Please choose a staff role.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_BHW and len(purok_ids) < 1:
            logger.error("Validation error: BHW requires at least one purok")
            flash_warning(request, "BHW must be assigned to at least one Purok/Sitio.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_LUPON and len(schedules) < 1:
            logger.error("Validation error: Lupon requires at least one schedule")
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
                logger.error("Validation error: Duplicate Purok/Sitio selections are not allowed: %s", _raw_purok_ids)
                flash_warning(request, "Duplicate Purok/Sitio selections are not allowed.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_LUPON and schedules:
            _days = [s["day"] for s in schedules]
            if len(_days) != len(set(_days)):
                logger.error("Validation error: Duplicate day selections in schedule are not allowed: %s", _days)
                flash_warning(request, "Duplicate day selections in schedule are not allowed.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        # ▼▼▼ CHANGED: after sanitization above, enforce proof presence
        if not (proof_file or proof_url):
            flash_warning(request, "Please attach a proof of employment.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        # ▲▲▲ END CHANGED

        BUCKET_FOR_PROOF = BUCKET_STAFF_PROOF

        # Build nice storage key base from resident details
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
                "middle_name":rd.get("middle_name") or "",
                "birthdate":  rd.get("birthdate") or "",
                "mobile_num": rd.get("mobile_num") or "",
            }

        try:
            personal_like = _personal_like(res_for_key)
            final_base = f"staff_acc_req_proof/{_key_from_personal(personal_like)}"
        except Exception:
            final_base = f"staff_acc_req_proof/{pid}"

        # ── Upload/Sanitize proof and ALWAYS store a PUBLIC (permanent) URL ───────────
        uploaded_proof_url = None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if proof_file:
            try:
                buf, mime, ext = _prep_image_for_upload(proof_file)
                proof_rel_path = f"{final_base}/staff-app-proof-{role_id}-{timestamp}.{ext}"
                up_res = _upload_to_storage_retry(
                    buf,
                    path=proof_rel_path,
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,   # public permanent URL
                )
                uploaded_proof_url = (
                    (up_res.get("public_url") if isinstance(up_res, dict) else None)
                    or (up_res.get("signed_url") if isinstance(up_res, dict) else None)
                )
                if not uploaded_proof_url:
                    logger.error("Proof upload returned no usable URL for %s", proof_rel_path)
                    flash_system_error(request, "Proof upload did not return a usable URL.")
                    return redirect(request.META.get("HTTP_REFERER") or request.path)
            except (DatabaseError, OperationalError, IntegrityError) as e:
                flash_db_error(request, e)
                return redirect(request.META.get("HTTP_REFERER") or request.path)
            except Exception as e:
                flash_system_error(request, "Proof upload failed.", exc=e)
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        elif proof_url:
            # Accept a data-URL or https URL, re-host data-URL as permanent public URL
            m = re.match(r"^data:(.+?);base64,(.+)$", proof_url)
            if m:
                _mime_hint, b64 = m.groups()
                raw = io.BytesIO(base64.b64decode(b64))
                buf, mime, ext = _prep_image_for_upload(raw)
                proof_rel_path = f"{final_base}/staff-app-proof-{role_id}-{timestamp}.{ext}"
                up_res = _upload_to_storage_retry(
                    buf,
                    path=proof_rel_path,
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,  # public permanent URL
                )
                uploaded_proof_url = (
                    (up_res.get("public_url") if isinstance(up_res, dict) else None)
                    or (up_res.get("signed_url") if isinstance(up_res, dict) else None)
                )
                if not uploaded_proof_url:
                    logger.error("Proof upload returned no usable URL for %s", proof_rel_path)
                    flash_system_error(request, "Proof upload did not return a usable URL.")
                    return redirect(request.META.get("HTTP_REFERER") or request.path)
            else:
                # Already-hosted https URL — accept as-is
                uploaded_proof_url = proof_url

        # ▼▼▼ CHANGED: final guard — refuse non-URL value just in case
        if uploaded_proof_url and not uploaded_proof_url.startswith(("http://", "https://")):
            logger.error("Refusing to store non-URL proof value: %r", uploaded_proof_url)
            flash_system_error(request, "Proof upload failed to produce a valid URL.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        # ▲▲▲ END CHANGED

        # (1) CREATE STAFF DIRECTLY — returns (out_staff_id, out_staff_code)
        try:
            res_direct = Admin.create_staff_direct(
                p_requested_by_id=staff_id,
                p_person_id=int(pid),
                p_role_id=role_id,
                p_supporting_docs=([uploaded_proof_url] if uploaded_proof_url else None),
                p_lupon_sched=(schedules if schedules else None),
                p_bhw_purok_ids=(purok_ids if purok_ids else None),
            )

            new_staff_id = int(
                (res_direct.get("staff_id") if isinstance(res_direct, dict) else None)
                or (res_direct.get("out_staff_id") if isinstance(res_direct, dict) else None)
            )
            staff_code = (
                (res_direct.get("staff_code") if isinstance(res_direct, dict) else None)
                or (res_direct.get("out_staff_code") if isinstance(res_direct, dict) else None)
                or ""
            ).strip()

            if not new_staff_id or not staff_code:
                flash_warning(request, "Staff created, but no identifier returned. Please verify in the Staff List.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

            logger.info("Staff created -> id=%s code=%s (person_id=%s)", new_staff_id, staff_code, pid)
        except (DatabaseError, OperationalError, IntegrityError) as e:
            flash_db_error(request, e)
            logger.exception("DB error: create_staff_direct failed")
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "System error: create_staff_direct failed.", exc=e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # (2) UPSERT CREDENTIALS
        try:
            srow = None
            if staff_code:
                srow = _get_staff_by_code(staff_code)
            if not srow:
                srow = _get_staff_by_id(new_staff_id)

            if not srow:
                flash_warning(
                    request,
                    f"Staff created (code={staff_code or 'N/A'}) but record could not be reloaded for credentials."
                )
                return redirect(request.META.get("HTTP_REFERER") or request.path)

            staff_code = (staff_code or srow.get("staff_code") or "").strip()
            if not staff_code:
                flash_warning(request, "Staff created but staff_code is missing. Please verify in Staff List.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

            initials = _initials_from_name(
                first=srow.get("first_name"),
                middle=srow.get("middle_name"),
                last=srow.get("last_name"),
                suffix=srow.get("suffix"),
            )
            username = f"brgySN.{initials}{staff_code}"
            temp_password = _rand_password(8)

            email_to = (request.POST.get("email") or "").strip() or (srow.get("email") or "").strip()
            
            # Validate email if provided
            if email_to:
                is_valid, reason = verify_email_deliverable_abstract(email_to)
                if not is_valid:
                    flash_warning(request, f"Email validation failed: {reason}. Staff account created but credentials not sent.")
                    email_to = None
            
            sent_flag = bool(email_to)

            ok_upsert = Captain.upsert_staff_credentials_and_log(
                p_staff_id=new_staff_id,
                p_username=username,
                p_password_plain=temp_password,
                p_sender_staff_id=staff_id,
                p_is_credentials_sent=sent_flag,
            )
            if not ok_upsert:
                flash_warning(request, "Staff created, but failed to write credentials. Please re-issue credentials.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)
        except (DatabaseError, OperationalError, IntegrityError) as e:
            flash_db_error(request, e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "Failed while preparing credentials.", exc=e)
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # (3) SEND EMAIL (best-effort)
        try:
            if email_to:
                try:
                    rl = _label_from_choices(ChooseRole().fields["role"].choices, role_id) if role_id else None
                except Exception:
                    rl = None
                rl = rl or f"Role ID {role_id}" if role_id else "staff"

                subj = f"Barangay Sto. Niño Staff Account Creation and Credentials ({rl})"
                body_txt = (
                    f"Good day!\n\n"
                    f"We are pleased to inform you that your {rl} staff account request has been created. "
                    "Below are your login credentials:\n\n"
                    f"  Username: {username}\n"
                    f"  Temporary Password: {temp_password}\n\n"
                    "For your security, please sign in as soon as possible and change your password immediately.\n\n"
                    "Thank you,\n"
                    "Barangay Sto. Niño"
                )
                body_html = f"""
                <p>Good day!</p>
                <p>We are pleased to inform you that your <strong>{rl}</strong> staff account request has been created. Below are your login credentials:</p>
                <ul>
                    <li><strong>Username:</strong> {username}</li>
                    <li><strong>Temporary Password:</strong> {temp_password}</li>
                </ul>
                <p>For your security, please sign in as soon as possible and change your password immediately.</p>
                <p>Thank you,<br>Barangay Sto. Niño</p>
                """.strip()
                resp = send_email(
                    subject=subj,
                    to=[email_to],
                    body_text=body_txt,
                    body_html=body_html,
                    from_name="Barangay Sto. Niño",
                    fail_silently=True,
                )
                if getattr(resp, "ok", False):
                    flash_success(request, f"Staff account created. Credentials have been emailed to this staff.")
                else:
                    flash_warning(request, f"Staff account created. Email sending failed; please resend manually.")
            else:
                flash_success(request, f"Staff account created. No email on file; credentials stored.")
        except Exception as e:
            logger.warning("Email send failed for staff_code=%s: %s", staff_code, e)
            flash_warning(request, f"Staff account created and credentials stored, but emailing failed. Please resend manually.")

        return redirect(request.META.get("HTTP_REFERER") or request.path)

    # GET (or POST without creation): search & preview only
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
                    if v: return v
                return None

            front_val  = _val(res_details, "valid_id_front_files", "valid_id_front_url", "valid_id_front_path")
            back_val   = _val(res_details, "valid_id_back_files",  "valid_id_back_url",  "valid_id_back_path")
            selfie_val = _val(res_details, "selfie_with_id",       "selfie_url",         "selfie_with_id_path")

            PERSON_BUCKET = BUCKET_FINAL
            def _push(label: str, value: Optional[str]):
                if not value: return
                v = str(value).strip()
                if v.startswith("http://") or v.startswith("https://"):
                    doc_images.append({"label": label, "src": v, "alt": label}); return
                signed = _make_signed_url(PERSON_BUCKET, v, expire_seconds=1800)
                if signed: doc_images.append({"label": label, "src": signed, "alt": label})

            _push("Front of ID", front_val)
            _push("Back of ID",  back_val)
            _push("Selfie w/ ID", selfie_val)
            logger.debug("doc_images_count=%s keys=%s", len(doc_images), list(res_details.keys()))
    except (DatabaseError, OperationalError, IntegrityError) as e:
        flash_db_error(request, e)
    except Exception as e:
        flash_system_error(request, "Error loading resident details.", exc=e)

    role_form  = ChooseRole()
    sched_form = Schedule()
    proof_form = ResidentProfileform()
    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/staff/staff_selection_resident.html", {
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


# ── Non-resident Step 1 ──────────────────────────────────────────────────────
@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres(request: HttpRequest) -> HttpResponse:
    # Get existing wizard data for form initialization
    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}
    
    # Prepare initial data for form
    initial_data = {}
    if personal and request.method == "GET":
        initial_data = {
            "first_name": personal.get("first_name", ""),
            "last_name": personal.get("last_name", ""),
            "middle_name": personal.get("middle_name", ""),
            "suffix": personal.get("suffix", ""),
            "sex": personal.get("sex_id"),
            "civil_status": personal.get("civil_status_id"),
            "nationality": personal.get("nationality_id"),
            "religion": personal.get("religion_id"),
            "email": personal.get("email", ""),
            "mob_num": personal.get("mobile_num", ""),
            "street": personal.get("street", ""),
            "purok_sitio": personal.get("sitio_purok", ""),
            "barangay": personal.get("barangay", ""),
            "city": personal.get("city", ""),
        }
        # Handle date field separately
        if personal.get("birthdate"):
            try:
                from datetime import datetime
                birthdate_str = personal.get("birthdate")
                if isinstance(birthdate_str, str):
                    initial_data["dob"] = datetime.fromisoformat(birthdate_str).date()
            except (ValueError, TypeError):
                pass
    
    form = ResidentProfileform(request.POST or None, initial=initial_data)
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
            dob = cd.get("dob")
            
            # Validate email if provided
            email_value = cd.get("email") or ""
            if email_value:
                is_valid, reason = verify_email_deliverable_abstract(email_value)
                if not is_valid:
                    flash_warning(request, f"Email validation failed: {reason}. Please provide a valid email address.")
                    return redirect(request.path)
            
            _wiz_set(request, "personal", {
                "first_name":  cd.get("first_name") or "",
                "last_name":   cd.get("last_name") or "",
                "middle_name": cd.get("middle_name") or "",
                "suffix":      (cd.get("suffix") or "").strip() or None,
                "birthdate":   (dob.isoformat() if dob else None),
                "birthdate_label": (dob.strftime("%B %d, %Y") if dob else ""),
                "email":       email_value,
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
            flash_success(request, "Personal information saved.")
            return redirect("staff_admin:staff_selection_nonres_docs")
        else:
            flash_warning(request, "Please correct the errors below.")

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/staff/staff_selection_nonresident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
        'redirect': 'staff_admin:staff_selection_nonres_docs',
        'has_saved_data': bool(personal),  # Indicate if there's saved data
    })

# ── Non-resident Step 2 (docs preview) ───────────────────────────────────────
@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres_docs(request: HttpRequest) -> HttpResponse:
    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}
    docs = wiz.get("docs") or {}
    
    # Prepare initial data for form when navigating back
    initial_data = {}
    if docs and request.method == "GET":
        initial_data = {
            "type_of_id": docs.get("valid_id_type_id"),
        }
    
    form = ResidentProfileform(request.POST or None, request.FILES or None, initial=initial_data)
    for f in ("last_name","first_name","middle_name","suffix","sex","dob",
              "civil_status","nationality","religion","email","mob_num",
              "street","purok_sitio","barangay","city"):
        if f in form.fields:
            form.fields[f].required = False

    if request.method == "GET":
        if not personal:
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("staff_admin:staff_selection_nonres")

    if request.method == "POST":
        valid_id_type_raw = (request.POST.get("type_of_id") or "").strip()
        valid_id_type_id = int(valid_id_type_raw) if valid_id_type_raw.isdigit() else None
        valid_id_type_label = None
        try:
            field_choices = form.fields.get("type_of_id").choices if "type_of_id" in form.fields else []
            for key, label in field_choices:
                if str(key) == valid_id_type_raw:
                    valid_id_type_label = label
                    break
        except Exception:
            valid_id_type_label = None
        if not valid_id_type_id:
            flash_warning(request, "Please choose the Valid ID Type.")
            return redirect(request.path)

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

        try:
            def _readall(fobj):
                try: fobj.seek(0)
                except Exception: pass
                return fobj.read()
            from io import BytesIO
            from PIL import Image  # noqa: F401

            def _jpeg_bytes(fileobj):
                buf, mime, _ext = _prep_image_for_upload(fileobj)
                return _readall(buf)

            b_front  = _jpeg_bytes(front_in)
            b_back   = _jpeg_bytes(back_in)
            b_selfie = _jpeg_bytes(selfie_in)
            b_proof  = _jpeg_bytes(proof_in) if proof_in is not None else None

            docs_payload = {
                "valid_id_type_id": valid_id_type_id,
                "valid_id_type_label": valid_id_type_label,
                "front_preview":  _bytes_to_data_url(b_front,  "image/jpeg"),
                "back_preview":   _bytes_to_data_url(b_back,   "image/jpeg"),
                "selfie_preview": _bytes_to_data_url(b_selfie, "image/jpeg"),
                "proof_preview":  _bytes_to_data_url(b_proof,  "image/jpeg") if b_proof is not None else None,
                "front_b64": base64.b64encode(b_front).decode("ascii"),
                "back_b64": base64.b64encode(b_back).decode("ascii"),
                "selfie_b64": base64.b64encode(b_selfie).decode("ascii"),
                "proof_b64": base64.b64encode(b_proof).decode("ascii") if b_proof is not None else None,
            }
            _wiz_set(request, "docs", docs_payload)
        except Exception as e:
            logger.error("Admin Step2 preview prep failed: %s", e)
            flash_system_error(request, "Could not prepare previews.", exc=e)
            return redirect(request.path)

        flash_success(request, "Documents loaded for preview. Please review and choose role.")
        return redirect("staff_admin:staff_selection_nonres_role_review")

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/staff/supporting_docs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

# ── Non-resident Step 3 (role + finalize -> request) ──────────────────────────
@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres_role_review(request: HttpRequest) -> HttpResponse:
    role_form = ChooseRole(request.POST or None)
    sched_form = Schedule(request.POST or None)

    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}
    docs = wiz.get("docs") or {}

    if request.method == "GET":
        if not personal:
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("staff_admin:staff_selection_nonres")
        if not docs:
            flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
            return redirect("staff_admin:staff_selection_nonres_docs")

        user_fullname, user_role, user_role_template = get_user_info(request)
        return render(request, "staff_admin/staff/role.html", {
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
        if not d_s or not ts_s or not te_s: return
        if not str(d_s).isdigit(): return
        d = int(d_s); ts = _parse_hhmm(ts_s); te = _parse_hhmm(te_s)
        if d < 1 or d > 7 or not ts or not te or not (te > ts): return
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

    if not personal or not docs:
        flash_warning(request, "Missing information. Please complete previous steps.")
        return redirect("staff_admin:staff_selection_nonres")

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    if not staff_id:
        flash_warning(request, "Your session is missing staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or request.path)

    # Upload all images now
    front_b64 = docs.get("front_b64")
    back_b64  = docs.get("back_b64")
    selfie_b64= docs.get("selfie_b64")
    proof_b64 = docs.get("proof_b64")
    valid_id_type_id = docs.get("valid_id_type_id")
    if not (front_b64 and back_b64 and selfie_b64):
        flash_warning(request, "Supporting documents are incomplete. Please re-upload.")
        return redirect("staff_admin:staff_selection_nonres_docs")

    final_base = f"person/{_key_from_personal(personal)}"
    proof_final_base = f"staff_acc_req_proof/{_key_from_personal(personal)}"

    try:
        b_front  = base64.b64decode(front_b64)
        b_back   = base64.b64decode(back_b64)
        b_selfie = base64.b64decode(selfie_b64)
        b_proof  = base64.b64decode(proof_b64) if proof_b64 else None

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
        proof_url = None
        if b_proof is not None:
            p_buf, p_mime, p_ext = _prep_image_for_upload(io.BytesIO(b_proof))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            proof_rel_path = f"{proof_final_base}/staff-app-proof-{role_id}-{timestamp}.{p_ext}"
            up_proof = _upload_to_storage_retry(
                p_buf,
                path=proof_rel_path,
                bucket=BUCKET_STAFF_PROOF,
                content_type=p_mime,
                make_public=True,
            )
            proof_url = (
                (up_proof.get("public_url") if isinstance(up_proof, dict) else None)
                or (up_proof.get("signed_url") if isinstance(up_proof, dict) else None)
            )
            if not proof_url:
                logger.error("Non-resident proof upload returned no usable URL: %s", proof_rel_path)
                flash_system_error(request, "Proof upload did not return a usable URL. Please try again.")
                return redirect(request.path)
    except Exception as e:
        logger.error("Admin Step3 upload failed: %s", e)
        flash_system_error(request, "Final upload failed.", exc=e)
        return redirect(request.path)

    # Resolve final URLs (ID images can remain public as you had them)
    front_url = (up_front.get("public_url") or up_front.get("signed_url"))
    back_url  = (up_back.get("public_url") or up_back.get("signed_url"))
    self_url  = (up_selfie.get("public_url") or up_selfie.get("signed_url"))

    # Generate credentials
    initials = _initials_from_name(
        first=personal.get("first_name"),
        middle=personal.get("middle_name"),
        last=personal.get("last_name"),
        suffix=personal.get("suffix"),
    )
    
    # Create staff directly
    try:
        result = Admin.insert_person_and_staff(
            p_added_by_id=staff_id,
            p_role_id=role_id,
            p_supporting_docs=([proof_url] if proof_url else None),
            p_first_name=personal.get("first_name"),
            p_last_name=personal.get("last_name"),
            p_birthdate=personal.get("birthdate"),
            p_email=personal.get("email"),
            p_mobile_num=personal.get("mobile_num"),
            p_sex_id=personal.get("sex_id"),
            p_civil_status_id=personal.get("civil_status_id"),
            p_nationality_id=personal.get("nationality_id"),
            p_religion_id=personal.get("religion_id"),
            p_city=personal.get("city"),
            p_barangay=personal.get("barangay"),
            p_sitio_purok=personal.get("purok_sitio"),
            p_street=personal.get("street"),
            p_valid_id_front=front_url,
            p_valid_id_back=back_url,
            p_valid_id_type_id=valid_id_type_id,
            p_selfie_path=self_url,
            p_lupon_sched=schedules if schedules else None,
            p_bhw_purok_ids=sorted(set(purok_ids)) if purok_ids else None,
            p_middle_name=(personal.get("middle_name") or "").strip() or None,
            p_suffix=(personal.get("suffix") or "").strip() or None,
        )
        
        new_staff_id = result.get("staff_id")
        
        # Get staff_code from database
        with connection.cursor() as cursor:
            cursor.execute("SELECT staff_code FROM staff WHERE staff_id = %s", [new_staff_id])
            code_row = cursor.fetchone()
            staff_code = code_row[0] if code_row else None
        
        if not new_staff_id or not staff_code:
            flash_warning(request, "Staff created but no identifier returned. Please verify in Staff List.")
            return redirect(request.path)
            
    except ValueError as e:
        error_msg = str(e)
        if "already exists" in error_msg.lower():
            flash_warning(request, "This person already exists in the system. Please check if they are already registered.")
        else:
            flash_warning(request, error_msg)
        return redirect(request.path)
    except (DatabaseError, OperationalError, IntegrityError) as e:
        logger.exception("DB error: insert_person_and_staff failed")
        flash_db_error(request, e)
        return redirect(request.path)
    except Exception as e:
        logger.exception("System error: insert_person_and_staff failed")
        flash_system_error(request, "Failed to create staff account.", exc=e)
        return redirect(request.path)

    # Generate and store credentials (same as process_staff_request)
    username = f"brgySN.{initials}{staff_code}"
    final_password = _rand_password(8)
    
    try:
        from captain.models import Captain
        ok_upsert = Captain.upsert_staff_credentials_and_log(
            p_staff_id=new_staff_id,
            p_username=username,
            p_password_plain=final_password,
            p_sender_staff_id=staff_id,
            p_is_credentials_sent=True,
        )
        
        if not ok_upsert:
            flash_warning(request, "Staff created but failed to store credentials. Please re-issue credentials.")
            return redirect(request.path)
            
    except (DatabaseError, OperationalError, IntegrityError) as e:
        flash_db_error(request, e)
        return redirect(request.path)
    except Exception as e:
        flash_system_error(request, "Failed to generate credentials.", exc=e)
        return redirect(request.path)

    # Send emails
    applicant_email = (personal.get("email") or "").strip()
    if applicant_email:
        # Validate email before sending
        is_valid, reason = verify_email_deliverable_abstract(applicant_email)
        if not is_valid:
            flash_warning(request, f"Staff account created successfully but email validation failed: {reason}. Credentials not sent.")
            applicant_email = None
    
    if applicant_email:
        try:
            role_label = None
            try:
                if role_id and hasattr(role_form, "fields") and "role" in role_form.fields:
                    role_label = _label_from_choices(role_form.fields["role"].choices, role_id)
            except Exception:
                role_label = None
            role_label = role_label or f"Role ID {role_id}" if role_id else "Staff"

            # Send account creation and credentials email
            subj = f"Barangay Sto. Niño Staff Account Created - {role_label}"
            body_txt = (
                f"Good day!\n\n"
                f"Your {role_label} staff account has been created successfully. "
                "Below are your login credentials:\n\n"
                f"Username: {username}\n"
                f"Temporary Password: {final_password}\n\n"
                "For your security, please sign in as soon as possible and change your password immediately.\n\n"
                "Thank you,\n"
                "Barangay Sto. Niño"
            )
            body_html = f"""
            <p>Good day!</p>
            <p>Your <strong>{role_label}</strong> staff account has been created successfully. Below are your login credentials:</p>
            <ul>
                <li><strong>Username:</strong> {username}</li>
                <li><strong>Temporary Password:</strong> {final_password}</li>
            </ul>
            <p>For your security, please sign in as soon as possible and change your password immediately.</p>
            <p>Thank you,<br>Barangay Sto. Niño</p>
            """.strip()

            resp = send_email(
                subject=subj,
                to=[applicant_email],
                body_text=body_txt,
                body_html=body_html,
                from_name="Barangay Sto. Niño",
                fail_silently=True,
            )
            
            if getattr(resp, "ok", False):
                flash_success(request, f"Staff account created successfully. Credentials sent to the receiver.")
            else:
                flash_warning(request, "Staff account created but failed to send credentials email.")
                
        except Exception as e:
            logger.warning("Failed to send credentials email to %s: %s", applicant_email, e)
            flash_warning(request, "Staff account created but failed to send credentials email.")
    else:
        flash_success(request, "Staff account created successfully. No email provided for credentials.")

    # Clean heavy previews
    try:
        if "docs" in wiz:
            for k in ("front_b64","back_b64","selfie_b64","proof_b64","front_preview","back_preview","selfie_preview","proof_preview"):
                wiz["docs"].pop(k, None)
            _wiz_set(request, "docs", wiz["docs"])
    except Exception:
        pass

    _wiz_clear(request)
    return redirect("staff_admin:staff_selection")

STAFF_FILTER_SESSION_KEY = "admin_staff_filters"
STAFF_REQ_FILTER_SESSION_KEY = "admin_staff_req_filters"

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_list(request: HttpRequest) -> HttpResponse:
    filters = request.session.get(STAFF_FILTER_SESSION_KEY, {}) or {}
    role_raw = (filters.get("role") or "").strip()
    acc_raw = (filters.get("account_stat") or "").strip()
    search_term = (filters.get("q") or "").strip()

    updated = False
    should_redirect = False

    if "clear_filters" in request.GET:
        role_raw = ""
        acc_raw = ""
        search_term = ""
        updated = True
        should_redirect = True

    remove_target = (request.GET.get("remove_filter") or "").strip()
    if remove_target:
        if remove_target == "role":
            role_raw = ""
        elif remove_target == "account_stat":
            acc_raw = ""
        elif remove_target == "search":
            search_term = ""
        updated = True
        should_redirect = True

    if "role" in request.GET:
        role_raw = (request.GET.get("role") or "").strip()
        updated = True
    if "account_stat" in request.GET:
        acc_raw = (request.GET.get("account_stat") or "").strip()
        updated = True
    if "q" in request.GET:
        search_term = (request.GET.get("q") or "").strip()
        updated = True
    if "search" in request.GET:
        search_term = (request.GET.get("search") or "").strip()
        updated = True

    filters_state = {
        "role": role_raw,
        "account_stat": acc_raw,
        "q": search_term,
    }
    if updated or STAFF_FILTER_SESSION_KEY not in request.session:
        request.session[STAFF_FILTER_SESSION_KEY] = filters_state
        request.session.modified = True

    if should_redirect:
        return redirect(request.path)

    role_id = int(role_raw) if role_raw.isdigit() else None
    acc_id = int(acc_raw) if acc_raw.isdigit() else None

    rows: List[Dict[str, Any]] = []
    try:
        if role_id is not None or acc_id is not None:
            rows = Secretary.filter_staff_by_role_and_account(role_id, acc_id) or []
            if search_term:
                term = search_term.lower()
                rows = [r for r in rows if term in (r.get("full_name") or "").lower()]
        elif search_term:
            rows = Secretary.search_staff_by_name(search_term) or []
        else:
            rows = Secretary.get_all_staff_info_summary() or []
    except Exception as e:
        logger.exception("Failed to load staff summaries: %s", e)
        rows = []

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

    form_initial = {
        "role": role_raw,
        "account_stat": acc_raw,
        "search": search_term,
    }
    form = StaffFilters(initial=form_initial)

    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(page_number)

    role_choices = {str(k): v for k, v in form.fields["role"].choices}
    acc_choices = {str(k): v for k, v in form.fields["account_stat"].choices}

    active_filters: List[Dict[str, str]] = []
    if role_raw:
        label = role_choices.get(role_raw) or f"Role {role_raw}"
        active_filters.append({
            "label": label,
            "remove_url": f"{request.path}?remove_filter=role",
        })
    if acc_raw:
        label = acc_choices.get(acc_raw) or f"Status {acc_raw}"
        active_filters.append({
            "label": label,
            "remove_url": f"{request.path}?remove_filter=account_stat",
        })
    if search_term:
        active_filters.append({
            "label": f"Search: \"{search_term}\"",
            "remove_url": f"{request.path}?remove_filter=search",
        })

    clear_filters_url = f"{request.path}?clear_filters=1"

    user_fullname, user_role, user_role_template = get_user_info(request)
    current_filters = filters_state

    return render(request, "staff_admin/staff/staff_list.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Account List",
        "page_title": "Staff Account List",
        "user_role_template": user_role_template,
        "form": form,
        "page_obj": page_obj,
        "total_count": paginator.count,
        "per_page": per_page,
        "active_filters": active_filters,
        "clear_filters_url": clear_filters_url,
        "current_filters": current_filters,
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_GET
def staff_search_api(request):
    raw_query = (request.GET.get("q") or "").strip()

    filters = request.session.get(STAFF_FILTER_SESSION_KEY, {}) or {}
    role_raw = (filters.get("role") or "").strip()
    acc_raw = (filters.get("account_stat") or "").strip()

    role_id = int(role_raw) if role_raw.isdigit() else None
    acc_id = int(acc_raw) if acc_raw.isdigit() else None

    try:
        if role_id is not None or acc_id is not None:
            rows = Secretary.filter_staff_by_role_and_account(role_id, acc_id) or []
        else:
            rows = Secretary.get_all_staff_info_summary() or []

        if raw_query:
            q_lower = raw_query.lower()
            rows = [r for r in rows if q_lower in (r.get("full_name") or "").lower()]

        filters.update({
            "role": role_raw,
            "account_stat": acc_raw,
            "q": raw_query,
        })
        request.session[STAFF_FILTER_SESSION_KEY] = filters
        request.session.modified = True

        return JsonResponse({"results": rows[:50]})
    except Exception as e:
        logger.exception("staff_search_api error: %s", e)
        return JsonResponse({"results": [], "error": "Search failed"}, status=500)

@session_login_required
@role_required(ADMIN_ROLE)
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
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_dets(request, staff_code: str):
    form = UpdateInfo()
    
    # Handle POST request for staff updates
    if request.method == "POST":
        auth = request.session.get("auth") or {}
        updated_by_staff_id = auth.get("staff_id")
        
        if not updated_by_staff_id:
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.path)
        
        try:
            # Get current staff data first
            rows = Secretary.get_staff_profile_display(staff_code) if staff_code else []
            current_staff = rows[0] if rows else None
            
            if not current_staff:
                flash_warning(request, "Staff not found.")
                return redirect("staff_admin:staff_list")
            
            staff_id = current_staff.get("staff_id")
            if not staff_id:
                flash_warning(request, "Staff ID not found.")
                return redirect("staff_admin:staff_list")
            
            # Handle personal information update
            if request.POST.get('action') == 'update_personal_info':
                from authentication.models import Authentication
                
                # Check if reason is provided
                reason = (request.POST.get('reason') or '').strip()
                if not reason:
                    flash_warning(request, "Please provide a reason for updating personal information.")
                    return redirect(request.path)
                
                # Extract only the fields that are in the modal
                first_name = (request.POST.get('first_name') or '').strip() or None
                middle_name = (request.POST.get('middle_name') or '').strip() or None
                last_name = (request.POST.get('last_name') or '').strip() or None
                suffix = (request.POST.get('suffix') or '').strip() or None
                birthdate = (request.POST.get('birthdate') or '').strip() or None
                sex_id = Authentication._to_int_or_none(request.POST.get('sex_id'))
                civil_status_id = Authentication._to_int_or_none(request.POST.get('civil_status_id'))
                nationality_id = Authentication._to_int_or_none(request.POST.get('nationality_id'))
                religion_id = Authentication._to_int_or_none(request.POST.get('religion_id'))
                mobile_num = (request.POST.get('mobile_number') or '').strip() or None
                
                # Address fields
                city = (request.POST.get('city') or '').strip() or None
                barangay = (request.POST.get('barangay') or '').strip() or None
                sitio_purok = (request.POST.get('sitio_purok') or '').strip() or None
                street = (request.POST.get('street') or '').strip() or None
                province = (request.POST.get('province') or '').strip() or None
                
                # Call the update function with only the fields in the modal
                result = Authentication.update_personal_information(
                    staff_id=staff_id,
                    updated_by_staff_id=updated_by_staff_id,
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    suffix=suffix,
                    birthdate=birthdate,
                    sex_id=sex_id,
                    civil_status_id=civil_status_id,
                    nationality_id=nationality_id,
                    religion_id=religion_id,
                    email=None,
                    mobile_number=mobile_num,
                    occupation=None,
                    monthly_income_id=None,
                    residential_status_id=None,
                    education_id=None,
                    employment_status_id=None,
                    is_student=None,
                    gov_mem_prog_ids=None,
                    city=city,
                    barangay=barangay,
                    sitio_purok=sitio_purok,
                    street=street,
                    province=province,
                    reason=f'Personal information update by admin: {reason}'
                )
                
                if result:
                    flash_success(request, 'Personal information updated successfully!')
                else:
                    flash_warning(request, 'No changes were made.')
                    
                return redirect(request.path)
            
            # Handle staff information update (existing functionality)
            # Extract form data
            role_id = _to_int_or_none(request.POST.get("role_id"))
            acc_status_id = _to_int_or_none(request.POST.get("acc_status_id"))
            username = (request.POST.get("username") or "").strip() or None
            password = (request.POST.get("password") or "").strip() or None
            email = (request.POST.get("email_address") or "").strip() or None
            
            # Validate email if provided
            if email:
                is_valid, reason = verify_email_deliverable_abstract(email)
                if not is_valid:
                    flash_warning(request, f"Email validation failed: {reason}. Please provide a valid email address.")
                    return redirect(request.path)
            
            # Extract purok IDs
            purok_ids = []
            for purok_id in request.POST.getlist("purok_ids[]"):
                if purok_id and purok_id.isdigit():
                    purok_ids.append(int(purok_id))
            
            # Extract schedules
            schedules_json = []
            days = request.POST.getlist("schedule_day[]")
            starts = request.POST.getlist("schedule_time_start[]")
            ends = request.POST.getlist("schedule_time_end[]")
            
            for i, day in enumerate(days):
                if day and day.isdigit() and i < len(starts) and i < len(ends):
                    start_time = starts[i].strip()
                    end_time = ends[i].strip()
                    if start_time and end_time:
                        schedules_json.append({
                            "day": int(day),
                            "time_start": start_time,
                            "time_end": end_time
                        })
            
            # Validate required fields
            if not role_id:
                flash_warning(request, "Role is required.")
                return redirect(request.path)
            
            if not acc_status_id:
                flash_warning(request, "Account status is required.")
                return redirect(request.path)
            
            # Get reason from form
            staff_reason = (request.POST.get("staff_reason") or "").strip()
            if not staff_reason:
                flash_warning(request, "Please provide a reason for updating staff information.")
                return redirect(request.path)
            
            # Call the database function
            logger.info("Updating staff %s with role_id=%s, acc_status_id=%s", staff_id, role_id, acc_status_id)
            result = Admin.update_staff_information(
                staff_id=staff_id,
                updated_by_staff_id=updated_by_staff_id,
                role_id=role_id,
                acc_status_id=acc_status_id,
                username=username,
                password=password,
                email=email,
                purok_ids=purok_ids if purok_ids else None,
                schedules_json=schedules_json if schedules_json else None,
                reason=staff_reason
            )
            
            logger.info("Update result: %s", result)
            if result:
                flash_success(request, "Staff information updated successfully.")
                # Fetch updated staff_code to handle cases where it changed due to role change
                try:
                    with connection.cursor() as cur:
                        cur.execute(
                            "SELECT staff_code FROM staff WHERE staff_id = %s",
                            [staff_id]
                        )
                        row = cur.fetchone()
                        new_staff_code = row[0] if row else None
                        
                    if new_staff_code and new_staff_code != staff_code:
                        logger.info("Staff code changed from %s to %s, redirecting to new URL", staff_code, new_staff_code)
                        from django.urls import reverse
                        new_url = reverse('staff_admin:staff_details', args=[new_staff_code])
                        return redirect(new_url)
                except Exception as e:
                    logger.warning("Could not fetch updated staff code: %s", e)
            else:
                flash_warning(request, "No changes were made.")
                
        except (DatabaseError, OperationalError, IntegrityError) as e:
            flash_db_error(request, e)
        except Exception as e:
            flash_system_error(request, "Failed to update staff information.", exc=e)
        
        # Clear any potential cache and redirect to same page
        logger.info("POST processing completed, redirecting to same page: %s", request.path)
        return redirect(request.path)
    
    # GET request handling
    logger.info("GET request for staff_code=%s", staff_code)
    try:
        rows = Secretary.get_staff_profile_display(staff_code) if staff_code else []
        logger.info("Retrieved %d rows for staff_code=%s", len(rows), staff_code)
        if not rows:
            logger.warning("No staff data found for staff_code=%s", staff_code)
    except Exception as e:
        logger.exception("get_staff_profile_display failed for staff_code=%s: %s", staff_code, e)
        rows = []

    p = rows[0] if rows else None
    
    if not p:
        logger.warning("No profile data found for staff_code=%s, redirecting to staff list", staff_code)
        flash_warning(request, f"Staff with code {staff_code} not found.")
        return redirect("staff_admin:staff_list")
    
    logger.info("Successfully loaded profile data for staff_code=%s", staff_code)
    
    # Use assigned_purok_ids directly from returned data
    purok_list = []
    if p:
        logger.debug("Profile data keys: %s", list(p.keys()) if p else None)
        logger.debug("assigned_purok_ids: %s", p.get('assigned_purok_ids'))
        
        purok_ids = p.get('assigned_purok_ids', [])
        if isinstance(purok_ids, list):
            purok_list = [str(pid) for pid in purok_ids if pid]
        elif purok_ids:
            purok_list = [str(purok_ids)]
        
        # Fallback: try to parse from assigned_purok text if no IDs
        if not purok_list and p.get('assigned_purok'):
            purok_text = str(p.get('assigned_purok', '')).strip()
            if purok_text:
                from .forms import PUROK_CHOICES
                purok_name_to_id = {label: str(value) for value, label in PUROK_CHOICES}
                purok_names = [item.strip() for item in purok_text.replace('\n', ',').split(',') if item.strip()]
                purok_list = [purok_name_to_id.get(name, '') for name in purok_names if purok_name_to_id.get(name)]
        
        logger.debug("Final purok_list: %s", purok_list)
    
    # Process schedule data
    schedule_list = []
    if p:
        schedule_day_ids = p.get('schedule_day_ids', [])
        schedule_time_start = p.get('schedule_time_start', [])
        schedule_time_end = p.get('schedule_time_end', [])
        
        if isinstance(schedule_day_ids, list) and isinstance(schedule_time_start, list) and isinstance(schedule_time_end, list):
            for i in range(len(schedule_day_ids)):
                if i < len(schedule_time_start) and i < len(schedule_time_end):
                    # Convert 12-hour format to 24-hour format for HTML time input
                    def convert_to_24h(time_str):
                        if not time_str:
                            return ''
                        try:
                            # Parse 12-hour format and convert to 24-hour
                            time_obj = datetime.strptime(time_str.strip(), '%I:%M %p')
                            return time_obj.strftime('%H:%M')
                        except ValueError:
                            try:
                                # Try without AM/PM (already 24-hour format)
                                time_obj = datetime.strptime(time_str.strip(), '%H:%M')
                                return time_obj.strftime('%H:%M')
                            except ValueError:
                                return time_str  # Return as-is if parsing fails
                    
                    schedule_list.append({
                        'day': str(schedule_day_ids[i]) if schedule_day_ids[i] else '',
                        'time_start': convert_to_24h(schedule_time_start[i]),
                        'time_end': convert_to_24h(schedule_time_end[i])
                    })
        
        logger.debug("Final schedule_list: %s", schedule_list)
    
    # Autofill update form with current data
    initial_data = {
        'assigned_purok': purok_list[0] if purok_list else '',
        'schedule': p.get('schedule', '') if p else '',
        'username': p.get('username', '') if p else '',
    }
    
    update_form = StaffUpdateForm(initial=initial_data)
    
    placeholder = static("images/brgy-sto-nino.png")
    def _img(v): return (v or "").strip() or placeholder

    doc_slides = []
    if p:
        doc_slides = [
            {"src": _img(p.get("valid_id_front_img_path")), "label": "Front of ID"},
            {"src": _img(p.get("valid_id_back_img_path")),  "label": "Back of ID"},
            {"src": _img(p.get("selfie_img_path")),         "label": "Selfie w/ ID"},
        ]

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/staff/person_dets.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Details : {staff_code}",
        "page_title": f"Staff Details : {staff_code}",
        "user_role_template": user_role_template,
        "profile": p,
        "doc_slides": doc_slides,
        "form": form,
        "update_form": update_form,
        "purok_list": purok_list,
        "schedule_list": schedule_list,
        "day_choices": DAY_CHOICES,
    })


@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_account_requests_list(request: HttpRequest) -> HttpResponse:
    filters = request.session.get(STAFF_REQ_FILTER_SESSION_KEY, {}) or {}
    role_raw = (filters.get("role") or "").strip()
    date_raw = (filters.get("date_submitted") or "").strip()
    status_raw = (filters.get("status") or "").strip()
    search_term = (filters.get("q") or "").strip()

    # Set default status to 30 if no status is set
    if not status_raw:
        status_raw = "30"

    updated = False
    should_redirect = False

    if "clear_filters" in request.GET:
        role_raw = ""
        date_raw = ""
        status_raw = ""  # Reset to ALL
        search_term = ""
        updated = True
        should_redirect = True

    remove_target = (request.GET.get("remove_filter") or "").strip()
    if remove_target:
        if remove_target == "role":
            role_raw = ""
        elif remove_target == "date_submitted":
            date_raw = ""
        elif remove_target == "status":
            status_raw = "30"  # Reset to default
        elif remove_target == "search":
            search_term = ""
        updated = True
        should_redirect = True

    if "role" in request.GET:
        role_raw = (request.GET.get("role") or "").strip()
        updated = True
    if "date_submitted" in request.GET:
        date_raw = (request.GET.get("date_submitted") or "").strip()
        updated = True
    if "status" in request.GET:
        status_raw = (request.GET.get("status") or "").strip()
        updated = True
    if "q" in request.GET:
        search_term = (request.GET.get("q") or "").strip()
        updated = True
    if "search" in request.GET:
        search_term = (request.GET.get("search") or "").strip()
        updated = True

    filters_state = {
        "role": role_raw,
        "date_submitted": date_raw,
        "status": status_raw,
        "q": search_term,
    }
    if updated or STAFF_REQ_FILTER_SESSION_KEY not in request.session:
        request.session[STAFF_REQ_FILTER_SESSION_KEY] = filters_state
        request.session.modified = True

    if should_redirect:
        return redirect(request.path)

    try:
        staff_req = Captain.list_requests() or []
    except Exception:
        logger.exception("Error loading staff requests")
        staff_req = []

    def get(row, key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    # Apply status filter
    filtered = []
    status_id = int(status_raw) if status_raw.isdigit() else None
    
    for r in staff_req:
        sid = get(r, "status_id") or get(r, "request_status_id")
        try:
            sid = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid = None
        
        # If status_raw is empty (ALL), show all requests
        if not status_raw or status_raw == "":
            filtered.append(r)
        # Otherwise filter by specific status ID
        elif status_id is not None and sid == status_id:
            filtered.append(r)

    # Apply filters
    if role_raw:
        role_id = int(role_raw) if role_raw.isdigit() else None
        if role_id:
            filtered = [r for r in filtered if get(r, "role_id") == role_id]

    if date_raw:
        from datetime import datetime
        try:
            target_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            target_date = None
        
        if target_date:
            date_filtered = []
            for r in filtered:
                date_val = get(r, "date_time_submitted")
                pretty_date = get(r, "date_time_submitted_pretty")
                found_match = False
                
                try:
                    # Check the main date field
                    if date_val and not found_match:
                        if hasattr(date_val, 'date'):
                            if date_val.date() == target_date:
                                found_match = True
                        elif hasattr(date_val, 'strftime'):
                            if date_val == target_date:
                                found_match = True
                        elif isinstance(date_val, str):
                            # Check for month name and day in the string
                            month_name = target_date.strftime("%B")
                            day_str = str(target_date.day)
                            year_str = str(target_date.year)
                            if month_name in date_val and day_str in date_val and year_str in date_val:
                                found_match = True
                    
                    # Also check the pretty formatted date
                    if pretty_date and isinstance(pretty_date, str) and not found_match:
                        month_name = target_date.strftime("%B")
                        day_str = str(target_date.day)
                        year_str = str(target_date.year)
                        if month_name in pretty_date and day_str in pretty_date and year_str in pretty_date:
                            found_match = True
                    
                    if found_match:
                        date_filtered.append(r)
                        
                except (ValueError, AttributeError, TypeError):
                    continue
            filtered = date_filtered

    if search_term:
        search_lower = search_term.lower()
        filtered = [r for r in filtered if search_lower in (get(r, "name") or "").lower()]

    try:
        per_page = int(request.GET.get("per_page") or 10)
        if per_page <= 0:
            per_page = 10
    except (TypeError, ValueError):
        per_page = 10

    form_initial = {
        "role": role_raw,
        "date_submitted": date_raw,
        "status": status_raw,
        "search": search_term,
    }
    form = StaffAccountRequestFilters(initial=form_initial)

    paginator = Paginator(filtered, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    role_choices = {str(k): v for k, v in form.fields["role"].choices}

    # Status choices for filter chips
    status_choices = {
        "30": "WAITING FOR ADMIN'S APPROVAL",
        "46": "WAITING FOR ID VALIDATION", 
        "29": "WAITING FOR BARANGAY CAPTAIN'S APPROVAL",
        "3": "APPROVED",
        "4": "REJECTED"
    }

    active_filters = []
    if role_raw:
        label = role_choices.get(role_raw) or f"Role {role_raw}"
        active_filters.append({
            "label": label,
            "remove_url": f"{request.path}?remove_filter=role",
        })
    if date_raw:
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_raw, "%Y-%m-%d")
            date_label = date_obj.strftime("%B %d, %Y")
        except ValueError:
            date_label = date_raw
        active_filters.append({
            "label": f"Date: {date_label}",
            "remove_url": f"{request.path}?remove_filter=date_submitted",
        })
    if status_raw == "":  # Show ALL as active filter when explicitly selected
        active_filters.append({
            "label": "ALL",
            "remove_url": f"{request.path}?remove_filter=status",
        })
    elif status_raw and status_raw != "30":  # Show other statuses except default
        label = status_choices.get(status_raw) or f"Status {status_raw}"
        active_filters.append({
            "label": label,
            "remove_url": f"{request.path}?remove_filter=status",
        })
    if search_term:
        active_filters.append({
            "label": f"Search: \"{search_term}\"",
            "remove_url": f"{request.path}?remove_filter=search",
        })

    clear_filters_url = f"{request.path}?clear_filters=1"

    current_filters = filters_state

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/staff/staff_account_req.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Account Requests",
        "page_title": "Staff Account Requests",
        "user_role_template": user_role_template,
        "form": form,
        "page_obj": page_obj,
        "staff_req": page_obj.object_list,
        "total_count": paginator.count,
        "per_page": per_page,
        "active_filters": active_filters,
        "clear_filters_url": clear_filters_url,
        "current_filters": current_filters,
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET"])
def pending_staff_dets(request, p_staff_acc_req_id: str):
    try:
        rows = Captain.get_pending_staff_details(p_staff_acc_req_id) if p_staff_acc_req_id else []
    except Exception:
        logger.exception("get_pending_staff_details failed for staff_code=%s", p_staff_acc_req_id)
        rows = []

    # Get status history
    status_history = []
    try:
        from staff_admin.models import Admin
        status_history = Admin.get_staff_acc_req_status_history(int(p_staff_acc_req_id)) if p_staff_acc_req_id else []
    except Exception:
        logger.exception("get_staff_acc_req_status_history failed for req_id=%s", p_staff_acc_req_id)
        status_history = []

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

    user_fullname, user_role, user_role_template = get_user_info(request)
    ctx = {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Details : {p_staff_acc_req_id}",
        "page_title": f"Staff Details : {p_staff_acc_req_id}",
        "user_role_template": user_role_template,
        "profile": p,
        "doc_slides": doc_slides,
        "staff_acc_req_id": p_staff_acc_req_id,
        "status_history": status_history,
    }
    return render(request, "staff_admin/staff/pending_staff_dets.html", ctx)

def _rand_password(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def _initials_from_name(first: str, middle: Optional[str], last: str, suffix: Optional[str]) -> str:
    def fch(s: Optional[str]) -> str:
        s = (s or "").strip()
        return s[0] if s else ""
    def clean_suffix(s: Optional[str]) -> str:
        s = (s or "").strip()
        s = re.sub(r"[^\w]+", "", s)
        return s
    parts = [
        fch(first),
        fch(middle),
        fch(last),
        clean_suffix(suffix),
    ]
    return "".join(p for p in parts if p).lower()

def _get_staff_by_code(staff_code: str) -> Optional[dict]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   p.email,
                   p.first_name,
                   p.middle_name,
                   p.last_name,
                   p.suffix
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            WHERE s.staff_code = %s
            """,
            [staff_code],
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "staff_id": row[0],
            "email": row[1],
            "first_name": row[2],
            "middle_name": row[3],
            "last_name": row[4],
            "suffix": row[5],
        }

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["POST"])
def process_staff_request(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth") or {}
    approver_id = auth.get("staff_id")
    
    if not approver_id:
        flash_system_error(request, "Your session is missing staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")
    
    try:
        approver_id = int(approver_id)
    except (TypeError, ValueError):
        flash_system_error(request, "Invalid staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")

    # Get staff account request ID
    staff_acc_req_id_raw = (
        request.POST.get("staff_acc_req_id") or 
        request.POST.get("id")
    )
    
    if not staff_acc_req_id_raw:
        flash_warning(request, "Missing staff account request ID.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")
    
    try:
        staff_acc_req_id = int(staff_acc_req_id_raw)
    except (TypeError, ValueError):
        flash_warning(request, "Invalid staff account request ID.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")

    # Get decision status
    status_raw = request.POST.get("p_request_status_id")
    if not status_raw:
        flash_warning(request, "Missing decision status.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")
    
    try:
        status_id = int(status_raw)
    except (TypeError, ValueError):
        flash_warning(request, "Invalid decision status.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")
    
    if status_id not in (REQUEST_STATUS_APPROVED, REQUEST_STATUS_REJECTED):
        flash_warning(request, "Invalid decision status.")
        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")

    remarks = (request.POST.get("remarks") or "").strip() or None
    email_from_form = (request.POST.get("email") or "").strip()
    
    # Validate email if provided
    if email_from_form:
        is_valid, reason = verify_email_deliverable_abstract(email_from_form)
        if not is_valid:
            flash_warning(request, f"Email validation failed: {reason}. Request will be processed but email notifications may not be sent.")
            email_from_form = ""

    try:
        result_text = Captain.process_staff_account_request(
            p_staff_acc_req_id=staff_acc_req_id,
            p_approver_id=approver_id,
            p_request_status_id=status_id,
            p_remarks=remarks,
        )

        # Get role information for email
        role_label = None
        try:
            _rows = Captain.get_pending_staff_details(staff_acc_req_id) or []
            _req = _rows[0] if _rows else {}
            role_label = (_req.get("role_name") or _req.get("role") or _req.get("role_label"))
        except Exception:
            role_label = None

        if status_id == REQUEST_STATUS_REJECTED:
            # Send rejection email if email provided
            if email_from_form:
                try:
                    rl = role_label or "staff"
                    reason = remarks or "No specific reason was provided."
                    send_email(
                        subject="Staff Account Request Rejected",
                        to=[email_from_form],
                        body_text=f"Good day!\n\nYour {rl} staff account creation request has been REJECTED.\n\nReason: {reason}\n\nPlease contact the authorized staff if you have any concern.\n\nBarangay Sto. Niño",
                        body_html=f"<p>Good day!</p><p>Your <strong>{rl}</strong> staff account creation request has been <strong>REJECTED</strong>.</p><p><strong>Reason:</strong> {reason}</p><p>Please contact the authorized staff if you have any concern.</p><p>Barangay Sto. Niño</p>",
                        from_name="Barangay Sto. Niño",
                        fail_silently=True,
                    )
                except Exception as e:
                    logger.warning("Failed to send rejection email: %s", e)
            
            flash_success(request, "Staff account request rejected.")
        
        elif status_id == REQUEST_STATUS_APPROVED:
            if result_text == "TRUE":
                # This shouldn't happen for admin, but handle it
                flash_success(request, "Request processed successfully.")
            
            elif result_text and result_text.strip():
                # Final approval with staff code - create credentials
                staff_code = result_text.strip()
                
                try:
                    staff_row = _get_staff_by_code(staff_code)
                    if not staff_row:
                        flash_warning(request, f"Approved (staff_code={staff_code}), but staff record could not be found.")
                        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")

                    staff_id = staff_row["staff_id"]
                    initials = _initials_from_name(
                        first=staff_row["first_name"],
                        middle=staff_row["middle_name"],
                        last=staff_row["last_name"],
                        suffix=staff_row["suffix"],
                    )
                    username = f"brgySN.{initials}{staff_code}"
                    temp_password = _rand_password(8)

                    email_to = email_from_form or (staff_row.get("email") or "").strip()
                    
                    # Validate email if provided
                    if email_to:
                        is_valid, reason = verify_email_deliverable_abstract(email_to)
                        if not is_valid:
                            flash_warning(request, f"Email validation failed: {reason}. Staff approved but credentials email not sent.")
                            email_to = None
                    
                    sent_flag = bool(email_to)

                    ok_upsert = Captain.upsert_staff_credentials_and_log(
                        p_staff_id=staff_id,
                        p_username=username,
                        p_password_plain=temp_password,
                        p_sender_staff_id=approver_id,
                        p_is_credentials_sent=sent_flag,
                    )
                    
                    if not ok_upsert:
                        flash_warning(request, "Approved, but failed to create credentials. Please try again.")
                        return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")

                    # Send credentials email
                    if email_to:
                        try:
                            rl = role_label or "staff"
                            send_email(
                                subject="Barangay Sto. Niño Staff Account Approved",
                                to=[email_to],
                                body_text=f"Good day!\n\nYour {rl} staff account request has been approved. Below are your login credentials:\n\nUsername: {username}\nTemporary Password: {temp_password}\n\nFor your security, please sign in as soon as possible and change your password immediately.\n\nThank you,\nBarangay Sto. Niño",
                                body_html=f"<p>Good day!</p><p>Your <strong>{rl}</strong> staff account request has been approved. Below are your login credentials:</p><ul><li><strong>Username:</strong> {username}</li><li><strong>Temporary Password:</strong> {temp_password}</li></ul><p>For your security, please sign in as soon as possible and change your password immediately.</p><p>Thank you,<br>Barangay Sto. Niño</p>",
                                from_name="Barangay Sto. Niño",
                                fail_silently=True,
                            )
                            flash_success(request, f"Staff account approved. Credentials sent to {email_to}.")
                        except Exception as e:
                            logger.warning("Failed to send credentials email: %s", e)
                            flash_warning(request, "Staff approved and credentials created, but email sending failed.")
                    else:
                        flash_success(request, "Staff account approved and credentials created.")
                        
                except Exception as e:
                    logger.exception("Error creating credentials for approved staff: %s", e)
                    flash_warning(request, "Staff approved but there was an error creating credentials.")
            
            else:
                flash_warning(request, "Request processed but no confirmation received. Please verify the status.")

        logger.info(
            "process_staff_request completed: req_id=%s approver_id=%s status=%s result=%s",
            staff_acc_req_id, approver_id, status_id, result_text
        )

    except DatabaseError as db_err:
        logger.exception("Database error processing staff request (req_id=%s)", staff_acc_req_id)
        flash_db_error(request, db_err)
    except Exception as ex:
        logger.exception("Unexpected error processing staff request (req_id=%s)", staff_acc_req_id)
        flash_system_error(request, "Unable to process the request.", exc=ex)
    
    return redirect(request.META.get("HTTP_REFERER") or "staff_admin:staff_account_requests_list")

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def all_staff_requests_list(request: HttpRequest) -> HttpResponse:
    """View all staff account requests in the system"""
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    role_filter = request.GET.get('role', '').strip()
    date_filter = request.GET.get('date_submitted', '').strip()
    
    try:
        requests = Admin.get_staff_account_req_list_by_all()
        stats_data = Admin.get_staff_request_statistics()
        stats = stats_data[0] if stats_data else {
            'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0
        }
    except Exception as e:
        logger.exception("Error loading all requests")
        flash_system_error(request, "Failed to load requests.")
        requests = []
        stats = {'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0}
    
    filtered_requests = requests
    
    if search_query:
        search_lower = search_query.lower()
        filtered_requests = [r for r in filtered_requests if search_lower in (r.get('name') or '').lower()]
    
    if status_filter:
        filtered_requests = [r for r in filtered_requests if str(r.get('status_id', '')) == status_filter]
    
    if role_filter:
        filtered_requests = [r for r in filtered_requests if str(r.get('role_id', '')) == role_filter]
    
    if date_filter:
        from datetime import datetime
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            date_filtered = []
            for r in filtered_requests:
                pretty_date = r.get('date_time_submitted_pretty')
                if pretty_date and isinstance(pretty_date, str):
                    try:
                        date_part = ' '.join(pretty_date.split()[:3])
                        parsed_date = datetime.strptime(date_part, "%B %d, %Y").date()
                        if parsed_date == target_date:
                            date_filtered.append(r)
                    except (ValueError, IndexError):
                        continue
            filtered_requests = date_filtered
        except ValueError:
            pass
    
    from django.core.paginator import Paginator
    paginator = Paginator(filtered_requests, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "staff_admin/requests_list.html", {
        'page_obj': page_obj,
        'requests': filtered_requests,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'date_filter': date_filter,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'user_role_template': user_role_template,
        'page_path': f"{user_role} / All Staff Requests",
        'page_title': 'All Staff Requests',
        'show_requester': True,  # Show requester column for all requests view
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_requests_list(request: HttpRequest) -> HttpResponse:
    """View staff account requests submitted by this admin"""
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    role_filter = request.GET.get('role', '').strip()
    date_filter = request.GET.get('date_submitted', '').strip()
    
    try:
        requests = Admin.get_staff_account_req_list_by_requester(staff_id)
        stats_data = Admin.get_staff_request_statistics_by_requester(staff_id)
        stats = stats_data[0] if stats_data else {
            'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0
        }
    except Exception as e:
        logger.exception("Error loading requests")
        flash_system_error(request, "Failed to load requests.")
        requests = []
        stats = {'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0}
    
    filtered_requests = requests
    
    if search_query:
        search_lower = search_query.lower()
        filtered_requests = [r for r in filtered_requests if search_lower in (r.get('name') or '').lower()]
    
    if status_filter:
        filtered_requests = [r for r in filtered_requests if str(r.get('status_id', '')) == status_filter]
    
    if role_filter:
        filtered_requests = [r for r in filtered_requests if str(r.get('role_id', '')) == role_filter]
    
    if date_filter:
        from datetime import datetime
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            date_filtered = []
            for r in filtered_requests:
                pretty_date = r.get('date_time_submitted_pretty')
                if pretty_date and isinstance(pretty_date, str):
                    try:
                        date_part = ' '.join(pretty_date.split()[:3])
                        parsed_date = datetime.strptime(date_part, "%B %d, %Y").date()
                        if parsed_date == target_date:
                            date_filtered.append(r)
                    except (ValueError, IndexError):
                        continue
            filtered_requests = date_filtered
        except ValueError:
            pass
    
    from django.core.paginator import Paginator
    paginator = Paginator(filtered_requests, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "staff_admin/requests_list.html", {
        'page_obj': page_obj,
        'requests': filtered_requests,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'date_filter': date_filter,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'user_role_template': user_role_template,
        'page_path': f"{user_role} / My Requests",
        'page_title': 'My Staff Requests',
        'show_requester': False,  # Don't show requester column for personal requests
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_request_detail(request: HttpRequest, request_id: int) -> HttpResponse:
    """View detailed information about a specific staff request"""
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    try:
        details_data = Admin.get_staff_acc_req_profile_progress(request_id)
        history = Admin.get_staff_acc_req_status_history(request_id)
        
        if not details_data:
            flash_warning(request, "Request not found.")
            return redirect('staff_admin:staff_requests_list')
        
        request_detail = details_data[0]
        
    except Exception as e:
        logger.exception(f"Error loading request {request_id}")
        flash_system_error(request, "Failed to load request details.")
        return redirect('staff_admin:staff_requests_list')
    
    return render(request, "staff_admin/request_detail.html", {
        'request': request_detail,
        'history': history,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'user_role_template': user_role_template,
        'page_path': f"{user_role} / My Requests / Details",
        'page_title': f"Request Details - {request_detail.get('full_name', 'Unknown')}",
    })

ACCESS_LOG_FILTER_SESSION_KEY = "admin_access_log_filters"

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def access_logs(request):
    from .forms import AccessLogFilters
    
    filters = request.session.get(ACCESS_LOG_FILTER_SESSION_KEY, {}) or {}
    role_raw = (filters.get("role") or "").strip()
    login_status_raw = (filters.get("login_status") or "").strip()
    search_term = (filters.get("q") or "").strip()

    updated = False
    should_redirect = False

    if "clear_filters" in request.GET:
        role_raw = ""
        login_status_raw = ""
        search_term = ""
        updated = True
        should_redirect = True

    remove_target = (request.GET.get("remove_filter") or "").strip()
    if remove_target:
        if remove_target == "role":
            role_raw = ""
        elif remove_target == "login_status":
            login_status_raw = ""
        elif remove_target == "search":
            search_term = ""
        updated = True
        should_redirect = True

    if "role" in request.GET:
        role_raw = (request.GET.get("role") or "").strip()
        updated = True
    if "login_status" in request.GET:
        login_status_raw = (request.GET.get("login_status") or "").strip()
        updated = True
    if "q" in request.GET:
        search_term = (request.GET.get("q") or "").strip()
        updated = True

    filters_state = {
        "role": role_raw,
        "login_status": login_status_raw,
        "q": search_term,
    }
    if updated or ACCESS_LOG_FILTER_SESSION_KEY not in request.session:
        request.session[ACCESS_LOG_FILTER_SESSION_KEY] = filters_state
        request.session.modified = True

    if should_redirect:
        return redirect(request.path)

    # Get login logs from database (grouped by staff)
    try:
        rows = Admin.get_login_logs_grouped_by_staff()
    except Exception as e:
        logger.exception("Failed to load access logs: %s", e)
        rows = []

    # Apply filters
    filtered = rows
    
    if role_raw and role_raw != "all":
        try:
            role_id = int(role_raw)
            filtered = [r for r in filtered if r.get("role_id") == role_id]
        except ValueError:
            pass
    
    if login_status_raw:
        if login_status_raw == "active":
            filtered = [r for r in filtered if r.get("active_sessions", 0) > 0]
        elif login_status_raw == "inactive":
            filtered = [r for r in filtered if r.get("active_sessions", 0) == 0]

    if search_term:
        search_lower = search_term.lower()
        filtered = [r for r in filtered if search_lower in (r.get("user_name") or "").lower() or search_lower in (r.get("role_name") or "").lower()]

    try:
        per_page = int(request.GET.get("per_page") or 10)
        if per_page <= 0:
            per_page = 10
    except ValueError:
        per_page = 10

    form_initial = {
        "role": role_raw,
        "login_status": login_status_raw,
        "search": search_term,
    }
    form = AccessLogFilters(initial=form_initial)

    paginator = Paginator(filtered, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Build active filters
    active_filters = []
    if role_raw and role_raw != "all":
        # Find role name from ROLE_CHOICES
        role_name = "Unknown Role"
        try:
            role_id = int(role_raw)
            from .forms import ROLE_CHOICES
            for choice_id, choice_name in ROLE_CHOICES:
                if choice_id == role_id:
                    role_name = choice_name
                    break
        except ValueError:
            pass
        active_filters.append({
            "label": f"Role: {role_name}",
            "remove_url": f"{request.path}?remove_filter=role",
        })
    if login_status_raw:
        status_label = "Active" if login_status_raw == "active" else "Inactive" if login_status_raw == "inactive" else login_status_raw
        active_filters.append({
            "label": f"Status: {status_label}",
            "remove_url": f"{request.path}?remove_filter=login_status",
        })
    if search_term:
        active_filters.append({
            "label": f"Search: \"{search_term}\"",
            "remove_url": f"{request.path}?remove_filter=search",
        })

    clear_filters_url = f"{request.path}?clear_filters=1"
    current_filters = filters_state

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/user_logs/access_logs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Access Logs',
        'page_title': 'Access Logs',
        'user_role_template': user_role_template,
        'form': form,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'per_page': per_page,
        'active_filters': active_filters,
        'clear_filters_url': clear_filters_url,
        'current_filters': current_filters,
    })

OPERATIONAL_LOG_FILTER_SESSION_KEY = "admin_operational_log_filters"

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def operational_logs(request):
    filters = request.session.get(OPERATIONAL_LOG_FILTER_SESSION_KEY, {}) or {}
    user_type_raw = (filters.get("user_type") or "").strip()
    action_raw = (filters.get("action") or "").strip()
    subsystem_raw = (filters.get("subsystem") or "").strip()
    date_from_raw = (filters.get("date_from") or "").strip()
    date_to_raw = (filters.get("date_to") or "").strip()
    search_term = (filters.get("q") or "").strip()

    updated = False
    should_redirect = False

    if "clear_filters" in request.GET:
        user_type_raw = ""
        action_raw = ""
        subsystem_raw = ""
        date_from_raw = ""
        date_to_raw = ""
        search_term = ""
        updated = True
        should_redirect = True

    remove_target = (request.GET.get("remove_filter") or "").strip()
    if remove_target:
        if remove_target == "user_type":
            user_type_raw = ""
        elif remove_target == "action":
            action_raw = ""
        elif remove_target == "subsystem":
            subsystem_raw = ""
        elif remove_target == "date_from":
            date_from_raw = ""
        elif remove_target == "date_to":
            date_to_raw = ""
        elif remove_target == "search":
            search_term = ""
        updated = True
        should_redirect = True

    if "user_type" in request.GET:
        user_type_raw = (request.GET.get("user_type") or "").strip()
        updated = True
    if "action" in request.GET:
        action_raw = (request.GET.get("action") or "").strip()
        updated = True
    if "subsystem" in request.GET:
        subsystem_raw = (request.GET.get("subsystem") or "").strip()
        updated = True
    if "date_from" in request.GET:
        date_from_raw = (request.GET.get("date_from") or "").strip()
        updated = True
    if "date_to" in request.GET:
        date_to_raw = (request.GET.get("date_to") or "").strip()
        updated = True
    if "q" in request.GET:
        search_term = (request.GET.get("q") or "").strip()
        updated = True

    filters_state = {
        "user_type": user_type_raw,
        "action": action_raw,
        "subsystem": subsystem_raw,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "q": search_term,
    }
    if updated or OPERATIONAL_LOG_FILTER_SESSION_KEY not in request.session:
        request.session[OPERATIONAL_LOG_FILTER_SESSION_KEY] = filters_state
        request.session.modified = True

    if should_redirect:
        return redirect(request.path)

    # Get operational logs from database
    try:
        rows = Admin.get_common_logs_with_names()
    except Exception as e:
        logger.exception("Failed to load operational logs: %s", e)
        rows = []

    # Apply filters
    filtered = rows
    
    if user_type_raw and user_type_raw != "all":
        filtered = [r for r in filtered if (r.get("user_type_name") or "").lower() == user_type_raw.lower()]
    
    if action_raw and action_raw != "all":
        filtered = [r for r in filtered if r.get("action") == action_raw]
    
    if subsystem_raw and subsystem_raw != "all":
        try:
            subsystem_id = int(subsystem_raw)
            filtered = [r for r in filtered if r.get("subsystem_id") == subsystem_id]
        except ValueError:
            pass
    
    if date_from_raw:
        from datetime import datetime
        try:
            date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date()
            filtered = [r for r in filtered if r.get("date_time") and r["date_time"].date() >= date_from]
        except ValueError:
            pass

    if date_to_raw:
        from datetime import datetime
        try:
            date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date()
            filtered = [r for r in filtered if r.get("date_time") and r["date_time"].date() <= date_to]
        except ValueError:
            pass

    if search_term:
        search_lower = search_term.lower()
        filtered = [r for r in filtered if 
                   search_lower in (r.get("performer_name") or "").lower() or 
                   search_lower in (r.get("action") or "").lower() or 
                   search_lower in (r.get("details") or "").lower()]

    try:
        per_page = int(request.GET.get("per_page") or 10)
        if per_page <= 0:
            per_page = 10
    except ValueError:
        per_page = 10

    paginator = Paginator(filtered, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Build active filters
    active_filters = []
    if user_type_raw and user_type_raw != "all":
        active_filters.append({
            "label": f"User Type: {user_type_raw.title()}",
            "remove_url": f"{request.path}?remove_filter=user_type",
        })
    if action_raw and action_raw != "all":
        active_filters.append({
            "label": f"Action: {action_raw}",
            "remove_url": f"{request.path}?remove_filter=action",
        })
    if subsystem_raw and subsystem_raw != "all":
        # Find subsystem name
        subsystem_name = "Unknown Subsystem"
        try:
            subsystem_id = int(subsystem_raw)
            for r in rows:
                if r.get("subsystem_id") == subsystem_id:
                    subsystem_name = r.get("subsystem_name") or f"Subsystem {subsystem_id}"
                    break
        except ValueError:
            pass
        active_filters.append({
            "label": f"Subsystem: {subsystem_name}",
            "remove_url": f"{request.path}?remove_filter=subsystem",
        })
    if date_from_raw:
        active_filters.append({
            "label": f"From: {date_from_raw}",
            "remove_url": f"{request.path}?remove_filter=date_from",
        })
    if date_to_raw:
        active_filters.append({
            "label": f"To: {date_to_raw}",
            "remove_url": f"{request.path}?remove_filter=date_to",
        })
    if search_term:
        active_filters.append({
            "label": f"Search: \"{search_term}\"",
            "remove_url": f"{request.path}?remove_filter=search",
        })

    clear_filters_url = f"{request.path}?clear_filters=1"
    current_filters = filters_state

    # Get unique subsystems for filter dropdown
    subsystems = []
    seen_subsystems = set()
    for r in rows:
        subsystem_id = r.get("subsystem_id")
        subsystem_name = r.get("subsystem_name")
        if subsystem_id and subsystem_name and subsystem_id not in seen_subsystems:
            subsystems.append({"id": subsystem_id, "name": subsystem_name})
            seen_subsystems.add(subsystem_id)

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/user_logs/operational_logs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Operational Logs',
        'page_title': 'Operational Logs',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'per_page': per_page,
        'active_filters': active_filters,
        'clear_filters_url': clear_filters_url,
        'current_filters': current_filters,
        'subsystems': subsystems,
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def access_log_details(request, log_id):
    try:
        # Use the new function to get all logs for the specific staff
        rows = Admin.get_login_logs_with_status_for_staff(int(log_id))
    except Exception as e:
        logger.exception("Failed to load access log details: %s", e)
        rows = []

    if not rows:
        flash_warning(request, f"No access logs found for staff ID {log_id}.")
        return redirect("staff_admin:access_logs")

    # Add pagination
    try:
        per_page = int(request.GET.get("per_page") or 15)
        if per_page <= 0:
            per_page = 15
    except ValueError:
        per_page = 15

    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/user_logs/access_log_details.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Access Log Details',
        'page_title': 'Access Log Details',
        'user_role_template': user_role_template,
        'logs': rows,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'per_page': per_page,
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def operational_log_details(request, log_id):
    try:
        log_detail = Admin.get_common_log_detail(int(log_id))
    except Exception as e:
        logger.exception("Failed to load operational log details: %s", e)
        log_detail = None

    if not log_detail:
        flash_warning(request, f"No operational log found with ID {log_id}.")
        return redirect("staff_admin:operational_logs")

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "staff_admin/user_logs/operational_log_details.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Operational Log Details',
        'page_title': 'Operational Log Details',
        'user_role_template': user_role_template,
        'log_detail': log_detail,
    })