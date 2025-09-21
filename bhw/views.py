from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import SearchActiveScheduleFilter
from .forms import StatusActiveScheduleFilter
from .forms import WeekRangeActiveScheduleFilter
from .forms import Reschedule


user_fullname = 'laname fname mname suffix'
user_role = 'Barangay Health Worker'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def active_schedule(request):
    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    search_form = SearchActiveScheduleFilter()
    status_form = StatusActiveScheduleFilter()
    week_range_form = WeekRangeActiveScheduleFilter()
    reschedule_form = Reschedule()

    return render(request, "household/quarterly/active_schedule.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : '',
        'page_title' : '',
        'user_role_template' : user_role_template,
        'search_form' : search_form,
        'status_form' : status_form,
        'week_range_form' : week_range_form,
        'reschedule_form' : reschedule_form,
        'page_obj': page_obj,
    })

def household_info(request):
    return render(request, "household/household_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Request Details',
        'page_title' : 'Request Details',
        'user_role_template' : user_role_template
    })