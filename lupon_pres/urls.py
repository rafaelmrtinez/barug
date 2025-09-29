from django.urls import path
from . import views

app_name = "lupon_pres"

urlpatterns = [
    path("members_selection/", views.staff_selection, name="staff_selection"),
    path("members_selection/staff_selection_resident/", views.staff_selection_resident, name="staff_selection_resident"),
    path("members_selection/staff_selection_non-resident_personal_info/", views.staff_selection_nonres, name="staff_selection_non-resident"),
    # path("members_selection/staff_selection_non-resident_socio/", views.staff_selection_nonres_socio, name="staff_selection_non-resident_socio"),
    path("members_selection/staff_selection_non-resident_supporting_docs/", views.staff_selection_nonres_docs , name="staff_selection_non-resident_docs"),
    path("members_selection/staff_selection_non-resident_role_review/", views.staff_selection_nonres_role_review , name="staff_selection_non-resident_role_review"),
    path("members_list/", views.members_list , name="members_list"),
]