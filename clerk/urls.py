from django.urls import path
from . import views

app_name = 'clerk'

urlpatterns = [

    # newly added

    path("requests/", views.queue, name="queue"),
    path("requests/<int:doc_request_id>/", views.detail, name="detail"),
    path("requests/<int:doc_request_id>/mark-printing/", views.mark_for_printing, name="mark_printing"),
    path("requests/<int:doc_request_id>/mark-released/", views.mark_released, name="mark_released"),
    path("requests/<int:doc_request_id>/decline/", views.decline, name="decline"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("identity_verification/", views.review_approve, name="identity_verification"),
    # path("person_details/<str:req_id>/", views.person_submission_dets, name="person_details"),

    # actions
    path("account-verification/<int:req_id>/approve/", views.approve_request, name="approve_request"),
    path("account-verification/<int:req_id>/decision/", views.decision_request, name="decision_request"),

    # business
    path("business/business_owner/", views.business_owner, name="business_owner"),
    path("business/business_owner_resident/", views.business_owner_resident, name="business_owner_resident"),
    path("business/business_details/", views.business_details, name="business_details"),
    path("business_list/", views.business_list, name="business_list"),
    path("business_information/<str:b_id>/", views.business_information, name="business_information"),
]