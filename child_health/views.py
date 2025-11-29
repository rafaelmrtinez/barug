from datetime import datetime
import json
from pprint import pprint
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.core.cache import cache
from django.contrib import messages
import time
import re

from child_health.utilities.repo_sequence import RepoSequence
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from barug.utility.lazy_repository import LazyRepositoryProxy
from barug.utility.messages_util import MessageUtility
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from child_health.forms.child_bf_form import ChildBreastFeedingForm
from child_health.forms.child_birth_supplemention import BirthAndSupplentationForm
from child_health.forms.child_immunization_form import ChildImmunizationForm
from child_health.forms.child_information_form import ChildInformationForm
from child_health.forms.child_visit_form import ChildVisitForm
from child_health.forms.iron_intake_form import IronIntakeForm
from child_health.forms.newborn_screening_form import NewbornScreeningForm
from child_health.forms.vitamin_form import VitaminForm
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.app.services.child_health_services import ChildHealthService
from src.app.transfer_objects.request.child_health_version_two.child_monitoring_log import ChildMonitoringLog
from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2
from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException
from src.infra.database.connection_adapter import ConnectionAdapter
from child_health.utilities.repository_payload_validator import RepositoryPayloadValidator

import logging

from src.infra.repositories.child_health_repository import ChildHealthRepository
from src.infra.repositories.queries.maternal_health_record_queries import MaternalHealthRecordQueries

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin", "barangay health worker")
CONNECTION = ConnectionAdapter()
CHILD_HEALTH_REPOSITORY: ChildHealthRecordRepository = LazyRepositoryProxy(repo_factory=lambda: ChildHealthRecordRepository(CONNECTION))

# Create your views here.
@session_login_required
@role_required(*ACCESS)
@nocache
@require_http_methods(["POST"])
@csrf_protect
def child_immunization_http(request: HttpRequest) -> HttpResponse:
    try:
        data = json.loads(request.body or "{}")
        print(f'Received immunization data: {data}')
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
            date_given = None
        
        immunization_data = ImmunizationRequestVersion2(
            p_child_record_id=child_record_id,
            p_assessed_by_id=staff_id,
            p_immunization_type_id=immunization_type_id,
            p_immunization_stage_given_id=immunization_stage_given_id,
            p_date_given=date_given or None
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

@session_login_required
@role_required(*ACCESS)
@nocache
@require_http_methods(["GET"])
def child_health_entry(request: HttpRequest, child_health_record_id: int) -> HttpResponse:
    try:
        maternal_data = MaternalHealthRecordQueries(CONNECTION)
        role = request.session.get("auth").get("role_name").lower()
        child_information_form = ChildInformationForm(maternal_data=maternal_data,chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id, role=role, is_readonly=True)
        bf_form = ChildBreastFeedingForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        immunizations = ChildImmunizationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        birth_and_supplementation = BirthAndSupplentationForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        vitamin_form = VitaminForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        iron_intake_form = IronIntakeForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        visit_form = ChildVisitForm()
        new_born_screening = NewbornScreeningForm(chr_repo=CHILD_HEALTH_REPOSITORY, child_health_record_id=child_health_record_id)
        visit_log = CHILD_HEALTH_REPOSITORY.fetch_child_monitoring_logs(child_health_record_id)
        print(f"Visit log: {visit_log}")
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
        from src.infra.repositories.queries.person_queries import PersonQuery
        from src.app.adapters.resident_service_adapter import ResidentServiceAdapter
        from src.app.services.resident_service import ResidentService
        from src.infra.repositories.resident_repository import ResidentRepository
        p = ResidentServiceAdapter(ResidentService(ResidentRepository(CONNECTION)), PersonQuery(CONNECTION))
        results = [{"id": r["person_id"], "name": r["full_name"], "address": r.get("address") or ""} for r in p.get_minors_under5_active(key=q, limit=15)]
        return JsonResponse({"ok": True, "count": len(results), "results": results})
    except Exception as e:
        logger.exception("find_person failed: %s", e)
        return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)

