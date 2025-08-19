from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from .forms import SearchVerificationRequest
from common.decorators import staff_login_required

user_fullname = 'lname fname mname suffix'
user_role = 'Clerk'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.

@staff_login_required
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
    return render(request, "resident/person_submission_dets.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Account Verification : {req_id}',
        'page_title' : f'Account Verification : {req_id}',
        'user_role_template' : user_role_template,
    })
