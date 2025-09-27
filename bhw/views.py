from django.shortcuts import render
from django.core.paginator import Paginator
from dependency_injector.wiring import inject, Provide

from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.scheduling_service_contract import ISchedulingService
from .forms import SearchActiveScheduleFilter
from .forms import StatusActiveScheduleFilter
from .forms import WeekRangeActiveScheduleFilter
from .forms import Reschedule

# ============================ BHW =================================
# bhw/views_ocr.py (or wherever you keep views)
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.conf import settings

from common.supabase_client import supabase
from common.verify_id import _upload_file, _public_url, verify_id_via_edge

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
@inject
def active_schedule(request, scheduling_service: ISchedulingService = Provide[AppContainer.scheduling_service]):
    pending = scheduling_service.get_active_schedules()
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    print(scheduling_service.get_active_schedules())

    search_form = SearchActiveScheduleFilter()
    status_form = StatusActiveScheduleFilter()
    week_range_form = WeekRangeActiveScheduleFilter()
    reschedule_form = Reschedule()
    
    session = request.session.get("auth")
    user_fullname = session.get("first_name") + " " + session.get("last_name")
    return render(request, "household/quarterly/active_schedule.html", {
        'user_fullname' : user_fullname,
        'user_role' : session.get("role_name"),
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