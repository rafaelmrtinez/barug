# midwife/views.py
from __future__ import annotations

import json
from datetime import date
import json

import os
os.environ.setdefault("HTTPX_DISABLE_HTTP2", "1")

from datetime import date, datetime, time as dtime
from typing import Any, Dict, List, Optional, Tuple

from django.views.decorators.http import require_http_methods
from dependency_injector.wiring import inject, Provide

from django.views.decorators.csrf import csrf_protect

from django.views.decorators.http import require_http_methods
from dependency_injector.wiring import inject, Provide

from django.views.decorators.csrf import csrf_protect

import io
import base64
import logging
import re
import time as _time
import io
import base64
import logging
import re
import time as _time

from django.conf import settings
from django.contrib import messages

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from django.core.paginator import Paginator
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    HttpResponseNotAllowed,
)
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from barug.error_messages import SOMETHING_WENT_WRONG
from barug.utility.json_utility import JSONCustomUtility
from midwife.utility.anc_view_utility import ANCViewUtility
from midwife.utility.immunitization_view_utility import ImmunizationViewUtility
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.antenatal_service import IAntenatalCareService
from src.app.contracts.child_services import IChildService
from src.app.exceptions.person_not_found import PersonNotFoundException
from src.app.exceptions.prescription_exception import PrescriptionException
from src.app.transfer_objects.request.anc_labolatory_results_request import ANCLaboratoryResultsRequest
from src.app.transfer_objects.request.antenatal_care_request import AntenatalCareRequest
from src.app.transfer_objects.request.breast_feeding_type_request import BreastFeedingCheckRequest
from src.app.transfer_objects.request.child_immunization_request import ChildImmunizationRequest
from src.app.transfer_objects.request.child_iron_supplement_request import ChildIronSupplementRequest
from src.app.transfer_objects.request.child_monitoring_request import ChildMonitoringRequest
from src.app.transfer_objects.request.child_screening_request import ChildScreeningRequest
from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.child_vitamins_request import ChildVitaminsRequest
from src.app.transfer_objects.request.init_chilld_immunization_request import InitialChildImmunizationRequest
from src.app.transfer_objects.request.tetanus_toxoid_request import TetanusToxoidRequest
from src.domain.contracts.maternal_service import IMaternalService
from src.infra.exceptions.anc_visit_exception import ANCVisitException
from src.infra.exceptions.child_visit_exception import ChildVisitException

from .forms import (
    SearchActiveScheduleFilter,
    StatusActiveScheduleFilter,
    WeekRangeActiveScheduleFilter,
    Reschedule,
    MaternalBhwIntakeForm,
    SearchPerson,
    ResidentProfileform,
    ChooseRole,
    StaffFilters,
)

# Service helpers (unchanged)
from .services import (
    fetch_maternal_registry,
    search_residents,
    verify_valid_id,
    build_maternal_payload,
    create_maternal_record,
    get_record_detail,
    build_anc_visit_payload,
    insert_anc_visit_with_details,
)

# Two AJAX helpers use RPC directly
from common.supabase_client import supabase
from common.services.storage import upload_to_storage

# For account management RPCs
from secretary.models import Secretary

# Flash helpers
from common.flash import flash_success, flash_warning, flash_db_error, flash_system_error
from django.db import DatabaseError, OperationalError, IntegrityError
from common.db_errors import _pg_err_tuple

logger = logging.getLogger(__name__)

import logging

logger = logging.getLogger(__name__)

# -------------------- Role / UI globals (unchanged) --------------------
ROLE_MIDWIFE = ("MIDWIFE", "Midwife", "midwife")
# This was added to allow extended roles to access/re-use features such as resident search
FEATURE_ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "Super Admin")
user_fullname = "laname fname mname suffix"
user_role = "MIDWIFE"
user_role_template = user_role.lower().replace(" ", "_")

ROLE_BHW = 9
ROLE_LUPON = 8
WZ_KEY = "staff_nonres_wizard"

