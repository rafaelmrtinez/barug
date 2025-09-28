# bhw/views.py
from __future__ import annotations
from typing import Any
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.template.loader import render_to_string
from django.contrib import messages

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

from .forms import (
    SearchActiveScheduleFilter,
    StatusActiveScheduleFilter,
    WeekRangeActiveScheduleFilter,
    Reschedule,
    MaternalBhwIntakeForm,
)

# All logic lives here:
from . import health_views as hv

# -------------------- Simple UI-only globals --------------------
user_fullname = "laname fname mname suffix"
user_role = "Barangay Health Worker"
user_role_template = user_role.lower().replace(" ", "_")

# -------------------- UI / render handlers ----------------------

# bhw/views.py
from typing import List, Dict, Any
from django.http import JsonResponse, HttpRequest
from django.template.loader import render_to_string
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

from common.supabase_client import supabase  # same client Clerk uses

ROLE_BHW = ("BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw")

# bhw/views.py
from datetime import date
from typing import Any, Dict
from django.http import JsonResponse, HttpRequest
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.supabase_client import supabase

ROLE_BHW = ("BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw")

def _age_from_birthdate_py(bd: Any):
    try:
        if not bd:
            return None
        if isinstance(bd, str):
            bd = date.fromisoformat(bd[:10])
        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None

@session_login_required
@role_required(*ROLE_BHW)
@nocache
def ajax_person_details(request: HttpRequest):
    """Return minimal structured details for a person_id (DOB, age, address, etc.)."""
    try:
        pid = int(request.GET.get("person_id") or 0)
    except Exception:
        pid = 0
    if not pid:
        return JsonResponse({"ok": False, "error": "missing person_id"}, status=400)

    try:
        # Use your existing DB RPC that already joins address pieces
        resp = supabase.rpc("get_specific_resident_full_profile", {"p_person_id": pid}).execute()
        data = resp.data or []
        row: Dict[str, Any] = (data[0] if isinstance(data, list) and data else data) or {}
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"{e}"}, status=500)

    # Compose address
    parts = [
        (row.get("street_name") or "").strip(),
        (row.get("sitio_purok_name") or row.get("purok_sitio_name") or "").strip(),
        (row.get("barangay_name") or "").strip(),
        (row.get("city_name") or "").strip(),
    ]
    address = ", ".join([p for p in parts if p]) or None
    birthdate = (row.get("birthdate") or row.get("date_of_birth") or None)
    birthdate_iso = str(birthdate)[:10] if birthdate else None
    age = _age_from_birthdate_py(birthdate_iso)
    family_num = row.get("family_num")

    payload = {
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "person_code": row.get("person_code"),
        "birthdate": birthdate_iso,
        "age": age,
        "address": address,
        "civil_status": row.get("civil_status"),
        "occupation": row.get("occupation"),
        "sex": row.get("sex"),
        "family_num": family_num
    }
    return JsonResponse({"ok": True, "person": payload})


@session_login_required
@role_required(*ROLE_BHW)
@nocache
def ajax_resident_search(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    rows: List[Dict[str, Any]] = []
    if len(q) >= 2:
        try:
            resp = supabase.rpc("search_person_by_code_or_name", {"raphael": q}).execute()
            rows = resp.data or []
        except Exception:
            rows = []

    html = render_to_string("bhw/_resident_results.html", {"residents": rows})
    return JsonResponse({"ok": True, "html": html})

@session_login_required
@role_required(*ROLE_BHW)
@nocache
def ajax_person_card(request: HttpRequest) -> JsonResponse:
    """Load a lightweight person card (mirrors Clerk’s ‘view details’ style)."""
    try:
        pid = int(request.GET.get("person_id") or 0)
    except Exception:
        pid = 0

    row: Dict[str, Any] | None = None
    if pid:
        try:
            res = supabase.rpc("get_details", {"p_person_id": pid}).execute()
            data = res.data or []
            row = (data[0] if isinstance(data, list) and data else data) or {}
        except Exception:
            row = None

    html = render_to_string("bhw/_person_card.html", {"p": row})
    return JsonResponse({"ok": bool(row), "html": html})


def active_schedule(request: HttpRequest) -> HttpResponse:
    pending = []
    page_obj = Paginator(pending, 10).get_page(request.GET.get("page"))
    return render(request, "household/quarterly/active_schedule.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": "",
        "page_title": "",
        "user_role_template": user_role_template,
        "search_form": SearchActiveScheduleFilter(),
        "status_form": StatusActiveScheduleFilter(),
        "week_range_form": WeekRangeActiveScheduleFilter(),
        "reschedule_form": Reschedule(),
        "page_obj": page_obj,
    })

