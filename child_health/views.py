from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.http import require_http_methods


from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from child_health.forms.child_bf_form import ChildBreastFeedingForm
from child_health.forms.child_birth_supplemention import BirthAndSupplentationForm
from child_health.forms.child_immunization_form import ChildImmunizationForm
from child_health.forms.child_information_form import ChildInformationForm
from child_health.forms.child_visit_form import ChildVisitForm
from child_health.forms.newborn_screening_form import NewbornScreeningForm
from child_health.repository import ChildHealthRecordRepository
from src.infra.database.connection_adapter import ConnectionAdapter

import logging

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")
CONNECTION = ConnectionAdapter()
CHILD_HEALTH_REPOSITORY: ChildHealthRecordRepository = ChildHealthRecordRepository(CONNECTION)

# Create your views here.

def fetch_person_and_house_basic_details_http(request: HttpRequest, person_id: int) -> JsonResponse:
    try:
        repo = CHILD_HEALTH_REPOSITORY
        details = repo.fetch_person_and_house_basic_details_by_id(person_id)
        if not details:
            return JsonResponse({"ok": False, "error": "Person not found"}, status=404)
        return JsonResponse({"ok": True, "details": details})
    except Exception as e:
        logger.exception("fetch_person_and_house_basic_details failed: %s", e)
        return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)

def fetch_person_basic_details_http(request: HttpRequest, person_id: int) -> JsonResponse:
    try:
        repo = CHILD_HEALTH_REPOSITORY
        details = repo.find_person_basic_details_by_id(person_id)
        if not details:
            return JsonResponse({"ok": False, "error": "Person not found"}, status=404)
        return JsonResponse({"ok": True, "details": details})
    except Exception as e:
        logger.exception("fetch_person_basic_details failed: %s", e)
        return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)

@session_login_required
@role_required(*ACCESS)
@nocache
@require_http_methods(["GET"])
def find_person_http(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"ok": True, "count": 0, "results": []})
    try:
        rows = CHILD_HEALTH_REPOSITORY.match_person_by_key(q)  # [{'person_id':..., 'full_name':..., 'address':...}, ...]
        results = [{"id": r["person_id"], "name": r["full_name"], "address": r.get("address") or ""} for r in rows]
        logger.info("FIND PERSON RESULTS: %s", results)
        return JsonResponse({"ok": True, "count": len(results), "results": results})
    except Exception as e:
        logger.exception("find_person failed: %s", e)
        return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)

@session_login_required
@role_required(*ACCESS)
@nocache
def create_child_health_record(request: HttpRequest) -> HttpResponse:
    
    if request.method == "POST":
        child_information_form = ChildInformationForm(
        chr_repo=CHILD_HEALTH_REPOSITORY,
        child_id=None,
        role=request.session.get("auth").get("role_name"),
        data=request.POST
    )
        if not child_information_form.is_valid():
            messages.warning(request, "Only father and occupation are optional.")
            return render(
                request,
                "child_health/create_chr.html",
                {
                    "form": child_information_form,
                },
            )
        
        return redirect('child_health:create_child_health_record')
    
    child_information_form = ChildInformationForm(
        chr_repo=CHILD_HEALTH_REPOSITORY,
        child_id=None,
        role=request.session.get("auth").get("role_name"),
    )
    return render(
        request,
        "child_health/create_chr.html",
        {
            "form": child_information_form,
        },
    )

@session_login_required
@role_required(*ACCESS)
@nocache
def child_record_list_view(request: HttpRequest) -> HttpRequest:
    rows = CHILD_HEALTH_REPOSITORY.fetch_all_basic_records()
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    return render(
        request,
        "child_health/child_record.html",
        {
            "page_obj": page_obj,
        },
    )


@session_login_required
@role_required(*ACCESS)
@nocache
def child_health_entry(request: HttpRequest, child_id: int) -> HttpResponse:
    chr_id = CHILD_HEALTH_REPOSITORY.fetch_child_record_id_by_person_id(child_id)
    child_information_form = ChildInformationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_id=child_id, role=None)
    newborn_screening_form = NewbornScreeningForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_id=child_id)
    bf_form = ChildBreastFeedingForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_id=child_id)
    immunizations = ChildImmunizationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_id=child_id)
    birth_and_supplementation = BirthAndSupplentationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_id=child_id)
    visit_form = ChildVisitForm()
    visit_log = CHILD_HEALTH_REPOSITORY.fetch_child_monitoring_logs(chr_id)
    print("Visit Log:", visit_log)
    return render(
        request,
        "child_health/chr_entry.html",
        {
            "form": birth_and_supplementation,
            "child_information_form": child_information_form,
            "visit_form": visit_form,
            "child_id": child_id,
            "newborn_screening_form": newborn_screening_form,
            "bf_form": bf_form,
            "immunizations": immunizations,
            "visit_log": visit_log,
        },
    )