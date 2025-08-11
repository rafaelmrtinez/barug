from django.urls import path
from . import api_views

urlpatterns = [
    path('register/', api_views.ResidentRegisterAPIView.as_view(), name='api-resident-register'),
    path('profile/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
<<<<<<< HEAD
    path('verify/', api_views.PersonVerificationRequestAPIView.as_view(), name='api-resident-verify'),
=======
>>>>>>> b910daa1f305ba4e34ee46579bd1c7883f32bbb9
    # path('profile/<int:pk>/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
]
