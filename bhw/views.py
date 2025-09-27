from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from .forms import SearchActiveScheduleFilter
from .forms import StatusActiveScheduleFilter
from .forms import WeekRangeActiveScheduleFilter
from .forms import Reschedule

# ============================ BHW =================================
# bhw/views_ocr.py (or wherever you keep views)
from django.http import JsonResponse, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.http import require_http_methods
from django.conf import settings

from common.supabase_client import supabase
from common.verify_id import _upload_file, _public_url, verify_id_via_edge

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from django.contrib import messages  # for modal POST success toasts

# map dropdown -> valid_id_type_id (replace with real lookup!)
IDTYPE_TO_ID = {
    "ephil_id": 2,
    "philid": 2,
    "drivers_license": 6,
    # ...
}

@require_http_methods(["POST"])
def verify_valid_id_view(request: HttpRequest):
    """
    Expected multipart/form-data:
      - supabase_uid: str  (Auth UID used in 'person/{uid}/...')
      - legit_person_id: int (your numeric person_id for RPC)
      - id_type: str (e.g., 'ePhil ID' or already normalized)
      - profile_name: str
      - front: file
      - back: file
      - selfie: file
    """
    try:
        supabase_uid = request.POST.get("supabase_uid") or ""
        legit_person_id = int(request.POST.get("legit_person_id") or 0)
        id_type_raw = request.POST.get("id_type") or ""
        profile_name = request.POST.get("profile_name") or ""

        front = request.FILES.get("front")
        back = request.FILES.get("back")
        selfie = request.FILES.get("selfie")

        if not (supabase_uid and legit_person_id and id_type_raw and profile_name and front and back and selfie):
            return JsonResponse({"ok": False, "error": "Missing required fields/files."}, status=400)

        # normalize id_type like your RN code
        id_type_code = (
            id_type_raw.lower()
            .replace("’", "")
            .replace("'", "")
            .replace(r"[^a-z0-9]+", " ")
            .strip()
            .replace(" ", "_")
        )

        base = f"person/{supabase_uid}"
        # Give each upload a fixed filename (to match your RN storage layout)
        front_key = f"{base}/front.jpg"
        back_key = f"{base}/back.jpg"
        selfie_key = f"{base}/selfie.jpg"

        _upload_file(front, front.content_type, front_key)
        _upload_file(back, back.content_type, back_key)
        _upload_file(selfie, selfie.content_type, selfie_key)

        # Edge Function expects STORAGE PATHS (keys), not the full public URLs
        res = verify_id_via_edge(
            supabase_uid=supabase_uid,
            profile_name=profile_name,
            id_type_code=id_type_code,
            front_path=front_key,
            back_path=back_key,
            selfie_path=selfie_key,
        )

        if not res.ok:
            # include any checks the function sent back
            return JsonResponse(
                {"ok": False, "status": res.status, "data": res.data},
                status=422,
            )

        # If PASSED — save via RPC (mirror of your RN call)
        valid_id_type_id = IDTYPE_TO_ID.get(id_type_code)
        if not valid_id_type_id:
            return JsonResponse(
                {"ok": False, "error": f'ID type "{id_type_code}" is not mapped to a valid_id_type_id.'},
                status=400,
            )

        # If your bucket is public and you want to store public URLs (same as mobile):
        front_url = _public_url(front_key)
        back_url = _public_url(back_key)
        selfie_url = _public_url(selfie_key)

        rpc = supabase.rpc(
            "insert_valid_id",
            {
                "p_person_id": legit_person_id,
                "p_valid_id_type_id": valid_id_type_id,
                "p_selfie_path": selfie_url,
                "p_valid_id_front": front_url,
                "p_valid_id_back": back_url,
            },
        ).execute()

        if getattr(rpc, "error", None):
            return JsonResponse({"ok": False, "error": str(rpc.error)}, status=500)

        return JsonResponse({"ok": True, "status": res.status, "edge": res.data})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

# ============================ BHW =================================

user_fullname = 'laname fname mname suffix'
user_role = 'Barangay Health Worker'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def active_schedule(request):
    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    search_form = SearchActiveScheduleFilter()
    status_form = StatusActiveScheduleFilter()
    week_range_form = WeekRangeActiveScheduleFilter()
    reschedule_form = Reschedule()

    return render(request, "household/quarterly/active_schedule.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : '',
        'page_title' : '',
        'user_role_template' : user_role_template,
        'search_form' : search_form,
        'status_form' : status_form,
        'week_range_form' : week_range_form,
        'reschedule_form' : reschedule_form,
        'page_obj': page_obj,
    })

