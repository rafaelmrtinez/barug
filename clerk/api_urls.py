from django.urls import path
from .api_views import *

urlpatterns = [
    path("id-validation-requests/", GetIDValidationRequestsAPIView.as_view(), name="id-validation-requests"),
    path("id-validation-requests/<str:req_id>/", GetIDValidationRequestDetailAPIView.as_view(), name="id_validation_request_detail"),
    path("id-validation/requests/<int:req_id>/approve/", ApprovePersonByClerkAPIView.as_view()),
]