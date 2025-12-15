# secretary/views.py
from __future__ import annotations
from django.templatetags.static import static

import os
os.environ.setdefault("HTTPX_DISABLE_HTTP2", "1")

import io
import logging
from uuid import uuid4
from datetime import datetime, time as dtime, date
from dateutil.relativedelta import relativedelta
import logging
log = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional
from django.urls import reverse

from django.conf import settings
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.db import connection
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
from src.app.contracts.resident_service_contract import ( 
    IResidentService,
)
from common.logging_utils import (
    log_announcement_action
)
from src.app.transfer_objects.commands.announcement_cmd import (
    CreateAnnouncementDraftCMD,
)
from src.app.contracts.announcement_service_contract import (
    IAnnouncementService,
)
from src.app.contracts.audience_service_contract import (
    IAudienceService,
)
from src.app.transfer_objects.commands.audience_cmd import (
    AddAnnouncementAudienceCMD
)
from src.app.contracts.channel_service_contract import (
    IChannelService,
)
from src.app.transfer_objects.commands.channel_cmd import (
    UpsertAnnouncementChannelsCMD,
    CreateAnnouncementRecipientsCMD
)
from src.app.transfer_objects.commands.publish_now_cmd import PublishAnnouncementNowCMD
from src.app.transfer_objects.commands.schedule_cmd import ScheduleAnnouncementCMD


from .forms import (
    StaffFilters,
    StaffAccountRequestFilters,
    BusinessFilters,
    HouseholdFilters,
    AnnouncementDraftForm,
    DraftListSearch,
    ResidentFilters,
    AudienceScope,
    AddChannelForm,
    FamilyFilters,
)


from common.supabase_client import supabase
from common.services.storage import upload_to_storage

from secretary.models import Secretary
from .forms import ResidentProfileform, ChooseRole, StaffFilters, Schedule

from common.flash import flash_success, flash_warning, flash_db_error, flash_system_error
from common.email_validator import verify_email_deliverable_abstract
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
STAFF_FILTER_SESSION_KEY = "secretary_staff_filters"
STAFF_REQ_FILTER_SESSION_KEY = "secretary_staff_req_filters"

SECRETARY_ROLE = "Barangay Secretary"

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

BUCKET_FINAL = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
BUCKET_STAFF_PROOF = getattr(settings, "SUPABASE_STAFF_PROOF_BUCKET", "staff-proof")

# ─────────────────────────────
# Helpers
# ─────────────────────────────

from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
import json

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
import base64 as b64

