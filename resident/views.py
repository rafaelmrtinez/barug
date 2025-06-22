from django.shortcuts import render
from .forms import ResidentProfileform

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'User'

# Create your views here.
def profile_resident(request) :
    form = ResidentProfileform()

    return render(request, "resident_profiling/profile_resident.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident',
        'page_title' : 'Register Resident',
        'form' : form,
    })

def resident_records(request) :
    return render(request, 'resident_profiling/resident_records.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
    })

def resident_record(request, res_id) :
    form = ResidentProfileform()

    for field in form.fields.values():
        field.disabled = True
        field.widget.attrs['class'] = 'form-control editable-field'

    return render(request, 'resident_profiling/resident_record.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records / Resident : {res_id}',
        'page_title' : f'Resident : {res_id}',
        'res_id' : res_id,
        'form' : form,
    })