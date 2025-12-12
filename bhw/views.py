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
from typing import Any, Optional
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.contrib import messages
from datetime import datetime

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

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

def _auth_staff_id(request: HttpRequest) -> Optional[int]:
    return ((request.session.get("auth") or {}).get("staff_id")) or None

@session_login_required
@role_required(*hv.ROLE_BHW)
@nocache
@inject
def dashboard(
    request: HttpRequest,
    bhw_dashboard_service=Provide[AppContainer.bhw_dashboard_service],
):
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    person_id = auth.get('person_id')

    bhw_id = _auth_staff_id(request)


    kpis = {
        "ongoing_maternal_total": 0,
        "ongoing_maternal_total_sub": 0,
        "visit_today_maternal": 0,
        "visit_today_postpartum": 0,
        "visit_today_child": 0,
        "household_to_be_visited": 0,
        "residents_total": 0,
        "families_total": 0,
        "household_total": 0,
    }

    dashboard_json = None
    announcements = []

    try:
        payload = bhw_dashboard_service.get_dashboard_content(bhw_id) or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json")
    except Exception as exc:
        print("Error fetching bhw dashboard KPIs:", exc)
    
    if person_id:
        try:
            from authentication.announcement_views import get_user_announcements
            announcements = get_user_announcements(person_id)
        except Exception as exc:
            print(f"Error fetching announcements for person {person_id}:", exc)


    return render(request, "bhw/dashboard.html", {
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'kpis': kpis,
        'dashboard_json': dashboard_json,
        'today': datetime.now().strftime("%B %d, %Y"),
        'announcements': announcements,
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


# -------------------------------
# HOUSEHOLD MAP
# -------------------------------

def _to_int_or_none(val) -> Optional[int]:
    try:
        if val in (None, "", "None"):
            return None
        return int(val)
    except Exception:
        return None

@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def household_map_list(
    request: HttpRequest,
    household_service = Provide[AppContainer.household_service],
) -> HttpResponse:
    from django.urls import reverse
    
    user_role = _auth_role_name(request)
    
    from captain.forms import HouseholdFilters
    form = HouseholdFilters(request.GET or None)

    search = request.GET.get("search")
    house_type = _to_int_or_none(request.GET.get("house_type"))
    house_ownership = _to_int_or_none(request.GET.get("house_ownership"))

    rows = household_service.execute(
        search=search,
        house_type=house_type,
        ownership_type=house_ownership,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or house_type is not None or house_ownership is not None) and not form.is_valid():
        form = HouseholdFilters()

    assigned_puroks = request.session.get("auth", {}).get("assigned_puroks", [])
    assigned_purok_names = request.session.get("auth", {}).get("assigned_purok_names", [])
    
    try:
        resp_hh_visited = supabase.rpc("get_household_visited").execute()
        resp_hh_not_visited = supabase.rpc("get_household_not_visited").execute()
        resp_fam_visited = supabase.rpc("get_family_visited").execute()
        resp_fam_not_visited = supabase.rpc("get_family_not_visited").execute()
        
        visit_counts = {
            'households_visited': len(resp_hh_visited.data or []),
            'households_not_visited': len(resp_hh_not_visited.data or []),
            'families_visited': len(resp_fam_visited.data or []),
            'families_not_visited': len(resp_fam_not_visited.data or []),
        }
    except Exception:
        visit_counts = {'households_visited': 0, 'households_not_visited': 0, 'families_visited': 0, 'families_not_visited': 0}
    
    all_puroks = [{'id': 1, 'name': 'KANIPAAN'}, {'id': 2, 'name': 'PAMPANGO'}, {'id': 3, 'name': 'LUTAW-LUTAW'}, {'id': 4, 'name': 'MAUCO'}]

    return render(
        request,
        "household/household_map_list.html",
        {
            'page_path': f'{user_role} / Household Map',
            'page_title': 'Household Map',
            'page_obj': page_obj,
            'form': form,
            'filters': {
                'search': search,
                'house_type': house_type,
                'house_ownership': house_ownership,
            },
            "pins_url": reverse("bhw:api_household_pins"),
            'search_url': 'bhw:ajax_household_search',
            'visit_counts': visit_counts,
            'assigned_puroks': assigned_puroks,
            'assigned_purok_names': assigned_purok_names,
            'all_puroks': all_puroks,
        },
    )

@session_login_required
@role_required(*ROLE_BHW)
@nocache
@inject
def ajax_household_search(
    request: HttpRequest,
    household_service = Provide[AppContainer.household_service],
) -> HttpResponse:
    from django.http import HttpResponseBadRequest
    
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")

    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    if tpl_key == "cards":
        template_name = "household/_households.html"
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
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def api_household_pins(
    request: HttpRequest,
    household_repo = Provide[AppContainer.household_repository],
):
    from django.http import HttpResponseBadRequest
    
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    pins = household_repo.fetch_household_pins(
        search=(request.GET.get("search") or None),
        house_type=_to_int_or_none(request.GET.get("house_type")),
        ownership_type=_to_int_or_none(request.GET.get("house_ownership")),
    )
    
    # Add visit status and family counts
    try:
        resp_visited = supabase.rpc("get_household_visited").execute()
        resp_not_visited = supabase.rpc("get_household_not_visited").execute()
        resp_fam_visited = supabase.rpc("get_family_visited").execute()
        resp_fam_not_visited = supabase.rpc("get_family_not_visited").execute()
        
        visited_data = resp_visited.data or []
        not_visited_data = resp_not_visited.data or []
        fam_visited_data = resp_fam_visited.data or []
        fam_not_visited_data = resp_fam_not_visited.data or []
        
        visited_ids = {row['household_id'] for row in visited_data}
        
        # Build household map from RPC data
        household_map = {}
        for row in visited_data + not_visited_data:
            if row.get('household_id'):
                household_map[row['household_id']] = row
        
        # Count families per household
        from collections import defaultdict
        fam_visited_counts = defaultdict(int)
        fam_not_visited_counts = defaultdict(int)
        
        for row in fam_visited_data:
            hid = row.get('household_id')
            if hid:
                fam_visited_counts[hid] += 1
        
        for row in fam_not_visited_data:
            hid = row.get('household_id')
            if hid:
                fam_not_visited_counts[hid] += 1
        
        # Update pins with visit status and family counts
        for pin in pins:
            hid = pin.get('household_id') or pin.get('id')
            pin['visited'] = hid in visited_ids
            pin['families_visited'] = fam_visited_counts.get(hid, 0)
            pin['families_not_visited'] = fam_not_visited_counts.get(hid, 0)
            
            # Merge RPC data if available
            if hid in household_map:
                rpc_data = household_map[hid]
                if rpc_data.get('latitude') and rpc_data.get('longitude'):
                    pin['lat'] = float(rpc_data['latitude'])
                    pin['lng'] = float(rpc_data['longitude'])
    except Exception as e:
        print(f"[api_household_pins] Error: {e}")
        for pin in pins:
            pin['visited'] = False
            pin['families_visited'] = 0
            pin['families_not_visited'] = 0
    
    return JsonResponse(pins, safe=False)


# -------------------------------
# RESIDENT LIST
# -------------------------------

@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def resident_list(
    request: HttpRequest,
    resident_service = Provide[AppContainer.resident_service],
):
    """Display resident list for BHW."""
    from bhw.forms import ResidentFilters
    
    user_role = request.session.get("authenticated_role_name", "")
    form = ResidentFilters()
    
    search = request.GET.get("search")
    purok_sitio = request.GET.get("purok_sitio")

    rows = resident_service.execute(
        search=search,
        purok=purok_sitio,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    if (search or purok_sitio is not None) and not form.is_valid():
        form = ResidentFilters()

    return render(request, "resident/resident_list.html", {
        'page_path': f'{user_role} / Resident List',
        'page_title': 'Resident List',
        'page_obj': page_obj,
        'form': form,
        'search_url': 'bhw:ajax_resident_search',
    })


@session_login_required
@role_required(*ROLE_BHW)
@nocache
@require_http_methods(["GET"])
@inject
def ajax_resident_search(
    request: HttpRequest,
    resident_service = Provide[AppContainer.resident_service],
) -> HttpResponse:
    """AJAX search for residents."""
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
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def resident_detail(
    request: HttpRequest,
    person_id: int,
    resident_service = Provide[AppContainer.resident_service],
) -> HttpResponse:
    """Display detailed resident information."""
    user_role = request.session.get("authenticated_role_name", "")
    
    resident = resident_service.get_resident_detail(person_id)
    
    if not resident:
        messages.error(request, "Resident not found.")
        return redirect("bhw:resident_list")
    
    return render(request, "resident/resident_detail.html", {
        'page_path': f'{user_role} / Resident / {resident.person_code}',
        'page_title': f'Resident {resident.person_code}',
        'resident': resident,
    })


# -------------------------------
# HOUSEHOLD LIST
# -------------------------------

@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def household_list(
    request: HttpRequest,
    household_service = Provide[AppContainer.household_service],
) -> HttpResponse:
    """Display household list for BHW."""
    from bhw.forms import HouseholdFilters
    
    user_role = request.session.get("authenticated_role_name", "")
    form = HouseholdFilters(request.GET or None)

    search = request.GET.get("search")
    
    house_type = request.GET.get("house_type")
    if house_type:
        try:
            house_type = int(house_type)
        except:
            house_type = None
    else:
        house_type = None
    
    house_ownership = request.GET.get("house_ownership")
    if house_ownership:
        try:
            house_ownership = int(house_ownership)
        except:
            house_ownership = None
    else:
        house_ownership = None

    rows = household_service.execute(
        search=search,
        house_type=house_type,
        ownership_type=house_ownership,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or house_type is not None or house_ownership is not None) and not form.is_valid():
        form = HouseholdFilters()

    return render(request, "household/household_list.html", {
        'page_path': f'{user_role} / Household List',
        'page_title': 'Household List',
        'page_obj': page_obj,
        'form': form,
        'filters': {
            'search': search,
            'house_type': house_type,
            'house_ownership': house_ownership,
        },
        "search_url": "bhw:ajax_household_search",
    })


@session_login_required
@role_required(*ROLE_BHW)
@nocache
@inject
def ajax_household_search(
    request: HttpRequest,
    household_service = Provide[AppContainer.household_service],
) -> HttpResponse:
    """AJAX search for households."""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")

    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    if tpl_key == "rows":
        template_name = "household/_household_list.html"
        ctx_key = "rows"
    elif tpl_key == "cards":
        template_name = "household/_households.html"
        ctx_key = "cards"
    else:
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q")
    
    house_type = request.GET.get("house_type")
    if house_type:
        try:
            house_type = int(house_type)
        except:
            house_type = None
    else:
        house_type = None
    
    house_ownership = request.GET.get("house_ownership")
    if house_ownership:
        try:
            house_ownership = int(house_ownership)
        except:
            house_ownership = None
    else:
        house_ownership = None

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
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def household_detail(
    request: HttpRequest,
    household_id: int,
    household_service = Provide[AppContainer.household_service],
) -> HttpResponse:
    """Display detailed household information."""
    user_role = request.session.get("authenticated_role_name", "")
    
    household = household_service.get_household_detail(household_id)
    print(f'[household_detail] household: {household}')
    if not household:
        messages.error(request, "Household not found.")
        return redirect("bhw:household_list")
    
    return render(request, "household/household_detail.html", {
        'page_path': f'{user_role} / Household / {household.household_num}',
        'page_title': f'Household {household.household_num}',
        'household': household,
    })


# -------------------------------
# FAMILY LIST
# -------------------------------

@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def family_list(
    request: HttpRequest,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """Display family list for BHW."""
    from bhw.forms import FamilyFilters
    
    user_role = request.session.get("authenticated_role_name", "")
    form = FamilyFilters(request.GET or None)

    search = request.GET.get("search")
    
    household_type = request.GET.get("household_type")
    if household_type:
        try:
            household_type = int(household_type)
        except:
            household_type = None
    else:
        household_type = None
    
    nhts_status = request.GET.get("nhts_status")
    if nhts_status:
        try:
            nhts_status = int(nhts_status)
        except:
            nhts_status = None
    else:
        nhts_status = None
    
    indigent_status = request.GET.get("indigent_status")
    if indigent_status:
        try:
            indigent_status = int(indigent_status)
        except:
            indigent_status = None
    else:
        indigent_status = None

    # Fetch family list based on filters
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

    if (search or household_type is not None or nhts_status is not None or indigent_status is not None) and not form.is_valid():
        form = FamilyFilters()

    return render(request, "family/family_list.html", {
        'page_path': f'{user_role} / Family List',
        'page_title': 'Family List',
        'page_obj': page_obj,
        'form': form,
        'filters': {
            'search': search,
            'household_type': household_type,
            'nhts_status': nhts_status,
            'indigent_status': indigent_status,
        },
        "search_url": "bhw:ajax_family_search",
    })


@session_login_required
@role_required(*ROLE_BHW)
@nocache
@inject
def ajax_family_search(
    request: HttpRequest,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """AJAX search for families."""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")

    tpl_key = (request.GET.get("tpl") or "rows").strip().lower()
    if tpl_key == "rows":
        template_name = "family/_family_list.html"
        ctx_key = "rows"
    else:
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q")
    
    household_type = request.GET.get("household_type")
    if household_type:
        try:
            household_type = int(household_type)
        except:
            household_type = None
    else:
        household_type = None
    
    nhts_status = request.GET.get("nhts_status")
    if nhts_status:
        try:
            nhts_status = int(nhts_status)
        except:
            nhts_status = None
    else:
        nhts_status = None
    
    indigent_status = request.GET.get("indigent_status")
    if indigent_status:
        try:
            indigent_status = int(indigent_status)
        except:
            indigent_status = None
    else:
        indigent_status = None

    # Fetch family search results based on filters
    if q:
        rows = household_repo.search_family(q)
    elif household_type:
        rows = household_repo.filter_family_by_household_type(household_type)
    elif nhts_status:
        rows = household_repo.filter_family_by_nhts_status(nhts_status)
    elif indigent_status:
        rows = household_repo.filter_family_by_indigent_status(indigent_status)
    else:
        rows = household_repo.fetch_family_list()
    
    rows = rows[:50]

    html = render_to_string(
        template_name,
        {ctx_key: rows},
        request=request,
    )
    return HttpResponse(html)


@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def family_detail(
    request: HttpRequest,
    family_id: int,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """Display detailed family information."""
    user_role = request.session.get("authenticated_role_name", "")
    
    family = household_repo.fetch_family_detail(family_id)
    
    if not family:
        messages.error(request, "Family not found.")
        return redirect("bhw:family_list")
    
    return render(request, "family/family_detail.html", {
        'page_path': f'{user_role} / Family / {family.get("family_num", "")}',
        'page_title': f'Family {family.get("family_num", "")}',
        'family': family,
    })


# -------------------------------
# HOUSEHOLD HISTORY
# -------------------------------

@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def household_history_list(
    request: HttpRequest,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Display household history records for a specific quarter and year.
    Supports search, house type, and ownership filtering.
    Only accessible by BHW.
    """
    from bhw.forms import HouseholdHistoryFilters
    from datetime import datetime
    
    user_role = request.session.get("authenticated_role_name", "")
    
    # Default to current quarter and year
    current_date = datetime.now()
    default_quarter = (current_date.month - 1) // 3 + 1
    default_year = current_date.year
    
    # Get filter parameters
    quarter = request.GET.get("quarter")
    if quarter:
        try:
            quarter = int(quarter)
        except:
            quarter = default_quarter
    else:
        quarter = default_quarter
    
    year = request.GET.get("year")
    if year:
        try:
            year = int(year)
        except:
            year = default_year
    else:
        year = default_year
    
    search = request.GET.get("search")
    
    house_type = request.GET.get("house_type")
    if house_type:
        try:
            house_type = int(house_type)
        except:
            house_type = None
    else:
        house_type = None
    
    house_ownership = request.GET.get("house_ownership")
    if house_ownership:
        try:
            house_ownership = int(house_ownership)
        except:
            house_ownership = None
    else:
        house_ownership = None
    
    # Initialize form with current values
    form_data = {
        'quarter': str(quarter),
        'year': year,
        'search': search or '',
        'house_type': house_type or '',
        'house_ownership': house_ownership or '',
    }
    form = HouseholdHistoryFilters(form_data)
    
    # Fetch data based on filters
    try:
        if search:
            rows = household_repo.search_household_history(search, quarter, year)
        elif house_type:
            rows = household_repo.sort_household_history_by_house_type(house_type, quarter, year)
        elif house_ownership:
            rows = household_repo.sort_household_history_by_ownership(house_ownership, quarter, year)
        else:
            rows = household_repo.fetch_household_history_by_quarter_year(quarter, year)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error fetching household history")
        messages.error(request, f"Error fetching household history: {str(e)}")
        rows = []
    
    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(request, "household/household_history_list.html", {
        'page_path': f'{user_role} / Household History',
        'page_title': 'Household History',
        'page_obj': page_obj,
        'form': form,
        'filters': {
            'quarter': quarter,
            'year': year,
            'search': search,
            'house_type': house_type,
            'house_ownership': house_ownership,
        },
    })


@session_login_required
@role_required(*ROLE_BHW)
@csrf_protect
@nocache
@inject
def household_history_detail(
    request: HttpRequest,
    household_history_id: int,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Display detailed household history information including all families and members.
    Only accessible by BHW.
    """
    user_role = request.session.get("authenticated_role_name", "")
    
    try:
        result = household_repo.fetch_household_history_detail(household_history_id)
        
        if not result:
            messages.error(request, "Household history record not found.")
            return redirect("bhw:household_history_list")
        
        household_data = result.get('household')
        families_data = result.get('families', [])
        
        if not household_data:
            messages.error(request, "Household history data is incomplete.")
            return redirect("bhw:household_history_list")
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error fetching household history detail")
        messages.error(request, f"Error fetching household history: {str(e)}")
        return redirect("bhw:household_history_list")
    
    return render(request, "household/household_history_detail.html", {
        'page_path': f'{user_role} / Household History / {household_data.get("household_num", "")}',
        'page_title': f'Household History {household_data.get("household_num", "")}',
        'household': household_data,
        'families': families_data,
    })

# -------------------------------
# FAMILY HISTORY
# -------------------------------

@session_login_required
@role_required(*ROLE_BHW)
@nocache
@inject
def family_history_list(
    request: HttpRequest,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Display family history records for a specific quarter and year.
    Supports search, household type, NHTS status, and indigent status filtering.
    Only accessible by BHW.
    """
    from bhw.forms import FamilyHistoryFilters
    from datetime import datetime
    
    user_role = request.session.get("authenticated_role_name", "")
    
    # Default to current quarter and year
    current_date = datetime.now()
    default_quarter = (current_date.month - 1) // 3 + 1
    default_year = current_date.year
    
    # Get filter parameters
    quarter = request.GET.get("quarter")
    if quarter:
        try:
            quarter = int(quarter)
        except:
            quarter = default_quarter
    else:
        quarter = default_quarter
    
    year = request.GET.get("year")
    if year:
        try:
            year = int(year)
        except:
            year = default_year
    else:
        year = default_year
    
    search = request.GET.get("search")
    
    household_type = request.GET.get("household_type")
    if household_type:
        try:
            household_type = int(household_type)
        except:
            household_type = None
    else:
        household_type = None
    
    nhts_status = request.GET.get("nhts_status")
    if nhts_status:
        try:
            nhts_status = int(nhts_status)
        except:
            nhts_status = None
    else:
        nhts_status = None
    
    indigent_status = request.GET.get("indigent_status")
    if indigent_status:
        try:
            indigent_status = int(indigent_status)
        except:
            indigent_status = None
    else:
        indigent_status = None
    
    # Initialize form with current values
    form_data = {
        'quarter': str(quarter),
        'year': year,
        'search': search or '',
        'household_type': household_type or '',
        'nhts_status': nhts_status or '',
        'indigent_status': indigent_status or '',
    }
    form = FamilyHistoryFilters(form_data)
    
    # Fetch data based on filters
    try:
        if search:
            rows = household_repo.search_family_history(search, quarter, year)
        elif household_type:
            rows = household_repo.sort_family_history_by_household_type(household_type, quarter, year)
        elif nhts_status:
            rows = household_repo.sort_family_history_by_nhts_status(nhts_status, quarter, year)
        elif indigent_status:
            rows = household_repo.sort_family_history_by_indigent_status(indigent_status, quarter, year)
        else:
            rows = household_repo.fetch_family_history_by_quarter_year(quarter, year)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error fetching family history")
        rows = []
        messages.error(request, f"Error fetching family history: {str(e)}")
    
    # Pagination
    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(request, "family/family_history_list.html", {
        'page_path': f'{user_role} / Family History',
        'page_title': 'Family History',
        'page_obj': page_obj,
        'form': form,
        'filters': {
            'quarter': quarter,
            'year': year,
            'search': search,
            'household_type': household_type,
            'nhts_status': nhts_status,
            'indigent_status': indigent_status,
        },
    })

@session_login_required
@role_required(*ROLE_BHW)
@nocache
@inject
def family_history_detail(
    request: HttpRequest,
    family_id: int,
    household_repo = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Display detailed family history information.
    Only accessible by BHW.
    """
    user_role = request.session.get("authenticated_role_name", "")
    
    try:
        family_data = household_repo.fetch_family_history_detail(family_id)
        
        if not family_data:
            messages.error(request, "Family history record not found.")
            return redirect("bhw:family_history_list")
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error fetching family history detail")
        messages.error(request, f"Error fetching family history: {str(e)}")
        return redirect("bhw:family_history_list")
    
    return render(request, "family/family_history_detail.html", {
        'page_path': f'{user_role} / Family History / {family_data.get("family_num", "")}',
        'page_title': f'Family History {family_data.get("family_num", "")}',
        'family': family_data,
    })
