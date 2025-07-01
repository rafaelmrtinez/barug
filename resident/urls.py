from django.urls import path
from . import views

app_name = 'resident'

urlpatterns = [
    path("register_resident/", views.register_resident, name="register_resident"),
    path("register_resident/personal_information/", views.personal_info , name="personal_info"),
    path("register_resident/socioeconomic_information/", views.socioeconomic_info, name="socioeconomic_info"),
    path("register_resident/supporting_documents/", views.supporting_documents, name="supporting_documents"),
    path("register_resident/review_information/", views.review_info, name="review_info"),
    path("resident_records/", views.resident_records, name="resident_records"),
    path("register_household/household_information/", views.household_info, name="household_info"),
    path("register_household/family_information/", views.family_info, name="family_info"),
    path("<str:res_id>/", views.resident_record, name="resident_record"),
]