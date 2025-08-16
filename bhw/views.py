from django.shortcuts import render
from django.core.paginator import Paginator
from datetime import date

#need back-end for proper assignment
user_fullname = 'laname fname mname suffix'
user_role = 'BHW'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def requests(request):
    return render(request, "household_profiling/requests.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Requests',
        'page_title' : 'Requests',
        'user_role_template' : user_role_template
    })

def request_details(request):
    details = {
        "household_name": "Bellosillo Household",
        "date_submitted": date(2025, 8, 14),
        "address": "Purok 3, Sitio San Roque",
        "household_head": "Bellosillo, Raphael H.",
        "household_num": "HH-000123",
        "house_type": "Concrete",
        "house_ownership": "Owned",
        "families": [
            {
                "family_num": "FM-002345",
                "head_name": "Bellosillo, Raphael H.",
                "members": ["Bellosillo, Raphael H.", "Maria Lourdes A. Cruz"]
            },
            {
                "family_num": "FM-002812",
                "head_name": "De la Peña, Marivic",
                "members": ["De la Peña, Marivic", "De la Peña, Rommel", "De la Peña, Kaye"]
            }
        ]
    }
    ctx = {
    'user_fullname': user_fullname,
    'user_role': user_role,
    'page_path': f'{user_role} / Request Details',
    'page_title': 'Request Details',
    'user_role_template': user_role_template,
    **details,  # flattens details into the context
}
    return render(request, "household_profiling/request_details.html", ctx
    )