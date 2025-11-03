# bhw/views.py
from __future__ import annotations
# Raf
import json
from urllib import request
from django.db import connection
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from dependency_injector.wiring import inject, Provide
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_http_methods
from authentication.guards import role_required, session_login_required
from src.app.bootstrap.app_containers import AppContainer
from src.domain.contracts.household_info_service_contract import IHouseholdInfoService
from src.domain.contracts.scheduling_service_contract import ISchedulingService
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.domain.contracts.maternal_service import IMaternalService
from src.infra.exceptions.maternal_exceptions import MaternalException
from src.infra.exceptions.rescheduling_exception import ReschedulingException

from .forms import SearchActiveScheduleFilter
from .forms import StatusActiveScheduleFilter
from .forms import WeekRangeActiveScheduleFilter
from .forms import Reschedule
from .forms import ChildHealtheRecordForm


# Raph
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

ROLE_BHW = ("BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw", "Super Admin")

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


# Create your views here.
@session_login_required
@role_required("Super Admin", "Barangay Health Worker")
@csrf_protect
@inject
def active_schedule(
    request: HttpRequest,
    scheduling_service: ISchedulingService = Provide[AppContainer.scheduling_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:

    search_form = SearchActiveScheduleFilter(request.GET or None)
    status_form = StatusActiveScheduleFilter(request.GET or None)
    week_range_form = WeekRangeActiveScheduleFilter()
    reschedule_form = Reschedule()
    template = "household/quarterly/active_schedule.html"
    
    session = request.session.get("auth")
    user_fullname = " ".join(
        filter(None, [session.get("first_name"), session.get(
            "middle_name", ""), session.get("last_name")])
    )
    
    pending = scheduling_service.execute(
        request.GET.get("search"),
        request.GET.get("status"),
        request.GET.get("week_range"),
    )
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.method == "POST":
        week_range = request.POST.get("week_start")
        reason = request.POST.get("reason")
        schedule_id = request.POST.get("schedule_id")

        try:
            service = scheduling_service.execute_reschedule(
                week_start=week_range,
                reasoning=reason,
                schedule_id=schedule_id,
                added_by=session.get("person_id"),
            )
            
            if not service:
                messages.error(request, "Rescheduling failed, please try again.")
                return redirect("bhw:active_schedule")
            
            messages.success(request, "Rescheduling successful.")
            return redirect("bhw:active_schedule")
        except ReschedulingException as se:
            # add to messages framework
            messages.error(request, f"Rescheduling failed: {se.message}")
            return redirect("bhw:active_schedule")

    if request.GET.get("search") and not search_form.is_valid():
        search_form = SearchActiveScheduleFilter()
    if request.GET.get("status") and not status_form.is_valid():
        status_form = StatusActiveScheduleFilter()
    if request.GET.get("week_range") and not week_range_form.is_valid():
        week_range_form = WeekRangeActiveScheduleFilter()
        
    return render(
        request,
        template,
        {
            "user_fullname": user_fullname,
            "user_role": session.get("role_name"),
            "page_path": "",
            "page_title": "",
            "user_role_template": user_role_template,
            "search_form": search_form,
            "status_form": status_form,
            "week_range_form": week_range_form,
            "reschedule_form": reschedule_form,
            "page_obj": page_obj,
        },
    )


@session_login_required
@role_required("Super Admin", "Barangay Health Worker")
@csrf_protect
@inject
def household_info(
    request, household_id,
    service: IHouseholdInfoService = Provide[
        AppContainer.household_info_service]) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    if not household_id:
        return redirect('bhw:active_schedule')
    session = request.session.get("auth")
    household_details = service.execute(household_id)
    return render(request, "household/household_info.html", {
        'user_fullname': session.get("first_name") + " " + session.get("middle_name", "") + " " + session.get("last_name"),
        'user_role': session.get("role_name"),
        'page_path': f'{user_role} / Request Details',
        'page_title': 'Request Details',
        'user_role_template': user_role_template,
        'household_details': household_details.get('household_info'),
        'families': household_details.get('family_units'),
    })

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def dashboard(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth")
    profile = getattr(request, "person_profile", None)
    return render(request, "bhw_dashboard.html", {
        "page_path": "Barangay Health Worker/Dashboard",
        "page_title": "Dashboard",
        "profile": profile,
        "auth": auth,
    })

@session_login_required
@role_required(*hv.ROLE_BHW, "midwife")
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

@csrf_protect
@session_login_required
@role_required(*ROLE_BHW)
@nocache
def child_new(request: HttpRequest) -> HttpResponse:
    """
    UI for the Child Health Record intake that mirrors the DOH paper form.
    This version focuses on frontend capture; wire to your RPC when ready.
    """
    return render(
        request,
        "bhw/child_new.html",
        {
            "page_path": "Midwife / Child Records / New",
            "page_title": "New Child Health Record",
        },
    )
    
@csrf_exempt
@require_http_methods(["POST"])
@role_required(*ROLE_BHW)
@session_login_required
@inject
def add_child(request: HttpRequest, service: IMaternalService = Provide[AppContainer.maternal_service]) -> HttpResponse:
    try:
        if request.content_type == "application/json":
            try:
                data = json.loads(request.body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return JsonResponse({"response": "Invalid JSON body."}, status=400)
        else:
            return JsonResponse({"response": "Unsupported content type."}, status=415)
        
        form = ChildHealtheRecordForm(data)
        
        if not form.is_valid():
            print(f'form data is not valid: {form.errors}')
            return JsonResponse({"response": form.errors}, status=400)
            
        child_data = CreateChildRecordRequest(
            request.session.get("auth", {}).get("staff_id"),
            data.get("child_id"),
            data.get("mother_id"),
            data.get("father_id"),
            data.get("birth_order"),
            data.get("place_delivery"),
            data.get("family_no")
        )
        id = service.execute_insert_child_record(child_data)
        
        if not id:
            return JsonResponse({"response": "Something went wrong."}, status=500)
        
        return JsonResponse({"response": True}, status=200)

    except MaternalException as e:
        return JsonResponse({"response": str(e.message)}, status=500)

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
def add_vaccine(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Vaccine dose saved (demo).")
    return redirect("bhw:record_detail", kind="child", record_id=record_id)

@session_login_required
@role_required(*hv.ROLE_BHW, "midwife")
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

@session_login_required
@role_required(*hv.ROLE_BHW, "midwife")
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
@role_required(*hv.ROLE_BHW, "midwife")
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
