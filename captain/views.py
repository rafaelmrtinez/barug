from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import (
    SearchPerson,
    ResidentProfileform,
    ChooseRole,
    StaffFilters,
    Schedule,
)

user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Captain'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def staff_selection(request):
    return render(request, "staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

def staff_selection_resident(request):
    form = SearchPerson()
    role_form = ChooseRole()
    sched_form = Schedule()
    return render(request, "staff_selection_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
        'role_form': role_form,
        'sched_form': sched_form
    })

def staff_selection_nonres(request):
    form = ResidentProfileform()
    return render(request, "staff_selection_nonresident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

def staff_selection_nonres_docs(request):
    form = ResidentProfileform()
    return render(request, "supporting_docs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

def staff_selection_nonres_role_review(request):
    role_form = ChooseRole()
    sched_form = Schedule()
    return render(request, "role.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'role_form': role_form,
        'sched_form': sched_form,
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