from django.urls import path
from . import api_views

urlpatterns = [
    path('register/', api_views.ResidentRegisterAPIView.as_view(), name='api-resident-register'),
    path('profile/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
    # path('profile/<int:pk>/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
]
