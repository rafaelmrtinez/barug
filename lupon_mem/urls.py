from django.urls import path
from . import views

app_name = "lupon_mem"

urlpatterns = [
    path("cases/", views.case_list, name="case_list"),
    path("cases/<int:case_id>/", views.case_detail, name="case_detail"),
    path("cases/<int:case_id>/forms/add/", views.add_form_choose, name="add_form_choose"),
    path("cases/<int:case_id>/forms/<int:form_id>/build/", views.form_builder, name="form_builder"),
    path("cases/<int:case_id>/submissions/<int:submission_id>/edit/", views.form_builder, name="form_edit"),

    # ajax
    path("api/preview/", views.preview_image, name="preview_image"),   # ?form_id=&case_id=&submission_id=
    path("api/save-answers/", views.save_answers, name="save_answers"),
    path("api/submit-form/", views.submit_form, name="submit_form"),
]
