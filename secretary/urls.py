# secretary/urls.py
from django.urls import path
from . import views
from common.api.residents_pdf_api import ResidentsPDFAPI
from common.api.business_pdf_api import BusinessPDFAPI
from common.api.household_pdf_api import HouseholdPDFAPI
from common.api.family_pdf_api import FamilyPDFAPI

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

    # Residents
    path("residents/", views.residents_list, name="residents_list"),
    path("residents/<int:person_id>/", views.resident_detail, name="resident_detail"),

    # Resident (legacy paths kept if still used elsewhere)
    path("resident/resident_list/", views.resident_list, name="resident_list"),
    path("resident/resident_map/", views.resident_map_list, name="resident_map"),
    path("ajax/resident_search/", views.ajax_resident_search, name="ajax_resident_search"),

    # Household
    path("household/household_list/", views.household_list, name="household_list"),
    path("household/<int:household_id>/", views.household_detail, name="household_detail"),
    path("household/household_map/", views.household_map_list, name="household_map"),
    path("ajax/household_search/", views.ajax_household_search, name="ajax_household_search"),
    path("api/household/pins", views.api_household_pins, name="api_household_pins"),

    # Family
    path('families/', views.family_list, name='family_list'),
    path('api/families/search/', views.ajax_family_search, name='ajax_family_search'),
    path('families/<int:family_id>/', views.family_detail, name='family_detail'),

    # Business
    path("business/business_list/", views.business_list, name="business_list"),
    path("business_information/<int:b_id>/", views.business_information, name="business_information"),
    path("business/business_map/", views.business_map_list, name="business_map"),
    path("ajax/business_search/", views.ajax_business_search, name="ajax_business_search"),
    path("api/business/pins", views.api_business_pins, name="api_business_pins"),

    # APIs: staff
    path("api/staff/search/", views.staff_search_api, name="staff_search_api"),
    # path("api/staff/filter/", views.staff_filter_api, name="staff_filter_api"),

    # INCIDENT HEATMAP
    path("incident-heatmap/", views.incident_heatmap, name="incident_heatmap"),

    # ANNOUNCEMENT
    path("announcement/create_draft/", views.announcement_draft, name="announcement_draft"),
    path("announcement/draft_list/", views.announcement_draft_list, name="announcement_draft_list"),
    path("announcement/draft_view/<int:announcement_id>/", views.announcement_draft_view, name="announcement_draft_view"),
    path("announcement/view/<int:announcement_id>/", views.announcement_view, name="announcement_view"),
    path("announcement/draft_edit/<int:announcement_id>/", views.announcement_draft_edit, name="announcement_draft_edit"),
    path("announcement/audience_scope/", views.announcement_audience_scope, name="announcement_audience_scope"),
    path("ajax/save_audience_rules/", views.save_audience_rules, name="save_audience_rules"),
    path("ajax/remove_audience/", views.remove_audience, name="remove_audience"),
    path("ajax/announcement_draft_search/", views.ajax_announcement_draft_search, name="ajax_announcement_draft_search"),
    path("ajax/delete_announcement_draft/", views.ajax_delete_announcement_draft, name="ajax_delete_announcement_draft"),
    
    # SCHEDULED ANNOUNCEMENTS
    path("announcement/scheduled_list/", views.announcement_scheduled_list, name="announcement_scheduled_list"),
    path("ajax/announcement_scheduled_search/", views.ajax_announcement_scheduled_search, name="ajax_announcement_scheduled_search"),
    path("ajax/cancel_scheduled_announcement/", views.ajax_cancel_scheduled_announcement, name="ajax_cancel_scheduled_announcement"),
    
    # PUBLISHED ANNOUNCEMENTS
    path("announcement/published_list/", views.announcement_published_list, name="announcement_published_list"),
    path("ajax/announcement_published_search/", views.ajax_announcement_published_search, name="ajax_announcement_published_search"),
    
    # EXPIRED ANNOUNCEMENTS
    path("announcement/expired_list/", views.announcement_expired_list, name="announcement_expired_list"),
    path("ajax/announcement_expired_search/", views.ajax_announcement_expired_search, name="ajax_announcement_expired_search"),
    
    # CANCELLED ANNOUNCEMENTS
    path("announcement/cancelled_list/", views.announcement_cancelled_list, name="announcement_cancelled_list"),
    path("ajax/announcement_cancelled_search/", views.ajax_announcement_cancelled_search, name="ajax_announcement_cancelled_search"),
    
    # CHANNEL MANAGEMENT
    path("ajax/upsert_announcement_channels/", views.upsert_announcement_channels, name="upsert_announcement_channels"),
    path('api/announcement_channels/<int:announcement_id>/', views.announcement_channels_api, name='announcement_channels_api'),
    path('ajax/publish_announcement_now/', views.publish_announcement_now, name='publish_announcement_now'),
    path('ajax/schedule_announcement/', views.schedule_announcement, name='schedule_announcement'),
    
    # PDF APIs
    path("api/residents/pdf/", ResidentsPDFAPI.as_view(), name="residents_pdf_api"),
    path("api/business/pdf/", BusinessPDFAPI.as_view(), name="business_pdf_api"),
    path("api/household/pdf/", HouseholdPDFAPI.as_view(), name="household_pdf_api"),
    path("api/family/pdf/", FamilyPDFAPI.as_view(), name="family_pdf_api"),
]
