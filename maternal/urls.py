from django.urls import path
from maternal import views

app_name = 'maternal'

API_VERSION = 1

urlpatterns = [
    path('records/', views.records, name='maternal_records'),
    path('record/<int:person_id>/', views.record_detail, name='maternal_record_detail'),
    path("anc/form/<int:record_id>/", views.maternal_health_record_form, name="maternal_health_record_form"),
    path("anc/form/<int:record_id>/lab/save/", views.laboratory_save_api, name="maternal_lab_save_api"),
    path("create/", views.create_new_maternal_entry, name="create_maternal_entry"),
    path("find-mother-basic-info/<int:person_id>/", views.find_mother_basic_info, name="find_mother_basic_info"),
    path("form/prenatal/<int:mhr_id>/", views.health_worker_prenatal_form_view, name="bhw_prenatal_form"),
    path("api/form/prenatal/", views.prenatal_api, name="bhw_prenatal_api"),
    path("api/form/postpartum/bhw/", __import__('maternal.api.postpartum_bhw_api', fromlist=['']).PostpartumVisitBHWAPI.as_view(), name='postpartum_bhw_api'),
    path("api/form/postpartum/midwife/", __import__('maternal.api.postpartum_midwife_api', fromlist=['']).PostpartumFollowupMidwifeAPI.as_view(), name='postpartum_midwife_api'),
    # v1 API to update maternal health record status
    path(f'api/v{API_VERSION}/mhr/status/update/', __import__('maternal.api.maternal_heal_status_api', fromlist=['']).MaternalHealthRecordStatusUpdateAPI.as_view(), name='mhr_status_update_api'),
    # v1 API to complete a maternal visit schedule
    path(f'api/v{API_VERSION}/mhr/visit/complete/', __import__('maternal.api.complete_maternal_visit_api', fromlist=['']).CompleteMaternalVisitAPI.as_view(), name='mhr_visit_complete_api'),
    # v1 API to insert prenatal and postpartum schedules
    path(f'api/v{API_VERSION}/mhr/schedule/prenatal/', __import__('maternal.api.insert_prenatal_schedule_api', fromlist=['']).PrenatalScheduleAPI.as_view(), name='mhr_schedule_prenatal_api'),
    path(f'api/v{API_VERSION}/mhr/schedule/postpartum/', __import__('maternal.api.insert_postpartum_schedule_api', fromlist=['']).PostpartumScheduleAPI.as_view(), name='mhr_schedule_postpartum_api'),
    path(f'api/v{API_VERSION}/mhr/postpartum-record/', __import__('maternal.api.insert_postpartum_record_api', fromlist=['']).PostpartumRecordAPI.as_view(), name='mhr_postpartum_record_api'),
    path(f'api/v{API_VERSION}/mhr/side-panel/', __import__('maternal.api.mhr_side_panel_api', fromlist=['']).MhrSidePanelAPI.as_view(), name='mhr_side_panel_api'),
    path(f'api/v{API_VERSION}/mhr/lab-images/zip/', __import__('maternal.api.download_image_download_api', fromlist=['']).DownloadImageDownload.as_view(), name='mhr_lab_images_zip_api'),
    path(f'api/v{API_VERSION}/mhr/report/', __import__('maternal.api.maternal_report_api', fromlist=['']).MaternalReportAPI.as_view(), name='mhr_report_api'),
]