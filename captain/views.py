from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from typing import Optional
from django.urls import reverse

from django.shortcuts import render
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.business_service_contract import (
    IBusinessService,
    IBusinessInfoService,
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository
)
from src.app.contracts.household_service_contract import (
    IHouseholdService,
)
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository,
)


from .forms import (
    StaffFilters,
    BusinessFilters,
    HouseholdFilters,
)

CAPTAIN_ROLE = "Barangay Captain"


user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Captain'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

def _to_int_or_none(val) -> Optional[int]:
    try:
        if val in (None, "", "None"):
            return None
        return int(val)
    except Exception:
        return None

@session_login_required
@role_required(CAPTAIN_ROLE)
def dashboard(request):
    return render(request, "captain_dashboard.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'user_role_template' : user_role_template,
    })

def staff_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "staff_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Staff Lits',
        'page_title': 'Staff List',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

def staff_dets(request, staff_id):
    return render(request, "person/staff_dets.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Staff Details : {staff_id}',
        'page_title' : f'Staff Details : {staff_id}',
        'user_role_template' : user_role_template,
    })

# -------------------------------
# RESIDENT
# -------------------------------

def resident_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "resident/resident_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Resident List',
        'page_title': 'Resident List',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

def resident_map_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "resident/resident_map_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Resident Map',
        'page_title': 'Resident Map',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })



