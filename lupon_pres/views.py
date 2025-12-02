# lupon_pres/views.py
from __future__ import annotations

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
from django.db import connection

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

from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer

# Supabase upload helper you already use elsewhere
from common.supabase_client import supabase
from common.services.storage import upload_to_storage

# Flash helpers
from common.flash import flash_success, flash_warning, flash_db_error, flash_system_error
from common.email_validator import verify_email_deliverable_abstract
from django.db import DatabaseError, OperationalError, IntegrityError
from common.db_errors import _pg_err_tuple

logger = logging.getLogger(__name__)

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

ROLE_LUPON = 8
WZ_KEY = "lpres_nonres_wizard"

# App/role for guard
LUPON_PRES_ROLE = "Barangay Lupon President"

STAFF_FILTER_SESSION_KEY = "lupon_pres_member_filters"

DAY_LABELS = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

# Buckets
BUCKET_FINAL = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
BUCKET_STAFF_PROOF = getattr(settings, "SUPABASE_STAFF_PROOF_BUCKET", "staff-proof")


def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

# --- Dashboard ---
@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
@inject
def dashboard(
    request: HttpRequest,
    lupon_mem_dashboard_service=Provide[AppContainer.lupon_mem_dashboard_service],
):
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    person_id = auth.get('person_id')

    kpis = {
        "ongoing_cases": 0,
        "open_cases": None,
        "total_case_settled": 0,
        "total_case_settled_delta": None,
        "total_case_unsettled": 0,
        "total_case_unsettled_delta": None,
        "settlement_rate": 0,
    }

    dashboard_json = None
    announcements = []

    try:
        payload = lupon_mem_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json") 
    except Exception as exc:
        print("Error fetching lupon mem dashboard KPIs:", exc)

    # Get filter options for modal
    with connection.cursor() as cur:
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()
    
    if person_id:
        try:
            from authentication.announcement_views import get_user_announcements
            announcements = get_user_announcements(person_id)
        except Exception as exc:
            print(f"Error fetching announcements for person {person_id}:", exc)

    return render(
        request,
        "lupon_pres/dashboard.html",
        {
            'page_path' : f'{user_role} / Dashboard',
            'page_title' : 'Dashboard',
            'kpis': kpis,
            'dashboard_json': dashboard_json,
            'today': datetime.now().strftime("%B %d, %Y"),
            'announcements': announcements,
            'complaint_titles': complaint_titles,
            'case_natures': case_natures,
        },
    )


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


def _format_birthdate_display(*values: Any) -> str:
    for raw in values:
        if not raw:
            continue

        birth_dt: Optional[date] = None
        if isinstance(raw, datetime):
            birth_dt = raw.date()
        elif isinstance(raw, date):
            birth_dt = raw
        else:
            txt = str(raw).strip()
            if not txt:
                continue
            try:
                birth_dt = date.fromisoformat(txt[:10])
            except Exception:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        birth_dt = datetime.strptime(txt, fmt).date()
                        break
                    except Exception:
                        continue
            if birth_dt is None:
                return txt

        if birth_dt is not None:
            return birth_dt.strftime("%B %d, %Y")

    return ""

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

# Image preprocessing (autorotate + compress)
def _pil_autorotate_and_jpeg(file_obj, *, max_w=2200, max_h=2200, quality=85) -> BytesIO:
    try:
        from PIL import Image, ImageOps
        file_obj.seek(0)
        img = Image.open(file_obj)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_w, max_h))
        buf = BytesIO()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=85, optimize=True)
        buf.seek(0)
        return buf
    except Exception:
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return file_obj

def _prep_image_for_upload(file_obj, *, max_w=2200, max_h=2200):
    """Return (buf, mime, ext). Keep PNG if has alpha, else JPEG."""
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


