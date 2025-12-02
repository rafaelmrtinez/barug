# FAMILY VIEWS TO ADD TO secretary/views.py
# Add these functions after api_household_pins function (around line 1797)
# Before the BUSINESS section

# -------------------------------
# FAMILY
# -------------------------------

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def family_list(
    request: HttpRequest,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Display list of all active families with filtering options.
    """
    user_role = _auth_role_name(request)
    form = FamilyFilters(request.GET or None)

    search = request.GET.get("search")
    household_type = _to_int_or_none(request.GET.get("household_type"))
    nhts_status = _to_int_or_none(request.GET.get("nhts_status"))
    indigent_status = _to_int_or_none(request.GET.get("indigent_status"))

    # Determine which repository method to call
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
        'search_url': 'secretary:ajax_family_search',
    })

@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@inject
def ajax_family_search(
    request: HttpRequest,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Returns partial HTML for live family search.
    """
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR only")

    q = request.GET.get("q")
    household_type = _to_int_or_none(request.GET.get("household_type"))
    nhts_status = _to_int_or_none(request.GET.get("nhts_status"))
    indigent_status = _to_int_or_none(request.GET.get("indigent_status"))

    # Determine which repository method to call
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

    rows = rows[:50]  # Limit results

    html = render_to_string(
        "family/_family_list.html",
        {"rows": rows},
        request=request,
    )
    return HttpResponse(html)

@session_login_required
@role_required(SECRETARY_ROLE)
@csrf_protect
@nocache
@inject
def family_detail(
    request: HttpRequest,
    family_id: int,
    household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
) -> HttpResponse:
    """
    Display detailed family information including all members.
    """
    user_role = _auth_role_name(request)
    
    family = household_repo.fetch_family_detail(family_id)
    
    if not family:
        messages.error(request, "Family not found.")
        return redirect("secretary:family_list")
    
    return render(request, "family/family_detail.html", {
        'page_path': f'{user_role} / Family / {family.get("family_num", "")}',
        'page_title': f'Family {family.get("family_num", "")}',
        'family': family,
    })
