from django.urls import path
from . import views

app_name = "treasurer"

urlpatterns = [
    path("requests/", views.queue, name="queue"),
    path("requests/<int:doc_request_id>/", views.detail, name="detail"),
    path("requests/<int:doc_request_id>/pay/", views.take_payment, name="take_payment"),
    path("fees/", views.fees, name="fees"),
    path("fees/update/", views.fee_update, name="fee_update"),
    path("fees/add/", views.fee_add, name="fee_add"),
    path("fees/<str:fee_code>/edit/", views.fee_edit, name="fee_edit"),

    # Business-only queue
    path("business/requests/", views.business_queue, name="business_queue"),

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
]
