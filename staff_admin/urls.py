from django.urls import path
from . import views

app_name = "staff_admin"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("staff_selection/", views.staff_selection, name="staff_selection"),
    path("staff_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
    path("staff_selection/staff_selection_non-resident_personal_info/", views.staff_selection_nonres, name="staff_selection_non-resident"),
    # path("staff_selection/staff_selection_non-resident_socio/", views.staff_selection_nonres_socio, name="staff_selection_non-resident_socio"),
    path("staff_selection/staff_selection_non-resident_supporting_docs/", views.staff_selection_nonres_docs , name="staff_selection_non-resident_docs"),
    path("staff_selection/staff_selection_non-resident_role_review/", views.staff_selection_nonres_role_review , name="staff_selection_non-resident_role_review"),
    path("staff_list/", views.staff_list , name="staff_list"),
    path("staff_list/staff_details/<str:staff_code>/", views.staff_dets , name="staff_details"),

    path("staff_account_requests_list/", views.staff_account_requests_list, name="staff_account_requests_list"),
    path("staff_account_requests_list/pending_staff_details/<str:p_staff_acc_req_id>/", views.pending_staff_dets , name="pending_staff_details"),

    path("staff-requests/process/", views.process_staff_request, name="process_staff_request"),

    path("api/staff/search/", views.staff_search_api, name="staff_search_api"),
    path("api/staff/filter/", views.staff_filter_api, name="staff_filter_api"),
]