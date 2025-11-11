from django.urls import path
from child_health import views
from child_health.api.child_report_api import ChildReportAPI
from child_health.api.child_health_schedule_api import ChildHealthScheduleAPI

app_name = 'child_health'

urlpatterns = [
    path('health-entry/<int:child_health_record_id>/', views.child_health_entry, name='child_health_entry'),
    path('records/', views.child_record_list_view, name='child_record_list'),
    path('create_child_health_record/', views.create_child_health_record, name='create_child_health_record'),
    path('ajax/find-person/', views.find_person_http, name='ajax_find_person'),
    path('ajax/child-basic-info/<int:person_id>/', views.fetch_person_basic_details_http, name='ajax_child_basic_info'),
    path('ajax/person-basic/<int:person_id>/', views.fetch_person_and_house_basic_details_http, name='ajax_person_basic_info'),
    path("child-immunization/request/", views.child_immunization_http, name="child_immunization_request"),
    # API: child report PDF
    path('api/v1/chr/report/', ChildReportAPI.as_view(), name='child_report_api'),
    # API: child visit schedule create
    path('api/v1/chr/schedule/', ChildHealthScheduleAPI.as_view(), name='child_schedule_api'),
]