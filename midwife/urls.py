# midwife/urls.py
from django.urls import path
from . import views

app_name = "midwife"

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
    path("maternal/new/", views.maternal_new, name="maternal_new"),
    path("child/new/", views.child_new, name="child_new"),
    
    path("child-visit/", views.child_visit_http, name="child_visit"),
    path("child-basic-info/<int:q>/", views.child_basic_info_http, name="child_basic_info"),
]
