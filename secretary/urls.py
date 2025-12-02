# secretary/urls.py
from django.urls import path
from . import views
from common.api.residents_pdf_api import ResidentsPDFAPI
from common.api.business_pdf_api import BusinessPDFAPI
from common.api.household_pdf_api import HouseholdPDFAPI

app_name = "secretary"

urlpatterns = [
    # Dashboard
    path("dashboard/", views.dashboard, name="dashboard"),

    # Staff selection (resident / non-resident)
    path("staff_selection/", views.staff_selection, name="staff_selection"),
    path("staff_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
    path("staff_selection/staff_selection_non-resident_personal_info/", views.staff_selection_nonres, name="staff_selection_non-resident"),
    path("staff_selection/staff_selection_non-resident_supporting_docs/", views.staff_selection_nonres_docs, name="staff_selection_non-resident_docs"),
    path("staff_selection/staff_selection_non-resident_role_review/", views.staff_selection_nonres_role_review, name="staff_selection_non-resident_role_review"),
    path("api/resident-suggest/", views.resident_suggest, name="resident_suggest"),

    # Staff list & details
    path("staff_list/", views.staff_list, name="staff_list"),
    path("staff_list/staff_details/<str:staff_code>/", views.staff_dets, name="staff_details"),
    
    # Staff account requests
    path("staff_account_requests_list/", views.staff_account_requests_list, name="staff_account_requests_list"),
    path("staff_account_requests_list/pending_staff_details/<str:p_staff_acc_req_id>/", views.pending_staff_dets, name="pending_staff_details"),
    
    # Staff requests list and details
    path("staff/requests/", views.staff_requests_list, name="staff_requests_list"),
    path("staff/requests/<int:request_id>/", views.staff_request_detail, name="staff_request_detail"),

    # Residents
    path("residents/", views.residents_list, name="residents_list"),
    path("residents/<int:person_id>/", views.resident_profile, name="resident_profile"),

    # Resident (legacy paths kept if still used elsewhere)
    path("resident/resident_list/", views.resident_list, name="resident_list"),
    path("resident/resident_map/", views.resident_map_list, name="resident_map"),
    path("ajax/resident_search/", views.ajax_resident_search, name="ajax_resident_search"),

    # Household
    path("household/household_list/", views.household_list, name="household_list"),
    path("household/household_map/", views.household_map_list, name="household_map"),
    path("ajax/household_search/", views.ajax_household_search, name="ajax_household_search"),
    path("api/household/pins", views.api_household_pins, name="api_household_pins"),

    # Business
    path("business/business_list/", views.business_list, name="business_list"),
    path("business_information/<int:b_id>/", views.business_information, name="business_information"),
    path("business/business_map/", views.business_map_list, name="business_map"),
    path("ajax/business_search/", views.ajax_business_search, name="ajax_business_search"),
    path("api/business/pins", views.api_business_pins, name="api_business_pins"),

    # APIs: staff
    path("api/staff/search/", views.staff_search_api, name="staff_search_api"),
    path("api/staff_account_requests/search/", views.staff_account_requests_search_api, name="staff_account_requests_search_api"),
    
    # Staff request processing
    path("staff-requests/process/", views.process_staff_request, name="process_staff_request"),

    # BLOTTER CASES (VIEW ONLY)
    path("blotter-cases/", views.blotter_cases, name="blotter_cases"),
    
    # INCIDENT HEATMAP
    path("incident-heatmap/", views.incident_heatmap, name="incident_heatmap"),

    # ANNOUNCEMENT
    path("announcement/create_draft/", views.announcement_draft, name="announcement_draft"),
    path("announcement/draft_list/", views.announcement_draft_list, name="announcement_draft_list"),
    path("announcement/draft_view/<int:announcement_id>/", views.announcement_draft_view, name="announcement_draft_view"),
    path("announcement/audience_scope/", views.announcement_audience_scope, name="announcement_audience_scope"),
    path("ajax/save_audience_rules/", views.save_audience_rules, name="save_audience_rules"),
    path("ajax/announcement_draft_search/", views.ajax_announcement_draft_search, name="ajax_announcement_draft_search"),
    
    # CHANNEL MANAGEMENT
    path("ajax/upsert_announcement_channels/", views.upsert_announcement_channels, name="upsert_announcement_channels"),
    path('api/announcement_channels/<int:announcement_id>/', views.announcement_channels_api, name='announcement_channels_api'),
    path('ajax/publish_announcement_now/', views.publish_announcement_now, name='publish_announcement_now'),
    path('ajax/schedule_announcement/', views.schedule_announcement, name='schedule_announcement'),
    
    # PDF APIs
    path("api/residents/pdf/", ResidentsPDFAPI.as_view(), name="residents_pdf_api"),
    path("api/business/pdf/", BusinessPDFAPI.as_view(), name="business_pdf_api"),
    path("api/household/pdf/", HouseholdPDFAPI.as_view(), name="household_pdf_api"),
]
