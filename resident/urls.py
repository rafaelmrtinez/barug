from django.urls import path
from . import views

app_name = 'resident'

urlpatterns = [
    path("register_resident/", views.profile_resident , name="register_resident"),
    path("resident_records/", views.resident_records, name="resident_records"),
    path("<str:res_id>/", views.resident_record, name="resident_record"),
]