def household_info(request: HttpRequest) -> HttpResponse:
    return render(request, "household/household_info.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Request Details",
        "page_title": "Request Details",
        "user_role_template": user_role_template,
    })

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def dashboard(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth")
    profile = getattr(request, "person_profile", None)
    return render(request, "bhw/dashboard.html", {
        "page_path": "Barangay Health Worker/Dashboard",
        "page_title": "Dashboard",
        "profile": profile,
        "auth": auth,
    })

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def records(request: HttpRequest) -> HttpResponse:
    rows = hv.sample_registry()
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    return render(request, "bhw/records.html", {
        "page_path": "Barangay Health Worker / Records",
        "page_title": "Records",
        "q": request.GET.get("q", ""),
        "types": request.GET.getlist("type"),
        "puroks": request.GET.getlist("purok"),
        "statuses": request.GET.getlist("status"),
        "types_all": ["maternal", "child"],
        "puroks_all": ["Kanipaan", "Pampango", "Lutaw-lutaw", "Mauco"],
        "statuses_all": ["active", "completed", "archived"],
        "active_count": len(request.GET.getlist("type")) + len(request.GET.getlist("purok")) + len(request.GET.getlist("status")),
        "page_obj": page_obj,
    })

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def record_detail(request: HttpRequest, kind: str, record_id: int) -> HttpResponse:
    rec = hv.get_record_detail(kind, record_id)
    return render(request, "bhw/record_detail.html", {
        "page_path": "Barangay Health Worker / Record Details",
        "page_title": "Record Details",
        "rec": rec,
    })

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def ajax_resident_search(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    rows = hv.search_residents(q)
    html = render_to_string("bhw/_resident_results.html", {"residents": rows})
    return JsonResponse({"ok": True, "html": html})

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def verify_valid_id_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    supabase_uid = request.POST.get("supabase_uid") or ""
    legit_person_id = int(request.POST.get("legit_person_id") or 0)
    id_type_raw = request.POST.get("id_type") or ""
    profile_name = request.POST.get("profile_name") or ""

    result = hv.verify_valid_id(
        supabase_uid=supabase_uid,
        legit_person_id=legit_person_id,
        id_type_raw=id_type_raw,
        profile_name=profile_name,
        front=request.FILES.get("front"),
        back=request.FILES.get("back"),
        selfie=request.FILES.get("selfie"),
    )
    status = result.pop("status", 200) if not result.get("ok") else 200
    return JsonResponse(result, status=status)

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def add_anc_visit(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    messages.success(request, "ANC visit saved (demo).")
    return redirect("bhw:record_detail", kind="maternal", record_id=record_id)

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def add_child_visit(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Child visit saved (demo).")
    return redirect("bhw:record_detail", kind="child", record_id=record_id)

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def add_vaccine(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Vaccine dose saved (demo).")
    return redirect("bhw:record_detail", kind="child", record_id=record_id)

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def maternal_new(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    if request.method == "POST":
        form = MaternalBhwIntakeForm(request.POST)
        if form.is_valid():
            payload = hv.build_maternal_payload(form.cleaned_data, staff_id)
            ok, err = hv.create_maternal_record(payload)
            if ok:
                messages.success(request, "Maternal health record created.")
                return redirect("bhw:maternal_new")
            messages.error(request, f"RPC error: {err}")
        else:
            messages.error(request, "Please fix the form errors below.")
    else:
        form = MaternalBhwIntakeForm()

    return render(request, "bhw/maternal_new.html", {
        "page_path": "Barangay Health Worker / Maternal Records / New",
        "page_title": "New Maternal Record (BHW Intake)",
        "form": form,
    })