def household_info(request):
    return render(request, "household/household_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Request Details',
        'page_title' : 'Request Details',
        'user_role_template' : user_role_template
    })

@session_login_required
@role_required("BARANGAY HEALTH WORKER")
@nocache
def dashboard(request: HttpRequest):
    auth = request.session.get("auth")
    profile = getattr(request, "person_profile", None)
    return render(request, "bhw/dashboard.html", {
        "page_path": f"Barangay Health Worker/Dashboard",
        "page_title": "Dashboard",
        "profile": profile,
        "auth": auth
    })


# ------------------------------------------------------------------
# 🔽 ADDITIONS ONLY — Health Records UI (list + detail + modals)
#     (Uses sample data so you can preview immediately)
# ------------------------------------------------------------------

# Accept common role spellings just in case
ROLE_BHW = ("BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw")

def _sample_registry():
    # Replace with real query later
    return [
        {"id": 1, "name": "Maria Santos",  "family_no": "F-001", "ufc_no": "",       "purok": "Kanipaan", "kind": "maternal"},
        {"id": 2, "name": "Jethro Santos", "family_no": "F-002", "ufc_no": "UFC-12", "purok": "Kanipaan", "kind": "child"},
        {"id": 3, "name": "Ana Rivera",    "family_no": "F-010", "ufc_no": "",       "purok": "Pampango", "kind": "maternal"},
    ]

def _detail_maternal(pk: int):
    return {
        "id": pk, "kind": "maternal", "name": "Maria Santos", "age": 28,
        "family_no": "F-001", "address": "Purok Kanipaan",
        "present": {"gravida": 2, "para": 1, "lmp": "2025-05-01", "edc": "2026-02-05"},
        "tt": [{"dose": "TT1", "date": "2024-11-10"}, {"dose": "TT2", "date": "2025-01-12"}],
        "anc": [{"date": "2025-06-10", "ga": "8w", "bp": "110/70", "wt": "54 kg", "fht": "—", "remarks": "Initial"}],
        "labs": {"Urinalysis": "Normal", "Syphilis": "NR"},
        "ogct_50": "85 mg/dL", "ogct_100": "—",
        "plan_delivery": "NSVD – District Hospital", "plan_nbs": True,
    }

def _detail_child(pk: int):
    return {
        "id": pk, "kind": "child", "name": "Jethro Santos", "sex": "M",
        "family_no": "F-002", "ufc_no": "UFC-12", "dob": "2025-02-03", "birth_order": 1,
        "place_of_delivery": "Hospital (Gov’t)", "birth_weight": "3.2 kg",
        "feeding": "Exclusive BF", "mother": "Maria Santos", "father": "Joel Santos",
        "immunizations": [{"name": "BCG", "doses": ["2025-02-04", "", "", ""]}],
        "visits": [{"date": "2025-03-10", "age": "1 mo", "wt": "4.0 kg", "temp": "36.6", "ht": "54 cm", "findings": "Healthy", "notes": "—"}],
    }

@session_login_required
@role_required(*ROLE_BHW)
@nocache
def records(request: HttpRequest) -> HttpResponse:
    rows = _sample_registry()
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    return render(request, "bhw/records.html", {
        "page_path": "Barangay Health Worker / Records",
        "page_title": "Records",
        "q": request.GET.get("q",""),
        "types": request.GET.getlist("type"),
        "puroks": request.GET.getlist("purok"),
        "statuses": request.GET.getlist("status"),
        "types_all": ["maternal","child"],
        "puroks_all": ["Kanipaan","Pampango","Lutaw-lutaw","Mauco"],
        "statuses_all": ["active","completed","archived"],
        "active_count": len(request.GET.getlist("type")) + len(request.GET.getlist("purok")) + len(request.GET.getlist("status")),
        "page_obj": page_obj,
    })

@session_login_required
@role_required(*ROLE_BHW)
@nocache
def record_detail(request: HttpRequest, kind: str, record_id: int) -> HttpResponse:
    rec = _detail_maternal(record_id) if kind == "maternal" else _detail_child(record_id)
    return render(request, "bhw/record_detail.html", {
        "page_path": "Barangay Health Worker / Record Details",
        "page_title": "Record Details",
        "rec": rec,
    })

