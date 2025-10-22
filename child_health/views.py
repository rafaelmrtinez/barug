from datetime import datetime
import json
from pprint import pprint
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

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
from child_health.forms.iron_intake_form import IronIntakeForm
from child_health.forms.newborn_screening_form import NewbornScreeningForm
from child_health.forms.vitamin_form import VitaminForm
from child_health.repository import ChildHealthRecordRepository
from child_health.utilities.immunizations_util import ImmunizationUtility
from src.app.services.child_health_services import ChildHealthService
from src.app.transfer_objects.request.child_health_version_two.child_monitoring_log import ChildMonitoringLog
from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2
from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException
from src.infra.database.connection_adapter import ConnectionAdapter

import logging

from src.infra.repositories.child_health_repository import ChildHealthRepository

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")
CONNECTION = ConnectionAdapter()
CHILD_HEALTH_REPOSITORY: ChildHealthRecordRepository = ChildHealthRecordRepository(CONNECTION)

# Create your views here.

@session_login_required
@role_required(*ACCESS)
@nocache
@require_http_methods(["POST"])
@csrf_protect
def child_immunization_http(request: HttpRequest) -> HttpResponse:
    try:
        data = json.loads(request.body or "{}")
        staff_id = request.session.get("auth").get("staff_id")
        child_record_id = data.get("child_health_record_id")
        immunization_type_id = data.get("immunization_type_id")
        immunization_stage_given_id = data.get("immunization_stage_given_id")
        date_given_str = data.get("date_given")
        if not all([child_record_id, immunization_type_id, immunization_stage_given_id]):
            return JsonResponse({
                "message": "Missing required immunization fields."
            }, status=400)
        if date_given_str:
            try:
                date_given = datetime.strptime(date_given_str, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({
                    "message": f"Invalid date format: {date_given_str}. Expected YYYY-MM-DD."
                }, status=400)
        else:
            date_given = DateAndTimeUtility.get_current_date()
        immunization_data = ImmunizationRequestVersion2(
            p_child_record_id=child_record_id,
            p_assessed_by_id=staff_id,
            p_immunization_type_id=immunization_type_id,
            p_immunization_stage_given_id=immunization_stage_given_id,
            p_date_given=date_given
        )
        service = ChildHealthService(ChildHealthRepository(ctx=CONNECTION))
        response = service.execute_insert_child_immunization(immunization=immunization_data)
        if not response:
            return JsonResponse({"message": "Failed to save immunization data."}, status=500)
        return JsonResponse({"message": response}, status=200)
    except (ChildHealthRecordException, ChildHealthDomainException) as chre:
        logger.warning("ChildHealth exception in child_immunization_http: %s", chre.message)
        return JsonResponse({"message": chre.message}, status=400)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON body in child_immunization_http.")
        return JsonResponse({"message": "Invalid JSON data."}, status=400)
    except Exception as e:
        logger.exception("child_immunization_http failed: %s", e)
        return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)


# @session_login_required
# @role_required(*ACCESS)
# @nocache
# @require_http_methods(["POST"])
# @csrf_protect
# def child_immunization_http(request: HttpRequest) -> HttpResponse:
#     # parse json data
#     try:
#         data = json.loads(request.body)
#         staff = request.session.get("auth").get("staff_id")
#         immunization_data = ImmunizationRequestVersion2(
#             p_child_record_id=data.get("child_health_record_id"),
#             p_assessed_by_id=staff,
#             p_immunization_type_id=data.get("immunization_type_id"),
#             p_immunization_stage_given_id=data.get("immunization_stage_given_id"),
#             p_date_given=DateAndTimeUtility.get_current_date()
#         )
#         service = ChildHealthService(ChildHealthRepository(ctx=CONNECTION))
#         response = service.execute_insert_child_immunization(immunization=immunization_data)
#         if not response:
#             # messages.error(request, "Failed to save immunization data.")
#             return JsonResponse({"message": "Failed to save immunization data"}, status=500)
#         # messages.success(request, "Immunization data saved successfully.")
#         return JsonResponse({"message": response}, status=200)
#     except (ChildHealthRecordException, ChildHealthDomainException) as chre:
#         logger.warning("ChildHealthRecordException in child_new_born_screening_http: %s", chre.message)
#         # messages.warning(request, f"Warning: {chre.message}")
#         return JsonResponse({"message": chre.message}, status=400)
#     except ValueError as ve:
#         logger.warning("ValueError in child_new_born_screening_http: %s", str(ve))
#         # messages.warning(request, f"Warning: {str(ve)}")
#         return JsonResponse({"message": str(ve)}, status=400)
#     except Exception as e:
#         logger.exception("child_new_born_screening_http failed: %s", e)
#         # messages.error(request, "Failed to submit Newborn Screening Data. Please try again.")
#         return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)    

