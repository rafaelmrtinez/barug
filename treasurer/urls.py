# treasurer/urls.py
from django.urls import path
from . import views

app_name = "treasurer"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path("requests/", views.queue, name="queue"),
    path("requests/<int:doc_request_id>/", views.detail, name="detail"),
    path("requests/<int:doc_request_id>/pay/", views.take_payment, name="take_payment"),
    path("fees/", views.fees, name="fees"),
    path("fees/update/", views.fee_update, name="fee_update"),
    path("fees/add/", views.fee_add, name="fee_add"),
    path("fees/<str:fee_code>/edit/", views.fee_edit, name="fee_edit"),

    # NEW: confirm + post OR for an already-paid request
    path("requests/<int:doc_request_id>/confirm-or/", views.confirm_post_or, name="confirm_post_or"),

    # NEW: mark a refund completed (manual finalize)
    path("requests/<int:doc_request_id>/refund/complete/", views.treasurer_complete_refund, name="treasurer_complete_refund"),

    # Business-only queue
    path("business/requests/", views.business_queue, name="business_queue"),
    path("business/renewal/", views.business_renewal, name="business_renewal"),
    path("business/renewal/<int:renewal_request_id>/", views.business_renewal_detail, name="business_renewal_detail"),

    # Business detail WITH request id
    path(
        "business/<int:business_id>/requests/<int:doc_request_id>/",
        views.business_detail,
        name="business_detail",
    ),

    # One-click: pay -> set flag -> mark for printing
    path(
        "business/<int:business_id>/requests/<int:doc_request_id>/pay/",
        views.business_pay_and_print,
        name="business_pay_and_print",
    ),

    path(
        "business/renewal/<int:renewal_request_id>/recalc/",
        views.business_renewal_recalc,
        name="business_renewal_recalc"
    ),

]
