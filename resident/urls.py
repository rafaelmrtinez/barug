from django.urls import path
from . import views, api

app_name = 'resident'

urlpatterns = [
    path("doc-requests/", views.docreq_history, name="docreq_history"),
    path("doc-requests/<int:doc_request_id>/", views.docreq_detail, name="docreq_detail"),

    path("register/", views.register_resident, name="register_resident"),
    path("register/personal_information/", views.personal_info , name="personal_info"),
    path("register/socioeconomic_information/", views.socioeconomic_info, name="socioeconomic_info"),
    path("register/supporting_documents/", views.supporting_documents, name="supporting_documents"),
    path("register_resident/review_information/", views.review_info, name="review_info"),
    path("resident_records/", views.resident_records, name="resident_records"),
    path("register_household/household_information/", views.household_info, name="household_info"),
    path("register_household/family_information/<int:household_id>/", views.family_info, name="family_info"),
    path("<str:res_id>/", views.resident_record, name="resident_record"),
    path("house/membership/<int:family_id>/", views.house_membership, name="house_membership"),
    
    # API CALLS
    path("api/search/", api.ResidentSearchAPI.as_view(), name="person_search_api"),
    path("api/household/create/", api.HouseholdCreateAPI.as_view(), name="household_create_api"),
    path("api/register/family_unit/", api.FamilyMembershipAPI.as_view(), name="family_membership"),
    path("api/register/household_members/", api.HouseholdMembershipAPI.as_view(), name="household_membership_api"),
]