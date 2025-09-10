from django.urls import path
from . import views

app_name = 'clerk'

urlpatterns = [
    path("review_approve/", views.review_approve, name="review_request"),
    path("person_details/<str:req_id>/", views.person_submission_dets, name="person_details"),
    path("business/business_owner/", views.business_owner, name="business_owner"),
    path("business/business_owner_resident/", views.business_owner_resident, name="business_owner_resident"),
    path("business/business_details/", views.business_details, name="business_details"),
    path("business_list/", views.business_list, name="business_list"),
    path("business_information/", views.business_information, name="business_information"),
]