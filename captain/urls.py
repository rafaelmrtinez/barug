from django.urls import path
from . import views

app_name = 'captain'

urlpatterns = [
    path("staff_list/", views.staff_list, name="staff_list"),
    path("staff_list/staff_details/<str:req_id>/", views.person_submission_dets, name="staff_details"),
]