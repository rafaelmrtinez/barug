import json
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction


from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from barug.utility.custom_date_time_util import DateAndTimeUtility
from barug.utility.messages_util import MessageUtility
from child_health.exception.child_health_record_exception import ChildHealthRecordException
from child_health.forms.bf_feeding_type import BreastFeedingTypeForm
from child_health.forms.child_bf_form import ChildBreastFeedingForm
from child_health.forms.child_birth_supplemention import BirthAndSupplentationForm
from child_health.forms.child_immunization_form import ChildImmunizationForm
from child_health.forms.child_information_form import ChildInformationForm
from child_health.forms.child_visit_form import ChildVisitForm
from child_health.forms.newborn_screening_form import NewbornScreeningForm
from child_health.repository import ChildHealthRecordRepository
from child_health.utilities.immunizations_util import ImmunizationUtility
from src.infra.database.connection_adapter import ConnectionAdapter

import logging

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")
CONNECTION = ConnectionAdapter()
CHILD_HEALTH_REPOSITORY: ChildHealthRecordRepository = ChildHealthRecordRepository(CONNECTION)

# Create your views here.

def child_immunization_http(request: HttpRequest) -> HttpResponse:
    # parse json data
    try:
        data = json.loads(request.body)
        staff = request.session.get("auth").get("staff_id")
        response = CHILD_HEALTH_REPOSITORY.insert_child_immunizations(
            p_child_record_id=data.get("child_health_record_id"),
            p_assessed_by_id=staff,
            p_immunization_type_id=data.get("immunization_type_id"),
            p_immunization_stage_given_id=data.get("immunization_stage_given_id"),
            p_date_given=DateAndTimeUtility.get_current_date()
        )
        
        if not response:
            messages.error(request, "Failed to save immunization data.")
            return JsonResponse({"message": "Failed to save immunization data"}, status=500)

        messages.success(request, "Immunization data saved successfully.")
        return JsonResponse({"message": response}, status=200)
    except ChildHealthRecordException as chre:
        logger.warning("ChildHealthRecordException in child_new_born_screening_http: %s", chre.message)
        messages.warning(request, f"Warning: {chre.message}")
        return JsonResponse({"message": chre.message}, status=400)
    except Exception as e:
        logger.exception("child_new_born_screening_http failed: %s", e)
        messages.error(request, "Failed to submit Newborn Screening Data. Please try again.")
        return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)    

