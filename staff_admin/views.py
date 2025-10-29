from django.shortcuts import render
from django.core.paginator import Paginator

import secretary
from .forms import (
    SearchPerson,
    ResidentProfileform,
    ChooseRole,
    StaffFilters,
    Schedule,
    UpdateInfo,
)
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import DatabaseError
from django.shortcuts import redirect
from django.templatetags.static import static
import logging
from secretary.models import Secretary
from captain.models import Captain
from common.send_email import send_email
from common.flash import flash_success, flash_warning, flash_system_error, flash_db_error
from django.db import connection
from typing import Optional
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from django.views.decorators.http import require_GET, require_http_methods


import secrets
import string
import re

logger = logging.getLogger(__name__)

ADMIN_ROLE = "Admin"
REQUEST_STATUS_APPROVED = 30
REQUEST_STATUS_REJECTED = 4
WAITING_FOR_ADMIN = 29

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Admin'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
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

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_resident(request):
    form = SearchPerson()
    role_form = ChooseRole()
    sched_form = Schedule()
    return render(request, "staff_admin/staff/staff_selection_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
        'role_form': role_form,
        'sched_form': sched_form
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres(request):
    form = ResidentProfileform()
    return render(request, "staff/staff_selection_nonresident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres_docs(request):
    form = ResidentProfileform()
    return render(request, "staff_admin/staff/supporting_docs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

@session_login_required
@role_required(ADMIN_ROLE)
@nocache
@require_http_methods(["GET","POST"])
def staff_selection_nonres_role_review(request):
    role_form = ChooseRole()
    sched_form = Schedule()
    return render(request, "staff_admin/staff/role.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'role_form': role_form,
        'sched_form': sched_form,
    })


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