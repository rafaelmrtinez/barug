from django.urls import path
from maternal import views

app_name = 'maternal'

urlpatterns = [
    path('records/', views.records, name='maternal_records'),
    path('anc/<int:person_id>/<int:record_id>/', views.record_detail, name='maternal_record_detail'),
    path('maternal-health/<int:person_id>/', views.maternal_health_record_form, name='maternal_health_record_view'),
    # path("health-record-form/<int:maternal_id>/", views.maternal_health_record_form, name="maternal_health_record_form"),
    path("health-record-form/", views.maternal_health_record_form, name="maternal_health_record_form"),
]