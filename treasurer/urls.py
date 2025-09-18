from django.urls import path
from . import views

app_name = 'treasurer'

urlpatterns = [
    path("dashboard", views.dashboard, name="dashboard"),
    path("document_requested/", views.docs_requested, name="doc_reqs"),
    path("document_requested/details/<int:doc_id>/", views.doc_details, name="doc_dets"),
]