from django.urls import path
from . import views
from doc_ingest.api.faq_ingest_api import FAQIngestAPI

app_name = 'captain'

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path("staff_selection/", views.staff_selection, name="staff_selection"),
    path("staff_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
    path("staff_selection/staff_selection_non-resident_personal_info/", views.staff_selection_nonres, name="staff_selection_non-resident"),
    # path("staff_selection/staff_selection_non-resident_socio/", views.staff_selection_nonres_socio, name="staff_selection_non-resident_socio"),
    path("staff_selection/staff_selection_non-resident_supporting_docs/", views.staff_selection_nonres_docs , name="staff_selection_non-resident_docs"),
    path("api/resident-suggest/", views.resident_suggest, name="resident_suggest"),
    path("staff_selection/staff_selection_non-resident_role_review/", views.staff_selection_nonres_role_review , name="staff_selection_non-resident_role_review"),
    path("staff_list/", views.staff_list, name="staff_list"),
    path("staff_list/staff_details/<str:staff_code>/", views.staff_dets , name="staff_details"),

    path("api/staff/search/", views.staff_search_api, name="staff_search_api"),
    path("api/staff/filter/", views.staff_filter_api, name="staff_filter_api"),

    path("staff_account_requests_list/", views.staff_account_requests_list, name="staff_account_requests_list"),
    path("staff_account_requests_list/pending_staff_details/<str:p_staff_acc_req_id>/", views.pending_staff_dets , name="pending_staff_details"),

    # RESIDENT
    path("resident/resident_list/", views.resident_list , name="resident_list"),
    path("resident/resident_map/", views.resident_map_list , name="resident_map"),

    # HOUSEHOLD 
    path("household/household_list/", views.household_list , name="household_list"),
    path("household/household_map/", views.household_map_list , name="household_map"),
    path("ajax/household_search/", views.ajax_household_search ,name="ajax_household_search"),
    path("api/household/pins", views.api_household_pins, name="api_household_pins"),

    # BUSINESS
    path("business/business_list/", views.business_list , name="business_list"),
    path("business_information/<int:b_id>/", views.business_information, name="business_information"),
    path("business/business_map/", views.business_map_list , name="business_map"),
    path("ajax/business_search/", views.ajax_business_search, name="ajax_business_search"),
    path("api/business/pins", views.api_business_pins, name="api_business_pins"),

    path("staff-requests/process/", views.process_staff_request, name="process_staff_request"),
    # FAQ upload endpoint used by captain UI (multipart or JSON)
    path("api/upload_faqs/", FAQIngestAPI.as_view(), name="upload_faqs"),
]