BUCKET_FINAL = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
BUCKET_STAFF_PROOF = getattr(settings, "SUPABASE_STAFF_PROOF_BUCKET", "staff-proof")

# -------------------- Small utilities (unchanged) --------------------
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


# -------------------- Parsing helpers for normalization --------------------
def _to_float(s: Any) -> Optional[float]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        # strip units like "54 kg"
        txt = str(s)
        num = "".join(ch for ch in txt if (ch.isdigit() or ch == "." or ch == "-"))
        return float(num) if num else None
    except Exception:
        return None


def _parse_bp(bp: Any) -> Tuple[Optional[int], Optional[int]]:
    try:
        if not bp:
            return (None, None)
        txt = str(bp)
        if "/" in txt:
            a, b = txt.split("/", 1)
            return (int("".join(ch for ch in a if ch.isdigit())),
                    int("".join(ch for ch in b if ch.isdigit())))
        return (None, None)
    except Exception:
        return (None, None)


def _parse_ga_weeks(ga: Any) -> Optional[int]:
    if ga is None:
        return None
    if isinstance(ga, (int, float)):
        return int(ga)
    txt = str(ga).lower().strip()
    # accept formats like "8w", "8", "8 weeks"
    digits = "".join(ch for ch in txt if ch.isdigit())
    return int(digits) if digits else None


def _trimester_name(ga_weeks: Optional[int]) -> Optional[str]:
    if ga_weeks is None:
        return None
    if ga_weeks <= 13:
        return "1st"
    if ga_weeks <= 27:
        return "2nd"
    return "3rd"


def _normalize_maternal_detail(raw: Dict[str, Any] | None, record_id: int) -> Dict[str, Any]:
    """
    Accepts either your service's 'maternal_health_record' style or the sample payload style
    (id/kind/name/plan_delivery/anc/etc.) and returns a unified dict the template can use safely.
    """
    raw = raw or {}

    def first(*keys, default=None):
        for k in keys:
            if k in raw and raw[k] not in (None, "", [], {}):
                return raw[k]
        return default

    # IDs / names
    mhr_id = first("maternal_record_id", "id", default=record_id)
    person_name = first("person_name", "name")
    family_num = first("family_num", "family_no")
    status = first("status", default="ACTIVE")

    # baseline / anthropometrics
    height = first("height", "height_m")
    weight = first("weight", "baseline_weight_kg")
    bmi_status_id = first("bmi_status_id")
    created_at = first("created_at")
    assessed_by_id = first("assessed_by_id")
    husband_id = first("husband_id")
    person_id = first("person_id")
    family_id = first("family_id")

    # plans
    place_plan = first("place_of_delivery_plan", "plan_delivery")
    nbs_plan = first("new_born_screening_plan", "plan_nbs")

    # dates (optional)
    lmp_date = first("lmp_date", ("present" in raw and raw["present"].get("lmp")))
    edd_date = first("edd_date", ("present" in raw and raw["present"].get("edc")))

    # Normalize visits
    visits: List[Dict[str, Any]] = []
    if isinstance(raw.get("visits"), list):
        # already normalized by service
        visits = list(raw["visits"])
    elif isinstance(raw.get("anc"), list):
        for v in raw["anc"]:
            ga_w = _parse_ga_weeks(v.get("ga"))
            bp_s, bp_d = _parse_bp(v.get("bp"))
            visits.append({
                "visit_date": v.get("date"),
                "ga_weeks": ga_w,
                "trimester_name": _trimester_name(ga_w),
                "bp_sys": bp_s,
                "bp_dia": bp_d,
                "weight_kg": _to_float(v.get("wt")),
                "fhr_bpm": _to_float(v.get("fhr")) if v.get("fhr") not in (None, "—") else None,
                "fundic_height_cm": None,
                "has_danger": False,
                "notes": v.get("remarks"),
                "labs": [],
                "tt": [],
                "supplements": [],
                "assessed_by": None,
            })

    # Delivery block (optional)
    delivery = raw.get("delivery")

    # Shape for template
    return {
        "mhr_id": mhr_id,
        "person_name": person_name,
        "family_num": family_num,
        "status": status,
        "height": height,
        "weight": weight,
        "bmi_status_id": bmi_status_id,
        "created_at": created_at,
        "assessed_by_id": assessed_by_id,
        "husband_id": husband_id,
        "person_id": person_id,
        "family_id": family_id,
        "place_of_delivery_plan": place_plan,
        "new_born_screening_plan": nbs_plan,
        "lmp_date": lmp_date,
        "edd_date": edd_date,
        "visits": visits,
        "delivery": delivery,
    }


