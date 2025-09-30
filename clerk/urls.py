from django.urls import path
# from . import views
from . views import business as b
from . views import doc_req as dr

app_name = 'clerk'

urlpatterns = [
    # document requests
    path("requests/", dr.queue, name="queue"),
    path("requests/<int:doc_request_id>/", dr.detail, name="detail"),
    path("requests/<int:doc_request_id>/mark-printing/", dr.mark_for_printing, name="mark_printing"),
    path("requests/<int:doc_request_id>/mark-ready-for-pickup/", dr.mark_request_ready_for_pickup, name="mark_ready_for_pickup"),
    path("requests/<int:doc_request_id>/mark-released/", dr.mark_released, name="mark_released"),
    path("requests/<int:doc_request_id>/decline/", dr.decline, name="decline"),
    
    path("walkin/", dr.walkin_new, name="walkin_new"),
    path("walkin/create/", dr.walkin_create, name="walkin_create"),

    # Search Helpers
    path("ajax/resident-search/", dr.ajax_resident_search, name="ajax_resident_search"),
    path("ajax/purpose-options/", dr.ajax_purpose_options, name="ajax_purpose_options"),

    # identity verification
    path("dashboard/", dr.dashboard, name="dashboard"),
    path("identity_verification/", dr.review_approve, name="identity_verification"),
    path("person_details/<int:req_id>/", dr.person_submission_dets, name="person_details"),

    # actions
    path("account-verification/<int:req_id>/approve/", dr.approve_request, name="approve_request"),
    path("account-verification/<int:req_id>/decision/", dr.decision_request, name="decision_request"),

    # BUSINESS
    path("business/business_owner/", b.business_owner, name="business_owner"),
    path("business/business_owner_resident/", b.business_owner_resident, name="business_owner_resident"),
     path("business/business_owner_non-resident/", b.business_owner_nonresident, name="business_owner_nonres"),
    path("business/business_details/", b.business_details, name="business_details"),
    path("business_list/", b.business_list, name="business_list"),
    path("business_information/<int:b_id>/", b.business_information, name="business_information"),
]