def _bytes_to_data_url(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{b64.b64encode(b).decode('ascii')}"

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

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject 
def dashboard(
    request: HttpRequest,
    secretary_dashboard_service=Provide[AppContainer.secretary_dashboard_service],
):

    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    person_id = auth.get('person_id')

    kpis = {
        "ongoing_cases": 0,
        "open_cases": None,
        "active_businesses": 0,
        "new_businesses_week": None,
        "residents_total": 0,
        "new_residents_month": None,
    }

    dashboard_json = None
    announcements = []

    try:
        payload = secretary_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json")
    except Exception as exc:
        print("Error fetching secretary dashboard KPIs:", exc)
    
    if person_id:
        try:
            from authentication.announcement_views import get_user_announcements
            announcements = get_user_announcements(person_id)
        except Exception as exc:
            print(f"Error fetching announcements for person {person_id}:", exc)

    return render(request, "secretary/dashboard.html", {
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'kpis': kpis,
        'dashboard_json': dashboard_json,
        'today': datetime.now().strftime("%B %d, %Y"),
        'announcements': announcements,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_selection(request: HttpRequest) -> HttpResponse:
    user_fullname, user_role, user_role_template = get_user_info(request)
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
    
    # --- Collect multiple roles from chips
    role_ids: List[int] = []
    for x in request.POST.getlist("role_ids[]"):
        x = (x or "").strip()
        if x.isdigit():
            role_ids.append(int(x))
    role_ids = sorted(set(role_ids))  # Remove duplicates
    
    # For backward compatibility, use first role as primary
    role_id = role_ids[0] if role_ids else None

    # --- Collect multiple proof files
    proof_files = []
    proof_urls = []
    
    # Handle data URLs from chips (base64 encoded files)
    for proof_data in request.POST.getlist("proof_files[]"):
        if proof_data and proof_data.startswith("data:"):
            proof_urls.append(proof_data)
    
    # Primary proof file (fallback for direct upload)
    if hasattr(request, "FILES"):
        primary_proof = (
            request.FILES.get("proof")
            or request.FILES.get("proof_file")
            or None
        )
        if primary_proof:
            proof_files.append(primary_proof)
        
        # Additional proof files (if any direct uploads)
        for proof_file in request.FILES.getlist("proof_files[]"):
            if proof_file:
                proof_files.append(proof_file)

    # Handle other proof URLs
    primary_proof_url = (request.POST.get("proof") or "").strip() or None
    if primary_proof_url and primary_proof_url.startswith(("http://", "https://")):
        proof_urls.append(primary_proof_url)
    elif primary_proof_url and primary_proof_url.startswith("data:"):
        proof_urls.append(primary_proof_url)
    elif primary_proof_url:
        logger.warning("Ignoring non-URL, non-data proof value: %r", primary_proof_url)

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
        logger.debug("POST ▶ pid=%s role_ids=%s staff_id=%s purok_ids=%s schedules=%s proof_files=%d proof_urls=%d",
                     pid, role_ids, staff_id, purok_ids, schedules, len(proof_files), len(proof_urls))

    if request.method == "POST" and pid:
        if not (pid or role_ids or proof_files or proof_urls or base_purok
                or request.POST.getlist("purok_sitio_ids[]")
                or request.POST.get("day") or request.POST.getlist("day[]")):
            flash_warning(request, "Please select a resident and fill out the form before submitting.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not staff_id:
            logger.error("Validation ✗ Missing staff_id")
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not role_ids:
            logger.error("Validation ✗ No roles selected")
            flash_warning(request, "Please choose at least one staff role.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # Check BHW requirements for any BHW role
        if ROLE_BHW in role_ids and len(purok_ids) < 1:
            logger.error("Validation ✗ BHW requires ≥1 purok")
            flash_warning(request, "BHW must be assigned to at least one Purok/Sitio.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # Check Lupon requirements for any Lupon role
        if ROLE_LUPON in role_ids and len(schedules) < 1:
            logger.error("Validation ✗ Lupon requires ≥1 schedule")
            flash_warning(request, "Lupon Member must have at least one schedule.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # Validate purok duplicates for BHW
        if ROLE_BHW in role_ids:
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

        # Validate schedule duplicates for Lupon
        if ROLE_LUPON in role_ids and schedules:
            _days = [s["day"] for s in schedules]
            if len(_days) != len(set(_days)):
                logger.error("Validation ✗ Duplicate day selections in schedule are not allowed: %s", _days)
                flash_warning(request, "Duplicate day selections in schedule are not allowed.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not (proof_files or proof_urls):
            flash_warning(request, "Please attach at least one proof of employment.")
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

        # Upload multiple proof files
        uploaded_proof_urls = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Process file uploads
        for i, proof_file in enumerate(proof_files):
            try:
                buf, mime, ext = _prep_image_for_upload(proof_file)
                proof_rel_path = f"{final_base}/staff-app-proof-{role_id}-{timestamp}-{i+1}.{ext}"
                res_up = _upload_to_storage_retry(
                    buf,
                    path=proof_rel_path,
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,
                )
                uploaded_url = (
                    (res_up.get("public_url") if isinstance(res_up, dict) else None)
                    or (res_up.get("signed_url") if isinstance(res_up, dict) else None)
                )
                if uploaded_url:
                    uploaded_proof_urls.append(uploaded_url)
                else:
                    logger.error("Proof upload returned no usable URL for %s", proof_rel_path)
            except Exception as e:
                logger.error("Failed to upload proof file %d: %s", i+1, e)
                continue

        # Process data URLs from chips and other sources
        for i, proof_url in enumerate(proof_urls):
            try:
                import re
                m = re.match(r"^data:(.+?);base64,(.+)$", proof_url)
                if m:
                    _mime_hint, b64_data = m.groups()
                    raw = io.BytesIO(b64.b64decode(b64_data))
                    buf, mime, ext = _prep_image_for_upload(raw)
                    proof_rel_path = f"{final_base}/staff-app-proof-{role_id}-{timestamp}-data-{i+1}.{ext}"
                    res_up = _upload_to_storage_retry(
                        buf,
                        path=proof_rel_path,
                        bucket=BUCKET_FOR_PROOF,
                        content_type=mime,
                        make_public=True,
                    )
                    uploaded_url = (
                        (res_up.get("public_url") if isinstance(res_up, dict) else None)
                        or (res_up.get("signed_url") if isinstance(res_up, dict) else None)
                    )
                    if uploaded_url:
                        uploaded_proof_urls.append(uploaded_url)
                else:
                    # Direct URL
                    if proof_url.startswith(("http://", "https://")):
                        uploaded_proof_urls.append(proof_url)
            except Exception as e:
                logger.error("Failed to process proof URL %d: %s", i+1, e)
                continue

        if not uploaded_proof_urls:
            flash_system_error(request, "Failed to upload any proof files.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # Create request with multiple roles
        try:
            result = Secretary.insert_res_staff_account_request(
                p_requested_by_id=staff_id,
                p_person_id=int(pid),
                p_role_ids=role_ids,
                p_supporting_docs=uploaded_proof_urls if uploaded_proof_urls else None,
                p_lupon_sched=(schedules if schedules and ROLE_LUPON in role_ids else None),
                p_bhw_purok_ids=(purok_ids if purok_ids and ROLE_BHW in role_ids else None),
            )
            created_requests = [result["staff_acc_req_id"]]
            
            if len(role_ids) == 1:
                flash_success(request, "Staff account request created.")
            else:
                flash_success(request, f"Staff account request created for {len(role_ids)} roles.")
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
    user_fullname, user_role, user_role_template = get_user_info(request)
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
                "province":  cd.get("province") or "",
                "barangay":  cd.get("barangay") or "",
                "sitio_purok": cd.get("purok_sitio") or "",
                "street":    cd.get("street") or "",
            })
            # flash_success(request, "Personal information saved successfully.")
            logger.info("Step1 ✓ personal info saved to wizard")
            return redirect("secretary:staff_selection_non-resident_docs")
        else:
            # Keep same logic: show validation message; do not expose internals
            logger.error("Validation ✗ Form errors: %s", form.errors.as_json())
            # flash_warning(request, "Please correct the errors below.")
            # fall-through to re-render with form errors

    user_fullname, user_role, user_role_template = get_user_info(request)
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

        except Exception as e:
            logger.warning("Step2 ⚠ image preprocess failed; using originals: %s", e)
            try: front_in.seek(0); back_in.seek(0); selfie_in.seek(0)
            except Exception: pass
            front_buf, back_buf, selfie_buf = front_in, back_in, selfie_in

        # 3) Build previews + store base64 (no uploads here)
        try:
            def _readall(fobj):
                try: fobj.seek(0)
                except Exception: pass
                return fobj.read()

            b_front  = _readall(front_buf)
            b_back   = _readall(back_buf)
            b_selfie = _readall(selfie_buf)


            docs_payload = {
                "valid_id_type_id": valid_id_type_id,
                "valid_id_type_label": valid_id_type_label,
                # previews
                "front_preview": _bytes_to_data_url(b_front,  "image/jpeg"),
                "back_preview":  _bytes_to_data_url(b_back,   "image/jpeg"),
                "selfie_preview":_bytes_to_data_url(b_selfie, "image/jpeg"),

                # raw b64
                "front_b64": b64.b64encode(b_front).decode("ascii"),
                "back_b64": b64.b64encode(b_back).decode("ascii"),
                "selfie_b64": b64.b64encode(b_selfie).decode("ascii"),

            }
            _wiz_set(request, "docs", docs_payload)
        except Exception as e:
            logger.error("Step2 ✗ Preview preparation failed: %s", e)
            flash_system_error(request, "Could not prepare previews.", exc=e)
            return redirect(request.path)

        # flash_success(request, "Documents loaded for preview. Please review and choose role.")
        logger.info("Step2 ✓ Preview-only complete (no uploads).")
        return redirect("secretary:staff_selection_non-resident_role_review")

    # GET
    user_fullname, user_role, user_role_template = get_user_info(request)
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

    # Prepare a shallow copy for template-safe enrichment (e.g., parsed dates).
    personal_view = dict(personal) if isinstance(personal, dict) else {}

    b_raw = personal_view.get("birthdate")
    birthdate_obj: Optional[date] = None
    if isinstance(b_raw, date):
        birthdate_obj = b_raw
    elif isinstance(b_raw, str) and b_raw.strip():
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                birthdate_obj = datetime.strptime(b_raw, fmt).date()
                break
            except ValueError:
                continue
    personal_view["birthdate_obj"] = birthdate_obj

    if request.method == "GET":
        if not personal:
            logger.error("Wizard ✗ Missing personal info in session")
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("secretary:staff_selection_non-resident")
        if not docs:
            logger.error("Wizard ✗ Missing docs info in session")
            flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
            return redirect("secretary:staff_selection_non-resident_docs")

        user_fullname, user_role, user_role_template = get_user_info(request)
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
                "personal": personal_view,
                "docs": docs,
            },
        )

    # --- Collect multiple roles: primary + additional roles
    role_ids: List[int] = []
    primary_role = (request.POST.get("role") or "").strip()
    if primary_role.isdigit():
        role_ids.append(int(primary_role))
    for x in request.POST.getlist("role_ids[]"):
        x = (x or "").strip()
        if x.isdigit():
            role_ids.append(int(x))
    role_ids = sorted(set(role_ids))  # Remove duplicates
    
    # For backward compatibility, use first role as primary
    role_id = role_ids[0] if role_ids else None

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

    if not role_ids:
        flash_warning(request, "Please choose at least one staff role.")
        return redirect(request.path)

    # Check BHW requirements for any BHW role
    if ROLE_BHW in role_ids:
        if len(purok_ids) < 1:
            flash_warning(request, "Barangay Health Worker must be assigned to at least one Purok/Sitio.")
            return redirect(request.path)
        if len(purok_ids) != len(set(purok_ids)):
            flash_warning(request, "Duplicate Purok/Sitio selections are not allowed.")
            return redirect(request.path)

    # Check Lupon requirements for any Lupon role
    if ROLE_LUPON in role_ids:
        if len(schedules) < 1:
            flash_warning(request, "Lupon Member must have at least one schedule.")
            return redirect(request.path)
        _days = [s["day"] for s in schedules]
        if len(_days) != len(set(_days)):
            flash_warning(request, "Duplicate day selections in schedule are not allowed.")
            return redirect(request.path)

    # Collect proof of employment files from this step
    proof_files = []
    proof_urls = []
    
    # Handle data URLs from chips (base64 encoded files)
    for proof_data in request.POST.getlist("proof_files[]"):
        if proof_data and proof_data.startswith("data:"):
            proof_urls.append(proof_data)
    
    # Primary proof file (fallback for direct upload)
    if hasattr(request, "FILES"):
        primary_proof = (
            request.FILES.get("proof")
            or request.FILES.get("proof_file")
            or None
        )
        if primary_proof:
            proof_files.append(primary_proof)
        
        # Additional proof files (if any direct uploads)
        for proof_file in request.FILES.getlist("proof_files[]"):
            if proof_file:
                proof_files.append(proof_file)

    # Handle other proof URLs
    primary_proof_url = (request.POST.get("proof") or "").strip() or None
    if primary_proof_url and primary_proof_url.startswith(("http://", "https://")):
        proof_urls.append(primary_proof_url)
    elif primary_proof_url and primary_proof_url.startswith("data:"):
        proof_urls.append(primary_proof_url)
    elif primary_proof_url:
        logger.warning("Ignoring non-URL, non-data proof value: %r", primary_proof_url)

    if not (proof_files or proof_urls):
        flash_warning(request, "Please attach at least one proof of employment.")
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
    valid_id_type_id = docs.get("valid_id_type_id")

    if not (front_b64 and back_b64 and selfie_b64):
        logger.error("Step3 ✗ Missing base64 docs: %s", list(docs.keys()))
        flash_warning(request, "Supporting documents are incomplete. Please re-upload.")
        return redirect("secretary:staff_selection_non-resident_docs")

    final_base = f"person/{_key_from_personal(personal)}"
    proof_final_base = f"staff_acc_req_proof/{_key_from_personal(personal)}"

    try:
        b_front  = b64.b64decode(front_b64)
        b_back   = b64.b64decode(back_b64)
        b_selfie = b64.b64decode(selfie_b64)
    except Exception as e:
        logger.error("Step3 Base64 decode failed: %s", e)
        from django.contrib import messages
        messages.error(request, "Images could not be decoded from session. Please re-upload your documents.")
        return redirect("secretary:staff_selection_non-resident_docs")

    uploaded_proof_urls = []
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

        # Upload multiple proof files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Process file uploads
        for i, proof_file in enumerate(proof_files):
            try:
                buf, mime, ext = _prep_image_for_upload(proof_file)
                proof_rel_path = f"{proof_final_base}/staff-app-proof-{role_id}-{timestamp}-{i+1}.{ext}"
                res_up = _upload_to_storage_retry(
                    buf,
                    path=proof_rel_path,
                    bucket=BUCKET_STAFF_PROOF,
                    content_type=mime,
                    make_public=True,
                )
                uploaded_url = (
                    (res_up.get("public_url") if isinstance(res_up, dict) else None)
                    or (res_up.get("signed_url") if isinstance(res_up, dict) else None)
                )
                if uploaded_url:
                    uploaded_proof_urls.append(uploaded_url)
                else:
                    logger.error("Proof upload returned no usable URL for %s", proof_rel_path)
            except Exception as e:
                logger.error("Failed to upload proof file %d: %s", i+1, e)
                continue

        # Process data URLs from chips and other sources
        for i, proof_url in enumerate(proof_urls):
            try:
                import re
                m = re.match(r"^data:(.+?);base64,(.+)$", proof_url)
                if m:
                    _mime_hint, b64_data = m.groups()
                    raw = io.BytesIO(b64.b64decode(b64_data))
                    buf, mime, ext = _prep_image_for_upload(raw)
                    proof_rel_path = f"{proof_final_base}/staff-app-proof-{role_id}-{timestamp}-data-{i+1}.{ext}"
                    res_up = _upload_to_storage_retry(
                        buf,
                        path=proof_rel_path,
                        bucket=BUCKET_STAFF_PROOF,
                        content_type=mime,
                        make_public=True,
                    )
                    uploaded_url = (
                        (res_up.get("public_url") if isinstance(res_up, dict) else None)
                        or (res_up.get("signed_url") if isinstance(res_up, dict) else None)
                    )
                    if uploaded_url:
                        uploaded_proof_urls.append(uploaded_url)
                else:
                    # Direct URL
                    if proof_url.startswith(("http://", "https://")):
                        uploaded_proof_urls.append(proof_url)
            except Exception as e:
                logger.error("Failed to process proof URL %d: %s", i+1, e)
                continue
        
        if not uploaded_proof_urls:
            flash_system_error(request, "Failed to upload proof files. Please try again.")
            return redirect(request.path)
    except Exception as e:
        logger.error("Step3 ✗ Upload failed: %s", e)
        flash_system_error(request, "Final upload failed.", exc=e)
        return redirect(request.path)

    front_url = up_front.get("public_url") or up_front.get("signed_url")
    back_url  = up_back.get("public_url") or up_back.get("signed_url")
    self_url  = up_selfie.get("public_url") or up_selfie.get("signed_url")

    # Validate all proof URLs
    for proof_url in uploaded_proof_urls:
        if not proof_url.startswith(("http://", "https://")):
            logger.error("Refusing to store non-URL proof value: %r", proof_url)
            flash_system_error(request, "Proof upload failed to produce valid URLs.")
            return redirect(request.path)

    # Create request with multiple roles
    try:
        req_id = Secretary.insert_nonres_staff_account_request(
            p_requested_by_id=staff_id,
            p_person_id=None,
            p_role_ids=role_ids,
            p_supporting_docs=uploaded_proof_urls if uploaded_proof_urls else None,
            p_lupon_sched=schedules if schedules and ROLE_LUPON in role_ids else None,
            p_bhw_purok_ids=sorted(set(purok_ids)) if purok_ids and ROLE_BHW in role_ids else None,
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
                p_province=personal.get("province"),
                p_barangay=personal.get("barangay"),
                p_sitio_purok=personal.get("sitio_purok"),
                p_street=personal.get("street"),
                p_valid_id_front=front_url,
                p_valid_id_back=back_url,
                p_valid_id_type_id=valid_id_type_id,
                p_selfie_path=self_url,
        )
        created_requests = [req_id]
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
            for k in ("front_b64","back_b64","selfie_b64","front_preview","back_preview","selfie_preview"):
                wiz["docs"].pop(k, None)
            _wiz_set(request, "docs", wiz["docs"])
    except Exception:
        pass

    logger.info(
        "Step3 ✓ staff_requests created: req_ids=%s role_ids=%s purok_ids=%s schedules_count=%s",
        created_requests, role_ids, purok_ids, len(schedules)
    )
    if len(role_ids) == 1:
        flash_success(request, "Staff account request created.")
    else:
        flash_success(request, f"Staff account request created for {len(role_ids)} roles.")
    
    _wiz_clear(request)
    return redirect("secretary:staff_selection")


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_list(request):
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

    if updated:
        request.session[STAFF_FILTER_SESSION_KEY] = {
            "role": role_raw,
            "account_stat": acc_raw,
            "q": search_term,
        }
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
                s = search_term.lower()
                rows = [r for r in rows if s in (r.get("full_name") or "").lower()]
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
    except (TypeError, ValueError):
        per_page = 10

    try:
        page_number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
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

    current_filters = {
        "role": role_raw,
        "account_stat": acc_raw,
        "q": search_term,
    }

    return render(request, "staff/staff_list.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff List",
        "page_title": "Staff List",
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
@role_required(SECRETARY_ROLE)
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

        filters["q"] = raw_query
        request.session[STAFF_FILTER_SESSION_KEY] = filters
        request.session.modified = True

        return JsonResponse({"results": rows[:50]})
    except Exception as e:
        logger.exception("staff_search_api error: %s", e)
        return JsonResponse({"results": [], "error": "Search failed"}, status=500)

    
# @session_login_required
# @role_required(SECRETARY_ROLE)
# @nocache
# @require_GET
# def staff_filter_api(request):
#     role_raw = (request.GET.get("role_id") or "").strip()
#     acc_raw  = (request.GET.get("account_status_id") or "").strip()

#     role_id = int(role_raw) if role_raw.isdigit() else None
#     acc_id  = int(acc_raw)  if acc_raw.isdigit()  else None

#     try:
#         if role_id is None and acc_id is None:
#             rows = Secretary.get_all_staff_info_summary()
#         else:
#             rows = Secretary.filter_staff_by_role_and_account(role_id, acc_id)
#         return JsonResponse({"results": rows})
#     except Exception as e:
#         logger.exception("staff_filter_api error: %s", e)
#         return JsonResponse({"results": [], "error": "Filter failed"}, status=500)



@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_dets(request, staff_code: str):
    # Handle POST request for personal information update
    if request.method == "POST" and request.POST.get('action') == 'update_personal_info':
        from authentication.models import Authentication
        
        auth = request.session.get("auth") or {}
        updated_by_staff_id = auth.get("staff_id")
        
        if not updated_by_staff_id:
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.path)
        
        # Check if reason is provided
        reason = (request.POST.get('reason') or '').strip()
        if not reason:
            flash_warning(request, "Please provide a reason for updating personal information.")
            return redirect(request.path)
        
        try:
            # Get current staff data first
            rows = Secretary.get_staff_profile_display(staff_code) if staff_code else []
            current_staff = rows[0] if rows else None
            
            if not current_staff:
                flash_warning(request, "Staff not found.")
                return redirect("secretary:staff_list")
            
            staff_id = current_staff.get("staff_id")
            if not staff_id:
                flash_warning(request, "Staff ID not found.")
                return redirect("secretary:staff_list")
            
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
                reason=f'Personal information update by secretary: {reason}'
            )
            
            if result:
                flash_success(request, 'Personal information updated successfully!')
            else:
                flash_warning(request, 'No changes were made.')
                
        except (DatabaseError, OperationalError, IntegrityError) as e:
            logger.error(f"Database error updating personal info: {str(e)}", exc_info=True)
            flash_db_error(request, e)
        except Exception as e:
            logger.error(f"Error updating personal info: {str(e)}", exc_info=True)
            flash_system_error(request, 'An error occurred while updating personal information.', exc=e)
        
        return redirect(request.path)
    
    # GET request handling
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

    user_fullname, user_role, user_role_template = get_user_info(request)
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

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_account_requests_list(request: HttpRequest) -> HttpResponse:
    filters = request.session.get(STAFF_REQ_FILTER_SESSION_KEY, {}) or {}
    role_raw = (filters.get("role") or "").strip()
    date_raw = (filters.get("date_submitted") or "").strip()
    search_term = (filters.get("q") or "").strip()

    updated = False
    should_redirect = False

    if "clear_filters" in request.GET:
        role_raw = ""
        date_raw = ""
        search_term = ""
        updated = True
        should_redirect = True

    remove_target = (request.GET.get("remove_filter") or "").strip()
    if remove_target:
        if remove_target == "role":
            role_raw = ""
        elif remove_target == "date_submitted":
            date_raw = ""
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
    if "q" in request.GET:
        search_term = (request.GET.get("q") or "").strip()
        updated = True
    if "search" in request.GET:
        search_term = (request.GET.get("search") or "").strip()
        updated = True

    filters_state = {
        "role": role_raw,
        "date_submitted": date_raw,
        "q": search_term,
    }
    if updated or STAFF_REQ_FILTER_SESSION_KEY not in request.session:
        request.session[STAFF_REQ_FILTER_SESSION_KEY] = filters_state
        request.session.modified = True

    if should_redirect:
        return redirect(request.path)

    try:
        from captain.models import Captain
        staff_req = Captain.list_requests() or []
    except Exception:
        logger.exception("Error loading staff requests")
        staff_req = []

    # simple getters for dicts/objects
    def get(row, key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    # Secretary can only view requests waiting for secretary's approval (status_id == 29)
    filtered = []
    for r in staff_req:
        sid = get(r, "status_id") or get(r, "request_status_id")
        name = (get(r, "status_name") or "").upper()
        try:
            sid = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid = None
        if sid == 29 or sid == 47 or "WAITING FOR BARANGAY CAPTAIN" in name or "WAITING FOR BARANGAY SECRETARY" in name:
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
                pretty_date = get(r, "date_time_submitted_pretty")
                
                if pretty_date and isinstance(pretty_date, str):
                    try:
                        # Parse "October 12, 2025 9:06 A.M" format
                        date_part = ' '.join(pretty_date.split()[:3])  # "October 12, 2025"
                        parsed_date = datetime.strptime(date_part, "%B %d, %Y").date()
                        if parsed_date == target_date:
                            date_filtered.append(r)
                    except (ValueError, IndexError):
                        pass
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
        "search": search_term,
    }
    form = StaffAccountRequestFilters(initial=form_initial)

    paginator = Paginator(filtered, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    role_choices = {str(k): v for k, v in form.fields["role"].choices}

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
    if search_term:
        active_filters.append({
            "label": f"Search: \"{search_term}\"",
            "remove_url": f"{request.path}?remove_filter=search",
        })

    clear_filters_url = f"{request.path}?clear_filters=1"

    current_filters = filters_state
    user_fullname, user_role, user_role_template = get_user_info(request)

    return render(request, "secretary/staff_account_req.html", {
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
@role_required(SECRETARY_ROLE)
@nocache
def pending_staff_dets(request, p_staff_acc_req_id: str):
    try:
        from captain.models import Captain
        rows = Captain.get_pending_staff_details(p_staff_acc_req_id) if p_staff_acc_req_id else []
    except Exception:
        logger.exception("get_pending_staff_details failed for staff_code=%s", p_staff_acc_req_id)
        rows = []

    # Get status history
    status_history = []
    try:
        status_history = Secretary.get_staff_acc_req_status_history(int(p_staff_acc_req_id)) if p_staff_acc_req_id else []
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
    return render(request, "secretary/pending_staff_dets.html", ctx)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def staff_account_requests_search_api(request):
    raw_query = (request.GET.get("q") or "").strip()

    filters = request.session.get(STAFF_REQ_FILTER_SESSION_KEY, {}) or {}
    role_raw = (filters.get("role") or "").strip()
    date_raw = (filters.get("date_submitted") or "").strip()

    try:
        from captain.models import Captain
        staff_req = Captain.list_requests() or []
    except Exception as e:
        logger.exception("staff_account_requests_search_api error: %s", e)
        return JsonResponse({"results": [], "error": "Search failed"}, status=500)

    def get(row, key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    # Secretary can only view requests waiting for secretary's approval (status_id == 29)
    filtered = []
    for r in staff_req:
        sid = get(r, "status_id") or get(r, "request_status_id")
        name = (get(r, "status_name") or "").upper()
        try:
            sid = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid = None
        if sid == 29 or sid == 47 or "WAITING FOR BARANGAY CAPTAIN'S APPROVAL" in name or "WAITING FOR BARANGAY SECRETARY'S APPROVAL" in name:
            filtered.append(r)

    # Apply role filter
    if role_raw:
        role_id = int(role_raw) if role_raw.isdigit() else None
        if role_id:
            filtered = [r for r in filtered if get(r, "role_id") == role_id]

    # Apply date filter
    if date_raw:
        from datetime import datetime
        try:
            target_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            target_date = None
        
        if target_date:
            date_filtered = []
            for r in filtered:
                pretty_date = get(r, "date_time_submitted_pretty")
                
                if pretty_date and isinstance(pretty_date, str):
                    try:
                        # Parse "October 12, 2025 9:06 A.M" format
                        date_part = ' '.join(pretty_date.split()[:3])  # "October 12, 2025"
                        parsed_date = datetime.strptime(date_part, "%B %d, %Y").date()
                        if parsed_date == target_date:
                            date_filtered.append(r)
                    except (ValueError, IndexError):
                        pass
            filtered = date_filtered

    # Apply search filter
    if raw_query:
        q_lower = raw_query.lower()
        filtered = [r for r in filtered if q_lower in (get(r, "name") or "").lower()]

    # Update session
    filters.update({
        "role": role_raw,
        "date_submitted": date_raw,
        "q": raw_query,
    })
    request.session[STAFF_REQ_FILTER_SESSION_KEY] = filters
    request.session.modified = True

    return JsonResponse({"results": filtered[:50]})

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_requests_list(request: HttpRequest) -> HttpResponse:
    """View staff account requests submitted by this secretary"""
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    # Get filter parameters
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    role_filter = request.GET.get('role', '').strip()
    date_filter = request.GET.get('date_submitted', '').strip()
    
    try:
        requests = Secretary.get_staff_account_req_list_by_requester(staff_id)
        stats_data = Secretary.get_staff_request_statistics_by_requester(staff_id)
        stats = stats_data[0] if stats_data else {
            'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0
        }
    except Exception as e:
        logger.exception("Error loading requests")
        from common.flash import flash_system_error
        flash_system_error(request, "Failed to load requests.")
        requests = []
        stats = {'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0}
    
    # Apply filters
    filtered_requests = requests
    
    # Search by name
    if search_query:
        search_lower = search_query.lower()
        filtered_requests = [
            r for r in filtered_requests 
            if search_lower in (r.get('name') or '').lower()
        ]
    
    # Filter by status
    if status_filter:
        filtered_requests = [
            r for r in filtered_requests 
            if str(r.get('status_id', '')) == status_filter
        ]
    
    # Filter by role
    if role_filter:
        filtered_requests = [
            r for r in filtered_requests 
            if str(r.get('role_id', '')) == role_filter
        ]
    
    # Filter by date
    if date_filter:
        from datetime import datetime
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            date_filtered = []
            for r in filtered_requests:
                pretty_date = r.get('date_time_submitted_pretty')
                if pretty_date and isinstance(pretty_date, str):
                    try:
                        # Parse "December 1, 2025 3:28 A.M." format
                        date_part = ' '.join(pretty_date.split()[:3])  # "December 1, 2025"
                        parsed_date = datetime.strptime(date_part, "%B %d, %Y").date()
                        if parsed_date == target_date:
                            date_filtered.append(r)
                    except (ValueError, IndexError):
                        continue
            filtered_requests = date_filtered
        except ValueError:
            pass
    
    # Implement pagination with 9 requests per page
    paginator = Paginator(filtered_requests, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "secretary/requests_list.html", {
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
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def staff_request_detail(request: HttpRequest, request_id: int) -> HttpResponse:
    """View detailed information about a specific staff request"""
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    try:
        details_data = Secretary.get_staff_acc_req_profile_progress(request_id)
        history = Secretary.get_staff_acc_req_status_history(request_id)
        
        if not details_data:
            from common.flash import flash_warning
            flash_warning(request, "Request not found.")
            return redirect('secretary:staff_requests_list')
        
        request_detail = details_data[0]
        
        # Allow access if user is the requester OR if user has appropriate role permissions
        if request_detail.get('requested_by_id') != staff_id:
            # For now, allow secretaries to view all requests for debugging
            # TODO: Implement proper role-based access control
            pass
            
    except Exception as e:
        logger.exception(f"Error loading request {request_id}")
        from common.flash import flash_system_error
        flash_system_error(request, "Failed to load request details.")
        return redirect('secretary:staff_requests_list')
    
    return render(request, "secretary/request_detail.html", {
        'request': request_detail,
        'history': history,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'user_role_template': user_role_template,
        'page_path': f"{user_role} / My Requests / Details",
        'page_title': f"Request Details - {request_detail.get('full_name', 'Unknown')}",
    })

REQUEST_STATUS_APPROVED = 30
REQUEST_STATUS_REJECTED = 4

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["POST"])
def process_staff_request(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth") or {}
    approver_id = auth.get("staff_id")
    
    if not approver_id:
        flash_system_error(request, "Your session is missing staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")
    
    try:
        approver_id = int(approver_id)
    except (TypeError, ValueError):
        flash_system_error(request, "Invalid staff credentials.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")

    staff_acc_req_id_raw = (
        request.POST.get("staff_acc_req_id") or 
        request.POST.get("id")
    )
    
    if not staff_acc_req_id_raw:
        flash_warning(request, "Missing staff account request ID.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")
    
    try:
        staff_acc_req_id = int(staff_acc_req_id_raw)
    except (TypeError, ValueError):
        flash_warning(request, "Invalid staff account request ID.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")

    status_raw = request.POST.get("p_request_status_id")
    if not status_raw:
        flash_warning(request, "Missing decision status.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")
    
    try:
        status_id = int(status_raw)
    except (TypeError, ValueError):
        flash_warning(request, "Invalid decision status.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")
    
    if status_id not in (REQUEST_STATUS_APPROVED, REQUEST_STATUS_REJECTED):
        flash_warning(request, "Invalid decision status.")
        return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")

    remarks = (request.POST.get("remarks") or "").strip() or None
    email_to = (request.POST.get("email") or "").strip()
    
    if email_to:
        is_valid, reason = verify_email_deliverable_abstract(email_to)
        if not is_valid:
            flash_warning(request, f"Email validation failed: {reason}. Request will be processed but email notifications may not be sent.")
            email_to = ""

    try:
        result_text = Secretary.process_staff_account_request(
            p_staff_acc_req_id=staff_acc_req_id,
            p_approver_id=approver_id,
            p_request_status_id=status_id,
            p_remarks=remarks,
        )

        if status_id == REQUEST_STATUS_REJECTED:
            if email_to:
                try:
                    import common.send_email as send_email
                    reason = remarks or "No specific reason was provided."
                    send_email.send_email(
                        subject="Staff Account Request Rejected",
                        to=[email_to],
                        body_text=f"Good day!\n\nYour staff account creation request has been REJECTED.\n\nReason: {reason}\n\nPlease contact the authorized staff if you have any concern.\n\nBarangay Sto. Niño",
                        body_html=f"<p>Good day!</p><p>Your staff account creation request has been <strong>REJECTED</strong>.</p><p><strong>Reason:</strong> {reason}</p><p>Please contact the authorized staff if you have any concern.</p><p>Barangay Sto. Niño</p>",
                        from_name="Barangay Sto. Niño",
                        fail_silently=True,
                    )
                except Exception as e:
                    logger.warning("Failed to send rejection email: %s", e)
            
            flash_success(request, "Staff account request rejected.")
        
        elif status_id == REQUEST_STATUS_APPROVED:
            if result_text == "TRUE":
                if email_to:
                    try:
                        import common.send_email as send_email
                        send_email.send_email(
                            subject="Staff Account Request Update",
                            to=[email_to],
                            body_text="Good day!\n\nYour staff account request has been reviewed by the Barangay Secretary.\n\nCurrent Status: WAITING FOR ADMIN'S APPROVAL\n\nYou will receive another update after the Admin's final decision.\n\nBarangay Sto. Niño",
                            body_html="<p>Good day!</p><p>Your staff account request has been reviewed by the Barangay Secretary.</p><p><strong>Current Status:</strong> WAITING FOR ADMIN'S APPROVAL</p><p>You will receive another update after the Admin's final decision.</p><p>Barangay Sto. Niño</p>",
                            from_name="Barangay Sto. Niño",
                            fail_silently=True,
                        )
                    except Exception as e:
                        logger.warning("Failed to send approval email: %s", e)
                
                flash_success(request, "Request approved and forwarded to Admin for final processing.")
            
            elif result_text and result_text.strip():
                staff_code = result_text.strip()
                flash_success(request, f"Staff account approved. Staff Code: {staff_code}")
                
                if email_to:
                    try:
                        import common.send_email as send_email
                        send_email.send_email(
                            subject="Staff Account Request Approved",
                            to=[email_to],
                            body_text="Good day!\n\nYour staff account request has been APPROVED.\n\nYou will receive your login credentials in a separate email shortly.\n\nBarangay Sto. Niño",
                            body_html="<p>Good day!</p><p>Your staff account request has been <strong>APPROVED</strong>.</p><p>You will receive your login credentials in a separate email shortly.</p><p>Barangay Sto. Niño</p>",
                            from_name="Barangay Sto. Niño",
                            fail_silently=True,
                        )
                    except Exception as e:
                        logger.warning("Failed to send final approval email: %s", e)
            
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
    
    return redirect(request.META.get("HTTP_REFERER") or "secretary:staff_account_requests_list")

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

    user_fullname, user_role, user_role_template = get_user_info(request)
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

    user_fullname, user_role, user_role_template = get_user_info(request)
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
@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def resident_list(
    request: HttpRequest,
    resident_service: IResidentService = Provide[AppContainer.resident_service],
):
    user_role = _auth_role_name(request)
    form = ResidentFilters()
    
    search = request.GET.get("search")
    purok_sitio = request.GET.get("purok_sitio")

    rows = resident_service.execute(
        search=search,
        purok=purok_sitio,
    )

    paginator = Paginator(rows,10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    

    if (search or purok_sitio is not None) and not form.is_valid():
        form = ResidentFilters()

    return render(request, "resident/resident_list.html", {
        'page_path': f'{user_role} / Resident List',
        'page_title': 'Resident List',
        'page_obj': page_obj,
        'form': form,
        'search_url': 'secretary:ajax_resident_search',
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
@inject
def ajax_resident_search(
    request: HttpRequest,
    resident_service: IResidentService = Provide[AppContainer.resident_service],
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    # only allow XHR (optional, but nice)
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR required")
    
    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key != "rows":
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    purok_sitio = request.GET.get("purok_sitio")

    rows = resident_service.execute(
        search=q,
        purok=purok_sitio,
    )[:50]

    context = {"rows": rows}
    html = render_to_string("resident/_resident_list.html", context, request=request)
    return HttpResponse(html)

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def resident_detail(
    request: HttpRequest,
    person_id: int,
    resident_service: IResidentService = Provide[AppContainer.resident_service],
) -> HttpResponse:
    """
    Display detailed resident information.
    """
    user_role = _auth_role_name(request)
    
    resident = resident_service.get_resident_detail(person_id)
    
    if not resident:
        messages.error(request, "Resident not found.")
        return redirect("secretary:resident_list")
    
    return render(request, "resident/resident_detail.html", {
        'page_path': f'{user_role} / Resident / {resident.person_code}',
        'page_title': f'Resident {resident.person_code}',
        'resident': resident,
    })

def resident_map_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    user_fullname, user_role, user_role_template = get_user_info(request)
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
def household_detail(
    request: HttpRequest,
    household_id: int,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponse:
    """
    Display detailed household information including all families and members.
    """
    user_role = _auth_role_name(request)
    
    household = household_service.get_household_detail(household_id)
    
    if not household:
        messages.error(request, "Household not found.")
        return redirect("secretary:household_list")
    
    return render(request, "household/household_detail.html", {
        'page_path': f'{user_role} / Household / {household.household_num}',
        'page_title': f'Household {household.household_num}',
        'household': household,
    })

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


@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def family_list(
    request: HttpRequest,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = FamilyFilters(request.GET or None)

    search = request.GET.get("search")
    household_type = _to_int_or_none(request.GET.get("household_type"))
    nhts_status = _to_int_or_none(request.GET.get("nhts_status"))
    indigent_status = _to_int_or_none(request.GET.get("indigent_status"))

    if search:
        rows = household_repo.search_family(search)
    elif household_type:
        rows = household_repo.filter_family_by_household_type(household_type)
    elif nhts_status:
        rows = household_repo.filter_family_by_nhts_status(nhts_status)
    elif indigent_status:
        rows = household_repo.filter_family_by_indigent_status(indigent_status)
    else:
        rows = household_repo.fetch_family_list()

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "user_role": user_role,
        "form": form,
        "page_obj": page_obj,
        "search_url": "secretary:ajax_family_search",
    }
    return render(request, "family/family_list.html", context)


@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def ajax_family_search(
    request: HttpRequest,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
) -> HttpResponse:
    
    search = request.GET.get("search")
    household_type = _to_int_or_none(request.GET.get("household_type"))
    nhts_status = _to_int_or_none(request.GET.get("nhts_status"))
    indigent_status = _to_int_or_none(request.GET.get("indigent_status"))

    if search:
        rows = household_repo.search_family(search)
    elif household_type:
        rows = household_repo.filter_family_by_household_type(household_type)
    elif nhts_status:
        rows = household_repo.filter_family_by_nhts_status(nhts_status)
    elif indigent_status:
        rows = household_repo.filter_family_by_indigent_status(indigent_status)
    else:
        rows = household_repo.fetch_family_list()

    context = {
        "rows": rows,
        "search_url": "secretary:ajax_family_search",
    }
    return render(request, "family/_family_list.html", context)


@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def family_detail(
    request: HttpRequest,
    family_id: int,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    family = household_repo.fetch_family_detail(family_id)
    
    if not family:
        messages.error(request, "Family not found.")
        return redirect("secretary:family_list")

    context = {
        'page_path': f'{user_role} / Family / {family.get("family_num", "")}',
        'page_title': f'Family {family.get("family_num", "")}',
        "user_role": user_role,
        "family": family,
    }
    return render(request, "family/family_detail.html", context)


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
    purok = request.GET.get("purok") or None
    date_range = request.GET.get("date_range") or None
    employee_range = request.GET.get("employee_range") or None

    # Use execute_with_filters if any of the new filters are applied
    use_filter_query = purok or date_range or employee_range
    
    if use_filter_query:
        rows = business_service.execute_with_filters()
    else:
        rows = business_service.execute(
            search=search,
            b_category=b_category,
            ownership_type=ownership_type,
            status=status,
        )
    
    # Apply additional filters after fetching results
    if purok:
        rows = [r for r in rows if (r.sitio_purok or '').upper() == purok.upper()]
    
    if date_range:
        months = int(date_range)
        cutoff_date = datetime.now().date() - relativedelta(months=months)
        rows = [r for r in rows if r.date_established and r.date_established >= cutoff_date]
    
    if employee_range:
        min_emp, max_emp = map(int, employee_range.split('-'))
        rows = [r for r in rows if r.num_of_employees and min_emp <= r.num_of_employees <= max_emp]

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
                'purok': purok,
                'date_range': date_range,
                'employee_range': employee_range,
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
        purok=(request.GET.get("purok") or None),
        date_range=(request.GET.get("date_range") or None),
        employee_range=(request.GET.get("employee_range") or None),
    )
    return JsonResponse(pins, safe=False)

# -------------------------------
# ANNOUNCEMENT
# -------------------------------

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def announcement_draft(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """Create or edit an announcement draft"""
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    
    if not staff_id:
        messages.error(request, "Your session is missing staff credentials.")
        return redirect('secretary:dashboard')
    
    form = AnnouncementDraftForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        try:
            
            command = CreateAnnouncementDraftCMD(
                title=form.cleaned_data['title'],
                body=form.cleaned_data['body'],
                created_by_id=staff_id,
                publish_at=form.cleaned_data.get('publish_at'),
                expire_at=form.cleaned_data.get('expire_at')
            )
            
            announcement_id = announcement_service.create_draft(command)
            log_announcement_action(
                announcement_id=announcement_id,
                table_affected= 'ANNOUNCEMENT',
                action='INSERT',
                performer_id=staff_id,
                details=f'Created a new announcement draft. ID :{announcement_id}',
            )
            messages.success(request, f"Announcement draft created successfully! ID: {announcement_id}")
            return redirect('secretary:announcement_draft_list')
            
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, "An error occurred while creating the announcement draft.")
            logger.exception("Failed to create announcement draft: %s", e)
    
    return render(request, "secretary/announcement/draft.html", {
        'page_path': f'{user_role} / Announcements / Create Draft',
        'page_title': 'Create Announcement Draft',
        'form': form,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_draft_list(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """List all announcement drafts"""
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    
    form = DraftListSearch(request.GET or None)
    search_query = request.GET.get('search', '').strip()
    
    try:
        # Get all drafts (you can modify this to filter by creator if needed)
        drafts = announcement_service.execute(
            search= search_query
        )
        
        paginator = Paginator(drafts, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if search_query is not None and not form.is_valid:
            form = DraftListSearch()
        
    except Exception as e:
        messages.error(request, "An error occurred while loading announcement drafts.")
        logger.exception("Failed to load announcement drafts: %s", e)
        page_obj = None
    
    return render(request, "secretary/announcement/draft_list.html", {
        'page_path': f'{user_role} / Announcements / Draft List',
        'page_title': 'Announcement Drafts',
        'form': form,
        'page_obj': page_obj,
        'search_query': search_query,
        'search_url': 'secretary:ajax_announcement_draft_search',
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@require_GET
@inject
def ajax_announcement_draft_search(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")
    
    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key != "rows":
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    
    try:
        rows = announcement_service.execute(
            search=q,
        )[:50]
        
    except Exception as e:
        logger.exception("ajax_announcement_draft_search error: %s", e)
        rows = []

    context = {"rows": rows}
    html = render_to_string("announcement/_draft_list.html", context, request=request)
    return HttpResponse(html)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_draft_view(
    request: HttpRequest,
    announcement_id: int,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
    audience_service: IAudienceService = Provide[AppContainer.audience_service],
) -> HttpResponse:
    """View announcement draft details (editable with actions)"""
    user_role = _auth_role_name(request)

    channel_form = AddChannelForm()
    audience_form = AudienceScope()
    
    try:
        draft = announcement_service.get_draft_by_id(announcement_id)
        
        if not draft:
            messages.error(request, "Announcement not found.")
            return redirect('secretary:announcement_draft_list')
        
        audiences = audience_service.get_announcement_audiences(announcement_id)
        
    except Exception as e:
        messages.error(request, "Failed to load announcement details.")
        logger.exception("Failed to load announcement: %s", e)
        return redirect('secretary:announcement_draft_list')
    
    return render(request, "secretary/announcement/draft_view.html", {
        'page_path': f'{user_role} / Announcements / View Draft',
        'page_title': f'View Draft: {draft.announcement_title}',
        'form' : channel_form,
        'audience_form': audience_form,
        'draft': draft,
        'audiences': audiences,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_view(
    request: HttpRequest,
    announcement_id: int,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
    audience_service: IAudienceService = Provide[AppContainer.audience_service],
) -> HttpResponse:
    """View announcement details (read-only, for published/scheduled/expired/cancelled)"""
    user_role = _auth_role_name(request)
    
    try:
        # Use generic get_by_id instead of get_draft_by_id to get any status
        announcement = announcement_service.announcement_repository.get_by_id(announcement_id)
        
        if not announcement:
            messages.error(request, "Announcement not found.")
            return redirect('secretary:announcement_draft_list')
        
        audiences = audience_service.get_announcement_audiences(announcement_id)
        
    except Exception as e:
        messages.error(request, "Failed to load announcement details.")
        logger.exception("Failed to load announcement: %s", e)
        return redirect('secretary:announcement_draft_list')
    
    return render(request, "secretary/announcement/announcement_view.html", {
        'page_path': f'{user_role} / Announcements / View',
        'page_title': f'View: {announcement.announcement_title}',
        'announcement': announcement,
        'audiences': audiences,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_draft_edit(
    request: HttpRequest,
    announcement_id: int,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """Edit an announcement draft"""
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    
    # Get the existing draft
    try:
        draft = announcement_service.get_draft_by_id(announcement_id)
        if not draft:
            messages.error(request, "Announcement draft not found.")
            return redirect('secretary:announcement_draft_list')
    except Exception as e:
        messages.error(request, "Failed to load announcement draft.")
        logger.exception("Failed to load draft for edit: %s", e)
        return redirect('secretary:announcement_draft_list')
    
    # Populate form with existing data
    if request.method == 'POST':
        form = AnnouncementDraftForm(request.POST)
        if form.is_valid():
            try:
                from src.app.transfer_objects.commands.announcement_cmd import UpdateAnnouncementDraftCMD
                
                command = UpdateAnnouncementDraftCMD(
                    announcement_id=announcement_id,
                    title=form.cleaned_data['title'],
                    body=form.cleaned_data['body'],
                    publish_at=form.cleaned_data.get('publish_at'),
                    expire_at=form.cleaned_data.get('expire_at')
                )
                
                announcement_service.update_draft(command)
                
                log_announcement_action(
                    announcement_id=announcement_id,
                    table_affected='ANNOUNCEMENT',
                    action='UPDATE',
                    performer_id=staff_id,
                    details=f'Updated announcement draft ID: {announcement_id}',
                )
                
                messages.success(request, "Announcement draft updated successfully!")
                return redirect('secretary:announcement_draft_list')
                
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, "An error occurred while updating the announcement draft.")
                logger.exception("Failed to update announcement draft: %s", e)
    else:
        # Pre-fill form with existing data
        initial_data = {
            'title': draft.announcement_title,
            'body': draft.announcement_body,
            'publish_at': draft.announcement_published_at,
            'expire_at': draft.announcement_expire_at,
        }
        form = AnnouncementDraftForm(initial=initial_data)
    
    return render(request, "secretary/announcement/draft_edit.html", {
        'page_path': f'{user_role} / Announcements / Edit Draft',
        'page_title': f'Edit Draft: {draft.announcement_title}',
        'form': form,
        'draft': draft,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@inject
def ajax_delete_announcement_draft(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> JsonResponse:
    """Delete an announcement draft via AJAX"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        announcement_id = data.get('announcement_id')
        
        if not announcement_id:
            return JsonResponse({'error': 'Announcement ID is required'}, status=400)
        
        auth = request.session.get('auth', {})
        staff_id = auth.get('staff_id')
        
        # Delete the draft
        success = announcement_service.delete_draft(announcement_id)
        
        if success:
            log_announcement_action(
                announcement_id=announcement_id,
                table_affected='ANNOUNCEMENT',
                action='DELETE',
                performer_id=staff_id,
                details=f'Deleted announcement draft ID: {announcement_id}',
            )
            
            return JsonResponse({'success': True, 'message': 'Draft deleted successfully'})
        else:
            return JsonResponse({'error': 'Failed to delete draft'}, status=400)
            
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Failed to delete announcement draft: %s", e)
        return JsonResponse({'error': 'An error occurred while deleting the draft'}, status=500)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_audience_scope(
    request: HttpRequest,
    audience_service: IAudienceService = Provide[AppContainer.audience_service],
) -> HttpResponse:
    """Add audience scope to announcement"""
    user_role = _auth_role_name(request)
    form = AudienceScope(request.POST or None)
    
    announcement_id = request.GET.get('announcement_id')
    
    return render(request, "secretary/announcement/audience_scope.html", {
        'page_path': f'{user_role} / Announcements / Audience Scope',
        'page_title': 'Audience Scope',
        'form': form,
        'announcement_id': announcement_id,
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def save_audience_rules(
    request: HttpRequest,
    audience_service: IAudienceService = Provide[AppContainer.audience_service],
) -> JsonResponse:
    """Save all audience rules to database with duplicate prevention"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        announcement_id = data.get('announcement_id')
        rules = data.get('rules', [])
        
        if not announcement_id:
            return JsonResponse({'error': 'Announcement ID required'}, status=400)
        
        # Get existing audiences to check for duplicates
        existing_audiences = audience_service.get_announcement_audiences(announcement_id)
        
        saved_count = 0
        skipped_count = 0
        
        for rule in rules:
            scope_id = rule.get('scope_id')
            role_id = rule.get('role_id')
            purok_id = rule.get('purok_id')
            
            # Check for duplicate
            is_duplicate = any(
                aud.audience_scope_id == scope_id and
                aud.role_id == role_id and
                aud.purok_sitio_id == purok_id
                for aud in existing_audiences
            )
            
            if is_duplicate:
                skipped_count += 1
                continue
            
            command = AddAnnouncementAudienceCMD(
                announcement_id=announcement_id,
                audience_scope_id=scope_id,
                role_id=role_id,
                purok_sitio_id=purok_id,
                person_ids=None  # No longer used for scope 6 (STUDENTS)
            )
            
            audience_id, inserted_persons = audience_service.add_announcement_audience(command)
            saved_count += inserted_persons
        
        message = f'{len(rules) - skipped_count} rules saved, {saved_count} persons added'
        if skipped_count > 0:
            message += f' ({skipped_count} duplicate(s) skipped)'
        
        return JsonResponse({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        logger.exception("Failed to save audience rules: %s", e)
        return JsonResponse({'error': str(e)}, status=500)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def remove_audience(
    request: HttpRequest,
    audience_service: IAudienceService = Provide[AppContainer.audience_service],
) -> JsonResponse:
    """Remove an audience scope from an announcement"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        audience_id = data.get('audience_id')
        
        if not audience_id:
            return JsonResponse({'error': 'Audience ID required'}, status=400)
        
        # Delete from audience_person_list first (foreign key constraint)
        sql_delete_persons = "DELETE FROM public.audience_person_list WHERE audience_id = %s"
        audience_service.audience_repository.ctx.execute_command(sql_delete_persons, (audience_id,))
        
        # Delete from audience
        sql_delete_audience = "DELETE FROM public.audience WHERE audience_id = %s"
        audience_service.audience_repository.ctx.execute_command(sql_delete_audience, (audience_id,))
        
        return JsonResponse({
            'success': True,
            'message': 'Audience removed successfully'
        })
        
    except Exception as e:
        logger.exception("Failed to remove audience: %s", e)
        return JsonResponse({'error': str(e)}, status=500)

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def upsert_announcement_channels(
    request: HttpRequest,
    channel_service: IChannelService = Provide[AppContainer.channel_service],
) -> JsonResponse:
    """Upsert channels for an announcement and create recipients in the same transaction"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        announcement_id = data.get('announcement_id')
        channel_type_ids = data.get('channel_type_ids', [])

        if not announcement_id:
            return JsonResponse({'error': 'Announcement ID required'}, status=400)

        if not channel_type_ids:
            return JsonResponse({'error': 'At least one channel type is required'}, status=400)

        # Use DB transaction to ensure atomicity
        with transaction.atomic():
            upsert_cmd = UpsertAnnouncementChannelsCMD(
                announcement_id=announcement_id,
                channel_type_ids=channel_type_ids
            )
            upsert_success = channel_service.upsert_announcement_channels(upsert_cmd)

            if not upsert_success:
                return JsonResponse({'error': 'Failed to upsert channels'}, status=500)

            create_cmd = CreateAnnouncementRecipientsCMD(announcement_id=announcement_id)
            recipients_count = channel_service.create_announcement_recipients(create_cmd)

        return JsonResponse({
            'success': True,
            'message': f'Channels updated and {recipients_count} recipients created for announcement {announcement_id}',
            'recipients_count': recipients_count
        })

    except Exception as e:
        logger.exception("Failed to upsert channels and create recipients: %s", e)
        return JsonResponse({'error': str(e)}, status=500)


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_channels_api(
    request: HttpRequest,
    announcement_id: int,
    channel_service: IChannelService = Provide[AppContainer.channel_service],
) -> JsonResponse:
    """Return applied channels for an announcement"""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    try:
        channels = channel_service.get_announcement_channels(announcement_id)
        data = [
            {
                'announcement_channel_id': ch.announcement_channel_id,
                'channel_type_id': ch.channel_type_id,
                'channel_type_name': ch.channel_type_name,
                'is_enabled': ch.is_enabled,
            }
            for ch in channels
        ]
        return JsonResponse({'success': True, 'channels': data})
    except Exception as e:
        logger.exception("Failed to get channels: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def publish_announcement_now(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> JsonResponse:
    """Publish an announcement immediately"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        announcement_id = data.get('announcement_id')
        
        if not announcement_id:
            return JsonResponse({'error': 'Announcement ID required'}, status=400)
        
        auth = request.session.get('auth', {})
        staff_id = auth.get('staff_id')
        
        command = PublishAnnouncementNowCMD(
            announcement_id=announcement_id,
            published_by_id=staff_id
        )
        
        result = announcement_service.publish_announcement_now(command)
        
        log_announcement_action(
            announcement_id=result.announcement_id,
            table_affected='ANNOUNCEMENT',
            action='UPDATE',
            performer_id=staff_id,
            details=f'Published announcement immediately. Recipients: {result.total_recipients}',
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Announcement published successfully to {result.total_recipients} recipients',
            'announcement_id': result.announcement_id,
            'total_recipients': result.total_recipients
        })
        
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Failed to publish announcement: %s", e)
        return JsonResponse({'error': 'Failed to publish announcement'}, status=500)


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def schedule_announcement(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> JsonResponse:
    """Schedule an announcement for future publishing"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        announcement_id = data.get('announcement_id')
        
        if not announcement_id:
            return JsonResponse({'error': 'Announcement ID required'}, status=400)
        
        auth = request.session.get('auth', {})
        staff_id = auth.get('staff_id')
        
        command = ScheduleAnnouncementCMD(
            announcement_id=announcement_id,
            scheduled_by_id=staff_id
        )
        
        result = announcement_service.schedule_announcement(command)
        
        log_announcement_action(
            announcement_id=result.announcement_id,
            table_affected='ANNOUNCEMENT',
            action='UPDATE',
            performer_id=staff_id,
            details=f'Scheduled announcement for {result.publish_at}',
        )
        
        # Format publish_at to local timezone for display
        from django.utils import timezone
        local_time = timezone.localtime(result.publish_at) if result.publish_at else None
        formatted_time = local_time.strftime('%Y-%m-%d %I:%M %p') if local_time else 'Unknown'
        
        return JsonResponse({
            'success': True,
            'message': f'Announcement scheduled for {local_time}',
            'announcement_id': result.announcement_id,
            'new_status': result.new_status,
            'publish_at': result.publish_at.isoformat() if result.publish_at else None
        })
        
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Failed to schedule announcement: %s", e)
        return JsonResponse({'error': 'Failed to schedule announcement'}, status=500)


# -------------------------------
# SCHEDULED ANNOUNCEMENTS
# -------------------------------
@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_scheduled_list(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """List all scheduled announcements"""
    user_role = _auth_role_name(request)
    
    form = DraftListSearch(request.GET or None)
    search_query = request.GET.get('search', '').strip()
    
    try:
        repo = announcement_service.announcement_repository
        
        if search_query:
            announcements = repo.search_scheduled(search_query)
        else:
            announcements = repo.get_all_scheduled()
        
        paginator = Paginator(announcements, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if search_query is not None and not form.is_valid:
            form = DraftListSearch()
        
    except Exception as e:
        messages.error(request, "An error occurred while loading scheduled announcements.")
        logger.exception("Failed to load scheduled announcements: %s", e)
        page_obj = None
    
    return render(request, "secretary/announcement/scheduled_list.html", {
        'page_path': f'{user_role} / Announcements / Scheduled',
        'page_title': 'Scheduled Announcements',
        'form': form,
        'page_obj': page_obj,
        'search_query': search_query,
        'search_url': 'secretary:ajax_announcement_scheduled_search',
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@require_GET
@inject
def ajax_announcement_scheduled_search(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")
    
    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key != "rows":
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    
    try:
        repo = announcement_service.announcement_repository
        
        if q:
            rows = repo.search_scheduled(q)[:50]
        else:
            rows = repo.get_all_scheduled()[:50]
        
    except Exception as e:
        logger.exception("ajax_announcement_scheduled_search error: %s", e)
        rows = []

    context = {"rows": rows}
    html = render_to_string("announcement/_scheduled_list.html", context, request=request)
    return HttpResponse(html)


@session_login_required
@role_required(SECRETARY_ROLE)
@require_http_methods(["POST"])
@inject
def ajax_cancel_scheduled_announcement(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> JsonResponse:
    """Cancel a scheduled announcement"""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return JsonResponse({'success': False, 'message': 'XHR only'}, status=400)
    
    try:
        announcement_id = int(request.POST.get('announcement_id', 0))
        if announcement_id <= 0:
            return JsonResponse({'success': False, 'message': 'Invalid announcement ID'}, status=400)
        
        repo = announcement_service.announcement_repository
        
        # Cancel the scheduled announcement
        success = repo.cancel_scheduled(announcement_id)
        
        if success:
            log_announcement_action(
                announcement_id=announcement_id,
                table_affected='announcement',
                action='CANCEL_SCHEDULED',
                performer_id=request.session.get('auth', {}).get('staff_id'),
                details=f"Scheduled announcement cancelled"
            )
            return JsonResponse({
                'success': True,
                'message': 'Announcement cancelled successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Failed to cancel announcement. It may not be in scheduled status.'
            }, status=400)
            
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid announcement ID'}, status=400)
    except Exception as e:
        logger.exception("ajax_cancel_scheduled_announcement error: %s", e)
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while cancelling the announcement'
        }, status=500)


# -------------------------------
# PUBLISHED ANNOUNCEMENTS
# -------------------------------
@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_published_list(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """List all published announcements"""
    user_role = _auth_role_name(request)
    
    form = DraftListSearch(request.GET or None)
    search_query = request.GET.get('search', '').strip()
    
    try:
        repo = announcement_service.announcement_repository
        
        if search_query:
            announcements = repo.search_published(search_query)
        else:
            announcements = repo.get_all_published()
        
        paginator = Paginator(announcements, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if search_query is not None and not form.is_valid:
            form = DraftListSearch()
        
    except Exception as e:
        messages.error(request, "An error occurred while loading published announcements.")
        logger.exception("Failed to load published announcements: %s", e)
        page_obj = None
    
    return render(request, "secretary/announcement/published_list.html", {
        'page_path': f'{user_role} / Announcements / Published',
        'page_title': 'Published Announcements',
        'form': form,
        'page_obj': page_obj,
        'search_query': search_query,
        'search_url': 'secretary:ajax_announcement_published_search',
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@require_GET
@inject
def ajax_announcement_published_search(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")
    
    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key != "rows":
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    
    try:
        repo = announcement_service.announcement_repository
        
        if q:
            rows = repo.search_published(q)[:50]
        else:
            rows = repo.get_all_published()[:50]
        
    except Exception as e:
        logger.exception("ajax_announcement_published_search error: %s", e)
        rows = []

    context = {"rows": rows}
    html = render_to_string("announcement/_published_list.html", context, request=request)
    return HttpResponse(html)


# -------------------------------
# EXPIRED ANNOUNCEMENTS
# -------------------------------
@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_expired_list(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """List all expired announcements"""
    user_role = _auth_role_name(request)
    
    form = DraftListSearch(request.GET or None)
    search_query = request.GET.get('search', '').strip()
    
    try:
        repo = announcement_service.announcement_repository
        
        if search_query:
            announcements = repo.search_expired(search_query)
        else:
            announcements = repo.get_all_expired()
        
        paginator = Paginator(announcements, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if search_query is not None and not form.is_valid:
            form = DraftListSearch()
        
    except Exception as e:
        messages.error(request, "An error occurred while loading expired announcements.")
        logger.exception("Failed to load expired announcements: %s", e)
        page_obj = None
    
    return render(request, "secretary/announcement/expired_list.html", {
        'page_path': f'{user_role} / Announcements / Expired',
        'page_title': 'Expired Announcements',
        'form': form,
        'page_obj': page_obj,
        'search_query': search_query,
        'search_url': 'secretary:ajax_announcement_expired_search',
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@require_GET
@inject
def ajax_announcement_expired_search(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")
    
    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key != "rows":
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    
    try:
        repo = announcement_service.announcement_repository
        
        if q:
            rows = repo.search_expired(q)[:50]
        else:
            rows = repo.get_all_expired()[:50]
        
    except Exception as e:
        logger.exception("ajax_announcement_expired_search error: %s", e)
        rows = []

    context = {"rows": rows}
    html = render_to_string("announcement/_expired_list.html", context, request=request)
    return HttpResponse(html)


# -------------------------------
# CANCELLED ANNOUNCEMENTS
# -------------------------------
@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def announcement_cancelled_list(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    """List all cancelled announcements"""
    user_role = _auth_role_name(request)
    
    form = DraftListSearch(request.GET or None)
    search_query = request.GET.get('search', '').strip()
    
    try:
        repo = announcement_service.announcement_repository
        
        if search_query:
            announcements = repo.search_cancelled(search_query)
        else:
            announcements = repo.get_all_cancelled()
        
        paginator = Paginator(announcements, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if search_query is not None and not form.is_valid:
            form = DraftListSearch()
        
    except Exception as e:
        messages.error(request, "An error occurred while loading cancelled announcements.")
        logger.exception("Failed to load cancelled announcements: %s", e)
        page_obj = None
    
    return render(request, "secretary/announcement/cancelled_list.html", {
        'page_path': f'{user_role} / Announcements / Cancelled',
        'page_title': 'Cancelled Announcements',
        'form': form,
        'page_obj': page_obj,
        'search_query': search_query,
        'search_url': 'secretary:ajax_announcement_cancelled_search',
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@require_GET
@inject
def ajax_announcement_cancelled_search(
    request: HttpRequest,
    announcement_service: IAnnouncementService = Provide[AppContainer.announcement_service],
) -> HttpResponse:
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")
    
    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key != "rows":
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    
    try:
        repo = announcement_service.announcement_repository
        
        if q:
            rows = repo.search_cancelled(q)[:50]
        else:
            rows = repo.get_all_cancelled()[:50]
        
    except Exception as e:
        logger.exception("ajax_announcement_cancelled_search error: %s", e)
        rows = []

    context = {"rows": rows}
    html = render_to_string("announcement/_cancelled_list.html", context, request=request)
    return HttpResponse(html)


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


# -------------------------------
# BLOTTER CASES (VIEW ONLY)
# -------------------------------

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def blotter_cases(request: HttpRequest):
    """
    View-only list of blotter cases for secretary.
    Similar to lupon_mem case_list but without add/edit capabilities.
    """
    user_role = _auth_role_name(request)
    
    # Get filter parameters
    q = (request.GET.get("q") or "").strip()
    state = (request.GET.get("state") or "").strip()
    settlement = (request.GET.get("settlement") or "").strip()
    filed_from = (request.GET.get("filed_from") or "").strip()
    filed_to = (request.GET.get("filed_to") or "").strip()
    per_page = int(request.GET.get("per_page") or 10)
    page = int(request.GET.get("page") or 1)
    
    # Build SQL query
    with connection.cursor() as cur:
        # Base query
        sql = """
            SELECT bc.blotter_case_id,
                   bc.blotter_case_num,
                   COALESCE(bc.blotter_case_name, 'Unnamed Case') AS case_name,
                   bc.date_filed,
                   bc.time_filed,
                   COALESCE(cs.case_state_name, 'OPEN') AS case_state,
                   COALESCE(ss.settlement_status_name, 'PENDING') AS settlement_status,
                   COALESCE(ct.complaint_title_name, '—') AS complaint_title,
                   COALESCE(cn.case_name, '—') AS case_nature
            FROM blotter_case bc
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            WHERE 1=1
        """
        params = []
        
        # Add filters
        if q:
            sql += " AND (bc.blotter_case_num ILIKE %s OR bc.blotter_case_name ILIKE %s)"
            params.extend([f"%{q}%", f"%{q}%"])
        
        if state:
            sql += " AND UPPER(cs.case_state_name) = UPPER(%s)"
            params.append(state)
        
        if settlement:
            sql += " AND UPPER(ss.settlement_status_name) = UPPER(%s)"
            params.append(settlement)
        
        if filed_from:
            sql += " AND bc.date_filed >= %s"
            params.append(filed_from)
        
        if filed_to:
            sql += " AND bc.date_filed <= %s"
            params.append(filed_to)
        
        sql += " ORDER BY bc.date_filed DESC, bc.blotter_case_id DESC"
        
        # Get total count
        count_sql = f"SELECT COUNT(*) FROM ({sql}) AS subq"
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]
        
        # Add pagination
        offset = (page - 1) * per_page
        sql += f" LIMIT {per_page} OFFSET {offset}"
        
        cur.execute(sql, params)
        rows = cur.fetchall()
        
        # Get filter choices
        cur.execute("SELECT DISTINCT case_state_name FROM case_state ORDER BY case_state_name")
        state_choices = [r[0] for r in cur.fetchall()]
        
        cur.execute("SELECT DISTINCT settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
        settlement_choices = [r[0] for r in cur.fetchall()]
    
    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    prev_page = page - 1 if has_prev else 1
    next_page = page + 1 if has_next else total_pages
    first_item = offset + 1 if total > 0 else 0
    last_item = min(offset + per_page, total)
    
    # Page numbers for pagination
    page_numbers = []
    if total_pages <= 7:
        page_numbers = list(range(1, total_pages + 1))
    else:
        if page <= 4:
            page_numbers = list(range(1, 6)) + [total_pages]
        elif page >= total_pages - 3:
            page_numbers = [1] + list(range(total_pages - 4, total_pages + 1))
        else:
            page_numbers = [1] + list(range(page - 1, page + 2)) + [total_pages]
    
    # Build query string without page
    query_parts = []
    if q:
        query_parts.append(f"q={q}")
    if state:
        query_parts.append(f"state={state}")
    if settlement:
        query_parts.append(f"settlement={settlement}")
    if filed_from:
        query_parts.append(f"filed_from={filed_from}")
    if filed_to:
        query_parts.append(f"filed_to={filed_to}")
    query_parts.append(f"per_page={per_page}")
    query_no_page = "&".join(query_parts)
    
    return render(request, "secretary/blotter_cases.html", {
        'page_path': f'{user_role} / Blotter Cases',
        'page_title': 'Blotter Cases',
        'rows': rows,
        'q': q,
        'state': state,
        'settlement': settlement,
        'filed_from': filed_from,
        'filed_to': filed_to,
        'per_page': per_page,
        'page': page,
        'total': total,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_page': prev_page,
        'next_page': next_page,
        'first_item': first_item,
        'last_item': last_item,
        'page_numbers': page_numbers,
        'query_no_page': query_no_page,
        'state_choices': state_choices,
        'settlement_choices': settlement_choices,
    })


# -------------------------------
# INCIDENT HEATMAP
# -------------------------------

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
def incident_heatmap(request: HttpRequest):
    """
    Display comprehensive barangay incident heatmap with advanced analytics and filtering.
    """
    from django.db import connection
    import json
    
    # Get filter parameters
    time_filter = request.GET.get('time_filter', '1_year')
    case_type_filter = request.GET.get('case_type', 'all')
    settlement_filter = request.GET.get('settlement', 'all')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    # Build time filter condition (reports)
    time_conditions = {
        '1_month': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '1 month'",
        '3_months': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '3 months'",
        '6_months': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '6 months'",
        '1_year': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '1 year'",
        'all': "",
        'custom': ""
    }
    
    # Handle custom date range
    if time_filter == 'custom' and start_date and end_date:
        time_condition = f"AND br.date_time_reported::date BETWEEN '{start_date}' AND '{end_date}'"
        case_time_condition = f"AND bc.date_filed::date BETWEEN '{start_date}' AND '{end_date}'"
    else:
        time_condition = time_conditions.get(time_filter, time_conditions['1_year'])
        # Build time filter condition (cases)
        case_time_conditions = {
            '1_month': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '1 month'",
            '3_months': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '3 months'",
            '6_months': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '6 months'",
            '1_year': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '1 year'",
            'all': "",
            'custom': ""
        }
        case_time_condition = case_time_conditions.get(time_filter, case_time_conditions['1_year'])

    # Build case type filter (parameterized)
    case_type_condition = ""
    case_type_params = []
    if case_type_filter != 'all':
        case_type_condition = "AND ct.complaint_title_name = %s"
        case_type_params.append(case_type_filter)

    # Build settlement filter
    settlement_condition = ""
    if settlement_filter == 'settled':
        settlement_condition = "AND UPPER(ss.settlement_status_name) = 'SETTLED'"
    elif settlement_filter == 'pending':
        settlement_condition = "AND (ss.settlement_status_name IS NULL OR UPPER(ss.settlement_status_name) = 'PENDING')"
    elif settlement_filter == 'not_settled':
        settlement_condition = "AND UPPER(ss.settlement_status_name) = 'NOT SETTLED'"

    with connection.cursor() as cur:
        # ---------- 1) Incident rows ----------
        sql_incidents = f"""
            WITH incident_data AS (
                -- Blotter Reports (not yet converted to cases)
                SELECT 
                    'BR-' || br.blotter_report_id as incident_id,
                    COALESCE(br.incident_subject, 'Unnamed Incident') as incident_name,
                    COALESCE(br.incident_desc, 'No description') as incident_desc,
                    br.date_time_reported::date as date_filed,
                    br.date_time_reported::time as time_filed,
                    a.latitude,
                    a.longitude,
                    COALESCE(a.street, 'Unknown Street') as street,
                    COALESCE(a.barangay, 'Unknown Barangay') as barangay,
                    COALESCE(ps.purok_sitio_name, 'Unknown Purok') as purok,
                    'Blotter Report' as incident_type,
                    'Pending Review' as case_status,
                    'Not Applicable' as settlement_status,
                    COALESCE(pst.payment_status_name, 'Unpaid') as payment_status,
                    'Low' as severity_level,
                    br.date_time_reported as created_at,
                    '' as case_nature
                FROM blotter_report br
                LEFT JOIN addresss a ON a.address_id = br.incident_address_id
                LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                LEFT JOIN payment_status pst ON pst.payment_status_id = br.payment_status_id
                WHERE a.latitude IS NOT NULL 
                  AND a.longitude IS NOT NULL
                  {time_condition}
                  
                UNION ALL
                
                -- Blotter Cases (converted from reports or direct cases) - DEFAULT TO BARANGAY CASES ONLY
                SELECT 
                    'BC-' || bc.blotter_case_id as incident_id,
                    COALESCE(bc.blotter_case_name, 'Unnamed Case') as incident_name,
                    COALESCE(bc.incident_desc, 'No description') as incident_desc,
                    bc.date_filed::date as date_filed,
                    bc.time_filed as time_filed,
                    a.latitude,
                    a.longitude,
                    COALESCE(a.street, 'Unknown Street') as street,
                    COALESCE(a.barangay, 'Unknown Barangay') as barangay,
                    COALESCE(ps.purok_sitio_name, 'Unknown Purok') as purok,
                    COALESCE(ct.complaint_title_name, 'General Complaint') as incident_type,
                    COALESCE(cs.case_state_name, 'Open') as case_status,
                    COALESCE(ss.settlement_status_name, 'Pending') as settlement_status,
                    'Paid' as payment_status,
                    CASE 
                        WHEN UPPER(ss.settlement_status_name) = 'SETTLED' THEN 'Low'
                        WHEN UPPER(cs.case_state_name) = 'CLOSED' THEN 'Medium'
                        WHEN bc.date_filed < CURRENT_DATE - INTERVAL '6 months' AND UPPER(ss.settlement_status_name) != 'SETTLED' THEN 'High'
                        ELSE 'Medium'
                    END as severity_level,
                    COALESCE(bc.date_filed::timestamp, CURRENT_TIMESTAMP) as created_at,
                    COALESCE(cn.case_name, '') as case_nature
                FROM blotter_case bc
                LEFT JOIN addresss a ON a.address_id = (
                    SELECT br.incident_address_id 
                    FROM blotter_report br 
                    WHERE br.blotter_report_id = bc.blotter_report_id
                    LIMIT 1
                )
                LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                WHERE a.latitude IS NOT NULL 
                  AND a.longitude IS NOT NULL
                  AND bc.date_filed >= CURRENT_DATE - INTERVAL '2 years'
                  {case_time_condition}
                  {case_type_condition}
                  {settlement_condition}
            )
            SELECT * FROM incident_data
            ORDER BY created_at DESC, incident_id
            LIMIT 1000
        """

        cur.execute(sql_incidents, case_type_params)
        incidents = cur.fetchall()

        # ---------- 2) Stats by incident type ----------
        sql_stats = f"""
            WITH stats_data AS (
                SELECT 
                    COALESCE(ct.complaint_title_name, 'General Complaint') as incident_type,
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN UPPER(ss.settlement_status_name) = 'SETTLED' THEN 1 END) as settled_count,
                    COUNT(CASE WHEN UPPER(cs.case_state_name) = 'CLOSED' THEN 1 END) as closed_count,
                    COUNT(CASE WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL THEN 1 END) as mapped_count,
                    AVG(
                        CASE 
                            WHEN bc.date_filed IS NOT NULL AND ss.settlement_status_id IS NOT NULL
                            THEN (CURRENT_DATE::date - bc.date_filed::date)
                            ELSE NULL
                        END
                    ) AS avg_resolution_days
                FROM blotter_case bc
                LEFT JOIN addresss a ON a.address_id = (
                    SELECT br.incident_address_id 
                    FROM blotter_report br 
                    WHERE br.blotter_report_id = bc.blotter_report_id
                    LIMIT 1
                )
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                WHERE bc.date_filed >= CURRENT_DATE - INTERVAL '2 years'
                {case_time_condition}
                GROUP BY ct.complaint_title_name
                
                UNION ALL
                
                SELECT 
                    'Blotter Report' as incident_type,
                    COUNT(*) as total_count,
                    0 as settled_count,
                    0 as closed_count,
                    COUNT(CASE WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL THEN 1 END) as mapped_count,
                    NULL as avg_resolution_days
                FROM blotter_report br
                LEFT JOIN addresss a ON a.address_id = br.incident_address_id
                WHERE 1=1
                {time_condition}
            )
            SELECT incident_type, total_count, settled_count, closed_count, mapped_count, avg_resolution_days
            FROM stats_data
            WHERE total_count > 0
            ORDER BY total_count DESC
        """

        cur.execute(sql_stats)
        incident_stats = cur.fetchall()

        # ---------- 2b) Summary counts for headers ----------
        # Total blotter reports (apply selected time filter)
        cur.execute(f"SELECT COUNT(*) FROM blotter_report br WHERE 1=1 {time_condition}")
        blotter_reports_count = cur.fetchone()[0]

        # Total blotter cases (base window 2 years + selected time filter)
        cur.execute(f"SELECT COUNT(*) FROM blotter_case bc WHERE bc.date_filed >= CURRENT_DATE - INTERVAL '2 years' {case_time_condition}")
        blotter_cases_count = cur.fetchone()[0]

        # ---------- 3) Street-level stats ----------
        sql_streets = """
            SELECT 
                COALESCE(a.street, 'Unknown Street') as street_name,
                COALESCE(a.barangay, 'Unknown Barangay') as barangay_name,
                COUNT(*) as incident_count,
                COUNT(CASE WHEN UPPER(ss.settlement_status_name) = 'SETTLED' THEN 1 END) as settled_count,
                COUNT(CASE WHEN bc.date_filed >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as recent_count,
                MAX(bc.date_filed) as last_incident_date
            FROM blotter_case bc
            LEFT JOIN addresss a ON a.address_id = (
                SELECT br.incident_address_id 
                FROM blotter_report br 
                WHERE br.blotter_report_id = bc.blotter_report_id
                LIMIT 1
            )
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE a.latitude IS NOT NULL 
              AND a.longitude IS NOT NULL
              AND bc.date_filed >= CURRENT_DATE - INTERVAL '1 year'
            GROUP BY a.street, a.barangay
            HAVING COUNT(*) >= 1
            ORDER BY incident_count DESC, recent_count DESC
            LIMIT 25
        """

        cur.execute(sql_streets)
        street_stats = cur.fetchall()

        # ---------- 4) Case type options ----------
        cur.execute("""
            SELECT DISTINCT ct.complaint_title_name
            FROM complaint_title ct
            JOIN blotter_case bc ON bc.complaint_title_id = ct.complaint_title_id
            WHERE bc.date_filed >= CURRENT_DATE - INTERVAL '2 years'
            ORDER BY ct.complaint_title_name
        """)
        case_types = [row[0] for row in cur.fetchall()]

    # -------- Format payloads for the template --------
    incident_data = []

    for incident in incidents:
        incident_item = {
            'id': incident[0],
            'name': incident[1] or 'Unnamed Incident',
            'description': incident[2] or 'No description',
            'date': incident[3].strftime('%Y-%m-%d') if incident[3] else '',
            'time': str(incident[4]) if incident[4] else '',
            'lat': float(incident[5]) if incident[5] else 0,
            'lng': float(incident[6]) if incident[6] else 0,
            'street': incident[7] or 'Unknown Street',
            'barangay': incident[8] or 'Unknown Barangay',
            'purok': incident[9] or 'Unknown Purok',
            'type': incident[10] or 'Unknown Type',
            'case_status': incident[11] or 'Unknown Status',
            'settlement_status': incident[12] or 'Pending',
            'payment_status': incident[13] or 'Unknown',
            'severity': incident[14] or 'Medium',
            'created_at': incident[15].strftime('%Y-%m-%d %H:%M') if incident[15] else '',
            'case_nature': incident[16] if len(incident) > 16 else ''
        }
        incident_data.append(incident_item)
    
    stats_data = []
    for stat in incident_stats:
        settlement_rate = round((stat[2] / stat[1] * 100) if stat[1] > 0 else 0, 1)
        avg_days = round(stat[5]) if stat[5] is not None else None
        stats_data.append({
            'type': stat[0],
            'total_count': stat[1],
            'settled_count': stat[2],
            'closed_count': stat[3],
            'mapped_count': stat[4],
            'settlement_rate': settlement_rate,
            'avg_resolution_days': avg_days,
            'efficiency_score': min(100, max(0, 100 - (avg_days or 30) + settlement_rate)) if avg_days is not None else settlement_rate
        })

    street_data = []
    for street in street_stats:
        settlement_rate = round((street[3] / street[2] * 100) if street[2] > 0 else 0, 1)
        street_data.append({
            'street': street[0],
            'barangay': street[1],
            'incident_count': street[2],
            'settled_count': street[3],
            'recent_count': street[4],
            'settlement_rate': settlement_rate,
            'last_incident': street[5].strftime('%Y-%m-%d') if street[5] else 'N/A',
            'risk_level': 'High' if street[4] >= 3 else 'Medium' if street[4] >= 1 else 'Low'
        })

    user_role = _auth_role_name(request)
    return render(request, "secretary/incident_heatmap.html", {
        "incident_data_json": json.dumps(incident_data),
        "incident_data": incident_data,
        "incident_stats": json.dumps(stats_data),  # For JavaScript charts
        "street_stats": street_data,
        "blotter_reports_count": blotter_reports_count,
        "blotter_cases_count": blotter_cases_count,
        "case_types": case_types,
        "time_filter": time_filter,
        "case_type_filter": case_type_filter,
        "settlement_filter": settlement_filter,
        "start_date": start_date,
        "end_date": end_date,
        'page_path': f'{user_role} / Incident Heatmap',
        'page_title': 'Barangay Incident Heatmap & Analytics',
    })
    