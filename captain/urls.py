from django.urls import path
from . import views

app_name = 'captain'

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path("staff_list/", views.staff_list, name="staff_list"),
    path("staff_list/staff_details/<str:staff_id>/", views.staff_dets , name="staff_details"),

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
]