def _demo_maternal_payload(record_id: int) -> Dict[str, Any]:
    """Temporary sample data when the DB returns nothing (for debugging the UI)."""
    return {
        "id": record_id,
        "kind": "maternal",
        "name": "Maria Santos",
        "age": 28,
        "family_no": "F-001",
        "address": "Purok Kanipaan",
        "present": {"gravida": 2, "para": 1, "lmp": "2025-05-01", "edc": "2026-02-05"},
        "tt": [{"dose": "TT1", "date": "2024-11-10"}, {"dose": "TT2", "date": "2025-01-12"}],
        "anc": [
            {"date": "2025-06-10", "ga": "8w", "bp": "110/70", "wt": "54 kg", "fht": "—", "remarks": "Initial"}
        ],
        "labs": {"Urinalysis": "Normal", "Syphilis": "NR"},
        "ogct_50": "85 mg/dL",
        "ogct_100": "—",
        "plan_delivery": "NSVD – District Hospital",
        "plan_nbs": True,
    }


# -------------------- AJAX endpoints --------------------
@session_login_required
@role_required(*FEATURE_ACCESS)
@nocache
def ajax_person_details(request: HttpRequest):
    try:
        pid = int(request.GET.get("person_id") or 0)
    except Exception:
        pid = 0
    if not pid:
        return JsonResponse({"ok": False, "error": "missing person_id"}, status=400)

    try:
        resp = supabase.rpc("get_specific_resident_full_profile", {"p_person_id": pid}).execute()
        data = resp.data or []
        row: Dict[str, Any] = (data[0] if isinstance(data, list) and data else data) or {}
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"{e}"}, status=500)

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
        "family_num": row.get("family_num"),
    }
    return JsonResponse({"ok": True, "person": payload})


@session_login_required
@role_required(*FEATURE_ACCESS)
@nocache
def ajax_resident_search(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    rows = search_residents(q)
    html = render_to_string("midwife/_resident_results.html", {"residents": rows})
    return JsonResponse({"ok": True, "html": html})


@session_login_required
@role_required(*FEATURE_ACCESS)
@nocache
def ajax_person_card(request: HttpRequest) -> JsonResponse:
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

    html = render_to_string("midwife/_person_card.html", {"p": row})
    return JsonResponse({"ok": bool(row), "html": html})


# -------------------- Pages --------------------
def active_schedule(request: HttpRequest) -> HttpResponse:
    pending: List[Dict[str, Any]] = []
    page_obj = Paginator(pending, 10).get_page(request.GET.get("page"))
    return render(
        request,
        "household/quarterly/active_schedule.html",
        {
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
        },
    )


def household_info(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "household/household_info.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Request Details",
            "page_title": "Request Details",
            "user_role_template": user_role_template,
        },
    )


@session_login_required

