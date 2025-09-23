# REMOVE this: from email import message
from django.shortcuts import render
from django.contrib import messages
from django.views.decorators.http import require_GET
from django.http import JsonResponse

from secretary.models import Secretary

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
    # defaults
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