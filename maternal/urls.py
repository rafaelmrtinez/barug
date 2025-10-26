from django.urls import path
from maternal import views

app_name = 'maternal'

urlpatterns = [
    path('records/', views.records, name='maternal_records'),
    path('record/<int:person_id>/', views.record_detail, name='maternal_record_detail'),
    path("anc/form/<int:record_id>/", views.maternal_health_record_form, name="maternal_health_record_form"),
    path("anc/form/<int:record_id>/lab/save/", views.laboratory_save_api, name="maternal_lab_save_api"),
    path("create/", views.create_new_maternal_entry, name="create_maternal_entry"),
    path("find-mother-basic-info/<int:person_id>/", views.find_mother_basic_info, name="find_mother_basic_info"),
]