def _only_lupon_members(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter helper to keep only Barangay Lupon members."""
    if not rows:
        return []
    target = []
    for row in rows:
        role_id = str(row.get("role_id") or "")
        role_name = (row.get("role_name") or "").strip().upper()
        if role_id == str(ROLE_LUPON) or role_name == "BARANGAY LUPON MEMBER":
            target.append(row)
    return target


def _load_lupon_summary() -> List[Dict[str, Any]]:
    try:
        all_rows = Secretary.get_all_staff_info_summary() or []
    except Exception as exc:
        logger.exception("Failed to load staff summaries: %s", exc)
        return []
    return _only_lupon_members(all_rows)


def _matches_account(row: Dict[str, Any], status_code: str, *, status_label: str | None = None) -> bool:
    if not status_code:
        return True
    row_id = row.get("account_status_id")
    if row_id is not None and str(row_id) == status_code:
        return True
    if status_label:
        row_label = (row.get("account_status") or "").strip().lower()
        if row_label and row_label == status_label.strip().lower():
            return True
    return False


def _matches_day(row: Dict[str, Any], day_id: int | None) -> bool:
    if not day_id:
        return True
    day_name = DAY_LABELS.get(day_id)
    tokens = set()
    if day_name:
        tokens.add(day_name.strip().lower())
        tokens.add(day_name[:3].lower())

    labels = row.get("sched_labels") or []
    if isinstance(labels, str):
        labels = [labels]
    if isinstance(labels, (list, tuple)):
        for label in labels:
            lower = (label or "").strip().lower()
            if not lower:
                continue
            if any(tok in lower for tok in tokens if tok):
                return True

    # Fallback to richer schedule payloads if present
    schedules = row.get("lupon_schedule") or row.get("schedules") or []
    if isinstance(schedules, (list, tuple)):
        for sched in schedules:
            try:
                sched_day = int(sched.get("day"))
            except Exception:
                continue
            if sched_day == day_id:
                return True

    raw_day = row.get("schedule_day_id") or row.get("sched_day_id")
    try:
        if raw_day is not None and int(raw_day) == day_id:
            return True
    except Exception:
        pass

    return False


def _filter_member_rows(
    rows: List[Dict[str, Any]],
    *,
    day_id: int | None = None,
    account_code: str | None = None,
    account_label: str | None = None,
    search_term: str | None = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    needle = (search_term or "").strip().lower()
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if day_id and not _matches_day(row, day_id):
            continue
        if account_code and not _matches_account(row, account_code, status_label=account_label):
            continue
        if needle and needle not in (row.get("full_name") or "").lower():
            continue
        filtered.append(row)
    return filtered


def _account_status_label_for(code: str | None) -> str | None:
    if not code:
        return None
    try:
        field = StaffFilters().fields.get("account_stat")
        if not field:
            return None
        for key, label in field.choices:
            if str(key) == str(code):
                return label
    except Exception:
        return None
    return None

# Retry upload wrapper (same semantics you use elsewhere)
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
                logger.warning(
                    "Upload transient error (%s). Retrying in %.2fs [%d/%d]…",
                    msg, sleep_s, attempt + 1, max_retries
                )
                _time.sleep(sleep_s)
                continue
            last_err = e
            break
    raise last_err


# ───────────────────────────────────────────────────────────────────────────────
# Views
# ───────────────────────────────────────────────────────────────────────────────

# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
def staff_selection(request: HttpRequest) -> HttpResponse:
    user_fullname, user_role, user_role_template = get_user_info(request)
    # Landing selector (Resident vs Non-Resident)
    return render(request, "members/staff_selection.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
    })


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
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


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
@require_http_methods(["GET", "POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:

    pid = (request.POST.get("pid") or "").strip()
    # role_str = (request.POST.get("role") or "").strip()
    role_id = ROLE_LUPON

    proof_url = (request.POST.get("proof") or "").strip() or None
    if proof_url and not proof_url.startswith(("http://", "https://", "data:")):
        logger.warning("Ignoring non-URL, non-data proof value: %r", proof_url)
        proof_url = None

    proof_file = None
    if hasattr(request, "FILES"):
        proof_file = (
            request.FILES.get("proof")
            or request.FILES.get("proof_file")
            or request.FILES.get("file")
            or None
        )

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
    staff_id = auth.get("staff_id") or 16
    # fallback demo

    # Handle POST
    if request.method == "POST" and pid:
        # basic completeness gate
        if not (pid or role_id or proof_file or proof_url or request.POST.get("day") or request.POST.getlist("day[]")):
            flash_warning(request, "Please select a resident and fill out the form before submitting.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        # if not staff_id:
        #     flash_warning(request, "Your session is missing staff credentials.")
        #     return redirect(request.META.get("HTTP_REFERER") or request.path)

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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if proof_file:
            try:
                buf, mime, ext = _prep_image_for_upload(proof_file)
                proof_rel_path = f"{final_base}/staff-app-proof-{role_id}-{timestamp}.{ext}"
                res_up = _upload_to_storage_retry(
                    buf,
                    path=proof_rel_path,
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,
                )
                if isinstance(res_up, dict):
                    uploaded_proof_url = res_up.get("public_url") or res_up.get("signed_url")
                else:
                    uploaded_proof_url = None
                if not uploaded_proof_url:
                    flash_system_error(request, "Proof upload did not return a usable URL.")
                    return redirect(request.META.get("HTTP_REFERER") or request.path)
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
                import base64 as _b64

                _mime_hint, b64 = m.groups()
                raw = io.BytesIO(_b64.b64decode(b64))
                buf, mime, ext = _prep_image_for_upload(raw)
                proof_rel_path = f"{final_base}/staff-app-proof-{role_id}-{timestamp}.{ext}"
                res_up = _upload_to_storage_retry(
                    buf,
                    path=proof_rel_path,
                    bucket=BUCKET_FOR_PROOF,
                    content_type=mime,
                    make_public=True,
                )
                if isinstance(res_up, dict):
                    uploaded_proof_url = res_up.get("public_url") or res_up.get("signed_url")
                else:
                    uploaded_proof_url = None
                if not uploaded_proof_url:
                    flash_system_error(request, "Proof upload did not return a usable URL.")
                    return redirect(request.META.get("HTTP_REFERER") or request.path)
            else:
                uploaded_proof_url = proof_url

        if uploaded_proof_url and not uploaded_proof_url.startswith(("http://", "https://")):
            flash_system_error(request, "Proof upload failed to produce a valid URL.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

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
            addr_parts: List[str] = []
            for key in ("street_name", "purok_sitio_name", "barangay_name", "city_name"):
                val = res_details.get(key)
                if val is None:
                    continue
                val_str = str(val).strip()
                if val_str:
                    addr_parts.append(val_str)
            res_details["address_parts"] = addr_parts

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

    user_fullname, user_role, user_role_template = get_user_info(request)
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



# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
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
            
            # Validate email if provided
            email_value = cd.get("email") or ""
            if email_value:
                is_valid, reason = verify_email_deliverable_abstract(email_value)
                if not is_valid:
                    flash_warning(request, f"Email validation failed: {reason}. Please provide a valid email address.")
                    return redirect(request.path)
            
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
                "province":  cd.get("province") or "",
                "barangay":  cd.get("barangay") or "",
                "sitio_purok": cd.get("purok_sitio") or "",
                "street":    cd.get("street") or "",
            })
            flash_success(request, "Personal information saved successfully.")
            return redirect("lupon_pres:staff_selection_non-resident_docs")
        else:
            flash_warning(request, "Please correct the errors below.")

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "members/staff_selection_nonresident.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "form": form,
        "redirect": "lupon_pres:staff_selection_non-resident_docs",
    })


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
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

        # flash_success(request, "Documents loaded for preview. Please review and choose role.")
        return redirect("lupon_pres:staff_selection_non-resident_role_review")

    user_fullname, user_role, user_role_template = get_user_info(request)
    return render(request, "members/supporting_docs.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "form": form,
    })


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
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

        personal_display = dict(personal)
        birth_display = _format_birthdate_display(
            personal_display.get("birthdate"),
            personal_display.get("date_of_birth"),
        )
        if birth_display:
            personal_display["birthdate_display"] = birth_display

        user_fullname, user_role, user_role_template = get_user_info(request)
        return render(request, "members/schedule.html", {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Account Verification",
            "page_title": "Account Verification",
            "user_role_template": user_role_template,
            "role_form": role_form,
            "sched_form": sched_form,
            "personal": personal_display,
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
    staff_id = auth.get("staff_id") or 16
    
    # if not staff_id:
    #     flash_warning(request, "Your session is missing staff credentials.")
    #     return redirect(request.META.get("HTTP_REFERER") or request.path)

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

        proof_url = None
        if b_proof is not None:
            p_buf, p_mime, p_ext = _prep_image_for_upload(io.BytesIO(b_proof))
            proof_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            proof_rel_path = f"{proof_final_base}/staff-app-proof-{role_id}-{proof_timestamp}.{p_ext}"
            up_proof = _upload_to_storage_retry(
                p_buf,
                path=proof_rel_path,
                bucket=BUCKET_STAFF_PROOF,
                content_type=p_mime,
                make_public=True,
            )
            if isinstance(up_proof, dict):
                proof_url = up_proof.get("public_url") or up_proof.get("signed_url")
            if not proof_url:
                flash_system_error(request, "Proof upload did not return a usable URL. Please try again.")
                return redirect(request.path)
    except Exception as e:
        flash_system_error(request, "Final upload failed.", exc=e)
        return redirect(request.path)

    front_url = up_front.get("public_url") or up_front.get("signed_url")
    back_url  = up_back.get("public_url") or up_back.get("signed_url")
    self_url  = up_selfie.get("public_url") or up_selfie.get("signed_url")
    if proof_url and not proof_url.startswith(("http://", "https://")):
        flash_system_error(request, "Proof upload failed to produce a valid URL.")
        return redirect(request.path)

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
            p_province=personal.get("province"),
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


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
def members_list(request: HttpRequest) -> HttpResponse:
    filters = request.session.get(STAFF_FILTER_SESSION_KEY, {}) or {}
    filters = dict(filters)

    day_raw = (filters.get("day") or "").strip()
    acc_raw = (filters.get("account_stat") or "").strip()
    search_term = (filters.get("q") or "").strip()

    updated = False
    should_redirect = False

    if "clear_filters" in request.GET:
        day_raw = ""
        acc_raw = ""
        search_term = ""
        updated = True
        should_redirect = True

    remove_target = (request.GET.get("remove_filter") or "").strip()
    if remove_target:
        if remove_target == "day":
            day_raw = ""
        elif remove_target == "account_stat":
            acc_raw = ""
        elif remove_target == "search":
            search_term = ""
        updated = True
        should_redirect = True

    if "day" in request.GET:
        day_raw = (request.GET.get("day") or "").strip()
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

    if updated or not filters:
        filters.update({
            "day": day_raw,
            "account_stat": acc_raw,
            "q": search_term,
        })
        request.session[STAFF_FILTER_SESSION_KEY] = filters
        request.session.modified = True

    if should_redirect:
        return redirect(request.path)

    day_id = int(day_raw) if day_raw.isdigit() else None
    account_label = _account_status_label_for(acc_raw)

    base_rows = _load_lupon_summary()
    rows = _filter_member_rows(
        base_rows,
        day_id=day_id,
        account_code=acc_raw or None,
        account_label=account_label,
        search_term=search_term,
    )

    from django.core.paginator import Paginator
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

    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(page_number)

    day_initial = int(day_raw) if day_raw.isdigit() else None
    form_initial = {
        "search": search_term,
        "day": day_initial,
        "account_stat": acc_raw,
    }
    form = StaffFilters(initial=form_initial)

    day_choices = {str(k): v for k, v in form.fields["day"].choices if str(k)}
    acc_choices = {str(k): v for k, v in form.fields["account_stat"].choices}

    active_filters: List[Dict[str, str]] = []
    if day_raw:
        label = day_choices.get(day_raw) or f"Day {day_raw}"
        active_filters.append({
            "label": f"Day: {label}",
            "remove_url": f"{request.path}?remove_filter=day",
        })
    if acc_raw:
        label = acc_choices.get(acc_raw) or f"Status {acc_raw}"
        active_filters.append({
            "label": f"Status: {label}",
            "remove_url": f"{request.path}?remove_filter=account_stat",
        })
    if search_term:
        active_filters.append({
            "label": f'Search: "{search_term}"',
            "remove_url": f"{request.path}?remove_filter=search",
        })

    clear_filters_url = f"{request.path}?clear_filters=1"
    current_filters = {
        "day": day_raw,
        "account_stat": acc_raw,
        "q": search_term,
    }

    user_fullname, user_role, user_role_template = get_user_info(request)

    return render(request, "members/members_list.html", {
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
        "has_panel_filters": bool(day_raw or acc_raw),
    })



# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
@require_GET
def staff_search_api(request: HttpRequest):
    raw_query = (request.GET.get("q") or "").strip()

    filters = request.session.get(STAFF_FILTER_SESSION_KEY, {}) or {}
    filters = dict(filters)

    day_raw = (filters.get("day") or "").strip()
    acc_raw = (filters.get("account_stat") or "").strip()

    day_id = int(day_raw) if day_raw.isdigit() else None
    account_label = _account_status_label_for(acc_raw)

    try:
        base_rows = _load_lupon_summary()
        rows = _filter_member_rows(
            base_rows,
            day_id=day_id,
            account_code=acc_raw or None,
            account_label=account_label,
            search_term=raw_query,
        )
    except Exception as exc:
        logger.exception("staff_search_api error: %s", exc)
        return JsonResponse({"results": [], "error": "Search failed"}, status=500)

    filters.update({
        "q": raw_query,
    })
    request.session[STAFF_FILTER_SESSION_KEY] = filters
    request.session.modified = True

    return JsonResponse({"results": rows[:50]})


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
@require_GET
def staff_filter_api(request: HttpRequest):
    day_raw = (request.GET.get("day_id") or "").strip()
    acc_raw = (request.GET.get("account_status_id") or "").strip()

    day_id = int(day_raw) if day_raw.isdigit() else None
    account_label = _account_status_label_for(acc_raw)

    try:
        base_rows = _load_lupon_summary()
        rows = _filter_member_rows(
            base_rows,
            day_id=day_id,
            account_code=acc_raw or None,
            account_label=account_label,
        )
        return JsonResponse({"results": rows})
    except Exception as exc:
        logger.exception("staff_filter_api error: %s", exc)
        return JsonResponse({"results": [], "error": "Filter failed"}, status=500)


# @session_login_required
# @role_required(LUPON_PRES_ROLE)
# @nocache
@require_http_methods(["GET", "POST"])
def member_dets(request: HttpRequest, staff_code: str) -> HttpResponse:
    
    # Handle POST request for schedule updates
    if request.method == "POST":
        auth = request.session.get("auth") or {}
        updated_by_staff_id = auth.get("staff_id")
        
        # if not updated_by_staff_id:
        #     flash_warning(request, "Your session is missing staff credentials.")
        #     return redirect(request.path)
        
        # Get staff_id from profile
        try:
            rows = Secretary.get_staff_profile_display(staff_code) if staff_code else []
            current_staff = rows[0] if rows else None
            
            if not current_staff:
                flash_warning(request, "Staff not found.")
                return redirect("lupon_pres:members_list")
            
            staff_id = current_staff.get("staff_id")
            if not staff_id:
                flash_warning(request, "Staff ID not found.")
                return redirect("lupon_pres:members_list")
        except Exception as e:
            flash_system_error(request, "Error loading staff data.", exc=e)
            return redirect(request.path)
        
        schedules = []
        
        # Collect schedule data from form
        days = request.POST.getlist("schedule_day[]")
        starts = request.POST.getlist("schedule_time_start[]")
        ends = request.POST.getlist("schedule_time_end[]")
        
        for day, start, end in zip(days, starts, ends):
            if day and start and end:
                schedules.append({
                    "day": int(day),
                    "time_start": start,
                    "time_end": end
                })
        
        # Update schedule in database
        try:
            from .models import LuponPres
            result = LuponPres.update_staff_assigned_sched(
                staff_id=staff_id,
                updated_by_staff_id=updated_by_staff_id,
                schedules_json=schedules
            )
            
            if result:
                added = result.get('sched_added_count', 0)
                removed = result.get('sched_removed_count', 0)
                if added > 0 or removed > 0:
                    flash_success(request, f"Schedule updated successfully. Added: {added}, Removed: {removed}")
                else:
                    flash_warning(request, "No changes were made to the schedule.")
            else:
                flash_warning(request, "Schedule update completed but no result returned.")
        except Exception as e:
            flash_system_error(request, "Failed to update schedule.", exc=e)
        
        return redirect("lupon_pres:mem_details", staff_code=staff_code)

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

    # Process schedule data like staff_admin
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

    # Day choices for the form
    from .forms import DAY_CHOICES
    day_choices = DAY_CHOICES

    user_fullname, user_role, user_role_template = get_user_info(request)
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
        "schedule_list": schedule_list,
        "day_choices": day_choices,
    })


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

# Staff requests views
@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
def staff_requests_list(request: HttpRequest) -> HttpResponse:
    """View staff account requests submitted by this lupon president"""
    from common.staff_request_views_simple import staff_requests_list_view
    return staff_requests_list_view(request, "lupon_pres", "lupon_pres/requests_list.html")

@session_login_required
@role_required(LUPON_PRES_ROLE)
@nocache
def staff_request_detail(request: HttpRequest, request_id: int) -> HttpResponse:
    """View detailed information about a specific staff request"""
    from common.staff_request_views_simple import staff_request_detail_view
    return staff_request_detail_view(request, request_id, "lupon_pres", "lupon_pres/request_detail.html")