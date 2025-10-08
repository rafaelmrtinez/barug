# midwife/views.py
from __future__ import annotations

import json

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.views.decorators.http import require_http_methods
from dependency_injector.wiring import inject, Provide

from django.views.decorators.csrf import csrf_protect

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    HttpResponseNotAllowed,
)
from django.shortcuts import render, redirect
from django.template.loader import render_to_string

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from barug.error_messages import SOMETHING_WENT_WRONG
from barug.utility.json_utility import JSONCustomUtility
from src.app.services.anc_service_utility import ANCServiceUtility
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

import logging

logger = logging.getLogger(__name__)

# -------------------- Role / UI globals (unchanged) --------------------
ROLE_MIDWIFE = ("MIDWIFE", "Midwife", "midwife")
# This was added to allow extended roles to access/re-use features such as resident search
FEATURE_ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "Super Admin")
user_fullname = "laname fname mname suffix"
user_role = "MIDWIFE"
user_role_template = user_role.lower().replace(" ", "_")


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
        tities_vacc = data.get("p_tt_vaccines")

        if isinstance(raw_lab_results, str):
            raw_lab_results = json.loads(raw_lab_results)

        if isinstance(tities_vacc, str):
            tities_vacc = json.loads(tities_vacc)

        data = JSONCustomUtility.clean_empty_strings(data)
        
        init_data = AntenatalCareRequest(**data)
        init_data.p_assessed_by_id = request.session.get("auth", None).get("staff_id", None)

        res = service.execute(init_data, raw_lab_results, tities_vacc)
        
        if not res:
            return JsonResponse({"error": "Failed to process ANC Care"}, status=500)

        return JsonResponse({"message": "ANC Care RPC endpoint placeholder"}, status=200)

    except json.JSONDecodeError:
        logger.error(f"View (anc_care_http) = {e}")
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except ANCVisitException as e:
        logger.error(f"View (anc_care_http) = {e}")
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.critical(f"View (anc_care_http) = {e}")
        return JsonResponse({"error": "Unexpected error encountered. Please try again."}, status=500)
