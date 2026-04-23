from django.urls import path
from . import views

app_name = 'metrics'

urlpatterns = [
    path('health-check/', views.HealthCheckView.as_view(), name='health_check'),
]