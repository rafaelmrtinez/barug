from django.urls import path
from . import views

app_name = 'bhw'

urlpatterns=[
    path("active_schedule/", views.active_schedule, name="active_schedule"),
    path("active_schedule/household_info", views.household_info, name="active_sched_householf_info"),
]