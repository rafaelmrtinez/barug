from django.urls import path
from . import views

app_name = 'clerk'

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("document_request/document_requests", views.doc_reqs, name="doc_reqs"),
    path("document_requested/details/<int:doc_id>/", views.doc_details, name="doc_dets"),
    path("identity_verification/", views.review_approve, name="identity_verification"),
    path("person_details/<str:per_id>/", views.person_submission_dets, name="person_details"),
    path("business/business_owner/", views.business_owner, name="business_owner"),
    path("business/business_owner_resident/", views.business_owner_resident, name="business_owner_resident"),
    path("business/business_details/", views.business_details, name="business_details"),
    path("business_list/", views.business_list, name="business_list"),
    path("business_information/<str:b_id>/", views.business_information, name="business_information"),
]