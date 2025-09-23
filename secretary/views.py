from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import SearchPerson
from .forms import ResidentProfileform
from .forms import ChooseRole

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Barangay Secretary'

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
    form = SearchPerson()
    role_form = ChooseRole()
    return render(request, "staff/staff_selection_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
        'role_form': role_form,
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