from django.urls import path
from . import views

app_name = 'bhw'

urlpatterns=[
    path("active_schedule/", views.active_schedule, name="active_schedule"),
    path("active_schedule/household_info/<int:household_id>/", views.household_info, name="active_sched_household_info"),
    path("ocr/verify/", views.verify_valid_id_view, name="ocr_verify"),
]