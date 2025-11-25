# bhw/urls.py
from django.urls import path
from . import views

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
]
