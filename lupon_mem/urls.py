# lupon_mem/urls.py
from django.urls import path
from . import views
from lupon_mem.views_sql import (
    SubmissionViewSQL,
    SubmissionEditSQL,
    SubmissionUpdateSQL,
)
from lupon_mem.views_mobile import residents_search

app_name = "lupon_mem"

urlpatterns = [
    # existing
    path("submissions/<int:pk>/",      SubmissionViewSQL.as_view(),   name="kp_submission_view"),
    path("submissions/<int:pk>/edit/", SubmissionEditSQL.as_view(),   name="kp_submission_edit"),
    path("submissions/<int:pk>/save/", SubmissionUpdateSQL.as_view(), name="kp_submission_update"),

    path("cases/", views.case_list, name="case_list"),
    path("cases/new/", views.case_new, name="case_new"),
    path("cases/<int:case_id>/", views.case_detail, name="case_detail"),
    path("cases/<int:case_id>/settlement", views.case_settlement_update, name="case_settlement_update"),  # NEW
    path("cases/<int:case_id>/forms/add/", views.add_form_choose, name="add_form_choose"),
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_builder"),
    path("cases/<int:case_id>/submissions/<int:submission_id>/edit/", views.form_builder, name="form_edit"),
    path("cases/<int:case_id>/forms/choose/", views.add_form_choose_static, name="add_form_choose_static"),
    path("cases/<int:case_id>/forms/code/<slug:form_code>/build/", views.form_builder_by_code, name="form_builder_by_code"),

    # reports (existing)
    path("reports/", views.report_list, name="report_list"),
    path("reports/new/", views.report_new, name="report_new"),
    path("reports/<int:report_id>/confirm/", views.report_confirm, name="report_confirm"),

    # NEW: lupon approves report (sets UNPAID)
    path("reports/", views.report_list, name="report_list"),
    path("reports/<int:report_id>/review/", views.report_review, name="report_review"),
    path("reports/<int:report_id>/approve/", views.report_approve, name="report_approve"),
    path("reports/<int:report_id>/decline/", views.report_decline, name="report_decline"),
    path("reports/<int:report_id>/pay-open/", views.report_pay_and_open_case, name="report_pay_and_open_case"), # optional legacy
    # NEW: treasurer pays & opens case (GET form + POST submit)
    # path("reports/<int:report_id>/pay/", views.report_pay_and_open_case, name="report_pay"),
    # lupon_mem/urls.py
    # path("reports/<int:report_id>/pay/", views.report_pay_and_open_case, name="report_pay_and_open_case"),
    # apis
    path("api/submissions/<int:submission_id>/pdf/", views.submission_pdf, name="submission_pdf"),
    path("api/preview/", views.preview_image, name="preview_image"),
    path("api/save-answers/", views.save_answers, name="save_answers"),
    path("api/submit-form/", views.submit_form, name="submit_form"),
    path("api/staff-suggest/", views.staff_suggest, name="staff_suggest"),
    path("person_suggest/", views.person_suggest, name="person_suggest"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("cases/<int:case_id>/timeline/", views.case_timeline, name="case_timeline"),
    path("mobile/residents/search/", residents_search, name="residents_search"),
]