# -------------------------------
# HOUSEHOLD
# -------------------------------
@session_login_required
@role_required(CAPTAIN_ROLE)
@csrf_protect
@nocache
@inject
def household_list(
    request: HttpRequest,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponseRedirect | HttpResponseRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = HouseholdFilters(request.GET or None)

    search = request.GET.get("search")
    house_type = _to_int_or_none(request.GET.get("house_type"))
    house_ownership = _to_int_or_none(request.GET.get("house_ownership"))

    rows = household_service.execute(
        search=search,
        house_type=house_type,
        ownership_type=house_ownership,
    )

    paginator = Paginator(rows,10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or house_type is not None or house_ownership is not None) and not form.is_valid():
        form = HouseholdFilters()

    return render(request, "household/household_list.html", {
        'page_path': f'{user_role} / Household List',
        'page_title': 'Household List',
        'page_obj': page_obj,
        'form': form,
        'filters' : {
            'search' : search,
            'house_type' : house_type,
            'house_ownership':  house_ownership,
        },
        "search_url": "captain:ajax_household_search",
    })

@session_login_required
@role_required(CAPTAIN_ROLE)   # change if needed
@nocache
@inject
def ajax_household_search(
    request: HttpRequest,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponse:
    """
    Returns partial HTML for live search.
    Accepts:
      q -> search
      house_type, house_ownership
      tpl -> 'cards' (default) or 'rows'
    """
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")

    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    if tpl_key == "rows":
        template_name = "household/_household_list.html"   # table rows partial
        ctx_key = "rows"
    elif tpl_key == "cards":
        template_name = "household/_households.html"       # cards partial (map list)
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
@role_required(CAPTAIN_ROLE)
@csrf_protect
@nocache
@inject
def household_map_list(
    request: HttpRequest,
    household_service: IHouseholdService = Provide[AppContainer.household_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = HouseholdFilters(request.GET or None)

    search = request.GET.get("search")
    house_type = _to_int_or_none(request.GET.get("house_type"))
    house_ownership = _to_int_or_none(request.GET.get("house_ownership"))

    rows = household_service.execute(
        search=search,
        house_type=house_type,
        ownership_type=house_ownership,
    )

    paginator = Paginator(rows,10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or house_type is not None or house_ownership is not None) and not form.is_valid():
        form = HouseholdFilters()

    return render(request, "household/household_map_list.html", {
        'page_path': f'{user_role} / Household Map',
        'page_title': 'Household Map',
        'page_obj': page_obj,
        'form': form,
        'filters' : {
            'search' : search,
            'house_type' : house_type,
            'house_ownership':  house_ownership,
        },
        "pins_url": reverse("captain:api_household_pins"),
        'search_url': 'captain:ajax_household_search',
    })

@session_login_required
@role_required(CAPTAIN_ROLE)
@csrf_protect
@nocache
@inject
def api_household_pins(
    request: HttpRequest,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
):
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    pins = household_repo.fetch_household_pins(
        search=(request.GET.get("search") or None),
        house_type=_to_int_or_none(request.GET.get("house_type")),
        ownership_type=_to_int_or_none(request.GET.get("house_ownership")),
    )
    return JsonResponse(pins, safe=False)


# -------------------------------
# BUSINESS
# -------------------------------

@session_login_required
@role_required(CAPTAIN_ROLE)
@csrf_protect
@nocache
@inject
def business_list(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = BusinessFilters(request.GET or None)

    search = request.GET.get("search")
    b_category = _to_int_or_none(request.GET.get("b_category"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search= search,
        b_category= b_category,
        ownership_type= ownership_type,
        status= status,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_category is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(request, "business/business_list.html", {
        'page_path': f'{user_role} / Business Records',
        'page_title': 'Business Records',
        'form' : form,
        'page_obj' : page_obj,
        'filters' : {
            'search' : search,
            'b_category' : b_category,
            'ownership_type' :ownership_type,
            'status' : status,
        },
        'url_name' : 'captain:business_information',
        'search_url': 'captain:ajax_business_search',
        'is_clerk': (user_role == 'Barangay Clerk'),
    })

AJAX_BUSINESS_PARTIALS = {
    # key      -> template path
    "cards": "business/_businesses.html",         # your map list cards
    "rows":  "business/_business_list.html",      # table rows for list page
}

@session_login_required
@role_required(CAPTAIN_ROLE)
@require_GET
@inject
def ajax_business_search(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    # only allow XHR (optional, but nice)
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR required")
    
    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    template_name = AJAX_BUSINESS_PARTIALS.get(tpl_key)
    if not template_name:
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    b_category = request.GET.get("b_category")
    ownership_type = request.GET.get("ownership_type")
    status = request.GET.get("status")

    # def to_int_or_none(v):
    #     try:
    #         return int(v) if v not in (None, "",) else None
    #     except ValueError:
    #         return None

    rows = business_service.execute(
        search=q,
        b_category=_to_int_or_none(b_category),
        ownership_type=_to_int_or_none(ownership_type),
        status=_to_int_or_none(status),
    )[:50]

    base_ctx = {
        "url_name": "captain:business_information",
    }

    context = {**base_ctx, ("rows" if tpl_key == "rows" else "cards"): rows}
    html = render_to_string(template_name, context, request=request)
    return HttpResponse(html)

@session_login_required
@role_required(CAPTAIN_ROLE)
@nocache
@inject
def business_information(
    request, 
    b_id: int,
    business_info: IBusinessInfoService = Provide[
        AppContainer.owner_business_service]) -> HttpResponse:
    user_role = _auth_role_name(request)
    
    person_id = request.GET.get("owner")
    person_id = int(person_id) if person_id and str(person_id).isdigit() else None

    dto = (
        business_info.execute(person_id=person_id, business_id=b_id)
        if person_id is not None
        else business_info.execute_by_business_id(b_id)  # see helper below
    )

    def _compose_owner_full_name(data: dict) -> str | None:
        last   = (data.get("last_name") or "").strip()
        first  = (data.get("first_name") or "").strip()
        middle = (data.get("middle_name") or "").strip()
        suffix = (data.get("suffix") or "").strip()

        parts = []
        if last:
            parts.append(last.upper())                   # LAST
        if first:
            parts.append((", " if parts else "") + first.title())  # , First
        if middle:
            parts.append(" " + middle[:1].upper() + ".")           #  M.
        if suffix:
            parts.append(" " + suffix.upper())                     #  JR / III, etc.
        return "".join(parts) or None
    
    def _compose_full_address_from_owner(data: dict) -> str | None:
        street      = (data.get("street") or "").strip()
        sitio_purok = (data.get("sitio_purok") or "").strip()
        barangay    = (data.get("barangay") or "").strip()
        city        = (data.get("city") or "").strip()

        # Order strictly: STREET, PUROK/SITIO, BARANGAY, CITY
        parts = [p for p in [street, sitio_purok, barangay, city] if p]
        return ", ".join(parts) if parts else None

    owner = dict(dto.owner or {})
    owner["owner_full_name"] = _compose_owner_full_name(owner)
    owner["full_address"]    = _compose_full_address_from_owner(owner)

    operating_days = (dto.business.get("operating_days") or "").strip()  # e.g., "Mon, Tue, Wed"
    days = [d.strip() for d in operating_days.split(",")] if operating_days else []
    operating_days_start_name = days[0] if days else None
    operating_days_end_name = days[-1] if days else None

    formatted_id = f"{int(b_id):06d}"

    return render(
        request,
        "business/business_information.html",
        {
            "page_path": f"{user_role} / Business Records / Business Details : {formatted_id}",
            "page_title": f"Business Details : {formatted_id}",
            "owner": owner,
            "business": dto.business,
            "business_files": (dto.business_proof or {}).get("files") or [],
            "operating_days_start_name": operating_days_start_name,
            "operating_days_end_name": operating_days_end_name,
        },
    )

@session_login_required
@role_required(CAPTAIN_ROLE)
@csrf_protect
@nocache
@inject
def business_map_list(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = BusinessFilters(request.GET or None)

    search = request.GET.get("search")
    b_category = _to_int_or_none(request.GET.get("b_category"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search=search,
        b_category=b_category,
        ownership_type=ownership_type,
        status=status,
    )

    paginator = Paginator(rows, 5)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_category is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(
        request,
        "business/business_map_list.html",
        {
            'page_path': f"{user_role} / Business Map",
            'page_title': "Business Map",
            'form': form,
            'page_obj' : page_obj,
            'filters' : {
                'search' : search,
                'b_category' : b_category,
                'ownership_type' :ownership_type,
                'status' : status,
            },
            "pins_url": reverse("captain:api_business_pins"),
            'search_url': 'captain:ajax_business_search',
        }
    )

@session_login_required
@role_required(CAPTAIN_ROLE)
@csrf_protect
@nocache
@inject
def api_business_pins(
    request: HttpRequest,
    business_repo: IBusinessRepository = Provide[AppContainer.infra.business],
):
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    pins = business_repo.fetch_business_pins(
        search=(request.GET.get("search") or None),
        b_category=_to_int_or_none(request.GET.get("b_category")),
        ownership_type=_to_int_or_none(request.GET.get("ownership_type")),
        status=_to_int_or_none(request.GET.get("status")),
    )
    return JsonResponse(pins, safe=False)