# modal POST endpoints (no-op; for working UI now)
@session_login_required
@role_required(*ROLE_BHW)
def add_anc_visit(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    messages.success(request, "ANC visit saved (demo).")
    return redirect("bhw:record_detail", kind="maternal", record_id=record_id)

@session_login_required
@role_required(*ROLE_BHW)
def add_child_visit(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Child visit saved (demo).")
    return redirect("bhw:record_detail", kind="child", record_id=record_id)

@session_login_required
@role_required(*ROLE_BHW)
def add_vaccine(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    messages.success(request, "Vaccine dose saved (demo).")
    return redirect("bhw:record_detail", kind="child", record_id=record_id)


# ----------------------- NEW: Maternal intake (BHW create) -------------------
from django.contrib import messages
from django.shortcuts import redirect
from .forms import MaternalBhwIntakeForm

def _parse_csv_ints(s: str | None) -> list[int] | None:
    if not s:
        return None
    out = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(int(tok))
        except Exception:
            continue
    return out or None

@session_login_required
@role_required("BARANGAY HEALTH WORKER")
@nocache
def maternal_new(request: HttpRequest):
    """
    BHW creates a Maternal Health Record using the RPC create_maternal_health_record.
    Midwife fields are left as None for now.
    """
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    if request.method == "POST":
        form = MaternalBhwIntakeForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            payload = {
                # Required context
                "p_staff_id": int(staff_id) if staff_id else None,
                "p_person_id": int(cd["person_id"]),
                "p_husband_id": int(cd["husband_id"]) if cd.get("husband_id") else None,
                "p_family_id": int(cd["family_id"]) if cd.get("family_id") else None,

                # Anthropometrics
                "p_weight": cd.get("weight"),
                "p_height": cd.get("height"),
                "p_bmi_status_id": int(cd["bmi_status_id"]) if cd.get("bmi_status_id") else None,

                # Plans
                "p_place_of_delivery_plan": cd.get("place_of_delivery_plan") or None,
                "p_newborn_screening_plan": bool(cd.get("newborn_screening_plan")),

                # Past history
                "p_prev_illness": cd.get("prev_illness") or None,
                "p_prev_hospitalization": cd.get("prev_hospitalization") or None,
                "p_prev_preg_complication": cd.get("prev_preg_complication") or None,

                "p_num_children_born_alive": cd.get("num_children_born_alive"),
                "p_num_children_living": cd.get("num_children_living"),
                "p_num_abortion": cd.get("num_abortion"),
                "p_num_stillbirth": cd.get("num_stillbirth"),
                "p_num_large_babies": cd.get("num_large_babies"),
                "p_has_diabetes": bool(cd.get("has_diabetes")),
                "p_gravida": cd.get("gravida"),
                "p_para": cd.get("para"),

                # Optional categorized flags (IDs)
                "p_checklist_item_ids": _parse_csv_ints(cd.get("checklist_item_ids")),
                "p_risk_category_ids": _parse_csv_ints(cd.get("risk_category_ids")),

                # Midwife-owned fields (set None/empty for now)
                "p_is_fullterm": None,
                "p_is_preterm": None,
                "p_lmp": None,
                "p_edc": None,
                "p_iron_start_date": None,
                "p_iron_end_date": None,
                "p_deworming_given_date": None,
                "p_tt_vaccines": None,  # jsonb
                "p_anc_visits": None,   # jsonb
                "p_lab_results": None,  # jsonb
                "p_prev_pregs": None,   # jsonb
            }

            try:
                res = supabase.rpc("create_maternal_health_record", payload).execute()
                if getattr(res, "error", None):
                    messages.error(request, f"RPC error: {res.error.message}")
                else:
                    messages.success(request, "Maternal health record created.")
                    return redirect("bhw:maternal_new")  # or a detail/list page
            except Exception as e:
                messages.error(request, f"Failed to save: {e}")

        else:
            messages.error(request, "Please fix the form errors below.")
    else:
        form = MaternalBhwIntakeForm()

    return render(request, "bhw/maternal_new.html", {
        "page_path": "Barangay Health Worker / Maternal Records / New",
        "page_title": "New Maternal Record (BHW Intake)",
        "form": form,
    })
