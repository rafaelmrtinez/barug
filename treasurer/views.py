from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import RequestedDocsFilters

user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Treasurer'
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

def docs_requested(request):
    form = RequestedDocsFilters()
    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)


    return render(request, "docs_requested.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard' ,
        'user_role_template' : user_role_template,
        'form' : form,
        'page_obj' : page_obj,
    })

def doc_details(request, doc_id):
    return render(request, "doc_details.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Document Request / {doc_id}',
        'page_title' : 'Dashboard' ,
        'user_role_template' : user_role_template,
    })