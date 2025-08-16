from django.urls import path
from . import views

app_name = 'bhw'

urlpatterns = [
    path("requests/", views.requests, name="requetsts"),
    path("request_details/", views.request_details, name='request_details'),
]