from django.urls import path
from . import views

app_name = "secretayr"

urlpatterns = [
    path("staff_selection/", views.staff_selection, name="staff_selection"),
    path("staff_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
    path("staff_selection/staff_selection_non-resident/", views.staff_selection_nonres, name="staff_selection_non-resident"),
]