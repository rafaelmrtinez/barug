from django.urls import path
from . import views

app_name = 'clerk'

urlpatterns = [
    path("review_approve/", views.review_approve, name="review_request"),
    path("person_details/<str:req_id>/", views.person_submission_dets, name="person_details"),

    # actions
    path("account-verification/<int:req_id>/approve/", views.approve_request, name="approve_request"),
    path("account-verification/<int:req_id>/decision/", views.decision_request, name="decision_request"),
]