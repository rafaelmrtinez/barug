from django.shortcuts import render
from .forms import ResidentProfileform

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Clerk'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def register_resident(request):
    return render(request, "resident_profiling/register_resident.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident',
        'page_title' : 'Register Resident',
        'user_role_template' : user_role_template,
    })

def personal_info(request):
    form = ResidentProfileform()

    return render(request, "resident_profiling/personal_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Personal Information',
        'page_title' : 'Personal Information',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def socioeconomic_info(request):
    form = ResidentProfileform()

    return render(request, "resident_profiling/socioeconomic_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Socioeconomic Information',
        'page_title' : 'Socioeconomic Information',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def supporting_documents(request):
    form = ResidentProfileform()

    return render(request, "resident_profiling/supporting_documents.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Supporting Documents',
        'page_title' : 'Supporting Documents',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def review_info(request):
    return render(request, "resident_profiling/review_information.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Supporting Documents',
        'page_title' : 'Supporting Documents',
        'user_role_template' : user_role_template,
    })

def resident_records(request):
    return render(request, 'resident_profiling/resident_records.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
    })

def resident_record(request, res_id):
    form = ResidentProfileform()

    for field in form.fields.values():
        field.disabled = True
        field.widget.attrs['class'] = 'form-control editable-field'

    return render(request, 'resident_profiling/resident_record.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records / Resident : {res_id}',
        'page_title' : f'Resident : {res_id}',
        'user_role_template' : user_role_template,
        'form' : form,
    })