from django.shortcuts import render
from .forms import ResidentProfileform

# Create your views here.
def profile_resident(request) :
    user_role = 'User' #need back-end for proper way
    form = ResidentProfileform(request.POST or None)

    return render(request, "resident_profiling/profile_resident.html", {
        'page_path' : f'{user_role} / Resident Management / Register Resident',
        'page_title' : 'Register Resident',
        'form' : form,
    })