@session_login_required
@role_required(*ACCESS)
@nocache
def create_child_health_record(request: HttpRequest) -> HttpResponse:
    try:
        maternal_data = MaternalHealthRecordQueries(CONNECTION)
        if request.method == "POST":
            child_information_form = ChildInformationForm(
            chr_repo=CHILD_HEALTH_REPOSITORY,
            maternal_data=maternal_data,
            child_health_record_id=None,
            role=request.session.get("auth").get("role_name"),
            data=request.POST,
            is_readonly=False,
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
            # Sanitize and validate inputs before repository call
            payload = {
                'staff_id': request.session.get("auth").get("staff_id"),
                'child_id': request.POST.get("child_id"),
                'birth_order': child_information_form.cleaned_data.get("birth_order"),
                'place_of_delivery': child_information_form.cleaned_data.get("place_of_delivery"),
            }
            schema = {
                'staff_id': {'type': 'int', 'required': True},
                'child_id': {'type': 'int', 'required': True},
                'birth_order': {'type': 'int', 'required': True},
                'place_of_delivery': {'type': 'int', 'required': True},
            }

            cleaned_vals, v_errors = RepositoryPayloadValidator.validate_payload(payload, schema)
            if v_errors:
                for e in v_errors:
                    messages.error(request, e)
                return render(
                    request,
                    "child_health/create_chr.html",
                    {
                        "form": child_information_form,
                    },
                )

            # Additional validation: birth_order must be present and >= 1
            # First check: not empty
            raw_birth_order = child_information_form.cleaned_data.get('birth_order')
            if raw_birth_order in (None, ""):
                messages.error(request, "Birth order is required and cannot be empty.")
                return render(
                    request,
                    "child_health/create_chr.html",
                    {
                        "form": child_information_form,
                    },
                )

            # Now ensure it's an integer >= 1
            try:
                birth_order_int = int(raw_birth_order)
            except Exception:
                birth_order_int = None

            if birth_order_int is None or birth_order_int < 1:
                messages.error(request, "Birth order must be a number 1 or greater.")
                return render(
                    request,
                    "child_health/create_chr.html",
                    {
                        "form": child_information_form,
                    },
                )

            res = CHILD_HEALTH_REPOSITORY.insert_chr_record(
                p_staff_id=cleaned_vals.get('staff_id'),
                p_person_id=cleaned_vals.get('child_id'),
                p_birth_order=str(cleaned_vals.get('birth_order')),
                p_delivery_place_type_id=cleaned_vals.get('place_of_delivery'),
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
            maternal_data=maternal_data,
            child_health_record_id=None,
            role=request.session.get("auth").get("role_name"),
            is_readonly=False,
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
    # Raw query as received (for showing back in UI); keep original raw for safe display
    raw_q = request.GET.get("q")
    # Normalize and defensively sanitize
    q = (raw_q or "")
    q = re.sub(r"[\x00-\x1f\x7f]", "", q).strip()
    # Cap query length to prevent abuse
    MAX_Q_LEN = 128
    if len(q) > MAX_Q_LEN:
        q = q[:MAX_Q_LEN]

    # Validate page param
    try:
        page = int(request.GET.get("page", 1))
        if page < 1:
            page = 1
    except Exception:
        page = 1
    # Prevent extremely large page values
    MAX_PAGE = 1000
    if page > MAX_PAGE:
        page = MAX_PAGE

    per_page = 10

    # If there is a search query, use repository-level count + limit/offset
    # to avoid loading all rows into memory. We wrap the repo with a
    # lightweight sequence object so Django's Paginator can call len()
    # and slice() without fetching everything.
    if q:
        # Rate limiting per staff or per IP for basic DOS protection
        auth_info = request.session.get("auth") or {}
        staff_id = auth_info.get("staff_id")
        identifier = staff_id or request.META.get("REMOTE_ADDR", "anon")
        cache_key = f"chr_search_rl:{identifier}"
        window_seconds = 60
        max_requests_per_window = 20
        try:
            count = int(cache.get(cache_key) or 0)
        except Exception:
            count = 0
        if count >= max_requests_per_window:
            messages.error(request, "Search rate limit exceeded. Please wait a minute and try again.")
            total = 0
            p = Paginator([], per_page)
            page_obj = p.get_page(1)
            return render(request, "child_health/child_record.html", {"page_obj": page_obj, "q": raw_q, "total_matches": total})
        else:
            try:
                cache.set(cache_key, count + 1, timeout=window_seconds)
            except Exception:
                # non-fatal: proceed even if cache unavailable
                pass

        # Minimum query length guard to avoid expensive wildcard scans
        if len(q) < 2:
            total = 0
            p = Paginator([], per_page)
            page_obj = p.get_page(1)
            return render(request, "child_health/child_record.html", {"page_obj": page_obj, "q": raw_q, "total_matches": total})

        try:
            total = CHILD_HEALTH_REPOSITORY.count_basic_chr_record_search(q)
            seq = RepoSequence.create(CHILD_HEALTH_REPOSITORY, q, total)
            paginator = Paginator(seq, per_page)
            page_obj = paginator.get_page(page)
        except Exception as e:
            logger.exception("Error searching child records: %s", e)
            messages.error(request, "An error occurred while searching. Please try again later.")
            total = 0
            p = Paginator([], per_page)
            page_obj = p.get_page(1)
            return render(request, "child_health/child_record.html", {"page_obj": page_obj, "q": raw_q, "total_matches": total})
    else:
        try:
            rows = CHILD_HEALTH_REPOSITORY.fetch_all_basic_chr_record()
            page_obj = Paginator(rows, per_page).get_page(page)
            total = None
        except Exception as e:
            logger.exception("Error fetching child records: %s", e)
            messages.error(request, "An error occurred fetching records. Please try again later.")
            p = Paginator([], per_page)
            page_obj = p.get_page(1)
            total = 0

    return render(
        request,
        "child_health/child_record.html",
        {
            "page_obj": page_obj,
            "q": raw_q,
            "total_matches": total,
        },
    )
