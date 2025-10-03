from django.urls import path
from . import views as pay_views

app_name = "payments"

urlpatterns = [
    path("api/renewals/<int:renewal_id>/start",   pay_views.start_checkout,         name="start_checkout"),
    path("api/renewals/<int:renewal_id>/status",  pay_views.renewal_status,         name="renewal_status"),
    path("api/renewals/<int:renewal_id>/confirm", pay_views.confirm_after_redirect,  name="confirm_after_redirect"),
    path("api/renewals/<int:renewal_id>/decline", pay_views.decline_and_refund,     name="decline_and_refund"),
    path("webhook/paymongo",                      pay_views.paymongo_webhook,       name="paymongo_webhook"),
    path("success",                               pay_views.success_page,           name="success_page"),
    # ✅ NEW: DOC REQUESTS
    path("api/docs/<int:doc_id>/start",           pay_views.start_doc_checkout,      name="start_doc_checkout"),
    path("api/docs/<int:doc_id>/status",          pay_views.doc_status,              name="doc_status"),
path("api/docs/<int:doc_id>/confirm",             pay_views.confirm_doc_after_redirect,name="confirm_doc_after_redirect"),
]
