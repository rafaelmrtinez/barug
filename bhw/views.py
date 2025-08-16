from django.shortcuts import render
from django.core.paginator import Paginator

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
    return render(request, "household_profiling/request_details.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Request Details',
        'page_title' : 'Request Details',
        'user_role_template' : user_role_template
    })