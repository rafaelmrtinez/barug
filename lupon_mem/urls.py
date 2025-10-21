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
    # submissions (existing)
    path("submissions/<int:pk>/",      SubmissionViewSQL.as_view(),   name="kp_submission_view"),
    path("submissions/<int:pk>/edit/", SubmissionEditSQL.as_view(),   name="kp_submission_edit"),
    path("submissions/<int:pk>/save/", SubmissionUpdateSQL.as_view(), name="kp_submission_update"),

    # cases
    path("cases/", views.case_list, name="case_list"),
    path("cases/new/", views.case_new, name="case_new"),
    path("cases/<int:case_id>/", views.case_detail, name="case_detail"),
    path("cases/<int:case_id>/settlement", views.case_settlement_update, name="case_settlement_update"),

    # chooser + builder
    path("cases/<int:case_id>/forms/add/", views.add_form_choose, name="add_form_choose"),
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_builder"),
    # alias so templates can use 'form_build'
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_build"),
    path("cases/<int:case_id>/submissions/<int:submission_id>/edit/", views.form_builder, name="form_edit"),
    path("cases/<int:case_id>/forms/choose/", views.add_form_choose_static, name="add_form_choose_static"),
    path("cases/<int:case_id>/forms/code/<slug:form_code>/build/", views.form_builder_by_code, name="form_builder_by_code"),
    path("cases/<int:case_id>/generate-summary/", views.generate_settlement_summary,
        name="generate_settlement_summary"),

    # hearings & mediation
    path("cases/hearings/", views.hearing_list, name="hearing_list"),  # global listing (kept)
    path("cases/<int:case_id>/hearings/", views.case_hearing_list, name="case_hearing_list"),  # NEW per-case list
    path("cases/<int:case_id>/hearing/", views.case_hearing_schedule, name="case_hearing_schedule"),
        # KP-16 opener used when outcome is settled
    path(
        "cases/<int:case_id>/hearing/kp16/",
        views.open_kp16_from_hearing,
        name="open_kp16_from_hearing",
    ),
    path(
        "cases/<int:case_id>/hearing/med-attendance/open/",
        views.open_med_attendance_from_hearing,
        name="open_med_attendance_from_hearing",
    ),

    path(
        "cases/<int:case_id>/hearing/open-med-att/",
        views.open_mediation_attendance,
        name="open_mediation_attendance",
    ),
    path('case/<int:case_id>/hearing/media/upload/',
         views.hearing_media_upload,
         name='hearing_media_upload'),

    path("case/<int:case_id>/mediation/<int:submission_id>/photos/upload/",
         views.mediation_photos_upload, name="mediation_photos_upload"),
    path("cases/<int:case_id>/mediation/complete/",    views.mediation_complete,    name="mediation_complete"),
    path("cases/<int:case_id>/conciliation/complete/", views.conciliation_complete, name="conciliation_complete"),
    path("cases/<int:case_id>/summary/pdf/", views.case_summary_pdf, name="case_summary_pdf"),
    path("cases/<int:case_id>/hearings/mark-held-dev/",
         views.mark_hearing_held_dev, name="mark_hearing_held_dev"),

    # summons
    path("cases/<int:case_id>/summons/", views.case_summon_list, name="case_summon_list"),  # NEW per-case list
    path("cases/<int:case_id>/summon/attend/", views.summon_attendance, name="summon_attendance"),
    path("cases/summons/<int:submission_id>/set-status/", views.summon_set_status, name="summon_set_status"),

    # timeline
    path("cases/<int:case_id>/timeline/", views.case_timeline, name="case_timeline"),

    # reports
    path("reports/", views.report_list, name="report_list"),
    path("reports/new/", views.report_new, name="report_new"),
    path("reports/<int:report_id>/confirm/",  views.report_confirm, name="report_confirm"),
    path("reports/<int:report_id>/review/",   views.report_review,  name="report_review"),
    path("reports/<int:report_id>/approve/",  views.report_approve, name="report_approve"),
    path("reports/<int:report_id>/decline/",  views.report_decline, name="report_decline"),
    path("reports/<int:report_id>/pay-open/", views.report_pay_and_open_case, name="report_pay_and_open_case"),

    # apis
    path("api/submissions/<int:submission_id>/pdf/", views.submission_pdf, name="submission_pdf"),
    path("api/preview/", views.preview_image, name="preview_image"),
    path("api/save-answers/", views.save_answers, name="save_answers"),
    path("api/submit-form/", views.submit_form, name="submit_form"),
    path("api/staff-suggest/", views.staff_suggest, name="staff_suggest"),
    path("api/staff-suggest-all/", views.staff_suggest_all, name="staff_suggest_all"),
    path("resident-lookup/", views.resident_lookup, name="resident_lookup"),
    path("resident/quick-search/", views.resident_quick_search, name="resident_quick_search"),
    path("person/lookup/", views.person_lookup, name="person_lookup"),
    path("person_suggest/", views.person_suggest, name="person_suggest"),
    path("staff/lookup", views.staff_lookup, name="staff_lookup"),
    # misc
    path("dashboard/", views.dashboard, name="dashboard"),
    path("mobile/residents/search/", residents_search, name="residents_search"),
]
