from django.urls import path
from child_health import views

app_name = 'child_health'

urlpatterns = [
    path('health-entry/<int:child_health_record_id>/', views.child_health_entry, name='child_health_entry'),
    path('records/', views.child_record_list_view, name='child_record_list'),
    path('create_child_health_record/', views.create_child_health_record, name='create_child_health_record'),
    path('ajax/find-person/', views.find_person_http, name='ajax_find_person'),
    path('ajax/child-basic-info/<int:person_id>/', views.fetch_person_basic_details_http, name='ajax_child_basic_info'),
    path('ajax/person-basic/<int:person_id>/', views.fetch_person_and_house_basic_details_http, name='ajax_person_basic_info'),
    path("child-immunization/request/", views.child_immunization_http, name="child_immunization_request"),
]