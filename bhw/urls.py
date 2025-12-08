# bhw/urls.py
from django.urls import path
from . import views
from common.api.household_history_pdf_api import HouseholdHistoryPDFAPI
from common.api.family_history_pdf_api import FamilyHistoryPDFAPI
from common.api.household_pdf_api import HouseholdPDFAPI
from common.api.residents_pdf_api import ResidentsPDFAPI
from common.api.family_pdf_api import FamilyPDFAPI

app_name = "bhw"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("records/", views.records, name="records"),
    path("records/<str:kind>/<int:record_id>/", views.record_detail, name="record_detail"),
    path("records/<int:record_id>/add-anc/", views.add_anc_visit, name="add_anc_visit"),
    path("records/<int:record_id>/add-child-visit/", views.add_child_visit, name="add_child_visit"),
    path("records/<int:record_id>/add-vaccine/", views.add_vaccine, name="add_vaccine"),

    path("ajax/resident-search/", views.ajax_resident_search, name="ajax_resident_search"),
    path("ajax/person-card/", views.ajax_person_card, name="ajax_person_card"),
    path("ajax/person-details/", views.ajax_person_details, name="ajax_person_details"),  # NEW
    
    path("verify-id/", views.verify_valid_id_view, name="verify_valid_id"),

    
    # BHW
    path("maternal/new/", views.maternal_new, name="maternal_new"),

    path("child/new/", views.child_new, name="child_new"),
    path("add-child/", views.add_child, name="add_child"),

    # HOUSEHOLD MAP
    path("household/household_map/", views.household_map_list, name="household_map"),
    path("ajax/household_search/", views.ajax_household_search, name="ajax_household_search"),
    path("api/household/pins", views.api_household_pins, name="api_household_pins"),

    # RESIDENT LIST
    path("resident/resident_list/", views.resident_list, name="resident_list"),
    path("resident/<int:person_id>/", views.resident_detail, name="resident_detail"),
    path("ajax/resident_search/", views.ajax_resident_search, name="ajax_resident_search"),

    # HOUSEHOLD LIST
    path("household/household_list/", views.household_list, name="household_list"),
    path("household/<int:household_id>/", views.household_detail, name="household_detail"),

    # FAMILY
    path('families/', views.family_list, name='family_list'),
    path('api/families/search/', views.ajax_family_search, name='ajax_family_search'),
    path('families/<int:family_id>/', views.family_detail, name='family_detail'),

    # HOUSEHOLD HISTORY
    path("household/history/", views.household_history_list, name="household_history_list"),
    path("household/history/<int:household_history_id>/", views.household_history_detail, name="household_history_detail"),
    path("family/history/<int:family_id>/", views.family_history_detail, name="family_history_detail"),
    
    # FAMILY HISTORY
    path("family/history/", views.family_history_list, name="family_history_list"),
    
    # PDF APIs
    path("api/household/history/pdf/", HouseholdHistoryPDFAPI.as_view(), name="household_history_pdf_api"),
    path("api/family/history/pdf/", FamilyHistoryPDFAPI.as_view(), name="family_history_pdf_api"),
    path("api/household/pdf/", HouseholdPDFAPI.as_view(), name="household_pdf_api"),
    path("api/family/pdf/", FamilyPDFAPI.as_view(), name="family_pdf_api"),
    path("api/residents/pdf/", ResidentsPDFAPI.as_view(), name="residents_pdf_api"),
    
    # RESIDENT PROFILING
    path("profiling/personal-info/", views.profile_personal_info, name="profile_personal_info"),
    path("profiling/link-parent/", views.profile_link_parent, name="profile_link_parent"),
    path("profiling/link-children/", views.profile_link_children, name="profile_link_children"),
    path("profiling/socioeconomic/", views.profile_socioeconomic, name="profile_socioeconomic"),
    path("profiling/review/", views.profile_review, name="profile_review"),
]
