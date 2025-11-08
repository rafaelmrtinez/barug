# lupon_pres/views.py
from django.shortcuts import render
from authentication.guards import session_login_required, role_required

# Import all view functions from lupon_mem.views
from lupon_mem.views import (
    form_builder,
    add_form_choose_static,
    form_builder_by_code,
    generate_settlement_summary,
    hearing_list,
    case_hearing_list,
    case_hearing_schedule,
    open_kp16_from_hearing,
    open_med_attendance_from_hearing,
    open_mediation_attendance,
    hearing_media_upload,
    mediation_photos_upload,
    mediation_complete,
    conciliation_complete,
    case_summary_pdf,
    mark_hearing_held_dev,
    case_summon_list,
    summon_attendance,
    summon_set_status,
    case_timeline,
    incident_heatmap
)

@session_login_required
@role_required("barangay lupon president")
def dashboard(request):
    """Dashboard for Barangay Lupon President"""
    auth = request.session.get("auth")
    return render(request, "lupon_pres/dashboard.html", {
        "page_path": "Barangay Lupon President/Dashboard",
        "page_title": "Dashboard",
        "auth": auth,
    })