from django.urls import path
from . import views

app_name = 'event_logs'

urlpatterns = [
    path("activity_log/", views.activity_log, name="activity_log"),
    path("authentication_log/", views.authentication_log, name="authentication_log"),
]