from django.urls import path
from . import views
from common.api.financial_pdf_api import FinancialPDFAPI

app_name = "treasurer"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/api", views.dashboard_api, name="dashboard_api"),

    path("requests/", views.queue, name="queue"),
    path("requests/<int:doc_request_id>/", views.detail, name="detail"),
    path("requests/<int:doc_request_id>/pay/", views.take_payment, name="take_payment"),

    # FEES
    path("fees/", views.fees, name="fees"),
    path("fees/update/", views.fee_update, name="fee_update"),

    # NEW split add pages
    path("fees/add/existing/", views.fee_add_existing, name="fee_add_existing"),
    path("fees/add/new/", views.fee_add_new, name="fee_add_new"),

    # (Optional) keep legacy combined add route if still used anywhere
    path("fees/add/", views.fee_add, name="fee_add"),
    # NEW: Level-1 and Level-2s
    path("fees/types/", views.fees_index, name="fees_index"),
    path("fees/types/<int:doc_type_id>/", views.fees_by_type, name="fees_by_type"),
    path("fees/<str:fee_code>/edit/", views.fee_edit, name="fee_edit"),

    # FINANCIAL REPORT
    path("financial-report/", views.financial_report, name="financial_report"),
    path("financial-report/search/", views.financial_report, name="financial_report_search"),
    
    # PDF API
    path("api/financial/pdf/", FinancialPDFAPI.as_view(), name="financial_pdf_api"),

    # REFUND
    path("refunds/", views.payment_refunds, name="payment_refunds"),
    path("requests/<int:doc_request_id>/confirm-or/", views.confirm_post_or, name="confirm_post_or"),
    path("requests/<int:doc_request_id>/refund/complete/", views.treasurer_complete_refund, name="treasurer_complete_refund"),

    # Business-only queue
    path("business/requests/", views.business_queue, name="business_queue"),
    path("business/renewal/", views.business_renewal, name="business_renewal"),
    path("business/renewal/<int:renewal_request_id>/", views.business_renewal_detail, name="business_renewal_detail"),
    path("business/renewal/group/<int:business_id>/", views.business_renewal_group, name="business_renewal_group"),
    path("business/<int:business_id>/requests/<int:doc_request_id>/", views.business_detail, name="business_detail"),
    path("business/<int:business_id>/requests/<int:doc_request_id>/pay/", views.business_pay_and_print, name="business_pay_and_print"),
    path("business/renewal/<int:renewal_request_id>/recalc/", views.business_renewal_recalc, name="business_renewal_recalc"),
    path("business/renewal/<int:renewal_request_id>/pay/", views.business_renewal_take_payment, name="business_renewal_take_payment"),
    path("treasurer/business/<int:business_id>/renewal/pay-all/", views.business_renewal_take_payment_all, name="business_renewal_take_payment_all"),
    path("closure/", views.closure_list, name="closure_list"),
    path("closure/<int:closure_payment_request_id>/", views.closure_detail, name="closure_detail"),
    path("closure/<int:business_id>/group/", views.closure_group, name="closure_group"),
    path("closure/<int:closure_payment_request_id>/take-payment/", views.closure_take_payment, name="closure_take_payment"),
    path("closure/<int:business_id>/take-payment-all/", views.closure_take_payment_all, name="closure_take_payment_all"),
]
