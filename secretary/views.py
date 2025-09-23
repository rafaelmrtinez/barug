# REMOVE this: from email import message
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.views.decorators.http import require_GET, require_POST
from django.http import JsonResponse

from secretary.models import Secretary
from .forms import ResidentProfileform

user_fullname = 'lname, fname mname suffix'
user_role = 'Barangay Secretary'
user_role_template = user_role.lower().replace(' ', '_')

def staff_selection(request):
    return render(request, "staff/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

@require_GET
def resident_suggest(request):
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    try:
        rows = Secretary.search_resident(q) or []
        out = []
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
        return JsonResponse({"results": [], "error": str(e)}, status=500)
    

    

def staff_selection_resident(request):
    # ── Branch: handle "Continue" (second form posts pid) ───────────────
    pid = (request.POST.get('pid') or '').strip()
    auth = request.session.get("auth") or {}
    staff_id = 6
    if request.method == "POST" and pid:
        if not staff_id:
            messages.error(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

        try:
            req_id = Secretary.insert_staff_account_request(
                p_requested_by_id=6,
                p_person_id=int(pid),
                p_role_id=8,  # <- your chosen role
                # ignored when p_person_id is provided
                # p_first_name=None,
                # p_last_name=None,
                # p_middle_name=None,
                # p_suffix=None,
                # p_birthdate=None,
                # p_email=None,
                # p_mobile_num=None,
                # p_sex_id=None,
                # p_civil_status_id=None,
                # p_nationality_id=None,
                # p_religion_id=None,
                # p_city=None,
                # p_barangay=None,
                # p_sitio_purok=None,
                # p_street=None,
                # p_valid_id_front=None,
                # p_valid_id_back=None,
                # p_valid_id_type_id=None,
                # p_selfie_path=None,
                # p_supporting_docs=None,
            )
            messages.success(request, f"Staff account request created. Ref: #{req_id}")
            # PRG pattern to avoid resubmits
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            messages.error(request, f"Failed to create staff account request: {e}")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

    # ── Your original search/detail logic (unchanged) ───────────────────
    residents = []
    res_details = None

    res_search = (request.POST.get('residentSearch') or '').strip()
    res_id = (request.POST.get('person_id') or '').strip()

    try:
        if res_search:
            residents = Secretary.search_resident(res_search) or []

        if res_id:
            rows = Secretary.get_resident_details(int(res_id)) or []
            res_details = rows[0] if rows else None   # pass a single dict to the template
    except Exception as e:
        messages.error(request, f"Error loading resident: {e}")

    return render(request, "staff/staff_selection_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'residents': residents,
        'res_details': res_details,
        'staff_id': staff_id,
    })



def staff_selection_nonres(request):
    form = ResidentProfileform()
    return render(request, "person/personal_info.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
        'redirect' : 'secretary:staff_selection_non-resident_docs',
    })


# def staff_selection_nonres_socio(request):
#     form = ResidentProfileform()
#     return render(request, "person/socioeconomic_info.html", {
#         'user_fullname': user_fullname,
#         'user_role': user_role,
#         'page_path': f'{user_role} / Account Verification',
#         'page_title': 'Account Verification',
#         'user_role_template': user_role_template,
#         'form' : form,
#         'redirect' : 'secretary:staff_selection_non-resident_docs',
#     })

def staff_selection_nonres_docs(request):
    form = ResidentProfileform()
    return render(request, "staff/supporting_docs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })