from django.shortcuts import render
from django.core.paginator import Paginator

user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Captain'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def staff_list(request):
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
    })

def person_submission_dets(request, req_id):
    return render(request, "person/person_submission_dets.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Staff Details : {req_id}',
        'page_title' : f'Staff Details : {req_id}',
        'user_role_template' : user_role_template,
    })