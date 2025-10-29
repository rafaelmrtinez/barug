# staff_admin/views.py
from __future__ import annotations
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.templatetags.static import static
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods, require_GET
from django.db import DatabaseError, OperationalError, IntegrityError, connection
from typing import Any, Dict, List, Optional
import logging
import secrets
import string
import re
import io
import base64
from datetime import datetime, time as dtime, date

# External modules / app models
import secretary
from secretary.models import Secretary
from captain.models import Captain
from staff_admin.models import Admin

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.flash import flash_success, flash_warning, flash_system_error, flash_db_error
from common.send_email import send_email
from common.supabase_client import supabase
from common.services.storage import upload_to_storage
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Constants / Config ────────────────────────────────────────────────────────
ADMIN_ROLE = "Admin"
REQUEST_STATUS_APPROVED = 30
REQUEST_STATUS_REJECTED = 4
WAITING_FOR_ADMIN = 29

ROLE_BHW = 9
ROLE_LUPON = 8
WZ_KEY = "admin_staff_nonres_wizard"

# Demo identity (keep your placeholders)
user_fullname = 'lname, fname mname suffix'
user_role = 'Admin'
user_role_template = user_role.lower().replace(' ', '_')

BUCKET_FINAL = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
BUCKET_STAFF_PROOF = getattr(settings, "SUPABASE_STAFF_PROOF_BUCKET", "staff-proof")

