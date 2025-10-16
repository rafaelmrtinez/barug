from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import StaffFilters

user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Captain'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def dashboard(request):
    return render(request, "dashboard.html", {
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

def household_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "household/household_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Household List',
        'page_title': 'Household List',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

def household_map_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "household/household_map_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Household Map',
        'page_title': 'Household Map',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

# -------------------------------
# BUSINESS
# -------------------------------

def business_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "business/business_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business List',
        'page_title': 'Business List',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

def business_map_list(request):
    form = StaffFilters()
    list = []
    paginator = Paginator(list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "business/business_map_list.html", {
        'user_fullname' : user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business Map',
        'page_title': 'Business Map',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })

