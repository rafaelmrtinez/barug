from django.urls import path
from . import views

app_name = "staff_admin"

urlpatterns = [
    path("staff_selection/", views.staff_selection, name="staff_selection"),
    path("staff_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
    path("staff_selection/staff_selection_non-resident_personal_info/", views.staff_selection_nonres, name="staff_selection_non-resident"),
    # path("staff_selection/staff_selection_non-resident_socio/", views.staff_selection_nonres_socio, name="staff_selection_non-resident_socio"),
    path("staff_selection/staff_selection_non-resident_supporting_docs/", views.staff_selection_nonres_docs , name="staff_selection_non-resident_docs"),
    path("staff_selection/staff_selection_non-resident_role_review/", views.staff_selection_nonres_role_review , name="staff_selection_non-resident_role_review"),
    path("staff_list/", views.staff_list , name="staff_list"),
    path("staff_list/staff_details/<str:staff_id>/", views.staff_dets , name="staff_details"),
]