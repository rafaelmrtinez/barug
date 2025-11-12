from django.urls import path
from . import views
from . import web_views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'clerk'

urlpatterns = [
    # document requests
    path("requests/", views.queue, name="queue"),

    path("requests/<int:doc_request_id>/", views.detail, name="detail"),

    # ✅ FIXED: confirm should call views.confirm_request (not detail)
    path("requests/<int:doc_request_id>/confirm/", views.confirm_request, name="confirm_request"),
    path("requests/<int:doc_request_id>/confirm-forward-treasurer/", views.confirm_forward_treasurer, name="confirm_forward_treasurer"),

    path("requests/<int:doc_request_id>/mark-printing/", views.mark_for_printing, name="mark_printing"),
    path("requests/<int:doc_request_id>/mark-ready-for-pickup/", views.mark_request_ready_for_pickup, name="mark_ready_for_pickup"),
    path("requests/<int:doc_request_id>/mark-released/", views.mark_released, name="mark_released"),
    path("requests/<int:doc_request_id>/decline/", views.decline, name="decline"),

    path("walkin/", views.walkin_new, name="walkin_new"),
    path("walkin/create/", views.walkin_create, name="walkin_create"),

    # Search Helpers
    path("ajax/owner-businesses/", views.ajax_owner_businesses, name="ajax_owner_businesses"),
    path("ajax/resident-search/", views.ajax_resident_search, name="ajax_resident_search"),
    path("ajax/purpose-options/", views.ajax_purpose_options, name="ajax_purpose_options"),

    # identity verification
    path("dashboard/", views.dashboard, name="dashboard"),
    path("identity_verification/", views.review_approve, name="identity_verification"),
    path("person_details/<int:req_id>/", views.person_submission_dets, name="person_details"),
    path("decision_request/", views.decision_request, name="decision_request"),
    
    # Actions
    path("account-verification/<int:req_id>/approve/", views.approve_request, name="approve_request"),
    path("account-verification/<int:req_id>/decision/", views.decision_request, name="decision_request"),

    # BUSINESS
    path("business/business_owner/", views.business_owner, name="business_owner"),
    path("business/business_owner_resident/", views.business_owner_resident, name="business_owner_resident"),
    path("business/business_owner_non-resident/", views.business_owner_nonresident, name="business_owner_nonres"),
    path("business/business_details/", views.business_details, name="business_details"),
    path("business/business_information_review/", views.business_information_review, name="business_information_review"),
    path("business/business_list/", views.business_list, name="business_list"),
    path("business/business_information/<int:b_id>/", views.business_information, name="business_information"),
    path("business/business_map/", views.business_map_list, name="business_map_list"),
    path("business/business_renewal/", views.renewal_list, name="renewal_list"),
    path("business/create_renewal_request/<int:b_id>/", views.create_renewal_request, name="create_renewal_request"),
    path("business/renewal_request/", views.renewal_request, name="renewal_request"),
    path("business/initiate_business_closure/<int:b_id>/", views.initiate_business_closure, name="initiate_business_closure"),
    path("business/<int:b_id>/closure/payment/", views.create_closure_payment_request, name="create_closure_payment_request"),

    # OCR
    path('upload-id/', web_views.upload_valid_id_files, name='upload_id_files'),
    path("valid-id/upload/", web_views.upload_valid_id_files, name="valid_id_upload"),
    path("valid-id/test/", web_views.upload_valid_id_test_page, name="valid_id_test"),

    path("ajax/business_search/", views.ajax_business_search, name="ajax_business_search"),
    path("ajax/business_renewal_search/", views.ajax_business_search, name="ajax_renewal_search"),
    path("ajax/resident_owner_search/", views.ajax_owner_search, name="ajax_owner_search"),
    path("ajax/nonresident_owner_search/", views.ajax_nonresident_owner_search, name="ajax_nonresident_owner_search"),
    path("api/business/pins", views.api_business_pins, name="api_business_pins"),
]