@session_login_required
@role_required(*ACCESS)
@nocache
@require_http_methods(["GET", "POST"])
def child_health_entry(request: HttpRequest, child_health_record_id: int) -> HttpResponse:
    try:
        child_information_form = ChildInformationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, role=None)
        bf_form = ChildBreastFeedingForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        immunizations = ChildImmunizationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        birth_and_supplementation = BirthAndSupplentationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        visit_form = ChildVisitForm()
        new_born_screening = NewbornScreeningForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        visit_log = CHILD_HEALTH_REPOSITORY.fetch_child_monitoring_logs(child_health_record_id)
        bf_type = BreastFeedingTypeForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        
        staff_id = request.session.get("auth").get("staff_id")
        
        logger.info("STAFF ID in child_health_entry: %s", staff_id)
        logger.info("FORM TYPE in POST data: %s", request.POST.get("form_type"))
        
        if request.method == "GET":
            return render(
                request,
                "child_health/chr_entry.html",
                {
                    "form": birth_and_supplementation,
                    "new_born_screening": new_born_screening,
                    "child_information_form": child_information_form,
                    "visit_form": visit_form,
                    "child_health_record_id": child_health_record_id,
                    "bf_form": bf_form,
                    "immunizations": immunizations,
                    "visit_log": visit_log,
                    "bf_type": bf_type,
                },
            )
        
        form_type = request.POST.get("form_type")
        
        if form_type == "newborn_screening_form":
            screening_data = NewbornScreeningForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, data=request.POST)
            if screening_data.is_valid():
                is_success = CHILD_HEALTH_REPOSITORY.insert_new_born_screening_date(
                    p_child_record_id=child_health_record_id, 
                    p_assessed_by_id=staff_id, 
                    p_referred_nbs_date=screening_data.cleaned_data.get("referred_for_newborn_screening"))
                
                if is_success and isinstance(is_success, tuple):
                    messages.success(request, "Newborn Screening data saved successfully.")
                    return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
            else:
                MessageUtility.push_form_errors_as_messages(request, screening_data)
                return render(
                    request,
                    "child_health/chr_entry.html",
                    {
                        "form": birth_and_supplementation,
                        "new_born_screening": screening_data,
                        "child_information_form": child_information_form,
                        "visit_form": visit_form,
                        "child_health_record_id": child_health_record_id,
                        "bf_form": bf_form,
                        "immunizations": immunizations,
                        "visit_log": visit_log,
                        "bf_type": bf_type,
                    },
                )
        elif form_type == "bf_feeding_form":
            bf_data = ChildBreastFeedingForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, data=request.POST)
            
            if bf_data.is_valid():
                is_success = CHILD_HEALTH_REPOSITORY.insert_bf_check(
                    p_child_record_id=child_health_record_id,
                    p_assessed_by_id=staff_id,
                    p_feeding_type_id=bf_data.cleaned_data.get("type_of_feeding"),
                    p_check_date=bf_data.cleaned_data.get("exclusive_bf_check_last")
                )
                print(f"DEBUG: is_success value {is_success}")
                if is_success and isinstance(is_success, tuple):
                    messages.success(request, "Breast Feeding Type saved successfully.")

                    return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
            else:
                MessageUtility.push_form_errors_as_messages(request, bf_data)
                return render(
                    request,
                    "child_health/chr_entry.html",
                    {
                        "form": birth_and_supplementation,
                        "new_born_screening": new_born_screening,
                        "child_information_form": child_information_form,
                        "visit_form": visit_form,
                        "child_health_record_id": child_health_record_id,
                        "bf_form": bf_form,
                        "immunizations": immunizations,
                        "visit_log": visit_log,
                        "bf_type": bf_data,
                    },
                )
            
        else:
            messages.error(request, "Invalid form submission.")
            return render(
                request,
                "child_health/chr_entry.html",
                {
                    "form": birth_and_supplementation,
                    "new_born_screening": new_born_screening,
                    "child_information_form": child_information_form,
                    "visit_form": visit_form,
                    "child_health_record_id": child_health_record_id,
                    "bf_form": bf_form,
                    "immunizations": immunizations,
                    "visit_log": visit_log,
                    "bf_type": bf_type,
                },
            )
    except ChildHealthRecordException as chre:
        logger.warning("ChildHealthRecordException in child_health_entry: %s", chre.message)
        messages.warning(request, f"Warning: {chre.message}")
        return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
    except Exception as e:
        logger.exception("child_health_entry failed: %s", e)
        messages.error(request, "An unexpected error occurred. Please try again later.")
        return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
        
        

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
    try:
        if request.method == "POST":
            child_information_form = ChildInformationForm(
            chr_repo=CHILD_HEALTH_REPOSITORY,
            child_health_record_id=None,
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
            res = CHILD_HEALTH_REPOSITORY.insert_chr_record(
                p_staff_id=request.session.get("auth").get("staff_id"),
                p_person_id=child_information_form.cleaned_data.get("child_health_record_id"),
                p_birth_order=child_information_form.cleaned_data.get("birth_order").__str__(),
                p_delivery_place_type_id=int(child_information_form.cleaned_data.get("place_of_delivery")),
            )
            if not res or not isinstance(res, tuple):
                messages.error(request, "Failed to create child health record.")
                return render(
                    request,
                    "child_health/create_chr.html",
                    {
                        "form": child_information_form,
                    },
                )
            messages.success(request, "Child Health Record created successfully.")
            return redirect('child_health:create_child_health_record')
        child_information_form = ChildInformationForm(
            chr_repo=CHILD_HEALTH_REPOSITORY,
            child_health_record_id=None,
            role=request.session.get("auth").get("role_name"),
        )
        return render(
            request,
            "child_health/create_chr.html",
            {
                "form": child_information_form,
            },
        )
    except ChildHealthRecordException as chre:
        logger.error("ChildHealthRecordExcetion: %s", chre.message)
        messages.warning(request, f"Warning: {chre.message}")
        return render(
            request,
            "child_health/create_chr.html",
            {
                "form": child_information_form,
            },
        )
    except Exception as e:
        logger.exception("create_child_health_record failed: %s", e)
        messages.error(request, "An error occurred while creating the child health record.")
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
    # rows = CHILD_HEALTH_REPOSITORY.fetch_all_basic_records()
    rows = CHILD_HEALTH_REPOSITORY.fetch_all_basic_chr_record()
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    return render(
        request,
        "child_health/child_record.html",
        {
            "page_obj": page_obj,
        },
    )
