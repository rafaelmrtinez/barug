from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import SearchVerificationRequest
from .forms import SearchBusinessOwner
from .forms import BusinessDetails
from .forms import BusinessFilters
from .forms import RequestedDocsFilters

user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Clerk'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def dashboard(request):
    return render(request, "dashboard.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard' ,
        'user_role_template' : user_role_template,
    })

def doc_reqs(request):
    form = RequestedDocsFilters()

    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "doc_req/doc_reqs.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard' ,
        'user_role_template' : user_role_template,
        'form' : form,
        'page_obj': page_obj,
    })

def doc_details(request, doc_id):
    return render(request, "doc_req/doc_details.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Document Request / {doc_id}',
        'page_title' : 'Dashboard' ,
        'user_role_template' : user_role_template,
    })

def review_approve(request):
    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    form = SearchVerificationRequest()

    return render(request, "resident/identity_verification_list.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Identity Verification',
        'page_title': 'Identity Verification',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form' : form,
    })

def person_submission_dets(request, per_id):
    return render(request, "person/person_submission_dets.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Identity Verification : {per_id}',
        'page_title' : f'Identity Verification : {per_id}',
        'user_role_template' : user_role_template,
    })

def business_owner(request):
    return render(request, "business/business_owner.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business Records / Add Business / Business Owner',
        'page_title': 'Business Owner',
        'user_role_template': user_role_template,
    })

def business_owner_resident(request):
    form = SearchBusinessOwner()
    return render(request, "business/business_owner_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business Records / Add Business / Business Owner Information',
        'page_title': 'Business Owner Information',
        'user_role_template': user_role_template,
        'form' : form,
    })

def business_details(request):
    form = BusinessDetails()
    return render(request, "business/business_details.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business Records / Add Business / Business Information',
        'page_title': 'Business Information',
        'user_role_template': user_role_template,
        'form' : form,
    })

def business_list(request):
    form = BusinessFilters()
    return render(request, "business/business_list.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business Records',
        'page_title': 'Business Records',
        'user_role_template': user_role_template,
        'form' : form,
    })

def business_information(request, b_id):
    return render(request, "business/business_information.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Business Records / Business Details : {b_id}',
        'page_title': f'Business Details : {b_id}',
        'user_role_template': user_role_template,
    })