@role_required(*ROLE_MIDWIFE, "Super Admin")
@nocache
def dashboard(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth")
    return render(
        request,
        "midwife/dashboard.html",
        {
            "page_path": "Midwife/Dashboard",
            "page_title": "Dashboard",
            "auth": auth,
        },
    )


@session_login_required
@role_required(*ROLE_MIDWIFE, "Super Admin")
@nocache
def records(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    rows = fetch_maternal_registry(q=q, limit=300)
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    return render(
        request,
        "midwife/records.html",
        {
            "page_path": "Midwife / Records",
            "page_title": "Records",
            "q": q,
            "types": request.GET.getlist("type"),
            "puroks": request.GET.getlist("purok"),
            "statuses": request.GET.getlist("status"),
            "types_all": ["maternal", "child"],
            "puroks_all": ["Kanipaan", "Pampango", "Lutaw-lutaw", "Mauco"],
            "statuses_all": ["active", "completed", "archived"],
            "active_count": len(request.GET.getlist("type"))
            + len(request.GET.getlist("purok"))
            + len(request.GET.getlist("status")),
            "page_obj": page_obj,
        },
    )


@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def record_detail(request: HttpRequest, kind: str, record_id: int) -> HttpResponse:
    """
    When opened from Records, display maternal details prefilled *up to Anthropometrics*.
    Falls back to demo data if none returned, and normalizes keys for the template.
    """
    raw = get_record_detail(kind, record_id)
    if not raw:
        raw = _demo_maternal_payload(record_id)  # <-- temp data for debugging

    rec = _normalize_maternal_detail(raw, record_id)

    return render(
        request,
        "midwife/record_detail.html",
        {
            "page_path": "Midwife / Record Details",
            "page_title": "Record Details",
            "rec": rec,          # normalized record
            "kind": kind,
            "record_id": record_id,  # provided for completeness
        },
    )


@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def verify_valid_id_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    supabase_uid = request.POST.get("supabase_uid") or ""
    legit_person_id = int(request.POST.get("legit_person_id") or 0)
    id_type_raw = request.POST.get("id_type") or ""
    profile_name = request.POST.get("profile_name") or ""

    result = verify_valid_id(
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
@role_required(*ROLE_MIDWIFE)
@nocache
def add_anc_visit(request: HttpRequest, record_id: int) -> HttpResponse:
    """
    Insert a new ANC visit via Supabase RPC `insert_anc_visit_with_details`.
    The form posts JSON strings for labs/tt/supplements/danger_signs.
    We also compute trimester_stage_id from GA weeks.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # helpers
    def _to_i(x):
        try:
            return int(x) if x not in (None, "",) else None
        except Exception:
            return None

    def _to_f(x):
        try:
            return float(x) if x not in (None, "",) else None
        except Exception:
            return None

    def _to_b(x):
        if x in (True, "true", "True", "1", 1): return True
        if x in (False, "false", "False", "0", 0): return False
        return None

    def _parse_json(s):
        import json
        try:
            return json.loads(s) if s else None
        except Exception:
            return None

    def _tri_id(ga_weeks: Optional[int]) -> Optional[int]:
        if ga_weeks is None:
            return None
        return 1 if ga_weeks <= 13 else 2 if ga_weeks <= 27 else 3

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    # POST fields
    visit_date = request.POST.get("visit_date") or None
    ga_weeks = _to_i(request.POST.get("ga_weeks"))
    bp_sys = _to_i(request.POST.get("bp_sys"))
    bp_dia = _to_i(request.POST.get("bp_dia"))
    weight_kg = _to_f(request.POST.get("weight_kg"))
    fundic_cm = _to_i(request.POST.get("fundic_height_cm"))
    fhr_bpm = _to_i(request.POST.get("fhr_bpm"))
    assessed_by_id = _to_i(request.POST.get("assessed_by_id")) or _to_i(staff_id)
    notes = (request.POST.get("notes") or "").strip()
    trimester_stage_id = _to_i(request.POST.get("trimester_stage_id")) or _tri_id(ga_weeks)

    labs = _parse_json(request.POST.get("labs_json"))
    tt = _parse_json(request.POST.get("tt_json"))
    supps = _parse_json(request.POST.get("supplements_json"))
    danger = _parse_json(request.POST.get("danger_signs_json")) or ["NONE"]

    # Build RPC payload. Only include keys your function expects.
    # (Extras are typically ignored by PostgREST; still, we keep a clean set.)
    payload: Dict[str, Any] = {
        # required
        "p_maternal_record_id": int(record_id),
        "p_assessed_by_id": assessed_by_id,
        "p_visit_date": visit_date,
        "p_trimester_stage_id": trimester_stage_id,

        # visit vitals (if your RPC supports these named args)
        "p_bp_sys": bp_sys,
        "p_bp_dia": bp_dia,
        "p_weight_kg": weight_kg,
        "p_fundic_height_cm": fundic_cm,
        "p_fhr_bpm": fhr_bpm,
        "p_notes": notes if notes else None,

        # collections (jsonb)
        "p_lab_results": labs,
        "p_tt_vaccines": tt,
        "p_supplements": supps,
        "p_danger_signs": danger,
    }

    # Optional maternal fields (leave None unless you capture them here)
    # Keeping them out avoids accidental overwrites.

    # DEBUG LOG
    try:
        import json as _json
        print("\n[MIDWIFE] insert_anc_visit_with_details payload:")
        print(_json.dumps(payload, indent=2, default=str))
    except Exception:
        pass

    # Call Supabase
    try:
        res = supabase.rpc("insert_anc_visit_with_details", payload).execute()
        print("[MIDWIFE] RPC insert_anc_visit_with_details → data:", getattr(res, "data", None))
        print("[MIDWIFE] RPC insert_anc_visit_with_details → error:", getattr(res, "error", None))
        if getattr(res, "error", None):
            messages.error(request, f"Insert failed: {getattr(res.error, 'message', res.error)}")
        else:
            messages.success(request, "ANC visit saved.")
    except Exception as e:
        print("[MIDWIFE] RPC insert_anc_visit_with_details → exception:", e)
        messages.error(request, f"Error: {e}")

    return redirect("midwife:record_detail", kind="maternal", record_id=record_id)


@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def add_child_visit(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Child visit saved (demo).")
    return redirect("midwife:record_detail", kind="child", record_id=record_id)


@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def add_vaccine(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Vaccine dose saved (demo).")
    return redirect("midwife:record_detail", kind="child", record_id=record_id)


@session_login_required
@role_required(*ROLE_MIDWIFE, "Super Admin")
@nocache
def maternal_new(request: HttpRequest) -> HttpResponse:
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    if request.method == "POST":
        form = MaternalBhwIntakeForm(request.POST)
        if form.is_valid():
            payload = build_maternal_payload(form.cleaned_data, staff_id)
            ok, err = create_maternal_record(payload)
            if ok:
                messages.success(request, "Maternal health record created.")
                return redirect("midwife:maternal_new")
            messages.error(request, f"RPC error: {err}")
        else:
            messages.error(request, "Please fix the form errors below.")
    else:
        form = MaternalBhwIntakeForm()

    return render(
        request,
        "midwife/maternal_new.html",
        {
            "page_path": "Midwife / Maternal Records / New",
            "page_title": "New Maternal Record (BHW Intake)",
            "form": form,
        },
    )

# -------------------- NEW: Child Health Record (UI only / ready for RPC wiring) --------------------
@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def child_new(request: HttpRequest) -> HttpResponse:
    """
    UI for the Child Health Record intake that mirrors the DOH paper form.
    This version focuses on frontend capture; wire to your RPC when ready.
    """
    if request.method == "POST":
        # Placeholder: accept POST, show success. Replace with your service call later.
        messages.success(request, "Child health record saved (demo UI).")
        return redirect("midwife:child_new")

    return render(
        request,
        "midwife/child_new.html",
        {
            "page_path": "Midwife / Child Records / New",
            "page_title": "New Child Health Record",
        },
    )
    
@require_http_methods(["POST"])
@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
@inject
def child_visit_http(request: HttpRequest, service: IMaternalService = Provide[AppContainer.maternal_service]) -> JsonResponse:
    
    if request.content_type != "application/json":
        return JsonResponse({"error": "Unsupported Media Type"}, status=415)
    
    try:
        data = json.loads(request.body)
        immunization_data = json.loads(data.get("p_child_immunizations", None))
        monitoring_data = json.loads(data.get("child_monitoring", None))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    breast_feeding_checks = [BreastFeedingCheckRequest(**i) for i in data.get("p_bf_checks", [])]
    child_screening = ChildScreeningRequest(**data.get("screening", {}))
    iron_supplements = ChildIronSupplementRequest(**data.get("iron_supplements", {}))
    vitamins = [ChildVitaminsRequest(**i) for i in data.get("vitamins", [])]
    initial_immunization = ImmunizationViewUtility.parse_immunization_payload(immunization_data)
    monitoring = ChildMonitoringRequest(
        check_date=monitoring_data[0].get("date", None),
        age=monitoring_data[0].get("age", None),
        wt=monitoring_data[0].get("wt", None),
        temp=monitoring_data[0].get("temp", None),
        ht=monitoring_data[0].get("ht", None),
        findings=monitoring_data[0].get("findings", None),
        notes=monitoring_data[0].get("notes", None),
    )
    
    initial_data = ChildVisitRequest(
        p_child_id=data.get("p_child_id", None),
        p_child_record_id=None,
        p_assessed_by_id=request.session.get("auth", None).get("staff_id", None),
        p_visit_date=data.get("p_visit_date", None),
        p_feeding_type_id=data.get("p_feeding_type_id", None),
        p_referred_nbs_date=data.get("p_referred_nbs_date", None),
        p_child_immunizations=None,
        p_bf_checks=breast_feeding_checks,
        p_monitoring_logs=monitoring,
        p_screening=child_screening,
        p_iron_supplements=iron_supplements,
        p_vitamin_a=vitamins,
    )
    
    try:
        res = service.execute_child_visit(initial_data, initial_immunization)
        
        if not res:
            return JsonResponse({"error": "Failed to create child visit"}, status=500)

        return JsonResponse({"message": "Child visit created successfully", "child_visit_id": res}, status=201)        
    except (PersonNotFoundException, PrescriptionException, ChildVisitException) as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception:
        return JsonResponse({"error": SOMETHING_WENT_WRONG}, status=500)
    

@csrf_protect
@require_http_methods(["GET"])
@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
@inject
def child_basic_info_http(
    request: HttpRequest, 
    q: int, 
    service: IChildService = Provide[AppContainer.child_service]) -> JsonResponse:
    try:
        res = service.execute_get_child_basic_info(q)
        return JsonResponse({"message": res.__dict__}, status=200)
    except Exception as e:
        return JsonResponse({"error": "Something went wrong, unable to retrieve child basic information"}, status=400)

@require_http_methods(["POST"])
@session_login_required
@role_required(*ROLE_MIDWIFE)
@csrf_protect
@nocache
@inject
def anc_care_http(request: HttpRequest, service: IAntenatalCareService = Provide[AppContainer.antenatal_care_service]) -> JsonResponse:
    
    if request.content_type != "application/json":
        return JsonResponse({"error": "Unsupported Media Type"}, status=415)
    
    try:
        data = json.loads(request.body)
        
        raw_lab_results = data.get("p_lab_results")
        raw_tt_vacc = data.get("p_tt_vaccines")

        if isinstance(raw_lab_results, str):
            raw_lab_results = json.loads(raw_lab_results)

        if isinstance(raw_tt_vacc, str):
            raw_tt_vacc = json.loads(raw_tt_vacc)

        data = JSONCustomUtility.clean_empty_strings(data)
        
        staff_id = request.session.get("auth", None).get("staff_id", None)
        
        init_data = AntenatalCareRequest(**data, p_assessed_by_id=staff_id)
        tt_vaccines = ANCViewUtility.tt_vaccines_obj_converter(raw_tt_vacc)
        lab_results = ANCViewUtility.laboratory_results_obj_converter(raw_lab_results)

        res = service.execute(init_data, lab_results, tt_vaccines)
        
        if not res:
            return JsonResponse({"error": "Failed to process ANC Care"}, status=500)

        return JsonResponse({"message": "ANC Care RPC endpoint placeholder"}, status=200)

    except json.JSONDecodeError:
        logger.error("View (anc_care_http) encountered an exception", exc_info=True)
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except ANCVisitException as e:
        logger.error("View (anc_care_http) encountered an exception", exc_info=True)
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.critical("View (anc_care_http) encountered an exception", exc_info=True)
        return JsonResponse({"error": "Unexpected error encountered. Please try again."}, status=500)



# ================================ ACCOUNT MANAGEMENT ==============================


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
        img.save(buf, format="JPEG", quality=85, optimize=True)
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

@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def staff_selection(request: HttpRequest) -> HttpResponse:
    return render(request, "acc_management/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

@session_login_required
@role_required(*ROLE_MIDWIFE)
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
@role_required(*ROLE_MIDWIFE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:
    pid = (request.POST.get("pid") or "").strip()

    # role_str = (
    #     (request.POST.get("role") or "").strip()
    #     or (request.POST.get("role_locked") or "").strip()
    # )
    role_id = ROLE_BHW

    logger.error("staff_selection_resident ▶ pid=%s role_id=%s", pid, role_id)

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

    if request.method == "POST":
        logger.debug("POST ▶ pid=%s role_id=%s staff_id=%s purok_ids=%s proof_url=%s file=%s",
                     pid, role_id, staff_id, purok_ids, bool(proof_url), bool(proof_file))

    if request.method == "POST" and pid:
        if not (pid or role_id or proof_file or proof_url or base_purok
                or request.POST.getlist("purok_sitio_ids[]")):
            flash_warning(request, "Please select a resident and fill out the form before submitting.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not staff_id:
            logger.error("Validation ✗ Missing staff_id")
            flash_warning(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if not role_id:
            logger.error("Validation ✗ No role selected.") 
            flash_warning(request, "Please choose a staff role.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        if role_id == ROLE_BHW and len(purok_ids) < 1:
            logger.error("Validation ✗ BHW requires ≥1 purok")
            flash_warning(request, "BHW must be assigned to at least one Purok/Sitio.")
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

        # ===========================
        # Create staff request in DB
        # ===========================
        try:
            result = Secretary.insert_res_staff_account_request(
                p_requested_by_id=staff_id,
                p_person_id=int(pid),
                p_role_id=role_id,
                p_supporting_docs=([uploaded_proof_url] if uploaded_proof_url else None),
                p_lupon_sched=None,
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
    proof_form = ResidentProfileform()
    return render(request, "acc_management/staff_selection_resident.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification",
        "page_title": "Account Verification",
        "user_role_template": user_role_template,
        "residents": residents,
        "res_details": res_details,
        "staff_id": staff_id,
        "role_form": role_form,
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
@role_required(*ROLE_MIDWIFE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform(request.POST or None)
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
            flash_success(request, "Personal information saved successfully.")
            logger.info("Step1 ✓ personal info saved to wizard")
            return redirect("midwife:staff_selection_non-resident_docs")
        else:
            # Keep same logic: show validation message; do not expose internals
            logger.error("Validation ✗ Form errors: %s", form.errors.as_json())
            flash_warning(request, "Please correct the errors below.")
            # fall-through to re-render with form errors

    return render(request, "acc_management/staff_selection_nonresident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form': form,
        'redirect': 'midwife:staff_selection_non-resident_docs',
    })

@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres_docs(request: HttpRequest) -> HttpResponse:

    form = ResidentProfileform(request.POST or None, request.FILES or None)
    for f in (
        "res_code", "username", "temp_pass", "res_status", "reg_method",
        "reg_date", "acc_status", "added_by", "home_address",
        "type_of_id", "front_id", "back_id", "res_img", "proof",
    ):
        if f in form.fields:
            form.fields[f].required = False

    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}

    if request.method == "GET":
        if not personal:
            logger.error("Wizard ✗ Missing personal info in session")
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("midwife:staff_selection_non-resident")

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
        return redirect("midwife:staff_selection_non-resident_role_review")

    # GET
    return render(request, "acc_management/supporting_docs.html", {
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
@role_required(*ROLE_MIDWIFE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_nonres_role_review(request: HttpRequest) -> HttpResponse:
    role_form = ChooseRole(request.POST or None)

    wiz = _wiz_get(request)
    personal = wiz.get("personal") or {}
    docs = wiz.get("docs") or {}

    if request.method == "GET":
        if not personal:
            logger.error("Wizard ✗ Missing personal info in session")
            flash_warning(request, "Personal information is missing. Please complete Step 1.")
            return redirect("midwife:staff_selection_non-resident")
        if not docs:
            logger.error("Wizard ✗ Missing docs info in session")
            flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
            return redirect("midwife:staff_selection_non-resident_docs")

        return render(
            request,
            "acc_management/role.html",
            {
                "user_fullname": user_fullname,
                "user_role": user_role,
                "page_path": f"{user_role} / Account Verification",
                "page_title": "Account Verification",
                "user_role_template": user_role_template,
                "role_form": role_form,
                "personal": personal,
                "docs": docs,
            },
        )

    role_str = (request.POST.get("role") or "").strip()
    role_id = int(role_str) if role_str.isdigit() else ROLE_BHW

    purok_ids: List[int] = []
    base_purok = (request.POST.get("purok_sitio") or "").strip()
    if base_purok.isdigit():
        purok_ids.append(int(base_purok))
    for x in request.POST.getlist("purok_sitio_ids[]"):
        x = (x or "").strip()
        if x.isdigit():
            purok_ids.append(int(x))

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

    if not personal:
        flash_warning(request, "Personal information is missing. Please go back to Step 1.")
        return redirect("midwife:staff_selection_non-resident")

    if not docs:
        flash_warning(request, "Supporting documents are missing. Please complete Step 2.")
        return redirect("midwife:staff_selection_non-resident_docs")

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id") or 1
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
        return redirect("midwife:staff_selection_non-resident_docs")

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
        return redirect("midwife:staff_selection_non-resident_docs")

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
            p_lupon_sched=None,
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
            return _smart_redirect(request, "midwife:staff_selection_resident")

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
        "Step3 ✓ staff_request created: req_id=%s role_id=%s purok_ids=%s",
        req_id, role_id, purok_ids
    )
    flash_success(request, f"Staff account request created.")
    
    _wiz_clear(request)
    return redirect("midwife:staff_selection")


@session_login_required
@role_required(*ROLE_MIDWIFE)
@nocache
def staff_list(request):

    try:
        rows = Secretary.get_all_staff_info_summary() or []
    except Exception as e:
        logger.exception("Failed to load staff summaries: %s", e)
        rows = []

    ROLE_BHW_NAME = "BARANGAY HEALTH WORKER"

    def _is_bhw(r):
        rid = r.get("role_id")
        if isinstance(rid, int):
            return rid == ROLE_BHW
        # Fallback: compare role_name (case-insensitive, strip)
        rname = (r.get("role_name") or "").strip().upper()
        return rname == ROLE_BHW_NAME

    rows = [r for r in rows if _is_bhw(r)] 

    # Pagination only
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

    return render(request, "acc_management/staff_list.html", {
        "user_fullname": _user_fullname,
        "user_role": _user_role,
        "page_path": f"{_user_role} / Staff List",
        "page_title": "Staff List (BHW Only)",
        "user_role_template": _user_role_template,
        "form": form,
        "page_obj": page_obj,
        "total_count": paginator.count, 
        "per_page": per_page,
    })



@session_login_required
@role_required(*ROLE_MIDWIFE)
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
@role_required(*ROLE_MIDWIFE)
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
@role_required(*ROLE_MIDWIFE)
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
    return render(request, "acc_management/staff_dets.html", ctx)