@session_login_required
@role_required(*ACCESS)
@nocache
@require_http_methods(["GET", "POST"])
def child_health_entry(request: HttpRequest, child_health_record_id: int) -> HttpResponse:
    try:
        role = request.session.get("auth").get("role_name").lower()
        child_information_form = ChildInformationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, role=role)
        bf_form = ChildBreastFeedingForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        immunizations = ChildImmunizationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        birth_and_supplementation = BirthAndSupplentationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        vitamin_form = VitaminForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        iron_intake_form = IronIntakeForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        visit_form = ChildVisitForm()
        new_born_screening = NewbornScreeningForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        visit_log = CHILD_HEALTH_REPOSITORY.fetch_child_monitoring_logs(child_health_record_id)
        staff_id = request.session.get("auth").get("staff_id")
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
                    "vitamin_form": vitamin_form,
                    "iron_intake_form": iron_intake_form
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
                        "vitamin_form": vitamin_form,
                        "iron_intake_form": iron_intake_form
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
                        "vitamin_form": vitamin_form,
                        "iron_intake_form": iron_intake_form,
                    },
                )
        elif form_type == "child_visit_form":
            visit_data = ChildVisitForm(data=request.POST)
            if visit_data.is_valid():
                visit_data.cleaned_data.pop("form_type", None)
                log = ChildMonitoringLog(**visit_data.cleaned_data)
                res = CHILD_HEALTH_REPOSITORY.insert_child_monitoring_log(log=log, chr_id=child_health_record_id, staff_id=staff_id)
                logger.info("Insert Child Monitoring Log Result: %s", res)
                messages.success(request, "Child Monitoring Log saved successfully.")
                return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
            else:
                messages.warning(request, "Please correct the errors below.")
                return render(
                    request,
                    "child_health/chr_entry.html",
                    {
                        "form": birth_and_supplementation,
                        "new_born_screening": new_born_screening,
                        "child_information_form": child_information_form,
                        "visit_form": visit_data,
                        "child_health_record_id": child_health_record_id,
                        "bf_form": bf_form,
                        "immunizations": immunizations,
                        "visit_log": visit_log,
                        "vitamin_form": vitamin_form,
                        "iron_intake_form": iron_intake_form,
                    },
                )
        elif form_type == "birth_and_supplementation_form":
            birth_and_supplementation = BirthAndSupplentationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, data=request.POST)
            if birth_and_supplementation.is_valid():
                birth_and_supplementation.cleaned_data.pop("form_type", None)
                result = CHILD_HEALTH_REPOSITORY.insert_child_screening(
                    chr_id=child_health_record_id,
                    assessed_by_id=staff_id,
                    date_assessed=birth_and_supplementation.cleaned_data.get("data_assessed"),
                    anemic_seen=birth_and_supplementation.cleaned_data.get("anemia_2_59_seen") or None,
                    anemic_given_iron=birth_and_supplementation.cleaned_data.get("anemia_2_59_given_iron") or None,
                    birth_weight=birth_and_supplementation.cleaned_data.get("birth_weight"),
                    is_low_birth_weight=birth_and_supplementation.cleaned_data.get("low_birth_weight"),
                    seen_2_6_mos=birth_and_supplementation.cleaned_data.get("birth_wt_seen") or None,
                    given_2_6_mos=birth_and_supplementation.cleaned_data.get("birth_wt_given_iron") or None,
                )
                logger.info("Insert Child Screening Result: %s", result)
                if not result:
                    messages.error(request, "Failed to save Birth and Supplementation data.")
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
                            "vitamin_form": vitamin_form,
                            "iron_intake_form": iron_intake_form,
                        },
                    )
                messages.success(request, "Birth and Supplementation saved successfully.")
                return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
            else:
                messages.warning(request, "Please correct the errors below.")
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
                        "vitamin_form": vitamin_form,
                        "iron_intake_form": iron_intake_form,
                    },
                )
        elif form_type == "iron_intake_form":
            iron_intake_data = IronIntakeForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, data=request.POST)
            if iron_intake_data.is_valid():
                response = CHILD_HEALTH_REPOSITORY.upsert_iron_supplement_completion_by_chr_id(
                    chr_id=child_health_record_id,
                    assessed_by_id=staff_id,
                    date_started=iron_intake_data.cleaned_data.get("date_iron_started"),
                    date_completed=iron_intake_data.cleaned_data.get("date_iron_completed")
                )
                if response and isinstance(response, tuple):
                    messages.success(request, "Iron Intake data saved successfully.")
                messages.success(request, "Iron Intake data saved successfully.")
                return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
            else:
                MessageUtility.push_form_errors_as_messages(request, iron_intake_data)
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
                        "vitamin_form": vitamin_form,
                        "iron_intake_form": iron_intake_data,
                    },
                )
        elif form_type == "vitamin_form":
            vitamin_form = VitaminForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, data=request.POST)
            if vitamin_form.is_valid():
                response = CHILD_HEALTH_REPOSITORY.upsert_vitamin_a_stage_by_chr_id(
                    p_child_record_id=child_health_record_id,
                    staff_id=staff_id,
                    stage_id=vitamin_form.cleaned_data.get("vit_a_stage"),
                    date_given=DateAndTimeUtility.get_current_date(),
                )
                if response and isinstance(response, tuple):
                    messages.success(request, "Vitamin A data saved successfully.")
                return redirect('child_health:child_health_entry', child_health_record_id=child_health_record_id)
            else:
                MessageUtility.push_form_errors_as_messages(request, vitamin_form)
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
                        "vitamin_form": vitamin_form,
                        "iron_intake_form": iron_intake_form,
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
                    "vitamin_form": vitamin_form,
                    "iron_intake_form": iron_intake_form,
                },
            )
    except ChildHealthRecordException as chre:
        logger.warning("ChildHealthRecordException in child_health_entry: %s", chre.message)
        messages.warning(request, f"Warning: {chre.message}")
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
                "vitamin_form": vitamin_form,
                "iron_intake_form": iron_intake_form,
            },
        )
    except Exception as e:
        logger.exception("child_health_entry failed: %s", e)
        messages.error(request, "An unexpected error occurred. Please try again later.")
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
                "vitamin_form": vitamin_form,
                "iron_intake_form": iron_intake_form,
            },
        )
        
        

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
                MessageUtility.push_form_errors_as_messages(request, child_information_form)
                return render(
                    request,
                    "child_health/create_chr.html",
                    {
                        "form": child_information_form,
                    },
                )
            res = CHILD_HEALTH_REPOSITORY.insert_chr_record(
                p_staff_id=request.session.get("auth").get("staff_id"),
                p_person_id=request.POST.get("child_id"),
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
