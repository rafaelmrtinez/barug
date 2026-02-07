# lupon_mem/urls.py
from django.urls import path
from . import views
from lupon_mem import views_reports
from . import views_api
from . import views_cases
from . import views_progress  # ← ADDED: import for flow progress API
from . import views_hearing_api
from . import views_hearings
from . import views_resident_records
from .views_case_state import update_case_state
from . import views_profiling
from . import views_residents
from . import views_blotter_pdf

from lupon_mem.views_sql import (
    SubmissionViewSQL,
    SubmissionEditSQL,
    SubmissionUpdateSQL,
)
from lupon_mem.views_mobile import residents_search
from lupon_mem.views_delete_submission import delete_submission

app_name = "lupon_mem"

urlpatterns = [
    # submissions (existing)
    path("submissions/<int:pk>/",      SubmissionViewSQL.as_view(),   name="kp_submission_view"),
    path("submissions/<int:pk>/edit/", SubmissionEditSQL.as_view(),   name="kp_submission_edit"),
    path("submissions/<int:pk>/save/", SubmissionUpdateSQL.as_view(), name="kp_submission_update"),
    path("submissions/<int:submission_id>/delete/", delete_submission, name="kp_submission_delete"),

    # cases
    path("cases/", views_cases.case_list, name="case_list"),
    path("cases/new/", views_cases.case_new, name="case_new"),
    path("cases/<int:case_id>/", views_cases.case_detail, name="case_detail"),
    path("cases/<int:case_id>/settlement", views_cases.case_settlement_update, name="case_settlement_update"),
    path("cases/<int:case_id>/update-settlement/", views_cases.case_settlement_update, name="update_settlement_status"),
    path("cases/<int:case_id>/close",  views_cases.case_close,  name="case_close"),
    path("cases/<int:case_id>/reopen", views_cases.case_reopen, name="case_reopen"),
    path("cases/<int:case_id>/update-case-state/", update_case_state, name="update_case_state"),

    # chooser + builder
    path("cases/<int:case_id>/forms/add/", views_cases.add_form_choose, name="add_form_choose"),
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_builder"),
    # alias so templates can use 'form_build'
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_build"),
    path("cases/<int:case_id>/submissions/<int:submission_id>/edit/", views.form_builder, name="form_builder"),
    path("cases/<int:case_id>/forms/choose/", views.add_form_choose_static, name="add_form_choose_static"),
    path("cases/<int:case_id>/forms/code/<slug:form_code>/build/", views.form_builder_by_code, name="form_builder_by_code"),
    path("cases/<int:case_id>/generate-summary/", views.generate_settlement_summary,
        name="generate_settlement_summary"),

    # hearings & mediation
    path("cases/hearings/", views.hearing_list, name="hearing_list"),  # global listing (kept)
    path("cases/<int:case_id>/hearings/", views.case_hearing_list, name="case_hearing_list"),  # NEW per-case list
    path("cases/<int:case_id>/hearing/", views.case_hearing_schedule, name="case_hearing_schedule"),
    path("cases/<int:case_id>/hearing/<int:sid>/", views.case_hearing_schedule, name="case_hearing"),
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
    path('case/<int:case_id>/hearing/media/delete/',
         views.hearing_media_delete,
         name='hearing_media_delete'),
    path('cases/<int:case_id>/hearing/documentation-pdf/',
         views.hearing_documentation_pdf,
         name='hearing_documentation_pdf'),
    path('cases/<int:case_id>/hearing/reschedule/',
         views_hearings.reschedule_hearing,
         name='reschedule_hearing'),

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
    path("reports/", views_reports.report_list, name="report_list"), # added to views_reports
    path("reports/new/", views_reports.report_new, name="report_new"),  # added to views_reports
    path("reports/<int:report_id>/confirm/",  views_reports.report_confirm, name="report_confirm"), # added to views_reports
    path("reports/<int:report_id>/review/",   views_reports.report_review,  name="report_review"), # added to views_reports
    path("reports/<int:report_id>/approve/",  views_reports.report_approve, name="report_approve"), # added to views_reports
    path("reports/<int:report_id>/decline/",  views_reports.report_decline, name="report_decline"), # added to views_reports
    path("reports/<int:report_id>/delete/",  views_reports.report_delete, name="report_delete"),
    path("reports/<int:report_id>/mark-paid/", views_reports.report_mark_paid, name="report_mark_paid"),
    path("reports/<int:report_id>/update-respondents/", views_reports.report_update_respondents, name="report_update_respondents"), # added to views_reports 
    path("reports/<int:report_id>/pay-open/", views_reports.report_pay_and_open_case, name="report_pay_and_open_case"), # added to views_reports
    path("reports/<int:report_id>/payment-details/", views_reports.report_payment_details, name="report_payment_details"), # added to views_reports
    path("reports/<int:report_id>/blotter-pdf/", views_blotter_pdf.generate_blotter_pdf, name="generate_blotter_pdf"),
    path("store-session-values/", views_reports.store_session_values, name="store_session_values"),
    
    # blotter reports
    path("blotter-reports/", views_reports.blotter_reports_menu, name="blotter_reports_menu"),
    path("blotter-reports/total_cases_by_status/", views_reports.total_cases_by_status_report, name="total_cases_by_status_report"),
    path("blotter-reports/case_summaries/", views_reports.case_summaries_report, name="case_summaries_report"),
    path("blotter-reports/settlement_statistics/", views_reports.settlement_statistics_report, name="settlement_statistics_report"),
    path("blotter-reports/monthly_activity/", views_reports.monthly_activity_report, name="monthly_activity_report"),
    path("blotter-reports/blotter_reports_summary/", views_reports.blotter_reports_summary, name="blotter_reports_summary"),
    path("blotter-reports/incident_by_location/", views_reports.incident_by_location_report, name="incident_by_location_report"),
    
    # case-specific PDF reports
    path("cases/<int:case_id>/timeline-pdf/", views_reports.case_timeline_pdf, name="case_timeline_pdf"),
    path("cases/<int:case_id>/forms-pdf/", views_reports.case_forms_pdf, name="case_forms_pdf"),
    path("cases/<int:case_id>/hearings-pdf/", views_reports.case_hearings_pdf, name="case_hearings_pdf"),

    # ===== ADDED: flow progress API (namespaced) =====
    path("api/case/<int:case_id>/flow-progress", views_progress.flow_progress_api, name="flow_progress_api"),
    path("api/hearing-status/<int:case_id>/", views_hearing_api.hearing_status_api, name="hearing_status_api"),
    path("api/kp16-date/<int:case_id>/", views_api.kp16_date_api, name="kp16_date_api"),
    path("api/case-kp7-details/<int:case_id>/", views_api.kp7_details_api, name="kp7_details_api"),
    path("api/upcoming-hearings/<int:case_id>/", views_api.upcoming_hearings_api, name="upcoming_hearings_api"),

    # apis
    path("api/mediation-hearings/<int:case_id>/", views_cases.mediation_hearings_api, name="mediation_hearings_api"),
    path("api/submissions/<int:submission_id>/pdf/", views_api.submission_pdf, name="submission_pdf"),
    path("api/preview/", views_api.preview_image, name="preview_image"),
    path("api/save-answers/", views_api.save_answers, name="save_answers"),
    path("api/submit-form/", views_api.submit_form, name="submit_form"),
    path("api/staff-suggest/", views_api.staff_suggest, name="staff_suggest"),
    path("api/staff-suggest-all/", views_api.staff_suggest_all, name="staff_suggest_all"),
    path("resident-lookup/", views_api.resident_lookup, name="resident_lookup"),
    path("resident/quick-search/", views_api.resident_quick_search, name="resident_quick_search"),
    path("person/lookup/", views_api.person_lookup, name="person_lookup"),
    path("person_suggest/", views_api.person_suggest, name="person_suggest"),
    path("staff/lookup", views_api.staff_lookup, name="staff_lookup"),
    # resident records
    path("residents/", views_resident_records.resident_records_list, name="resident_records_list"),
    path("residents/<int:person_id>/", views_resident_records.resident_records_detail, name="resident_records_detail"),
    path("residents/<int:person_id>/update-photo/", views_resident_records.update_resident_photo, name="update_resident_photo"),
    path("api/residents/search/", views_resident_records.resident_records_api, name="resident_records_api"),
    
    # resident list (all residents)
    path("resident-list/", views_residents.resident_list, name="resident_list"),
    path("resident-list/<int:person_id>/delete/", views_residents.resident_delete, name="resident_delete"),
    
    # resident profiling
    path("profiling/personal-info/", views_profiling.profile_personal_info, name="profile_personal_info"),
    path("profiling/socioeconomic/", views_profiling.profile_socioeconomic, name="profile_socioeconomic"),
    path("profiling/review/", views_profiling.profile_review, name="profile_review"),

    # misc
    path("dashboard/", views.dashboard, name="dashboard"),
    path("incident-heatmap/", views.incident_heatmap, name="incident_heatmap"),
    path("mobile/residents/search/", residents_search, name="residents_search"),
    
]
