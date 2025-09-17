from django.urls import path
from . import views

app_name = "secretary"

urlpatterns = [
    path("staff_selection/", views.staff_selection, name="staff_selection"),
    path("staff_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
]