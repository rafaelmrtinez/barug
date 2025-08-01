from django.urls import path
from . import views

app_name = 'ai'

urlpatterns = [
    path('c/', views.AIChatView.as_view(), name='chat'),
]
