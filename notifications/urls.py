# notification/urls.py
from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
  path('api/push/register', views.register_push_device),
  path('api/push/test', views.send_test_push),           # optional for testing
  path('api/notifications/clear', views.clear_notifications),  # optional
  path('api/notifications/list', views.list_notifications),    # optional
]
