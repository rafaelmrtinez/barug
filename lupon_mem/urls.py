# lupon_mem/urls.py
from django.urls import path
from . import views
from lupon_mem.views_sql import (
    SubmissionViewSQL,
    SubmissionEditSQL,
    SubmissionUpdateSQL,   # <- exists now
)

app_name = "lupon_mem"

urlpatterns = [
    # NEW: fast View + “Edit” redirect
    path("submissions/<int:pk>/",      SubmissionViewSQL.as_view(),   name="kp_submission_view"),
    path("submissions/<int:pk>/edit/", SubmissionEditSQL.as_view(),   name="kp_submission_edit"),
    path("submissions/<int:pk>/save/", SubmissionUpdateSQL.as_view(), name="kp_submission_update"),

    # existing cases
    path("cases/", views.case_list, name="case_list"),
    path("cases/new/", views.case_new, name="case_new"),
    path("cases/<int:case_id>/", views.case_detail, name="case_detail"),

    # existing builder/edit routes (we reuse these!)
    path("cases/<int:case_id>/forms/add/", views.add_form_choose, name="add_form_choose"),
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_builder"),
    path("cases/<int:case_id>/submissions/<int:submission_id>/edit/", views.form_builder, name="form_edit"),

    # zero-DB choose + code builder
    path("cases/<int:case_id>/forms/choose/", views.add_form_choose_static, name="add_form_choose_static"),
    path("cases/<int:case_id>/forms/code/<slug:form_code>/build/", views.form_builder_by_code, name="form_builder_by_code"),

    # reports
    path("reports/", views.report_list, name="report_list"),
    path("reports/new/", views.report_new, name="report_new"),
    path("reports/<int:report_id>/confirm/", views.report_confirm, name="report_confirm"),

    # apis (unchanged)
    path("api/submissions/<int:submission_id>/pdf/", views.submission_pdf, name="submission_pdf"),
    path("api/preview/", views.preview_image, name="preview_image"),
    path("api/save-answers/", views.save_answers, name="save_answers"),
    path("api/submit-form/", views.submit_form, name="submit_form"),
    path("api/staff-suggest/", views.staff_suggest, name="staff_suggest"),

    # dashboard + timeline
    path("dashboard/", views.dashboard, name="dashboard"),
    path("cases/<int:case_id>/timeline/", views.case_timeline, name="case_timeline"),
]
