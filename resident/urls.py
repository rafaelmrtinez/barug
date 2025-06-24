from django.urls import path
from . import views

app_name = 'resident'

urlpatterns = [
    path("register_resident", views.register_resident, name="register_resident"),
    path("register_resident/personal_info", views.personal_info , name="personal_info"),
    path("register_resident/socioeconomic_info/", views.socioeconomic_info, name="socioeconomic_info"),
    path("register_resident/supporting_documents", views.supporting_documents, name="supporting_documents"),
    path("resident_records/", views.resident_records, name="resident_records"),
    path("<str:res_id>/", views.resident_record, name="resident_record"),
]