# ── Small helpers (aligned with Secretary code) ───────────────────────────────
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
    """
    Minimal, reliable reload by PK. Returns the fields needed for credentials.
    """
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
    return render(request, "staff_admin/staff/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

# ── Resident flow (Admin) ────────────────────────────────────────────────────
from .forms import SearchPerson, ResidentProfileform, ChooseRole, StaffFilters, Schedule, UpdateInfo


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
        # For AJAX we still return JSON; logging kept
        logger.exception("resident_suggest failed")
        return JsonResponse({"results": [], "error": "Oops! Our system is having an issue for now. Please try again later."}, status=500)


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
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:
    pid = (request.POST.get("pid") or "").strip()
    role_str = (request.POST.get("role") or "").strip()
    role_id = int(role_str) if role_str.isdigit() else None

    proof_url  = (request.POST.get("proof") or "").strip() or None
    proof_file = request.FILES.get("proof_file") if hasattr(request, "FILES") else None

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id") or 1

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

    # ─────────────────────────────────────────────────────────────────────
    # POST: Create Staff → Upsert Credentials → Send Email
    # ─────────────────────────────────────────────────────────────────────
    if request.method == "POST" and pid:
        # Basic validations
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

        # Build nice storage key
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

        # Upload proof (file / data-url / direct)
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
                flash_db_error(request, e); return redirect(request.META.get("HTTP_REFERER") or request.path)
            except Exception as e:
                flash_system_error(request, "Proof upload failed.", exc=e); return redirect(request.META.get("HTTP_REFERER") or request.path)
        elif proof_url:
            import re, base64, io
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

            # Be tolerant to either keys returned by your wrapper/model
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

            logger.info("✓ Staff created → id=%s code=%s (person_id=%s)", new_staff_id, staff_code, pid)
        except (DatabaseError, OperationalError, IntegrityError) as e:
            logger.exception("DB ✗ create_staff_direct failed")
            flash_db_error(request, e); return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "System ✗ create_staff_direct failed.", exc=e); return redirect(request.META.get("HTTP_REFERER") or request.path)

        # (2) UPSERT CREDENTIALS
        try:
            # 1) Reload staff row (prefer code, but fall back to ID)
            srow = None
            if staff_code:
                srow = _get_staff_by_code(staff_code)  # existing helper
            if not srow:
                srow = _get_staff_by_id(new_staff_id)  # ← reliable fallback

            if not srow:
                flash_warning(
                    request,
                    f"Staff created (code={staff_code or 'N/A'}) but record could not be reloaded for credentials."
                )
                return redirect(request.META.get("HTTP_REFERER") or request.path)

            # 2) If code was blank earlier, take it from DB to keep later messages consistent
            staff_code = (staff_code or srow.get("staff_code") or "").strip()
            if not staff_code:
                # Still empty? Hard stop; something's off in DB trigger/update
                flash_warning(request, "Staff created but staff_code is missing. Please verify in Staff List.")
                return redirect(request.META.get("HTTP_REFERER") or request.path)

            # 3) Build username + password
            initials = _initials_from_name(        # existing helper
                first   = srow.get("first_name"),
                middle  = srow.get("middle_name"),
                last    = srow.get("last_name"),
                suffix  = srow.get("suffix"),
            )
            username = f"brgySN.{initials}{staff_code}"
            temp_password = _rand_password(8)      # existing helper

            # 4) Choose email target
            email_to = (request.POST.get("email") or "").strip() or (srow.get("email") or "").strip()
            sent_flag = bool(email_to)

            # 5) Upsert credentials
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
            flash_db_error(request, e); return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            flash_system_error(request, "Failed while preparing credentials.", exc=e); return redirect(request.META.get("HTTP_REFERER") or request.path)


        # (3) SEND EMAIL (best-effort; does not roll back)
        try:
            if email_to:
                subj = "Barangay Sto. Niño Staff Account Creation and Credentials"

                body_txt = (
                    "Good day!\n\n"
                    "We are pleased to inform you that your staff account request has been created. "
                    "Below are your login credentials:\n\n"
                    f"  Username: {username}\n"
                    f"  Temporary Password: {temp_password}\n\n"
                    "For your security, please sign in as soon as possible and change your password immediately.\n\n"
                    "Thank you,\n"
                    "Barangay Sto. Niño"
                )

                body_html = f"""
                <p>Good day!</p>
                <p>We are pleased to inform you that your staff account request has been created. Below are your login credentials:</p>
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

    # ─────────────────────────────────────────────────────────────────────
    # GET (or POST without creation): search & preview only
    # ─────────────────────────────────────────────────────────────────────
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



# ── Non-resident Step 1 (personal info) ───────────────────────────────────────
@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform(request.POST or None)
    # Ensure these fields are NOT required in Step 1
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
            flash_success(request, "Personal information saved.")
            return redirect("staff_admin:staff_selection_nonres_docs")
        else:
            flash_warning(request, "Please correct the errors below.")

    return render(request, "staff_admin/staff/staff_selection_nonresident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
        'redirect': 'staff_admin:staff_selection_nonres_docs',
    })

    

# ── Non-resident Step 2 (supporting docs → previews only) ────────────────────
@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
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
            return redirect("staff_admin:staff_selection_nonres")

    if request.method == "POST":
        valid_id_type_raw = (request.POST.get("type_of_id") or "").strip()
        valid_id_type_id = int(valid_id_type_raw) if valid_id_type_raw.isdigit() else None
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

        # Preprocess + b64 previews
        try:
            def _readall(fobj):
                try: fobj.seek(0)
                except Exception: pass
                return fobj.read()
            from io import BytesIO
            from PIL import Image  # noqa: F401

            # convert to JPEG for preview
            def _jpeg_bytes(fileobj):
                buf, mime, _ext = _prep_image_for_upload(fileobj)
                return _readall(buf)

            b_front  = _jpeg_bytes(front_in)
            b_back   = _jpeg_bytes(back_in)
            b_selfie = _jpeg_bytes(selfie_in)
            b_proof  = _jpeg_bytes(proof_in) if proof_in is not None else None

            docs_payload = {
                "valid_id_type_id": valid_id_type_id,
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
            logger.error("Admin Step2 ✗ Preview prep failed: %s", e)
            flash_system_error(request, "Could not prepare previews.", exc=e)
            return redirect(request.path)

        flash_success(request, "Documents loaded for preview. Please review and choose role.")
        return redirect("staff_admin:staff_selection_nonres_role_review")

    return render(request, "staff_admin/staff/supporting_docs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

# ── Non-resident Step 3 (role + finalize → send request) ─────────────────────
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
    staff_id = auth.get("staff_id") or 1
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
                    b_dt = datetime.strptime(b, fmt).date()
                    break
                except Exception:
                    pass
        b_str = b_dt.strftime("%m%d%Y") if b_dt else ""
        mobile_raw = (personal.get("mobile_num") or "").strip()
        mobile_digits = re.sub(r"\D+", "", mobile_raw)
        last8 = mobile_digits[-8:] if mobile_digits else ""
        return f"{initials}{b_str}{last8}-staff-app"

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
        if b_proof is not None:
            p_buf, p_mime, p_ext = _prep_image_for_upload(io.BytesIO(b_proof))
            up_proof = _upload_to_storage_retry(
                p_buf, path=f"{proof_final_base}/staff-app-proof.{p_ext}",
                bucket=BUCKET_STAFF_PROOF, content_type=p_mime, make_public=True
            )
    except Exception as e:
        logger.error("Admin Step3 ✗ Upload failed: %s", e)
        flash_system_error(request, "Final upload failed.", exc=e)
        return redirect(request.path)

    front_url = up_front.get("public_url") or up_front.get("signed_url")
    back_url  = up_back.get("public_url") or up_back.get("signed_url")
    self_url  = up_selfie.get("public_url") or up_selfie.get("signed_url")
    proof_url = up_proof.get("public_url") or up_proof.get("signed_url") if up_proof else None

    try:
        req_id = Secretary.insert_nonres_staff_account_request(
            p_requested_by_id=staff_id,            # Admin requester → DB sets WAITING FOR ID VALIDATION
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
        flash_db_error(request, e)
        return redirect(request.path)
    except Exception as e:
        logger.exception("System ✗ insert_nonres_staff_account_request failed")
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

    _wiz_clear(request)
    flash_success(request, "Staff account request created (initial status: Waiting for ID Validation).")
    return redirect("staff_admin:staff_selection")


@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_list(request):

    try:
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

    form = StaffFilters()
    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(page_number)

    # Session/user display info
    auth = request.session.get("auth") or {}
    _user_fullname = auth.get("full_name") or user_fullname
    _user_role = auth.get("role_name") or user_role
    _user_role_template = (_user_role or "").lower().replace(" ", "_")

    return render(request, "staff_admin/staff/staff_list.html", {
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
@role_required(ADMIN_ROLE)
@require_http_methods(["GET"])
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
@role_required(ADMIN_ROLE)
@require_http_methods(["GET"])
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
def staff_dets(request, staff_code: str):
    form = UpdateInfo()

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
        "form": form,
    }
    return render(request, "staff_admin/staff/person_dets.html", ctx)


@session_login_required
@role_required(ADMIN_ROLE)
@nocache
def staff_account_requests_list(request: HttpRequest) -> HttpResponse:
    try:
        staff_req = Captain.list_requests() or []
    except Exception:
        logger.exception("Error loading staff requests")
        staff_req = []

    def get(row, key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    # keep only status_id == 29 OR status_name containing "WAITING FOR BARANGAY CAPTAIN"
    filtered = []
    for r in staff_req:
        sid = get(r, "status_id") or get(r, "request_status_id")
        name = (get(r, "status_name") or "").upper()
        try:
            sid = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid = None
        if sid == 30 or "WAITING FOR ADMIN" in name:
            filtered.append(r)

    try:
        per_page = int(request.GET.get("per_page") or 10)
        if per_page <= 0:
            per_page = 10
    except (TypeError, ValueError):
        per_page = 10

    paginator = Paginator(filtered, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "staff_admin/staff/staff_account_req.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Staff Account Requests",
        "page_title": "Staff Account Requests",
        "user_role_template": user_role_template,
        "page_obj": page_obj,
        "staff_req": page_obj.object_list,
        "total_count": paginator.count,
        "per_page": per_page,
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
        "page_path": f"{user_role} / Staff Details : {p_staff_acc_req_id}",
        "page_title": f"Staff Details : {p_staff_acc_req_id}",
        "user_role_template": user_role_template,
        "profile": p,
        "doc_slides": doc_slides,
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
@require_http_methods(["POST", "GET"])
def process_staff_request(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth") or {}
    approver_id = auth.get("staff_id")

    # --- IDs & status
    staff_acc_req_id = int(
        request.POST.get("staff_acc_req_id")
        or request.POST.get("id")
        or request.GET.get("staff_acc_req_id")
        or request.GET.get("id")
        or getattr(getattr(request, "resolver_match", None), "kwargs", {}).get("staff_acc_req_id")
    )
    status_raw = request.POST.get("p_request_status_id")
    if status_raw is None:
        action_type = (request.POST.get("action_type") or "").strip().upper()
        status_id = REQUEST_STATUS_APPROVED if action_type == "APPROVE" else REQUEST_STATUS_REJECTED
    else:
        status_id = int(status_raw)

    remarks = (request.POST.get("remarks") or "").strip() or None
    email_from_form = (request.POST.get("email") or "").strip()

    try:
        result_text = Captain.process_staff_account_request(
            p_staff_acc_req_id=staff_acc_req_id,
            p_approver_id=approver_id,
            p_request_status_id=status_id,
            p_remarks=remarks,
        )

        # =========================
        # REJECT
        # =========================
        if status_id == REQUEST_STATUS_REJECTED:
            if email_from_form:
                subj = "Staff Account Request Rejected"
                reason = remarks or "No specific reason was provided."
                body_txt = (
                    "Good day!\n\n"
                    "We regret to inform you that your staff account creation request has been rejected.\n\n"
                    f"Reason/Remarks:\n{reason}\n\n"
                    "Please contact the authorized staff if you have any concern.\n\n"
                    "Barangay Sto. Niño"
                )
                body_html = f"""
                    <p>Good day!</p>
                    <p>Your staff account creation request has been <strong>rejected</strong>.</p>
                    <p><strong>Reason/Remarks:</strong><br>{reason}</p>
                    <p>Please contact the authorized staff if you have any concern.</p>
                    <p>Barangay Sto. Niño</p>
                """.strip()
                send_email(
                    subject=subj,
                    to=[email_from_form],
                    body_text=body_txt,
                    body_html=body_html,
                    from_name="Barangay Sto. Niño",
                    fail_silently=True,
                )
                flash_success(request, "Staff account request rejected. Notification email sent.")
            else:
                flash_success(request, "Staff account request rejected. (No email on file.)")

            return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")

        # =========================
        # APPROVE
        # =========================
        if result_text == "TRUE":
            flash_success(request, "Forwarded for Admin approval. (Captain approval recorded.)")
            return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")

        staff_code = (result_text or "").strip()
        if not staff_code:
            flash_warning(request, "Approval processed, but no staff code was returned. Verify the status.")
            return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")

        # Still need staff_id & name for username/password; keep existing helper
        staff_row = _get_staff_by_code(staff_code)
        if not staff_row:
            flash_warning(request, f"Approved (staff_code={staff_code}), but staff record could not be resolved.")
            return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")

        staff_id = staff_row["staff_id"]
        initials = _initials_from_name(
            first=staff_row["first_name"],
            middle=staff_row["middle_name"],
            last=staff_row["last_name"],
            suffix=staff_row["suffix"],
        )
        username = f"brgySN.{initials}{staff_code}"
        temp_password = _rand_password(8)

        # Use hidden email if present; else fall back to person.email from DB
        email_to = email_from_form or (staff_row.get("email") or "").strip()
        sent_flag = bool(email_to)

        ok_upsert = Captain.upsert_staff_credentials_and_log(
            p_staff_id=staff_id,
            p_username=username,
            p_password_plain=temp_password,
            p_sender_staff_id=approver_id,
            p_is_credentials_sent=sent_flag,
        )
        if not ok_upsert:
            flash_warning(request, "Approved, but failed to write credentials. Please try re-issuing credentials.")
            return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")

        if email_to:
            subj = "Barangay Sto. Niño Staff Account Approval and Credentials"

            body_txt = (
                "Good day!\n\n"
                "We are pleased to inform you that your staff account request has been approved. "
                "Below are your login credentials:\n\n"
                f"  Username: {username}\n"
                f"  Temporary Password: {temp_password}\n\n"
                "For your security, please sign in as soon as possible and change your password immediately.\n\n"
                "Thank you,\n"
                "Barangay Sto. Niño"
            )

            body_html = f"""
            <p>Good day!</p>
            <p>We are pleased to inform you that your staff account request has been approved. Below are your login credentials:</p>
            <ul>
                <li><strong>Username:</strong> {username}</li>
                <li><strong>Temporary Password:</strong> {temp_password}</li>
            </ul>
            <p>For your security, please sign in as soon as possible and change your password immediately.</p>
            <p>Thank you,<br>Barangay Sto. Niño</p>
            """.strip()
            res = send_email(
                subject=subj,
                to=[email_to],
                body_text=body_txt,
                body_html=body_html,
                from_name="Barangay Sto. Niño",
                fail_silently=True,
            )
            if res.ok:
                flash_success(request, f"Staff account approved. Credentials emailed to {email_to}.")
            else:
                flash_warning(request, "Staff approved and credentials created, but sending email failed. Please resend manually.")
        else:
            flash_warning(request, "Staff approved and credentials created, but no email on file to send credentials.")

        return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")

    except DatabaseError as db_err:
        flash_db_error(request, db_err)
    except Exception as ex:
        flash_system_error(request, "Unable to process the request.", exc=ex)

    return redirect(request.POST.get("next") or request.GET.get("next") or "staff_admin:staff_account_requests_list")