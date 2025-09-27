from django.urls import path
from . import views

app_name = 'bhw'

urlpatterns = [
    # existing
    path("active_schedule/", views.active_schedule, name="active_schedule"),
    path("active_schedule/household_info", views.household_info, name="active_sched_householf_info"),
    path("ocr/verify/", views.verify_valid_id_view, name="ocr_verify"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # NEW
    path("maternal/new/", views.maternal_new, name="maternal_new"),
    
    # NEW – Records UI
    path("records/", views.records, name="records"),
    path("record/<str:kind>/<int:record_id>/", views.record_detail, name="record_detail"),
    path("record/<int:record_id>/anc/add/", views.add_anc_visit, name="add_anc_visit"),
    path("record/<int:record_id>/child/visit/add/", views.add_child_visit, name="add_child_visit"),
    path("record/<int:record_id>/vaccine/add/", views.add_vaccine, name="add_vaccine"),
]
