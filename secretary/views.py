from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import SearchBusinessOwner

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'clerk'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def staff_selection(request):
    return render(request, "staff/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

def staff_selection_resident(request):
    form = SearchBusinessOwner()
    return render(request, "staff/staff_selection_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })
