from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import SearchVerificationRequest
from .forms import SearchBusinessOwner
from .forms import BusinessDetails

user_fullname = 'lname fname mname suffix'
user_role = 'Clerk'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def review_approve(request):
    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    form = SearchVerificationRequest()

    return render(request, "resident/review_approve.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form' : form,
    })

def person_submission_dets(request, req_id):
    return render(request, "person/person_submission_dets.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Account Verification : {req_id}',
        'page_title' : f'Account Verification : {req_id}',
        'user_role_template' : user_role_template,
    })

def business_owner(request):
    return render(request, "business/business_owner.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })

def business_owner_resident(request):
    form = SearchBusinessOwner()
    return render(request, "business/business_owner_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })

def business_details(request):
    form = BusinessDetails()
    return render(request, "business/business_details.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form' : form,
    })