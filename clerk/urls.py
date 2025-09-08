from django.urls import path
from . import views

app_name = 'clerk'

urlpatterns = [
    path("review_approve/", views.review_approve, name="review_request"),
    path("person_details/<str:req_id>/", views.person_submission_dets, name="person_details"),
    path("business/business_details/", views.business_details, name="business_details"),
]