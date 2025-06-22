from django.urls import path
from . import views

app_name = 'resident'

urlpatterns = [
    path("profile_resident/", views.profile_resident , name="profile_resident"),
]